"""
GENZ HR — Data Integrations Page (redesigned)
Modern SaaS UI using the GENZ HR Design System.
All backend logic unchanged.
"""
from __future__ import annotations
import streamlit as st
from datetime import datetime
from pathlib import Path


def render_integrations_page(selected_company: str, get_company_session_fn, get_company_dir_fn):
    from frontend.components.design_system import (
        section_label, empty_state, alert, status_badge, badge, mapping_row,
    )

    try:
        from backend.modules.integration_manager import (
            register_excel_source, register_gsheet_source,
            save_mappings, run_sync, list_data_sources, get_sync_history,
        )
        from backend.modules.column_mapper import FIELD_REGISTRY, propose_mappings
        from backend.modules.gsheets_connector import is_configured, extract_sheet_id
        from backend.core.integration_models import DataSource, ColumnMapping, SyncLog
    except ImportError as e:
        alert("Integration modules not available", str(e), "warning")
        return

    if not selected_company:
        empty_state("🔗", "Select a company first")
        return

    session = get_company_session_fn(selected_company)

    tab_sources, tab_excel, tab_gsheet, tab_mapping, tab_logs = st.tabs([
        "📋  Sources", "📂  Upload Excel", "🔗  Google Sheets", "🗺️  Column Mapping", "📜  Sync Logs",
    ])

    # ── Sources tab ──────────────────────────────────────────────────────
    with tab_sources:
        try:
            sources = list_data_sources(selected_company, session)
        except Exception:
            sources = []

        if not sources:
            empty_state("🔗", "No data sources connected",
                        "Upload an Excel file or connect a Google Sheet to get started.")
        else:
            active_n   = sum(1 for s in sources if s["status"] == "active")
            total_rows = sum(s["row_count"] or 0 for s in sources)
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Sources", len(sources))
            c2.metric("Active",        active_n)
            c3.metric("Total Rows",    f"{total_rows:,}")

            st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
            section_label("Connected Sources")

            for src in sources:
                icon_cls   = "gz-source-icon-excel" if src["source_type"] == "excel" else "gz-source-icon-gsheet"
                icon       = "📊" if src["source_type"] == "excel" else "🔗"
                type_label = "Excel / CSV" if src["source_type"] == "excel" else "Google Sheets"
                badge_html = status_badge(src["status"])
                last_sync  = src.get("last_synced_at") or ""
                if last_sync:
                    try:
                        last_sync = datetime.fromisoformat(last_sync).strftime("%d %b %Y %H:%M")
                    except Exception:
                        pass

                st.markdown(f"""
                <div class="gz-source-card">
                  <div class="gz-source-icon {icon_cls}">{icon}</div>
                  <div style="flex:1;">
                    <p class="gz-source-name">{src['name']}</p>
                    <p class="gz-source-meta">{type_label}
                      {f" · {src['tab_name']}" if src.get('tab_name') else ""}
                      · {src['row_count'] or 0:,} rows
                      {"· 🔄 Auto-sync" if src.get("auto_sync") else ""}</p>
                    {f'<p style="font-size:11px;color:var(--danger);margin:4px 0 0;">{src["error_message"][:80]}</p>' if src.get("error_message") else ""}
                  </div>
                  <div class="gz-source-right">
                    {badge_html}
                    <p style="font-size:11px;color:var(--gray-400);margin:4px 0 0;text-align:right;">
                      {f"Synced {last_sync}" if last_sync else "Never synced"}
                    </p>
                  </div>
                </div>
                """, unsafe_allow_html=True)

                col_s, col_h, _ = st.columns([1, 1, 4])
                with col_s:
                    if st.button("🔄  Sync", key=f"sync_{src['id']}", use_container_width=True):
                        with st.spinner("Syncing…"):
                            result = run_sync(selected_company, src["id"], session, trigger="manual")
                        if result.get("status") == "complete":
                            st.success(f"✅ +{result.get('rows_inserted',0)} / ~{result.get('rows_updated',0)}")
                        elif result.get("status") == "skipped":
                            st.info("ℹ️ No changes")
                        else:
                            st.error(result.get("error","Error"))
                        st.rerun()
                with col_h:
                    show_key = f"show_hist_{src['id']}"
                    if st.button("📋  History", key=f"hist_{src['id']}", use_container_width=True):
                        st.session_state[show_key] = not st.session_state.get(show_key, False)

                if st.session_state.get(f"show_hist_{src['id']}"):
                    history = get_sync_history(src["id"], session)
                    if not history:
                        st.caption("No sync history yet")
                    else:
                        for h in history[:8]:
                            icon2 = "✅" if h["status"] == "complete" else ("⏭" if h["status"] == "skipped" else "❌")
                            st.markdown(f"""
                            <div style="display:flex;justify-content:space-between;padding:7px 12px;
                                 background:var(--gray-50);border-radius:var(--radius-sm);margin-bottom:3px;">
                              <span style="font-size:12px;font-weight:600;">{icon2} {h['status'].title()}</span>
                              <span style="font-size:11px;color:var(--gray-400);">
                                +{h.get('rows_inserted',0)} · ~{h.get('rows_updated',0)} · {h.get('started_at','')[:16]}
                              </span>
                            </div>
                            """, unsafe_allow_html=True)

    # ── Excel upload tab ─────────────────────────────────────────────────
    with tab_excel:
        st.markdown('<div class="gz-card" style="max-width:620px">', unsafe_allow_html=True)
        section_label("Upload Excel or CSV File")
        st.caption("Supported: .xlsx, .xls, .csv · Large files processed in batches of 200 rows")

        uploaded_file = st.file_uploader("Drop file or click to browse",
                                         type=["xlsx","xls","csv"], label_visibility="collapsed")

        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                source_name = st.text_input("Source Label",
                                            value=Path(uploaded_file.name).stem)
            with col2:
                tab_name = st.text_input("Sheet Tab (blank = first)", placeholder="Sheet1")

            if st.button("👁️  Preview Mappings", use_container_width=True):
                raw = uploaded_file.read()
                uploaded_file.seek(0)
                try:
                    from backend.modules.data_ingestion import read_from_bytes
                    headers, rows = read_from_bytes(raw, uploaded_file.name, tab_name or None)
                    proposals     = propose_mappings(headers)

                    section_label(f"{len(rows):,} rows · {len(headers)} columns")
                    needs_review = 0
                    for p in proposals:
                        mapping_row(p.sheet_column, p.system_field, p.label, p.confidence)
                        if p.needs_review:
                            needs_review += 1

                    if needs_review:
                        alert(f"{needs_review} columns need manual mapping",
                              "Use 🗺️ Column Mapping tab to assign them.", "warning")

                    st.session_state.update({
                        "xl_raw": raw, "xl_fname": uploaded_file.name,
                        "xl_tab": tab_name, "xl_name": source_name,
                    })
                    st.success(f"✅ {len(rows):,} rows across {len(headers)} columns")
                except Exception as e:
                    st.error(f"Preview error: {e}")

            if st.session_state.get("xl_raw"):
                col_imp, col_reg, _ = st.columns([1.5, 1.5, 2])
                with col_imp:
                    if st.button("⬇️  Import Now", type="primary", use_container_width=True):
                        raw  = st.session_state["xl_raw"]
                        fname= st.session_state["xl_fname"]
                        dest = get_company_dir_fn(selected_company) / "uploads" / fname
                        dest.parent.mkdir(exist_ok=True)
                        dest.write_bytes(raw)
                        with st.spinner("Importing…"):
                            try:
                                from backend.modules.integrations.excel_importer import ExcelImporter
                                result = ExcelImporter(selected_company).import_file(
                                    str(dest), sheet_name=st.session_state.get("xl_tab") or None
                                )
                                st.success(f"✅ +{result.rows_inserted} new · ~{result.rows_updated} updated · {result.rows_errored} errors")
                                if result.needs_approval:
                                    alert(f"{len(result.needs_approval)} salary changes queued",
                                          "Go to ✅ Approvals.", "warning")
                            except Exception as e:
                                st.error(f"Import error: {e}")

                with col_reg:
                    if st.button("📋  Register Only", use_container_width=True):
                        raw  = st.session_state["xl_raw"]
                        fname= st.session_state["xl_fname"]
                        dest = get_company_dir_fn(selected_company) / "uploads" / fname
                        dest.parent.mkdir(exist_ok=True)
                        dest.write_bytes(raw)
                        try:
                            r = register_excel_source(selected_company, str(dest),
                                                      st.session_state.get("xl_name","Source"),
                                                      session)
                            st.success(f"✅ Registered — {r['row_count']:,} rows")
                        except Exception as e:
                            st.error(f"Error: {e}")

        st.markdown("</div>", unsafe_allow_html=True)

    # ── Google Sheets tab ────────────────────────────────────────────────
    with tab_gsheet:
        if not is_configured():
            alert("Google credentials not configured",
                  "Place service_account.json in project root. Running in demo mode.", "info")

        st.markdown('<div class="gz-card" style="max-width:600px">', unsafe_allow_html=True)
        section_label("Connect Google Sheet")
        gs_url  = st.text_input("Google Sheet URL", placeholder="https://docs.google.com/spreadsheets/d/…")
        gs_name = st.text_input("Source Label", placeholder="Employee Master Sheet")
        col1, col2, col3 = st.columns(3)
        with col1: gs_tab      = st.text_input("Tab Name", value="Sheet1")
        with col2: gs_auto     = st.toggle("Auto-Sync", value=True)
        with col3: gs_interval = st.number_input("Sync (min)", min_value=5, value=30)

        if gs_url:
            try:
                sid = extract_sheet_id(gs_url)
                st.caption(f"Sheet ID: `{sid}`")
            except Exception:
                st.warning("Invalid Google Sheets URL")

        col_c, col_p, _ = st.columns([1.5, 1.5, 2])
        with col_c:
            if st.button("🔗  Connect", type="primary", use_container_width=True, disabled=not gs_url):
                with st.spinner("Connecting…"):
                    try:
                        r = register_gsheet_source(selected_company, gs_url,
                                                   gs_name or gs_url[:40], session,
                                                   tab_name=gs_tab or None,
                                                   auto_sync=gs_auto,
                                                   sync_interval=gs_interval*60)
                        mock = " (demo mode)" if r.get("mock_mode") else ""
                        st.success(f"✅ Connected{mock} — {r.get('row_count',0):,} rows")
                    except Exception as e:
                        st.error(f"Error: {e}")

        with col_p:
            if st.button("👁️  Preview", use_container_width=True, disabled=not gs_url):
                with st.spinner("Fetching…"):
                    try:
                        from backend.modules.gsheets_connector import read_sheet, read_sheet_mock
                        if is_configured():
                            headers, rows = read_sheet(extract_sheet_id(gs_url), gs_tab or None)
                        else:
                            headers, rows = read_sheet_mock()
                        proposals = propose_mappings(headers)
                        st.markdown(f"**{len(rows):,} rows · {len(headers)} columns**")
                        for p in proposals[:8]:
                            mapping_row(p.sheet_column, p.system_field, p.label, p.confidence)
                    except Exception as e:
                        st.error(f"Preview error: {e}")

        st.markdown("</div>", unsafe_allow_html=True)

        with st.expander("📖 Setup guide"):
            st.markdown("""
**One-time setup:**
1. [Google Cloud Console](https://console.cloud.google.com) → Create project
2. Enable **Google Sheets API** + **Google Drive API**
3. Create Service Account → Download JSON key → save as `service_account.json`
4. Share your Sheet with the service account email
5. Set `GOOGLE_CREDENTIALS_PATH=service_account.json` in `.env`
            """)

    # ── Column Mapping tab ────────────────────────────────────────────────
    with tab_mapping:
        try:
            sources = list_data_sources(selected_company, session)
        except Exception:
            sources = []

        if not sources:
            empty_state("🗺️", "No sources", "Upload or connect a source first.")
        else:
            src_opts = {f"{s['name']} ({s['source_type']})": s["id"] for s in sources}
            sel_key  = st.selectbox("Data Source", list(src_opts.keys()))
            sel_id   = src_opts[sel_key]

            existing = session.query(ColumnMapping).filter(
                ColumnMapping.data_source_id == sel_id
            ).all()
            src_obj = session.query(DataSource).filter(DataSource.id == sel_id).first()

            proposals = []
            if not existing and src_obj:
                try:
                    if src_obj.source_type == "excel" and src_obj.file_path and Path(src_obj.file_path).exists():
                        from backend.modules.data_ingestion import read_excel
                        headers, _ = read_excel(src_obj.file_path, src_obj.tab_name)
                    else:
                        from backend.modules.gsheets_connector import read_sheet_mock
                        headers, _ = read_sheet_mock()
                    proposals = propose_mappings(headers)
                except Exception as e:
                    st.caption(f"Could not load headers: {e}")
            else:
                for m in existing:
                    class _P:
                        def __init__(self, col, field):
                            self.sheet_column = col
                            self.system_field = field
                            self.label        = FIELD_REGISTRY.get(field, field)
                            self.confidence   = 1.0
                            self.needs_review = False
                    proposals.append(_P(m.sheet_column, m.system_field))

            if proposals:
                section_label("Column Mappings")
                st.caption("Select the HR field each spreadsheet column maps to. Set to blank to skip.")
                field_opts   = ["— skip —"] + sorted(FIELD_REGISTRY.keys())
                field_labels = {f: f"{f} — {FIELD_REGISTRY[f]}" for f in FIELD_REGISTRY}
                overrides    = {}

                for p in proposals:
                    col_l, col_r = st.columns([2, 3])
                    with col_l:
                        st.markdown(f'<div style="padding:9px 12px;background:var(--gray-50);border-radius:var(--radius-md);font-family:var(--font-mono);font-size:12px;color:var(--gray-700);margin-top:4px;">{p.sheet_column}</div>', unsafe_allow_html=True)
                    with col_r:
                        curr     = p.system_field or ""
                        curr_idx = field_opts.index(curr) if curr in field_opts else 0
                        sel      = st.selectbox("→", field_opts, index=curr_idx,
                                                key=f"m_{sel_id}_{p.sheet_column}",
                                                format_func=lambda x: "— skip —" if x == "— skip —" else field_labels.get(x, x),
                                                label_visibility="collapsed")
                        if sel != curr:
                            overrides[p.sheet_column] = sel if sel != "— skip —" else None

                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                if st.button("💾  Save Mappings", type="primary", use_container_width=True):
                    prop_dicts = [{"sheet_column": getattr(p,"sheet_column",""), "system_field": getattr(p,"system_field","")} for p in proposals]
                    n = save_mappings(sel_id, prop_dicts, overrides, session)
                    st.success(f"✅ {n} mappings saved!")
                    st.rerun()
            else:
                empty_state("🗺️", "No columns to map")

    # ── Sync Logs tab ────────────────────────────────────────────────────
    with tab_logs:
        try:
            from backend.core.database import IntegrationLog as IL
            logs = session.query(IL).filter(
                IL.company_id == selected_company
            ).order_by(IL.timestamp.desc()).limit(100).all()
        except Exception:
            logs = []

        if not logs:
            empty_state("📜", "No sync logs yet")
        else:
            success_n = sum(1 for l in logs if l.success)
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Events", len(logs))
            c2.metric("✅ Success",   success_n)
            c3.metric("❌ Errors",    len(logs) - success_n)

            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            event_types = sorted(set(l.event for l in logs))
            f_ev = st.selectbox("Filter", ["All"] + event_types)

            section_label("Events")
            for log in logs[:60]:
                if f_ev != "All" and log.event != f_ev:
                    continue
                ts    = log.timestamp.strftime("%d %b %H:%M:%S") if log.timestamp else "—"
                icon  = "✅" if log.success else "❌"
                rows_ = f"+{log.rows_affected}" if log.rows_affected else ""
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:12px;padding:8px 14px;
                     background:var(--white);border:1px solid var(--gray-100);
                     border-radius:var(--radius-md);margin-bottom:3px;">
                  <span>{icon}</span>
                  <span style="font-size:11px;font-weight:700;background:var(--gray-100);
                        color:var(--gray-500);padding:2px 6px;border-radius:4px;
                        font-family:var(--font-mono);">{(log.source or '').upper()}</span>
                  <span style="font-size:13px;font-weight:600;color:var(--gray-700);flex:1;">{log.event}</span>
                  <span style="font-size:12px;color:var(--blue-600);font-weight:500;">{rows_}</span>
                  <span style="font-size:11px;color:var(--gray-400);font-family:var(--font-mono);">{ts}</span>
                </div>
                """, unsafe_allow_html=True)

    session.close()
