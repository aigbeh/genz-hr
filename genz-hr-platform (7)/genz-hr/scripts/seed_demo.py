#!/usr/bin/env python3
"""
GENZ HR — Sample Data Seeder
Creates realistic test data for one company to demonstrate the platform.
Usage: python scripts/seed_demo.py --company-id demo_company
"""
import sys
import argparse
from pathlib import Path
from datetime import date, timedelta
import random

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.database import (
    init_master_db, init_company_db, MasterSession,
    CompanyRegistry, get_company_session,
    Employee, TaskSheet, AttendanceRecord, Candidate, EmploymentStatus
)
from backend.core.config import get_company_dir
from rich.console import Console

console = Console()

DEMO_EMPLOYEES = [
    {"employee_id": "EMP-001", "first_name": "Chidi",    "last_name": "Okonkwo",  "position": "Senior Backend Engineer",  "dept": "Engineering",  "salary": 650_000},
    {"employee_id": "EMP-002", "first_name": "Amara",    "last_name": "Nwosu",    "position": "Product Manager",          "dept": "Product",      "salary": 850_000},
    {"employee_id": "EMP-003", "first_name": "Tunde",    "last_name": "Adeyemi",  "position": "Frontend Developer",       "dept": "Engineering",  "salary": 450_000},
    {"employee_id": "EMP-004", "first_name": "Ngozi",    "last_name": "Eze",      "position": "Head of Sales",            "dept": "Sales",        "salary": 750_000},
    {"employee_id": "EMP-005", "first_name": "Emeka",    "last_name": "Obi",      "position": "Data Analyst",             "dept": "Data",         "salary": 520_000},
    {"employee_id": "EMP-006", "first_name": "Fatima",   "last_name": "Aliyu",    "position": "UI/UX Designer",           "dept": "Design",       "salary": 400_000},
    {"employee_id": "EMP-007", "first_name": "Obinna",   "last_name": "Igwe",     "position": "DevOps Engineer",          "dept": "Engineering",  "salary": 600_000},
    {"employee_id": "EMP-008", "first_name": "Adaeze",   "last_name": "Okafor",   "position": "HR Coordinator",           "dept": "HR",           "salary": 380_000},
    {"employee_id": "EMP-009", "first_name": "Seun",     "last_name": "Afolabi",  "position": "Business Development",     "dept": "Sales",        "salary": 480_000},
    {"employee_id": "EMP-010", "first_name": "Kemi",     "last_name": "Balogun",  "position": "Finance Manager",          "dept": "Finance",      "salary": 700_000},
]

DEMO_CANDIDATES = [
    {"name": "Ahmed Musa",       "email": "ahmed@example.com",   "position": "Senior Backend Engineer", "score": 82.5},
    {"name": "Chiamaka Onyeka",  "email": "chi@example.com",     "position": "Senior Backend Engineer", "score": 76.0},
    {"name": "Biodun Oladele",   "email": "bio@example.com",     "position": "Senior Backend Engineer", "score": 91.2},
    {"name": "Nkechi Osei",      "email": "nke@example.com",     "position": "UI/UX Designer",          "score": 68.5},
    {"name": "Femi Adeleke",     "email": "femi@example.com",    "position": "UI/UX Designer",          "score": 55.0},
]


def seed(company_id: str, company_name: str):
    init_master_db()

    # Register company if not exists
    session = MasterSession()
    existing = session.query(CompanyRegistry).filter(CompanyRegistry.id == company_id).first()
    if not existing:
        company = CompanyRegistry(
            id=company_id, name=company_name,
            industry="Technology", size="startup",
        )
        session.add(company)
        session.commit()
    session.close()

    init_company_db(company_id)
    get_company_dir(company_id)

    co_session = get_company_session(company_id)

    console.print(f"\n[bold green]Seeding {company_name}...[/bold green]")

    # Employees
    console.print("  Adding employees...")
    for emp_data in DEMO_EMPLOYEES:
        existing_emp = co_session.query(Employee).filter(
            Employee.employee_id == emp_data["employee_id"]
        ).first()
        if not existing_emp:
            emp = Employee(
                employee_id=emp_data["employee_id"],
                first_name=emp_data["first_name"],
                last_name=emp_data["last_name"],
                email=f"{emp_data['first_name'].lower()}.{emp_data['last_name'].lower()}@{company_id}.ng",
                phone=f"080{random.randint(10000000, 99999999)}",
                department=emp_data["dept"],
                position=emp_data["position"],
                employment_type="full-time",
                status=EmploymentStatus.active,
                gross_salary=emp_data["salary"],
                start_date=date.today() - timedelta(days=random.randint(30, 730)),
                bank_name=random.choice(["GTBank", "Access Bank", "First Bank", "Zenith Bank", "UBA"]),
                account_number=f"0{random.randint(100000000, 999999999)}",
            )
            co_session.add(emp)

    co_session.commit()

    # Task sheets for current period
    console.print("  Generating task sheets and performance scores...")
    period = date.today().strftime("%Y-%m")
    employees = co_session.query(Employee).all()

    for emp in employees:
        existing_sheet = co_session.query(TaskSheet).filter(
            TaskSheet.employee_id == emp.id,
            TaskSheet.period == period,
        ).first()
        if not existing_sheet:
            score = round(random.uniform(45, 98), 1)
            completion = round(random.uniform(50, 100), 1)
            sheet = TaskSheet(
                employee_id=emp.id,
                period=period,
                period_type="monthly",
                tasks=[
                    {"description": "Core responsibilities", "weight": 40, "status": "completed"},
                    {"description": "Project deliverables", "weight": 30, "status": "completed" if completion > 70 else "in_progress"},
                    {"description": "Team collaboration", "weight": 20, "status": "completed"},
                    {"description": "Reporting", "weight": 10, "status": "completed"},
                ],
                completion_pct=completion,
                performance_score=score,
                lead_feedback="Good work this period." if score > 70 else "Needs improvement in delivery.",
                bonus_eligible=score >= 85,
            )
            co_session.add(sheet)

    # Attendance records (last 14 days)
    console.print("  Adding attendance records...")
    for emp in employees:
        for days_ago in range(14):
            att_date = date.today() - timedelta(days=days_ago)
            if att_date.weekday() >= 5:  # Skip weekends
                continue
            existing_att = co_session.query(AttendanceRecord).filter(
                AttendanceRecord.employee_id == emp.id,
                AttendanceRecord.date == att_date,
            ).first()
            if not existing_att:
                is_present = random.random() > 0.15  # 85% attendance rate
                att = AttendanceRecord(
                    employee_id=emp.id,
                    date=att_date,
                    task_activity_score=random.uniform(50, 100) if is_present else 0,
                    comms_activity_score=random.uniform(40, 100) if is_present else 0,
                    meeting_score=random.uniform(60, 100) if is_present else 0,
                    presence_score=random.uniform(60, 100) if is_present else 0,
                    is_absent=not is_present,
                )
                co_session.add(att)

    co_session.commit()

    # Candidates
    console.print("  Adding recruitment candidates...")
    for cand_data in DEMO_CANDIDATES:
        existing_cand = co_session.query(Candidate).filter(
            Candidate.email == cand_data["email"]
        ).first()
        if not existing_cand:
            cand = Candidate(
                name=cand_data["name"],
                email=cand_data["email"],
                position_applied=cand_data["position"],
                education_score=round(random.uniform(60, 95), 1),
                skills_score=round(random.uniform(50, 95), 1),
                experience_score=round(random.uniform(55, 90), 1),
                keyword_score=round(random.uniform(40, 90), 1),
                total_score=cand_data["score"],
                shortlisted=cand_data["score"] >= 60,
                interview_status="pending" if cand_data["score"] >= 60 else "not_shortlisted",
            )
            co_session.add(cand)

    co_session.commit()
    co_session.close()

    console.print(f"  [green]✓[/] {len(DEMO_EMPLOYEES)} employees")
    console.print(f"  [green]✓[/] {len(DEMO_EMPLOYEES)} task sheets")
    console.print(f"  [green]✓[/] {len(DEMO_CANDIDATES)} candidates")
    console.print(f"  [green]✓[/] 14 days attendance records")
    console.print(f"\n[bold]Demo data ready! Launch dashboard:[/bold]")
    console.print(f"  streamlit run frontend/dashboard.py")


def main():
    parser = argparse.ArgumentParser(description="Seed demo data for GENZ HR")
    parser.add_argument("--company-id", default="demo_company", help="Company ID")
    parser.add_argument("--company-name", default="Demo Tech Ltd", help="Company name")
    args = parser.parse_args()
    seed(args.company_id, args.company_name)


if __name__ == "__main__":
    main()
