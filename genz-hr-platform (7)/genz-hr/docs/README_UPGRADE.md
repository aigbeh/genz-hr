# GENZ HR v1.1.0 — Upgrade Documentation
## Data Integration Layer: Excel + Google Sheets

---

## What's New in v1.1.0

| Feature | Description |
|---|---|
| Excel / CSV Upload | Upload `.xlsx`, `.xls`, `.xlsm`, `.csv` files directly in the dashboard |
| Google Sheets Sync | Connect a live Google Sheet with automatic change detection |
| Smart Column Mapping | AI-assisted column detection with fuzzy matching and alias dictionary |
| Delta Sync | Only re-imports changed rows — skips unchanged data |
| Batch Processing | 1000+ row sheets processed in batches without blocking the UI |
| Sync Logging | Every import event logged with row counts, errors, and timing |
| Duplicate Prevention | Upsert logic — updates existing employees, never creates duplicates |
| Data Integrations Page | New dashboard page: `🔗 Data Integrations` |

---

## New Files Added

```
backend/
  core/
    integration_models.py   ← DataSource, ColumnMapping, SyncLog DB models
  modules/
    column_mapper.py        ← Smart column mapping engine (fuzzy + alias)
    data_ingestion.py       ← Excel/CSV reader, type coercion, upsert logic
    gsheets_connector.py    ← Google Sheets API v4 connector
    integration_manager.py  ← Orchestrates full sync lifecycle
frontend/
  integrations_page.py      ← Complete Data Integrations UI page
docs/
  README_UPGRADE.md         ← This file
```

**Modified files** (backward compatible — no existing features removed):
- `backend/core/database.py` — integration models auto-created in company DBs
- `backend/main.py` — 8 new API endpoints under `/api/companies/{id}/integrations/`
- `frontend/dashboard.py` — new `🔗 Data Integrations` nav item added
- `requirements.txt` — Google Sheets API packages added

---

## How Excel Uploads Work

### Step 1 — Upload
Navigate to `🔗 Data Integrations` → `📂 Upload Excel / CSV`.
Select your file. Supported formats: `.xlsx`, `.xls`, `.xlsm`, `.csv`.

### Step 2 — Column Analysis
Click **Analyse Columns**. The system reads your headers and proposes mappings:

```
Your Column      →  GENZ HR Field          Module      Confidence
─────────────────────────────────────────────────────────────────
Employee Name    →  full_name              employees   100%  🎯
dept             →  department             employees    95%  📘
Gross Salary     →  gross_salary           payroll     100%  🎯
start            →  start_date             employees    78%  🔍 ⚠
Bank Acct        →  account_number         employees    71%  🔍 ⚠
```

- 🎯 **Exact** — perfect column name match
- 📘 **Alias** — recognised abbreviation (e.g. `dept` → `department`)
- 🔍 **Fuzzy** — close enough (you should confirm)
- ⚠ **Needs review** — confidence below 80%, dropdown shown for you to correct

### Step 3 — Confirm & Import
Review any flagged columns using the dropdowns, then click **Confirm & Import Now**.

The system:
1. Saves your mappings permanently for this source
2. Processes all rows in batches of 100
3. Upserts each employee (update if exists, insert if new)
4. Shows you a summary: `✅ 47 new · 📝 12 updated · ❌ 0 errors`

### Re-uploading a new version
Upload a new version of the same file. The system detects the change (SHA256 hash
comparison), imports only changed rows, and logs the delta.

---

## How Google Sheets Sync Works

### Prerequisites
Set up Google API credentials (one-time, ~5 minutes):

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable the **Google Sheets API**
4. Go to **IAM & Admin → Service Accounts**
5. Create a service account, download the JSON credentials file
6. **Share your Google Sheet** with the service account email address
   (it looks like `something@your-project.iam.gserviceaccount.com`)
7. Give it **Viewer** access

### Configure GENZ HR

Add to your `.env` file:
```
GOOGLE_CREDENTIALS_PATH=/path/to/your/credentials.json
```

Or set the environment variable:
```bash
export GOOGLE_CREDENTIALS_PATH=/path/to/your/credentials.json
```

### Connect a Sheet

1. Navigate to `🔗 Data Integrations` → `🔗 Google Sheets`
2. Paste your Google Sheet URL:
   ```
   https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit#gid=0
   ```
3. Optionally specify a tab name (e.g. `Employees`)
4. Choose auto-sync interval: Every 15 min / Hourly / Every 6 hours / Daily / Manual
5. Click **Connect & Analyse**

### How Auto-Sync Works

The APScheduler background worker checks every connected Google Sheet at the
configured interval:

```
Scheduler wakes up
    ↓
Reads sheet from Google API
    ↓
Computes SHA256 hash of all rows
    ↓
Compares to stored hash from last sync
    ↓
Hash unchanged? → Skip (log: "no changes")
Hash changed?   → Delta import (only process changed rows)
                → Update stored hash
                → Log sync event with counts
```

The scheduler is pre-wired at `8:00 AM WAT` for daily summaries and additionally
calls `run_auto_syncs()` for any sheets with `auto_sync=True`.

### Manual Sync
In `📋 Active Sources`, click **🔄 Sync Now** next to any source to force an immediate sync.

---

## How Column Mapping Works

### Mapping Priority

```
1. EXACT match         "gross_salary"   → gross_salary   (100%)
2. ALIAS lookup        "salary"         → gross_salary    (95%)
                       "dept"           → department
                       "emp_name"       → full_name
                       "tin"            → tax_id
3. FUZZY match         "Gross Salary"   → gross_salary    (87%)
                       "Start Dt"       → start_date      (74%) ⚠
4. No match            "ref_code"       → unmapped         (0%) ⚠
```

### Alias Dictionary Coverage

The built-in alias dictionary covers common Nigerian HR column naming:

| Your Column | Maps To |
|---|---|
| `emp_name`, `staff_name`, `worker_name` | `full_name` |
| `dept`, `team`, `division`, `unit` | `department` |
| `salary`, `pay`, `gross`, `ctc`, `remuneration` | `gross_salary` |
| `date_joined`, `hire_date`, `commencement` | `start_date` |
| `tin`, `tax`, `taxpayer_id` | `tax_id` |
| `pfa`, `rsa`, `pension` | `pension_pin` |
| `bank`, `bank_details` | `bank_name` |
| `account`, `account_no`, `acct`, `nuban` | `account_number` |
| `mobile`, `tel`, `contact` | `phone` |

### Adding Custom Aliases
Edit `ALIASES` dict in `backend/modules/column_mapper.py`:
```python
ALIASES: dict[str, str] = {
    # Add your own:
    "my_column_name": "system_field",
    "staff_identifier": "employee_id",
}
```

### Saving Mappings
Once confirmed, mappings are stored in the `column_mappings` table per data source.
The same mapping is reused every time that source syncs — you only configure once.

---

## Upsert / Duplicate Safety

The system **never creates duplicate employees**. For each row, it searches in order:

1. Match on `employee_id` (if column mapped)
2. Match on `email` (if column mapped)
3. Match on `first_name` + `last_name`

If a match is found → **update** only changed fields.
If no match → **insert** new employee.

This means you can safely re-upload the same sheet multiple times — unchanged rows
are a no-op (counted as `skipped`).

---

## Batch Processing (Large Sheets)

Sheets with 1,000+ rows are processed in batches of 100 rows:

```python
BATCH_SIZE = 100  # configurable in data_ingestion.py

for batch in chunks(rows, BATCH_SIZE):
    process_batch(batch)   # transform + upsert
    session.commit()       # commit each batch
    log_progress()
```

Each batch is committed independently. If a batch fails, previous batches are
preserved — the error is logged and processing continues with the next batch.

The dashboard shows a spinner during import and displays the final summary.
For very large files (10,000+ rows), consider running the sync via the API
endpoint rather than the dashboard upload.

---

## API Reference (New Endpoints)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/companies/{id}/integrations` | List all data sources |
| `POST` | `/api/companies/{id}/integrations/excel` | Upload Excel/CSV file |
| `POST` | `/api/companies/{id}/integrations/gsheet` | Connect Google Sheet |
| `POST` | `/api/companies/{id}/integrations/{sid}/mappings` | Confirm column mappings |
| `POST` | `/api/companies/{id}/integrations/{sid}/sync` | Trigger manual sync |
| `GET` | `/api/companies/{id}/integrations/{sid}/history` | Sync history |
| `GET` | `/api/companies/{id}/integrations/{sid}/mappings` | View saved mappings |
| `DELETE` | `/api/companies/{id}/integrations/{sid}` | Remove data source |

---

## Database Tables Added (per company DB)

### `data_sources`
One row per registered source (Excel file or Google Sheet).
Stores file path / sheet URL, status, last sync time, row count.

### `column_mappings`
One row per confirmed mapping. Reused on every sync.

### `sync_logs`
Immutable log of every sync event. Records row counts, errors, duration.
Retained permanently for audit trail.

---

## Configuration Reference

Add to `.env`:

```env
# Google Sheets (optional)
GOOGLE_CREDENTIALS_PATH=/path/to/service-account-credentials.json

# Sync batch size (optional, default=100)
IMPORT_BATCH_SIZE=100
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "google-api-python-client not installed" | `pip install google-api-python-client google-auth` |
| "Credentials file not found" | Check `GOOGLE_CREDENTIALS_PATH` in `.env` |
| "Permission denied" on sheet | Share sheet with the service account email |
| Import stops mid-way | Check `sync_logs` table for batch errors; previous batches committed |
| Duplicate employees appearing | Ensure `employee_id` or `email` column is mapped as a key field |
| Date parsing fails | Ensure dates are in `YYYY-MM-DD`, `DD/MM/YYYY`, or `DD-Mon-YYYY` format |
| "No column mappings configured" | Complete the mapping step before clicking Sync |

---

*GENZ HR v1.1.0 — Built for Esther · Nigerian Labor Law Compliant · All rights reserved*
