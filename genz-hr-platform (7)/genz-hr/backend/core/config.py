"""
GENZ HR — Core Configuration
"""
import os
from pathlib import Path
from dataclasses import dataclass, field


BASE_DIR      = Path(__file__).resolve().parent.parent.parent
COMPANIES_DIR = BASE_DIR / "companies"
COMPANIES_DIR.mkdir(exist_ok=True)


@dataclass
class Settings:
    # App
    APP_NAME:     str = "GENZ HR"
    VERSION:      str = "1.0.0"
    SECRET_KEY:   str = "genz-hr-secret-change-in-production"
    ESTHER_EMAIL: str = "eonwuanumba@gmail.com"

    # Ollama / LLM
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL:    str = "llama3.1"

    # Database (master)
    MASTER_DB_URL: str = field(default_factory=lambda: f"sqlite:///{BASE_DIR}/genz_master.db")

    # Limits
    MAX_COMPANIES: int = 20

    # Scheduler
    DAILY_SUMMARY_HOUR: int = 8   # 8 AM daily
    PAYROLL_CHECK_DAY:  int = 25  # 25th of each month

    def __post_init__(self):
        # Allow .env overrides via environment variables
        for attr in self.__dataclass_fields__:
            env_val = os.getenv(attr.upper())
            if env_val is not None:
                setattr(self, attr, type(getattr(self, attr))(env_val))


settings = Settings()


def get_company_dir(company_id: str) -> Path:
    """Return isolated directory for a company."""
    path = COMPANIES_DIR / company_id
    path.mkdir(parents=True, exist_ok=True)
    (path / "templates").mkdir(exist_ok=True)
    (path / "policies").mkdir(exist_ok=True)
    (path / "uploads").mkdir(exist_ok=True)
    (path / "reports").mkdir(exist_ok=True)
    return path


def get_company_db_url(company_id: str) -> str:
    """Return isolated SQLite DB path for a company."""
    db_path = get_company_dir(company_id) / "hr_data.db"
    return f"sqlite:///{db_path}"
