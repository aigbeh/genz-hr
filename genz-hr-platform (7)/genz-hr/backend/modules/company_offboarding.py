"""
GENZ HR — Company Offboarding & Restore Module
===============================================
Three operations:

1. EXPORT  — Download all company data as a structured ZIP archive
              (Excel sheets + metadata JSON, readable by humans)

2. OFFBOARD — Soft-delete: removes from active platform, archives all data,
               keeps a snapshot in companies/_archived/ so it can be restored.
               Does NOT permanently destroy data.

3. RESTORE  — Re-registers a previously offboarded company from its archive,
               re-creates the database, and spawns a fresh GENZ Agent.

Archive format (ZIP):
    company_export_{company_id}_{date}.zip
    ├── company_info.json         — Registry metadata
    ├── employees.xlsx            — All employee records
    ├── payroll.xlsx              — All payroll records
    ├── candidates.xlsx           — Recruitment pipeline
    ├── task_sheets.xlsx          — Performance data
    ├── attendance.xlsx           — Attendance records
    ├── leave_requests.xlsx       — Leave history
    ├── audit_log.xlsx            — Full audit trail
    └── hr_data.db                — Raw SQLite database (for restore)
"""
from __future__ import annotations

import io
import json
import logging
import shutil
import zipfile
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger("genz.offboard")


# ─── Export ───────────────────────────────────────────────────────────────────

def export_company_data(company_id: str, company_name: str) -> bytes:
    """
    Export all company data into a single downloadable ZIP archive.

    Returns raw ZIP bytes ready for st.download_button.
    The archive is also saved to companies/_archived/ for restore purposes.
    """
    from backend.core.config import COMPANIES_DIR
    from backend.core.database import (
        get_company_session, Employee, Candidate, TaskSheet,
        AttendanceRecord, LeaveRequest, PayrollRecord, AuditLog
    )

    session       = get_company_session(company_id)
    buf           = io.BytesIO()
    today_str     = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name  = f"company_export_{company_id}_{today_str}"

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:

        # ── company_info.json ─────────────────────────────────────────────────
        from backend.core.database import MasterSession, CompanyRegistry
        master = MasterSession()
        co = master.query(CompanyRegistry).filter(CompanyRegistry.id == company_id).first()
        master.close()

        company_info = {
            "company_id":    company_id,
            "company_name":  company_name,
            "industry":      co.industry if co else "",
            "size":          co.size if co else "",
            "contact_email": co.contact_email if co else "",
            "onboarded_at":  co.onboarded_at.isoformat() if co and co.onboarded_at else "",
            "exported_at":   datetime.utcnow().isoformat(),
            "export_version":"1.0",
            "platform":      "GENZ HR",
            "restore_hint":  (
                "To restore this company: Go to Companies → Restore Company → "
                "upload this ZIP file and enter the company ID."
            ),
        }
        zf.writestr(
            f"{archive_name}/company_info.json",
            json.dumps(company_info, indent=2)
        )

        # ── employees.xlsx ────────────────────────────────────────────────────
        employees = session.query(Employee).all()
        if employees:
            emp_data = []
            for e in employees:
                emp_data.append({
                    "EmployeeID":      e.employee_id,
                    "FirstName":       e.first_name,
                    "LastName":        e.last_name,
                    "Email":           e.email or "",
                    "Phone":           e.phone or "",
                    "Department":      e.department or "",
                    "Position":        e.position or "",
                    "EmploymentType":  e.employment_type or "full-time",
                    "Status":          e.status.value if e.status else "active",
                    "GrossSalary":     e.gross_salary or 0,
                    "BankName":        e.bank_name or "",
                    "AccountNumber":   e.account_number or "",
                    "PensionPIN":      e.pension_pin or "",
                    "TaxID":           e.tax_id or "",
                    "StartDate":       str(e.start_date) if e.start_date else "",
                    "EndDate":         str(e.end_date) if e.end_date else "",
                    "CreatedAt":       str(e.created_at) if e.created_at else "",
                })
            zf.writestr(f"{archive_name}/employees.xlsx", _df_to_excel_bytes(pd.DataFrame(emp_data)))

        # ── payroll.xlsx ──────────────────────────────────────────────────────
        payroll = session.query(PayrollRecord).all()
        emp_map = {e.id: f"{e.first_name} {e.last_name}" for e in employees}
        if payroll:
            pay_data = [{
                "EmployeeName":     emp_map.get(p.employee_id, ""),
                "Period":           p.period or "",
                "GrossSalary":      p.gross_salary or 0,
                "BasicSalary":      p.basic_salary or 0,
                "HousingAllowance": p.housing_allowance or 0,
                "TransportAllow":   p.transport_allowance or 0,
                "PAYETax":          p.paye_tax or 0,
                "PensionEmployee":  p.pension_employee or 0,
                "PensionEmployer":  p.pension_employer or 0,
                "NHFDeduction":     p.nhf_deduction or 0,
                "OtherDeductions":  p.other_deductions or 0,
                "PerformanceBonus": p.performance_bonus or 0,
                "NetSalary":        p.net_salary or 0,
                "Status":           p.status or "draft",
                "AnomalyFlag":      p.anomaly_flag or False,
                "AnomalyReason":    p.anomaly_reason or "",
                "ApprovedBy":       p.approved_by or "",
                "ApprovedAt":       str(p.approved_at) if p.approved_at else "",
                "CreatedAt":        str(p.created_at) if p.created_at else "",
            } for p in payroll]
            zf.writestr(f"{archive_name}/payroll.xlsx", _df_to_excel_bytes(pd.DataFrame(pay_data)))

        # ── candidates.xlsx ───────────────────────────────────────────────────
        candidates = session.query(Candidate).all()
        if candidates:
            cand_data = [{
                "Name":             c.name,
                "Email":            c.email or "",
                "Phone":            c.phone or "",
                "PositionApplied":  c.position_applied or "",
                "EducationScore":   c.education_score or 0,
                "SkillsScore":      c.skills_score or 0,
                "ExperienceScore":  c.experience_score or 0,
                "KeywordScore":     c.keyword_score or 0,
                "TotalScore":       c.total_score or 0,
                "EstherOverride":   c.esther_override_score or "",
                "Shortlisted":      c.shortlisted or False,
                "InterviewStatus":  c.interview_status or "",
                "InterviewNotes":   c.interview_notes or "",
                "AiSummary":        c.ai_summary or "",
                "AppliedAt":        str(c.applied_at) if c.applied_at else "",
            } for c in candidates]
            zf.writestr(f"{archive_name}/candidates.xlsx", _df_to_excel_bytes(pd.DataFrame(cand_data)))

        # ── task_sheets.xlsx ──────────────────────────────────────────────────
        sheets = session.query(TaskSheet).all()
        if sheets:
            ts_data = [{
                "EmployeeName":    emp_map.get(s.employee_id, ""),
                "Period":          s.period or "",
                "PeriodType":      s.period_type or "",
                "CompletionPct":   s.completion_pct or 0,
                "PerformanceScore":s.performance_score or 0,
                "BonusEligible":   s.bonus_eligible or False,
                "LeadFeedback":    s.lead_feedback or "",
                "AiAnalysis":      s.ai_analysis or "",
                "Tasks":           json.dumps(s.tasks) if s.tasks else "[]",
                "CreatedAt":       str(s.created_at) if s.created_at else "",
            } for s in sheets]
            zf.writestr(f"{archive_name}/task_sheets.xlsx", _df_to_excel_bytes(pd.DataFrame(ts_data)))

        # ── attendance.xlsx ───────────────────────────────────────────────────
        attendance = session.query(AttendanceRecord).all()
        if attendance:
            att_data = [{
                "EmployeeName":      emp_map.get(a.employee_id, ""),
                "Date":              str(a.date) if a.date else "",
                "CheckIn":           str(a.check_in) if a.check_in else "",
                "CheckOut":          str(a.check_out) if a.check_out else "",
                "TaskActivityScore": a.task_activity_score or 0,
                "CommsActivityScore":a.comms_activity_score or 0,
                "MeetingScore":      a.meeting_score or 0,
                "PresenceScore":     a.presence_score or 0,
                "IsAbsent":          a.is_absent or False,
                "IsApprovedLeave":   a.is_approved_leave or False,
                "Notes":             a.notes or "",
            } for a in attendance]
            zf.writestr(f"{archive_name}/attendance.xlsx", _df_to_excel_bytes(pd.DataFrame(att_data)))

        # ── leave_requests.xlsx ───────────────────────────────────────────────
        leaves = session.query(LeaveRequest).all()
        if leaves:
            leave_data = [{
                "EmployeeName": emp_map.get(l.employee_id, ""),
                "LeaveType":    l.leave_type or "",
                "StartDate":    str(l.start_date) if l.start_date else "",
                "EndDate":      str(l.end_date) if l.end_date else "",
                "Reason":       l.reason or "",
                "Status":       l.status or "",
                "ApprovedBy":   l.approved_by or "",
                "CreatedAt":    str(l.created_at) if l.created_at else "",
            } for l in leaves]
            zf.writestr(f"{archive_name}/leave_requests.xlsx", _df_to_excel_bytes(pd.DataFrame(leave_data)))

        # ── audit_log.xlsx ────────────────────────────────────────────────────
        audit = session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(5000).all()
        if audit:
            audit_data = [{
                "Timestamp":   str(a.timestamp) if a.timestamp else "",
                "User":        a.user or "",
                "Action":      a.action or "",
                "Module":      a.module or "",
                "RecordType":  a.record_type or "",
                "RecordID":    a.record_id or "",
                "FieldChanged":a.field_changed or "",
                "OldValue":    a.old_value or "",
                "NewValue":    a.new_value or "",
            } for a in audit]
            zf.writestr(f"{archive_name}/audit_log.xlsx", _df_to_excel_bytes(pd.DataFrame(audit_data)))

        # ── raw SQLite DB (for perfect restore) ───────────────────────────────
        from backend.core.config import COMPANIES_DIR
        db_path = COMPANIES_DIR / company_id / "hr_data.db"
        if db_path.exists():
            zf.write(db_path, f"{archive_name}/hr_data.db")

    session.close()

    raw_bytes = buf.getvalue()

    # Also save a copy to _archived/ for restore
    _save_archive(company_id, archive_name, raw_bytes)

    return raw_bytes


def _df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Convert a DataFrame to Excel bytes in memory."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return buf.getvalue()


def _save_archive(company_id: str, archive_name: str, zip_bytes: bytes):
    """Persist the export ZIP to disk for future restore."""
    from backend.core.config import COMPANIES_DIR
    archive_dir = COMPANIES_DIR / "_archived"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{archive_name}.zip"
    archive_path.write_bytes(zip_bytes)
    logger.info(f"Archive saved: {archive_path}")


# ─── Offboard (soft delete) ───────────────────────────────────────────────────

def offboard_company(company_id: str, reason: str = "") -> dict:
    """
    Soft-delete a company:
    1. Export all data to _archived/
    2. Mark as inactive in master registry
    3. Shut down the GENZ Agent
    4. Remove the company data directory
    5. Keep the archive for restore

    Returns the export bytes + metadata.
    """
    from backend.core.database import MasterSession, CompanyRegistry
    from backend.core.config import COMPANIES_DIR

    # Get company info
    master  = MasterSession()
    company = master.query(CompanyRegistry).filter(CompanyRegistry.id == company_id).first()
    if not company:
        master.close()
        raise ValueError(f"Company '{company_id}' not found")

    company_name = company.name

    # Step 1: Export
    logger.info(f"Offboarding {company_name} — exporting data first...")
    try:
        zip_bytes = export_company_data(company_id, company_name)
    except Exception as e:
        master.close()
        raise RuntimeError(f"Export failed before offboarding — aborting. Error: {e}")

    # Step 2: Write offboard metadata to archive folder
    from backend.core.config import COMPANIES_DIR
    archive_dir = COMPANIES_DIR / "_archived"
    archive_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "company_id":    company_id,
        "company_name":  company_name,
        "industry":      company.industry or "",
        "size":          company.size or "",
        "contact_email": company.contact_email or "",
        "onboarded_at":  company.onboarded_at.isoformat() if company.onboarded_at else "",
        "offboarded_at": datetime.utcnow().isoformat(),
        "offboard_reason": reason,
    }
    meta_path = archive_dir / f"{company_id}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    # Step 3: Mark inactive
    company.is_active    = False
    company.agent_status = "offboarded"
    master.commit()
    master.close()

    # Step 4: Shut down agent
    try:
        from backend.agents.genz_director import director
        if company_id in director._agents:
            director._agents[company_id].close()
            del director._agents[company_id]
        # Also evict from DB session cache
        from backend.core.database import _engines, _sessions
        if company_id in _engines:
            _engines[company_id].dispose()
            del _engines[company_id]
        if company_id in _sessions:
            del _sessions[company_id]
    except Exception as e:
        logger.warning(f"Agent shutdown warning: {e}")

    # Step 5: Remove data directory
    company_dir = COMPANIES_DIR / company_id
    if company_dir.exists():
        try:
            shutil.rmtree(company_dir)
            logger.info(f"Removed company dir: {company_dir}")
        except Exception as e:
            logger.warning(f"Could not remove {company_dir}: {e}")

    logger.info(f"Offboarding complete for {company_name} ({company_id})")
    return {
        "company_id":   company_id,
        "company_name": company_name,
        "offboarded":   True,
        "archive_saved": True,
        "zip_bytes":    zip_bytes,
    }


# ─── List Archives ────────────────────────────────────────────────────────────

def list_archived_companies() -> list[dict]:
    """Return metadata for all archived (offboarded) companies."""
    from backend.core.config import COMPANIES_DIR
    archive_dir = COMPANIES_DIR / "_archived"
    if not archive_dir.exists():
        return []

    result = []
    for meta_file in archive_dir.glob("*_meta.json"):
        try:
            meta = json.loads(meta_file.read_text())
            # Find matching archive ZIP
            zip_pattern = f"company_export_{meta['company_id']}_*.zip"
            zips = sorted(archive_dir.glob(zip_pattern), reverse=True)
            meta["archive_zip"] = str(zips[0]) if zips else None
            meta["archive_zip_name"] = zips[0].name if zips else None
            result.append(meta)
        except Exception as e:
            logger.warning(f"Could not read meta {meta_file}: {e}")

    return sorted(result, key=lambda x: x.get("offboarded_at", ""), reverse=True)


def get_archive_zip_bytes(company_id: str) -> Optional[bytes]:
    """Return the ZIP bytes for an archived company (latest export)."""
    from backend.core.config import COMPANIES_DIR
    archive_dir = COMPANIES_DIR / "_archived"
    if not archive_dir.exists():
        return None
    pattern = f"company_export_{company_id}_*.zip"
    zips = sorted(archive_dir.glob(pattern), reverse=True)
    if not zips:
        return None
    return zips[0].read_bytes()


# ─── Restore ──────────────────────────────────────────────────────────────────

def restore_company_from_zip(zip_bytes: bytes, company_id: str) -> dict:
    """
    Restore a previously offboarded company from a ZIP archive.

    Steps:
    1. Validate the ZIP contains company_info.json
    2. Re-register the company in master registry
    3. Recreate the company data directory
    4. If hr_data.db is in the ZIP, restore it (full DB restore)
    5. Otherwise import from Excel sheets (data-only restore)
    6. Spawn a new GENZ Agent

    Returns restore summary.
    """
    from backend.core.database import (
        MasterSession, CompanyRegistry, init_company_db
    )
    from backend.core.config import COMPANIES_DIR, get_company_dir

    # ── Step 1: Read and validate ZIP ────────────────────────────────────────
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except Exception as e:
        raise ValueError(f"Invalid ZIP file: {e}")

    names = zf.namelist()
    if not any("company_info.json" in n for n in names):
        raise ValueError("Invalid archive: missing company_info.json. Only GENZ HR export ZIPs are supported.")

    # Read company_info
    info_name = next(n for n in names if "company_info.json" in n)
    archive_prefix = info_name.replace("/company_info.json", "").strip("/") + "/"
    company_info = json.loads(zf.read(info_name).decode())
    archive_company_id = company_info.get("company_id", company_id)

    # Use the provided company_id (allows renaming on restore)
    target_id = company_id.strip().lower().replace(" ", "_")

    # ── Step 2: Check not already active ─────────────────────────────────────
    master = MasterSession()
    existing = master.query(CompanyRegistry).filter(CompanyRegistry.id == target_id).first()

    if existing and existing.is_active:
        master.close()
        raise ValueError(f"Company '{target_id}' is already active on this platform.")

    if existing:
        # Re-activate existing (was soft-deleted)
        existing.is_active    = True
        existing.agent_status = "idle"
        master.commit()
        logger.info(f"Re-activated existing registry entry for {target_id}")
    else:
        # Create fresh registry entry
        new_co = CompanyRegistry(
            id             = target_id,
            name           = company_info.get("company_name", target_id),
            industry       = company_info.get("industry", ""),
            size           = company_info.get("size", "startup"),
            contact_email  = company_info.get("contact_email", ""),
            is_active      = True,
            agent_status   = "idle",
            onboarded_at   = datetime.utcnow(),
        )
        master.add(new_co)
        master.commit()
        logger.info(f"Created fresh registry entry for {target_id}")

    company_name = existing.name if existing else company_info.get("company_name", target_id)
    master.close()

    # ── Step 3: Create data directory ────────────────────────────────────────
    get_company_dir(target_id)  # creates uploads/, reports/, templates/ etc.

    # ── Step 4: Try full DB restore from hr_data.db ───────────────────────────
    db_entries = [n for n in names if n.endswith("hr_data.db")]
    restored_from_db = False

    if db_entries:
        try:
            from backend.core.config import COMPANIES_DIR
            dest_db = COMPANIES_DIR / target_id / "hr_data.db"
            dest_db.parent.mkdir(parents=True, exist_ok=True)
            dest_db.write_bytes(zf.read(db_entries[0]))
            # Ensure session cache uses the restored DB
            from backend.core.database import _engines, _sessions
            if target_id in _engines:
                _engines[target_id].dispose()
                del _engines[target_id]
            if target_id in _sessions:
                del _sessions[target_id]
            # Re-initialize so SQLAlchemy picks up the restored file
            init_company_db(target_id)
            restored_from_db = True
            logger.info(f"Restored DB from hr_data.db for {target_id}")
        except Exception as e:
            logger.warning(f"DB restore failed, falling back to Excel: {e}")

    # ── Step 5: Fallback — import from Excel sheets ───────────────────────────
    imported_employees = 0
    if not restored_from_db:
        emp_entries = [n for n in names if "employees.xlsx" in n]
        if emp_entries:
            try:
                imported_employees = _restore_employees_from_excel(
                    zf.read(emp_entries[0]), target_id
                )
                logger.info(f"Restored {imported_employees} employees from Excel for {target_id}")
            except Exception as e:
                logger.warning(f"Employee Excel restore warning: {e}")

    zf.close()

    # ── Step 6: Spawn GENZ Agent ──────────────────────────────────────────────
    try:
        from backend.agents.genz_director import director
        director.get_agent(target_id)  # initializes the agent
        logger.info(f"GENZ Agent spawned for restored company {target_id}")
    except Exception as e:
        logger.warning(f"Agent spawn warning: {e}")

    return {
        "restored":           True,
        "company_id":         target_id,
        "company_name":       company_name,
        "restored_from_db":   restored_from_db,
        "employees_imported": imported_employees,
        "message":            (
            f"✅ {company_name} restored successfully! "
            f"{'Full database restored.' if restored_from_db else f'{imported_employees} employees imported from Excel.'}"
        ),
    }


def _restore_employees_from_excel(excel_bytes: bytes, company_id: str) -> int:
    """Import employees from the employees.xlsx sheet during restore."""
    from backend.core.database import get_company_session, Employee, EmploymentStatus
    import re as _re

    df = pd.read_excel(io.BytesIO(excel_bytes), dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]

    session = get_company_session(company_id)
    added = 0

    COL_MAP = {
        "EmployeeID":     "employee_id",
        "FirstName":      "first_name",
        "LastName":       "last_name",
        "Email":          "email",
        "Phone":          "phone",
        "Department":     "department",
        "Position":       "position",
        "EmploymentType": "employment_type",
        "Status":         "status_str",
        "GrossSalary":    "gross_salary",
        "BankName":       "bank_name",
        "AccountNumber":  "account_number",
        "PensionPIN":     "pension_pin",
        "TaxID":          "tax_id",
        "StartDate":      "start_date",
    }

    for _, row in df.iterrows():
        data = {v: row.get(k, "") for k, v in COL_MAP.items()}
        first = data.get("first_name", "").strip()
        if not first:
            continue

        emp_id = data.get("employee_id", "").strip()
        if not emp_id:
            emp_id = f"EMP-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:18]}"

        email = data.get("email", "").strip().lower() or None

        # Skip duplicates
        if session.query(Employee).filter(Employee.employee_id == emp_id).first():
            continue
        if email and session.query(Employee).filter(Employee.email == email).first():
            continue

        sal_raw = data.get("gross_salary", "0")
        try:
            sal = float(_re.sub(r"[^\d.]", "", sal_raw)) if sal_raw else 0.0
        except ValueError:
            sal = 0.0

        start_d = None
        sr = data.get("start_date", "").strip()
        if sr and sr != "nan":
            for fmt in ["%Y-%m-%d", "%d/%m/%Y"]:
                try:
                    start_d = datetime.strptime(sr, fmt).date()
                    break
                except ValueError:
                    pass

        # Resolve status
        status_str = data.get("status_str", "active").strip().lower()
        status_map = {
            "active":     EmploymentStatus.active,
            "on_leave":   EmploymentStatus.on_leave,
            "probation":  EmploymentStatus.probation,
            "terminated": EmploymentStatus.terminated,
        }
        emp_status = status_map.get(status_str, EmploymentStatus.active)

        emp = Employee(
            employee_id    = emp_id,
            first_name     = first,
            last_name      = data.get("last_name", "").strip(),
            email          = email,
            phone          = data.get("phone", "").strip() or None,
            department     = data.get("department", "").strip() or None,
            position       = data.get("position", "").strip() or None,
            employment_type= data.get("employment_type", "full-time").strip() or "full-time",
            status         = emp_status,
            gross_salary   = sal,
            bank_name      = data.get("bank_name", "").strip() or None,
            account_number = data.get("account_number", "").strip() or None,
            pension_pin    = data.get("pension_pin", "").strip() or None,
            tax_id         = data.get("tax_id", "").strip() or None,
            start_date     = start_d,
        )
        session.add(emp)
        added += 1

    session.commit()
    session.close()
    return added


def restore_company_from_archive(company_id: str) -> dict:
    """Restore using the saved archive on disk (no upload needed)."""
    zip_bytes = get_archive_zip_bytes(company_id)
    if not zip_bytes:
        raise FileNotFoundError(f"No archive found for '{company_id}'")
    return restore_company_from_zip(zip_bytes, company_id)
