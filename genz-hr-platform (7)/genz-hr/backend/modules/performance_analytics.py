"""
GENZ HR — Performance Analytics
Generates productivity heatmaps, trend analysis, and performance insights.
"""
from datetime import datetime, date, timedelta
from typing import Optional
import pandas as pd

from backend.core.database import get_company_session, TaskSheet, AttendanceRecord, Employee, EmploymentStatus


def get_productivity_heatmap(company_id: str, weeks: int = 12) -> dict:
    """
    Build a week-by-employee productivity matrix for heatmap rendering.
    
    Returns:
        {
            employees: ["Name 1", "Name 2", ...],
            weeks: ["2024-W01", ...],
            matrix: [[score, score, ...], ...],  # employees × weeks
        }
    """
    session = get_company_session(company_id)
    employees = session.query(Employee).filter(
        Employee.status == EmploymentStatus.active
    ).all()

    end_date = date.today()
    start_date = end_date - timedelta(weeks=weeks)

    emp_names = [f"{e.first_name} {e.last_name}" for e in employees]
    emp_ids = [e.id for e in employees]
    week_labels = []
    current = start_date
    while current <= end_date:
        week_labels.append(current.strftime("%Y-W%W"))
        current += timedelta(weeks=1)

    matrix = []
    for emp_id in emp_ids:
        row = []
        current = start_date
        while current <= end_date:
            week_end = current + timedelta(days=6)
            records = session.query(AttendanceRecord).filter(
                AttendanceRecord.employee_id == emp_id,
                AttendanceRecord.date >= current,
                AttendanceRecord.date <= week_end,
            ).all()

            if records:
                avg_score = sum(r.presence_score or 0 for r in records) / len(records)
            else:
                avg_score = 0.0
            row.append(round(avg_score, 1))
            current += timedelta(weeks=1)
        matrix.append(row)

    session.close()
    return {
        "employees": emp_names,
        "weeks": week_labels,
        "matrix": matrix,
    }


def get_performance_trends(company_id: str, periods: int = 6) -> dict:
    """
    Get performance score trends for the last N periods.
    
    Returns:
        {
            periods: ["2024-01", "2024-02", ...],
            avg_scores: [72.0, 75.5, ...],
            completion_rates: [68.0, 71.0, ...],
            top_performer: {...},
            most_improved: {...},
        }
    """
    session = get_company_session(company_id)

    today = date.today()
    period_list = []
    for i in range(periods - 1, -1, -1):
        month = today.month - i
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        period_list.append(f"{year}-{month:02d}")

    avg_scores = []
    completion_rates = []

    for period in period_list:
        sheets = session.query(TaskSheet).filter(TaskSheet.period == period).all()
        if sheets:
            scores = [s.performance_score for s in sheets if s.performance_score is not None]
            completions = [s.completion_pct for s in sheets if s.completion_pct is not None]
            avg_scores.append(round(sum(scores) / len(scores), 1) if scores else 0)
            completion_rates.append(round(sum(completions) / len(completions), 1) if completions else 0)
        else:
            avg_scores.append(0)
            completion_rates.append(0)

    # Top performer across all time
    all_sheets = session.query(TaskSheet).filter(
        TaskSheet.performance_score.isnot(None)
    ).order_by(TaskSheet.performance_score.desc()).first()

    top_performer = None
    if all_sheets:
        emp = session.query(Employee).filter(Employee.id == all_sheets.employee_id).first()
        if emp:
            top_performer = {
                "name": f"{emp.first_name} {emp.last_name}",
                "score": all_sheets.performance_score,
                "period": all_sheets.period,
            }

    session.close()
    return {
        "periods": period_list,
        "avg_scores": avg_scores,
        "completion_rates": completion_rates,
        "top_performer": top_performer,
    }


def get_underperformer_alerts(company_id: str, threshold: float = 50.0) -> list[dict]:
    """Return employees whose performance score is below threshold."""
    session = get_company_session(company_id)
    period = date.today().strftime("%Y-%m")

    sheets = session.query(TaskSheet).filter(
        TaskSheet.period == period,
        TaskSheet.performance_score.isnot(None),
        TaskSheet.performance_score < threshold,
    ).all()

    alerts = []
    for sheet in sheets:
        emp = session.query(Employee).filter(Employee.id == sheet.employee_id).first()
        if emp:
            alerts.append({
                "employee_id": emp.id,
                "name": f"{emp.first_name} {emp.last_name}",
                "department": emp.department,
                "position": emp.position,
                "score": sheet.performance_score,
                "completion_pct": sheet.completion_pct,
                "period": period,
                "severity": "high" if sheet.performance_score < 30 else "medium",
            })

    session.close()
    return sorted(alerts, key=lambda x: x["score"])


def get_top_performers(company_id: str, top_n: int = 5) -> list[dict]:
    """Return top performing employees for the current period."""
    session = get_company_session(company_id)
    period = date.today().strftime("%Y-%m")

    sheets = session.query(TaskSheet).filter(
        TaskSheet.period == period,
        TaskSheet.performance_score.isnot(None),
    ).order_by(TaskSheet.performance_score.desc()).limit(top_n).all()

    result = []
    for sheet in sheets:
        emp = session.query(Employee).filter(Employee.id == sheet.employee_id).first()
        if emp:
            result.append({
                "name": f"{emp.first_name} {emp.last_name}",
                "position": emp.position,
                "department": emp.department,
                "score": sheet.performance_score,
                "completion_pct": sheet.completion_pct,
                "bonus_eligible": sheet.bonus_eligible,
            })

    session.close()
    return result


def compute_department_averages(company_id: str) -> list[dict]:
    """Compute average performance scores by department."""
    session = get_company_session(company_id)
    period = date.today().strftime("%Y-%m")

    sheets = session.query(TaskSheet).filter(TaskSheet.period == period).all()
    dept_scores: dict[str, list] = {}

    for sheet in sheets:
        emp = session.query(Employee).filter(Employee.id == sheet.employee_id).first()
        if emp and emp.department and sheet.performance_score is not None:
            dept = emp.department
            if dept not in dept_scores:
                dept_scores[dept] = []
            dept_scores[dept].append(sheet.performance_score)

    session.close()
    return [
        {
            "department": dept,
            "avg_score": round(sum(scores) / len(scores), 1),
            "headcount": len(scores),
        }
        for dept, scores in dept_scores.items()
    ]
