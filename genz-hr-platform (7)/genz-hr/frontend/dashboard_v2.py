"""
GENZ HR — Modern SaaS Dashboard
Redesigned UI: clean white, blue accents, component-based.
All backend logic unchanged — UI layer only.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
from datetime import datetime, date
import json

# ── Backend imports (unchanged) ───────────────────────────────────────────────
from backend.core.database import (
    init_master_db, MasterSession, CompanyRegistry,
    get_company_session, Employee, Candidate, PayrollRecord,
    TaskSheet, AttendanceRecord, AuditLog, EmploymentStatus,
    ApprovalRecord, IntegrationLog, DataIntegrationConfig,
)
from backend.core.config import settings, get_company_dir
from backend.core.approval_gate import (
    submit_action, approve_ticket, reject_ticket,
    get_pending_tickets, get_all_tickets,
    ActionType, TicketStatus, get_platform_pending_counts,
)
from backend.modules.payroll_engine import calculate_company_payroll
from backend.modules.template_engine import template_engine, BUILTIN_TEMPLATES
from backend.modules.audit_logger import log_action, get_audit_trail, format_audit_entry
from backend.agents.genz_director import director

# ── Design System ─────────────────────────────────────────────────────────────
from frontend.components.design_system import (
    inject_css, page_header, stat_card, badge, status_badge,
    section_label, empty_state, alert, sidebar_logo, sidebar_user,
    ticket_card, source_card, mapping_row,
)

# ─── App Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GENZ HR",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_master_db()
inject_css()


# ─── Helpers ──────────────────────────────────────────────────────────────────
def get_active_companies():
    session  = MasterSession()
    companies = session.query(CompanyRegistry).filter(CompanyRegistry.is_active == True).all()
    session.close()
    return [(c.id, c.name) for c in companies]


def fmt_naira(v):
    return f"₦{v:,.0f}" if v else "₦0"


def fmt_dt(dt):
    if not dt:
        return "—"
    return dt.strftime("%d %b %Y") if hasattr(dt, "strftime") else str(dt)


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    sidebar_logo()

    companies        = get_active_companies()
    pending_counts   = get_platform_pending_counts()
    total_pending    = sum(pending_counts.values())

    pending_indicator = (
        f' <span class="gz-pending-badge">{total_pending}</span>'
        if total_pending > 0 else ""
    )

    st.markdown("""<style>
    section[data-testid="stSidebar"] .stRadio div[data-baseweb="radio"] {
        align-items: center !important;
    }
    </style>""", unsafe_allow_html=True)

    nav = st.radio(
        "nav",
        [
            "🏠  Dashboard",
            "🏢  Companies",
            "👥  Employees",
            "📋  Recruitment",
            "💰  Payroll",
            "📊  Performance",
            "🕐  Attendance",
            "✅  Approvals",
            "🔗  Data Integrations",
            "📄  Templates",
            "📜  Audit Log",
            "⚙️  Settings",
        ],
        label_visibility="collapsed",
    )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    if companies:
        st.markdown('<p style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:.08em;padding:0 8px;margin-bottom:6px;">Active Company</p>', unsafe_allow_html=True)
        selected_company = st.selectbox(
            "company",
            options=[c[0] for c in companies],
            format_func=lambda x: next((c[1] for c in companies if c[0] == x), x),
            label_visibility="collapsed",
        )
    else:
        selected_company = None
        st.markdown("""
        <div style="margin:8px;padding:12px;background:var(--blue-50);border-radius:var(--radius-md);
             font-size:12px;color:var(--blue-700);">
          No companies yet. Go to ⚙️ Settings.
        </div>
        """, unsafe_allow_html=True)

    if total_pending > 0:
        st.markdown(f"""
        <div style="margin:12px 8px 0;padding:10px 14px;background:var(--danger-light);
             border:1px solid #fecaca;border-radius:var(--radius-md);
             display:flex;align-items:center;gap:10px;">
          <span style="font-size:14px;">🔔</span>
          <div>
            <div style="font-size:12px;font-weight:700;color:var(--danger-dark);">
              {total_pending} pending approval{"s" if total_pending != 1 else ""}
            </div>
            <div style="font-size:11px;color:#dc2626;opacity:.8;">Action required</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='flex:1'></div>", unsafe_allow_html=True)
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    sidebar_user("Esther", "HR Authority")
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown(f'<p style="font-size:10px;color:var(--gray-400);text-align:center;padding-bottom:8px;">GENZ HR v{settings.VERSION} · {len(companies)}/{settings.MAX_COMPANIES} companies</p>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
if nav == "🏠  Dashboard":
    page_header(
        "Dashboard",
        f"Good {'morning' if datetime.now().hour < 12 else 'afternoon'}, Esther 👋  — {date.today().strftime('%A, %d %B %Y')}"
    )

    # ── Pending approvals banner ──────────────────────────────────────────────
    if total_pending > 0:
        co_names = [next((c[1] for c in companies if c[0]==cid), cid)
                    for cid, n in pending_counts.items() if n > 0]
        alert(
            f"{total_pending} action{'s' if total_pending>1 else ''} awaiting your approval",
            f"Companies: {', '.join(co_names)} — go to ✅ Approvals",
            "warning",
        )

    # ── Stat cards ────────────────────────────────────────────────────────────
    session  = MasterSession()
    total_co = session.query(CompanyRegistry).filter(CompanyRegistry.is_active==True).count()
    session.close()

    total_employees = 0
    total_payroll   = 0.0
    total_pending_reviews = total_pending

    if selected_company:
        co_session = get_company_session(selected_company)
        total_employees = co_session.query(Employee).filter(Employee.status == EmploymentStatus.active).count()
        period = date.today().strftime("%Y-%m")
        pay_records = co_session.query(PayrollRecord).filter(
            PayrollRecord.period == period, PayrollRecord.status != "draft"
        ).all()
        total_payroll = sum(r.net_salary or 0 for r in pay_records)
        pending_cands = co_session.query(Candidate).filter(
            Candidate.shortlisted == True, Candidate.interview_status == "pending"
        ).count()
        co_session.close()
    else:
        pending_cands = 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        stat_card("Active Companies",    str(total_co),         f"{settings.MAX_COMPANIES - total_co} slots free", "🏢", "#3b82f6")
    with c2:
        stat_card("Active Employees",    str(total_employees),  "Current company",  "👥", "#8b5cf6")
    with c3:
        stat_card("Monthly Payroll",     fmt_naira(total_payroll), "This period",  "💰", "#10b981")
    with c4:
        stat_card("Pending Reviews",     str(total_pending_reviews), "Need attention", "🔔", "#f59e0b", delta_up=False)

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

    col_left, col_right = st.columns([3, 2])

    with col_left:
        section_label("Company Status")
        if not companies:
            empty_state("🏢", "No companies onboarded", "Go to ⚙️ Settings to register your first company.")
        else:
            for cid, cname in companies:
                try:
                    agent  = director.get_agent(cid)
                    report = agent.generate_daily_report() if agent else {}
                    alerts = report.get("alerts", [])
                    att    = report.get("attendance", {})
                    rec    = report.get("recruitment", {})
                    co_pending = pending_counts.get(cid, 0)

                    status_color  = "#ef4444" if alerts else "#22c55e"
                    status_text   = f"⚠ {len(alerts)} alert{'s' if len(alerts)>1 else ''}" if alerts else "✓ All clear"

                    pending_chip = ""
                    if co_pending:
                        pending_chip = f'<span class="gz-badge gz-badge-warning" style="margin-left:8px"><span class="gz-badge-dot"></span>⏳ {co_pending} pending</span>'

                    st.markdown(f"""
                    <div style="background:var(--white);border:1px solid var(--gray-200);
                         border-radius:var(--radius-lg);padding:16px 20px;margin-bottom:8px;
                         border-left:3px solid {status_color};transition:box-shadow .2s;">
                      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
                        <div style="display:flex;align-items:center;gap:8px;">
                          <span style="font-size:14px;font-weight:700;color:var(--gray-800);">{cname}</span>
                          {pending_chip}
                        </div>
                        <span style="font-size:12px;font-weight:600;color:{status_color};">{status_text}</span>
                      </div>
                      <div style="display:flex;gap:20px;font-size:12px;color:var(--gray-400);">
                        <span>👥 {rec.get('shortlisted',0)} shortlisted</span>
                        <span>🚨 {len(att.get('issues',[]))} attendance issues</span>
                        <span style="font-family:var(--font-mono);font-size:11px;color:var(--gray-300);">{cid}</span>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                except Exception as e:
                    st.markdown(f'<div class="gz-card" style="border-left:3px solid var(--danger);"><p style="font-size:13px;color:var(--danger);">⚠ {cname}: {str(e)[:60]}</p></div>', unsafe_allow_html=True)

    with col_right:
        section_label("Quick Actions")
        if st.button("🔄  Run Daily Cycle", use_container_width=True, type="primary"):
            with st.spinner("Running GENZ Director cycle…"):
                summary = director.run_daily_cycle()
            st.success(f"✅ Cycle complete — {summary['platform_summary']['companies_with_alerts']} companies need attention")

        if selected_company:
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            period_input = st.text_input("Payroll period", value=date.today().strftime("%Y-%m"), label_visibility="visible")
            if st.button("💰  Prepare Payroll", use_container_width=True):
                with st.spinner("Preparing payroll…"):
                    agent = director.get_agent(selected_company)
                    if agent:
                        ticket = agent.request_payroll_release(period_input)
                        st.success(f"✅ Payroll queued for approval — ticket {ticket.ticket_id}")
                    else:
                        st.error("Agent not available")

        section_label("Recent Activity")
        if selected_company:
            co_session = get_company_session(selected_company)
            logs = co_session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(6).all()
            co_session.close()
            if logs:
                for log in logs:
                    ts = log.timestamp.strftime("%H:%M") if log.timestamp else ""
                    st.markdown(f"""
                    <div class="gz-activity-item">
                      <div class="gz-activity-dot"></div>
                      <div>
                        <p class="gz-activity-text">{log.action} on {log.record_type or '—'}</p>
                        <p class="gz-activity-time">{ts} · {log.user}</p>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown('<p style="font-size:13px;color:var(--gray-400);text-align:center;padding:16px 0;">No recent activity</p>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANIES
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "🏢  Companies":
    page_header("Companies", "Manage your HR companies and GENZ Agents")

    tab_list, tab_new = st.tabs(["📋  All Companies", "➕  Register New"])

    with tab_list:
        session  = MasterSession()
        all_cos  = session.query(CompanyRegistry).all()
        session.close()

        if not all_cos:
            empty_state("🏢", "No companies registered", "Use the Register New tab to get started.")
        else:
            data = []
            for c in all_cos:
                data.append({
                    "Name":        c.name,
                    "ID":          c.id,
                    "Industry":    c.industry or "—",
                    "Size":        c.size or "—",
                    "Status":      "Active" if c.is_active else "Inactive",
                    "Last Summary": fmt_dt(c.last_summary_at),
                })
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True, hide_index=True,
                         column_config={"Status": st.column_config.TextColumn("Status")})

    with tab_new:
        st.markdown('<div class="gz-card" style="max-width:600px">', unsafe_allow_html=True)
        section_label("Company Details")
        col1, col2 = st.columns(2)
        with col1:
            new_id   = st.text_input("Company ID", placeholder="e.g. acme_corp", help="Lowercase, no spaces")
            new_name = st.text_input("Company Name", placeholder="Acme Corporation")
            new_industry = st.selectbox("Industry", [
                "Technology", "Fintech", "Healthcare", "Education",
                "E-commerce", "Media", "Logistics", "Other",
            ])
        with col2:
            new_size  = st.selectbox("Size", ["startup", "sme", "enterprise"])
            new_email = st.text_input("Contact Email", value=settings.ESTHER_EMAIL)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        if st.button("🚀  Register & Spawn GENZ Agent", type="primary", use_container_width=True):
            if new_id and new_name:
                try:
                    director.register_company(new_id.strip().lower(), new_name.strip(), new_industry, new_size, new_email)
                    from backend.core.database import init_company_db
                    init_company_db(new_id.strip().lower())
                    get_company_dir(new_id.strip().lower())
                    st.success(f"✅ {new_name} registered! GENZ Agent spawned.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Please fill in Company ID and Name")
        st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# EMPLOYEES
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "👥  Employees":
    if not selected_company:
        empty_state("👥", "Select a company", "Choose a company from the sidebar to manage employees.")
        st.stop()

    cname = next((c[1] for c in companies if c[0] == selected_company), selected_company)
    page_header(f"Employees", cname)

    tab_list, tab_add, tab_edit = st.tabs(["👥  Employee List", "➕  Add Employee", "✏️  Edit Employee"])

    with tab_list:
        co_session = get_company_session(selected_company)
        employees  = co_session.query(Employee).all()
        co_session.close()

        if not employees:
            empty_state("👥", "No employees yet", "Add your first employee using the Add Employee tab.")
        else:
            # Search + filter row
            sc1, sc2, sc3 = st.columns([3, 2, 1])
            with sc1:
                search = st.text_input("🔍  Search employees", placeholder="Name, position, department…", label_visibility="collapsed")
            with sc2:
                depts   = sorted(set(e.department for e in employees if e.department))
                dept_f  = st.selectbox("Department", ["All"] + depts, label_visibility="collapsed")
            with sc3:
                status_f = st.selectbox("Status", ["All", "Active", "On Leave", "Probation", "Terminated"], label_visibility="collapsed")

            # Build table data
            data = []
            for e in employees:
                name    = f"{e.first_name} {e.last_name}"
                status  = e.status.value if e.status else "active"
                if search and search.lower() not in name.lower() and search.lower() not in (e.position or "").lower() and search.lower() not in (e.department or "").lower():
                    continue
                if dept_f != "All" and (e.department or "") != dept_f:
                    continue
                if status_f != "All" and status.lower() != status_f.lower():
                    continue
                data.append({
                    "Employee":    name,
                    "Department":  e.department or "—",
                    "Position":    e.position or "—",
                    "Salary (₦)":  f"{e.gross_salary:,.0f}" if e.gross_salary else "—",
                    "Start Date":  fmt_dt(e.start_date),
                    "Status":      status.title(),
                    "Employee ID": e.employee_id,
                })

            if not data:
                empty_state("🔍", "No results", "Try adjusting your search or filters.")
            else:
                df = pd.DataFrame(data)
                st.markdown(f'<p style="font-size:12px;color:var(--gray-400);margin-bottom:8px;">{len(data)} employee{"s" if len(data)!=1 else ""}</p>', unsafe_allow_html=True)
                st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_add:
        st.markdown('<div class="gz-card">', unsafe_allow_html=True)
        section_label("Personal Details")
        col1, col2, col3 = st.columns(3)
        with col1:
            emp_id     = st.text_input("Employee ID", placeholder="EMP-001")
            first_name = st.text_input("First Name")
            last_name  = st.text_input("Last Name")
        with col2:
            email      = st.text_input("Email")
            phone      = st.text_input("Phone")
            position   = st.text_input("Position")
        with col3:
            department   = st.text_input("Department")
            emp_type     = st.selectbox("Employment Type", ["full-time", "part-time", "contract"])
            start_date   = st.date_input("Start Date")

        section_label("Compensation & Banking")
        col4, col5, col6 = st.columns(3)
        with col4:
            gross_salary  = st.number_input("Gross Monthly Salary (₦)", min_value=0, step=10000)
        with col5:
            bank_name     = st.text_input("Bank Name")
        with col6:
            account_number = st.text_input("Account Number")

        if st.button("➕  Add Employee", type="primary", use_container_width=True):
            if first_name and last_name:
                try:
                    co_session = get_company_session(selected_company)
                    new_emp = Employee(
                        employee_id    = emp_id or f"EMP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        first_name     = first_name, last_name=last_name,
                        email          = email or None, phone=phone or None,
                        department     = department or None, position=position or None,
                        employment_type= emp_type,
                        status         = EmploymentStatus.active,
                        gross_salary   = float(gross_salary),
                        start_date     = start_date,
                        bank_name      = bank_name or None,
                        account_number = account_number or None,
                    )
                    co_session.add(new_emp)
                    co_session.commit()
                    log_action(co_session, "Esther", "CREATE", "employees", "Employee",
                               str(new_emp.id), "employee_id", None, emp_id)
                    co_session.close()
                    st.success(f"✅ {first_name} {last_name} added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("First Name and Last Name are required.")
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_edit:
        co_session = get_company_session(selected_company)
        employees  = co_session.query(Employee).filter(Employee.status != EmploymentStatus.terminated).all()
        co_session.close()

        if not employees:
            empty_state("👥", "No employees to edit")
        else:
            emp_options = {f"{e.first_name} {e.last_name} ({e.employee_id})": e.id for e in employees}
            selected_key = st.selectbox("Select Employee", list(emp_options.keys()), label_visibility="visible")
            emp_id_sel   = emp_options[selected_key]

            co_session = get_company_session(selected_company)
            emp = co_session.query(Employee).filter(Employee.id == emp_id_sel).first()
            co_session.close()

            if emp:
                st.markdown('<div class="gz-card">', unsafe_allow_html=True)
                col1, col2 = st.columns(2)
                with col1:
                    new_pos  = st.text_input("Position", value=emp.position or "")
                    new_dept = st.text_input("Department", value=emp.department or "")
                    new_phone= st.text_input("Phone", value=emp.phone or "")
                with col2:
                    new_bank = st.text_input("Bank Name", value=emp.bank_name or "")
                    new_acc  = st.text_input("Account Number", value=emp.account_number or "")
                    status_opts = ["active", "on_leave", "probation", "terminated"]
                    new_status = st.selectbox("Status", status_opts, index=status_opts.index(emp.status.value))

                if st.button("💾  Save Changes", type="primary"):
                    co_session = get_company_session(selected_company)
                    emp = co_session.query(Employee).filter(Employee.id == emp_id_sel).first()
                    emp.position   = new_pos
                    emp.department = new_dept
                    emp.phone      = new_phone
                    emp.bank_name  = new_bank
                    emp.account_number = new_acc
                    emp.status     = EmploymentStatus(new_status)
                    co_session.commit()
                    co_session.close()
                    st.success("✅ Employee updated!")
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# RECRUITMENT
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "📋  Recruitment":
    if not selected_company:
        empty_state("📋", "Select a company first"); st.stop()

    cname = next((c[1] for c in companies if c[0] == selected_company), selected_company)
    page_header("Recruitment", cname)

    tab_candidates, tab_upload, tab_override = st.tabs(["👥  Candidates", "📂  Upload CV", "✏️  Override Scores"])

    with tab_candidates:
        co_session = get_company_session(selected_company)
        candidates = co_session.query(Candidate).order_by(Candidate.total_score.desc()).all()
        co_session.close()

        if not candidates:
            empty_state("📋", "No candidates yet", "Upload CVs to start building your pipeline.")
        else:
            # Metrics
            shortlisted = sum(1 for c in candidates if c.shortlisted)
            c1, c2, c3 = st.columns(3)
            c1.metric("Total", len(candidates))
            c2.metric("Shortlisted", shortlisted)
            c3.metric("Pending Interview", sum(1 for c in candidates if c.interview_status == "pending"))

            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

            data = []
            for c in candidates:
                eff_score = c.esther_override_score or c.total_score
                data.append({
                    "Name":      c.name,
                    "Position":  c.position_applied or "—",
                    "Score":     f"{eff_score:.1f}/100",
                    "Education": f"{c.education_score:.0f}",
                    "Skills":    f"{c.skills_score:.0f}",
                    "Experience":f"{c.experience_score:.0f}",
                    "Status":    c.interview_status or "pending",
                    "Shortlisted":"Yes" if c.shortlisted else "No",
                })
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_upload:
        st.markdown('<div class="gz-card" style="max-width:560px">', unsafe_allow_html=True)
        section_label("Upload Candidate CV")
        position_input = st.text_input("Position applying for")
        uploaded_cv    = st.file_uploader("Upload CV (PDF or DOCX)", type=["pdf", "docx"])

        if uploaded_cv and position_input:
            if st.button("📊  Parse & Score CV", type="primary"):
                upload_dir = get_company_dir(selected_company) / "uploads"
                upload_dir.mkdir(exist_ok=True)
                cv_path = upload_dir / uploaded_cv.name
                cv_path.write_bytes(uploaded_cv.read())
                with st.spinner("AI scoring in progress…"):
                    agent = director.get_agent(selected_company)
                    if agent:
                        result = agent.parse_cv(str(cv_path), position_input)
                        scored = result.get("result", {})
                        co_session = get_company_session(selected_company)
                        cand = Candidate(
                            name             = scored.get("name", uploaded_cv.name),
                            position_applied = position_input,
                            cv_path          = str(cv_path),
                            education_score  = scored.get("education_score", 0),
                            skills_score     = scored.get("skills_score", 0),
                            experience_score = scored.get("experience_score", 0),
                            keyword_score    = scored.get("keyword_score", 0),
                            total_score      = scored.get("total_score", 0),
                            shortlisted      = (scored.get("total_score", 0) or 0) >= 60,
                            interview_status = "pending",
                        )
                        co_session.add(cand)
                        co_session.commit()
                        co_session.close()
                        st.success(f"✅ CV scored! Total: {scored.get('total_score',0):.1f}/100")
                        st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_override:
        co_session  = get_company_session(selected_company)
        candidates  = co_session.query(Candidate).filter(Candidate.shortlisted==True).all()
        co_session.close()

        if not candidates:
            empty_state("✏️", "No shortlisted candidates to review")
        else:
            cand_options = {f"{c.name} — {c.position_applied or 'Unknown'}": c.id for c in candidates}
            sel_key = st.selectbox("Select Candidate", list(cand_options.keys()))
            sel_id  = cand_options[sel_key]

            co_session = get_company_session(selected_company)
            cand       = co_session.query(Candidate).filter(Candidate.id == sel_id).first()
            co_session.close()

            if cand:
                st.markdown('<div class="gz-card">', unsafe_allow_html=True)
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("AI Score",  f"{cand.total_score:.1f}")
                    st.metric("Education", f"{cand.education_score:.0f}")
                with col2:
                    st.metric("Skills",     f"{cand.skills_score:.0f}")
                    st.metric("Experience", f"{cand.experience_score:.0f}")

                new_override = st.slider("Esther Override Score", 0.0, 100.0,
                                         float(cand.esther_override_score or cand.total_score), 0.5)
                int_status   = st.selectbox("Interview Status",
                                            ["pending", "scheduled", "passed", "failed", "hired"],
                                            index=["pending","scheduled","passed","failed","hired"].index(cand.interview_status or "pending"))

                if st.button("💾  Save Override", type="primary"):
                    co_session = get_company_session(selected_company)
                    c = co_session.query(Candidate).filter(Candidate.id == sel_id).first()
                    c.esther_override_score = new_override
                    c.interview_status      = int_status
                    co_session.commit()
                    co_session.close()
                    st.success("✅ Score overridden!")
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PAYROLL
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "💰  Payroll":
    if not selected_company:
        empty_state("💰", "Select a company first"); st.stop()

    cname = next((c[1] for c in companies if c[0] == selected_company), selected_company)
    page_header("Payroll", f"{cname} · Nigeria Tax Act 2025")

    tab_prepare, tab_view, tab_calc = st.tabs(["📝  Prepare Payroll", "📋  View Records", "🧮  Calculator"])

    with tab_prepare:
        st.markdown('<div class="gz-card" style="max-width:480px">', unsafe_allow_html=True)
        section_label("Payroll Period")
        period = st.text_input("Pay Period (YYYY-MM)", value=date.today().strftime("%Y-%m"))
        if st.button("🔄  Compute Payroll", type="primary", use_container_width=True):
            with st.spinner("Computing payroll (Nigeria Tax Act 2025)…"):
                agent = director.get_agent(selected_company)
                if agent:
                    ticket = agent.request_payroll_release(period)
                    if ticket.status == TicketStatus.PENDING:
                        alert(f"Payroll queued — ticket {ticket.ticket_id}",
                              "Review the figures in ✅ Approvals before releasing.", "warning")
                    else:
                        st.success("Payroll processed!")
                else:
                    st.error("Agent not available")
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_view:
        co_session = get_company_session(selected_company)
        periods = sorted(set(r.period for r in co_session.query(PayrollRecord).all()), reverse=True)

        if not periods:
            empty_state("💰", "No payroll records yet", "Prepare a payroll run first.")
        else:
            selected_period = st.selectbox("Period", periods)
            records = co_session.query(PayrollRecord).filter(PayrollRecord.period == selected_period).all()
            co_session.close()

            if records:
                total_gross = sum(r.gross_salary or 0 for r in records)
                total_net   = sum(r.net_salary or 0 for r in records)
                total_paye  = sum(r.paye_tax or 0 for r in records)

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Headcount",    len(records))
                c2.metric("Total Gross",  fmt_naira(total_gross))
                c3.metric("Total Net",    fmt_naira(total_net))
                c4.metric("Total PAYE",   fmt_naira(total_paye))

                st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

                emp_map = {}
                co_session2 = get_company_session(selected_company)
                for r in records:
                    e = co_session2.query(Employee).filter(Employee.id == r.employee_id).first()
                    emp_map[r.id] = f"{e.first_name} {e.last_name}" if e else "—"
                co_session2.close()

                data = [{
                    "Employee":      emp_map.get(r.id, "—"),
                    "Gross (₦)":     f"{r.gross_salary:,.0f}" if r.gross_salary else "—",
                    "PAYE (₦)":      f"{r.paye_tax:,.0f}" if r.paye_tax else "—",
                    "Pension (₦)":   f"{r.pension_employee:,.0f}" if r.pension_employee else "—",
                    "Net (₦)":       f"{r.net_salary:,.0f}" if r.net_salary else "—",
                    "Status":        r.status or "draft",
                    "⚠ Anomaly":     "⚠ Yes" if r.anomaly_flag else "—",
                } for r in records]

                st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

                anomalies = [r for r in records if r.anomaly_flag]
                if anomalies:
                    section_label("Anomalies Requiring Review")
                    for r in anomalies:
                        alert(
                            emp_map.get(r.id, "Unknown"),
                            r.anomaly_reason or "Anomaly flagged",
                            "danger",
                        )

    with tab_calc:
        st.markdown('<div class="gz-card" style="max-width:560px">', unsafe_allow_html=True)
        section_label("Nigeria Tax Act 2025 — PAYE Calculator")
        st.caption("Effective 1 January 2026 · ₦800,000 tax-free · CRA removed")

        col1, col2 = st.columns(2)
        with col1:
            calc_gross = st.number_input("Monthly Gross Salary (₦)", min_value=0, value=500_000, step=10_000)
        with col2:
            calc_rent  = st.number_input("Annual Rent (₦)", min_value=0, value=0, step=50_000,
                                         help="20% of annual rent deducted, max ₦500,000")
        if calc_gross > 0:
            from backend.modules.payroll_engine import calculate_payroll
            r = calculate_payroll("DEMO", "Demo", "calc", float(calc_gross), annual_rent=float(calc_rent))
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Gross",   fmt_naira(r.gross_salary))
            c2.metric("PAYE/mo", fmt_naira(r.paye_monthly))
            c3.metric("Pension", fmt_naira(r.pension_employee))
            c4.metric("NHF",     fmt_naira(r.nhf_deduction))
            c5.metric("Net",     fmt_naira(r.net_salary))
            st.caption(f"Effective rate: {r.effective_tax_rate*100:.1f}%  ·  Annual PAYE: {fmt_naira(r.paye_annual)}")
        st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "📊  Performance":
    if not selected_company:
        empty_state("📊", "Select a company first"); st.stop()

    cname = next((c[1] for c in companies if c[0] == selected_company), selected_company)
    page_header("Performance", cname)

    from backend.modules.performance_analytics import (
        get_performance_trends, get_underperformer_alerts,
        get_top_performers, compute_department_averages,
    )

    tab_overview, tab_tasks, tab_depts = st.tabs(["📊  Overview", "📝  Task Sheets", "🏢  By Department"])

    with tab_overview:
        trends = get_performance_trends(selected_company)
        top    = get_top_performers(selected_company)
        under  = get_underperformer_alerts(selected_company)

        c1, c2, c3 = st.columns(3)
        avg_scores = [s for s in trends.get("avg_scores", []) if s > 0]
        c1.metric("Avg Score",     f"{sum(avg_scores)/len(avg_scores):.1f}" if avg_scores else "—")
        c2.metric("Top Performers", len(top))
        c3.metric("Needs Attention", len(under))

        if top:
            section_label("Top Performers")
            for t in top[:5]:
                st.markdown(f"""
                <div style="display:flex;align-items:center;justify-content:space-between;
                     padding:10px 16px;background:var(--white);border:1px solid var(--gray-200);
                     border-radius:var(--radius-md);margin-bottom:6px;">
                  <div>
                    <span style="font-size:14px;font-weight:600;color:var(--gray-800);">{t['name']}</span>
                    <span style="font-size:12px;color:var(--gray-400);margin-left:8px;">{t['position']}</span>
                    {'<span class="gz-badge gz-badge-success" style="margin-left:8px"><span class="gz-badge-dot"></span>Bonus eligible</span>' if t.get('bonus_eligible') else ''}
                  </div>
                  <span style="font-size:18px;font-weight:700;color:var(--blue-600);">{t['score']:.1f}</span>
                </div>
                """, unsafe_allow_html=True)

        if under:
            section_label("Needs Attention")
            for u in under:
                alert(u["name"], f"Score: {u['score']:.1f} · {u['department']}", "warning")

    with tab_tasks:
        co_session = get_company_session(selected_company)
        employees  = co_session.query(Employee).filter(Employee.status == EmploymentStatus.active).all()
        co_session.close()

        if not employees:
            empty_state("📝", "No active employees")
        else:
            emp_opts = {f"{e.first_name} {e.last_name}": e.id for e in employees}
            sel_emp  = st.selectbox("Employee", list(emp_opts.keys()))
            period_t = st.text_input("Period (YYYY-MM)", value=date.today().strftime("%Y-%m"))

            if st.button("🤖  Generate Task Sheet", type="primary"):
                agent = director.get_agent(selected_company)
                if agent:
                    result = agent.generate_task_sheet(emp_opts[sel_emp], period_t)
                    st.success(f"✅ Task sheet generated — {len(result.get('tasks',[]))} tasks")
                    st.json(result.get("tasks", []))

            # Show existing task sheets
            co_session = get_company_session(selected_company)
            sheets = co_session.query(TaskSheet).filter(
                TaskSheet.employee_id == emp_opts[sel_emp]
            ).order_by(TaskSheet.period.desc()).limit(6).all()
            co_session.close()

            if sheets:
                section_label("Recent Task Sheets")
                data = [{
                    "Period":      s.period,
                    "Completion":  f"{s.completion_pct:.0f}%" if s.completion_pct else "—",
                    "Score":       f"{s.performance_score:.1f}" if s.performance_score else "—",
                    "Bonus":       "Yes" if s.bonus_eligible else "No",
                } for s in sheets]
                st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

    with tab_depts:
        dept_avgs = compute_department_averages(selected_company)
        if not dept_avgs:
            empty_state("🏢", "No department data yet")
        else:
            data = [{"Department": d["department"], "Avg Score": f"{d['avg_score']:.1f}", "Headcount": d["headcount"]} for d in dept_avgs]
            st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ATTENDANCE
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "🕐  Attendance":
    if not selected_company:
        empty_state("🕐", "Select a company first"); st.stop()

    cname = next((c[1] for c in companies if c[0] == selected_company), selected_company)
    page_header("Attendance", cname)

    tab_issues, tab_log = st.tabs(["🚨  Issues", "➕  Log Attendance"])

    with tab_issues:
        agent  = director.get_agent(selected_company)
        issues = agent.detect_attendance_issues() if agent else []

        if not issues:
            st.markdown("""
            <div style="display:flex;align-items:center;gap:12px;padding:16px 20px;
                 background:var(--success-light);border:1px solid #bbf7d0;border-radius:var(--radius-lg);">
              <span style="font-size:20px;">✅</span>
              <div>
                <p style="margin:0;font-weight:600;color:var(--success-dark);">All clear</p>
                <p style="margin:0;font-size:12px;color:#15803d;">No attendance issues in the last 7 days</p>
              </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            c1, c2 = st.columns(2)
            c1.metric("Issues Found", len(issues))
            c2.metric("High Severity", sum(1 for i in issues if i.get("severity") == "high"))

            section_label("Issues Detected")
            for issue in issues:
                variant = "danger" if issue.get("severity") == "high" else "warning"
                alert(issue["name"], issue["issue"], variant)

    with tab_log:
        st.markdown('<div class="gz-card" style="max-width:480px">', unsafe_allow_html=True)
        section_label("Log Attendance")
        co_session = get_company_session(selected_company)
        employees  = co_session.query(Employee).filter(Employee.status == EmploymentStatus.active).all()
        co_session.close()

        if not employees:
            empty_state("👥", "No active employees")
        else:
            emp_opts = {f"{e.first_name} {e.last_name}": e.id for e in employees}
            sel_emp  = st.selectbox("Employee", list(emp_opts.keys()))
            att_date = st.date_input("Date", value=date.today())
            col1, col2, col3 = st.columns(3)
            with col1:
                task_score = st.slider("Task Activity", 0, 100, 80)
            with col2:
                comms_score = st.slider("Comms", 0, 100, 80)
            with col3:
                mtg_score = st.slider("Meetings", 0, 100, 80)

            if st.button("✅  Log Attendance", type="primary", use_container_width=True):
                agent = director.get_agent(selected_company)
                if agent:
                    result = agent.log_attendance(
                        emp_opts[sel_emp], att_date,
                        task_activity_score=task_score,
                        comms_activity_score=comms_score,
                        meeting_score=mtg_score,
                    )
                    st.success(f"✅ Logged! Ticket: {result['ticket_id']}")
        st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# APPROVAL QUEUE
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "✅  Approvals":
    page_header(
        "Approval Queue",
        "Nothing executes until you approve it"
        + (f" · {total_pending} pending" if total_pending else ""),
    )

    if not selected_company:
        empty_state("✅", "Select a company to view approvals"); st.stop()

    session = get_company_session(selected_company)
    tab_pending, tab_history = st.tabs([
        f"⏳  Pending ({len(get_pending_tickets(selected_company, session))})",
        "📋  History",
    ])

    RISK_BORDER = {"critical": "#ef4444", "high": "#f59e0b", "medium": "#3b82f6", "low": "#94a3b8"}

    with tab_pending:
        pending = get_pending_tickets(selected_company, session)

        if not pending:
            st.markdown("""
            <div style="display:flex;align-items:center;gap:16px;padding:20px 24px;
                 background:var(--success-light);border:1px solid #bbf7d0;border-radius:var(--radius-lg);">
              <span style="font-size:24px;">✅</span>
              <div>
                <p style="margin:0;font-weight:700;font-size:15px;color:var(--success-dark);">Queue is empty</p>
                <p style="margin:0;font-size:13px;color:#15803d;">All actions have been reviewed. No pending approvals.</p>
              </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            for ticket in pending:
                risk  = ticket.risk
                color = RISK_BORDER.get(risk, "#94a3b8")
                risk_variants = {"critical": "danger", "high": "warning", "medium": "blue", "low": "gray"}
                badge_html = badge(risk.title(), risk_variants.get(risk, "gray"))

                st.markdown(f"""
                <div style="background:var(--white);border:1px solid var(--gray-200);
                     border-left:4px solid {color};border-radius:0 var(--radius-lg) var(--radius-lg) 0;
                     padding:18px 20px;margin-bottom:4px;">
                  <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:8px;">
                    <span style="font-size:14px;font-weight:700;color:var(--gray-800);">{ticket.label}</span>
                    {badge_html}
                  </div>
                  <p style="font-size:13px;color:var(--gray-500);margin:0 0 10px;">{ticket.description}</p>
                  <div style="display:flex;gap:16px;font-size:11px;color:var(--gray-400);">
                    <span>🎫 {ticket.ticket_id}</span>
                    <span>👤 {ticket.requested_by}</span>
                    <span>🕐 {ticket.created_at.strftime('%d %b %H:%M') if ticket.created_at else '—'}</span>
                  </div>
                </div>
                """, unsafe_allow_html=True)

                with st.expander("View details"):
                    for k, v in ticket.payload.items():
                        if k not in ("record_ids", "payroll_result"):
                            st.markdown(f'<span style="font-size:12px;font-weight:600;color:var(--gray-400);text-transform:uppercase;">{k.replace("_"," ")}</span>: <span style="font-size:13px;color:var(--gray-700);">{v}</span>', unsafe_allow_html=True)

                note_key   = f"note_{ticket.ticket_id}"
                reason_key = f"reason_{ticket.ticket_id}"
                note   = st.text_input("Approval note (optional)", key=note_key, label_visibility="collapsed", placeholder="Add a note…")
                reason = st.text_input("Rejection reason", key=reason_key, label_visibility="collapsed", placeholder="Reason for rejection…")

                col_a, col_r, _ = st.columns([1.2, 1.2, 3])
                with col_a:
                    if st.button("✅  Approve", key=f"approve_{ticket.ticket_id}", type="primary", use_container_width=True):
                        ok, result = approve_ticket(selected_company, ticket.ticket_id, note=note, session=session)
                        if ok:
                            agent = director.get_agent(selected_company)
                            if agent:
                                agent.execute_approved_ticket(result)
                            st.success(f"✅ {ticket.label} — approved and executed")
                            st.rerun()
                        else:
                            st.error(result)

                with col_r:
                    if st.button("❌  Reject", key=f"reject_{ticket.ticket_id}", use_container_width=True):
                        ok, msg = reject_ticket(selected_company, ticket.ticket_id, reason=reason or "Rejected", session=session)
                        if ok:
                            st.error(f"❌ Rejected")
                            st.rerun()
                        else:
                            st.error(msg)

                st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    with tab_history:
        all_t = get_all_tickets(selected_company, session)
        resolved = [t for t in all_t if t.status != TicketStatus.PENDING]

        if not resolved:
            empty_state("📋", "No resolved tickets yet")
        else:
            approved_n = sum(1 for t in resolved if t.status == TicketStatus.APPROVED)
            rejected_n = sum(1 for t in resolved if t.status == TicketStatus.REJECTED)
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Resolved", len(resolved))
            c2.metric("✅ Approved", approved_n)
            c3.metric("❌ Rejected", rejected_n)

            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            for t in resolved:
                border = "#22c55e" if t.status == TicketStatus.APPROVED else "#ef4444"
                icon   = "✅" if t.status == TicketStatus.APPROVED else "❌"
                note_html = f'<span style="font-size:11px;color:var(--gray-400)"> · Note: {t.esther_note[:60]}</span>' if t.esther_note else ""
                st.markdown(f"""
                <div style="padding:12px 16px;border-left:3px solid {border};background:var(--white);
                     border-radius:0 var(--radius-md) var(--radius-md) 0;margin-bottom:6px;
                     border:1px solid var(--gray-100);border-left-width:3px;border-left-color:{border};">
                  <span style="font-weight:600;font-size:13px;color:var(--gray-800);">{icon} {t.label}</span>
                  <span style="font-size:11px;color:var(--gray-400);margin-left:8px;">{t.ticket_id}</span>
                  <br><span style="font-size:12px;color:var(--gray-500);">{t.description[:80]}</span>
                  <br><span style="font-size:11px;color:var(--gray-400);">
                    {t.resolved_at.strftime('%d %b %Y %H:%M') if t.resolved_at else '—'} by {t.resolved_by}
                    {note_html}
                  </span>
                </div>
                """, unsafe_allow_html=True)

    session.close()


# ═══════════════════════════════════════════════════════════════════════════════
# DATA INTEGRATIONS
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "🔗  Data Integrations":
    if not selected_company:
        empty_state("🔗", "Select a company first"); st.stop()

    cname = next((c[1] for c in companies if c[0] == selected_company), selected_company)
    page_header("Data Integrations", f"{cname} · Import from Excel or Google Sheets")

    from frontend.integrations_page import render_integrations_page
    render_integrations_page(selected_company, get_company_session, get_company_dir)


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "📄  Templates":
    if not selected_company:
        empty_state("📄", "Select a company first"); st.stop()

    cname = next((c[1] for c in companies if c[0] == selected_company), selected_company)
    page_header("Template Library", cname)

    tab_preview, tab_upload = st.tabs(["🔍  Preview & Generate", "📂  Upload Custom"])

    with tab_preview:
        col1, col2 = st.columns([1, 2])
        with col1:
            template_type = st.selectbox("Template", list(BUILTIN_TEMPLATES.keys()))
        with col2:
            st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)

        required_vars = template_engine.extract_variables(BUILTIN_TEMPLATES[template_type])
        st.markdown(f'<p style="font-size:12px;font-weight:600;color:var(--gray-400);">REQUIRED VARIABLES</p>', unsafe_allow_html=True)
        st.code(" · ".join(required_vars) if required_vars else "None", language=None)

        st.markdown('<div class="gz-card">', unsafe_allow_html=True)
        section_label("Fill Variables")
        col_grid = st.columns(3)
        var_values = {}
        for i, var in enumerate(required_vars):
            with col_grid[i % 3]:
                var_values[var] = st.text_input(f"{var}", key=f"var_{var}")
        st.markdown("</div>", unsafe_allow_html=True)

        if st.button("👁️  Preview Template", type="primary"):
            try:
                rendered = template_engine.render_builtin(template_type, var_values)
                st.markdown('<div class="gz-card">', unsafe_allow_html=True)
                st.markdown(rendered)
                st.markdown("</div>", unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Error: {e}")

    with tab_upload:
        st.markdown('<div class="gz-card" style="max-width:480px">', unsafe_allow_html=True)
        section_label("Upload Custom Template")
        tmpl_name   = st.text_input("Template Name")
        tmpl_type   = st.selectbox("Type", ["offer_letter", "employment_contract", "task_sheet", "payslip", "custom"])
        tmpl_file   = st.file_uploader("Template File (.md, .txt, .docx)", type=["md", "txt", "docx"])
        if tmpl_file and tmpl_name:
            if st.button("📤  Upload Template", type="primary", use_container_width=True):
                tmpl_dir = get_company_dir(selected_company) / "templates"
                tmpl_dir.mkdir(exist_ok=True)
                tmpl_path = tmpl_dir / tmpl_file.name
                tmpl_path.write_bytes(tmpl_file.read())
                st.success(f"✅ {tmpl_name} uploaded!")
        st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "📜  Audit Log":
    if not selected_company:
        empty_state("📜", "Select a company first"); st.stop()

    cname = next((c[1] for c in companies if c[0] == selected_company), selected_company)
    page_header("Audit Log", f"{cname} · Immutable record of all changes")

    co_session = get_company_session(selected_company)
    logs = co_session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(200).all()
    co_session.close()

    if not logs:
        empty_state("📜", "No audit log entries yet")
    else:
        # Filters
        fc1, fc2, fc3 = st.columns(3)
        df_all = pd.DataFrame([{
            "Timestamp":  l.timestamp.strftime("%Y-%m-%d %H:%M:%S") if l.timestamp else "",
            "User":       l.user,
            "Action":     l.action,
            "Module":     l.module or "",
            "Record":     l.record_type or "",
            "Field":      l.field_changed or "",
            "Old Value":  (l.old_value or "")[:50],
            "New Value":  (l.new_value or "")[:50],
        } for l in logs])

        with fc1:
            f_user = st.selectbox("User", ["All"] + sorted(df_all["User"].unique().tolist()))
        with fc2:
            f_mod  = st.selectbox("Module", ["All"] + sorted(df_all["Module"].unique().tolist()))
        with fc3:
            f_act  = st.selectbox("Action", ["All"] + sorted(df_all["Action"].unique().tolist()))

        filtered = df_all.copy()
        if f_user != "All": filtered = filtered[filtered["User"] == f_user]
        if f_mod  != "All": filtered = filtered[filtered["Module"] == f_mod]
        if f_act  != "All": filtered = filtered[filtered["Action"] == f_act]

        st.markdown(f'<p style="font-size:12px;color:var(--gray-400);margin-bottom:8px;">{len(filtered):,} entries</p>', unsafe_allow_html=True)
        st.dataframe(filtered, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "⚙️  Settings":
    page_header("Settings", "Platform configuration and administration")

    tab_platform, tab_register, tab_calc = st.tabs(["🔧  Platform", "🏢  Register Company", "🧮  PAYE Calculator"])

    with tab_platform:
        col1, col2, col3 = st.columns(3)
        col1.metric("Platform Version", settings.VERSION)
        col2.metric("Max Companies",    settings.MAX_COMPANIES)
        col3.metric("Active Companies", len(companies))

        section_label("Configuration")
        st.markdown(f"""
        <div class="gz-card">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
            <div>
              <p style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:.08em;margin:0 0 4px;">HR Authority</p>
              <p style="font-size:14px;color:var(--gray-800);margin:0;">{settings.ESTHER_EMAIL}</p>
            </div>
            <div>
              <p style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:.08em;margin:0 0 4px;">Local AI Model</p>
              <p style="font-size:14px;color:var(--gray-800);margin:0;">{settings.OLLAMA_MODEL}</p>
            </div>
            <div>
              <p style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:.08em;margin:0 0 4px;">Daily Cycle Time</p>
              <p style="font-size:14px;color:var(--gray-800);margin:0;">{settings.DAILY_SUMMARY_HOUR}:00 AM WAT</p>
            </div>
            <div>
              <p style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:.08em;margin:0 0 4px;">Payroll Check Day</p>
              <p style="font-size:14px;color:var(--gray-800);margin:0;">{settings.PAYROLL_CHECK_DAY}th of each month</p>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        section_label("Tax Law")
        st.markdown("""
        <div class="gz-card">
          <div style="font-size:13px;color:var(--gray-700);line-height:1.8;">
            <p style="margin:0 0 8px;font-weight:600;color:var(--gray-800);">Nigeria Tax Act 2025 · Effective 1 January 2026</p>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 24px;font-size:12px;">
              <span>₦0 – ₦800,000</span><span style="font-weight:600;color:var(--success-dark);">0% (tax-free)</span>
              <span>₦800,001 – ₦3,000,000</span><span>15%</span>
              <span>₦3,000,001 – ₦12,000,000</span><span>18%</span>
              <span>₦12,000,001 – ₦25,000,000</span><span>21%</span>
              <span>₦25,000,001 – ₦50,000,000</span><span>23%</span>
              <span>Above ₦50,000,000</span><span>25%</span>
            </div>
            <p style="margin:8px 0 0;font-size:11px;color:var(--gray-400);">CRA removed · Pension 8%/10% (PRA 2014) · NHF 2.5% · Rent relief 20% max ₦500k</p>
          </div>
        </div>
        """, unsafe_allow_html=True)

    with tab_register:
        st.markdown('<div class="gz-card" style="max-width:540px">', unsafe_allow_html=True)
        section_label("Register New Company")
        c1, c2 = st.columns(2)
        with c1:
            s_id   = st.text_input("Company ID", placeholder="acme_corp")
            s_name = st.text_input("Company Name", placeholder="Acme Corporation")
            s_ind  = st.selectbox("Industry", ["Technology","Fintech","Healthcare","Education","Other"])
        with c2:
            s_size  = st.selectbox("Size", ["startup","sme","enterprise"])
            s_email = st.text_input("Contact Email", value=settings.ESTHER_EMAIL)

        if st.button("🚀  Register Company", type="primary", use_container_width=True):
            if s_id and s_name:
                try:
                    director.register_company(s_id.strip().lower(), s_name.strip(), s_ind, s_size, s_email)
                    from backend.core.database import init_company_db
                    init_company_db(s_id.strip().lower())
                    get_company_dir(s_id.strip().lower())
                    st.success(f"✅ {s_name} registered!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Company ID and Name are required")
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_calc:
        st.markdown('<div class="gz-card" style="max-width:520px">', unsafe_allow_html=True)
        section_label("Quick PAYE Calculator")
        gc1, gc2 = st.columns(2)
        with gc1:
            c_gross = st.number_input("Monthly Gross (₦)", min_value=0, value=500_000, step=10_000, key="s_gross")
        with gc2:
            c_rent  = st.number_input("Annual Rent (₦)", min_value=0, value=0, step=50_000, key="s_rent")

        if c_gross > 0:
            from backend.modules.payroll_engine import calculate_payroll
            r = calculate_payroll("DEMO","Demo","calc",float(c_gross), annual_rent=float(c_rent))
            gc1, gc2, gc3, gc4, gc5 = st.columns(5)
            gc1.metric("Gross",  fmt_naira(r.gross_salary))
            gc2.metric("PAYE",   fmt_naira(r.paye_monthly))
            gc3.metric("Pension",fmt_naira(r.pension_employee))
            gc4.metric("NHF",    fmt_naira(r.nhf_deduction))
            gc5.metric("Net",    fmt_naira(r.net_salary))
            st.caption(f"Effective rate: {r.effective_tax_rate*100:.1f}% · Annual: {fmt_naira(r.paye_annual)}")
        st.markdown("</div>", unsafe_allow_html=True)
