"""
GENZ HR — Database Layer
Enforces complete company data isolation via separate SQLite databases.
"""
from datetime import datetime, date
from typing import Optional, Dict
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, Date, Text, ForeignKey, Enum as SAEnum, JSON
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import StaticPool
import enum

from backend.core.config import settings, get_company_db_url

Base = declarative_base()

# ─── Master DB (company registry only) ────────────────────────────────────────

master_engine = create_engine(
    settings.MASTER_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
MasterSession = sessionmaker(bind=master_engine)


class CompanyRegistry(Base):
    __tablename__ = "company_registry"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    industry = Column(String)
    size = Column(String)
    contact_email = Column(String)
    is_active = Column(Boolean, default=True)
    onboarded_at = Column(DateTime, default=datetime.utcnow)
    agent_status = Column(String, default="idle")
    last_summary_at = Column(DateTime)


# ─── Per-Company Models ────────────────────────────────────────────────────────

class EmploymentStatus(str, enum.Enum):
    active = "active"
    on_leave = "on_leave"
    probation = "probation"
    terminated = "terminated"


class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String, unique=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True)
    phone = Column(String)
    department = Column(String)
    position = Column(String)
    employment_type = Column(String)
    status = Column(SAEnum(EmploymentStatus), default=EmploymentStatus.active)
    start_date = Column(Date)
    end_date = Column(Date)
    gross_salary = Column(Float, default=0.0)
    bank_name = Column(String)
    account_number = Column(String)
    pension_pin = Column(String)
    tax_id = Column(String)
    manager_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    email = Column(String)
    phone = Column(String)
    position_applied = Column(String)
    cv_path = Column(String)
    raw_cv_text = Column(Text)
    education_score = Column(Float, default=0.0)
    skills_score = Column(Float, default=0.0)
    experience_score = Column(Float, default=0.0)
    keyword_score = Column(Float, default=0.0)
    total_score = Column(Float, default=0.0)
    rank = Column(Integer)
    shortlisted = Column(Boolean, default=False)
    interview_status = Column(String, default="pending")
    interview_notes = Column(Text)
    ai_summary = Column(Text)
    esther_override_score = Column(Float)
    applied_at = Column(DateTime, default=datetime.utcnow)


class TaskSheet(Base):
    __tablename__ = "task_sheets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    period = Column(String)
    period_type = Column(String)
    tasks = Column(JSON)
    completion_pct = Column(Float, default=0.0)
    performance_score = Column(Float)
    lead_feedback = Column(Text)
    ai_analysis = Column(Text)
    bonus_eligible = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    submitted_at = Column(DateTime)


class AttendanceRecord(Base):
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    date = Column(Date, nullable=False)
    check_in = Column(DateTime)
    check_out = Column(DateTime)
    task_activity_score = Column(Float, default=0.0)
    comms_activity_score = Column(Float, default=0.0)
    meeting_score = Column(Float, default=0.0)
    presence_score = Column(Float, default=0.0)
    is_absent = Column(Boolean, default=False)
    is_approved_leave = Column(Boolean, default=False)
    notes = Column(String)


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    leave_type = Column(String)
    start_date = Column(Date)
    end_date = Column(Date)
    reason = Column(Text)
    status = Column(String, default="pending")
    approved_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class PayrollRecord(Base):
    __tablename__ = "payroll"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    period = Column(String)
    gross_salary = Column(Float)
    basic_salary = Column(Float)
    housing_allowance = Column(Float, default=0.0)
    transport_allowance = Column(Float, default=0.0)
    other_allowances = Column(Float, default=0.0)
    paye_tax = Column(Float)
    pension_employee = Column(Float)
    pension_employer = Column(Float)
    nhf_deduction = Column(Float)
    other_deductions = Column(Float, default=0.0)
    performance_bonus = Column(Float, default=0.0)
    net_salary = Column(Float)
    status = Column(String, default="draft")
    anomaly_flag = Column(Boolean, default=False)
    anomaly_reason = Column(Text)
    approved_by = Column(String)
    approved_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class HRTemplate(Base):
    __tablename__ = "hr_templates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    template_type = Column(String)
    file_format = Column(String)
    file_path = Column(String)
    content = Column(Text)
    variables = Column(JSON)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_by = Column(String, default="esther")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


# ─── Integration Models (v2 upgrade) ──────────────────────────────────────────

class IntegrationLog(Base):
    """Log of every data integration event — separate from AuditLog."""
    __tablename__ = "integration_logs"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    company_id    = Column(String, nullable=False, index=True)
    source        = Column(String, nullable=False)   # excel / google_sheets / manual
    event         = Column(String, nullable=False)
    file_name     = Column(String)
    sheet_url     = Column(String)
    file_hash     = Column(String)
    rows_affected = Column(Integer, default=0)
    details       = Column(Text)
    success       = Column(Boolean, default=True)
    timestamp     = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class DataIntegrationConfig(Base):
    """Per-company Google Sheets + Excel integration configuration."""
    __tablename__ = "data_integration_config"
    id                      = Column(Integer, primary_key=True, autoincrement=True)
    company_id              = Column(String, unique=True, nullable=False, index=True)
    # Google Sheets
    gsheet_id               = Column(String)
    gsheet_name             = Column(String)
    gsheet_url              = Column(String)
    gsheet_tab              = Column(String, default="Sheet1")
    credentials_path        = Column(String)
    auto_sync_enabled       = Column(Boolean, default=False)
    sync_interval_minutes   = Column(Integer, default=30)
    last_synced_at          = Column(DateTime)
    # Column mappings (JSON)
    mapping_json            = Column(Text, default="{}")
    # Excel last import
    last_excel_file         = Column(String)
    last_excel_hash         = Column(String)
    last_excel_imported_at  = Column(DateTime)
    created_at              = Column(DateTime, default=datetime.utcnow)
    updated_at              = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── Approval Records ──────────────────────────────────────────────────────────

class ApprovalRecord(Base):
    """Persistent store for every approval ticket."""
    __tablename__ = "approval_records"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id    = Column(String, unique=True, nullable=False, index=True)
    company_id   = Column(String, nullable=False)
    action_type  = Column(String, nullable=False)
    label        = Column(String)
    risk         = Column(String, default="medium")
    requested_by = Column(String, default="GENZ Agent")
    description  = Column(Text)
    payload      = Column(Text)
    status       = Column(String, default="pending")
    esther_note  = Column(Text)
    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at  = Column(DateTime)
    resolved_by  = Column(String)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    user = Column(String, nullable=False)
    action = Column(String, nullable=False)
    module = Column(String)
    record_type = Column(String)
    record_id = Column(String)
    field_changed = Column(String)
    old_value = Column(Text)
    new_value = Column(Text)
    ip_address = Column(String)


# ─── Engine Registry ──────────────────────────────────────────────────────────

_engines: Dict[str, any] = {}
_sessions: Dict[str, sessionmaker] = {}


def get_company_engine(company_id: str):
    if company_id not in _engines:
        db_url = get_company_db_url(company_id)
        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        _engines[company_id] = engine
        _sessions[company_id] = sessionmaker(bind=engine)
    return _engines[company_id]


def get_company_session(company_id: str) -> Session:
    if company_id not in _sessions:
        get_company_engine(company_id)
    return _sessions[company_id]()


def init_master_db():
    Base.metadata.create_all(master_engine)


def init_company_db(company_id: str):
    engine = get_company_engine(company_id)
    Base.metadata.create_all(engine)
    return engine
