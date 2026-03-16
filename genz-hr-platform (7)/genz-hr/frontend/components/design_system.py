"""
GENZ HR — Design System
Complete CSS design token system and reusable component library.
Modern SaaS aesthetic: clean white, blue accents, Inter/Geist typography.
"""

# ─── Master CSS (injected once on app load) ───────────────────────────────────

DESIGN_SYSTEM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Design Tokens ─────────────────────────────────────────────────────── */
:root {
  /* Color Palette */
  --white:        #ffffff;
  --gray-50:      #f8fafc;
  --gray-100:     #f1f5f9;
  --gray-200:     #e2e8f0;
  --gray-300:     #cbd5e1;
  --gray-400:     #94a3b8;
  --gray-500:     #64748b;
  --gray-600:     #475569;
  --gray-700:     #334155;
  --gray-800:     #1e293b;
  --gray-900:     #0f172a;

  /* Blue Primary */
  --blue-50:      #eff6ff;
  --blue-100:     #dbeafe;
  --blue-200:     #bfdbfe;
  --blue-400:     #60a5fa;
  --blue-500:     #3b82f6;
  --blue-600:     #2563eb;
  --blue-700:     #1d4ed8;

  /* Semantic */
  --success-light: #f0fdf4;
  --success:       #22c55e;
  --success-dark:  #16a34a;
  --warning-light: #fffbeb;
  --warning:       #f59e0b;
  --warning-dark:  #d97706;
  --danger-light:  #fef2f2;
  --danger:        #ef4444;
  --danger-dark:   #dc2626;
  --info-light:    #eff6ff;
  --info:          #3b82f6;

  /* Spacing scale (4px base) */
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-5:  20px;
  --space-6:  24px;
  --space-8:  32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;

  /* Border Radius */
  --radius-sm:  6px;
  --radius-md:  10px;
  --radius-lg:  14px;
  --radius-xl:  20px;
  --radius-full: 9999px;

  /* Shadows */
  --shadow-xs:  0 1px 2px 0 rgb(0 0 0 / 0.05);
  --shadow-sm:  0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
  --shadow-md:  0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
  --shadow-lg:  0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
  --shadow-xl:  0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);
  --shadow-blue: 0 4px 14px 0 rgb(59 130 246 / 0.25);

  /* Typography */
  --font-sans:  'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono:  'JetBrains Mono', 'Fira Code', monospace;
  --font-size-xs:   11px;
  --font-size-sm:   13px;
  --font-size-base: 14px;
  --font-size-md:   15px;
  --font-size-lg:   17px;
  --font-size-xl:   20px;
  --font-size-2xl:  24px;
  --font-size-3xl:  30px;
  --font-size-4xl:  36px;

  /* Transitions */
  --transition-fast: 120ms ease;
  --transition-base: 200ms ease;
  --transition-slow: 300ms ease;
}

/* ── Global Reset ──────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }

.stApp {
  background: var(--gray-50) !important;
  font-family: var(--font-sans) !important;
}

/* Hide Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }
section[data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; }

/* ── Sidebar ───────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
  background: var(--white) !important;
  border-right: 1px solid var(--gray-200) !important;
  min-width: 240px !important;
  max-width: 240px !important;
}

section[data-testid="stSidebar"] .stRadio > label { display: none; }
section[data-testid="stSidebar"] .stRadio > div { gap: 2px !important; }
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] {
  display: flex; flex-direction: column; gap: 2px;
}
section[data-testid="stSidebar"] .stRadio div[data-testid="stMarkdownContainer"] p {
  font-size: var(--font-size-sm) !important;
  font-weight: 500 !important;
  color: var(--gray-600) !important;
  padding: 8px 12px !important;
  border-radius: var(--radius-md) !important;
  cursor: pointer !important;
  transition: all var(--transition-fast) !important;
  margin: 0 !important;
}
section[data-testid="stSidebar"] .stRadio label {
  border: none !important;
  background: transparent !important;
  padding: 0 !important;
}

/* ── Main Content ──────────────────────────────────────────────────────── */
.main .block-container {
  padding: 24px 32px !important;
  max-width: 1400px !important;
}

/* ── Streamlit Native Overrides ────────────────────────────────────────── */
.stButton > button {
  font-family: var(--font-sans) !important;
  font-size: var(--font-size-sm) !important;
  font-weight: 600 !important;
  border-radius: var(--radius-md) !important;
  border: 1px solid var(--gray-200) !important;
  padding: 8px 16px !important;
  transition: all var(--transition-fast) !important;
  cursor: pointer !important;
}
.stButton > button:hover {
  border-color: var(--blue-500) !important;
  color: var(--blue-600) !important;
  transform: translateY(-1px) !important;
  box-shadow: var(--shadow-sm) !important;
}
.stButton > button[kind="primary"] {
  background: var(--blue-600) !important;
  border-color: var(--blue-600) !important;
  color: white !important;
  box-shadow: var(--shadow-blue) !important;
}
.stButton > button[kind="primary"]:hover {
  background: var(--blue-700) !important;
  border-color: var(--blue-700) !important;
  color: white !important;
  box-shadow: 0 6px 20px 0 rgb(59 130 246 / 0.35) !important;
}

.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div > select,
.stDateInput > div > div > input,
.stTextArea textarea {
  font-family: var(--font-sans) !important;
  font-size: var(--font-size-sm) !important;
  border: 1px solid var(--gray-200) !important;
  border-radius: var(--radius-md) !important;
  background: var(--white) !important;
  padding: 9px 12px !important;
  color: var(--gray-800) !important;
  transition: border-color var(--transition-fast) !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus,
.stTextArea textarea:focus {
  border-color: var(--blue-500) !important;
  box-shadow: 0 0 0 3px var(--blue-100) !important;
  outline: none !important;
}

.stSelectbox > div { border-radius: var(--radius-md) !important; }
.stSelectbox label, .stTextInput label, .stNumberInput label,
.stDateInput label, .stTextArea label {
  font-family: var(--font-sans) !important;
  font-size: var(--font-size-xs) !important;
  font-weight: 600 !important;
  color: var(--gray-500) !important;
  letter-spacing: 0.05em !important;
  text-transform: uppercase !important;
  margin-bottom: 4px !important;
}

.stTabs [data-baseweb="tab-list"] {
  background: var(--gray-100) !important;
  padding: 4px !important;
  border-radius: var(--radius-lg) !important;
  gap: 2px !important;
  border-bottom: none !important;
}
.stTabs [data-baseweb="tab"] {
  font-family: var(--font-sans) !important;
  font-size: var(--font-size-sm) !important;
  font-weight: 500 !important;
  color: var(--gray-500) !important;
  border-radius: var(--radius-md) !important;
  padding: 6px 14px !important;
  border: none !important;
  background: transparent !important;
  transition: all var(--transition-fast) !important;
}
.stTabs [aria-selected="true"] {
  background: var(--white) !important;
  color: var(--gray-800) !important;
  font-weight: 600 !important;
  box-shadow: var(--shadow-xs) !important;
}
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }

.stDataFrame {
  border: 1px solid var(--gray-200) !important;
  border-radius: var(--radius-lg) !important;
  overflow: hidden !important;
}

.stMetric {
  background: var(--white) !important;
  border: 1px solid var(--gray-200) !important;
  border-radius: var(--radius-lg) !important;
  padding: 16px 20px !important;
}
.stMetric label {
  font-family: var(--font-sans) !important;
  font-size: var(--font-size-xs) !important;
  font-weight: 600 !important;
  color: var(--gray-400) !important;
  text-transform: uppercase !important;
  letter-spacing: 0.08em !important;
}
.stMetric [data-testid="metric-container"] > div:nth-child(2) {
  font-family: var(--font-sans) !important;
  font-size: var(--font-size-2xl) !important;
  font-weight: 700 !important;
  color: var(--gray-900) !important;
}

.stAlert {
  border-radius: var(--radius-lg) !important;
  border: none !important;
  font-family: var(--font-sans) !important;
  font-size: var(--font-size-sm) !important;
}

.stSpinner > div { color: var(--blue-500) !important; }

div[data-testid="stExpander"] {
  border: 1px solid var(--gray-200) !important;
  border-radius: var(--radius-lg) !important;
  overflow: hidden !important;
  background: var(--white) !important;
}
div[data-testid="stExpander"] summary {
  font-family: var(--font-sans) !important;
  font-size: var(--font-size-sm) !important;
  font-weight: 600 !important;
  color: var(--gray-700) !important;
  padding: 12px 16px !important;
}

hr { border-color: var(--gray-200) !important; margin: 16px 0 !important; }

.stFileUploader {
  border: 2px dashed var(--gray-200) !important;
  border-radius: var(--radius-lg) !important;
  background: var(--gray-50) !important;
  padding: 24px !important;
  transition: border-color var(--transition-base) !important;
}
.stFileUploader:hover { border-color: var(--blue-400) !important; }

/* ── Custom Component Styles ───────────────────────────────────────────── */

/* Page Header */
.gz-page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--gray-200);
}
.gz-page-title {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--gray-900);
  letter-spacing: -0.025em;
  margin: 0;
  line-height: 1.2;
}
.gz-page-subtitle {
  font-size: var(--font-size-sm);
  color: var(--gray-400);
  margin: 4px 0 0 0;
  font-weight: 400;
}

/* Cards */
.gz-card {
  background: var(--white);
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  padding: 20px 24px;
  transition: box-shadow var(--transition-base), border-color var(--transition-base);
}
.gz-card:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--gray-300);
}
.gz-card-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--gray-500);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin: 0 0 16px 0;
}

/* Stat Cards */
.gz-stat-card {
  background: var(--white);
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  padding: 20px 24px;
  position: relative;
  overflow: hidden;
  transition: all var(--transition-base);
}
.gz-stat-card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}
.gz-stat-card .icon-wrap {
  width: 44px; height: 44px;
  border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px;
  margin-bottom: 12px;
}
.gz-stat-card .stat-label {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--gray-400);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin: 0 0 4px 0;
}
.gz-stat-card .stat-value {
  font-size: var(--font-size-3xl);
  font-weight: 800;
  color: var(--gray-900);
  letter-spacing: -0.03em;
  line-height: 1;
  margin: 0 0 6px 0;
}
.gz-stat-card .stat-delta {
  font-size: var(--font-size-xs);
  font-weight: 500;
  color: var(--gray-400);
}
.gz-stat-card .stat-delta.up { color: var(--success-dark); }
.gz-stat-card .stat-delta.down { color: var(--danger); }
.gz-stat-card .bg-blob {
  position: absolute;
  right: -10px; top: -10px;
  width: 80px; height: 80px;
  border-radius: 50%;
  opacity: 0.07;
}

/* Badges / Status pills */
.gz-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: 600;
  line-height: 1.6;
  white-space: nowrap;
}
.gz-badge-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.gz-badge-success { background: var(--success-light); color: var(--success-dark); }
.gz-badge-success .gz-badge-dot { background: var(--success); }
.gz-badge-warning { background: var(--warning-light); color: var(--warning-dark); }
.gz-badge-warning .gz-badge-dot { background: var(--warning); }
.gz-badge-danger  { background: var(--danger-light);  color: var(--danger-dark); }
.gz-badge-danger  .gz-badge-dot { background: var(--danger); }
.gz-badge-blue    { background: var(--blue-50);  color: var(--blue-700); }
.gz-badge-blue    .gz-badge-dot { background: var(--blue-500); }
.gz-badge-gray    { background: var(--gray-100); color: var(--gray-600); }
.gz-badge-gray    .gz-badge-dot { background: var(--gray-400); }

/* Section divider */
.gz-section-label {
  font-size: var(--font-size-xs);
  font-weight: 700;
  color: var(--gray-400);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin: 24px 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--gray-100);
}

/* Empty state */
.gz-empty {
  text-align: center;
  padding: 48px 24px;
  color: var(--gray-400);
}
.gz-empty-icon { font-size: 40px; margin-bottom: 12px; }
.gz-empty-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--gray-500);
  margin: 0 0 6px 0;
}
.gz-empty-desc {
  font-size: var(--font-size-sm);
  color: var(--gray-400);
  margin: 0;
}

/* Alert banner */
.gz-alert {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 18px;
  border-radius: var(--radius-lg);
  margin-bottom: 16px;
  border: 1px solid transparent;
}
.gz-alert-icon { font-size: 16px; flex-shrink: 0; margin-top: 1px; }
.gz-alert-body { flex: 1; }
.gz-alert-title { font-size: var(--font-size-sm); font-weight: 600; margin: 0 0 2px; }
.gz-alert-desc  { font-size: var(--font-size-sm); margin: 0; opacity: 0.85; }
.gz-alert-warning { background: var(--warning-light); border-color: #fde68a; color: #92400e; }
.gz-alert-danger  { background: var(--danger-light);  border-color: #fecaca; color: #991b1b; }
.gz-alert-success { background: var(--success-light); border-color: #bbf7d0; color: #14532d; }
.gz-alert-info    { background: var(--blue-50);       border-color: var(--blue-200); color: var(--blue-700); }

/* Approval ticket card */
.gz-ticket {
  background: var(--white);
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  margin-bottom: 12px;
  border-left-width: 4px;
  transition: box-shadow var(--transition-base);
}
.gz-ticket:hover { box-shadow: var(--shadow-md); }
.gz-ticket-critical { border-left-color: var(--danger); }
.gz-ticket-high     { border-left-color: var(--warning); }
.gz-ticket-medium   { border-left-color: var(--blue-500); }
.gz-ticket-low      { border-left-color: var(--gray-300); }
.gz-ticket-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}
.gz-ticket-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--gray-800);
  margin: 0;
}
.gz-ticket-desc {
  font-size: var(--font-size-sm);
  color: var(--gray-500);
  margin: 0 0 10px;
}
.gz-ticket-meta {
  font-size: var(--font-size-xs);
  color: var(--gray-400);
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

/* Activity feed */
.gz-activity-item {
  display: flex;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--gray-100);
}
.gz-activity-item:last-child { border-bottom: none; }
.gz-activity-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--blue-500);
  margin-top: 5px;
  flex-shrink: 0;
}
.gz-activity-text {
  font-size: var(--font-size-sm);
  color: var(--gray-600);
  margin: 0 0 2px;
}
.gz-activity-time {
  font-size: var(--font-size-xs);
  color: var(--gray-400);
}

/* Sidebar logo */
.gz-sidebar-logo {
  padding: 20px 16px 12px;
  border-bottom: 1px solid var(--gray-100);
  margin-bottom: 12px;
}
.gz-sidebar-logo-mark {
  display: flex;
  align-items: center;
  gap: 10px;
}
.gz-logo-icon {
  width: 32px; height: 32px;
  background: var(--blue-600);
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px;
  color: white;
  font-weight: 700;
  flex-shrink: 0;
}
.gz-logo-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--gray-900);
  letter-spacing: -0.02em;
}
.gz-logo-sub {
  font-size: 10px;
  color: var(--gray-400);
  font-weight: 500;
  margin-top: 1px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

/* Sidebar user pill */
.gz-sidebar-user {
  margin: 0 8px;
  padding: 10px 12px;
  background: var(--gray-50);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  gap: 10px;
}
.gz-user-avatar {
  width: 30px; height: 30px;
  background: var(--blue-100);
  color: var(--blue-700);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}
.gz-user-name {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--gray-700);
  line-height: 1.2;
}
.gz-user-role {
  font-size: 11px;
  color: var(--gray-400);
}

/* Pending badge */
.gz-pending-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: var(--danger);
  color: white;
  border-radius: var(--radius-full);
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
}

/* Integration source card */
.gz-source-card {
  background: var(--white);
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: all var(--transition-base);
  margin-bottom: 8px;
}
.gz-source-card:hover {
  border-color: var(--blue-200);
  box-shadow: var(--shadow-sm);
}
.gz-source-icon {
  width: 40px; height: 40px;
  border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}
.gz-source-icon-excel  { background: #e8f5e9; }
.gz-source-icon-gsheet { background: var(--blue-50); }
.gz-source-name  { font-size: var(--font-size-base); font-weight: 600; color: var(--gray-800); margin: 0 0 2px; }
.gz-source-meta  { font-size: var(--font-size-xs); color: var(--gray-400); margin: 0; }
.gz-source-right { margin-left: auto; text-align: right; }

/* Mapping table */
.gz-map-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-radius: var(--radius-md);
  background: var(--gray-50);
  margin-bottom: 6px;
  transition: background var(--transition-fast);
}
.gz-map-row:hover { background: var(--blue-50); }
.gz-map-col-name {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--gray-700);
  font-family: var(--font-mono);
  background: var(--white);
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-sm);
  padding: 2px 8px;
  min-width: 140px;
}
.gz-map-arrow { color: var(--gray-400); font-size: 14px; }
.gz-map-confidence {
  font-size: var(--font-size-xs);
  font-weight: 600;
  margin-left: auto;
  padding: 2px 8px;
  border-radius: var(--radius-full);
}
.gz-map-conf-high   { background: var(--success-light); color: var(--success-dark); }
.gz-map-conf-medium { background: var(--warning-light); color: var(--warning-dark); }
.gz-map-conf-low    { background: var(--danger-light);  color: var(--danger-dark); }

/* Scrollbar */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--gray-300); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: var(--gray-400); }
</style>
"""

# ─── Component Functions ──────────────────────────────────────────────────────

def inject_css():
    """Inject the full design system CSS. Call once at app startup."""
    import streamlit as st
    st.markdown(DESIGN_SYSTEM_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", right_content: str = ""):
    import streamlit as st
    right = f'<div>{right_content}</div>' if right_content else ""
    st.markdown(f"""
    <div class="gz-page-header">
      <div>
        <h1 class="gz-page-title">{title}</h1>
        {f'<p class="gz-page-subtitle">{subtitle}</p>' if subtitle else ""}
      </div>
      {right}
    </div>
    """, unsafe_allow_html=True)


def stat_card(label: str, value: str, delta: str = "", icon: str = "📊",
              color: str = "#3b82f6", delta_up: bool = True):
    import streamlit as st
    delta_class = "up" if delta_up else "down"
    delta_html  = f'<p class="stat-delta {delta_class}">{delta}</p>' if delta else ""
    st.markdown(f"""
    <div class="gz-stat-card">
      <div class="icon-wrap" style="background:{color}18;">
        <span style="font-size:20px;">{icon}</span>
      </div>
      <p class="stat-label">{label}</p>
      <p class="stat-value">{value}</p>
      {delta_html}
      <div class="bg-blob" style="background:{color};"></div>
    </div>
    """, unsafe_allow_html=True)


def badge(text: str, variant: str = "gray") -> str:
    """Returns an HTML badge string. variant: success|warning|danger|blue|gray"""
    return f'<span class="gz-badge gz-badge-{variant}"><span class="gz-badge-dot"></span>{text}</span>'


def status_badge(status: str) -> str:
    mapping = {
        "active":      ("Active",      "success"),
        "inactive":    ("Inactive",    "gray"),
        "terminated":  ("Terminated",  "danger"),
        "on_leave":    ("On Leave",    "warning"),
        "probation":   ("Probation",   "blue"),
        "pending":     ("Pending",     "warning"),
        "approved":    ("Approved",    "success"),
        "rejected":    ("Rejected",    "danger"),
        "draft":       ("Draft",       "gray"),
        "paid":        ("Paid",        "success"),
        "synced":      ("Synced",      "success"),
        "error":       ("Error",       "danger"),
        "connected":   ("Connected",   "blue"),
        "never":       ("Never synced","gray"),
    }
    text, variant = mapping.get(status.lower(), (status.title(), "gray"))
    return badge(text, variant)


def section_label(text: str):
    import streamlit as st
    st.markdown(f'<p class="gz-section-label">{text}</p>', unsafe_allow_html=True)


def empty_state(icon: str, title: str, description: str = ""):
    import streamlit as st
    st.markdown(f"""
    <div class="gz-empty">
      <div class="gz-empty-icon">{icon}</div>
      <p class="gz-empty-title">{title}</p>
      {f'<p class="gz-empty-desc">{description}</p>' if description else ""}
    </div>
    """, unsafe_allow_html=True)


def alert(title: str, description: str = "", variant: str = "info", icon: str = None):
    import streamlit as st
    icons = {"info": "ℹ️", "warning": "⚠️", "danger": "🚨", "success": "✅"}
    _icon = icon or icons.get(variant, "ℹ️")
    st.markdown(f"""
    <div class="gz-alert gz-alert-{variant}">
      <span class="gz-alert-icon">{_icon}</span>
      <div class="gz-alert-body">
        <p class="gz-alert-title">{title}</p>
        {f'<p class="gz-alert-desc">{description}</p>' if description else ""}
      </div>
    </div>
    """, unsafe_allow_html=True)


def sidebar_logo():
    import streamlit as st
    st.markdown("""
    <div class="gz-sidebar-logo">
      <div class="gz-sidebar-logo-mark">
        <div class="gz-logo-icon">G</div>
        <div>
          <div class="gz-logo-name">GENZ HR</div>
          <div class="gz-logo-sub">HR Platform</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def sidebar_user(name: str = "Esther", role: str = "HR Authority"):
    import streamlit as st
    initials = "".join(w[0].upper() for w in name.split()[:2])
    st.markdown(f"""
    <div class="gz-sidebar-user">
      <div class="gz-user-avatar">{initials}</div>
      <div>
        <div class="gz-user-name">{name}</div>
        <div class="gz-user-role">{role}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def ticket_card(label: str, description: str, risk: str,
                ticket_id: str, requested_by: str, created_at: str):
    import streamlit as st
    risk_variants = {"critical": "danger", "high": "warning", "medium": "blue", "low": "gray"}
    badge_html = badge(risk.title(), risk_variants.get(risk, "gray"))
    st.markdown(f"""
    <div class="gz-ticket gz-ticket-{risk}">
      <div class="gz-ticket-header">
        <p class="gz-ticket-title">{label}</p>
        {badge_html}
      </div>
      <p class="gz-ticket-desc">{description}</p>
      <div class="gz-ticket-meta">
        <span>🎫 {ticket_id}</span>
        <span>👤 {requested_by}</span>
        <span>🕐 {created_at}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)


def source_card(name: str, source_type: str, status: str,
                last_synced: str, row_count: int):
    import streamlit as st
    icon = "📊" if source_type == "excel" else "🔗"
    icon_class = "gz-source-icon-excel" if source_type == "excel" else "gz-source-icon-gsheet"
    type_label = "Excel / CSV" if source_type == "excel" else "Google Sheets"
    badge_html = status_badge(status)
    st.markdown(f"""
    <div class="gz-source-card">
      <div class="gz-source-icon {icon_class}">{icon}</div>
      <div style="flex:1;">
        <p class="gz-source-name">{name}</p>
        <p class="gz-source-meta">{type_label} · {row_count:,} rows</p>
      </div>
      <div class="gz-source-right">
        {badge_html}
        <p style="font-size:11px;color:var(--gray-400);margin:4px 0 0;text-align:right;">
          {f"Last sync: {last_synced}" if last_synced else "Never synced"}
        </p>
      </div>
    </div>
    """, unsafe_allow_html=True)


def mapping_row(sheet_col: str, system_field: str, label: str, confidence: float):
    import streamlit as st
    if confidence >= 0.85:
        conf_class, conf_text = "gz-map-conf-high",   f"{confidence*100:.0f}%"
    elif confidence >= 0.6:
        conf_class, conf_text = "gz-map-conf-medium", f"{confidence*100:.0f}%"
    else:
        conf_class, conf_text = "gz-map-conf-low",    "Review"

    mapped_to = label or system_field or "— unmapped —"
    st.markdown(f"""
    <div class="gz-map-row">
      <code class="gz-map-col-name">{sheet_col}</code>
      <span class="gz-map-arrow">→</span>
      <span style="font-size:13px;color:var(--gray-700);font-weight:500;">{mapped_to}</span>
      <span class="gz-map-confidence {conf_class}">{conf_text}</span>
    </div>
    """, unsafe_allow_html=True)


def card(content_fn, title: str = "", padding: str = "20px 24px"):
    """Wrap a Streamlit content function in a white card."""
    import streamlit as st
    st.markdown(f"""
    <div class="gz-card" style="padding:{padding}">
      {f'<p class="gz-card-title">{title}</p>' if title else ""}
    """, unsafe_allow_html=True)
    content_fn()
    st.markdown("</div>", unsafe_allow_html=True)
