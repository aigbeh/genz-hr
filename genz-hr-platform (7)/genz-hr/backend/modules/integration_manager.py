"""
GENZ HR — Integration Manager
Orchestrates the full data sync lifecycle:
  1. Register a data source (Excel file or Google Sheet)
  2. Read raw data
  3. Auto-propose column mappings
  4. Apply confirmed mappings
  5. Upsert data into the correct HR modules
  6. Log every sync event

This is the single entry point used by both the API and the dashboard.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("genz.integration")


# ─── Register a new data source ───────────────────────────────────────────────

def register_excel_source(
    company_id: str,
    file_path:  str,
    name:       str,
    session,
    tab_name:   Optional[str] = None,
    auto_sync:  bool = False,
) -> dict:
    """
    Register an uploaded Excel/CSV file as a data source.
    Reads headers, proposes mappings — does NOT import data yet.
    Returns {data_source_id, proposals} for the dashboard to confirm.
    """
    from backend.core.integration_models import DataSource
    from backend.modules.data_ingestion import read_excel, compute_data_hash
    from backend.modules.column_mapper import propose_mappings

    # Read headers only (skip body for large files until mappings confirmed)
    headers, rows = read_excel(file_path, tab_name)
    data_hash     = compute_data_hash(rows)

    # Check if this source already exists (same path)
    existing = session.query(DataSource).filter(
        DataSource.file_path == file_path
    ).first()

    if existing:
        existing.name          = name
        existing.tab_name      = tab_name
        existing.row_count     = len(rows)
        existing.last_hash     = data_hash
        existing.status        = "pending"
        existing.auto_sync     = auto_sync
        session.commit()
        source_id = existing.id
    else:
        ds = DataSource(
            name        = name,
            source_type = "excel",
            file_path   = file_path,
            tab_name    = tab_name,
            row_count   = len(rows),
            last_hash   = data_hash,
            auto_sync   = auto_sync,
            status      = "pending",
            created_by  = "Esther",
        )
        session.add(ds)
        session.commit()
        source_id = ds.id

    proposals = propose_mappings(headers)
    return {
        "data_source_id": source_id,
        "name":           name,
        "source_type":    "excel",
        "headers":        headers,
        "row_count":      len(rows),
        "proposals":      [p.to_dict() for p in proposals],
        "needs_review":   [p.to_dict() for p in proposals if p.needs_review],
    }


def register_gsheet_source(
    company_id:       str,
    sheet_url:        str,
    name:             str,
    session,
    tab_name:         Optional[str] = None,
    auto_sync:        bool = True,
    sync_interval:    int  = 3600,
    credentials_path: Optional[str] = None,
) -> dict:
    """
    Register a Google Sheet as a live data source.
    Reads headers and proposes mappings — does NOT import data yet.
    """
    from backend.core.integration_models import DataSource
    from backend.modules.gsheets_connector import (
        extract_sheet_id, read_sheet, read_sheet_mock,
        is_configured, compute_data_hash
    )
    from backend.modules.data_ingestion import compute_data_hash
    from backend.modules.column_mapper import propose_mappings

    sheet_id = extract_sheet_id(sheet_url)

    # Read headers (mock if not configured)
    if is_configured(credentials_path):
        headers, rows = read_sheet(sheet_id, tab_name, credentials_path)
    else:
        headers, rows = read_sheet_mock(tab_name)
        logger.warning("Google Sheets not configured — using mock data for mapping preview")

    data_hash = compute_data_hash(rows)

    existing = session.query(DataSource).filter(
        DataSource.sheet_id == sheet_id
    ).first()

    if existing:
        existing.name          = name
        existing.tab_name      = tab_name
        existing.row_count     = len(rows)
        existing.last_hash     = data_hash
        existing.auto_sync     = auto_sync
        existing.sync_interval = sync_interval
        existing.status        = "pending"
        session.commit()
        source_id = existing.id
    else:
        ds = DataSource(
            name          = name,
            source_type   = "google_sheet",
            sheet_url     = sheet_url,
            sheet_id      = sheet_id,
            tab_name      = tab_name,
            row_count     = len(rows),
            last_hash     = data_hash,
            auto_sync     = auto_sync,
            sync_interval = sync_interval,
            status        = "pending",
            created_by    = "Esther",
        )
        session.add(ds)
        session.commit()
        source_id = ds.id

    proposals = propose_mappings(headers)
    return {
        "data_source_id": source_id,
        "name":           name,
        "source_type":    "google_sheet",
        "sheet_id":       sheet_id,
        "headers":        headers,
        "row_count":      len(rows),
        "proposals":      [p.to_dict() for p in proposals],
        "needs_review":   [p.to_dict() for p in proposals if p.needs_review],
        "mock_mode":      not is_configured(credentials_path),
    }


# ─── Save confirmed mappings ──────────────────────────────────────────────────

def save_mappings(
    data_source_id: int,
    proposals:      list[dict],
    overrides:      dict,        # {sheet_column: system_field}
    session,
) -> int:
    """
    Persist confirmed column mappings to the DB.
    Returns the number of mappings saved.
    """
    from backend.core.integration_models import ColumnMapping
    from backend.modules.column_mapper import (
        MappingProposal, ActionType, apply_confirmed_mappings
    )

    # Delete old mappings for this source
    session.query(ColumnMapping).filter(
        ColumnMapping.data_source_id == data_source_id
    ).delete()

    # Rebuild from proposals + overrides
    proposal_objs = [MappingProposal(**{k: v for k, v in p.items()
                     if k in MappingProposal.__dataclass_fields__}) for p in proposals]
    confirmed     = apply_confirmed_mappings(proposal_objs, overrides)

    saved = 0
    for p in confirmed:
        if p.system_field and p.system_field != "__unmapped__" and p.method != "skip":
            record = ColumnMapping(
                data_source_id = data_source_id,
                sheet_column   = p.sheet_column,
                system_field   = p.system_field,
                target_module  = p.target_module or "employees",
                transform      = p.field_type,
                is_key_field   = p.is_key_field,
                confirmed_by   = "Esther" if p.sheet_column in overrides else "auto",
            )
            session.add(record)
            saved += 1

    session.commit()
    logger.info(f"Saved {saved} column mappings for source {data_source_id}")
    return saved


# ─── Run a full sync ──────────────────────────────────────────────────────────

def run_sync(
    company_id:       str,
    data_source_id:   int,
    session,
    trigger:          str = "manual",
    credentials_path: Optional[str] = None,
    force:            bool = False,
) -> dict:
    """
    Execute a full or delta sync for a data source.

    Delta sync: skips if data hash unchanged (unless force=True).
    Full sync:  processes all rows.

    Returns sync result summary.
    """
    from backend.core.integration_models import DataSource, ColumnMapping, SyncLog
    from backend.modules.data_ingestion import (
        read_excel, read_from_bytes, compute_data_hash, process_import
    )
    from backend.modules.gsheets_connector import (
        read_sheet, read_sheet_mock, is_configured, detect_changes, extract_sheet_id
    )

    ds = session.query(DataSource).filter(DataSource.id == data_source_id).first()
    if not ds:
        return {"error": f"Data source {data_source_id} not found"}

    mappings = session.query(ColumnMapping).filter(
        ColumnMapping.data_source_id == data_source_id
    ).all()
    if not mappings:
        return {"error": "No column mappings configured. Please confirm mappings first."}

    # ── Create sync log entry ─────────────────────────────────────────────────
    sync_log = SyncLog(
        data_source_id = data_source_id,
        sync_type      = "full",
        trigger        = trigger,
        status         = "running",
        started_at     = datetime.utcnow(),
        triggered_by   = trigger,
    )
    session.add(sync_log)
    session.commit()

    try:
        # ── Fetch data ────────────────────────────────────────────────────────
        if ds.source_type == "excel":
            if not ds.file_path or not Path(ds.file_path).exists():
                raise FileNotFoundError(f"File not found: {ds.file_path}")
            headers, rows = read_excel(ds.file_path, ds.tab_name)

        elif ds.source_type == "google_sheet":
            if is_configured(credentials_path):
                has_changed, new_hash, headers, rows = detect_changes(
                    ds.sheet_id, ds.last_hash if not force else None,
                    ds.tab_name, credentials_path
                )
                if not has_changed and not force:
                    # No changes — skip
                    sync_log.status       = "complete"
                    sync_log.rows_total   = 0
                    sync_log.rows_skipped = ds.row_count or 0
                    sync_log.completed_at = datetime.utcnow()
                    sync_log.duration_ms  = 0
                    session.commit()
                    return {
                        "status": "skipped", "reason": "No changes detected",
                        "rows_total": 0, "rows_skipped": ds.row_count or 0,
                        "last_synced": ds.last_synced_at.isoformat() if ds.last_synced_at else None,
                    }
            else:
                headers, rows = read_sheet_mock(ds.tab_name)

        else:
            raise ValueError(f"Unknown source type: {ds.source_type}")

        new_hash = compute_data_hash(rows)

        # ── Process import ────────────────────────────────────────────────────
        result = process_import(
            company_id     = company_id,
            data_source_id = data_source_id,
            rows           = rows,
            mappings       = mappings,
            sync_log_id    = sync_log.id,
            session        = session,
            sync_type      = "full",
        )

        # ── Update data source record ─────────────────────────────────────────
        ds.last_synced_at = datetime.utcnow()
        ds.last_hash      = new_hash
        ds.row_count      = len(rows)
        ds.status         = "active"
        ds.error_message  = None
        session.commit()

        logger.info(
            f"Sync complete — source={data_source_id} company={company_id} "
            f"inserted={result['rows_inserted']} updated={result['rows_updated']} "
            f"errors={result['rows_errored']}"
        )
        return {**result, "status": "complete", "source_id": data_source_id}

    except Exception as e:
        # Update source and log with error
        ds.status        = "error"
        ds.error_message = str(e)
        sync_log.status       = "failed"
        sync_log.completed_at = datetime.utcnow()
        session.commit()
        logger.error(f"Sync failed for source {data_source_id}: {e}")
        return {"error": str(e), "status": "failed", "source_id": data_source_id}


# ─── Scheduler Hook ───────────────────────────────────────────────────────────

def run_auto_syncs(company_id: str, session):
    """
    Called by the background scheduler to auto-sync Google Sheets
    that have auto_sync=True and are due for a refresh.
    """
    from backend.core.integration_models import DataSource
    from datetime import timedelta

    now     = datetime.utcnow()
    sources = session.query(DataSource).filter(
        DataSource.source_type == "google_sheet",
        DataSource.auto_sync   == True,
        DataSource.status      != "error",
    ).all()

    synced = 0
    for ds in sources:
        interval = ds.sync_interval or 3600
        if ds.last_synced_at and (now - ds.last_synced_at).total_seconds() < interval:
            continue   # Not due yet
        result = run_sync(company_id, ds.id, session, trigger="schedule")
        if result.get("status") not in ("skipped",):
            synced += 1

    return synced


# ─── List sources and logs ────────────────────────────────────────────────────

def list_data_sources(company_id: str, session) -> list[dict]:
    from backend.core.integration_models import DataSource, SyncLog

    sources = session.query(DataSource).order_by(DataSource.created_at.desc()).all()
    result  = []
    for ds in sources:
        last_log = session.query(SyncLog).filter(
            SyncLog.data_source_id == ds.id
        ).order_by(SyncLog.started_at.desc()).first()

        result.append({
            "id":            ds.id,
            "name":          ds.name,
            "source_type":   ds.source_type,
            "status":        ds.status,
            "row_count":     ds.row_count,
            "tab_name":      ds.tab_name,
            "auto_sync":     ds.auto_sync,
            "sync_interval": ds.sync_interval,
            "last_synced_at": ds.last_synced_at.isoformat() if ds.last_synced_at else None,
            "error_message": ds.error_message,
            "last_sync_result": {
                "status":        last_log.status,
                "rows_inserted": last_log.rows_inserted,
                "rows_updated":  last_log.rows_updated,
                "rows_errored":  last_log.rows_errored,
                "duration_ms":   last_log.duration_ms,
            } if last_log else None,
        })
    return result


def get_sync_history(data_source_id: int, session, limit: int = 20) -> list[dict]:
    from backend.core.integration_models import SyncLog

    logs = session.query(SyncLog).filter(
        SyncLog.data_source_id == data_source_id
    ).order_by(SyncLog.started_at.desc()).limit(limit).all()

    return [{
        "id":            log.id,
        "sync_type":     log.sync_type,
        "trigger":       log.trigger,
        "status":        log.status,
        "rows_total":    log.rows_total,
        "rows_inserted": log.rows_inserted,
        "rows_updated":  log.rows_updated,
        "rows_skipped":  log.rows_skipped,
        "rows_errored":  log.rows_errored,
        "duration_ms":   log.duration_ms,
        "started_at":    log.started_at.isoformat() if log.started_at else None,
        "completed_at":  log.completed_at.isoformat() if log.completed_at else None,
    } for log in logs]
