"""
GENZ HR — GENZ Director
Central AI that supervises all company GENZ Agents,
aggregates insights, detects cross-company patterns,
and sends daily summaries to Esther.

The Director NEVER reads employee-level data from any company.
It only reads agent-generated summary reports.
"""
import json
from datetime import datetime, date
from typing import Dict, Optional
import logging
logger = logging.getLogger("genz.director")

from backend.core.database import CompanyRegistry, MasterSession
from backend.core.config import settings
from backend.agents.genz_agent import GENZAgent


class GENZDirector:
    """
    Central GENZ Director Agent.
    
    Responsibilities:
    - Spawn and manage per-company GENZ Agents
    - Aggregate daily reports from all companies
    - Detect platform-level anomalies
    - Compile and route summaries to Esther
    - Never access raw employee data (isolation guarantee)
    """

    def __init__(self, llm_client=None):
        self.llm = llm_client
        self._agents: Dict[str, GENZAgent] = {}
        logger.info("GENZ Director initialized")

    def get_agent(self, company_id: str) -> Optional[GENZAgent]:
        """Get or create a GENZ Agent for a company."""
        if company_id not in self._agents:
            session = MasterSession()
            company = session.query(CompanyRegistry).filter(
                CompanyRegistry.id == company_id,
                CompanyRegistry.is_active == True,
            ).first()
            session.close()

            if not company:
                logger.warning(f"Company not found or inactive: {company_id}")
                return None

            self._agents[company_id] = GENZAgent(
                company_id=company.id,
                company_name=company.name,
                llm_client=self.llm,
            )

        return self._agents[company_id]

    def get_all_active_companies(self) -> list:
        """Return all active companies from master registry."""
        session = MasterSession()
        companies = session.query(CompanyRegistry).filter(
            CompanyRegistry.is_active == True
        ).all()
        session.close()
        return companies

    def run_daily_cycle(self) -> dict:
        """
        Execute the daily HR cycle for ALL companies.
        Each agent runs independently. Results are aggregated here.
        """
        logger.info("GENZ Director: Starting daily cycle")
        companies = self.get_all_active_companies()
        
        all_reports = []
        total_alerts = []
        companies_needing_attention = []

        for company in companies:
            try:
                agent = self.get_agent(company.id)
                if not agent:
                    continue

                report = agent.generate_daily_report()
                all_reports.append(report)

                if report["alerts"]:
                    companies_needing_attention.append({
                        "company": company.name,
                        "alerts": report["alerts"],
                    })
                    total_alerts.extend(report["alerts"])

                logger.info(f"✓ {company.name} report complete")

            except Exception as e:
                logger.error(f"Error running agent for {company.name}: {e}")
                all_reports.append({
                    "company_id": company.id,
                    "company_name": company.name,
                    "error": str(e),
                })

        summary = self._compile_director_summary(all_reports, total_alerts, companies_needing_attention)

        # Include platform-wide pending approval counts
        from backend.core.approval_gate import get_platform_pending_counts
        summary["pending_approvals"] = get_platform_pending_counts()
        summary["total_pending_approvals"] = sum(summary["pending_approvals"].values())
        
        # Update last summary time
        session = MasterSession()
        for company in companies:
            reg = session.query(CompanyRegistry).filter(CompanyRegistry.id == company.id).first()
            if reg:
                reg.last_summary_at = datetime.utcnow()
        session.commit()
        session.close()

        return summary

    def _compile_director_summary(
        self, reports: list, alerts: list, attention_needed: list
    ) -> dict:
        """Compile all agent reports into a Director-level summary."""
        today = date.today().strftime("%d %B %Y")
        
        total_companies = len(reports)
        companies_with_issues = len(attention_needed)
        total_shortlisted = sum(
            r.get("recruitment", {}).get("shortlisted", 0) for r in reports
        )
        total_attendance_issues = sum(
            r.get("attendance", {}).get("issues_count", 0) for r in reports
        )
        payroll_due = [
            r["company_name"] for r in reports
            if r.get("payroll", {}).get("due_soon")
        ]

        # Collect total pending approvals across all companies
        total_pending_approvals = sum(
            r.get("pending_approvals", 0) for r in reports
        )

        return {
            "generated_at": datetime.utcnow().isoformat(),
            "report_date": today,
            "director": "GENZ Director",
            "recipient": settings.ESTHER_EMAIL,
            "platform_summary": {
                "total_companies_monitored": total_companies,
                "companies_with_alerts": companies_with_issues,
                "total_alerts": len(alerts),
                "total_shortlisted_candidates": total_shortlisted,
                "total_attendance_issues": total_attendance_issues,
                "payroll_due_companies": payroll_due,
                "total_pending_approvals": total_pending_approvals,
            },
            "company_reports": reports,
            "attention_needed": attention_needed,
            "formatted_summary": self._format_esther_summary(
                today, reports, attention_needed, payroll_due
            ),
        }

    def _format_esther_summary(
        self, today: str, reports: list, attention_needed: list, payroll_due: list
    ) -> str:
        """Generate a human-readable summary for Esther."""
        lines = [
            f"# 📋 GENZ HR — Daily Summary",
            f"**Date:** {today}",
            f"**To:** Esther",
            f"**Companies Monitored:** {len(reports)}",
            "",
        ]

        for report in reports:
            if "error" in report:
                lines.append(f"## ❌ {report['company_name']} — Agent Error")
                lines.append(f"> {report['error']}")
                continue

            company = report["company_name"]
            alerts = report.get("alerts", [])
            rec = report.get("recruitment", {})
            att = report.get("attendance", {})
            pay = report.get("payroll", {})

            status_icon = "🚨" if alerts else "✅"
            lines.append(f"## {status_icon} {company}")

            if rec.get("shortlisted", 0) > 0:
                lines.append(f"- 👥 {rec['shortlisted']} candidates shortlisted")
            if rec.get("pending_interviews", 0) > 0:
                lines.append(f"- 📅 {rec['pending_interviews']} interviews pending")
            if att.get("issues_count", 0) > 0:
                lines.append(f"- ⚠️ {att['issues_count']} attendance issues detected")
            if pay.get("due_soon"):
                lines.append(f"- 💰 Payroll for {pay['period']} ready for your approval")

            for alert in alerts:
                lines.append(f"- 🔴 {alert}")

            lines.append("")

        if payroll_due:
            lines.append("## 💳 Payroll Approvals Required")
            for company in payroll_due:
                lines.append(f"- {company}: Payroll needs review")
            lines.append("")

        lines.append("---")
        lines.append("_Generated by GENZ Director. All actions pending your approval._")
        lines.append(f"_Login at: http://localhost:8501_")

        return "\n".join(lines)

    def register_company(
        self, company_id: str, name: str, industry: str = "", size: str = "startup", contact_email: str = ""
    ) -> CompanyRegistry:
        """Register a new company in the master registry."""
        session = MasterSession()
        
        existing = session.query(CompanyRegistry).filter(CompanyRegistry.id == company_id).first()
        if existing:
            session.close()
            raise ValueError(f"Company '{company_id}' already registered")

        active_count = session.query(CompanyRegistry).filter(CompanyRegistry.is_active == True).count()
        if active_count >= settings.MAX_COMPANIES:
            session.close()
            raise ValueError(f"Maximum company limit ({settings.MAX_COMPANIES}) reached")

        company = CompanyRegistry(
            id=company_id,
            name=name,
            industry=industry,
            size=size,
            contact_email=contact_email,
        )
        session.add(company)
        session.commit()
        session.refresh(company)
        session.close()

        # Initialize company DB
        from backend.core.database import init_company_db
        init_company_db(company_id)

        logger.info(f"Company registered: {name} ({company_id})")
        return company

    def get_platform_stats(self) -> dict:
        """Dashboard stats across all companies (no PII)."""
        session = MasterSession()
        companies = session.query(CompanyRegistry).all()
        active = [c for c in companies if c.is_active]
        session.close()

        return {
            "total_companies": len(companies),
            "active_companies": len(active),
            "available_slots": settings.MAX_COMPANIES - len(active),
            "companies": [
                {
                    "id": c.id,
                    "name": c.name,
                    "industry": c.industry,
                    "size": c.size,
                    "agent_status": c.agent_status,
                    "last_summary": c.last_summary_at.isoformat() if c.last_summary_at else None,
                }
                for c in active
            ],
        }

    def shutdown(self):
        """Clean up all agent sessions."""
        for company_id, agent in self._agents.items():
            try:
                agent.close()
            except Exception:
                pass
        self._agents.clear()
        logger.info("GENZ Director: All agents shut down")


# Singleton Director instance
director = GENZDirector()
