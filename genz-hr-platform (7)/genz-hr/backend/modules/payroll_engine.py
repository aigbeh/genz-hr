"""
GENZ HR — Nigerian Payroll Engine
Compliant with: Nigeria Tax Act 2025, PRA 2014, NHF Act
Effective: 1 January 2026

PAYE Brackets (annual) — Nigeria Tax Act 2025:
  ₦0           – ₦800,000      →  0%  (tax-free band)
  ₦800,001     – ₦3,000,000    → 15%
  ₦3,000,001   – ₦12,000,000   → 18%
  ₦12,000,001  – ₦25,000,000   → 21%
  ₦25,000,001  – ₦50,000,000   → 23%
  Above ₦50,000,000             → 25%

Key 2026 Changes:
  • Consolidated Relief Allowance (CRA) — REMOVED
  • First ₦800,000 is fully tax-free
  • New rent relief: 20% of annual rent, capped at ₦500,000/year
  • Tax is still progressive (each band only applies to income within it)

Pension (PRA 2014) — unchanged:
  Employee: 8% of gross
  Employer: 10% of gross

NHF: 2.5% of basic salary (if employee earns ≥ ₦3,000/month)
"""
from dataclasses import dataclass, field
from typing import Optional
import math


# ─── Nigeria Tax Act 2025 Brackets (effective 1 Jan 2026) ─────────────────────
# Format: (upper_bound, rate) — upper_bound is the ceiling of that band.
# The tax-free band (₦0–₦800,000) is handled by starting taxable income
# calculation from ₦800,000, so PAYE_BRACKETS only covers the taxable portion.

TAX_FREE_THRESHOLD = 800_000          # First ₦800,000 — 0%

PAYE_BRACKETS = [
    # (band_width, rate)  — applied progressively on income above TAX_FREE_THRESHOLD
    (2_200_000,  0.15),   # ₦800,001  – ₦3,000,000   → 15%
    (9_000_000,  0.18),   # ₦3,000,001 – ₦12,000,000  → 18%
    (13_000_000, 0.21),   # ₦12,000,001 – ₦25,000,000 → 21%
    (25_000_000, 0.23),   # ₦25,000,001 – ₦50,000,000 → 23%
    (float("inf"), 0.25), # Above ₦50,000,000          → 25%
]

PENSION_EMPLOYEE_RATE = 0.08
PENSION_EMPLOYER_RATE = 0.10
NHF_RATE              = 0.025
NHF_MINIMUM_MONTHLY   = 3_000

# Rent relief — Nigeria Tax Act 2025
RENT_RELIEF_RATE      = 0.20          # 20% of annual rent
RENT_RELIEF_MAX       = 500_000       # Capped at ₦500,000/year


@dataclass
class SalaryBreakdown:
    """Standard Nigerian salary breakdown."""
    gross_monthly: float
    basic_salary: float           # typically 60–70% of gross
    housing_allowance: float      # typically 20% of gross
    transport_allowance: float    # typically 10% of gross
    other_allowances: float = 0.0

    @classmethod
    def from_gross(cls, gross: float) -> "SalaryBreakdown":
        return cls(
            gross_monthly=gross,
            basic_salary=round(gross * 0.60, 2),
            housing_allowance=round(gross * 0.20, 2),
            transport_allowance=round(gross * 0.10, 2),
            other_allowances=round(gross * 0.10, 2),
        )


@dataclass
class PayrollResult:
    employee_id: str
    employee_name: str
    period: str
    gross_salary: float
    basic_salary: float
    housing_allowance: float
    transport_allowance: float
    other_allowances: float
    pension_employee: float
    pension_employer: float
    nhf_deduction: float
    taxable_income_annual: float
    paye_annual: float
    paye_monthly: float
    other_deductions: float
    performance_bonus: float
    total_deductions: float
    net_salary: float
    effective_tax_rate: float
    anomaly: bool = False
    anomaly_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "period": self.period,
            "gross_salary": self.gross_salary,
            "basic_salary": self.basic_salary,
            "housing_allowance": self.housing_allowance,
            "transport_allowance": self.transport_allowance,
            "other_allowances": self.other_allowances,
            "pension_employee": self.pension_employee,
            "pension_employer": self.pension_employer,
            "nhf_deduction": self.nhf_deduction,
            "paye_monthly": self.paye_monthly,
            "performance_bonus": self.performance_bonus,
            "total_deductions": self.total_deductions,
            "net_salary": self.net_salary,
            "effective_tax_rate_pct": round(self.effective_tax_rate * 100, 2),
            "anomaly": self.anomaly,
            "anomaly_reason": self.anomaly_reason,
        }


def calculate_paye_annual(gross_annual: float, rent_annual: float = 0.0) -> tuple[float, float]:
    """
    Compute annual PAYE tax under Nigeria Tax Act 2025 (effective 1 Jan 2026).

    Steps:
      1. Apply rent relief (20% of annual rent, capped at ₦500,000).
      2. Subtract rent relief from gross to get taxable income.
      3. Apply ₦800,000 tax-free threshold — income up to ₦800,000 is 0%.
      4. Apply progressive brackets on the remainder.

    Note: CRA (Consolidated Relief Allowance) was abolished under the 2025 Act.
    Pension and NHF deductions reduce gross BEFORE arriving here.

    Args:
        gross_annual: Annual gross income after pension & NHF deductions (₦)
        rent_annual:  Annual rent paid by employee (₦) — optional, for rent relief

    Returns:
        (paye_tax_annual, taxable_income_annual)
    """
    # ── Step 1: Rent relief ───────────────────────────────────────────────────
    rent_relief = min(rent_annual * RENT_RELIEF_RATE, RENT_RELIEF_MAX) if rent_annual > 0 else 0.0
    taxable_income = max(0.0, gross_annual - rent_relief)

    # ── Step 2: Tax-free threshold ────────────────────────────────────────────
    # Income up to ₦800,000 is fully exempt — tax starts on the excess only
    income_above_threshold = max(0.0, taxable_income - TAX_FREE_THRESHOLD)

    if income_above_threshold <= 0:
        return 0.0, taxable_income

    # ── Step 3: Progressive bands on income above ₦800,000 ───────────────────
    tax = 0.0
    remaining = income_above_threshold

    for band_width, rate in PAYE_BRACKETS:
        if remaining <= 0:
            break
        taxable_in_band = min(remaining, band_width)
        tax += taxable_in_band * rate
        remaining -= taxable_in_band

    return round(tax, 2), round(taxable_income, 2)


def get_paye_breakdown(gross_annual: float, rent_annual: float = 0.0) -> list[dict]:
    """
    Return a band-by-band PAYE breakdown for payslip transparency.
    Useful for showing Esther exactly how the tax was computed.
    """
    rent_relief = min(rent_annual * RENT_RELIEF_RATE, RENT_RELIEF_MAX) if rent_annual > 0 else 0.0
    taxable_income = max(0.0, gross_annual - rent_relief)
    income_above_threshold = max(0.0, taxable_income - TAX_FREE_THRESHOLD)

    breakdown = [
        {
            "band": f"₦0 – ₦{TAX_FREE_THRESHOLD:,.0f}",
            "rate": "0%",
            "taxable_amount": min(taxable_income, TAX_FREE_THRESHOLD),
            "tax": 0.0,
        }
    ]

    band_starts = [
        (800_001,    3_000_000,   0.15),
        (3_000_001,  12_000_000,  0.18),
        (12_000_001, 25_000_000,  0.21),
        (25_000_001, 50_000_000,  0.23),
        (50_000_001, float("inf"), 0.25),
    ]

    remaining = income_above_threshold
    for lower, upper, rate in band_starts:
        if remaining <= 0:
            break
        band_width = (upper - lower + 1) if upper != float("inf") else float("inf")
        amount_in_band = min(remaining, band_width)
        breakdown.append({
            "band": f"₦{lower:,.0f} – {'above ₦50M' if upper == float('inf') else '₦' + f'{upper:,.0f}'}",
            "rate": f"{rate*100:.0f}%",
            "taxable_amount": round(amount_in_band, 2),
            "tax": round(amount_in_band * rate, 2),
        })
        remaining -= amount_in_band

    return breakdown


def calculate_payroll(
    employee_id: str,
    employee_name: str,
    period: str,
    gross_monthly: float,
    performance_bonus: float = 0.0,
    other_deductions: float = 0.0,
    annual_rent: float = 0.0,
    breakdown: Optional[SalaryBreakdown] = None,
) -> PayrollResult:
    """
    Calculate full Nigerian payroll for one employee.
    Compliant with Nigeria Tax Act 2025 (effective 1 Jan 2026).

    Key changes vs prior law:
      - CRA abolished: no ₦200,000 + 20% relief deduction
      - ₦800,000 annual tax-free threshold (replaces old first-bracket structure)
      - Rent relief: 20% of annual rent, max ₦500,000/year (new)
      - Higher bracket ceiling before hitting top rates

    Args:
        employee_id:       Employee identifier
        employee_name:     Full name for payslip
        period:            Pay period string e.g. "2026-03"
        gross_monthly:     Monthly gross salary (₦)
        performance_bonus: One-time bonus this period (₦)
        other_deductions:  Loans, advances, etc. (₦)
        annual_rent:       Employee's annual rent (₦) for rent relief calculation
        breakdown:         Optional custom salary structure

    Returns:
        PayrollResult with full statutory computations
    """
    if breakdown is None:
        breakdown = SalaryBreakdown.from_gross(gross_monthly)

    gross_annual = gross_monthly * 12

    # ── Pension (PRA 2014 — unchanged) ───────────────────────────────────────
    pension_employee_monthly = round(gross_monthly * PENSION_EMPLOYEE_RATE, 2)
    pension_employer_monthly = round(gross_monthly * PENSION_EMPLOYER_RATE, 2)

    # ── NHF (unchanged) ──────────────────────────────────────────────────────
    nhf_monthly = 0.0
    if gross_monthly >= NHF_MINIMUM_MONTHLY:
        nhf_monthly = round(breakdown.basic_salary * NHF_RATE, 2)

    # ── Taxable Income (2026 method: no CRA) ─────────────────────────────────
    # Pension and NHF are still pre-tax deductions under the 2025 Act
    pension_annual = pension_employee_monthly * 12
    nhf_annual     = nhf_monthly * 12
    gross_after_statutory = gross_annual - pension_annual - nhf_annual

    # ── PAYE (Nigeria Tax Act 2025) ───────────────────────────────────────────
    paye_annual, taxable_income = calculate_paye_annual(
        gross_annual=gross_after_statutory,
        rent_annual=annual_rent,
    )
    paye_monthly = round(paye_annual / 12, 2)

    # ── Net Salary ────────────────────────────────────────────────────────────
    total_deductions = (
        pension_employee_monthly
        + nhf_monthly
        + paye_monthly
        + other_deductions
    )
    net_salary = round(gross_monthly - total_deductions + performance_bonus, 2)

    # ── Effective Tax Rate (PAYE ÷ gross) ────────────────────────────────────
    effective_rate = paye_monthly / gross_monthly if gross_monthly > 0 else 0.0

    # ── Anomaly Detection ─────────────────────────────────────────────────────
    anomaly = False
    anomaly_reasons = []

    # Nigeria minimum wage is ₦70,000/month as of 2024 (may be updated)
    if net_salary < 70_000:
        anomaly = True
        anomaly_reasons.append("Net salary below ₦70,000 — check minimum wage compliance")

    # Under 2026 rules, PAYE on moderate salaries is low; >30% is suspicious
    if paye_monthly > 0 and paye_monthly > gross_monthly * 0.30:
        anomaly = True
        anomaly_reasons.append("PAYE exceeds 30% of gross — verify tax computation")

    if performance_bonus > gross_monthly * 0.5:
        anomaly = True
        anomaly_reasons.append("Bonus exceeds 50% of monthly gross — requires Esther approval")

    if net_salary <= 0:
        anomaly = True
        anomaly_reasons.append("CRITICAL: Net salary is zero or negative")

    # Flag employees who might benefit from rent relief but haven't claimed it
    if annual_rent == 0 and gross_monthly > 200_000 and paye_annual > 0:
        anomaly_reasons.append(
            "Tip: Employee may be eligible for rent relief — ask for annual rent amount"
        )
        # Note: this is informational, not flagged as a hard anomaly

    return PayrollResult(
        employee_id=employee_id,
        employee_name=employee_name,
        period=period,
        gross_salary=gross_monthly,
        basic_salary=breakdown.basic_salary,
        housing_allowance=breakdown.housing_allowance,
        transport_allowance=breakdown.transport_allowance,
        other_allowances=breakdown.other_allowances,
        pension_employee=pension_employee_monthly,
        pension_employer=pension_employer_monthly,
        nhf_deduction=nhf_monthly,
        taxable_income_annual=taxable_income,
        paye_annual=paye_annual,
        paye_monthly=paye_monthly,
        other_deductions=other_deductions,
        performance_bonus=performance_bonus,
        total_deductions=total_deductions,
        net_salary=net_salary,
        effective_tax_rate=effective_rate,
        anomaly=anomaly,
        anomaly_reason="; ".join(anomaly_reasons),
    )


def calculate_company_payroll(employees: list[dict], period: str) -> dict:
    """
    Compute payroll for all employees in a company.
    Compliant with Nigeria Tax Act 2025 (effective 1 Jan 2026).

    Args:
        employees: List of employee dicts:
                   id, name, gross_salary, bonus, other_deductions, annual_rent
        period: Pay period string e.g. "2026-03"

    Returns:
        {results: [...], summary: {...}, anomalies: [...]}
    """
    results = []
    anomalies = []
    total_gross           = 0.0
    total_net             = 0.0
    total_paye            = 0.0
    total_pension_employer = 0.0

    for emp in employees:
        result = calculate_payroll(
            employee_id=str(emp.get("id", "")),
            employee_name=emp.get("name", "Unknown"),
            period=period,
            gross_monthly=float(emp.get("gross_salary", 0)),
            performance_bonus=float(emp.get("bonus", 0)),
            other_deductions=float(emp.get("other_deductions", 0)),
            annual_rent=float(emp.get("annual_rent", 0)),
        )
        results.append(result.to_dict())
        total_gross           += result.gross_salary
        total_net             += result.net_salary
        total_paye            += result.paye_monthly
        total_pension_employer += result.pension_employer

        if result.anomaly:
            anomalies.append({
                "employee": result.employee_name,
                "reason": result.anomaly_reason,
            })

    return {
        "period": period,
        "tax_law": "Nigeria Tax Act 2025 (effective 1 Jan 2026)",
        "results": results,
        "summary": {
            "headcount": len(results),
            "total_gross": round(total_gross, 2),
            "total_net": round(total_net, 2),
            "total_paye": round(total_paye, 2),
            "total_pension_employer": round(total_pension_employer, 2),
            "total_payroll_cost": round(total_gross + total_pension_employer, 2),
        },
        "anomalies": anomalies,
        "requires_esther_approval": True,  # Always require Esther sign-off
    }


# ─── CLI Demo ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()

    console.print(Panel.fit(
        "[bold green]GENZ HR — Nigeria Tax Act 2025 Payroll Engine[/bold green]\n"
        "[dim]Effective 1 January 2026 · CRA removed · ₦800,000 tax-free threshold[/dim]",
        border_style="green",
    ))

    # ── Law Verification: the example from the brief ──────────────────────────
    # Annual taxable income = ₦2,000,000
    # Expected: ₦800k → 0%, ₦1.2M × 15% = ₦180,000 tax
    verify_gross_annual = 2_000_000
    verify_paye, verify_taxable = calculate_paye_annual(verify_gross_annual)
    console.print(f"\n[bold yellow]Law Verification — ₦2,000,000 annual income:[/bold yellow]")
    console.print(f"  Tax-free (₦0–₦800,000):     ₦0")
    console.print(f"  15% on ₦1,200,000:           ₦{1_200_000 * 0.15:,.0f}")
    console.print(f"  GENZ computed PAYE:           ₦{verify_paye:,.0f}")
    status = "[green]✓ CORRECT[/green]" if verify_paye == 180_000 else "[red]✗ MISMATCH[/red]"
    console.print(f"  Expected ₦180,000: {status}\n")

    # ── Full payroll demo ─────────────────────────────────────────────────────
    test_employees = [
        {"id": "EMP-001", "name": "Chidi Okonkwo",  "gross_salary":   450_000, "bonus":       0, "annual_rent":       0},
        {"id": "EMP-002", "name": "Amara Nwosu",    "gross_salary":   850_000, "bonus":  50_000, "annual_rent": 600_000},
        {"id": "EMP-003", "name": "Tunde Adeyemi",  "gross_salary":   200_000, "bonus":       0, "annual_rent":       0},
        {"id": "EMP-004", "name": "Ngozi Eze",      "gross_salary": 1_500_000, "bonus": 100_000, "annual_rent": 900_000},
        {"id": "EMP-005", "name": "Emeka Obi",      "gross_salary":   350_000, "bonus":  20_000, "annual_rent": 360_000},
        {"id": "EMP-006", "name": "Fatima Aliyu",   "gross_salary": 3_000_000, "bonus": 200_000, "annual_rent": 1_500_000},
    ]

    payroll = calculate_company_payroll(test_employees, "2026-03")

    table = Table(
        title="GENZ HR — March 2026 Payroll (Nigeria Tax Act 2025)",
        show_lines=True, show_header=True,
    )
    table.add_column("Employee",   style="cyan",        no_wrap=True)
    table.add_column("Gross (₦)",  justify="right",     style="green")
    table.add_column("PAYE (₦)",   justify="right",     style="yellow")
    table.add_column("Pension (₦)",justify="right")
    table.add_column("NHF (₦)",    justify="right")
    table.add_column("Bonus (₦)",  justify="right",     style="blue")
    table.add_column("Net (₦)",    justify="right",     style="bold green")
    table.add_column("Tax Rate",   justify="right",     style="dim")
    table.add_column("Status",     style="red")

    for r in payroll["results"]:
        table.add_row(
            r["employee_name"],
            f"{r['gross_salary']:,.0f}",
            f"{r['paye_monthly']:,.0f}",
            f"{r['pension_employee']:,.0f}",
            f"{r['nhf_deduction']:,.0f}",
            f"{r['performance_bonus']:,.0f}",
            f"{r['net_salary']:,.0f}",
            f"{r['effective_tax_rate_pct']:.1f}%",
            "⚠ " + r["anomaly_reason"][:35] if r["anomaly"] else "✓",
        )

    console.print(table)

    s = payroll["summary"]
    console.print(f"\n[bold]Total Gross:[/]      ₦{s['total_gross']:,.0f}")
    console.print(f"[bold]Total PAYE:[/]       ₦{s['total_paye']:,.0f}")
    console.print(f"[bold]Total Net:[/]        ₦{s['total_net']:,.0f}")
    console.print(f"[bold]Total Payroll Cost (inc. employer pension):[/] ₦{s['total_payroll_cost']:,.0f}")

    # ── Band breakdown for highest earner ────────────────────────────────────
    console.print("\n[bold yellow]PAYE Band Breakdown — Fatima Aliyu (₦3,000,000/month):[/bold yellow]")
    gross_annual_fatima = 3_000_000 * 12
    pension_annual_fatima = gross_annual_fatima * PENSION_EMPLOYEE_RATE
    nhf_annual_fatima = SalaryBreakdown.from_gross(3_000_000).basic_salary * NHF_RATE * 12
    after_statutory = gross_annual_fatima - pension_annual_fatima - nhf_annual_fatima
    bands = get_paye_breakdown(after_statutory, rent_annual=1_500_000)
    for band in bands:
        console.print(
            f"  {band['band']:40s}  {band['rate']:4s}  "
            f"on ₦{band['taxable_amount']:>14,.0f}  →  ₦{band['tax']:>12,.0f}"
        )

    if payroll["anomalies"]:
        console.print("\n[red bold]⚠  Anomalies — Esther must review:[/red bold]")
        for a in payroll["anomalies"]:
            console.print(f"  • {a['employee']}: {a['reason']}")
