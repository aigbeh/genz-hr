#!/usr/bin/env python3
"""
GENZ HR — Onboard a new company.
Usage: python scripts/onboard_company.py --name "Acme Corp" --id "acme"
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.database import init_master_db, init_company_db, MasterSession, CompanyRegistry
from backend.core.config import get_company_dir, settings
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def onboard_company(
    company_id: str,
    name: str,
    industry: str = "Technology",
    size: str = "startup",
    contact_email: str = "",
):
    init_master_db()

    # Normalize ID
    company_id = company_id.lower().replace(" ", "_")

    # Check if already exists
    session = MasterSession()
    existing = session.query(CompanyRegistry).filter(CompanyRegistry.id == company_id).first()
    if existing:
        console.print(f"[red]✗[/] Company '{company_id}' already registered")
        session.close()
        return

    # Check limit
    active_count = session.query(CompanyRegistry).filter(CompanyRegistry.is_active == True).count()
    if active_count >= settings.MAX_COMPANIES:
        console.print(f"[red]✗[/] Maximum company limit ({settings.MAX_COMPANIES}) reached")
        session.close()
        return

    # Register company
    company = CompanyRegistry(
        id=company_id,
        name=name,
        industry=industry,
        size=size,
        contact_email=contact_email or settings.ESTHER_EMAIL,
    )
    session.add(company)
    session.commit()
    session.close()

    # Initialize isolated database
    init_company_db(company_id)

    # Create directory structure
    company_dir = get_company_dir(company_id)

    console.print(Panel.fit(
        f"[bold green]✓ Company Onboarded![/bold green]\n"
        f"ID: [cyan]{company_id}[/cyan]\n"
        f"Name: [cyan]{name}[/cyan]\n"
        f"GENZ Agent: [green]Ready[/green]",
        border_style="green",
    ))

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Path", style="cyan")
    table.add_row("Company Dir", str(company_dir))
    table.add_row("Database", str(company_dir / "hr_data.db"))
    table.add_row("Templates", str(company_dir / "templates"))
    table.add_row("Policies", str(company_dir / "policies"))
    table.add_row("Uploads", str(company_dir / "uploads"))
    console.print(table)

    console.print(f"\n[dim]GENZ Agent '{company_id}' is now monitoring {name}[/dim]")


def main():
    parser = argparse.ArgumentParser(description="Onboard a company to GENZ HR")
    parser.add_argument("--id", required=True, help="Company ID (e.g. 'acme')")
    parser.add_argument("--name", required=True, help="Company name (e.g. 'Acme Corp')")
    parser.add_argument("--industry", default="Technology", help="Industry")
    parser.add_argument("--size", default="startup", choices=["startup", "sme", "enterprise"])
    parser.add_argument("--email", default="", help="Company contact email")

    args = parser.parse_args()
    onboard_company(args.id, args.name, args.industry, args.size, args.email)


if __name__ == "__main__":
    main()
