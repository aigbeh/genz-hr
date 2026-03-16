"""
GENZ HR — Google Sheets Connector
════════════════════════════════════════════════════════════════
Connects to a Google Sheet and syncs HR data into GENZ HR.

Setup (one-time):
  1. Create a Google Cloud project
  2. Enable Google Sheets API + Google Drive API
  3. Create a Service Account and download credentials JSON
  4. Share the Google Sheet with the service account email
  5. Set GOOGLE_CREDENTIALS_PATH in .env

Auto-sync:
  • When enabled, the APScheduler calls sync() on the configured interval
  • Each sync fetches current sheet data, diffs against last snapshot,
    and updates only changed rows (same logic as ExcelImporter)
  • Salary changes always go through the ApprovalGate

Column mapping:
  • Uses the same ColumnMapper engine as ExcelImporter
  • Mappings are stored in DataIntegrationConfig and reused across syncs
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

import pandas as pd

from backend.modules.integrations.column_mapper import map_columns, apply_override, MappingResult
from backend.modules.integrations.sync_log import SyncLogger, SyncEvent, SyncSource

logger = logging.getLogger("genz.gsheets")


# ─── Connection Config ────────────────────────────────────────────────────────

@dataclass
class SheetConfig:
    company_id:           str
    sheet_id:             str              # Google Sheet ID from URL
    sheet_name:           str = "Sheet1"   # Tab name
    credentials_path:     str = ""         # Path to service_account.json
    mapping_overrides:    dict = field(default_factory=dict)
    auto_sync_enabled:    bool = True
    sync_interval_minutes:int  = 30

    def sheet_url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.sheet_id}"


# ─── Sync Result ─────────────────────────────────────────────────────────────

@dataclass
class SheetSyncResult:
    company_id:      str
    sheet_id:        str
    started_at:      datetime = field(default_factory=datetime.utcnow)
    finished_at:     Optional[datetime] = None
    total_rows:      int = 0
    rows_inserted:   int = 0
    rows_updated:    int = 0
    rows_skipped:    int = 0
    rows_errored:    int = 0
    errors:          list[dict] = field(default_factory=list)
    needs_approval:  list[dict] = field(default_factory=list)
    mapping_result:  Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "company_id":    self.company_id,
            "sheet_id":      self.sheet_id,
            "started_at":    self.started_at.isoformat(),
            "finished_at":   self.finished_at.isoformat() if self.finished_at else None,
            "total_rows":    self.total_rows,
            "rows_inserted": self.rows_inserted,
            "rows_updated":  self.rows_updated,
            "rows_skipped":  self.rows_skipped,
            "rows_errored":  self.rows_errored,
            "errors":        self.errors[:10],
            "needs_approval":self.needs_approval[:10],
            "mapping":       self.mapping_result,
        }


# ─── Google Sheets Connector ─────────────────────────────────────────────────

class GoogleSheetsConnector:

    def __init__(self, config: SheetConfig):
        self.config   = config
        self.sync_log = SyncLogger(config.company_id)
        self._client  = None

    # ── Authentication ───────────────────────────────────────────────────────

    def _get_client(self):
        """Initialise gspread client from service account credentials."""
        if self._client:
            return self._client
        try:
            import gspread
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
            ]
            creds_path = self.config.credentials_path or _find_credentials()
            if not creds_path:
                raise FileNotFoundError(
                    "Google credentials not found. "
                    "Set GOOGLE_CREDENTIALS_PATH in .env or place service_account.json "
                    "in the project root."
                )
            creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
            self._client = gspread.authorize(creds)
            return self._client
        except ImportError:
            raise ImportError(
                "gspread not installed. Run: pip install gspread google-auth"
            )

    def test_connection(self) -> dict:
        """Verify the sheet is accessible. Returns {ok, title, sheet_names, error}."""
        try:
            client    = self._get_client()
            workbook  = client.open_by_key(self.config.sheet_id)
            sheets    = [ws.title for ws in workbook.worksheets()]
            return {"ok": True, "title": workbook.title, "sheet_names": sheets}
        except Exception as e:
            logger.error(f"Google Sheets connection test failed: {e}")
            return {"ok": False, "error": str(e)}

    # ── Data Fetch ───────────────────────────────────────────────────────────

    def fetch_as_dataframe(self) -> pd.DataFrame:
        """Fetch current sheet data as a Pandas DataFrame."""
        client   = self._get_client()
        workbook = client.open_by_key(self.config.sheet_id)
        try:
            sheet = workbook.worksheet(self.config.sheet_name)
        except Exception:
            sheet = workbook.get_worksheet(0)

        records = sheet.get_all_records(default_blank="")
        if not records:
            return pd.DataFrame()
        return pd.DataFrame(records).astype(str)

    # ── Sync ────────────────────────────────────────────────────────────────

    def sync(self, requested_by: str = "scheduler") -> SheetSyncResult:
        """
        Fetch the current sheet, diff against last sync snapshot,
        update only changed rows in GENZ HR.
        """
        result = SheetSyncResult(company_id=self.config.company_id, sheet_id=self.config.sheet_id)

        self.sync_log.log(SyncEvent(
            source     = SyncSource.GOOGLE_SHEETS,
            event      = "SYNC_START",
            company_id = self.config.company_id,
            sheet_url  = self.config.sheet_url(),
            details    = f"Sync triggered by {requested_by}",
        ))

        try:
            df = self.fetch_as_dataframe()
            if df.empty:
                self.sync_log.log(SyncEvent(
                    source=SyncSource.GOOGLE_SHEETS, event="SYNC_EMPTY",
                    company_id=self.config.company_id, sheet_url=self.config.sheet_url(),
                    details="Sheet returned no data",
                ))
                result.finished_at = datetime.utcnow()
                return result

            result.total_rows = len(df)

            # ── Column mapping ─────────────────────────────────────────────
            mapping = map_columns(list(df.columns))
            for col, sys_field in self.config.mapping_overrides.items():
                mapping = apply_override(mapping, col, sys_field)
            result.mapping_result = mapping.to_dict()

            # ── Re-use excel importer's row processor ──────────────────────
            from backend.modules.integrations.excel_importer import ExcelImporter, BATCH_SIZE
            importer = ExcelImporter(self.config.company_id)

            for chunk_start in range(0, len(df), BATCH_SIZE):
                chunk = df.iloc[chunk_start : chunk_start + BATCH_SIZE]
                sub_result = _make_sub_result(result)
                importer._process_chunk(chunk, mapping, sub_result, requested_by)
                result.rows_inserted  += sub_result.rows_inserted
                result.rows_updated   += sub_result.rows_updated
                result.rows_skipped   += sub_result.rows_skipped
                result.rows_errored   += sub_result.rows_errored
                result.errors         += sub_result.errors
                result.needs_approval += sub_result.needs_approval

            result.finished_at = datetime.utcnow()
            self.sync_log.log(SyncEvent(
                source        = SyncSource.GOOGLE_SHEETS,
                event         = "IMPORT_COMPLETE",
                company_id    = self.config.company_id,
                sheet_url     = self.config.sheet_url(),
                rows_affected = result.rows_inserted + result.rows_updated,
                details       = json.dumps({
                    "inserted": result.rows_inserted,
                    "updated":  result.rows_updated,
                    "skipped":  result.rows_skipped,
                    "errors":   result.rows_errored,
                }),
            ))

        except Exception as e:
            result.errors.append({"row": "sheet", "error": str(e)})
            result.finished_at = datetime.utcnow()
            logger.error(f"Google Sheets sync failed: {e}")
            self.sync_log.log(SyncEvent(
                source=SyncSource.GOOGLE_SHEETS, event="SYNC_ERROR",
                company_id=self.config.company_id, sheet_url=self.config.sheet_url(),
                details=str(e), success=False,
            ))

        return result

    def get_preview(self, max_rows: int = 5) -> dict:
        """Fetch header + sample rows for the mapping preview UI."""
        try:
            df      = self.fetch_as_dataframe()
            mapping = map_columns(list(df.columns))
            return {
                "sheet_id":    self.config.sheet_id,
                "sheet_name":  self.config.sheet_name,
                "sheet_url":   self.config.sheet_url(),
                "total_rows":  len(df),
                "columns":     list(df.columns),
                "preview":     df.head(max_rows).fillna("").to_dict(orient="records"),
                "mapping":     mapping.to_dict(),
                "needs_review":mapping.needs_review,
            }
        except Exception as e:
            return {"error": str(e)}


# ─── Scheduler Integration ────────────────────────────────────────────────────

def setup_auto_sync_jobs(scheduler, company_id: str):
    """
    Register Google Sheets auto-sync job for a company.
    Called when a Google Sheet connection is saved or on startup.
    """
    try:
        from backend.core.database import get_company_session, DataIntegrationConfig
        session = get_company_session(company_id)
        config_row = session.query(DataIntegrationConfig).filter(
            DataIntegrationConfig.company_id   == company_id,
            DataIntegrationConfig.auto_sync_enabled == True,
        ).first()
        session.close()

        if not config_row or not config_row.gsheet_id:
            return

        job_id = f"gsheet_sync_{company_id}"

        def _run():
            cfg = SheetConfig(
                company_id            = company_id,
                sheet_id              = config_row.gsheet_id,
                sheet_name            = config_row.gsheet_tab or "Sheet1",
                credentials_path      = config_row.credentials_path or "",
                mapping_overrides     = json.loads(config_row.mapping_json or "{}"),
                sync_interval_minutes = config_row.sync_interval_minutes or 30,
            )
            connector = GoogleSheetsConnector(cfg)
            result    = connector.sync(requested_by="scheduler")
            logger.info(
                f"Auto-sync {company_id}: "
                f"+{result.rows_inserted} / ~{result.rows_updated} / "
                f"skip {result.rows_skipped}"
            )

        scheduler.add_job(
            _run,
            "interval",
            minutes  = config_row.sync_interval_minutes or 30,
            id       = job_id,
            replace_existing = True,
        )
        logger.info(f"Auto-sync job registered for {company_id} every {config_row.sync_interval_minutes} min")

    except Exception as e:
        logger.warning(f"Could not set up auto-sync for {company_id}: {e}")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _find_credentials() -> Optional[str]:
    """Look for service_account.json in common locations."""
    import os
    candidates = [
        os.environ.get("GOOGLE_CREDENTIALS_PATH", ""),
        "service_account.json",
        "credentials/service_account.json",
        "config/service_account.json",
    ]
    for path in candidates:
        if path and __import__("os.path", fromlist=["exists"]).exists(path):
            return path
    return None


def _make_sub_result(parent):
    """Tiny proxy so chunk processor can accumulate into parent result."""
    from backend.modules.integrations.excel_importer import ImportResult
    sub = ImportResult(source="gsheet", company_id=parent.company_id)
    return sub
