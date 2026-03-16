#!/usr/bin/env python3
"""
GENZ HR — Initialize master database and create default structure.
Run once before starting the platform.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.database import init_master_db
from backend.core.config import settings, COMPANIES_DIR
from loguru import logger
from rich.console import Console
from rich.panel import Panel

console = Console()


def main():
    console.print(Panel.fit(
        "[bold green]GENZ HR[/bold green] — Initializing Platform",
        border_style="green",
    ))

    # Create companies directory
    COMPANIES_DIR.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]✓[/] Companies directory: {COMPANIES_DIR}")

    # Init master database
    init_master_db()
    console.print(f"[green]✓[/] Master database initialized")

    console.print(f"\n[bold]Platform Ready[/bold]")
    console.print(f"  Authority: [cyan]{settings.ESTHER_EMAIL}[/cyan]")
    console.print(f"  Max Companies: [cyan]{settings.MAX_COMPANIES}[/cyan]")
    console.print(f"  LLM Model: [cyan]{settings.OLLAMA_MODEL}[/cyan]")
    console.print(f"\nNext steps:")
    console.print("  1. python scripts/onboard_company.py --name 'Acme Corp' --id 'acme'")
    console.print("  2. streamlit run frontend/dashboard.py")
    console.print("  3. uvicorn backend.main:app --reload --port 8000")


if __name__ == "__main__":
    main()
