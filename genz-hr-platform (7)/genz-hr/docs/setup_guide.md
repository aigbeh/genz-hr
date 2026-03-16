# GENZ HR — Complete Setup Guide
# Step-by-step instructions to get GENZ HR running on your laptop

## Prerequisites

- Python 3.11+
- 8GB RAM minimum (16GB recommended for running Ollama LLM)
- macOS, Linux, or Windows with WSL2

---

## Step 1: Install Ollama (Local LLM)

Ollama powers all AI features and runs entirely offline.

### macOS / Linux
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

### Windows
Download from: https://ollama.ai/download

### Pull the AI model
```bash
# Start Ollama
ollama serve

# In a new terminal, pull the model (downloads ~4.7GB once)
ollama pull llama3.1

# Verify it works
ollama run llama3.1 "Hello, can you help me with HR tasks?"
```

---

## Step 2: Clone / Setup Project

```bash
# Create project folder
mkdir genz-hr && cd genz-hr

# Copy all the provided code files into their correct paths
# (see folder structure in README.md)

# Create virtual environment
python -m venv venv

# Activate virtual environment
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Step 3: Initialize the Platform

```bash
# Initialize master database
python scripts/init_db.py

# You should see:
# ✓ Companies directory created
# ✓ Master database initialized
# Platform Ready
```

---

## Step 4: Register Your First Companies

```bash
# Register company 1
python scripts/onboard_company.py \
  --id "acme_corp" \
  --name "Acme Corporation" \
  --industry "Technology" \
  --size "startup" \
  --email "hr@acmecorp.ng"

# Register company 2
python scripts/onboard_company.py \
  --id "nova_finance" \
  --name "Nova Finance Ltd" \
  --industry "Fintech" \
  --size "sme"

# Register up to 20 companies this way
```

Each company gets:
- An isolated SQLite database at `companies/{id}/hr_data.db`
- Its own GENZ Agent
- Separate templates, policies, uploads, reports folders

---

## Step 5: Start the API Server

```bash
# Start FastAPI backend (keep this terminal open)
uvicorn backend.main:app --reload --port 8000

# API docs available at: http://localhost:8000/docs
# Health check: http://localhost:8000/health
```

---

## Step 6: Launch the Dashboard

```bash
# In a new terminal (with venv activated)
streamlit run frontend/dashboard.py

# Dashboard opens at: http://localhost:8501
# Login as: Esther
```

---

## Step 7: Test the System

### Add an employee
1. Open dashboard → Select company → 👥 Employees
2. Click "Add Employee" tab
3. Fill in employee details
4. Click "Add Employee"

### Run payroll
1. Dashboard → 💰 Payroll
2. Enter pay period (e.g., `2024-06`)
3. Click "Prepare Payroll"
4. Review the computed figures
5. Click "Approve All Records"

### Upload a CV
1. Dashboard → 📋 Recruitment
2. Click "Upload CV" tab
3. Enter position name
4. Upload PDF/DOCX
5. GENZ Agent scores it instantly

### Run daily cycle
1. Dashboard → 🏠 Overview
2. Click "Run GENZ Director Now"
3. View aggregated company reports

---

## Step 8: Configure Automatic Scheduling (Optional)

Add the scheduler to your API startup:

```python
# In backend/main.py, update the lifespan function:

@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.core.scheduler import scheduler
    init_master_db()
    scheduler.start()  # <-- Add this line
    yield
    scheduler.shutdown()
    director.shutdown()
```

The scheduler will:
- Run daily HR cycle at 8:00 AM (Nigeria time)
- Prepare payroll on the 25th of each month
- Send alerts to Esther's email

---

## Step 9: Enable Email Notifications (Optional)

Edit `backend/core/scheduler.py`:

```python
def _notify_esther(subject: str, body: str):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = "noreply@yourcompany.ng"
    msg["To"] = "eonwuanumba@gmail.com"
    msg.attach(MIMEText(body, "plain"))
    
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login("YOUR_GMAIL", "YOUR_APP_PASSWORD")
        server.sendmail(msg["From"], msg["To"], msg.as_string())
```

For Gmail: Create an App Password at https://myaccount.google.com/apppasswords

---

## Running Everything at Once

Create a `start.sh` script:

```bash
#!/bin/bash
echo "Starting GENZ HR Platform..."

# Start Ollama (if not running)
ollama serve &

# Wait for Ollama
sleep 3

# Start API in background
uvicorn backend.main:app --port 8000 &

# Start dashboard
streamlit run frontend/dashboard.py --server.port 8501

echo "GENZ HR is running!"
echo "Dashboard: http://localhost:8501"
echo "API:       http://localhost:8000"
```

```bash
chmod +x start.sh && ./start.sh
```

---

## Troubleshooting

### "Ollama not available"
```bash
# Start Ollama
ollama serve
# Check it's running
curl http://localhost:11434/api/tags
```

### "Database locked" error
```bash
# Kill any stuck processes
pkill -f uvicorn
pkill -f streamlit
# Restart
```

### Module not found errors
```bash
# Make sure you're in project root with venv activated
cd genz-hr
source venv/bin/activate
python -m backend.main  # test imports
```

### Reset a company's data
```bash
# Delete company folder (WARNING: deletes all data)
rm -rf companies/company_id/
# Re-register
python scripts/onboard_company.py --id "company_id" --name "Company Name"
```

---

## Production Hardening (Future)

When ready to move beyond local laptop:

1. **Replace SQLite → PostgreSQL** per company (update `get_company_db_url()`)
2. **Add authentication** (JWT tokens on FastAPI routes)
3. **Containerize** with Docker Compose (one container per company agent)
4. **Add SSL** via Nginx reverse proxy
5. **Backup** the `companies/` folder daily
