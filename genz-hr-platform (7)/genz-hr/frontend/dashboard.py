"""
GENZ HR — Central Command Dashboard
Esther's single-screen control center for all 20 companies.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date
import json

from backend.core.database import (
    init_master_db, MasterSession, CompanyRegistry,
    get_company_session, Employee, Candidate, PayrollRecord,
    TaskSheet, AttendanceRecord, AuditLog, EmploymentStatus, ApprovalRecord
)
from backend.core.config import settings, get_company_dir
from backend.core.approval_gate import (
    submit_action, approve_ticket, reject_ticket,
    get_pending_tickets, get_all_tickets,
    ActionType, TicketStatus, get_platform_pending_counts
)
from backend.modules.payroll_engine import calculate_company_payroll
from backend.modules.template_engine import template_engine, BUILTIN_TEMPLATES
from backend.modules.audit_logger import log_action, get_audit_trail, format_audit_entry
from backend.agents.genz_director import director
from frontend.integrations_page import render_integrations_page

# ─── Page Config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="GENZ HR",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Styles ───────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');

:root {
    --bg: #0a0a0f;
    --surface: #13131a;
    --surface2: #1a1a24;
    --accent: #7c3aed;
    --accent2: #06b6d4;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --text: #e2e8f0;
    --muted: #64748b;
}

.stApp {
    background: var(--bg);
    font-family: 'DM Sans', sans-serif;
    color: var(--text);
}

h1, h2, h3 { font-family: 'Syne', sans-serif; }

.genz-header {
    background: linear-gradient(135deg, #7c3aed 0%, #06b6d4 100%);
    padding: 1.5rem 2rem;
    border-radius: 16px;
    margin-bottom: 1.5rem;
}

.genz-header h1 {
    font-family: 'Syne', sans-serif;
    font-size: 2rem;
    font-weight: 800;
    color: white;
    margin: 0;
    letter-spacing: -0.5px;
}

.genz-header p {
    color: rgba(255,255,255,0.8);
    margin: 0.25rem 0 0;
    font-size: 0.9rem;
}

.metric-card {
    background: var(--surface);
    border: 1px solid rgba(124,58,237,0.2);
    border-radius: 12px;
    padding: 1.25rem;
    text-align: center;
}

.metric-card .value {
    font-family: 'Syne', sans-serif;
    font-size: 2rem;
    font-weight: 800;
    color: var(--accent2);
}

.metric-card .label {
    font-size: 0.75rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 0.25rem;
}

.company-card {
    background: var(--surface);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 0.75rem;
    border-left: 3px solid var(--accent);
}

.alert-badge {
    display: inline-block;
    background: var(--danger);
    color: white;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 999px;
    font-weight: 600;
}

.ok-badge {
    display: inline-block;
    background: var(--success);
    color: white;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 999px;
    font-weight: 600;
}

.stDataFrame { border-radius: 8px; }

div[data-testid="metric-container"] {
    background: var(--surface);
    border: 1px solid rgba(124,58,237,0.2);
    border-radius: 12px;
    padding: 1rem;
}

.sidebar-title {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 1.4rem;
    color: white;
}

[data-testid="stSidebar"] {
    background: var(--surface) !important;
}

.stSelectbox > div > div {
    background: var(--surface2);
    border-color: rgba(124,58,237,0.3);
}

.stTextInput > div > div > input {
    background: var(--surface2);
    border-color: rgba(124,58,237,0.3);
    color: var(--text);
}

.approval-box {
    background: linear-gradient(135deg, rgba(124,58,237,0.1), rgba(6,182,212,0.1));
    border: 1px solid rgba(124,58,237,0.3);
    border-radius: 12px;
    padding: 1rem;
}
</style>
""", unsafe_allow_html=True)


# ─── Init ─────────────────────────────────────────────────────────────────────

init_master_db()


def get_active_companies():
    session = MasterSession()
    companies = session.query(CompanyRegistry).filter(
        CompanyRegistry.is_active == True
    ).all()
    result = [(c.id, c.name) for c in companies]
    session.close()
    return result


# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="sidebar-title">🤖 GENZ HR</div>', unsafe_allow_html=True)
    st.caption(f"Esther's AI HR Command Center")
    st.divider()

    nav = st.radio(
        "Navigation",
        [
            "🏠 Overview",
            "🏢 Companies",
            "👥 Employees",
            "📋 Recruitment",
            "💰 Payroll",
            "📊 Performance",
            "🕐 Attendance",
            "✅ Approval Queue",
            "🔗 Data Integrations",
            "📄 Templates",
            "📜 Audit Log",
            "⚙️ Settings",
        ],
        label_visibility="collapsed",
    )

    st.divider()
    
    companies = get_active_companies()
    if companies:
        selected_company = st.selectbox(
            "Active Company",
            options=[c[0] for c in companies],
            format_func=lambda x: next((c[1] for c in companies if c[0] == x), x),
        )
    else:
        selected_company = None
        st.info("No companies registered yet")

    st.divider()
    st.caption(f"👤 Esther · HR Authority")
    st.caption(f"🤖 {len(companies)} GENZ Agents active")

    # Pending approvals badge
    pending_counts = get_platform_pending_counts()
    total_pending  = sum(pending_counts.values())
    if total_pending > 0:
        st.markdown(
            f'<div style="background:#7c3aed;color:white;padding:8px 12px;'
            f'border-radius:8px;text-align:center;font-weight:700;margin-top:8px;">'
            f'⏳ {total_pending} Approval{"s" if total_pending != 1 else ""} Pending</div>',
            unsafe_allow_html=True,
        )


# ─── Main Header ──────────────────────────────────────────────────────────────

st.markdown("""
<div class="genz-header">
    <h1>🤖 GENZ HR Platform</h1>
    <p>AI-Powered HR Automation · Nigerian Labor Law Compliant · Esther's Control Center</p>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════

if nav == "🏠 Overview":
    st.subheader("Platform Overview")

    # ── Pending approvals callout — always shown first ────────────────────────
    pending_counts = get_platform_pending_counts()
    total_pending  = sum(pending_counts.values())
    if total_pending > 0:
        companies_with_pending = [
            f"{next((c[1] for c in companies if c[0]==cid), cid)} ({n})"
            for cid, n in pending_counts.items() if n > 0
        ]
        st.markdown(
            f'<div style="background:#7c3aed22;border:2px solid #7c3aed;'
            f'border-radius:10px;padding:16px 20px;margin-bottom:20px;">'
            f'<span style="font-size:18px;font-weight:700;color:#a78bfa;">'
            f'⏳ {total_pending} Action{"s" if total_pending != 1 else ""} Awaiting Your Approval</span><br>'
            f'<span style="color:#94a3b8;font-size:13px;">'
            f'{" · ".join(companies_with_pending)}</span><br>'
            f'<span style="color:#64748b;font-size:12px;margin-top:4px;display:block;">'
            f'Go to ✅ Approval Queue to review</span></div>',
            unsafe_allow_html=True,
        )

    # Platform metrics
    session = MasterSession()
    total = session.query(CompanyRegistry).count()
    active = session.query(CompanyRegistry).filter(CompanyRegistry.is_active == True).count()
    session.close()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Active Companies", active, delta=f"{settings.MAX_COMPANIES - active} slots free")
    with col2:
        st.metric("GENZ Agents Running", active)
    with col3:
        st.metric("Max Capacity", settings.MAX_COMPANIES)
    with col4:
        st.metric("Platform Status", "✅ Online")

    st.divider()

    if companies:
        st.subheader("Company Status Board")

        col_left, col_right = st.columns([2, 1])

        with col_left:
            for cid, cname in companies:
                try:
                    agent = director.get_agent(cid)
                    report = agent.generate_daily_report() if agent else {}
                    alerts = report.get("alerts", [])
                    badge = f'<span class="alert-badge">⚠ {len(alerts)} alerts</span>' if alerts else '<span class="ok-badge">✅ OK</span>'
                    
                    rec_count  = report.get("recruitment", {}).get("shortlisted", 0)
                    att_issues = len(report.get("attendance", {}).get("issues", []))
                    pending_n  = pending_counts.get(cid, 0)
                    pending_indicator = (
                        f'&nbsp;·&nbsp; <span style="color:#a78bfa;">⏳ {pending_n} pending approval{"s" if pending_n != 1 else ""}</span>'
                        if pending_n > 0 else ""
                    )

                    st.markdown(f"""
                    <div class="company-card">
                        <strong>{cname}</strong> {badge}
                        <div style="margin-top:0.5rem;font-size:0.85rem;color:#94a3b8">
                            👥 {rec_count} shortlisted &nbsp;·&nbsp;
                            🚨 {att_issues} attendance issues
                            {pending_indicator} &nbsp;·&nbsp;
                            ID: <code>{cid}</code>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"{cname}: {e}")

        with col_right:
            st.subheader("Run Daily Cycle")
            if st.button("🔄 Run GENZ Director Now", use_container_width=True):
                with st.spinner("GENZ Director running all agents..."):
                    summary = director.run_daily_cycle()
                st.success("Daily cycle complete!")
                st.markdown(summary.get("formatted_summary", ""))

    else:
        st.info("No companies onboarded yet. Go to ⚙️ Settings to register your first company.")


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANIES
# ═══════════════════════════════════════════════════════════════════════════════

elif nav == "🏢 Companies":
    st.subheader("Company Management")

    tab_active, tab_new, tab_offboard, tab_restore, tab_archived = st.tabs([
        "🏢 Active Companies",
        "➕ Register New",
        "📦 Offboard / Export",
        "🔄 Restore Company",
        "🗂️ Archived",
    ])

    # ── Tab 1: Active Companies ───────────────────────────────────────────────
    with tab_active:
        session = MasterSession()
        all_companies = session.query(CompanyRegistry).filter(CompanyRegistry.is_active == True).all()
        session.close()

        if all_companies:
            df = pd.DataFrame([{
                "ID":        c.id,
                "Name":      c.name,
                "Industry":  c.industry or "—",
                "Size":      c.size or "—",
                "Status":    "✅ Active",
                "Onboarded": c.onboarded_at.strftime("%Y-%m-%d") if c.onboarded_at else "—",
            } for c in all_companies])
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"{len(all_companies)} active companies · {settings.MAX_COMPANIES - len(all_companies)} slots available")
        else:
            st.info("No active companies. Register one or restore an archived company.")

    # ── Tab 2: Register New ───────────────────────────────────────────────────
    with tab_new:
        st.markdown("### Register a New Company")
        col1, col2 = st.columns(2)
        with col1:
            new_id   = st.text_input("Company ID (unique, lowercase)", placeholder="e.g. acme_corp")
            new_name = st.text_input("Company Name", placeholder="e.g. Acme Corporation")
            new_industry = st.selectbox("Industry", [
                "Technology", "Fintech", "Healthcare", "E-commerce",
                "Education", "Logistics", "Media", "Consulting", "Other"
            ])
        with col2:
            new_size  = st.selectbox("Company Size", ["startup", "sme", "enterprise"])
            new_email = st.text_input("Contact Email", value=settings.ESTHER_EMAIL)

        if st.button("🚀 Register Company & Spawn GENZ Agent", use_container_width=True):
            if new_id and new_name:
                try:
                    from backend.core.database import init_company_db
                    _cid = new_id.strip().lower().replace(" ", "_")
                    _master = MasterSession()
                    _exists = _master.query(CompanyRegistry).filter(CompanyRegistry.id == _cid).first()
                    if _exists and _exists.is_active:
                        _master.close()
                        st.warning(f"Company ID '{_cid}' is already active.")
                    else:
                        if _exists:
                            _exists.is_active    = True
                            _exists.agent_status = "idle"
                        else:
                            _co = CompanyRegistry(
                                id=_cid, name=new_name, industry=new_industry,
                                size=new_size, contact_email=new_email,
                            )
                            _master.add(_co)
                        _master.commit()
                        _master.close()
                        init_company_db(_cid)
                        get_company_dir(_cid)
                        st.success(f"✅ {new_name} registered! GENZ Agent spawned.")
                        st.rerun()
                except Exception as e:
                    st.error(f"Registration failed: {e}")
            else:
                st.warning("Please fill in Company ID and Name")

    # ── Tab 3: Offboard / Export ──────────────────────────────────────────────
    with tab_offboard:
        st.markdown("""
        ### 📦 Offboard or Export a Company

        **Export** — Download all company data without removing it from the platform.
        Perfect for backups or sharing data.

        **Offboard** — Company is leaving GENZ HR. Their data is exported and archived
        first, then removed from the active platform. They can be restored at any time.
        """)

        _master    = MasterSession()
        _actives   = _master.query(CompanyRegistry).filter(CompanyRegistry.is_active == True).all()
        _master.close()

        if not _actives:
            st.info("No active companies to export or offboard.")
        else:
            ob_options = {f"{c.name} ({c.id})": c.id for c in _actives}
            ob_key = st.selectbox("Select Company", list(ob_options.keys()), key="offboard_select")
            ob_id  = ob_options[ob_key]
            ob_name = next(c.name for c in _actives if c.id == ob_id)

            st.markdown("---")
            col_exp, col_off = st.columns(2)

            # ── Export only ───────────────────────────────────────────────────
            with col_exp:
                st.markdown("#### 📥 Export Data Only")
                st.caption("Downloads all data. Company stays active on the platform.")
                if st.button("⬇️ Download Company Data", use_container_width=True, key="btn_export"):
                    with st.spinner(f"Exporting {ob_name}…"):
                        try:
                            from backend.modules.company_offboarding import export_company_data
                            zip_bytes = export_company_data(ob_id, ob_name)
                            fname = f"genzhr_export_{ob_id}_{datetime.now().strftime('%Y%m%d')}.zip"
                            st.download_button(
                                label    = f"⬇️ Download {fname}",
                                data     = zip_bytes,
                                file_name= fname,
                                mime     = "application/zip",
                                key      = "dl_export_zip",
                            )
                            st.success(f"✅ Export ready — {len(zip_bytes):,} bytes")
                        except Exception as e:
                            st.error(f"Export failed: {e}")

            # ── Offboard ──────────────────────────────────────────────────────
            with col_off:
                st.markdown("#### 🚪 Offboard Company")
                st.caption("Exports data, removes from platform. Restorable later.")
                ob_reason = st.text_area(
                    "Reason for offboarding (optional)",
                    placeholder="Client decided to stop using GENZ HR…",
                    key="ob_reason", height=80,
                )
                confirm_ob = st.checkbox(
                    f"I confirm offboarding **{ob_name}** — data will be archived",
                    key="confirm_offboard",
                )
                if st.button(
                    "🚪 Offboard Company",
                    use_container_width=True,
                    disabled=not confirm_ob,
                    type="primary",
                    key="btn_offboard",
                ):
                    with st.spinner(f"Offboarding {ob_name}… exporting data first…"):
                        try:
                            from backend.modules.company_offboarding import offboard_company as do_ob
                            result    = do_ob(ob_id, ob_reason or "Client requested offboarding")
                            zip_bytes = result["zip_bytes"]
                            fname     = f"genzhr_final_export_{ob_id}_{datetime.now().strftime('%Y%m%d')}.zip"

                            st.success(f"✅ {ob_name} has been offboarded. Data archived and available below.")
                            st.download_button(
                                label    = f"⬇️ Download Final Export — {fname}",
                                data     = zip_bytes,
                                file_name= fname,
                                mime     = "application/zip",
                                key      = "dl_offboard_zip",
                            )
                            st.info("💡 This company can be restored at any time from the 🔄 Restore tab.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Offboarding failed: {e}")

    # ── Tab 4: Restore ────────────────────────────────────────────────────────
    with tab_restore:
        st.markdown("""
        ### 🔄 Restore a Company

        Upload a GENZ HR export ZIP to restore a company that previously left the platform.
        All their employees, payroll records, performance data, and history will be restored.

        **Two restore methods:**
        1. **Upload ZIP** — Upload the export ZIP file you downloaded when they left
        2. **From Archive** — Restore directly from the on-disk archive (no file upload needed)
        """)

        r_tab1, r_tab2 = st.tabs(["📂 Upload ZIP to Restore", "🗂️ Restore from Archive"])

        with r_tab1:
            st.markdown("#### Upload Export ZIP")
            restore_file = st.file_uploader(
                "Upload GENZ HR Export ZIP",
                type=["zip"],
                key="restore_zip_upload",
                help="Must be a ZIP exported from GENZ HR — contains company_info.json",
            )

            if restore_file:
                # Try to peek at company info
                import zipfile as _zf, io as _io
                try:
                    _z = _zf.ZipFile(_io.BytesIO(restore_file.read()))
                    restore_file.seek(0)
                    _info_name = next((n for n in _z.namelist() if "company_info.json" in n), None)
                    if _info_name:
                        _info = json.loads(_z.read(_info_name).decode())
                        st.info(f"""
                        **Archive detected:**
                        - Company: {_info.get('company_name', '?')}
                        - Original ID: `{_info.get('company_id', '?')}`
                        - Exported: {_info.get('exported_at', '?')[:10]}
                        """)
                        default_restore_id = _info.get("company_id", "")
                    else:
                        st.warning("company_info.json not found — may not be a valid GENZ HR export.")
                        default_restore_id = ""
                    _z.close()
                except Exception:
                    default_restore_id = ""

                restore_id = st.text_input(
                    "Company ID to restore as",
                    value=default_restore_id,
                    placeholder="original_company_id",
                    help="Use the original ID to restore exactly as before, or a new ID if they return under a different name.",
                    key="restore_id_input",
                )

                if st.button("🔄 Restore Company", type="primary", use_container_width=True,
                             disabled=not (restore_file and restore_id), key="btn_restore_upload"):
                    with st.spinner("Restoring company data…"):
                        try:
                            from backend.modules.company_offboarding import restore_company_from_zip
                            restore_file.seek(0)
                            result = restore_company_from_zip(restore_file.read(), restore_id.strip().lower())
                            st.success(result["message"])
                            if result.get("restored_from_db"):
                                st.info("🗄️ Full database restored — all historical data is back exactly as it was.")
                            else:
                                st.info(f"👥 {result.get('employees_imported', 0)} employees imported from Excel sheets.")
                            st.balloons()
                            st.rerun()
                        except ValueError as ve:
                            st.error(f"Restore error: {ve}")
                        except Exception as e:
                            st.error(f"Restore failed: {e}")

        with r_tab2:
            st.markdown("#### Restore from On-Disk Archive")
            st.caption("These are companies previously offboarded from this platform. No file upload needed.")
            try:
                from backend.modules.company_offboarding import list_archived_companies, restore_company_from_archive
                archived = list_archived_companies()
            except Exception:
                archived = []

            if not archived:
                st.info("No archived companies found on this platform.")
            else:
                for arch in archived:
                    with st.container():
                        col_info, col_btn = st.columns([3, 1])
                        with col_info:
                            st.markdown(f"""
                            **{arch['company_name']}** `{arch['company_id']}`
                            {arch.get('industry', '')} · {arch.get('size', '')}
                            Offboarded: {arch.get('offboarded_at', '')[:10]}
                            Reason: {arch.get('offboard_reason', '—')[:80]}
                            """)
                        with col_btn:
                            if st.button(
                                "🔄 Restore",
                                key=f"restore_arch_{arch['company_id']}",
                                use_container_width=True,
                            ):
                                with st.spinner(f"Restoring {arch['company_name']}…"):
                                    try:
                                        result = restore_company_from_archive(arch["company_id"])
                                        st.success(result["message"])
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Restore failed: {e}")
                        st.divider()

    # ── Tab 5: All Archived ───────────────────────────────────────────────────
    with tab_archived:
        st.markdown("### 🗂️ Archived Companies")
        st.caption("All companies that have been offboarded from GENZ HR.")

        _master = MasterSession()
        inactive = _master.query(CompanyRegistry).filter(CompanyRegistry.is_active == False).all()
        _master.close()

        try:
            from backend.modules.company_offboarding import list_archived_companies, get_archive_zip_bytes
            archived_meta = {a["company_id"]: a for a in list_archived_companies()}
        except Exception:
            archived_meta = {}

        if not inactive:
            st.info("No archived companies yet.")
        else:
            for co in inactive:
                meta = archived_meta.get(co.id, {})
                with st.expander(f"📁 {co.name} ({co.id}) — offboarded {meta.get('offboarded_at','')[:10] or '—'}"):
                    col1, col2, col3 = st.columns(3)
                    col1.markdown(f"**Industry:** {co.industry or '—'}")
                    col2.markdown(f"**Size:** {co.size or '—'}")
                    col3.markdown(f"**Reason:** {meta.get('offboard_reason','—')[:60]}")

                    btn_col1, btn_col2, btn_col3 = st.columns(3)

                    # Download archive
                    with btn_col1:
                        try:
                            zb = get_archive_zip_bytes(co.id)
                            if zb:
                                st.download_button(
                                    "⬇️ Download Archive",
                                    data      = zb,
                                    file_name = f"genzhr_archive_{co.id}.zip",
                                    mime      = "application/zip",
                                    key       = f"dl_arch_{co.id}",
                                    use_container_width=True,
                                )
                            else:
                                st.caption("No archive file found")
                        except Exception:
                            st.caption("Archive unavailable")

                    # Restore from archive
                    with btn_col2:
                        if st.button("🔄 Restore", key=f"arch_restore_{co.id}", use_container_width=True):
                            try:
                                from backend.modules.company_offboarding import restore_company_from_archive
                                result = restore_company_from_archive(co.id)
                                st.success(result["message"])
                                st.rerun()
                            except Exception as e:
                                st.error(f"Restore failed: {e}")

                    # Permanently delete
                    with btn_col3:
                        if st.button("🗑️ Delete Forever", key=f"perm_del_{co.id}", use_container_width=True):
                            confirm_perm = st.checkbox(
                                "⚠️ Confirm permanent deletion — cannot be undone",
                                key=f"perm_confirm_{co.id}"
                            )
                            if confirm_perm:
                                try:
                                    import shutil
                                    _m = MasterSession()
                                    _c = _m.query(CompanyRegistry).filter(CompanyRegistry.id == co.id).first()
                                    if _c:
                                        _m.delete(_c)
                                        _m.commit()
                                    _m.close()
                                    from backend.core.config import COMPANIES_DIR
                                    _arc = COMPANIES_DIR / "_archived"
                                    for _f in _arc.glob(f"*{co.id}*"):
                                        _f.unlink(missing_ok=True)
                                    st.success(f"✅ {co.name} permanently deleted.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Delete failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# EMPLOYEES
# ═══════════════════════════════════════════════════════════════════════════════

elif nav == "👥 Employees":
    if not selected_company:
        st.warning("Select a company first")
        st.stop()

    st.subheader(f"Employees — {next((c[1] for c in companies if c[0] == selected_company), selected_company)}")

    tab1, tab2, tab3 = st.tabs(["Employee List", "Add Employee", "Edit Employee"])

    with tab1:
        session = get_company_session(selected_company)
        employees = session.query(Employee).all()
        session.close()

        if employees:
            df = pd.DataFrame([{
                "ID": e.employee_id,
                "Name": f"{e.first_name} {e.last_name}",
                "Position": e.position,
                "Department": e.department,
                "Status": e.status.value if e.status else "—",
                "Gross Salary (₦)": f"{e.gross_salary:,.0f}" if e.gross_salary else "—",
                "Start Date": e.start_date.strftime("%Y-%m-%d") if e.start_date else "—",
            } for e in employees])
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Performance summary chart
            if len(employees) >= 2:
                salary_data = pd.DataFrame([
                    {"Name": f"{e.first_name} {e.last_name}", "Gross Salary": e.gross_salary or 0}
                    for e in employees
                ])
                fig = px.bar(salary_data, x="Name", y="Gross Salary",
                             title="Salary Distribution",
                             color="Gross Salary",
                             color_continuous_scale=["#7c3aed", "#06b6d4"])
                fig.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    font_color="#e2e8f0",
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No employees added yet")

    with tab2:
        st.markdown("### Add New Employee")
        col1, col2 = st.columns(2)
        with col1:
            emp_id = st.text_input("Employee ID", placeholder="EMP-001")
            first_name = st.text_input("First Name")
            last_name = st.text_input("Last Name")
            email = st.text_input("Email")
            phone = st.text_input("Phone")
            position = st.text_input("Position")
        with col2:
            department = st.text_input("Department")
            gross_salary = st.number_input("Gross Monthly Salary (₦)", min_value=0, step=10000)
            emp_type = st.selectbox("Employment Type", ["full-time", "part-time", "contract"])
            start_date = st.date_input("Start Date")
            bank_name = st.text_input("Bank Name")
            account_number = st.text_input("Account Number")

        if st.button("➕ Add Employee", use_container_width=True):
            if first_name and last_name and emp_id:
                try:
                    session = get_company_session(selected_company)

                    # Issue 5/6 fix: check duplicates before insert (UNIQUE constraint)
                    existing_id = session.query(Employee).filter(
                        Employee.employee_id == emp_id
                    ).first()
                    if existing_id:
                        session.close()
                        st.warning(f"⚠️ Employee ID '{emp_id}' already exists. Use a different ID.")
                        st.stop()

                    if email:
                        existing_email = session.query(Employee).filter(
                            Employee.email == email.lower().strip()
                        ).first()
                        if existing_email:
                            session.close()
                            st.warning(f"⚠️ Email '{email}' is already registered to another employee.")
                            st.stop()

                    emp = Employee(
                        employee_id=emp_id,
                        first_name=first_name,
                        last_name=last_name,
                        email=email.lower().strip() if email else None,
                        phone=phone if phone else None,
                        position=position if position else None,
                        department=department if department else None,
                        gross_salary=float(gross_salary),
                        employment_type=emp_type,
                        start_date=start_date,
                        bank_name=bank_name if bank_name else None,
                        account_number=account_number if account_number else None,
                        status=EmploymentStatus.active,
                    )
                    session.add(emp)
                    session.commit()
                    log_action(session, "Esther", "EMPLOYEE_CREATE", "employees",
                               "Employee", emp_id, new_value=f"{first_name} {last_name}")
                    session.close()
                    st.success(f"✅ {first_name} {last_name} added successfully!")
                    st.rerun()
                except Exception as e:
                    # Issue 5/6 fix: friendly error instead of raw traceback
                    err_msg = str(e)
                    if "UNIQUE constraint" in err_msg and "email" in err_msg:
                        st.error("⚠️ This email address is already registered. Please use a different email or leave it blank.")
                    elif "UNIQUE constraint" in err_msg and "employee_id" in err_msg:
                        st.error("⚠️ This Employee ID already exists. Please use a different ID.")
                    elif "UNIQUE constraint" in err_msg:
                        st.error("⚠️ A duplicate record was detected. Check Employee ID and Email for uniqueness.")
                    else:
                        st.error(f"Failed to add employee. Please check your inputs and try again.")
            else:
                st.warning("Please fill in required fields: Employee ID, First Name, Last Name")

    # ── Bulk Upload tab (Issue 3 fix) ─────────────────────────────────────────
    with st.expander("📂 Bulk Upload Employees (Excel / CSV)", expanded=False):
        st.markdown("""
        Upload an Excel or CSV file with employee data.
        **Required columns** (column names are flexible):
        `EmployeeID · FirstName · LastName · Email · Phone · Department · Salary · Position`
        """)
        upload_col1, upload_col2 = st.columns([3, 1])
        with upload_col1:
            bulk_file = st.file_uploader("Upload Employee Data", type=["xlsx", "xls", "csv"],
                                          key="bulk_emp_upload")
        with upload_col2:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            dl_template = st.button("📥 Download Template", use_container_width=True)

        if dl_template:
            import io as _io
            template_df = pd.DataFrame(columns=[
                "EmployeeID", "FirstName", "LastName", "Email", "Phone",
                "Department", "Position", "Salary", "BankName", "AccountNumber", "StartDate"
            ])
            buf = _io.BytesIO()
            template_df.to_excel(buf, index=False)
            st.download_button("⬇️ employee_template.xlsx", buf.getvalue(),
                               "employee_template.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        if bulk_file:
            st.info(f"📄 File: {bulk_file.name} — click Upload to process")
            if st.button("⬆️ Upload & Import Employees", type="primary", use_container_width=True,
                         key="bulk_upload_btn"):
                with st.spinner("Processing employee data…"):
                    try:
                        import io as _io
                        import pandas as _pd
                        import re as _re

                        raw = bulk_file.read()
                        buf = _io.BytesIO(raw)
                        suffix = bulk_file.name.rsplit(".", 1)[-1].lower()

                        if suffix == "csv":
                            df_bulk = _pd.read_csv(buf, dtype=str, keep_default_na=False)
                        else:
                            df_bulk = _pd.read_excel(buf, dtype=str, keep_default_na=False)

                        df_bulk.columns = [
                            c.strip().lower().replace(" ", "").replace("_", "")
                            for c in df_bulk.columns
                        ]
                        df_bulk = df_bulk.fillna("")

                        COL_ALIASES = {
                            "employeeid":"employee_id","empid":"employee_id","id":"employee_id",
                            "firstname":"first_name","fname":"first_name",
                            "lastname":"last_name","lname":"last_name",
                            "fullname":"full_name","name":"full_name",
                            "email":"email","emailaddress":"email",
                            "phone":"phone","phonenumber":"phone","mobile":"phone",
                            "department":"department","dept":"department",
                            "position":"position","jobtitle":"position","role":"position",
                            "salary":"gross_salary","grosssalary":"gross_salary",
                            "monthlysalary":"gross_salary",
                            "bankname":"bank_name","bank":"bank_name",
                            "accountnumber":"account_number","accountno":"account_number",
                            "startdate":"start_date",
                        }
                        df_bulk.rename(columns=COL_ALIASES, inplace=True)

                        co_session = get_company_session(selected_company)
                        added = skipped = err_count = 0
                        errors_list = []

                        for idx, row in df_bulk.iterrows():
                            row_num = idx + 2
                            try:
                                if "full_name" in df_bulk.columns and row.get("full_name", "").strip():
                                    parts = row["full_name"].strip().split(" ", 1)
                                    fn, ln = parts[0], parts[1] if len(parts) > 1 else ""
                                else:
                                    fn = row.get("first_name", "").strip()
                                    ln = row.get("last_name", "").strip()

                                if not fn:
                                    errors_list.append(f"Row {row_num}: missing first name")
                                    err_count += 1
                                    continue

                                email_v  = row.get("email", "").strip().lower() or None
                                emp_id_v = row.get("employee_id", "").strip()
                                emp_id_v = emp_id_v or f"EMP-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:18]}"

                                # Duplicate check
                                dup = None
                                if row.get("employee_id", "").strip():
                                    dup = co_session.query(Employee).filter(
                                        Employee.employee_id == row["employee_id"].strip()
                                    ).first()
                                if not dup and email_v:
                                    dup = co_session.query(Employee).filter(
                                        Employee.email == email_v
                                    ).first()
                                if dup:
                                    skipped += 1
                                    continue

                                sal_raw = row.get("gross_salary", "0").strip()
                                try:
                                    sal = float(_re.sub(r"[^\d.]", "", sal_raw)) if sal_raw else 0.0
                                except ValueError:
                                    sal = 0.0

                                start_d = None
                                sr = row.get("start_date", "").strip()
                                if sr:
                                    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"]:
                                        try:
                                            start_d = datetime.strptime(sr, fmt).date()
                                            break
                                        except ValueError:
                                            pass

                                new_emp = Employee(
                                    employee_id=emp_id_v, first_name=fn, last_name=ln,
                                    email=email_v, phone=row.get("phone","").strip() or None,
                                    department=row.get("department","").strip() or None,
                                    position=row.get("position","").strip() or None,
                                    gross_salary=sal,
                                    bank_name=row.get("bank_name","").strip() or None,
                                    account_number=row.get("account_number","").strip() or None,
                                    employment_type=row.get("employment_type","full-time").strip() or "full-time",
                                    start_date=start_d,
                                    status=EmploymentStatus.active,
                                )
                                co_session.add(new_emp)
                                co_session.flush()
                                added += 1
                            except Exception as row_err:
                                co_session.rollback()
                                errors_list.append(f"Row {row_num}: {str(row_err)[:80]}")
                                err_count += 1

                        co_session.commit()
                        co_session.close()

                        st.success(f"✅ Upload complete: **{added}** added · **{skipped}** duplicates skipped · **{err_count}** errors")
                        if errors_list:
                            with st.expander("⚠️ Row errors"):
                                for e in errors_list[:10]:
                                    st.caption(e)
                        st.rerun()

                    except Exception as e:
                        st.error(f"Upload failed: Check that your file has the required columns (FirstName, LastName). Details: {str(e)[:200]}")

    with tab3:
        session = get_company_session(selected_company)
        employees = session.query(Employee).all()
        session.close()

        if not employees:
            st.info("No employees to edit")
        else:
            emp_options = {f"{e.first_name} {e.last_name} ({e.employee_id})": e.id for e in employees}
            selected_emp_key = st.selectbox("Select Employee to Edit", list(emp_options.keys()))
            selected_emp_id = emp_options[selected_emp_key]

            session = get_company_session(selected_company)
            emp = session.query(Employee).filter(Employee.id == selected_emp_id).first()

            if emp:
                col1, col2 = st.columns(2)
                with col1:
                    new_position = st.text_input("Position", value=emp.position or "")
                    new_department = st.text_input("Department", value=emp.department or "")
                    new_salary = st.number_input("Gross Salary (₦)", value=float(emp.gross_salary or 0), step=10000)
                with col2:
                    new_status = st.selectbox("Status",
                        ["active", "on_leave", "probation", "terminated"],
                        index=["active", "on_leave", "probation", "terminated"].index(
                            emp.status.value if emp.status else "active"
                        ))
                    new_bank = st.text_input("Bank", value=emp.bank_name or "")
                    new_account = st.text_input("Account Number", value=emp.account_number or "")

                if st.button("💾 Save Changes (Esther)", use_container_width=True):
                    fields = {
                        "position": (emp.position, new_position),
                        "department": (emp.department, new_department),
                        "gross_salary": (emp.gross_salary, new_salary),
                        "status": (emp.status, new_status),
                        "bank_name": (emp.bank_name, new_bank),
                        "account_number": (emp.account_number, new_account),
                    }
                    for field, (old, new) in fields.items():
                        if str(old) != str(new):
                            setattr(emp, field, new)
                            log_action(session, "Esther", "EMPLOYEE_EDIT", "employees",
                                       "Employee", str(emp.id), field, old, new)
                    session.commit()
                    st.success("✅ Employee updated. Change logged to audit trail.")
            session.close()


# ═══════════════════════════════════════════════════════════════════════════════
# RECRUITMENT
# ═══════════════════════════════════════════════════════════════════════════════

elif nav == "📋 Recruitment":
    if not selected_company:
        st.warning("Select a company first")
        st.stop()

    cname = next((c[1] for c in companies if c[0] == selected_company), selected_company)
    st.subheader(f"Recruitment Pipeline — {cname}")

    tab1, tab2 = st.tabs(["Candidate Rankings", "Upload CV"])

    with tab1:
        session = get_company_session(selected_company)
        candidates = session.query(Candidate).order_by(Candidate.total_score.desc()).all()
        session.close()

        if candidates:
            df_data = []
            for i, c in enumerate(candidates):
                effective_score = c.esther_override_score or c.total_score
                df_data.append({
                    "Rank": i + 1,
                    "Name": c.name,
                    "Email": c.email,
                    "Position": c.position_applied,
                    "AI Score": c.total_score,
                    "Esther Score": c.esther_override_score or "—",
                    "Effective Score": effective_score,
                    "Shortlisted": "✅" if c.shortlisted else "❌",
                    "Interview": c.interview_status,
                    "ID": c.id,
                })

            df = pd.DataFrame(df_data)
            st.dataframe(df.drop(columns=["ID"]), use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("🎯 Override Candidate Score")
            
            cand_map = {f"{c.name} (Score: {c.total_score:.1f})": c.id for c in candidates}
            selected_cand = st.selectbox("Select Candidate", list(cand_map.keys()))
            selected_cand_id = cand_map[selected_cand]
            
            col1, col2 = st.columns(2)
            with col1:
                override_score = st.number_input("New Score (0–100)", min_value=0.0, max_value=100.0, step=0.5)
            with col2:
                override_shortlist = st.checkbox("Mark as Shortlisted")

            if st.button("✍️ Apply Override (Esther)", use_container_width=True):
                session = get_company_session(selected_company)
                cand = session.query(Candidate).filter(Candidate.id == selected_cand_id).first()
                old_score = cand.esther_override_score or cand.total_score
                cand.esther_override_score = override_score
                cand.shortlisted = override_shortlist
                log_action(session, "Esther", "CANDIDATE_OVERRIDE", "recruitment",
                           "Candidate", str(selected_cand_id), "score", old_score, override_score)
                session.commit()
                session.close()
                st.success("✅ Score overridden and logged")
                st.rerun()

            # Radar chart for top candidate
            top = candidates[0]
            fig = go.Figure(data=go.Scatterpolar(
                r=[top.education_score, top.skills_score, top.experience_score, top.keyword_score],
                theta=["Education", "Skills", "Experience", "Keywords"],
                fill="toself",
                line_color="#7c3aed",
                fillcolor="rgba(124,58,237,0.2)",
            ))
            fig.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                title=f"Top Candidate: {top.name}",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e2e8f0",
            )
            st.plotly_chart(fig, use_container_width=True)

        else:
            st.info("No candidates yet. Upload CVs to start scoring.")

    with tab2:
        st.markdown("### Upload CV for Scoring")
        position = st.text_input("Position Applied For", placeholder="e.g. Backend Engineer")
        uploaded_file = st.file_uploader("Upload CV (PDF or DOCX)", type=["pdf", "docx"])

        if uploaded_file and position:
            if st.button("🤖 Score with GENZ Agent", use_container_width=True):
                company_dir = get_company_dir(selected_company)
                file_path = company_dir / "uploads" / uploaded_file.name
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.read())

                with st.spinner("GENZ Agent analyzing CV..."):
                    from backend.modules.cv_parser import score_candidate
                    scored = score_candidate(str(file_path), position)

                    session = get_company_session(selected_company)
                    cand = Candidate(
                        name=scored.name or uploaded_file.name.replace(".pdf", "").replace(".docx", ""),
                        email=scored.email,
                        phone=scored.phone,
                        position_applied=position,
                        cv_path=str(file_path),
                        raw_cv_text=scored.raw_cv_text,
                        education_score=scored.education_score,
                        skills_score=scored.skills_score,
                        experience_score=scored.experience_score,
                        keyword_score=scored.keyword_score,
                        total_score=scored.total_score,
                        shortlisted=scored.total_score >= 60,
                    )
                    session.add(cand)
                    session.commit()
                    session.close()

                st.success(f"✅ CV scored! Total Score: **{scored.total_score:.1f}/100**")
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Education", f"{scored.education_score:.0f}/100")
                col2.metric("Skills", f"{scored.skills_score:.0f}/100")
                col3.metric("Experience", f"{scored.experience_score:.0f}/100")
                col4.metric("Keywords", f"{scored.keyword_score:.0f}/100")

                if scored.total_score >= 60:
                    st.success("🎉 Auto-shortlisted! Review before finalizing.")
                else:
                    st.warning("Score below 60 — not auto-shortlisted. You can override.")


# ═══════════════════════════════════════════════════════════════════════════════
# PAYROLL
# ═══════════════════════════════════════════════════════════════════════════════

elif nav == "💰 Payroll":
    if not selected_company:
        st.warning("Select a company first")
        st.stop()

    cname = next((c[1] for c in companies if c[0] == selected_company), selected_company)
    st.subheader(f"Payroll Engine — {cname}")

    tab1, tab2 = st.tabs(["Prepare & Approve Payroll", "Payroll History"])

    with tab1:
        period = st.text_input("Pay Period (YYYY-MM)", value=date.today().strftime("%Y-%m"))

        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("🤖 Prepare Payroll", use_container_width=True):
                with st.spinner("GENZ Agent computing Nigerian payroll..."):
                    agent = director.get_agent(selected_company)
                    if agent:
                        try:
                            # request_payroll_release computes payroll + queues approval
                            ticket = agent.request_payroll_release(period)
                            # Also run compute directly so we can show the draft table
                            from backend.modules.payroll_engine import calculate_company_payroll
                            from backend.core.database import get_company_session as _gcs, Employee as _Emp, EmploymentStatus as _ES
                            _sess = _gcs(selected_company)
                            _emps = _sess.query(_Emp).filter(_Emp.status == _ES.active).all()
                            _emp_data = [{"id": e.id, "name": f"{e.first_name} {e.last_name}",
                                          "gross_salary": e.gross_salary, "bonus": 0} for e in _emps]
                            _sess.close()
                            result = calculate_company_payroll(_emp_data, period)
                            result["ticket_id"] = ticket.ticket_id
                            st.session_state["payroll_result"] = result
                            st.info(f"✅ Payroll queued for approval — ticket {ticket.ticket_id}")
                        except Exception as _pe:
                            st.error(f"Payroll preparation failed: {str(_pe)[:200]}")
                    else:
                        st.error("No GENZ Agent available for this company.")

        if "payroll_result" in st.session_state:
            result = st.session_state["payroll_result"]
            
            if result.get("anomalies"):
                st.error(f"⚠️ {len(result['anomalies'])} anomalies detected — review before approving")
                for a in result["anomalies"]:
                    st.warning(f"**{a['employee']}:** {a['reason']}")

            st.markdown("### Payroll Draft")
            
            if result.get("results"):
                df = pd.DataFrame([{
                    "Employee": r["employee_name"],
                    "Gross (₦)": f"{r['gross_salary']:,.0f}",
                    "PAYE (₦)": f"{r['paye_monthly']:,.0f}",
                    "Pension (₦)": f"{r['pension_employee']:,.0f}",
                    "NHF (₦)": f"{r['nhf_deduction']:,.0f}",
                    "Bonus (₦)": f"{r['performance_bonus']:,.0f}",
                    "Net (₦)": f"{r['net_salary']:,.0f}",
                    "Tax Rate": f"{r['effective_tax_rate_pct']:.1f}%",
                    "⚠️": "⚠️" if r["anomaly"] else "✅",
                } for r in result["results"]])
                st.dataframe(df, use_container_width=True, hide_index=True)

                summary = result.get("summary", {})
                st.markdown("### Summary")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Headcount", summary.get("headcount", 0))
                col2.metric("Total Gross", f"₦{summary.get('total_gross', 0):,.0f}")
                col3.metric("Total PAYE", f"₦{summary.get('total_paye', 0):,.0f}")
                col4.metric("Total Net", f"₦{summary.get('total_net', 0):,.0f}")

            st.divider()
            st.markdown('<div class="approval-box">', unsafe_allow_html=True)
            st.markdown("### ✍️ Esther's Approval Required")
            st.info("All payroll records are in DRAFT status. Review and approve each record or batch approve.")
            
            session = get_company_session(selected_company)
            draft_records = session.query(PayrollRecord).filter(
                PayrollRecord.period == period,
                PayrollRecord.status == "draft",
            ).all()
            session.close()

            if draft_records:
                if st.button(f"✅ Approve All {len(draft_records)} Records", use_container_width=True):
                    session = get_company_session(selected_company)
                    for record in session.query(PayrollRecord).filter(
                        PayrollRecord.period == period, PayrollRecord.status == "draft"
                    ).all():
                        record.status = "approved"
                        record.approved_by = "Esther"
                        record.approved_at = datetime.utcnow()
                        log_action(session, "Esther", "PAYROLL_APPROVE", "payroll",
                                   "PayrollRecord", str(record.id))
                    session.commit()
                    session.close()
                    st.success(f"✅ {len(draft_records)} payroll records approved by Esther!")
                    del st.session_state["payroll_result"]
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    with tab2:
        session = get_company_session(selected_company)
        records = session.query(PayrollRecord).order_by(PayrollRecord.period.desc()).all()
        
        if records:
            periods = list(set(r.period for r in records))
            selected_period = st.selectbox("Period", sorted(periods, reverse=True))
            
            period_records = [r for r in records if r.period == selected_period]
            emps = {e.id: f"{e.first_name} {e.last_name}" 
                    for e in session.query(Employee).all()}
            
            df = pd.DataFrame([{
                "Employee": emps.get(r.employee_id, "Unknown"),
                "Net Salary": f"₦{r.net_salary:,.0f}",
                "Status": r.status,
                "Approved By": r.approved_by or "—",
            } for r in period_records])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No payroll history yet")
        session.close()


# ═══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════════════

elif nav == "📊 Performance":
    if not selected_company:
        st.warning("Select a company first")
        st.stop()

    cname = next((c[1] for c in companies if c[0] == selected_company), selected_company)
    st.subheader(f"Performance Analytics — {cname}")

    tab1, tab2 = st.tabs(["Generate Task Sheets", "Analytics"])

    with tab1:
        session = get_company_session(selected_company)
        employees = session.query(Employee).filter(Employee.status == EmploymentStatus.active).all()
        session.close()

        if not employees:
            st.info("No active employees")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                period_type = st.selectbox("Period Type", ["monthly", "weekly"])
            with col2:
                period = st.text_input("Period", value=date.today().strftime("%Y-%m"))
            with col3:
                st.markdown("<br>", unsafe_allow_html=True)
                gen_all = st.button("🤖 Generate All Task Sheets", use_container_width=True)

            if gen_all:
                agent = director.get_agent(selected_company)
                if agent:
                    try:
                        for emp in employees:
                            agent.generate_task_sheet(emp.id, period, period_type)
                        st.success(f"✅ Task sheets generated for {len(employees)} employees")
                    except Exception as _tse:
                        st.error(f"Task sheet generation failed: {str(_tse)[:200]}")

            # Show task sheets
            session = get_company_session(selected_company)
            sheets = session.query(TaskSheet).all()
            emp_map = {e.id: f"{e.first_name} {e.last_name}" for e in employees}
            session.close()

            if sheets:
                for sheet in sheets:
                    with st.expander(f"📋 {emp_map.get(sheet.employee_id, 'Unknown')} — {sheet.period}"):
                        if sheet.tasks:
                            df = pd.DataFrame(sheet.tasks)
                            st.dataframe(df, use_container_width=True, hide_index=True)

                        score = st.number_input(
                            "Performance Score", 0.0, 100.0,
                            value=float(sheet.performance_score or 0),
                            key=f"score_{sheet.id}"
                        )
                        feedback = st.text_area("Lead Feedback", value=sheet.lead_feedback or "", key=f"fb_{sheet.id}")
                        
                        if st.button("💾 Save Score", key=f"save_{sheet.id}"):
                            session = get_company_session(selected_company)
                            s = session.query(TaskSheet).filter(TaskSheet.id == sheet.id).first()
                            old_score = s.performance_score
                            s.performance_score = score
                            s.lead_feedback = feedback
                            s.bonus_eligible = score >= 85
                            log_action(session, "Esther", "PERFORMANCE_SCORE", "performance",
                                       "TaskSheet", str(sheet.id), "performance_score", old_score, score)
                            session.commit()
                            session.close()
                            st.success("✅ Score saved and logged")

    with tab2:
        period_filter = st.text_input("Filter by Period", value=date.today().strftime("%Y-%m"))
        agent = director.get_agent(selected_company)
        if agent:
            try:
                analytics = agent.analyze_performance(period_filter)
            except Exception as _e:
                st.info("📊 Performance analytics unavailable. Please ensure employees have task sheets assigned.")
                st.caption(f"Details: {str(_e)[:120]}")
                analytics = {}

            if not analytics:
                st.info("No analytics data available.")
            elif "message" in analytics:
                st.info(analytics["message"])
            else:
                col1, col2, col3 = st.columns(3)
                col1.metric("Avg Score",            f"{analytics.get('avg_performance_score', 0):.1f}/100")
                col2.metric("Avg Completion",        f"{analytics.get('avg_completion_pct', 0):.1f}%")
                col3.metric("Employees Reviewed",    analytics.get("total_employees_reviewed", 0))

                if analytics.get("top_performers"):
                    st.success(f"🌟 Top Performers: {', '.join(p['name'] for p in analytics['top_performers'])}")
                if analytics.get("low_performers"):
                    st.error(f"⚠️ Needs Attention: {', '.join(p['name'] for p in analytics['low_performers'])}")
                if analytics.get("attendance_risk"):
                    st.warning(f"🕐 Attendance Risk: {', '.join(p['name'] for p in analytics['attendance_risk'])}")
                if analytics.get("recommendations"):
                    st.markdown("### 💡 AI Recommendations")
                    for rec in analytics["recommendations"]:
                        st.markdown(f"• {rec}")
        else:
            st.info("No GENZ Agent available for this company.")


# ═══════════════════════════════════════════════════════════════════════════════
# ATTENDANCE
# ═══════════════════════════════════════════════════════════════════════════════

elif nav == "🕐 Attendance":
    if not selected_company:
        st.warning("Select a company first")
        st.stop()

    cname = next((c[1] for c in companies if c[0] == selected_company), selected_company)
    st.subheader(f"Attendance Monitor — {cname}")

    agent = director.get_agent(selected_company)
    if agent:
        try:
            issues = agent.detect_attendance_issues()
        except Exception as _ae:
            st.warning("Attendance data unavailable. Please ensure employees are added.")
            issues = []

        if issues:
            high = [i for i in issues if i.get("severity") == "high"]
            medium = [i for i in issues if i.get("severity") == "medium"]
            
            col1, col2 = st.columns(2)
            col1.metric("High Severity Issues", len(high), delta_color="inverse")
            col2.metric("Medium Severity Issues", len(medium), delta_color="inverse")

            for issue in issues:
                severity_color = "🔴" if issue["severity"] == "high" else "🟡"
                st.markdown(f"""
                <div class="company-card">
                    {severity_color} <strong>{issue['name']}</strong><br>
                    <small style="color:#94a3b8">{issue['issue']}</small>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✅ No attendance issues detected in the last 7 days")

    st.divider()
    st.subheader("Log Attendance")
    
    session = get_company_session(selected_company)
    employees = session.query(Employee).filter(Employee.status == EmploymentStatus.active).all()
    session.close()

    if employees:
        col1, col2, col3 = st.columns(3)
        with col1:
            att_emp = st.selectbox("Employee", 
                options=[e.id for e in employees],
                format_func=lambda x: next((f"{e.first_name} {e.last_name}" for e in employees if e.id == x), str(x))
            )
        with col2:
            att_date = st.date_input("Date", value=date.today())
        with col3:
            task_activity = st.slider("Task Activity Score", 0, 100, 70)

        if st.button("📝 Log Attendance", use_container_width=True):
            try:
                session = get_company_session(selected_company)
                # Check for existing record on same date
                existing = session.query(AttendanceRecord).filter(
                    AttendanceRecord.employee_id == att_emp,
                    AttendanceRecord.date == att_date,
                ).first()
                if existing:
                    existing.task_activity_score = task_activity
                    existing.check_in = datetime.now()
                    session.commit()
                    session.close()
                    st.success("✅ Attendance record updated")
                else:
                    record = AttendanceRecord(
                        employee_id=att_emp,
                        date=att_date,
                        check_in=datetime.now(),
                        task_activity_score=task_activity,
                    )
                    session.add(record)
                    session.commit()
                    session.close()
                    st.success("✅ Attendance logged")
            except Exception as _ate:
                st.error(f"Failed to log attendance: {str(_ate)[:150]}")


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# APPROVAL QUEUE
# ═══════════════════════════════════════════════════════════════════════════════

elif nav == "✅ Approval Queue":
    st.subheader("✅ Approval Queue")
    st.caption(
        "Nothing executes unless you approve it. "
        "Review every pending action — approve to execute, reject to permanently block."
    )

    if not selected_company:
        st.info("Select a company from the sidebar.")
        st.stop()

    session = get_company_session(selected_company)
    tab_pending, tab_history = st.tabs(["⏳ Pending Actions", "📋 History"])

    # ── Risk colour helper ────────────────────────────────────────────────────
    RISK_COLOUR  = {"critical": "#ef4444", "high": "#f59e0b", "medium": "#7c3aed", "low": "#10b981"}
    RISK_EMOJI   = {"critical": "🚨", "high": "⚠️", "medium": "🔔", "low": "📋"}
    STATUS_EMOJI = {"pending": "⏳", "approved": "✅", "rejected": "❌"}

    # ── PENDING TAB ───────────────────────────────────────────────────────────
    with tab_pending:
        pending = get_pending_tickets(selected_company, session)

        if not pending:
            st.success("✅ No pending approvals — all clear!")
        else:
            st.markdown(
                f'<div style="background:#7c3aed22;border:1px solid #7c3aed;'
                f'border-radius:8px;padding:12px 16px;margin-bottom:16px;">'
                f'<b style="color:#7c3aed;">⏳ {len(pending)} action{"s" if len(pending) != 1 else ""} '
                f'waiting for your decision</b></div>',
                unsafe_allow_html=True,
            )

            for ticket in pending:
                risk_col = RISK_COLOUR.get(ticket.risk, "#7c3aed")
                risk_emoji = RISK_EMOJI.get(ticket.risk, "📋")

                with st.container():
                    st.markdown(
                        f'<div style="border-left:4px solid {risk_col};'
                        f'background:#13131a;border-radius:0 8px 8px 0;'
                        f'padding:16px;margin-bottom:12px;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                        f'<span style="font-weight:700;font-size:15px;">'
                        f'{risk_emoji} {ticket.label}</span>'
                        f'<span style="color:{risk_col};font-size:11px;font-weight:700;'
                        f'background:{risk_col}22;padding:2px 8px;border-radius:4px;">'
                        f'{ticket.risk.upper()}</span></div>'
                        f'<div style="color:#94a3b8;margin:6px 0;font-size:13px;">'
                        f'{ticket.description}</div>'
                        f'<div style="color:#64748b;font-size:11px;">'
                        f'Requested by: {ticket.requested_by} · '
                        f'Ticket: {ticket.ticket_id} · '
                        f'{ticket.created_at.strftime("%d %b %Y %H:%M") if ticket.created_at else ""}'
                        f'</div></div>',
                        unsafe_allow_html=True,
                    )

                    # Show payload details in expander
                    with st.expander("View full details"):
                        payload = ticket.payload
                        for k, v in payload.items():
                            if k not in ("record_ids", "payroll_result"):
                                st.text(f"{k.replace('_', ' ').title()}: {v}")

                    col_approve, col_reject, col_spacer = st.columns([1, 1, 4])
                    with col_approve:
                        note = st.text_input(
                            "Approval note (optional)",
                            key=f"note_{ticket.ticket_id}",
                            placeholder="Add a note...",
                            label_visibility="collapsed",
                        )
                    with col_approve:
                        if st.button(
                            "✅ Approve",
                            key=f"approve_{ticket.ticket_id}",
                            type="primary",
                            use_container_width=True,
                        ):
                            ok, result = approve_ticket(
                                selected_company, ticket.ticket_id,
                                note=note, session=session
                            )
                            if ok:
                                # Execute the action via the agent
                                agent = director.get_agent(selected_company)
                                if agent:
                                    exec_r = agent.execute_approved_ticket(result)
                                    if exec_r.get("executed"):
                                        st.success(f"✅ Approved and executed: {ticket.label}")
                                    else:
                                        st.warning(f"Approved but execution issue: {exec_r.get('error', 'unknown')}")
                                else:
                                    st.success(f"✅ Approved: {ticket.label}")
                                st.rerun()
                            else:
                                st.error(result)

                    with col_reject:
                        reject_reason = st.text_input(
                            "Rejection reason",
                            key=f"reject_reason_{ticket.ticket_id}",
                            placeholder="Reason for rejection...",
                            label_visibility="collapsed",
                        )
                        if st.button(
                            "❌ Reject",
                            key=f"reject_{ticket.ticket_id}",
                            use_container_width=True,
                        ):
                            reason = reject_reason or "Rejected by Esther"
                            ok, msg = reject_ticket(
                                selected_company, ticket.ticket_id,
                                reason=reason, session=session
                            )
                            if ok:
                                st.error(f"❌ Rejected: {ticket.label}")
                                st.rerun()
                            else:
                                st.error(msg)

                    st.divider()

    # ── HISTORY TAB ───────────────────────────────────────────────────────────
    with tab_history:
        all_tickets = get_all_tickets(selected_company, session)
        resolved    = [t for t in all_tickets if t.status != TicketStatus.PENDING]

        if not resolved:
            st.info("No resolved tickets yet.")
        else:
            # Summary metrics
            approved_count = sum(1 for t in resolved if t.status == TicketStatus.APPROVED)
            rejected_count = sum(1 for t in resolved if t.status == TicketStatus.REJECTED)
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Resolved", len(resolved))
            c2.metric("✅ Approved", approved_count)
            c3.metric("❌ Rejected", rejected_count)

            st.divider()

            for ticket in resolved:
                status_emoji = STATUS_EMOJI.get(ticket.status.value, "📋")
                risk_col     = RISK_COLOUR.get(ticket.risk, "#64748b")
                border_col   = "#10b981" if ticket.status == TicketStatus.APPROVED else "#ef4444"

                st.markdown(
                    f'<div style="border-left:4px solid {border_col};'
                    f'background:#13131a;border-radius:0 8px 8px 0;'
                    f'padding:12px 16px;margin-bottom:8px;">'
                    f'<b>{status_emoji} {ticket.label}</b>'
                    f'<span style="color:#64748b;font-size:12px;margin-left:12px;">'
                    f'Ticket {ticket.ticket_id}</span><br>'
                    f'<span style="color:#94a3b8;font-size:13px;">{ticket.description}</span><br>'
                    f'<span style="color:#64748b;font-size:11px;">'
                    f'Resolved by {ticket.resolved_by} · '
                    f'{ticket.resolved_at.strftime("%d %b %Y %H:%M") if ticket.resolved_at else "—"}'
                    + (f' · Note: {ticket.esther_note}' if ticket.esther_note else '')
                    + f'</span></div>',
                    unsafe_allow_html=True,
                )

    session.close()



# ═══════════════════════════════════════════════════════════════════════════════
# DATA INTEGRATIONS
# ═══════════════════════════════════════════════════════════════════════════════

elif nav == "🔗 Data Integrations":
    render_integrations_page(selected_company, get_company_session, get_company_dir)


elif nav == "📄 Templates":
    if not selected_company:
        st.warning("Select a company first")
        st.stop()

    cname = next((c[1] for c in companies if c[0] == selected_company), selected_company)
    st.subheader(f"Template Library — {cname}")

    tab1, tab2 = st.tabs(["Preview & Generate", "Upload Custom Template"])

    with tab1:
        template_type = st.selectbox("Template Type", list(BUILTIN_TEMPLATES.keys()))

        # Show required variables
        required_vars = template_engine.extract_variables(BUILTIN_TEMPLATES[template_type])
        st.markdown(f"**Required Variables:** `{'` · `'.join(required_vars)}`")

        st.markdown("### Fill Variables")
        
        # Auto-populate from company employees
        session = get_company_session(selected_company)
        employees = session.query(Employee).all()
        session.close()

        variables = {}
        cols = st.columns(2)
        common_defaults = {
            "company_name": cname,
            "date": date.today().strftime("%d %B %Y"),
            "hr_signatory": "HR Manager",
            "acceptance_deadline": "Within 5 business days",
        }

        for i, var in enumerate(required_vars):
            with cols[i % 2]:
                default_val = common_defaults.get(var, "")
                variables[var] = st.text_input(f"{{{{{var}}}}}", value=default_val)

        if st.button("🤖 Generate Document Preview", use_container_width=True):
            rendered = template_engine.render_builtin(template_type, variables)
            st.markdown("### Preview (Esther review before sending)")
            st.markdown(rendered)
            
            st.download_button(
                "📥 Download as Markdown",
                data=rendered.encode(),
                file_name=f"{template_type}_{date.today()}.md",
                mime="text/markdown",
            )

    with tab2:
        st.markdown("### Upload Custom Template")
        template_name = st.text_input("Template Name")
        template_format = st.selectbox("Format", ["markdown", "json", "docx", "excel"])
        uploaded_template = st.file_uploader("Upload Template File")
        
        if uploaded_template and template_name:
            if st.button("📤 Upload Template"):
                company_dir = get_company_dir(selected_company)
                template_path = company_dir / "templates" / uploaded_template.name
                with open(template_path, "wb") as f:
                    f.write(uploaded_template.read())
                
                session = get_company_session(selected_company)
                from backend.core.database import HRTemplate
                tmpl = HRTemplate(
                    name=template_name,
                    template_type="custom",
                    file_format=template_format,
                    file_path=str(template_path),
                )
                session.add(tmpl)
                session.commit()
                session.close()
                st.success(f"✅ Template '{template_name}' uploaded and saved!")


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════════════

elif nav == "📜 Audit Log":
    if not selected_company:
        st.warning("Select a company first")
        st.stop()

    cname = next((c[1] for c in companies if c[0] == selected_company), selected_company)
    st.subheader(f"Audit Trail — {cname}")
    st.caption("Immutable log of all actions. Cannot be deleted or modified.")

    session = get_company_session(selected_company)
    logs = get_audit_trail(session, limit=100)
    session.close()

    if logs:
        df = pd.DataFrame([format_audit_entry(log) for log in logs])
        
        # Filter
        col1, col2 = st.columns(2)
        with col1:
            filter_user = st.selectbox("Filter by User", ["All"] + list(df["user"].unique()))
        with col2:
            filter_module = st.selectbox("Filter by Module", ["All"] + list(df["module"].unique()))

        if filter_user != "All":
            df = df[df["user"] == filter_user]
        if filter_module != "All":
            df = df[df["module"] == filter_module]

        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No audit logs yet. Actions will appear here as they occur.")


# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

elif nav == "⚙️ Settings":
    st.subheader("Platform Settings")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Platform Info")
        st.info(f"""
**Platform:** {settings.APP_NAME}  
**Version:** {settings.VERSION}  
**Authority:** {settings.ESTHER_EMAIL}  
**Max Companies:** {settings.MAX_COMPANIES}  
**LLM Model:** {settings.OLLAMA_MODEL}  
**LLM Server:** {settings.OLLAMA_BASE_URL}
        """)

    with col2:
        st.markdown("### Quick Stats")
        session = MasterSession()
        active = session.query(CompanyRegistry).filter(CompanyRegistry.is_active == True).count()
        total = session.query(CompanyRegistry).count()
        session.close()
        
        st.metric("Active Companies", active)
        st.metric("Available Slots", settings.MAX_COMPANIES - active)
        st.metric("Total Registered", total)

    st.divider()
    st.markdown("### Daily Cycle Schedule")
    st.info(f"""
- **Daily Summary:** {settings.DAILY_SUMMARY_HOUR}:00 AM  
- **Payroll Check Day:** {settings.PAYROLL_CHECK_DAY}th of each month  
- **Email Alerts:** Sent to {settings.ESTHER_EMAIL}
    """)

    st.divider()
    st.markdown("### Quick PAYE Calculator — Nigeria Tax Act 2025")
    st.caption("Effective 1 January 2026 · CRA removed · ₦800,000 tax-free threshold")

    col_a, col_b = st.columns(2)
    with col_a:
        calc_gross = st.number_input("Monthly Gross Salary (₦)", min_value=0, value=500_000, step=10_000)
    with col_b:
        calc_rent = st.number_input("Annual Rent (₦) — for rent relief", min_value=0, value=0, step=50_000,
                                    help="20% of annual rent deducted (max ₦500,000/year)")

    if calc_gross > 0:
        from backend.modules.payroll_engine import calculate_payroll
        result = calculate_payroll("DEMO", "Demo Employee", "2026-03",
                                   float(calc_gross), annual_rent=float(calc_rent))
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Gross", f"₦{result.gross_salary:,.0f}")
        col2.metric("PAYE/mo", f"₦{result.paye_monthly:,.0f}")
        col3.metric("Pension", f"₦{result.pension_employee:,.0f}")
        col4.metric("NHF", f"₦{result.nhf_deduction:,.0f}")
        col5.metric("Net", f"₦{result.net_salary:,.0f}")

        if calc_rent > 0:
            from backend.modules.payroll_engine import RENT_RELIEF_MAX, RENT_RELIEF_RATE
            relief = min(calc_rent * RENT_RELIEF_RATE, RENT_RELIEF_MAX)
            st.info(f"Rent relief applied: ₦{relief:,.0f}/year (₦{relief/12:,.0f}/month)")

        st.caption(f"Effective tax rate: {result.effective_tax_rate*100:.1f}% · Annual PAYE: ₦{result.paye_annual:,.0f}")
