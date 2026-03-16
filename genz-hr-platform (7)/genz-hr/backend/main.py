"""
GENZ HR — FastAPI Backend
Main application entry point.
"""
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from pathlib import Path
import json
import logging
from datetime import datetime
import uvicorn

logger = logging.getLogger("genz.api")

from backend.core.config import settings
from backend.core.database import init_master_db
from backend.agents.genz_director import director


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("GENZ HR starting up...")
    init_master_db()
    logger.info(f"GENZ HR v{settings.VERSION} ready — Esther's AI HR Platform")
    yield
    director.shutdown()
    logger.info("GENZ HR shut down cleanly")


app = FastAPI(
    title="GENZ HR API",
    description="AI-Powered HR Automation Platform for Nigerian Startups",
    version=settings.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "platform": "GENZ HR",
        "version": settings.VERSION,
        "status": "running",
        "authority": settings.ESTHER_EMAIL,
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "platform": "GENZ HR"}


# ─── Platform ─────────────────────────────────────────────────────────────────

@app.get("/api/platform/stats")
async def platform_stats():
    """Overall platform statistics for dashboard."""
    return director.get_platform_stats()


@app.get("/api/platform/daily-summary")
async def daily_summary():
    """Run the daily GENZ Director cycle and return summary."""
    return director.run_daily_cycle()


# ─── Companies ────────────────────────────────────────────────────────────────

@app.post("/api/companies/register")
async def register_company(
    company_id: str = Form(...),
    name: str = Form(...),
    industry: str = Form(""),
    size: str = Form("startup"),
    contact_email: str = Form(""),
):
    """Register a new company and initialize its isolated GENZ Agent."""
    try:
        company = director.register_company(
            company_id=company_id.lower().replace(" ", "_"),
            name=name,
            industry=industry,
            size=size,
            contact_email=contact_email,
        )
        return {
            "message": f"Company '{name}' registered successfully",
            "company_id": company.id,
            "genz_agent": "initialized",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/companies/{company_id}/report")
async def company_daily_report(company_id: str):
    """Get daily report for a specific company."""
    agent = director.get_agent(company_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Company not found")
    return agent.generate_daily_report()


# ─── Company Offboarding, Export & Restore ────────────────────────────────────

@app.get("/api/companies/{company_id}/export")
async def export_company(company_id: str):
    """
    Export all company data as a downloadable ZIP archive.
    Includes Excel sheets for every table + raw SQLite DB for perfect restore.
    Does NOT delete the company — use /offboard for that.
    """
    from backend.modules.company_offboarding import export_company_data
    from backend.core.database import MasterSession, CompanyRegistry
    from fastapi.responses import Response

    master  = MasterSession()
    company = master.query(CompanyRegistry).filter(CompanyRegistry.id == company_id).first()
    master.close()
    if not company:
        raise HTTPException(status_code=404, detail=f"Company '{company_id}' not found")

    try:
        zip_bytes = export_company_data(company_id, company.name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")

    filename = f"genzhr_export_{company_id}_{datetime.now().strftime('%Y%m%d')}.zip"
    return Response(
        content     = zip_bytes,
        media_type  = "application/zip",
        headers     = {"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/api/companies/{company_id}/offboard")
async def offboard_company(company_id: str, body: dict = {}):
    """
    Soft-delete a company:
    - Exports all data to archive
    - Marks company inactive
    - Shuts down GENZ Agent
    - Removes data directory
    - Keeps archive for future restore
    """
    from backend.modules.company_offboarding import offboard_company as do_offboard
    from fastapi.responses import Response

    reason = body.get("reason", "Client requested offboarding")
    try:
        result = do_offboard(company_id, reason)
        # Return zip bytes as download
        zip_bytes  = result.pop("zip_bytes")
        filename   = f"genzhr_final_export_{company_id}_{datetime.now().strftime('%Y%m%d')}.zip"
        return Response(
            content    = zip_bytes,
            media_type = "application/zip",
            headers    = {
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Company-ID":        company_id,
                "X-Offboarded":        "true",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Offboarding failed: {e}")


@app.delete("/api/companies/{company_id}")
async def delete_company(company_id: str):
    """
    Permanently delete a company (no restore possible).
    Use /offboard instead if you want to be able to restore later.
    """
    from backend.core.database import MasterSession, CompanyRegistry
    import shutil

    master  = MasterSession()
    company = master.query(CompanyRegistry).filter(CompanyRegistry.id == company_id).first()
    if not company:
        master.close()
        raise HTTPException(status_code=404, detail=f"Company '{company_id}' not found")

    company_name = company.name
    try:
        master.delete(company)
        master.commit()
    except Exception as e:
        master.rollback()
        master.close()
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    finally:
        master.close()

    # Shut down agent
    if company_id in director._agents:
        try:
            director._agents[company_id].close()
        except Exception:
            pass
        del director._agents[company_id]

    # Remove data directory
    from backend.core.config import COMPANIES_DIR
    company_dir = COMPANIES_DIR / company_id
    if company_dir.exists():
        try:
            shutil.rmtree(company_dir)
        except Exception as e:
            logger.warning(f"Could not remove {company_dir}: {e}")

    return {"message": f"'{company_name}' permanently deleted", "deleted": True}


@app.get("/api/companies/archived/list")
async def list_archived_companies():
    """List all offboarded/archived companies available for restore."""
    from backend.modules.company_offboarding import list_archived_companies as list_arch
    return {"archived": list_arch()}


@app.get("/api/companies/{company_id}/archived/download")
async def download_archive(company_id: str):
    """Download the archived ZIP for an offboarded company."""
    from backend.modules.company_offboarding import get_archive_zip_bytes
    from fastapi.responses import Response

    zip_bytes = get_archive_zip_bytes(company_id)
    if not zip_bytes:
        raise HTTPException(status_code=404, detail=f"No archive found for '{company_id}'")

    filename = f"genzhr_archive_{company_id}.zip"
    return Response(
        content    = zip_bytes,
        media_type = "application/zip",
        headers    = {"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/api/companies/restore")
async def restore_company(
    file: UploadFile = File(...),
    company_id: str  = Form(...),
):
    """
    Restore a previously offboarded company from a GENZ HR export ZIP.
    company_id: can be the original ID or a new one.
    """
    from backend.modules.company_offboarding import restore_company_from_zip

    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a .zip export from GENZ HR")

    zip_bytes = await file.read()
    try:
        result = restore_company_from_zip(zip_bytes, company_id.strip().lower())
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {e}")


@app.post("/api/companies/{company_id}/restore-from-archive")
async def restore_from_saved_archive(company_id: str):
    """Restore a company from its on-disk archive (no upload needed)."""
    from backend.modules.company_offboarding import restore_company_from_archive
    try:
        result = restore_company_from_archive(company_id)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {e}")


# ─── Employees ────────────────────────────────────────────────────────────────

@app.get("/api/companies/{company_id}/employees")
async def list_employees(company_id: str):
    from backend.core.database import get_company_session, Employee
    session = get_company_session(company_id)
    employees = session.query(Employee).all()
    return [
        {
            "id": e.id,
            "employee_id": e.employee_id,
            "name": f"{e.first_name} {e.last_name}",
            "position": e.position,
            "department": e.department,
            "status": e.status,
            "gross_salary": e.gross_salary,
        }
        for e in employees
    ]


@app.post("/api/companies/{company_id}/employees")
async def create_employee(company_id: str, employee_data: dict):
    from backend.core.database import get_company_session, Employee
    from backend.modules.audit_logger import log_action
    
    session = get_company_session(company_id)
    emp = Employee(**{k: v for k, v in employee_data.items() if hasattr(Employee, k)})
    session.add(emp)
    session.commit()
    session.refresh(emp)
    
    log_action(session, "Esther", "EMPLOYEE_CREATE", "employees",
               "Employee", str(emp.id), details=f"Created {emp.first_name} {emp.last_name}")
    
    return {"message": "Employee created", "employee_id": emp.id}


@app.post("/api/companies/{company_id}/employees/upload")
async def bulk_upload_employees(
    company_id: str,
    file: UploadFile = File(...),
):
    """
    Bulk upload employees from Excel (.xlsx) or CSV.
    Issue 3 fix: employee bulk upload.

    Required columns (case-insensitive):
        EmployeeID, FirstName, LastName, Email, Phone,
        Department, Salary, Position

    Returns:
        { employees_added: int, duplicates_skipped: int, errors: [...] }
    """
    import io
    import pandas as pd
    from backend.core.database import get_company_session, Employee, EmploymentStatus

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".xlsx", ".xls", ".csv"):
        raise HTTPException(status_code=400, detail="File must be .xlsx, .xls, or .csv")

    raw = await file.read()
    buf = io.BytesIO(raw)

    try:
        if suffix == ".csv":
            df = pd.read_csv(buf, dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(buf, dtype=str, keep_default_na=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {e}")

    # Normalise column names — lowercase, strip spaces/underscores
    df.columns = [c.strip().lower().replace(" ", "").replace("_", "") for c in df.columns]

    # Column alias map → canonical field name
    COL_MAP = {
        "employeeid":   "employee_id",
        "empid":        "employee_id",
        "id":           "employee_id",
        "firstname":    "first_name",
        "fname":        "first_name",
        "lastname":     "last_name",
        "lname":        "last_name",
        "fullname":     "full_name",   # will be split
        "name":         "full_name",
        "email":        "email",
        "emailaddress": "email",
        "phone":        "phone",
        "phonenumber":  "phone",
        "mobile":       "phone",
        "department":   "department",
        "dept":         "department",
        "position":     "position",
        "jobtitle":     "position",
        "role":         "position",
        "salary":       "gross_salary",
        "grosssalary":  "gross_salary",
        "monthlysalary":"gross_salary",
        "bankname":     "bank_name",
        "bank":         "bank_name",
        "accountnumber":"account_number",
        "accountno":    "account_number",
        "startdate":    "start_date",
        "employmenttype":"employment_type",
        "type":         "employment_type",
    }

    df.rename(columns=COL_MAP, inplace=True)
    df = df.fillna("")

    # Check required columns
    required = {"first_name", "last_name"}
    # Accept full_name as alternative to first+last
    has_fullname = "full_name" in df.columns
    if not has_fullname and not required.issubset(set(df.columns)):
        missing = required - set(df.columns)
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {missing}. "
                   f"Found columns: {list(df.columns)}"
        )

    session = get_company_session(company_id)
    added = 0
    skipped = 0
    errors = []

    for idx, row in df.iterrows():
        row_num = idx + 2  # 1-based, +1 for header
        try:
            # Resolve name
            if has_fullname and row.get("full_name", "").strip():
                parts      = row["full_name"].strip().split(" ", 1)
                first_name = parts[0]
                last_name  = parts[1] if len(parts) > 1 else ""
            else:
                first_name = row.get("first_name", "").strip()
                last_name  = row.get("last_name",  "").strip()

            if not first_name:
                errors.append({"row": row_num, "error": "Missing first name"})
                continue

            email      = row.get("email", "").strip().lower() or None
            emp_id_raw = row.get("employee_id", "").strip()
            emp_id     = emp_id_raw or f"EMP-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:18]}"

            # Duplicate check — by employee_id OR email
            existing = None
            if emp_id_raw:
                existing = session.query(Employee).filter(
                    Employee.employee_id == emp_id_raw
                ).first()
            if not existing and email:
                existing = session.query(Employee).filter(
                    Employee.email == email
                ).first()

            if existing:
                skipped += 1
                continue

            # Parse salary
            salary_raw = row.get("gross_salary", "0").strip()
            try:
                import re as _re
                salary = float(_re.sub(r"[^\d.]", "", salary_raw)) if salary_raw else 0.0
            except ValueError:
                salary = 0.0

            # Parse start date
            start_date_val = None
            start_raw = row.get("start_date", "").strip()
            if start_raw:
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"]:
                    try:
                        from datetime import datetime as _dt
                        start_date_val = _dt.strptime(start_raw, fmt).date()
                        break
                    except ValueError:
                        pass

            emp = Employee(
                employee_id     = emp_id,
                first_name      = first_name,
                last_name       = last_name,
                email           = email,
                phone           = row.get("phone", "").strip() or None,
                department      = row.get("department", "").strip() or None,
                position        = row.get("position", "").strip() or None,
                gross_salary    = salary,
                bank_name       = row.get("bank_name", "").strip() or None,
                account_number  = row.get("account_number", "").strip() or None,
                employment_type = row.get("employment_type", "full-time").strip() or "full-time",
                start_date      = start_date_val,
                status          = EmploymentStatus.active,
            )
            session.add(emp)
            session.flush()  # catch constraint errors per-row
            added += 1

        except Exception as e:
            session.rollback()
            errors.append({"row": row_num, "error": str(e)[:120]})
            continue

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        session.close()
        raise HTTPException(status_code=500, detail=f"Commit failed: {e}")

    session.close()
    return {
        "employees_added":    added,
        "duplicates_skipped": skipped,
        "errors":             errors[:20],
        "total_rows":         len(df),
        "message":            f"Upload complete: {added} added, {skipped} skipped, {len(errors)} errors",
    }



    from backend.core.database import get_company_session, Employee
    from backend.modules.audit_logger import log_employee_edit
    
    session = get_company_session(company_id)
    emp = session.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    for field, new_val in updates.items():
        if hasattr(emp, field):
            old_val = getattr(emp, field)
            setattr(emp, field, new_val)
            log_employee_edit(session, "Esther", employee_id, field, old_val, new_val)
    
    session.commit()
    return {"message": "Employee updated", "fields_changed": list(updates.keys())}


# ─── Recruitment ──────────────────────────────────────────────────────────────

@app.post("/api/companies/{company_id}/recruitment/upload-cv")
async def upload_cv(
    company_id: str,
    position: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload a CV for parsing and scoring."""
    from backend.core.config import get_company_dir
    from backend.modules.cv_parser import score_candidate
    from backend.core.database import get_company_session, Candidate
    import shutil
    
    company_dir = get_company_dir(company_id)
    upload_dir = company_dir / "uploads"
    
    # Save file
    file_path = upload_dir / file.filename
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    # Score candidate
    scored = score_candidate(str(file_path), position)
    
    # Save to DB
    session = get_company_session(company_id)
    candidate = Candidate(
        name=scored.name,
        email=scored.email,
        phone=scored.phone,
        position_applied=position,
        cv_path=str(file_path),
        raw_cv_text=scored.raw_cv_text,
        education_score=scored.education_score,
        skills_score=scored.skills_score,
        experience_score=scored.experience_score,
        keyword_score=scored.keyword_score,
        total_score=scored.total_score,
        shortlisted=scored.total_score >= 60,
    )
    session.add(candidate)
    session.commit()
    
    return {
        "message": "CV processed",
        "candidate": scored.to_dict(),
        "auto_shortlisted": scored.total_score >= 60,
        "note": "Esther can override scores before finalizing shortlist",
    }


@app.get("/api/companies/{company_id}/recruitment/candidates")
async def list_candidates(company_id: str, position: str = None):
    from backend.core.database import get_company_session, Candidate
    
    session = get_company_session(company_id)
    query = session.query(Candidate)
    if position:
        query = query.filter(Candidate.position_applied == position)
    candidates = query.order_by(Candidate.total_score.desc()).all()
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "position": c.position_applied,
            "total_score": c.total_score,
            "shortlisted": c.shortlisted,
            "interview_status": c.interview_status,
            "esther_override": c.esther_override_score,
        }
        for c in candidates
    ]


@app.patch("/api/companies/{company_id}/recruitment/candidates/{candidate_id}/override")
async def override_candidate_score(company_id: str, candidate_id: int, override: dict):
    """Esther overrides AI candidate score."""
    from backend.core.database import get_company_session, Candidate
    from backend.modules.audit_logger import log_candidate_override
    
    session = get_company_session(company_id)
    candidate = session.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    old_score = candidate.esther_override_score or candidate.total_score
    new_score = override.get("score")
    candidate.esther_override_score = new_score
    if override.get("shortlisted") is not None:
        candidate.shortlisted = override["shortlisted"]
    
    log_candidate_override(session, "Esther", candidate_id, "score", old_score, new_score)
    session.commit()
    
    return {"message": "Score overridden by Esther", "new_score": new_score}


# ─── Payroll ──────────────────────────────────────────────────────────────────

@app.post("/api/companies/{company_id}/payroll/prepare/{period}")
async def prepare_payroll(company_id: str, period: str):
    """Prepare payroll draft for a period."""
    agent = director.get_agent(company_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Company not found")
    return agent.prepare_payroll(period)


@app.get("/api/companies/{company_id}/payroll/{period}")
async def get_payroll(company_id: str, period: str):
    from backend.core.database import get_company_session, PayrollRecord, Employee
    
    session = get_company_session(company_id)
    records = session.query(PayrollRecord).filter(PayrollRecord.period == period).all()
    
    results = []
    for r in records:
        emp = session.query(Employee).filter(Employee.id == r.employee_id).first()
        results.append({
            "id": r.id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "Unknown",
            "gross_salary": r.gross_salary,
            "paye_tax": r.paye_tax,
            "pension_employee": r.pension_employee,
            "nhf_deduction": r.nhf_deduction,
            "performance_bonus": r.performance_bonus,
            "net_salary": r.net_salary,
            "status": r.status,
            "anomaly": r.anomaly_flag,
            "anomaly_reason": r.anomaly_reason,
        })
    
    return {"period": period, "records": results}


@app.post("/api/companies/{company_id}/payroll/{payroll_id}/approve")
async def approve_payroll(company_id: str, payroll_id: int):
    """Esther approves a payroll record."""
    from backend.core.database import get_company_session, PayrollRecord
    from backend.modules.audit_logger import log_approval
    
    session = get_company_session(company_id)
    record = session.query(PayrollRecord).filter(PayrollRecord.id == payroll_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Payroll record not found")
    
    record.status = "approved"
    record.approved_by = "Esther"
    from datetime import datetime
    record.approved_at = datetime.utcnow()
    
    log_approval(session, "Esther", "PayrollRecord", str(payroll_id), "APPROVED")
    session.commit()
    
    return {"message": f"Payroll #{payroll_id} approved by Esther"}


@app.patch("/api/companies/{company_id}/payroll/{payroll_id}")
async def edit_payroll(company_id: str, payroll_id: int, updates: dict):
    """Esther edits a payroll record before approval."""
    from backend.core.database import get_company_session, PayrollRecord
    from backend.modules.audit_logger import log_payroll_edit
    
    session = get_company_session(company_id)
    record = session.query(PayrollRecord).filter(PayrollRecord.id == payroll_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Payroll record not found")
    if record.status == "approved":
        raise HTTPException(status_code=400, detail="Cannot edit approved payroll")
    
    for field, new_val in updates.items():
        if hasattr(record, field):
            old_val = getattr(record, field)
            setattr(record, field, new_val)
            log_payroll_edit(session, "Esther", payroll_id, field, old_val, new_val)
    
    session.commit()
    return {"message": "Payroll updated"}


# ─── Audit Logs ───────────────────────────────────────────────────────────────

@app.get("/api/companies/{company_id}/audit-logs")
async def get_audit_logs(company_id: str, limit: int = 50):
    from backend.core.database import get_company_session
    from backend.modules.audit_logger import get_audit_trail, format_audit_entry
    
    session = get_company_session(company_id)
    logs = get_audit_trail(session, limit=limit)
    return [format_audit_entry(log) for log in logs]


# ─── Templates ────────────────────────────────────────────────────────────────

@app.get("/api/companies/{company_id}/templates")
async def list_templates(company_id: str):
    from backend.core.database import get_company_session, HRTemplate
    
    session = get_company_session(company_id)
    templates = session.query(HRTemplate).filter(HRTemplate.is_active == True).all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "type": t.template_type,
            "format": t.file_format,
            "version": t.version,
            "variables": t.variables,
        }
        for t in templates
    ]


@app.post("/api/companies/{company_id}/templates/{template_type}/render")
async def render_template(company_id: str, template_type: str, variables: dict):
    """Render a template with provided variables."""
    from backend.modules.template_engine import template_engine
    
    rendered = template_engine.render_builtin(template_type, variables)
    return {
        "template_type": template_type,
        "rendered_content": rendered,
        "note": "Preview only. Esther must approve before sending.",
    }



# ─── Data Integration Endpoints ───────────────────────────────────────────────

@app.get("/api/companies/{company_id}/integrations/sources")
async def list_integration_sources(company_id: str):
    """List all registered data sources for a company."""
    from backend.modules.integration_manager import list_data_sources
    from backend.core.database import get_company_session
    session = get_company_session(company_id)
    result  = list_data_sources(company_id, session)
    session.close()
    return {"company_id": company_id, "sources": result}


@app.post("/api/companies/{company_id}/integrations/excel/upload")
async def upload_excel(
    company_id: str,
    file: UploadFile = File(...),
    name: str = Form(""),
    tab_name: str = Form(""),
):
    """Upload an Excel or CSV file and register it as a data source."""
    from backend.modules.integration_manager import register_excel_source
    from backend.core.database import get_company_session
    from backend.core.config import get_company_dir

    allowed = {".xlsx", ".xls", ".csv"}
    suffix  = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"File type {suffix} not supported. Use .xlsx or .csv")

    # Save to company uploads folder
    upload_dir = get_company_dir(company_id) / "uploads"
    upload_dir.mkdir(exist_ok=True)
    dest = upload_dir / file.filename
    dest.write_bytes(await file.read())

    session = get_company_session(company_id)
    result  = register_excel_source(
        company_id = company_id,
        file_path  = str(dest),
        name       = name or file.filename,
        session    = session,
        tab_name   = tab_name or None,
    )
    session.close()
    return result


@app.post("/api/companies/{company_id}/integrations/excel/preview")
async def preview_excel(
    company_id: str,
    file: UploadFile = File(...),
    tab_name: str = Form(""),
):
    """Preview column mapping proposals for an uploaded file (no import)."""
    from backend.modules.data_ingestion import read_from_bytes
    from backend.modules.column_mapper import propose_mappings

    raw     = await file.read()
    headers, rows = read_from_bytes(raw, file.filename, tab_name or None)
    proposals     = propose_mappings(headers)
    return {
        "filename":    file.filename,
        "total_rows":  len(rows),
        "columns":     headers,
        "preview":     rows[:5],
        "proposals":   [p.to_dict() for p in proposals],
        "needs_review":[p.to_dict() for p in proposals if p.needs_review],
    }


@app.post("/api/companies/{company_id}/integrations/sources/{source_id}/mappings")
async def save_column_mappings(company_id: str, source_id: int, body: dict):
    """Save confirmed column mappings for a data source."""
    from backend.modules.integration_manager import save_mappings
    from backend.core.database import get_company_session

    proposals = body.get("proposals", [])
    overrides = body.get("overrides", {})
    session   = get_company_session(company_id)
    n_saved   = save_mappings(source_id, proposals, overrides, session)
    session.close()
    return {"saved": n_saved, "source_id": source_id}


@app.post("/api/companies/{company_id}/integrations/sources/{source_id}/sync")
async def trigger_sync(company_id: str, source_id: int, body: dict = {}):
    """Manually trigger a sync for a data source."""
    from backend.modules.integration_manager import run_sync
    from backend.core.database import get_company_session

    session = get_company_session(company_id)
    result  = run_sync(
        company_id       = company_id,
        data_source_id   = source_id,
        session          = session,
        trigger          = "manual",
        credentials_path = body.get("credentials_path"),
        force            = body.get("force", False),
    )
    session.close()
    return result


@app.get("/api/companies/{company_id}/integrations/sources/{source_id}/history")
async def get_sync_history_api(company_id: str, source_id: int, limit: int = 20):
    """Return sync history for a data source."""
    from backend.modules.integration_manager import get_sync_history
    from backend.core.database import get_company_session

    session = get_company_session(company_id)
    history = get_sync_history(source_id, session, limit)
    session.close()
    return {"source_id": source_id, "history": history}


@app.post("/api/companies/{company_id}/integrations/gsheet/connect")
async def connect_gsheet(company_id: str, body: dict):
    """Register a Google Sheet as a live data source."""
    from backend.modules.integration_manager import register_gsheet_source
    from backend.core.database import get_company_session

    sheet_url = body.get("sheet_url", "")
    if not sheet_url:
        raise HTTPException(status_code=400, detail="sheet_url is required")

    session = get_company_session(company_id)
    result  = register_gsheet_source(
        company_id       = company_id,
        sheet_url        = sheet_url,
        name             = body.get("name", "Google Sheet"),
        session          = session,
        tab_name         = body.get("tab_name"),
        auto_sync        = body.get("auto_sync", True),
        sync_interval    = body.get("sync_interval", 3600),
        credentials_path = body.get("credentials_path"),
    )
    session.close()
    return result


@app.get("/api/companies/{company_id}/integrations/logs")
async def get_integration_logs(company_id: str, limit: int = 50):
    """Return recent integration event logs for a company."""
    from backend.core.database import get_company_session, IntegrationLog

    session = get_company_session(company_id)
    logs    = (
        session.query(IntegrationLog)
        .filter(IntegrationLog.company_id == company_id)
        .order_by(IntegrationLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    session.close()
    return {"logs": [
        {
            "source":        l.source,
            "event":         l.event,
            "file_name":     l.file_name,
            "rows_affected": l.rows_affected,
            "details":       l.details,
            "success":       l.success,
            "timestamp":     l.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for l in logs
    ]}


@app.post("/api/companies/{company_id}/integrations/excel/import")
async def import_excel_direct(
    company_id: str,
    file: UploadFile = File(...),
    tab_name: str = Form(""),
    mapping_overrides: str = Form("{}"),
):
    """
    Upload + immediately import an Excel/CSV file with optional mapping overrides.
    Salary changes are automatically queued for Esther's approval.
    """
    from backend.modules.integrations.excel_importer import ExcelImporter
    from backend.core.config import get_company_dir

    upload_dir = get_company_dir(company_id) / "uploads"
    upload_dir.mkdir(exist_ok=True)
    dest = upload_dir / file.filename
    dest.write_bytes(await file.read())

    try:
        overrides = json.loads(mapping_overrides)
    except Exception:
        overrides = {}

    importer = ExcelImporter(company_id)
    result   = importer.import_file(
        file_path          = str(dest),
        sheet_name         = tab_name or None,
        mapping_overrides  = overrides,
        requested_by       = "Esther",
    )
    return result.to_dict()




@app.get("/api/companies/{company_id}/approvals")
async def list_approvals(company_id: str, status: str = "pending"):
    """
    Return all approval tickets for a company.
    status: 'pending' | 'approved' | 'rejected' | 'all'
    """
    from backend.core.approval_gate import get_all_tickets, get_pending_tickets
    from backend.core.database import get_company_session

    session = get_company_session(company_id)
    tickets = (
        get_pending_tickets(company_id, session)
        if status == "pending"
        else get_all_tickets(company_id, session)
    )
    session.close()

    if status not in ("pending", "all"):
        tickets = [t for t in tickets if t.status.value == status]

    return {"company_id": company_id, "tickets": [t.to_dict() for t in tickets]}


@app.post("/api/companies/{company_id}/approvals/{ticket_id}/approve")
async def approve_action(company_id: str, ticket_id: str, body: dict = {}):
    """
    Esther approves a pending ticket.
    Triggers execution of the underlying action immediately.
    """
    from backend.core.approval_gate import approve_ticket
    from backend.core.database import get_company_session

    note    = body.get("note", "")
    session = get_company_session(company_id)
    ok, result = approve_ticket(company_id, ticket_id, note=note, session=session)

    if not ok:
        session.close()
        raise HTTPException(status_code=400, detail=result)

    ticket = result  # approve_ticket returns the ApprovalTicket on success

    # Execute the action
    agent  = director.get_agent(company_id)
    exec_result = {"executed": False, "reason": "Agent not available"}
    if agent:
        exec_result = agent.execute_approved_ticket(ticket)

    session.close()
    return {
        "approved":    True,
        "ticket_id":   ticket_id,
        "action":      ticket.action_type,
        "executed":    exec_result.get("executed", False),
        "exec_detail": exec_result,
    }


@app.post("/api/companies/{company_id}/approvals/{ticket_id}/reject")
async def reject_action(company_id: str, ticket_id: str, body: dict = {}):
    """Esther rejects a pending ticket. Action is permanently blocked."""
    from backend.core.approval_gate import reject_ticket
    from backend.core.database import get_company_session

    reason  = body.get("reason", "Rejected by Esther")
    session = get_company_session(company_id)
    ok, msg = reject_ticket(company_id, ticket_id, reason=reason, session=session)
    session.close()

    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"rejected": True, "ticket_id": ticket_id, "reason": reason}


@app.get("/api/approvals/pending-counts")
async def platform_pending_counts():
    """How many pending approvals exist per company — for the director overview."""
    from backend.core.approval_gate import get_platform_pending_counts
    counts = get_platform_pending_counts()
    total  = sum(counts.values())
    return {"total_pending": total, "by_company": counts}


@app.post("/api/companies/{company_id}/approvals/submit")
async def submit_approval_request(company_id: str, body: dict):
    """
    Manually submit an action for Esther's approval.
    Used by the dashboard for ad-hoc requests like salary changes.
    """
    from backend.core.approval_gate import submit_action, ActionType
    from backend.core.database import get_company_session

    try:
        action_type = ActionType(body["action_type"])
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid action_type: {e}")

    session = get_company_session(company_id)
    ticket  = submit_action(
        company_id   = company_id,
        action_type  = action_type,
        description  = body.get("description", ""),
        payload      = body.get("payload", {}),
        requested_by = body.get("requested_by", "Dashboard"),
        session      = session,
    )
    session.close()

    return {
        "ticket_id": ticket.ticket_id,
        "status":    ticket.status.value,
        "queued":    ticket.status.value == "pending",
        "label":     ticket.label,
        "risk":      ticket.risk,
    }



# ─── Data Integration Endpoints ───────────────────────────────────────────────

@app.get("/api/companies/{company_id}/integrations")
async def list_integrations(company_id: str):
    """List all data sources registered for a company."""
    from backend.modules.integration_manager import list_data_sources
    from backend.core.database import get_company_session
    session = get_company_session(company_id)
    result  = list_data_sources(company_id, session)
    session.close()
    return {"company_id": company_id, "sources": result}


@app.post("/api/companies/{company_id}/integrations/excel")
async def upload_excel(
    company_id: str,
    file:       UploadFile = File(...),
    name:       str = Form(default=""),
    tab_name:   str = Form(default=""),
    auto_sync:  bool = Form(default=False),
):
    """
    Upload an Excel or CSV file.
    Returns proposed column mappings for Esther to confirm.
    """
    from backend.modules.integration_manager import register_excel_source
    from backend.modules.data_ingestion import read_from_bytes
    from backend.core.database import get_company_session
    from backend.core.config import get_company_dir
    import shutil

    allowed = {".xlsx", ".xls", ".csv", ".xlsm"}
    suffix  = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"File type {suffix} not supported. Use: {allowed}")

    # Save to company uploads directory
    upload_dir = get_company_dir(company_id) / "uploads"
    upload_dir.mkdir(exist_ok=True)
    file_path  = str(upload_dir / file.filename)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    session = get_company_session(company_id)
    try:
        result = register_excel_source(
            company_id = company_id,
            file_path  = file_path,
            name       = name or file.filename,
            session    = session,
            tab_name   = tab_name or None,
            auto_sync  = auto_sync,
        )
        return result
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        session.close()


@app.post("/api/companies/{company_id}/integrations/gsheet")
async def connect_gsheet(company_id: str, body: dict):
    """
    Connect a Google Sheet as a live data source.
    Returns proposed column mappings.
    """
    from backend.modules.integration_manager import register_gsheet_source
    from backend.core.database import get_company_session

    sheet_url  = body.get("sheet_url", "")
    name       = body.get("name", "Google Sheet")
    tab_name   = body.get("tab_name")
    auto_sync  = body.get("auto_sync", True)
    sync_interval = body.get("sync_interval", 3600)

    if not sheet_url:
        raise HTTPException(400, "sheet_url is required")

    session = get_company_session(company_id)
    try:
        result = register_gsheet_source(
            company_id    = company_id,
            sheet_url     = sheet_url,
            name          = name,
            session       = session,
            tab_name      = tab_name,
            auto_sync     = auto_sync,
            sync_interval = sync_interval,
        )
        return result
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        session.close()


@app.post("/api/companies/{company_id}/integrations/{source_id}/mappings")
async def confirm_mappings(company_id: str, source_id: int, body: dict):
    """
    Confirm or override column mappings for a data source.
    Body: {proposals: [...], overrides: {sheet_col: system_field, ...}}
    """
    from backend.modules.integration_manager import save_mappings
    from backend.core.database import get_company_session

    session = get_company_session(company_id)
    try:
        count = save_mappings(
            data_source_id = source_id,
            proposals      = body.get("proposals", []),
            overrides      = body.get("overrides", {}),
            session        = session,
        )
        return {"saved_mappings": count, "source_id": source_id}
    finally:
        session.close()


@app.post("/api/companies/{company_id}/integrations/{source_id}/sync")
async def trigger_sync(company_id: str, source_id: int, body: dict = {}):
    """Trigger a manual sync for a data source."""
    from backend.modules.integration_manager import run_sync
    from backend.core.database import get_company_session

    session = get_company_session(company_id)
    try:
        result = run_sync(
            company_id     = company_id,
            data_source_id = source_id,
            session        = session,
            trigger        = "manual",
            force          = body.get("force", False),
        )
        return result
    finally:
        session.close()


@app.get("/api/companies/{company_id}/integrations/{source_id}/history")
async def sync_history(company_id: str, source_id: int):
    """Return sync history for a data source."""
    from backend.modules.integration_manager import get_sync_history
    from backend.core.database import get_company_session

    session = get_company_session(company_id)
    logs    = get_sync_history(source_id, session)
    session.close()
    return {"source_id": source_id, "logs": logs}


@app.get("/api/companies/{company_id}/integrations/{source_id}/mappings")
async def get_mappings(company_id: str, source_id: int):
    """Get current column mappings for a data source."""
    from backend.core.integration_models import ColumnMapping
    from backend.core.database import get_company_session

    session  = get_company_session(company_id)
    mappings = session.query(ColumnMapping).filter(
        ColumnMapping.data_source_id == source_id
    ).all()
    session.close()
    return {"source_id": source_id, "mappings": [
        {
            "id":            m.id,
            "sheet_column":  m.sheet_column,
            "system_field":  m.system_field,
            "target_module": m.target_module,
            "transform":     m.transform,
            "is_key_field":  m.is_key_field,
            "confirmed_by":  m.confirmed_by,
        }
        for m in mappings
    ]}


@app.delete("/api/companies/{company_id}/integrations/{source_id}")
async def delete_source(company_id: str, source_id: int):
    """Remove a data source and its mappings."""
    from backend.core.integration_models import DataSource, ColumnMapping, SyncLog
    from backend.core.database import get_company_session

    session = get_company_session(company_id)
    session.query(SyncLog).filter(SyncLog.data_source_id == source_id).delete()
    session.query(ColumnMapping).filter(ColumnMapping.data_source_id == source_id).delete()
    session.query(DataSource).filter(DataSource.id == source_id).delete()
    session.commit()
    session.close()
    return {"deleted": True, "source_id": source_id}



# ─── Data Integration Endpoints (v2 upgrade) ─────────────────────────────────

@app.post("/api/companies/{company_id}/integrations/excel/upload")
async def upload_excel(
    company_id: str,
    file: UploadFile = File(...),
    sheet_name: str = Form(default=""),
    requested_by: str = Form(default="Esther"),
):
    """Upload an Excel / CSV file and import into GENZ HR."""
    import shutil, tempfile, os
    from backend.modules.integrations.excel_importer import ExcelImporter
    from backend.core.config import get_company_dir

    uploads_dir = get_company_dir(company_id) / "uploads"
    uploads_dir.mkdir(exist_ok=True)
    dest = uploads_dir / file.filename

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    importer = ExcelImporter(company_id)
    result   = importer.import_file(
        str(dest),
        sheet_name   = sheet_name or None,
        requested_by = requested_by,
    )
    return result.to_dict()


@app.post("/api/companies/{company_id}/integrations/excel/preview")
async def preview_excel(
    company_id: str,
    file: UploadFile = File(...),
    sheet_name: str = Form(default=""),
):
    """Preview column mappings for an Excel file before importing."""
    import shutil
    from backend.modules.integrations.excel_importer import ExcelImporter
    from backend.core.config import get_company_dir

    uploads_dir = get_company_dir(company_id) / "uploads"
    uploads_dir.mkdir(exist_ok=True)
    dest = uploads_dir / f"preview_{file.filename}"

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    importer = ExcelImporter(company_id)
    return importer.preview_file(str(dest), sheet_name or None)


@app.post("/api/companies/{company_id}/integrations/excel/confirm")
async def confirm_excel_import(company_id: str, body: dict):
    """Confirm an import with manual mapping overrides applied."""
    from backend.modules.integrations.excel_importer import ExcelImporter
    from backend.core.config import get_company_dir

    file_path        = body.get("file_path")
    mapping_overrides = body.get("mapping_overrides", {})
    requested_by     = body.get("requested_by", "Esther")

    if not file_path:
        raise HTTPException(status_code=400, detail="file_path required")

    importer = ExcelImporter(company_id)
    result   = importer.import_file(file_path, mapping_overrides=mapping_overrides, requested_by=requested_by)
    return result.to_dict()


@app.post("/api/companies/{company_id}/integrations/gsheets/connect")
async def connect_google_sheet(company_id: str, body: dict):
    """Save Google Sheets connection config and test connectivity."""
    from backend.core.database import get_company_session, DataIntegrationConfig
    from backend.modules.integrations.gsheets_connector import GoogleSheetsConnector, SheetConfig

    session = get_company_session(company_id)
    config_row = session.query(DataIntegrationConfig).filter(
        DataIntegrationConfig.company_id == company_id
    ).first()

    if not config_row:
        config_row = DataIntegrationConfig(company_id=company_id)
        session.add(config_row)

    config_row.gsheet_id             = body.get("sheet_id", "")
    config_row.gsheet_name           = body.get("sheet_name", "")
    config_row.gsheet_url            = body.get("sheet_url", "")
    config_row.gsheet_tab            = body.get("sheet_tab", "Sheet1")
    config_row.credentials_path      = body.get("credentials_path", "")
    config_row.auto_sync_enabled     = body.get("auto_sync", False)
    config_row.sync_interval_minutes = int(body.get("sync_interval_minutes", 30))
    session.commit()
    session.close()

    cfg    = SheetConfig(company_id=company_id, sheet_id=config_row.gsheet_id,
                         credentials_path=config_row.credentials_path or "")
    conn   = GoogleSheetsConnector(cfg)
    test   = conn.test_connection()
    return {"saved": True, "connection_test": test}


@app.post("/api/companies/{company_id}/integrations/gsheets/sync")
async def trigger_gsheet_sync(company_id: str, body: dict = {}):
    """Manually trigger a Google Sheets sync."""
    from backend.core.database import get_company_session, DataIntegrationConfig
    from backend.modules.integrations.gsheets_connector import GoogleSheetsConnector, SheetConfig
    import json as _json

    session    = get_company_session(company_id)
    config_row = session.query(DataIntegrationConfig).filter(
        DataIntegrationConfig.company_id == company_id
    ).first()
    session.close()

    if not config_row or not config_row.gsheet_id:
        raise HTTPException(status_code=400, detail="No Google Sheet connected for this company")

    cfg = SheetConfig(
        company_id            = company_id,
        sheet_id              = config_row.gsheet_id,
        sheet_name            = config_row.gsheet_name or "Sheet1",
        credentials_path      = config_row.credentials_path or "",
        mapping_overrides     = _json.loads(config_row.mapping_json or "{}"),
        sync_interval_minutes = config_row.sync_interval_minutes or 30,
    )
    conn   = GoogleSheetsConnector(cfg)
    result = conn.sync(requested_by=body.get("requested_by", "Esther"))
    return result.to_dict()


@app.get("/api/companies/{company_id}/integrations/gsheets/preview")
async def preview_gsheet(company_id: str):
    """Fetch a live preview of the connected Google Sheet with column mappings."""
    from backend.core.database import get_company_session, DataIntegrationConfig
    from backend.modules.integrations.gsheets_connector import GoogleSheetsConnector, SheetConfig
    import json as _json

    session    = get_company_session(company_id)
    config_row = session.query(DataIntegrationConfig).filter(
        DataIntegrationConfig.company_id == company_id
    ).first()
    session.close()

    if not config_row or not config_row.gsheet_id:
        raise HTTPException(status_code=400, detail="No Google Sheet connected")

    cfg  = SheetConfig(company_id=company_id, sheet_id=config_row.gsheet_id,
                       credentials_path=config_row.credentials_path or "")
    conn = GoogleSheetsConnector(cfg)
    return conn.get_preview()


@app.post("/api/companies/{company_id}/integrations/mapping/save")
async def save_mapping(company_id: str, body: dict):
    """Persist column mapping overrides for a company."""
    import json as _json
    from backend.core.database import get_company_session, DataIntegrationConfig

    session    = get_company_session(company_id)
    config_row = session.query(DataIntegrationConfig).filter(
        DataIntegrationConfig.company_id == company_id
    ).first()
    if not config_row:
        config_row = DataIntegrationConfig(company_id=company_id)
        session.add(config_row)

    config_row.mapping_json = _json.dumps(body.get("mappings", {}))
    session.commit()
    session.close()
    return {"saved": True}


@app.get("/api/companies/{company_id}/integrations/logs")
async def get_integration_logs(company_id: str, limit: int = 50):
    """Return integration sync logs for a company."""
    from backend.modules.integrations.sync_log import SyncLogger
    logger_obj = SyncLogger(company_id)
    return {"logs": logger_obj.get_recent(limit)}


@app.get("/api/companies/{company_id}/integrations/status")
async def integration_status(company_id: str):
    """Return current integration status (last sync times, connection state)."""
    from backend.modules.integrations.sync_log import SyncLogger
    return SyncLogger(company_id).get_sync_status()


@app.get("/api/integrations/fields")
async def list_system_fields():
    """Return all mappable HR system fields for the mapping UI."""
    from backend.modules.integrations.column_mapper import get_all_system_fields
    return {"fields": get_all_system_fields()}


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
