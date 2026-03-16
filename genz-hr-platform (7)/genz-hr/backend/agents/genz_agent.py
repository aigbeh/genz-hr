"""
GENZ HR — GENZ Agent (Per-Company)
Every consequential action is routed through the ApprovalGate.
Nothing executes unless Esther approves it.

Gate logic:
    ticket = submit_action(...)
    if ticket.status == PENDING  → queued, Esther will review
    if ticket.status == APPROVED → auto-executed (safe actions only)
"""
import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional

logger = logging.getLogger("genz.agent")

from backend.core.database import (
    get_company_session, Employee, Candidate, TaskSheet,
    AttendanceRecord, PayrollRecord, LeaveRequest, EmploymentStatus
)
from backend.core.config import settings
from backend.core.approval_gate import (
    submit_action, get_pending_tickets,
    ActionType, TicketStatus, ApprovalTicket
)
from backend.modules.payroll_engine import calculate_company_payroll
from backend.modules.audit_logger import log_action


class GENZAgent:
    """
    Autonomous GENZ HR Agent for a single company.
    All consequential actions pass through the ApprovalGate before execution.
    """

    def __init__(self, company_id: str, company_name: str, llm_client=None):
        self.company_id   = company_id
        self.company_name = company_name
        self.llm          = llm_client
        self._session     = None
        logger.info(f"GENZ Agent initialized for: {company_name} ({company_id})")

    @property
    def session(self):
        if self._session is None or not self._session.is_active:
            self._session = get_company_session(self.company_id)
        return self._session

    # ═══════════════════════════════════════════════════════════════════════════
    # GATE-PROTECTED ACTIONS  (require Esther approval before anything changes)
    # ═══════════════════════════════════════════════════════════════════════════

    def request_leave_approval(self, leave_request_id: int, requested_by: str = "GENZ Agent") -> ApprovalTicket:
        """
        Submit a leave request to Esther's queue.
        Leave status stays 'pending' in DB until Esther approves the ticket.
        """
        session = self.session
        leave   = session.query(LeaveRequest).filter(LeaveRequest.id == leave_request_id).first()
        if not leave:
            raise ValueError(f"Leave request {leave_request_id} not found")
        emp = session.query(Employee).filter(Employee.id == leave.employee_id).first()
        emp_name = f"{emp.first_name} {emp.last_name}" if emp else "Unknown"

        return submit_action(
            company_id   = self.company_id,
            action_type  = ActionType.LEAVE_APPROVAL,
            description  = (
                f"{emp_name} requests {leave.leave_type} leave "
                f"from {leave.start_date} to {leave.end_date}"
            ),
            payload      = {
                "leave_request_id": leave_request_id,
                "employee_id":      leave.employee_id,
                "employee_name":    emp_name,
                "leave_type":       leave.leave_type,
                "start_date":       str(leave.start_date),
                "end_date":         str(leave.end_date),
                "reason":           leave.reason,
            },
            requested_by = requested_by,
            session      = session,
        )

    def execute_leave_approval(self, ticket: ApprovalTicket, approved: bool):
        """Runs ONLY after Esther approves the ticket."""
        session = self.session
        leave   = session.query(LeaveRequest).filter(
            LeaveRequest.id == ticket.payload["leave_request_id"]
        ).first()
        if not leave:
            return
        leave.status      = "approved" if approved else "rejected"
        leave.approved_by = "Esther"
        if approved:
            start   = date.fromisoformat(ticket.payload["start_date"])
            end     = date.fromisoformat(ticket.payload["end_date"])
            current = start
            while current <= end:
                if current.weekday() < 5:
                    rec = session.query(AttendanceRecord).filter(
                        AttendanceRecord.employee_id == leave.employee_id,
                        AttendanceRecord.date        == current,
                    ).first()
                    if not rec:
                        rec = AttendanceRecord(
                            employee_id      = leave.employee_id,
                            date             = current,
                            is_approved_leave= True,
                            presence_score   = 100.0,
                        )
                        session.add(rec)
                    else:
                        rec.is_approved_leave = True
                        rec.presence_score    = 100.0
                current += timedelta(days=1)
        session.commit()

    def request_termination(
        self, employee_id: int, reason: str,
        effective_date: str, requested_by: str = "GENZ Agent",
    ) -> ApprovalTicket:
        """
        Queue a termination. Employee record is NOT touched
        until Esther explicitly approves the ticket.
        """
        session = self.session
        emp     = session.query(Employee).filter(Employee.id == employee_id).first()
        if not emp:
            raise ValueError(f"Employee {employee_id} not found")

        return submit_action(
            company_id  = self.company_id,
            action_type = ActionType.TERMINATION,
            description = (
                f"Terminate {emp.first_name} {emp.last_name} "
                f"({emp.position}) — effective {effective_date}"
            ),
            payload = {
                "employee_id":    employee_id,
                "employee_name":  f"{emp.first_name} {emp.last_name}",
                "position":       emp.position,
                "department":     emp.department,
                "reason":         reason,
                "effective_date": effective_date,
            },
            requested_by = requested_by,
            session      = session,
        )

    def execute_termination(self, ticket: ApprovalTicket):
        """Runs ONLY after Esther approves."""
        session = self.session
        emp     = session.query(Employee).filter(
            Employee.id == ticket.payload["employee_id"]
        ).first()
        if emp:
            emp.status   = EmploymentStatus.terminated
            emp.end_date = date.fromisoformat(ticket.payload["effective_date"])
            session.commit()
            log_action(session, "Esther", "TERMINATION_EXECUTED", "employees",
                       "Employee", str(emp.id), "status", "active", "terminated")

    def request_payroll_release(self, period: str, requested_by: str = "GENZ Agent") -> ApprovalTicket:
        """
        Compute payroll (safe, no money moves) and queue the RELEASE for approval.
        Records stay in DRAFT status until Esther approves the ticket.
        """
        session   = self.session
        employees = session.query(Employee).filter(
            Employee.status == EmploymentStatus.active
        ).all()
        emp_data = [
            {"id": e.id, "name": f"{e.first_name} {e.last_name}",
             "gross_salary": e.gross_salary, "bonus": 0}
            for e in employees
        ]
        result = calculate_company_payroll(emp_data, period)

        # Persist as DRAFT records — money does NOT move yet
        record_ids = []
        for r in result["results"]:
            existing = session.query(PayrollRecord).filter(
                PayrollRecord.employee_id == int(r["employee_id"]),
                PayrollRecord.period      == period,
            ).first()
            if not existing:
                rec = PayrollRecord(
                    employee_id        = int(r["employee_id"]),
                    period             = period,
                    gross_salary       = r["gross_salary"],
                    basic_salary       = r["basic_salary"],
                    housing_allowance  = r["housing_allowance"],
                    transport_allowance= r["transport_allowance"],
                    paye_tax           = r["paye_monthly"],
                    pension_employee   = r["pension_employee"],
                    pension_employer   = r["pension_employer"],
                    nhf_deduction      = r["nhf_deduction"],
                    performance_bonus  = r["performance_bonus"],
                    other_deductions   = r["other_deductions"],
                    net_salary         = r["net_salary"],
                    status             = "draft",           # ← stays draft until approval
                    anomaly_flag       = r["anomaly"],
                    anomaly_reason     = r["anomaly_reason"],
                )
                session.add(rec)
                session.flush()
                record_ids.append(rec.id)
            else:
                record_ids.append(existing.id)
        session.commit()

        s = result["summary"]
        return submit_action(
            company_id  = self.company_id,
            action_type = ActionType.PAYROLL_RELEASE,
            description = (
                f"Release {period} payroll: {s['headcount']} employees · "
                f"Total net ₦{s['total_net']:,.0f}"
                + (f" · ⚠ {len(result['anomalies'])} anomalies" if result["anomalies"] else "")
            ),
            payload = {
                "period":     period,
                "record_ids": record_ids,
                "summary":    s,
                "anomalies":  result["anomalies"],
            },
            requested_by = requested_by,
            session      = session,
        )

    def execute_payroll_release(self, ticket: ApprovalTicket):
        """Runs ONLY after Esther approves — flips records from draft → approved."""
        session    = self.session
        for rid in ticket.payload.get("record_ids", []):
            rec = session.query(PayrollRecord).filter(PayrollRecord.id == rid).first()
            if rec and rec.status == "draft":
                rec.status      = "approved"
                rec.approved_by = "Esther"
                rec.approved_at = datetime.utcnow()
        session.commit()
        log_action(session, "Esther", "PAYROLL_RELEASED", "payroll",
                   "PayrollRecord", ticket.ticket_id,
                   "status", "draft", f"approved — {ticket.payload['period']}")

    def request_hiring_decision(
        self, candidate_id: int, position: str,
        offered_salary: float, start_date: str,
        requested_by: str = "GENZ Agent",
    ) -> ApprovalTicket:
        """
        Queue a hiring decision. No offer letter is sent,
        no employee record created, until Esther approves.
        """
        session   = self.session
        candidate = session.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found")
        score = candidate.esther_override_score or candidate.total_score

        return submit_action(
            company_id  = self.company_id,
            action_type = ActionType.HIRING_DECISION,
            description = (
                f"Hire {candidate.name} for {position} "
                f"at ₦{offered_salary:,.0f}/month (score: {score:.1f})"
            ),
            payload = {
                "candidate_id":    candidate_id,
                "candidate_name":  candidate.name,
                "candidate_email": candidate.email,
                "position":        position,
                "offered_salary":  offered_salary,
                "start_date":      start_date,
                "ai_score":        score,
            },
            requested_by = requested_by,
            session      = session,
        )

    def execute_hiring_decision(self, ticket: ApprovalTicket):
        """Runs ONLY after Esther approves — creates employee record."""
        session   = self.session
        payload   = ticket.payload
        candidate = session.query(Candidate).filter(
            Candidate.id == payload["candidate_id"]
        ).first()
        if candidate:
            candidate.interview_status = "hired"
        parts = payload["candidate_name"].split(" ", 1)
        emp = Employee(
            employee_id     = f"EMP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            first_name      = parts[0],
            last_name       = parts[1] if len(parts) > 1 else "",
            email           = payload.get("candidate_email", ""),
            position        = payload["position"],
            gross_salary    = payload["offered_salary"],
            start_date      = date.fromisoformat(payload["start_date"]),
            status          = EmploymentStatus.probation,
            employment_type = "full-time",
        )
        session.add(emp)
        session.commit()
        log_action(session, "Esther", "HIRE_EXECUTED", "recruitment",
                   "Candidate", str(payload["candidate_id"]),
                   "interview_status", "shortlisted", "hired")

    def request_hr_warning(
        self, employee_id: int, warning_type: str,
        reason: str, requested_by: str = "GENZ Agent",
    ) -> ApprovalTicket:
        """Queue a formal warning for Esther's approval before it is issued."""
        session = self.session
        emp     = session.query(Employee).filter(Employee.id == employee_id).first()
        if not emp:
            raise ValueError(f"Employee {employee_id} not found")

        return submit_action(
            company_id  = self.company_id,
            action_type = ActionType.HR_WARNING,
            description = (
                f"Issue {warning_type} warning to "
                f"{emp.first_name} {emp.last_name} ({emp.department}): {reason[:80]}"
            ),
            payload = {
                "employee_id":   employee_id,
                "employee_name": f"{emp.first_name} {emp.last_name}",
                "warning_type":  warning_type,
                "reason":        reason,
                "position":      emp.position,
                "department":    emp.department,
            },
            requested_by = requested_by,
            session      = session,
        )

    def request_salary_change(
        self, employee_id: int, new_salary: float,
        reason: str, effective: str,
        requested_by: str = "GENZ Agent",
    ) -> ApprovalTicket:
        """Queue a salary change. Salary unchanged in DB until Esther approves."""
        session = self.session
        emp     = session.query(Employee).filter(Employee.id == employee_id).first()
        if not emp:
            raise ValueError(f"Employee {employee_id} not found")
        old = emp.gross_salary
        pct = ((new_salary - old) / old * 100) if old else 0

        return submit_action(
            company_id  = self.company_id,
            action_type = ActionType.SALARY_CHANGE,
            description = (
                f"Salary change: {emp.first_name} {emp.last_name} "
                f"₦{old:,.0f} → ₦{new_salary:,.0f} ({pct:+.1f}%)"
            ),
            payload = {
                "employee_id":   employee_id,
                "employee_name": f"{emp.first_name} {emp.last_name}",
                "old_salary":    old,
                "new_salary":    new_salary,
                "pct_change":    round(pct, 2),
                "reason":        reason,
                "effective":     effective,
            },
            requested_by = requested_by,
            session      = session,
        )

    def execute_salary_change(self, ticket: ApprovalTicket):
        """Runs ONLY after Esther approves."""
        session = self.session
        emp     = session.query(Employee).filter(
            Employee.id == ticket.payload["employee_id"]
        ).first()
        if emp:
            old = emp.gross_salary
            emp.gross_salary = ticket.payload["new_salary"]
            session.commit()
            log_action(session, "Esther", "SALARY_CHANGED", "employees",
                       "Employee", str(emp.id),
                       "gross_salary", str(old), str(ticket.payload["new_salary"]))

    # ═══════════════════════════════════════════════════════════════════════════
    # APPROVAL DISPATCHER  — called by dashboard / API after Esther approves
    # ═══════════════════════════════════════════════════════════════════════════

    def execute_approved_ticket(self, ticket: ApprovalTicket) -> dict:
        action = ActionType(ticket.action_type)
        logger.info(f"Executing approved ticket {ticket.ticket_id} — {action.value}")
        try:
            dispatch = {
                ActionType.LEAVE_APPROVAL:  lambda: self.execute_leave_approval(ticket, approved=True),
                ActionType.TERMINATION:     lambda: self.execute_termination(ticket),
                ActionType.PAYROLL_RELEASE: lambda: self.execute_payroll_release(ticket),
                ActionType.HIRING_DECISION: lambda: self.execute_hiring_decision(ticket),
                ActionType.SALARY_CHANGE:   lambda: self.execute_salary_change(ticket),
                ActionType.HR_WARNING:      lambda: None,  # warning is the ticket itself
            }
            fn = dispatch.get(action)
            if fn:
                fn()
                return {"executed": True, "ticket_id": ticket.ticket_id, "action": action.value}
            return {"executed": False, "reason": f"No executor for {action.value}"}
        except Exception as e:
            logger.error(f"Execution failed for ticket {ticket.ticket_id}: {e}")
            return {"executed": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════════════════════
    # AUTO-EXECUTE ACTIONS  (safe, non-destructive — gate passes immediately)
    # ═══════════════════════════════════════════════════════════════════════════

    def log_attendance(
        self, employee_id: int, check_date: date,
        check_in: Optional[datetime] = None,
        task_activity_score: float = 0.0,
        comms_activity_score: float = 0.0,
        meeting_score: float = 0.0,
    ) -> dict:
        """Auto-execute: safe read/write of attendance data."""
        ticket = submit_action(
            company_id  = self.company_id,
            action_type = ActionType.ATTENDANCE_LOGGING,
            description = f"Log attendance for employee {employee_id} on {check_date}",
            payload     = {"employee_id": employee_id, "date": str(check_date)},
            session     = self.session,
        )
        session  = self.session
        existing = session.query(AttendanceRecord).filter(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.date        == check_date,
        ).first()
        if not existing:
            checkin_score = 100.0 if check_in else 0.0
            presence = (
                checkin_score         * 0.40
                + task_activity_score * 0.30
                + comms_activity_score * 0.20
                + meeting_score        * 0.10
            )
            rec = AttendanceRecord(
                employee_id          = employee_id,
                date                 = check_date,
                check_in             = check_in,
                task_activity_score  = task_activity_score,
                comms_activity_score = comms_activity_score,
                meeting_score        = meeting_score,
                presence_score       = round(presence, 2),
                is_absent            = presence < 30,
            )
            session.add(rec)
            session.commit()
        return {"logged": True, "ticket_id": ticket.ticket_id}

    def parse_cv(self, file_path: str, position: str) -> dict:
        """Auto-execute: parse and score a CV file."""
        ticket = submit_action(
            company_id  = self.company_id,
            action_type = ActionType.CV_PARSING,
            description = f"Parse CV for {position}: {file_path.split('/')[-1]}",
            payload     = {"file_path": file_path, "position": position},
            session     = self.session,
        )
        from backend.modules.cv_parser import score_candidate
        result = score_candidate(file_path, position)
        return {"parsed": True, "ticket_id": ticket.ticket_id, "result": result.to_dict()}

    def generate_analytics(self, period: str) -> dict:
        """Auto-execute: run performance analytics (read-only)."""
        ticket = submit_action(
            company_id  = self.company_id,
            action_type = ActionType.ANALYTICS,
            description = f"Generate performance analytics for {period}",
            payload     = {"period": period},
            session     = self.session,
        )
        from backend.modules.performance_analytics import (
            get_performance_trends, get_underperformer_alerts, get_top_performers
        )
        return {
            "generated":       True,
            "ticket_id":       ticket.ticket_id,
            "trends":          get_performance_trends(self.company_id),
            "underperformers": get_underperformer_alerts(self.company_id),
            "top_performers":  get_top_performers(self.company_id),
        }

    def generate_task_sheet(self, employee_id: int, period: str, period_type: str = "monthly") -> dict:
        """Auto-execute: generate task sheet (still requires lead to enter scores)."""
        ticket = submit_action(
            company_id  = self.company_id,
            action_type = ActionType.TASK_SHEET_GENERATION,
            description = f"Generate {period_type} task sheet for employee {employee_id} — {period}",
            payload     = {"employee_id": employee_id, "period": period},
            session     = self.session,
        )
        session = self.session
        emp     = session.query(Employee).filter(Employee.id == employee_id).first()
        if not emp:
            return {"error": "Employee not found"}
        tasks = self._default_tasks(emp.position or "general")
        sheet = TaskSheet(
            employee_id  = employee_id,
            period       = period,
            period_type  = period_type,
            tasks        = tasks,
            completion_pct = 0.0,
        )
        session.add(sheet)
        session.commit()
        return {
            "generated": True, "ticket_id": ticket.ticket_id,
            "task_sheet_id": sheet.id, "tasks": tasks,
        }

    def _default_tasks(self, position: str) -> list[dict]:
        pos = position.lower()
        if any(x in pos for x in ["engineer", "developer", "dev"]):
            return [
                {"description": "Sprint ticket completion",  "weight": 30, "status": "pending"},
                {"description": "Code reviews",              "weight": 20, "status": "pending"},
                {"description": "Documentation",             "weight": 15, "status": "pending"},
                {"description": "Standups",                  "weight": 15, "status": "pending"},
                {"description": "Technical upskilling",      "weight": 10, "status": "pending"},
                {"description": "Stakeholder communication", "weight": 10, "status": "pending"},
            ]
        elif any(x in pos for x in ["sales", "business", "bd"]):
            return [
                {"description": "Sales target",    "weight": 40, "status": "pending"},
                {"description": "New outreach",    "weight": 25, "status": "pending"},
                {"description": "Pipeline follow", "weight": 20, "status": "pending"},
                {"description": "CRM updates",     "weight": 15, "status": "pending"},
            ]
        return [
            {"description": "Core responsibilities", "weight": 40, "status": "pending"},
            {"description": "Project deliverables",  "weight": 30, "status": "pending"},
            {"description": "Team collaboration",    "weight": 20, "status": "pending"},
            {"description": "Reporting",             "weight": 10, "status": "pending"},
        ]

    # ═══════════════════════════════════════════════════════════════════════════
    # SCAN / REPORT
    # ═══════════════════════════════════════════════════════════════════════════

    def scan_recruitment_pipeline(self) -> dict:
        session    = self.session
        candidates = session.query(Candidate).all()
        pending    = [c for c in candidates if c.shortlisted and c.interview_status == "pending"]
        return {
            "total_candidates":   len(candidates),
            "shortlisted":        sum(1 for c in candidates if c.shortlisted),
            "pending_interviews": len(pending),
            "alerts": [f"{len(pending)} shortlisted candidates awaiting interview"] if pending else [],
        }

    def detect_attendance_issues(self) -> list[dict]:
        session   = self.session
        week_ago  = date.today() - timedelta(days=7)
        employees = session.query(Employee).filter(
            Employee.status == EmploymentStatus.active
        ).all()
        issues = []
        for emp in employees:
            records = session.query(AttendanceRecord).filter(
                AttendanceRecord.employee_id      == emp.id,
                AttendanceRecord.date             >= week_ago,
                AttendanceRecord.is_approved_leave == False,
            ).all()
            if not records:
                issues.append({"employee_id": emp.id,
                               "name": f"{emp.first_name} {emp.last_name}",
                               "issue": "No attendance records in 7 days", "severity": "high"})
                continue
            avg    = sum(r.presence_score or 0 for r in records) / len(records)
            absent = sum(1 for r in records if r.is_absent)
            if avg < 40 or absent >= 2:
                issues.append({"employee_id": emp.id,
                               "name": f"{emp.first_name} {emp.last_name}",
                               "issue": f"Avg presence {avg:.0f}% · {absent} absent days",
                               "severity": "high" if absent >= 3 else "medium"})
        return issues

    def generate_daily_report(self) -> dict:
        period  = date.today().strftime("%Y-%m")
        pending = get_pending_tickets(self.company_id, self.session)
        return {
            "company_id":        self.company_id,
            "company_name":      self.company_name,
            "date":              date.today().isoformat(),
            "recruitment":       self.scan_recruitment_pipeline(),
            "attendance":        {"issues": self.detect_attendance_issues()[:5]},
            "payroll":           {"period": period, "due_soon": date.today().day >= 23},
            "pending_approvals": len(pending),
            "alerts":            [
                f"{len(pending)} action(s) awaiting Esther's approval"
            ] if pending else [],
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # AI PERFORMANCE ANALYSIS  (Issue 1 fix)
    # ═══════════════════════════════════════════════════════════════════════════

    def analyze_performance(self, period_filter: str) -> dict:
        """
        Pull employee + attendance + task data, send to Ollama, return
        structured performance insights.

        Returns:
            {
                top_performers:   [...],
                low_performers:   [...],
                attendance_risk:  [...],
                recommendations:  [...],
                avg_performance_score: float,
                avg_completion_pct:    float,
                total_employees_reviewed: int,
            }
        Falls back gracefully when Ollama is offline.
        """
        session = self.session

        # ── Gather employees ─────────────────────────────────────────────────
        employees = session.query(Employee).filter(
            Employee.status == EmploymentStatus.active
        ).all()

        if not employees:
            return {"message": "No employees available for analysis"}

        # ── Gather task sheets for the period ────────────────────────────────
        sheets = session.query(TaskSheet).filter(
            TaskSheet.period == period_filter
        ).all()
        sheet_map = {s.employee_id: s for s in sheets}

        # ── Gather attendance (last 30 days) ─────────────────────────────────
        thirty_days_ago = date.today() - timedelta(days=30)
        attendance_map: dict[int, dict] = {}
        for emp in employees:
            records = session.query(AttendanceRecord).filter(
                AttendanceRecord.employee_id == emp.id,
                AttendanceRecord.date >= thirty_days_ago,
            ).all()
            if records:
                avg_presence = sum(r.presence_score or 0 for r in records) / len(records)
                absent_days  = sum(1 for r in records if r.is_absent)
            else:
                avg_presence = 0.0
                absent_days  = 0
            attendance_map[emp.id] = {"avg_presence": avg_presence, "absent_days": absent_days}

        # ── Build per-employee summary ────────────────────────────────────────
        employee_summaries = []
        total_score   = 0.0
        total_compl   = 0.0
        scored_count  = 0

        for emp in employees:
            sheet  = sheet_map.get(emp.id)
            att    = attendance_map.get(emp.id, {"avg_presence": 0, "absent_days": 0})
            perf   = sheet.performance_score if sheet and sheet.performance_score else None
            compl  = sheet.completion_pct    if sheet and sheet.completion_pct    else 0.0
            if perf is not None:
                total_score  += perf
                total_compl  += compl
                scored_count += 1

            employee_summaries.append({
                "name":             f"{emp.first_name} {emp.last_name}",
                "department":       emp.department or "—",
                "position":         emp.position or "—",
                "performance_score": perf,
                "completion_pct":   compl,
                "avg_presence":     round(att["avg_presence"], 1),
                "absent_days":      att["absent_days"],
            })

        avg_score = total_score / scored_count if scored_count > 0 else 0.0
        avg_compl = total_compl / scored_count if scored_count > 0 else 0.0

        # ── Derive lists without AI (always available) ────────────────────────
        scored = [e for e in employee_summaries if e["performance_score"] is not None]
        scored_sorted = sorted(scored, key=lambda x: x["performance_score"], reverse=True)

        top_performers = [
            {"name": e["name"], "score": e["performance_score"], "dept": e["department"]}
            for e in scored_sorted[:3] if e["performance_score"] >= 70
        ]
        low_performers = [
            {"name": e["name"], "score": e["performance_score"], "dept": e["department"]}
            for e in scored_sorted if e["performance_score"] < 50
        ]
        attendance_risk = [
            {"name": e["name"], "absent_days": e["absent_days"], "avg_presence": e["avg_presence"]}
            for e in employee_summaries
            if e["absent_days"] >= 3 or e["avg_presence"] < 40
        ]

        # ── Ask Ollama for recommendations (safe fallback) ────────────────────
        recommendations = self._get_ai_recommendations(employee_summaries, period_filter)

        return {
            "period":                  period_filter,
            "top_performers":          top_performers,
            "low_performers":          low_performers,
            "attendance_risk":         attendance_risk,
            "recommendations":         recommendations,
            "avg_performance_score":   round(avg_score, 1),
            "avg_completion_pct":      round(avg_compl, 1),
            "total_employees_reviewed": len(employees),
            "employees_with_scores":   scored_count,
        }

    def _get_ai_recommendations(self, summaries: list[dict], period: str) -> list[str]:
        """
        Call Ollama for HR recommendations. Returns a plain list of strings.
        Never crashes — returns fallback text if Ollama is unavailable.
        Issue 4 fix: safe AI calls with timeout and fallback.
        """
        # Build a compact text summary for the prompt
        lines = []
        for emp in summaries[:15]:  # limit context size
            score_txt = f"{emp['performance_score']:.0f}/100" if emp["performance_score"] else "no score"
            lines.append(
                f"- {emp['name']} ({emp['department']}): score={score_txt}, "
                f"completion={emp['completion_pct']:.0f}%, presence={emp['avg_presence']:.0f}%, "
                f"absent={emp['absent_days']}d"
            )

        prompt = (
            f"You are an HR analyst for a Nigerian company. "
            f"Here is employee performance data for {period}:\n\n"
            + "\n".join(lines)
            + "\n\nProvide 3-5 concise, actionable HR recommendations. "
            "Return ONLY a JSON array of strings, e.g. [\"Rec 1\", \"Rec 2\"]. "
            "No preamble, no markdown."
        )

        try:
            import urllib.request
            import urllib.error

            payload = json.dumps({
                "model":  settings.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 512},
            }).encode()

            req = urllib.request.Request(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                data    = payload,
                headers = {"Content-Type": "application/json"},
                method  = "POST",
            )

            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
                raw  = data.get("response", "").strip()

            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(r) for r in parsed[:6]]
            return [str(parsed)]

        except (ImportError, OSError, TimeoutError) as e:
            logger.warning(f"Ollama unavailable for recommendations: {e}")
            return self._fallback_recommendations(summaries)
        except json.JSONDecodeError:
            logger.warning("Ollama returned non-JSON — using fallback")
            return self._fallback_recommendations(summaries)
        except Exception as e:
            logger.warning(f"AI recommendation error: {e}")
            return self._fallback_recommendations(summaries)

    def _fallback_recommendations(self, summaries: list[dict]) -> list[str]:
        """Rule-based recommendations when Ollama is offline."""
        recs = []
        absent_risk = [e for e in summaries if e.get("absent_days", 0) >= 3]
        low_score   = [e for e in summaries if (e.get("performance_score") or 0) < 50
                       and e.get("performance_score") is not None]
        no_score    = [e for e in summaries if e.get("performance_score") is None]

        if absent_risk:
            names = ", ".join(e["name"] for e in absent_risk[:3])
            recs.append(f"Schedule welfare check-ins for high-absenteeism employees: {names}.")
        if low_score:
            names = ", ".join(e["name"] for e in low_score[:3])
            recs.append(f"Consider performance improvement plans (PIP) for: {names}.")
        if no_score:
            recs.append(f"{len(no_score)} employee(s) have no task sheets for this period — assign task sheets to enable scoring.")
        if not recs:
            recs.append("Overall performance looks healthy. Continue regular check-ins and task sheet reviews.")
        recs.append("Tip: Start Ollama (`ollama serve`) for AI-powered recommendations.")
        return recs

    def close(self):
        if self._session:
            self._session.close()
