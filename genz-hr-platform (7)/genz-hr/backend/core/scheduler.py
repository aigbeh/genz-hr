"""
GENZ HR — Background Scheduler
Runs GENZ Agent cycles automatically on schedule.
Esther receives daily summaries at 8 AM.
Payroll check runs on the 25th of each month.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from loguru import logger

from backend.core.config import settings


def run_daily_director_cycle():
    """Run the GENZ Director daily cycle."""
    from backend.agents.genz_director import director
    logger.info("Scheduler: Running daily GENZ Director cycle")
    try:
        summary = director.run_daily_cycle()
        companies_with_alerts = summary.get("platform_summary", {}).get("companies_with_alerts", 0)
        logger.info(f"Daily cycle complete — {companies_with_alerts} companies need attention")

        # Send email if alerts exist
        if companies_with_alerts > 0:
            _send_daily_email(summary)

    except Exception as e:
        logger.error(f"Daily cycle error: {e}")


def run_payroll_reminder():
    """Send payroll preparation reminder on the 23rd of each month."""
    from backend.agents.genz_director import director
    from backend.core.database import MasterSession, CompanyRegistry

    logger.info("Scheduler: Running payroll reminder cycle")
    session = MasterSession()
    companies = session.query(CompanyRegistry).filter(CompanyRegistry.is_active == True).all()
    session.close()

    period = datetime.now().strftime("%Y-%m")
    reminder_lines = []

    for company in companies:
        try:
            agent = director.get_agent(company.id)
            if agent:
                result = agent.prepare_payroll(period)
                anomaly_count = len(result.get("anomalies", []))
                reminder_lines.append(
                    f"• {company.name}: {result['summary']['headcount']} employees · "
                    f"Total Net ₦{result['summary']['total_net']:,.0f} · "
                    f"{'⚠ ' + str(anomaly_count) + ' anomalies' if anomaly_count else '✓ clean'}"
                )
        except Exception as e:
            logger.error(f"Payroll prep error for {company.name}: {e}")

    if reminder_lines:
        body = f"Payroll for {period} has been prepared for your review:\n\n"
        body += "\n".join(reminder_lines)
        body += "\n\nPlease log in to approve: http://localhost:8501"
        _notify_esther("💰 GENZ HR — Payroll Ready for Approval", body)


def _send_daily_email(summary: dict):
    """Send daily HR summary to Esther via email."""
    subject = f"📋 GENZ HR Daily Summary — {summary.get('report_date', '')}"
    body = summary.get("formatted_summary", "No summary available")
    _notify_esther(subject, body)


def _notify_esther(subject: str, body: str):
    """
    Send notification to Esther.
    Currently logs to console — connect your email provider here.
    """
    logger.info(f"NOTIFICATION → {settings.ESTHER_EMAIL}")
    logger.info(f"Subject: {subject}")
    logger.info(f"Body preview: {body[:200]}...")

    # ── Email Integration ─────────────────────────────────────────────────────
    # Uncomment and configure to enable real email sending:
    #
    # import smtplib
    # from email.mime.text import MIMEText
    # from email.mime.multipart import MIMEMultipart
    #
    # msg = MIMEMultipart("alternative")
    # msg["Subject"] = subject
    # msg["From"] = "noreply@genzhr.local"
    # msg["To"] = settings.ESTHER_EMAIL
    # msg.attach(MIMEText(body, "plain"))
    #
    # with smtplib.SMTP("smtp.gmail.com", 587) as server:
    #     server.starttls()
    #     server.login("YOUR_EMAIL", "YOUR_APP_PASSWORD")
    #     server.sendmail(msg["From"], msg["To"], msg.as_string())


def create_scheduler() -> BackgroundScheduler:
    """Create and configure the background scheduler."""
    scheduler = BackgroundScheduler(
        job_defaults={"coalesce": False, "max_instances": 1},
        timezone="Africa/Lagos",  # Nigeria timezone
    )

    # Daily summary at 8:00 AM Lagos time
    scheduler.add_job(
        run_daily_director_cycle,
        CronTrigger(hour=settings.DAILY_SUMMARY_HOUR, minute=0),
        id="daily_director_cycle",
        name="GENZ Director Daily Cycle",
        replace_existing=True,
    )

    # Payroll preparation on 23rd of each month at 9:00 AM
    scheduler.add_job(
        run_payroll_reminder,
        CronTrigger(day=settings.PAYROLL_CHECK_DAY, hour=9, minute=0),
        id="payroll_reminder",
        name="Monthly Payroll Preparation",
        replace_existing=True,
    )

    logger.info("Scheduler configured:")
    logger.info(f"  Daily cycle: {settings.DAILY_SUMMARY_HOUR}:00 AM WAT")
    logger.info(f"  Payroll check: {settings.PAYROLL_CHECK_DAY}th of each month")

    return scheduler


# Global scheduler instance
scheduler = create_scheduler()
