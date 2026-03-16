"""
GENZ HR — Approval Gate
═══════════════════════════════════════════════════════════════
STRICT RULE: Nothing executes unless Esther approves it.

Every action flows through submit_action():

    ticket = submit_action(company_id, action_type, description, payload)

    if ticket.status == PENDING   →  queued in Esther's inbox, NOT executed
    if ticket.status == APPROVED  →  auto-executed (safe actions only)

Esther approves or rejects via the dashboard:
    approve_ticket(company_id, ticket_id)  →  action executes
    reject_ticket(company_id, ticket_id)   →  action permanently blocked

─────────────────────────────────────────────────────────────
REQUIRES APPROVAL (blocks until Esther acts):
  leave_approval     Leave request
  termination        Employee terminated
  payroll_release    Payroll disbursed / marked paid
  hiring_decision    Candidate hired
  hr_warning         Formal warning issued
  salary_change      Gross salary modified
  contract_issue     Employment contract issued
  policy_publish     HR policy published

AUTO-EXECUTE (safe, non-destructive — gate passes immediately):
  cv_parsing              CV uploaded and scored
  attendance_logging      Daily attendance recorded
  analytics               Performance reports generated
  task_sheet_generation   AI task sheet created
  daily_summary           GENZ Director daily report
  anomaly_detection       Flag only — no data changed
  template_render         Preview only
─────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional
import logging
logger = logging.getLogger("genz.gate")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")


# ─── Action Types ─────────────────────────────────────────────────────────────

class ActionType(str, Enum):
    # Requires Esther approval
    LEAVE_APPROVAL   = "leave_approval"
    TERMINATION      = "termination"
    PAYROLL_RELEASE  = "payroll_release"
    HIRING_DECISION  = "hiring_decision"
    HR_WARNING       = "hr_warning"
    SALARY_CHANGE    = "salary_change"
    CONTRACT_ISSUE   = "contract_issue"
    POLICY_PUBLISH   = "policy_publish"
    BULK_ACTION      = "bulk_action"

    # Auto-execute (safe)
    CV_PARSING            = "cv_parsing"
    ATTENDANCE_LOGGING    = "attendance_logging"
    ANALYTICS             = "analytics"
    TASK_SHEET_GENERATION = "task_sheet_generation"
    DAILY_SUMMARY         = "daily_summary"
    ANOMALY_DETECTION     = "anomaly_detection"
    TEMPLATE_RENDER       = "template_render"


AUTO_EXECUTE_ACTIONS: set[ActionType] = {
    ActionType.CV_PARSING,
    ActionType.ATTENDANCE_LOGGING,
    ActionType.ANALYTICS,
    ActionType.TASK_SHEET_GENERATION,
    ActionType.DAILY_SUMMARY,
    ActionType.ANOMALY_DETECTION,
    ActionType.TEMPLATE_RENDER,
}

ACTION_LABELS: dict[ActionType, str] = {
    ActionType.LEAVE_APPROVAL:        "Leave Request Approval",
    ActionType.TERMINATION:           "Employee Termination",
    ActionType.PAYROLL_RELEASE:       "Payroll Release",
    ActionType.HIRING_DECISION:       "Hiring Decision",
    ActionType.HR_WARNING:            "HR Warning / Disciplinary",
    ActionType.SALARY_CHANGE:         "Salary Change",
    ActionType.CONTRACT_ISSUE:        "Contract Issuance",
    ActionType.POLICY_PUBLISH:        "Policy Publication",
    ActionType.BULK_ACTION:           "Bulk Action",
    ActionType.CV_PARSING:            "CV Parsing",
    ActionType.ATTENDANCE_LOGGING:    "Attendance Logging",
    ActionType.ANALYTICS:             "Analytics",
    ActionType.TASK_SHEET_GENERATION: "Task Sheet Generation",
    ActionType.DAILY_SUMMARY:         "Daily Summary",
    ActionType.ANOMALY_DETECTION:     "Anomaly Detection",
    ActionType.TEMPLATE_RENDER:       "Template Render",
}

ACTION_RISK: dict[ActionType, str] = {
    ActionType.TERMINATION:      "critical",
    ActionType.PAYROLL_RELEASE:  "high",
    ActionType.HR_WARNING:       "high",
    ActionType.HIRING_DECISION:  "high",
    ActionType.SALARY_CHANGE:    "high",
    ActionType.LEAVE_APPROVAL:   "medium",
    ActionType.CONTRACT_ISSUE:   "medium",
    ActionType.POLICY_PUBLISH:   "medium",
    ActionType.BULK_ACTION:      "medium",
}


class TicketStatus(str, Enum):
    PENDING  = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ─── Ticket ───────────────────────────────────────────────────────────────────

@dataclass
class ApprovalTicket:
    ticket_id:    str
    company_id:   str
    action_type:  ActionType
    label:        str
    risk:         str
    requested_by: str
    description:  str
    payload:      dict
    status:       TicketStatus = TicketStatus.PENDING
    esther_note:  str = ""
    created_at:   datetime = field(default_factory=datetime.utcnow)
    resolved_at:  Optional[datetime] = None
    resolved_by:  str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action_type"] = self.action_type.value
        d["status"]      = self.status.value
        d["created_at"]  = self.created_at.isoformat() if self.created_at else None
        d["resolved_at"] = self.resolved_at.isoformat() if self.resolved_at else None
        return d


# ─── In-memory queue  (mirrors the DB for hot reads) ─────────────────────────

_queues: dict[str, dict[str, ApprovalTicket]] = {}


def _q(company_id: str) -> dict[str, ApprovalTicket]:
    if company_id not in _queues:
        _queues[company_id] = {}
    return _queues[company_id]


# ─── THE GATE ─────────────────────────────────────────────────────────────────

def requires_approval(action_type: ActionType) -> bool:
    """True → must wait for Esther.  False → safe to auto-execute."""
    return ActionType(action_type) not in AUTO_EXECUTE_ACTIONS


def submit_action(
    company_id:   str,
    action_type:  ActionType,
    description:  str,
    payload:      dict,
    requested_by: str = "GENZ Agent",
    session=None,
) -> ApprovalTicket:
    """
    THE GATE — every action enters here.

    Requires approval  →  ticket saved as PENDING, Esther notified, action BLOCKED.
    Auto-execute       →  ticket saved as APPROVED, action runs immediately.
    """
    action_type = ActionType(action_type)
    ticket_id   = str(uuid.uuid4())[:12].upper()

    ticket = ApprovalTicket(
        ticket_id    = ticket_id,
        company_id   = company_id,
        action_type  = action_type,
        label        = ACTION_LABELS.get(action_type, action_type.value),
        risk         = ACTION_RISK.get(action_type, "low"),
        requested_by = requested_by,
        description  = description,
        payload      = payload,
        status       = TicketStatus.PENDING,
        created_at   = datetime.utcnow(),
    )

    if requires_approval(action_type):
        # ── GATE CLOSED ──────────────────────────────────────────────────────
        _q(company_id)[ticket_id] = ticket
        _save_ticket(ticket, session)
        _notify_esther(ticket)
        logger.warning(
            f"[GATE BLOCKED] {action_type.value} | {company_id} | "
            f"ticket={ticket_id} | {description[:70]}"
        )
    else:
        # ── GATE OPEN (auto-execute) ─────────────────────────────────────────
        ticket.status      = TicketStatus.APPROVED
        ticket.resolved_at = datetime.utcnow()
        ticket.resolved_by = "system"
        _q(company_id)[ticket_id] = ticket
        _save_ticket(ticket, session)
        logger.info(f"[AUTO-EXEC] {action_type.value} | {company_id} | {description[:70]}")

    return ticket


def approve_ticket(
    company_id: str,
    ticket_id:  str,
    note:       str = "",
    session=None,
) -> tuple[bool, ApprovalTicket | str]:
    """
    Esther approves a PENDING ticket.
    Returns (True, ticket) so the caller can run execute_approved_ticket().
    """
    ticket = _get_ticket(company_id, ticket_id, session)
    if not ticket:
        return False, f"Ticket {ticket_id} not found"
    if ticket.status != TicketStatus.PENDING:
        return False, f"Ticket {ticket_id} is already {ticket.status.value}"

    ticket.status      = TicketStatus.APPROVED
    ticket.esther_note = note
    ticket.resolved_at = datetime.utcnow()
    ticket.resolved_by = "Esther"
    _q(company_id)[ticket_id] = ticket
    _update_ticket(ticket, session)

    logger.info(f"[APPROVED] {ticket.action_type} | {company_id} | ticket={ticket_id}")
    return True, ticket


def reject_ticket(
    company_id: str,
    ticket_id:  str,
    reason:     str,
    session=None,
) -> tuple[bool, str]:
    """Esther rejects a PENDING ticket. Action is permanently blocked."""
    ticket = _get_ticket(company_id, ticket_id, session)
    if not ticket:
        return False, f"Ticket {ticket_id} not found"
    if ticket.status != TicketStatus.PENDING:
        return False, f"Ticket {ticket_id} is already {ticket.status.value}"

    ticket.status      = TicketStatus.REJECTED
    ticket.esther_note = reason
    ticket.resolved_at = datetime.utcnow()
    ticket.resolved_by = "Esther"
    _q(company_id)[ticket_id] = ticket
    _update_ticket(ticket, session)

    logger.warning(
        f"[REJECTED] {ticket.action_type} | {company_id} | "
        f"ticket={ticket_id} | reason={reason[:60]}"
    )
    return True, "rejected"


# ─── Queue Views ──────────────────────────────────────────────────────────────

def get_pending_tickets(company_id: str, session=None) -> list[ApprovalTicket]:
    """All PENDING tickets for a company, newest first."""
    if session:
        _sync_from_db(company_id, session)
    return sorted(
        [t for t in _q(company_id).values() if t.status == TicketStatus.PENDING],
        key=lambda t: t.created_at, reverse=True,
    )


def get_all_tickets(company_id: str, session=None) -> list[ApprovalTicket]:
    """All tickets (all statuses) for a company, newest first."""
    if session:
        _sync_from_db(company_id, session)
    return sorted(
        list(_q(company_id).values()),
        key=lambda t: t.created_at, reverse=True,
    )


def get_platform_pending_counts() -> dict[str, int]:
    """Pending counts per company — for the director dashboard header."""
    return {
        cid: sum(1 for t in q.values() if t.status == TicketStatus.PENDING)
        for cid, q in _queues.items()
    }


# ─── DB Helpers ───────────────────────────────────────────────────────────────

def _save_ticket(ticket: ApprovalTicket, session):
    if not session:
        return
    try:
        from backend.core.database import ApprovalRecord
        rec = ApprovalRecord(
            ticket_id    = ticket.ticket_id,
            company_id   = ticket.company_id,
            action_type  = ticket.action_type.value,
            label        = ticket.label,
            risk         = ticket.risk,
            requested_by = ticket.requested_by,
            description  = ticket.description,
            payload      = json.dumps(ticket.payload),
            status       = ticket.status.value,
            esther_note  = ticket.esther_note,
            created_at   = ticket.created_at,
            resolved_at  = ticket.resolved_at,
            resolved_by  = ticket.resolved_by,
        )
        session.add(rec)
        session.commit()
    except Exception as e:
        logger.error(f"Failed to save ticket {ticket.ticket_id}: {e}")


def _update_ticket(ticket: ApprovalTicket, session):
    if not session:
        return
    try:
        from backend.core.database import ApprovalRecord
        rec = session.query(ApprovalRecord).filter(
            ApprovalRecord.ticket_id == ticket.ticket_id
        ).first()
        if rec:
            rec.status      = ticket.status.value
            rec.esther_note = ticket.esther_note
            rec.resolved_at = ticket.resolved_at
            rec.resolved_by = ticket.resolved_by
            session.commit()
    except Exception as e:
        logger.error(f"Failed to update ticket {ticket.ticket_id}: {e}")


def _get_ticket(company_id: str, ticket_id: str, session) -> Optional[ApprovalTicket]:
    ticket = _q(company_id).get(ticket_id)
    if not ticket and session:
        ticket = _load_from_db(ticket_id, session)
        if ticket:
            _q(company_id)[ticket_id] = ticket
    return ticket


def _load_from_db(ticket_id: str, session) -> Optional[ApprovalTicket]:
    try:
        from backend.core.database import ApprovalRecord
        rec = session.query(ApprovalRecord).filter(
            ApprovalRecord.ticket_id == ticket_id
        ).first()
        if not rec:
            return None
        return ApprovalTicket(
            ticket_id    = rec.ticket_id,
            company_id   = rec.company_id,
            action_type  = ActionType(rec.action_type),
            label        = rec.label or "",
            risk         = rec.risk or "medium",
            requested_by = rec.requested_by or "GENZ Agent",
            description  = rec.description or "",
            payload      = json.loads(rec.payload or "{}"),
            status       = TicketStatus(rec.status),
            esther_note  = rec.esther_note or "",
            created_at   = rec.created_at,
            resolved_at  = rec.resolved_at,
            resolved_by  = rec.resolved_by or "",
        )
    except Exception as e:
        logger.error(f"Failed to load ticket {ticket_id}: {e}")
        return None


def _sync_from_db(company_id: str, session):
    try:
        from backend.core.database import ApprovalRecord
        records = session.query(ApprovalRecord).filter(
            ApprovalRecord.company_id == company_id
        ).all()
        q = _q(company_id)
        for rec in records:
            if rec.ticket_id not in q:
                ticket = _load_from_db(rec.ticket_id, session)
                if ticket:
                    q[rec.ticket_id] = ticket
    except Exception as e:
        logger.error(f"DB sync error for {company_id}: {e}")


def _notify_esther(ticket: ApprovalTicket):
    from backend.core.config import settings
    risk_emoji = {"critical": "🚨", "high": "⚠️", "medium": "🔔"}.get(ticket.risk, "📋")
    logger.info(
        f"[NOTIFY → {settings.ESTHER_EMAIL}] "
        f"{risk_emoji} Approval needed: {ticket.label} | "
        f"{ticket.company_id} | ticket={ticket.ticket_id}"
    )
    # ── Email hook (configure to enable) ─────────────────────────────────────
    # from backend.core.scheduler import _notify_esther as send_email
    # send_email(
    #     subject = f"{risk_emoji} GENZ HR — Approval Required: {ticket.label}",
    #     body    = (
    #         f"Company:  {ticket.company_id}\n"
    #         f"Action:   {ticket.label}\n"
    #         f"Risk:     {ticket.risk.upper()}\n"
    #         f"Details:  {ticket.description}\n\n"
    #         f"Ticket:   {ticket.ticket_id}\n"
    #         f"Approve:  http://localhost:8501  →  Approval Queue\n"
    #     )
    # )
