"""
GENZ HR — PDF Generator
Produces professional payslips, offer letters, and HR reports.
Uses ReportLab for local, offline PDF generation.
"""
from pathlib import Path
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from backend.core.config import get_company_dir


# ─── Brand Colors ─────────────────────────────────────────────────────────────

GENZ_PURPLE = colors.HexColor("#7c3aed")
GENZ_TEAL   = colors.HexColor("#06b6d4")
DARK_BG     = colors.HexColor("#1e1b4b")
LIGHT_GRAY  = colors.HexColor("#f8fafc")
MID_GRAY    = colors.HexColor("#64748b")
SUCCESS     = colors.HexColor("#10b981")
WARNING     = colors.HexColor("#f59e0b")
DANGER      = colors.HexColor("#ef4444")


def _base_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "GenzTitle",
        fontSize=22, fontName="Helvetica-Bold",
        textColor=DARK_BG, alignment=TA_CENTER, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "GenzSubtitle",
        fontSize=11, fontName="Helvetica",
        textColor=MID_GRAY, alignment=TA_CENTER, spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        "SectionHeader",
        fontSize=10, fontName="Helvetica-Bold",
        textColor=GENZ_PURPLE, spaceBefore=10, spaceAfter=4,
        borderPadding=(0, 0, 2, 0),
    ))
    styles.add(ParagraphStyle(
        "BodyText2",
        fontSize=9, fontName="Helvetica",
        textColor=colors.HexColor("#334155"),
        spaceAfter=3, leading=13,
    ))
    styles.add(ParagraphStyle(
        "NetSalary",
        fontSize=16, fontName="Helvetica-Bold",
        textColor=SUCCESS, alignment=TA_CENTER,
    ))
    return styles


def _table_style(header_color=None):
    header_color = header_color or GENZ_PURPLE
    return TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  header_color),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0),  9),
        ("ALIGN",        (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN",        (0, 0), (0, -1),  "LEFT"),
        ("FONTSIZE",     (0, 1), (-1, -1), 9),
        ("BACKGROUND",   (0, 1), (-1, -1), LIGHT_GRAY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT_GRAY, colors.white]),
        ("GRID",         (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ])


def generate_payslip(
    payroll_data: dict,
    company_name: str,
    company_id: str,
    output_path: Optional[str] = None,
) -> str:
    """
    Generate a single employee payslip as PDF.
    
    Args:
        payroll_data: dict with all payroll fields
        company_name: Company name for header
        company_id: For file path isolation
        output_path: Optional override path
    
    Returns:
        Path to generated PDF
    """
    styles = _base_styles()

    if output_path is None:
        report_dir = get_company_dir(company_id) / "reports"
        report_dir.mkdir(exist_ok=True)
        emp_id = payroll_data.get("employee_id", "emp").replace("/", "-")
        period = payroll_data.get("period", "period")
        output_path = str(report_dir / f"payslip_{emp_id}_{period}.pdf")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=15*mm, bottomMargin=15*mm,
        leftMargin=20*mm, rightMargin=20*mm,
    )

    story = []

    # ── Header ───────────────────────────────────────────────────────────────

    story.append(Paragraph("GENZ HR", styles["GenzTitle"]))
    story.append(Paragraph(company_name, styles["GenzSubtitle"]))
    story.append(HRFlowable(width="100%", thickness=2, color=GENZ_PURPLE, spaceAfter=6))
    story.append(Paragraph(
        f"PAYSLIP — {payroll_data.get('period', '')}",
        ParagraphStyle("PayslipTitle", fontSize=13, fontName="Helvetica-Bold",
                       textColor=DARK_BG, alignment=TA_CENTER, spaceAfter=8)
    ))

    # ── Employee Info ─────────────────────────────────────────────────────────

    story.append(Paragraph("EMPLOYEE DETAILS", styles["SectionHeader"]))

    emp_table_data = [
        ["Employee Name", payroll_data.get("employee_name", "—"),
         "Employee ID", payroll_data.get("employee_id", "—")],
        ["Position", payroll_data.get("position", "—"),
         "Department", payroll_data.get("department", "—")],
        ["Bank", payroll_data.get("bank_name", "—"),
         "Account", payroll_data.get("account_number", "—")],
        ["Pay Period", payroll_data.get("period", "—"),
         "Pay Date", datetime.now().strftime("%d %B %Y")],
    ]

    emp_table = Table(emp_table_data, colWidths=[40*mm, 60*mm, 35*mm, 55*mm])
    emp_table.setStyle(TableStyle([
        ("FONTNAME",     (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME",     (0, 0), (0, -1),  "Helvetica-Bold"),
        ("FONTNAME",     (2, 0), (2, -1),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("TEXTCOLOR",    (0, 0), (0, -1),  MID_GRAY),
        ("TEXTCOLOR",    (2, 0), (2, -1),  MID_GRAY),
        ("BACKGROUND",   (0, 0), (-1, -1), LIGHT_GRAY),
        ("GRID",         (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    story.append(emp_table)
    story.append(Spacer(1, 8))

    # ── Earnings & Deductions ─────────────────────────────────────────────────

    col1_w, col2_w = 110*mm, 60*mm

    story.append(Paragraph("EARNINGS", styles["SectionHeader"]))
    earnings_data = [
        ["Description", "Amount (₦)"],
        ["Basic Salary",         f"{payroll_data.get('basic_salary', 0):,.2f}"],
        ["Housing Allowance",    f"{payroll_data.get('housing_allowance', 0):,.2f}"],
        ["Transport Allowance",  f"{payroll_data.get('transport_allowance', 0):,.2f}"],
        ["Other Allowances",     f"{payroll_data.get('other_allowances', 0):,.2f}"],
        ["Performance Bonus",    f"{payroll_data.get('performance_bonus', 0):,.2f}"],
    ]
    if payroll_data.get("performance_bonus", 0) == 0:
        earnings_data.pop()  # Don't show zero bonus line

    gross = payroll_data.get("gross_salary", 0)
    bonus = payroll_data.get("performance_bonus", 0)
    earnings_data.append(["GROSS SALARY", f"{gross + bonus:,.2f}"])

    earnings_table = Table(earnings_data, colWidths=[col1_w, col2_w])
    earnings_table.setStyle(_table_style(GENZ_TEAL))
    # Bold totals row
    earnings_table.setStyle(TableStyle([
        ("FONTNAME",   (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e0f2fe")),
        ("TEXTCOLOR",  (0, -1), (-1, -1), colors.HexColor("#0369a1")),
    ]))
    story.append(earnings_table)
    story.append(Spacer(1, 6))

    story.append(Paragraph("STATUTORY DEDUCTIONS", styles["SectionHeader"]))
    deductions_data = [
        ["Description", "Amount (₦)"],
        ["PAYE Income Tax (Finance Act 2020)", f"{payroll_data.get('paye_monthly', 0):,.2f}"],
        ["Pension Contribution (8% — PRA 2014)", f"{payroll_data.get('pension_employee', 0):,.2f}"],
        ["NHF Contribution (2.5% — NHF Act)",   f"{payroll_data.get('nhf_deduction', 0):,.2f}"],
    ]
    if payroll_data.get("other_deductions", 0) > 0:
        deductions_data.append(["Other Deductions", f"{payroll_data.get('other_deductions', 0):,.2f}"])

    total_ded = (
        payroll_data.get("paye_monthly", 0)
        + payroll_data.get("pension_employee", 0)
        + payroll_data.get("nhf_deduction", 0)
        + payroll_data.get("other_deductions", 0)
    )
    deductions_data.append(["TOTAL DEDUCTIONS", f"{total_ded:,.2f}"])

    ded_table = Table(deductions_data, colWidths=[col1_w, col2_w])
    ded_table.setStyle(_table_style(colors.HexColor("#7f1d1d")))
    ded_table.setStyle(TableStyle([
        ("FONTNAME",   (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fee2e2")),
        ("TEXTCOLOR",  (0, -1), (-1, -1), colors.HexColor("#991b1b")),
    ]))
    story.append(ded_table)
    story.append(Spacer(1, 12))

    # ── Net Salary ────────────────────────────────────────────────────────────

    net = payroll_data.get("net_salary", 0)
    net_table = Table(
        [["NET SALARY", f"₦{net:,.2f}"]],
        colWidths=[col1_w, col2_w]
    )
    net_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), DARK_BG),
        ("TEXTCOLOR",    (0, 0), (-1, -1), colors.white),
        ("FONTNAME",     (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 13),
        ("ALIGN",        (1, 0), (1, 0),   "RIGHT"),
        ("TOPPADDING",   (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 10),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(KeepTogether(net_table))
    story.append(Spacer(1, 12))

    # ── Anomaly Warning ───────────────────────────────────────────────────────

    if payroll_data.get("anomaly"):
        story.append(HRFlowable(width="100%", thickness=1, color=DANGER, spaceAfter=4))
        story.append(Paragraph(
            f"⚠ ANOMALY FLAGGED: {payroll_data.get('anomaly_reason', '')}",
            ParagraphStyle("Warning", fontSize=9, textColor=DANGER,
                           fontName="Helvetica-Bold", spaceAfter=8)
        ))

    # ── Employer Contribution ─────────────────────────────────────────────────

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    story.append(Paragraph(
        f"Employer Pension (10%): ₦{payroll_data.get('pension_employer', 0):,.2f}   |   "
        f"Effective Tax Rate: {payroll_data.get('effective_tax_rate_pct', 0):.1f}%",
        ParagraphStyle("Footer2", fontSize=8, textColor=MID_GRAY,
                       alignment=TA_CENTER, spaceBefore=4)
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "This payslip is computer-generated by GENZ HR · Approved by Esther · Confidential",
        ParagraphStyle("Footer", fontSize=7, textColor=MID_GRAY,
                       alignment=TA_CENTER)
    ))

    doc.build(story)
    return output_path


def generate_payroll_summary_pdf(
    payroll_result: dict,
    company_name: str,
    company_id: str,
) -> str:
    """Generate a company-wide payroll summary PDF."""
    styles = _base_styles()
    period = payroll_result.get("period", "")

    report_dir = get_company_dir(company_id) / "reports"
    report_dir.mkdir(exist_ok=True)
    output_path = str(report_dir / f"payroll_summary_{period}.pdf")

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=15*mm, bottomMargin=15*mm,
        leftMargin=20*mm, rightMargin=20*mm,
    )

    story = []
    story.append(Paragraph("GENZ HR", styles["GenzTitle"]))
    story.append(Paragraph(company_name, styles["GenzSubtitle"]))
    story.append(HRFlowable(width="100%", thickness=2, color=GENZ_PURPLE, spaceAfter=6))
    story.append(Paragraph(
        f"PAYROLL SUMMARY — {period}",
        ParagraphStyle("H", fontSize=13, fontName="Helvetica-Bold",
                       textColor=DARK_BG, alignment=TA_CENTER, spaceAfter=8)
    ))

    # Summary metrics
    s = payroll_result.get("summary", {})
    summary_data = [
        ["Metric", "Value"],
        ["Headcount", str(s.get("headcount", 0))],
        ["Total Gross Payroll", f"₦{s.get('total_gross', 0):,.2f}"],
        ["Total Net Payroll", f"₦{s.get('total_net', 0):,.2f}"],
        ["Total PAYE Remittance", f"₦{s.get('total_paye', 0):,.2f}"],
        ["Total Employer Pension", f"₦{s.get('total_pension_employer', 0):,.2f}"],
        ["Total Payroll Cost", f"₦{s.get('total_payroll_cost', 0):,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[100*mm, 70*mm])
    summary_table.setStyle(_table_style())
    story.append(summary_table)
    story.append(Spacer(1, 12))

    # Employee breakdown
    story.append(Paragraph("EMPLOYEE BREAKDOWN", styles["SectionHeader"]))
    emp_data = [["Employee", "Gross (₦)", "PAYE (₦)", "Pension (₦)", "Net (₦)", "Status"]]
    for r in payroll_result.get("results", []):
        emp_data.append([
            r.get("employee_name", "—"),
            f"{r.get('gross_salary', 0):,.0f}",
            f"{r.get('paye_monthly', 0):,.0f}",
            f"{r.get('pension_employee', 0):,.0f}",
            f"{r.get('net_salary', 0):,.0f}",
            "⚠" if r.get("anomaly") else "✓",
        ])
    emp_table = Table(emp_data, colWidths=[50*mm, 28*mm, 24*mm, 24*mm, 28*mm, 16*mm])
    emp_table.setStyle(_table_style())
    story.append(emp_table)

    # Anomalies
    anomalies = payroll_result.get("anomalies", [])
    if anomalies:
        story.append(Spacer(1, 10))
        story.append(Paragraph("ANOMALIES REQUIRING ESTHER'S REVIEW", styles["SectionHeader"]))
        for a in anomalies:
            story.append(Paragraph(
                f"• {a.get('employee', '—')}: {a.get('reason', '—')}",
                ParagraphStyle("Warn", fontSize=9, textColor=DANGER, spaceAfter=3)
            ))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"Generated by GENZ HR on {datetime.now().strftime('%d %B %Y %H:%M')} · "
        f"Requires approval from Esther before disbursement",
        ParagraphStyle("Footer", fontSize=7, textColor=MID_GRAY, alignment=TA_CENTER)
    ))

    doc.build(story)
    return output_path
