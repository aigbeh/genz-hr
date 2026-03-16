"""
GENZ HR — Audit Logger
Every edit is recorded. Nothing is ever deleted from audit logs.
"""
from datetime import datetime
from typing import Optional, Any
from sqlalchemy.orm import Session

from backend.core.database import AuditLog


def log_action(
    session: Session,
    user: str,
    action: str,
    module: str,
    record_type: str = "",
    record_id: str = "",
    field_changed: str = "",
    old_value: Any = None,
    new_value: Any = None,
    ip_address: str = "",
) -> AuditLog:
    """
    Write an immutable audit log entry.
    
    Examples:
        log_action(session, "Esther", "PAYROLL_EDIT", "payroll",
                   "PayrollRecord", "42", "bonus", 0, 50000)
    """
    entry = AuditLog(
        timestamp=datetime.utcnow(),
        user=user,
        action=action,
        module=module,
        record_type=record_type,
        record_id=str(record_id),
        field_changed=field_changed,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
        ip_address=ip_address,
    )
    session.add(entry)
    session.commit()
    return entry


def log_employee_edit(session: Session, user: str, employee_id: int, field: str, old_val: Any, new_val: Any):
    return log_action(session, user, "EMPLOYEE_EDIT", "employees", "Employee", str(employee_id), field, old_val, new_val)


def log_payroll_edit(session: Session, user: str, payroll_id: int, field: str, old_val: Any, new_val: Any):
    return log_action(session, user, "PAYROLL_EDIT", "payroll", "PayrollRecord", str(payroll_id), field, old_val, new_val)


def log_candidate_override(session: Session, user: str, candidate_id: int, field: str, old_val: Any, new_val: Any):
    return log_action(session, user, "CANDIDATE_OVERRIDE", "recruitment", "Candidate", str(candidate_id), field, old_val, new_val)


def log_performance_override(session: Session, user: str, task_id: int, field: str, old_val: Any, new_val: Any):
    return log_action(session, user, "PERFORMANCE_OVERRIDE", "performance", "TaskSheet", str(task_id), field, old_val, new_val)


def log_template_action(session: Session, user: str, action: str, template_id: int, details: str = ""):
    return log_action(session, user, f"TEMPLATE_{action}", "templates", "HRTemplate", str(template_id), details)


def log_approval(session: Session, user: str, record_type: str, record_id: str, action: str):
    return log_action(session, user, f"APPROVAL_{action}", "approvals", record_type, record_id)


def get_audit_trail(session: Session, record_type: str = None, record_id: str = None, limit: int = 100) -> list:
    """Retrieve audit log entries."""
    query = session.query(AuditLog)
    if record_type:
        query = query.filter(AuditLog.record_type == record_type)
    if record_id:
        query = query.filter(AuditLog.record_id == record_id)
    return query.order_by(AuditLog.timestamp.desc()).limit(limit).all()


def format_audit_entry(entry: AuditLog) -> dict:
    return {
        "timestamp": entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "user": entry.user,
        "action": entry.action,
        "module": entry.module,
        "record_type": entry.record_type,
        "record_id": entry.record_id,
        "field_changed": entry.field_changed,
        "old_value": entry.old_value,
        "new_value": entry.new_value,
    }
