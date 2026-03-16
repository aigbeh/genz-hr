"""
GENZ HR — Data Ingestion Engine
Handles reading, hashing, change-detection, and row-level import
for both Excel/CSV and Google Sheets sources.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("genz.ingest")


# ─── File Reading ─────────────────────────────────────────────────────────────

def read_excel(
    file_path: str,
    tab_name:  Optional[str] = None,
) -> tuple[list[str], list[dict]]:
    """
    Read an Excel (.xlsx) or CSV file.
    Returns (headers, rows) where rows is a list of {col: value} dicts.
    """
    import pandas as pd
    path   = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path, sheet_name=tab_name or 0, dtype=str, keep_default_na=False)
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Use .xlsx or .csv")

    df.columns = [str(c).strip() for c in df.columns]
    df = df.fillna("")
    headers = list(df.columns)
    rows    = df.to_dict(orient="records")
    return headers, rows


def read_from_bytes(
    raw_bytes:  bytes,
    filename:   str,
    tab_name:   Optional[str] = None,
) -> tuple[list[str], list[dict]]:
    """
    Read an Excel/CSV from raw bytes (from Streamlit file_uploader).
    """
    import pandas as pd

    suffix = Path(filename).suffix.lower()
    buf    = io.BytesIO(raw_bytes)

    if suffix == ".csv":
        df = pd.read_csv(buf, dtype=str, keep_default_na=False)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(buf, sheet_name=tab_name or 0, dtype=str, keep_default_na=False)
    else:
        raise ValueError(f"Unsupported: {suffix}")

    df.columns = [str(c).strip() for c in df.columns]
    df = df.fillna("")
    return list(df.columns), df.to_dict(orient="records")


def get_excel_sheet_names(file_path: str) -> list[str]:
    """List all sheet/tab names in an .xlsx file."""
    import pandas as pd
    path = Path(file_path)
    if path.suffix.lower() == ".xlsx":
        return pd.ExcelFile(file_path).sheet_names
    return ["Sheet1"]


# ─── Hashing + Change Detection ──────────────────────────────────────────────

def compute_data_hash(rows: list[dict]) -> str:
    """SHA-256 of the serialized row data — for change detection."""
    serialized = json.dumps(rows, sort_keys=True, default=str).encode()
    return hashlib.sha256(serialized).hexdigest()


def compute_file_hash(file_path: str) -> str:
    """SHA-256 of raw file bytes."""
    return hashlib.sha256(Path(file_path).read_bytes()).hexdigest()


def compute_bytes_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def detect_row_changes(
    old_rows: list[dict],
    new_rows: list[dict],
    key_field: str = "employee_id",
) -> dict:
    """
    Compare two row lists, keyed by key_field.
    Returns {inserted: [...], updated: [...], deleted: [...], unchanged_count: int}.
    """
    old_map = {str(r.get(key_field, "")): r for r in old_rows if r.get(key_field)}
    new_map = {str(r.get(key_field, "")): r for r in new_rows if r.get(key_field)}

    inserted   = [r for k, r in new_map.items() if k not in old_map]
    deleted    = [r for k, r in old_map.items() if k not in new_map]
    updated    = []
    unchanged  = 0

    for k, new_row in new_map.items():
        if k in old_map:
            if new_row != old_map[k]:
                updated.append({"old": old_map[k], "new": new_row})
            else:
                unchanged += 1

    return {
        "inserted":        inserted,
        "updated":         updated,
        "deleted":         deleted,
        "unchanged_count": unchanged,
    }


# ─── Row Processing (writes to GENZ HR DB) ───────────────────────────────────

def process_import(
    company_id:     str,
    data_source_id: int,
    rows:           list[dict],
    mappings:       list,          # list[ColumnMapping ORM objects]
    sync_log_id:    int,
    session,
    sync_type:      str = "full",
) -> dict:
    """
    Apply confirmed column mappings and upsert rows into GENZ HR tables.
    Routes salary changes through the approval gate.
    Returns summary dict.
    """
    from backend.core.database import Employee, EmploymentStatus
    from backend.core.integration_models import SyncLog
    from backend.core.approval_gate import submit_action, ActionType

    field_to_col = {m.system_field: m.sheet_column for m in mappings}

    inserted = updated = skipped = errored = approvals = 0
    errors   = []
    start    = datetime.utcnow()

    BATCH = 200
    for batch_start in range(0, len(rows), BATCH):
        batch = rows[batch_start : batch_start + BATCH]
        for row_idx, raw_row in enumerate(batch):
            abs_idx = batch_start + row_idx
            try:
                data = {
                    field: str(raw_row.get(col, "")).strip()
                    for field, col in field_to_col.items()
                    if col in raw_row
                }
                if not any(data.values()):
                    skipped += 1
                    continue

                emp = _find_employee(session, data)
                if emp is None:
                    _create_employee(session, data)
                    inserted += 1
                else:
                    changed, n_approvals = _update_employee(
                        session, emp, data, company_id
                    )
                    approvals += n_approvals
                    if changed:
                        updated += 1
                    else:
                        skipped += 1

            except Exception as e:
                errored += 1
                errors.append({"row": abs_idx, "error": str(e)})
                logger.warning(f"Row {abs_idx} import error: {e}")

        session.commit()

    # Update sync log
    duration = int((datetime.utcnow() - start).total_seconds() * 1000)
    log = session.query(SyncLog).filter(SyncLog.id == sync_log_id).first()
    if log:
        log.status        = "complete" if errored == 0 else "complete_with_errors"
        log.rows_total    = len(rows)
        log.rows_inserted = inserted
        log.rows_updated  = updated
        log.rows_skipped  = skipped
        log.rows_errored  = errored
        log.approvals_queued = approvals
        log.completed_at  = datetime.utcnow()
        log.duration_ms   = duration
        if errors:
            log.error_details = json.dumps(errors[:20])
        session.commit()

    return {
        "rows_total":       len(rows),
        "rows_inserted":    inserted,
        "rows_updated":     updated,
        "rows_skipped":     skipped,
        "rows_errored":     errored,
        "approvals_queued": approvals,
        "duration_ms":      duration,
        "errors":           errors[:20],
    }


# ─── Row helpers ──────────────────────────────────────────────────────────────

def _find_employee(session, data: dict):
    from backend.core.database import Employee
    if data.get("employee_id"):
        emp = session.query(Employee).filter(
            Employee.employee_id == data["employee_id"]
        ).first()
        if emp:
            return emp
    if data.get("email"):
        emp = session.query(Employee).filter(
            Employee.email == data["email"].lower()
        ).first()
        if emp:
            return emp
    first, last = _split_name(data)
    if first and last:
        return session.query(Employee).filter(
            Employee.first_name.ilike(first),
            Employee.last_name.ilike(last),
        ).first()
    return None


def _create_employee(session, data: dict):
    from backend.core.database import Employee, EmploymentStatus
    first, last = _split_name(data)
    if not first:
        raise ValueError("Cannot create employee: no name found")
    emp_id = data.get("employee_id") or f"EMP-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:18]}"
    emp = Employee(
        employee_id     = emp_id,
        first_name      = first,
        last_name       = last or "",
        email           = data.get("email", "").lower() or None,
        phone           = data.get("phone") or None,
        department      = data.get("department") or None,
        position        = data.get("position") or None,
        employment_type = data.get("employment_type", "full-time"),
        status          = EmploymentStatus.active,
        gross_salary    = _parse_float(data.get("gross_salary")),
        bank_name       = data.get("bank_name") or None,
        account_number  = data.get("account_number") or None,
        pension_pin     = data.get("pension_pin") or None,
        tax_id          = data.get("tax_id") or None,
        start_date      = _parse_date(data.get("start_date")),
    )
    session.add(emp)
    logger.info(f"Created employee: {first} {last} ({emp_id})")
    return emp


def _update_employee(session, emp, data: dict, company_id: str) -> tuple[bool, int]:
    """Returns (was_changed, n_approvals_queued)."""
    from backend.core.approval_gate import submit_action, ActionType

    simple_fields = {
        "department": "department", "position": "position",
        "email": "email", "phone": "phone",
        "bank_name": "bank_name", "account_number": "account_number",
        "pension_pin": "pension_pin", "tax_id": "tax_id",
        "employment_type": "employment_type",
    }
    changed    = False
    approvals  = 0

    for data_field, emp_attr in simple_fields.items():
        new_val = data.get(data_field, "").strip()
        if not new_val:
            continue
        old_val = str(getattr(emp, emp_attr, "") or "")
        if new_val != old_val:
            setattr(emp, emp_attr, new_val)
            changed = True

    # Salary changes → gate
    new_salary = _parse_float(data.get("gross_salary"))
    if new_salary and new_salary != emp.gross_salary:
        old = emp.gross_salary or 0
        pct = ((new_salary - old) / old * 100) if old else 0
        submit_action(
            company_id  = company_id,
            action_type = ActionType.SALARY_CHANGE,
            description = (
                f"Salary change from data import: "
                f"{emp.first_name} {emp.last_name} "
                f"₦{old:,.0f} → ₦{new_salary:,.0f} ({pct:+.1f}%)"
            ),
            payload = {
                "employee_id":   emp.id,
                "employee_name": f"{emp.first_name} {emp.last_name}",
                "old_salary":    old,
                "new_salary":    new_salary,
                "pct_change":    round(pct, 2),
                "reason":        "Data import",
                "effective":     date.today().isoformat(),
            },
        )
        approvals += 1

    return changed, approvals


def _split_name(data: dict) -> tuple[str, str]:
    if data.get("full_name"):
        parts = data["full_name"].strip().split(" ", 1)
        return parts[0], parts[1] if len(parts) > 1 else ""
    return data.get("first_name", "").strip(), data.get("last_name", "").strip()


def _parse_float(val: Optional[str]) -> Optional[float]:
    if not val:
        return None
    cleaned = re.sub(r"[^\d.]", "", str(val))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _parse_date(val: Optional[str]) -> Optional[date]:
    if not val:
        return None
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d %B %Y", "%B %d, %Y"]:
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except (ValueError, TypeError):
            pass
    return None
