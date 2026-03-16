# GENZ HR — AI-Powered HR Automation Platform

**Version:** 1.0.0  
**Human Authority:** Esther (eonwuanumba@gmail.com)  
**Max Companies:** 20  
**Deployment:** Local (offline-first)

---

## What is GENZ HR?

GENZ HR is an autonomous AI HR platform powered by GENZ agents — a team of specialized AI workers that manage HR operations for up to 20 Nigerian startups simultaneously. Each company gets its own dedicated GENZ Agent while a central GENZ Director coordinates all activity and reports to Esther.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install Ollama & pull model
ollama pull llama3.1

# 3. Initialize database
python scripts/init_db.py

# 4. Onboard a company
python scripts/onboard_company.py --name "Acme Corp" --id "company_a"

# 5. Launch dashboard
streamlit run frontend/dashboard.py

# 6. Launch API
uvicorn backend.main:app --reload --port 8000
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     ESTHER (Human Authority)                 │
│                   eonwuanumba@gmail.com                      │
└──────────────────────────┬──────────────────────────────────┘
                           │ Reviews / Approves / Edits
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  GENZ DIRECTOR (Central AI)                  │
│        Aggregates insights · Sends alerts · Coordinates     │
└──────┬────────┬────────┬────────┬────────┬──────────────────┘
       │        │        │        │        │
       ▼        ▼        ▼        ▼        ▼
  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ... (up to 20)
  │ GENZ   │ │ GENZ   │ │ GENZ   │ │ GENZ   │
  │Agent A │ │Agent B │ │Agent C │ │Agent D │
  └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘
      │          │          │          │
      ▼          ▼          ▼          ▼
  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
  │Company │ │Company │ │Company │ │Company │
  │  A DB  │ │  B DB  │ │  C DB  │ │  D DB  │
  └────────┘ └────────┘ └────────┘ └────────┘
```

---

## Folder Structure

```
genz-hr/
├── backend/
│   ├── main.py                    # FastAPI entry point
│   ├── api/
│   │   ├── routes_auth.py
│   │   ├── routes_companies.py
│   │   ├── routes_employees.py
│   │   ├── routes_recruitment.py
│   │   ├── routes_payroll.py
│   │   ├── routes_performance.py
│   │   ├── routes_attendance.py
│   │   ├── routes_templates.py
│   │   └── routes_audit.py
│   ├── agents/
│   │   ├── genz_director.py       # Central AI Director
│   │   ├── genz_agent.py          # Per-company HR Agent
│   │   ├── agent_recruitment.py
│   │   ├── agent_payroll.py
│   │   ├── agent_performance.py
│   │   └── agent_attendance.py
│   ├── core/
│   │   ├── database.py            # DB connection manager
│   │   ├── isolation.py           # Company data isolation
│   │   ├── llm.py                 # Ollama LLM wrapper
│   │   └── config.py
│   ├── modules/
│   │   ├── payroll_engine.py      # Nigerian PAYE calculator
│   │   ├── cv_parser.py           # CV extraction
│   │   ├── template_engine.py     # Template rendering
│   │   ├── pdf_generator.py       # PDF generation
│   │   └── audit_logger.py        # Immutable audit logs
│   └── utils/
│       ├── email_sender.py
│       └── validators.py
├── frontend/
│   └── dashboard.py               # Streamlit dashboard
├── companies/                     # Isolated company data
│   └── .gitkeep
├── scripts/
│   ├── init_db.py
│   └── onboard_company.py
├── requirements.txt
└── README.md
```

---

## Nigerian Labor Law Compliance

- **PAYE**: Nigeria Tax Act 2025 — effective 1 January 2026
  - ₦0–₦800,000: 0% (tax-free)
  - ₦800,001–₦3,000,000: 15%
  - ₦3,000,001–₦12,000,000: 18%
  - ₦12,000,001–₦25,000,000: 21%
  - ₦25,000,001–₦50,000,000: 23%
  - Above ₦50,000,000: 25%
  - CRA **removed**; new rent relief (20% of annual rent, max ₦500,000)
- **Pension**: PRA 2014 — Employee 8%, Employer 10%
- **NHF**: NHF Act — 2.5% of basic salary (employees earning ≥ ₦3,000/month)
- **Leave**: Minimum 6 working days annual leave
- **Notice**: Minimum 1 month notice for employees > 3 months tenure
