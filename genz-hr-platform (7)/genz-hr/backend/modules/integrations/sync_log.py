"""
GENZ HR — Integration Sync Logger
Dedicated log store for all data integration events:
  • File uploads (Excel, CSV)
  • Google Sheets sync events
  • Column mapping decisions
  • Row inserts, updates, skips, errors
  • Approval gate triggers from imports

Stored in the company's integration_logs table (isolated per company).
Separate from the audit_log (which tracks Esther's manual edits).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger("genz.synclog")


class SyncSource(str, Enum):
    EXCEL        = "excel"
    GOOGLE_SHEETS = "google_sheets"
    MANUAL       = "manual"


@dataclass
class SyncEvent:
    source:      SyncSource
    event:       str          # e.g. IMPORT_START, ROW_UPDATE, SYNC_ERROR
    company_id:  str
    file_name:   str = ""
    sheet_url:   str = ""
    file_hash:   str = ""
    rows_affected: int = 0
    details:     str = ""     # JSON or plain text detail
    timestamp:   datetime = field(default_factory=datetime.utcnow)
    success:     bool = True

    def to_dict(self) -> dict:
        return {
            "source":        self.source.value,
            "event":         self.event,
            "company_id":    self.company_id,
            "file_name":     self.file_name,
            "sheet_url":     self.sheet_url,
            "file_hash":     self.file_hash[:12] + "..." if self.file_hash else "",
            "rows_affected": self.rows_affected,
            "details":       self.details[:300] if self.details else "",
            "timestamp":     self.timestamp.isoformat(),
            "success":       self.success,
        }


class SyncLogger:
    """
    Per-company sync event logger.
    Uses the company's integration_logs DB table when available,
    falls back to in-memory list for testing.
    """

    def __init__(self, company_id: str):
        self.company_id = company_id
        self._memory_log: list[SyncEvent] = []  # fallback when no DB session

    def log(self, event: SyncEvent):
        """Write a sync event to the DB and in-memory buffer."""
        self._memory_log.append(event)
        self._persist(event)
        level = logging.INFO if event.success else logging.WARNING
        logger.log(level, f"[{event.source.value.upper()}:{event.event}] {event.details[:80]}")

    def _persist(self, event: SyncEvent):
        """Persist to company DB integration_logs table."""
        try:
            from backend.core.database import get_company_session, IntegrationLog
            session = get_company_session(self.company_id)
            record = IntegrationLog(
                company_id    = event.company_id,
                source        = event.source.value,
                event         = event.event,
                file_name     = event.file_name,
                sheet_url     = event.sheet_url,
                file_hash     = event.file_hash,
                rows_affected = event.rows_affected,
                details       = event.details[:1000],
                success       = event.success,
                timestamp     = event.timestamp,
            )
            session.add(record)
            session.commit()
            session.close()
        except Exception as e:
            # DB not available (e.g. testing) — silently continue
            logger.debug(f"Sync log persist skipped: {e}")

    def get_recent(self, limit: int = 50) -> list[dict]:
        """Return most recent sync events for this company."""
        try:
            from backend.core.database import get_company_session, IntegrationLog
            session = get_company_session(self.company_id)
            records = (
                session.query(IntegrationLog)
                .filter(IntegrationLog.company_id == self.company_id)
                .order_by(IntegrationLog.timestamp.desc())
                .limit(limit)
                .all()
            )
            session.close()
            return [
                {
                    "source":        r.source,
                    "event":         r.event,
                    "file_name":     r.file_name,
                    "sheet_url":     r.sheet_url,
                    "rows_affected": r.rows_affected,
                    "details":       r.details,
                    "success":       r.success,
                    "timestamp":     r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for r in records
            ]
        except Exception:
            return [e.to_dict() for e in reversed(self._memory_log[-limit:])]

    def get_last_sync(self, source: SyncSource) -> Optional[SyncEvent]:
        """Return the most recent successful sync event for a source."""
        try:
            from backend.core.database import get_company_session, IntegrationLog
            session = get_company_session(self.company_id)
            record = (
                session.query(IntegrationLog)
                .filter(
                    IntegrationLog.company_id == self.company_id,
                    IntegrationLog.source     == source.value,
                    IntegrationLog.event      == "IMPORT_COMPLETE",
                    IntegrationLog.success    == True,
                )
                .order_by(IntegrationLog.timestamp.desc())
                .first()
            )
            session.close()
            if not record:
                return None
            return SyncEvent(
                source     = SyncSource(record.source),
                event      = record.event,
                company_id = record.company_id,
                file_name  = record.file_name or "",
                sheet_url  = record.sheet_url or "",
                file_hash  = record.file_hash or "",
                timestamp  = record.timestamp,
            )
        except Exception:
            # Fallback to memory
            for evt in reversed(self._memory_log):
                if evt.source == source and evt.event == "IMPORT_COMPLETE":
                    return evt
            return None

    def get_sync_status(self) -> dict:
        """Return current sync status summary for the dashboard."""
        try:
            from backend.core.database import get_company_session, IntegrationLog, DataIntegrationConfig
            session = get_company_session(self.company_id)

            last_excel = (
                session.query(IntegrationLog)
                .filter(
                    IntegrationLog.company_id == self.company_id,
                    IntegrationLog.source     == SyncSource.EXCEL.value,
                    IntegrationLog.success    == True,
                )
                .order_by(IntegrationLog.timestamp.desc())
                .first()
            )
            last_gsheet = (
                session.query(IntegrationLog)
                .filter(
                    IntegrationLog.company_id == self.company_id,
                    IntegrationLog.source     == SyncSource.GOOGLE_SHEETS.value,
                    IntegrationLog.success    == True,
                )
                .order_by(IntegrationLog.timestamp.desc())
                .first()
            )
            config = (
                session.query(DataIntegrationConfig)
                .filter(DataIntegrationConfig.company_id == self.company_id)
                .first()
            )
            session.close()

            return {
                "excel": {
                    "last_sync":  last_excel.timestamp.strftime("%d %b %Y %H:%M") if last_excel else None,
                    "file_name":  last_excel.file_name if last_excel else None,
                    "status":     "synced" if last_excel else "never",
                },
                "google_sheets": {
                    "connected":  bool(config and config.gsheet_id),
                    "sheet_name": config.gsheet_name if config else None,
                    "sheet_url":  config.gsheet_url if config else None,
                    "last_sync":  last_gsheet.timestamp.strftime("%d %b %Y %H:%M") if last_gsheet else None,
                    "auto_sync":  config.auto_sync_enabled if config else False,
                    "sync_interval_min": config.sync_interval_minutes if config else 30,
                    "status":     "synced" if last_gsheet else ("connected" if config and config.gsheet_id else "not_connected"),
                },
            }
        except Exception as e:
            logger.debug(f"get_sync_status error: {e}")
            return {
                "excel":         {"status": "unknown"},
                "google_sheets": {"status": "unknown"},
            }
