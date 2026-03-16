# GENZ HR — Complete Technical Blueprint

## Database Schema (Per Company)

```sql
-- employees
CREATE TABLE employees (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id     TEXT UNIQUE NOT NULL,       -- EMP-001
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    email           TEXT UNIQUE,
    phone           TEXT,
    department      TEXT,
    position        TEXT,
    employment_type TEXT,                       -- full-time / contract
    status          TEXT DEFAULT 'active',      -- active/on_leave/probation/terminated
    start_date      DATE,
    end_date        DATE,
    gross_salary    REAL DEFAULT 0.0,
    bank_name       TEXT,
    account_number  TEXT,
    pension_pin     TEXT,
    tax_id          TEXT,
    manager_id      INTEGER REFERENCES employees(id),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- candidates
CREATE TABLE candidates (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    name                  TEXT NOT NULL,
    email                 TEXT,
    phone                 TEXT,
    position_applied      TEXT,
    cv_path               TEXT,
    raw_cv_text           TEXT,
    education_score       REAL DEFAULT 0.0,
    skills_score          REAL DEFAULT 0.0,
    experience_score      REAL DEFAULT 0.0,
    keyword_score         REAL DEFAULT 0.0,
    total_score           REAL DEFAULT 0.0,
    rank                  INTEGER,
    shortlisted           BOOLEAN DEFAULT 0,
    interview_status      TEXT DEFAULT 'pending',
    interview_notes       TEXT,
    ai_summary            TEXT,
    esther_override_score REAL,
    applied_at            DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- task_sheets
CREATE TABLE task_sheets (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id      INTEGER REFERENCES employees(id),
    period           TEXT,                      -- "2024-W01" or "2024-06"
    period_type      TEXT,                      -- weekly / monthly
    tasks            JSON,
    completion_pct   REAL DEFAULT 0.0,
    performance_score REAL,
    lead_feedback    TEXT,
    ai_analysis      TEXT,
    bonus_eligible   BOOLEAN DEFAULT 0,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    submitted_at     DATETIME
);

-- attendance
CREATE TABLE attendance (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id           INTEGER REFERENCES employees(id),
    date                  DATE NOT NULL,
    check_in              DATETIME,
    check_out             DATETIME,
    task_activity_score   REAL DEFAULT 0.0,
    comms_activity_score  REAL DEFAULT 0.0,
    meeting_score         REAL DEFAULT 0.0,
    presence_score        REAL DEFAULT 0.0,
    is_absent             BOOLEAN DEFAULT 0,
    is_approved_leave     BOOLEAN DEFAULT 0,
    notes                 TEXT
);

-- payroll
CREATE TABLE payroll (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id         INTEGER REFERENCES employees(id),
    period              TEXT,
    gross_salary        REAL,
    basic_salary        REAL,
    housing_allowance   REAL DEFAULT 0.0,
    transport_allowance REAL DEFAULT 0.0,
    other_allowances    REAL DEFAULT 0.0,
    paye_tax            REAL,
    pension_employee    REAL,
    pension_employer    REAL,
    nhf_deduction       REAL,
    other_deductions    REAL DEFAULT 0.0,
    performance_bonus   REAL DEFAULT 0.0,
    net_salary          REAL,
    status              TEXT DEFAULT 'draft',
    anomaly_flag        BOOLEAN DEFAULT 0,
    anomaly_reason      TEXT,
    approved_by         TEXT,
    approved_at         DATETIME,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- audit_logs
CREATE TABLE audit_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user         TEXT NOT NULL,
    action       TEXT NOT NULL,
    module       TEXT,
    record_type  TEXT,
    record_id    TEXT,
    field_changed TEXT,
    old_value    TEXT,
    new_value    TEXT,
    ip_address   TEXT
);
```

---

## Master Database Schema

```sql
-- company_registry (NO employee data here)
CREATE TABLE company_registry (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    industry        TEXT,
    size            TEXT,
    contact_email   TEXT,
    is_active       BOOLEAN DEFAULT 1,
    onboarded_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    agent_status    TEXT DEFAULT 'idle',
    last_summary_at DATETIME
);
```

---

## GENZ Agent Autonomy Scope

| Task | Autonomous | Requires Esther |
|------|-----------|-----------------|
| CV scoring | ✅ | Score overrides |
| Candidate shortlisting | ✅ auto (≥60) | Manual shortlist changes |
| Payroll calculation | ✅ | Approval before payment |
| Payroll edit | ❌ | Esther only |
| Attendance flagging | ✅ | — |
| Task sheet generation | ✅ | Score assignment |
| Performance scoring | Team lead | Esther can override |
| Contract generation | ✅ draft | Esther signs off |
| Policy generation | ✅ draft | Esther reviews |
| Employee termination | ❌ | Esther only |

---

## Nigerian PAYE Quick Reference — Nigeria Tax Act 2025 (effective 1 Jan 2026)

| Annual Taxable Income | Rate | Notes |
|----------------------|------|-------|
| ₦0 – ₦800,000 | **0%** | Tax-free band (major relief for low earners) |
| ₦800,001 – ₦3,000,000 | 15% | |
| ₦3,000,001 – ₦12,000,000 | 18% | |
| ₦12,000,001 – ₦25,000,000 | 21% | |
| ₦25,000,001 – ₦50,000,000 | 23% | |
| Above ₦50,000,000 | 25% | |

**Key 2026 changes:**
- CRA (Consolidated Relief Allowance) **removed**
- ₦800,000 tax-free threshold replaces old 7% first band
- New **rent relief**: 20% of annual rent, capped at ₦500,000/year
- Pension (8% employee) and NHF (2.5% basic) still reduce gross before PAYE

**Example (from the law):** Annual income = ₦2,000,000
- First ₦800,000 → ₦0
- Next ₦1,200,000 × 15% → ₦180,000
- **Total PAYE = ₦180,000/year = ₦15,000/month**

---

## API Endpoints Reference

```
GET    /api/platform/stats
GET    /api/platform/daily-summary

POST   /api/companies/register
GET    /api/companies/{id}/report

GET    /api/companies/{id}/employees
POST   /api/companies/{id}/employees
PATCH  /api/companies/{id}/employees/{emp_id}

POST   /api/companies/{id}/recruitment/upload-cv
GET    /api/companies/{id}/recruitment/candidates
PATCH  /api/companies/{id}/recruitment/candidates/{cid}/override

POST   /api/companies/{id}/payroll/prepare/{period}
GET    /api/companies/{id}/payroll/{period}
POST   /api/companies/{id}/payroll/{pid}/approve
PATCH  /api/companies/{id}/payroll/{pid}

GET    /api/companies/{id}/audit-logs
GET    /api/companies/{id}/templates
POST   /api/companies/{id}/templates/{type}/render
```
