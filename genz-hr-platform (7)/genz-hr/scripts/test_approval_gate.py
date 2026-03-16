#!/usr/bin/env python3
"""
GENZ HR — Approval Gate Test Suite
Tests every action type through the full gate lifecycle:
submit → pending → approve/reject → execute / block

Run: python scripts/test_approval_gate.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import traceback
from datetime import date

# ─── Test Helpers ─────────────────────────────────────────────────────────────

PASS = "✓"
FAIL = "✗"
results = []

def check(name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        raise AssertionError(f"FAILED: {name}")

def section(title: str):
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")


# ─── Import Gate ──────────────────────────────────────────────────────────────

section("0. Import checks")
from backend.core.approval_gate import (
    submit_action, approve_ticket, reject_ticket,
    get_pending_tickets, get_all_tickets,
    ActionType, TicketStatus, requires_approval,
    get_platform_pending_counts, AUTO_EXECUTE_ACTIONS,
)
check("approval_gate module imports", True)


# ─── Section 1: Action Classification ─────────────────────────────────────────

section("1. Action classification (which actions need approval?)")

MUST_APPROVE = [
    ActionType.LEAVE_APPROVAL,
    ActionType.TERMINATION,
    ActionType.PAYROLL_RELEASE,
    ActionType.HIRING_DECISION,
    ActionType.HR_WARNING,
    ActionType.SALARY_CHANGE,
    ActionType.CONTRACT_ISSUE,
    ActionType.POLICY_PUBLISH,
    ActionType.BULK_ACTION,
]

MUST_AUTO = [
    ActionType.CV_PARSING,
    ActionType.ATTENDANCE_LOGGING,
    ActionType.ANALYTICS,
    ActionType.TASK_SHEET_GENERATION,
    ActionType.DAILY_SUMMARY,
    ActionType.ANOMALY_DETECTION,
    ActionType.TEMPLATE_RENDER,
]

for action in MUST_APPROVE:
    check(f"{action.value} → requires approval", requires_approval(action))

for action in MUST_AUTO:
    check(f"{action.value} → auto-execute", not requires_approval(action))


# ─── Section 2: Gate blocks protected actions ─────────────────────────────────

section("2. Gate blocks consequential actions (PENDING, not executed)")

payroll_ticket = submit_action(
    "test_co", ActionType.PAYROLL_RELEASE,
    "Release March 2026 payroll for 12 employees — total net ₦6,240,000",
    {"period": "2026-03", "record_ids": list(range(1, 13)), "summary": {"headcount": 12, "total_net": 6_240_000}},
)
check("Payroll release → status PENDING", payroll_ticket.status == TicketStatus.PENDING)
check("Payroll release → risk is high", payroll_ticket.risk == "high")
check("Payroll release → ticket_id generated", len(payroll_ticket.ticket_id) > 0)

term_ticket = submit_action(
    "test_co", ActionType.TERMINATION,
    "Terminate Chidi Okonkwo (Senior Engineer) — effective 2026-04-01",
    {"employee_id": 1, "employee_name": "Chidi Okonkwo", "effective_date": "2026-04-01", "reason": "Misconduct"},
)
check("Termination → status PENDING", term_ticket.status == TicketStatus.PENDING)
check("Termination → risk is critical", term_ticket.risk == "critical")

leave_ticket = submit_action(
    "test_co", ActionType.LEAVE_APPROVAL,
    "Amara Nwosu requests annual leave from 2026-04-07 to 2026-04-11",
    {"leave_request_id": 1, "employee_name": "Amara Nwosu", "leave_type": "annual",
     "start_date": "2026-04-07", "end_date": "2026-04-11"},
)
check("Leave request → status PENDING", leave_ticket.status == TicketStatus.PENDING)

hire_ticket = submit_action(
    "test_co", ActionType.HIRING_DECISION,
    "Hire Biodun Oladele for Senior Engineer at ₦650,000/month (score: 91.2)",
    {"candidate_id": 3, "candidate_name": "Biodun Oladele", "offered_salary": 650_000,
     "position": "Senior Engineer", "start_date": "2026-05-01"},
)
check("Hiring decision → status PENDING", hire_ticket.status == TicketStatus.PENDING)
check("Hiring decision → risk is high", hire_ticket.risk == "high")

warning_ticket = submit_action(
    "test_co", ActionType.HR_WARNING,
    "Issue first warning to Tunde Adeyemi — repeated late attendance",
    {"employee_id": 3, "warning_type": "first warning", "reason": "Repeated late attendance"},
)
check("HR warning → status PENDING", warning_ticket.status == TicketStatus.PENDING)

salary_ticket = submit_action(
    "test_co", ActionType.SALARY_CHANGE,
    "Salary change: Ngozi Eze ₦750,000 → ₦850,000 (+13.3%)",
    {"employee_id": 4, "old_salary": 750_000, "new_salary": 850_000, "reason": "Annual review"},
)
check("Salary change → status PENDING", salary_ticket.status == TicketStatus.PENDING)


# ─── Section 3: Auto-execute actions pass through immediately ─────────────────

section("3. Auto-execute actions pass through gate immediately")

cv_ticket = submit_action(
    "test_co", ActionType.CV_PARSING,
    "Parse CV for Senior Engineer: biodun_cv.pdf",
    {"file_path": "/uploads/biodun_cv.pdf", "position": "Senior Engineer"},
)
check("CV parsing → status APPROVED (auto)", cv_ticket.status == TicketStatus.APPROVED)
check("CV parsing → resolved_by = system", cv_ticket.resolved_by == "system")

att_ticket = submit_action(
    "test_co", ActionType.ATTENDANCE_LOGGING,
    "Log attendance for employee 1 on 2026-03-13",
    {"employee_id": 1, "date": "2026-03-13"},
)
check("Attendance logging → status APPROVED (auto)", att_ticket.status == TicketStatus.APPROVED)

analytics_ticket = submit_action(
    "test_co", ActionType.ANALYTICS,
    "Generate performance analytics for 2026-03",
    {"period": "2026-03"},
)
check("Analytics → status APPROVED (auto)", analytics_ticket.status == TicketStatus.APPROVED)


# ─── Section 4: Pending queue is accurate ────────────────────────────────────

section("4. Pending queue contains exactly the blocked actions")

pending = get_pending_tickets("test_co")
check(
    f"Pending queue has 6 items (payroll, term, leave, hire, warning, salary)",
    len(pending) == 6,
    f"got {len(pending)}",
)

pending_ids = {t.ticket_id for t in pending}
for t in [payroll_ticket, term_ticket, leave_ticket, hire_ticket, warning_ticket, salary_ticket]:
    check(f"Ticket {t.ticket_id[:8]} is in pending queue", t.ticket_id in pending_ids)

all_tickets = get_all_tickets("test_co")
check(
    f"All-tickets view has 9 items (6 pending + 3 auto-exec)",
    len(all_tickets) == 9,
    f"got {len(all_tickets)}",
)


# ─── Section 5: Approval executes action and removes from queue ───────────────

section("5. Esther approves — ticket moves from PENDING → APPROVED")

ok, approved_ticket = approve_ticket("test_co", payroll_ticket.ticket_id, note="Figures verified")
check("approve_ticket returns True", ok)
check("Approved ticket status = APPROVED", approved_ticket.status == TicketStatus.APPROVED)
check("Approved ticket resolved_by = Esther", approved_ticket.resolved_by == "Esther")
check("Approved ticket note saved", approved_ticket.esther_note == "Figures verified")

ok2, approved_leave = approve_ticket("test_co", leave_ticket.ticket_id, note="Approved — enjoy!")
check("Leave approval → approved", ok2 and approved_leave.status == TicketStatus.APPROVED)

pending_after = get_pending_tickets("test_co")
check("Pending queue reduced by 2 after approvals", len(pending_after) == 4, f"got {len(pending_after)}")


# ─── Section 6: Rejection permanently blocks action ──────────────────────────

section("6. Esther rejects — action permanently blocked")

ok3, msg3 = reject_ticket("test_co", term_ticket.ticket_id, reason="Insufficient documentation")
check("reject_ticket returns True", ok3)

all_t2 = get_all_tickets("test_co")
rejected = [t for t in all_t2 if t.status == TicketStatus.REJECTED]
check("Rejected ticket appears in history", len(rejected) == 1)
check("Rejected ticket has correct reason", rejected[0].esther_note == "Insufficient documentation")

pending_after2 = get_pending_tickets("test_co")
check("Pending queue reduced by 1 after rejection", len(pending_after2) == 3, f"got {len(pending_after2)}")


# ─── Section 7: Double-approve / double-reject blocked ───────────────────────

section("7. Guard rails — cannot approve/reject a resolved ticket")

ok4, msg4 = approve_ticket("test_co", payroll_ticket.ticket_id)  # already approved
check("Cannot re-approve an already-approved ticket", not ok4, f"msg={msg4}")

ok5, msg5 = approve_ticket("test_co", term_ticket.ticket_id)    # already rejected
check("Cannot approve an already-rejected ticket", not ok5, f"msg={msg5}")

ok6, msg6 = reject_ticket("test_co", payroll_ticket.ticket_id, reason="second thought")
check("Cannot reject an already-approved ticket", not ok6, f"msg={msg6}")


# ─── Section 8: Platform pending counts ─────────────────────────────────────

section("8. Platform-wide pending counts")

counts = get_platform_pending_counts()
check("test_co pending count = 3", counts.get("test_co", 0) == 3, f"got {counts}")

# Submit to a second company
submit_action("test_co2", ActionType.PAYROLL_RELEASE, "Release payroll", {"period": "2026-03"})
submit_action("test_co2", ActionType.HIRING_DECISION, "Hire candidate", {"candidate_id": 9})
counts2 = get_platform_pending_counts()
check("test_co2 has 2 pending", counts2.get("test_co2", 0) == 2, f"got {counts2}")
total = sum(counts2.values())
check("Total platform pending = 5 (3 + 2)", total == 5, f"got {total}")


# ─── Section 9: Unknown ticket ID handled gracefully ─────────────────────────

section("9. Edge cases — unknown tickets, empty companies")

ok_bad, msg_bad = approve_ticket("test_co", "NONEXISTENT-ID")
check("Approve unknown ticket_id → returns False gracefully", not ok_bad)

ok_bad2, msg_bad2 = reject_ticket("test_co", "ALSO-FAKE", reason="whatever")
check("Reject unknown ticket_id → returns False gracefully", not ok_bad2)

empty_pending = get_pending_tickets("completely_new_company")
check("Empty company → empty pending list (no crash)", isinstance(empty_pending, list) and len(empty_pending) == 0)


# ─── Summary ─────────────────────────────────────────────────────────────────

section("RESULTS")
passed = sum(1 for s, *_ in results if s == PASS)
failed = sum(1 for s, *_ in results if s == FAIL)
total  = len(results)
print(f"\n  {passed}/{total} tests passed")
if failed == 0:
    print("  ✅ ALL TESTS PASSED — Approval gate is working correctly\n")
else:
    print(f"  ❌ {failed} tests FAILED\n")
    sys.exit(1)
