"""
GENZ HR — Google Sheets Connector (top-level)
Top-level module that re-exports from integrations/ and adds
utility functions used by integration_manager.py.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Optional

import pandas as pd

logger = logging.getLogger("genz.gsheets")


def extract_sheet_id(url: str) -> str:
    """Extract the Sheet ID from a Google Sheets URL."""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    # Might be a raw ID already
    if re.match(r"^[a-zA-Z0-9_-]{20,}$", url.strip()):
        return url.strip()
    raise ValueError(f"Cannot extract Sheet ID from: {url}")


def is_configured(credentials_path: Optional[str] = None) -> bool:
    """Return True if Google credentials are available."""
    candidates = [
        credentials_path or "",
        os.environ.get("GOOGLE_CREDENTIALS_PATH", ""),
        "service_account.json",
        "credentials/service_account.json",
    ]
    return any(c and os.path.exists(c) for c in candidates)


def _find_credentials(credentials_path: Optional[str] = None) -> Optional[str]:
    candidates = [
        credentials_path or "",
        os.environ.get("GOOGLE_CREDENTIALS_PATH", ""),
        "service_account.json",
        "credentials/service_account.json",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def read_sheet(
    sheet_id: str,
    tab_name: Optional[str] = None,
    credentials_path: Optional[str] = None,
) -> tuple[list[str], list[dict]]:
    """
    Fetch a Google Sheet and return (headers, rows).
    Requires gspread + google-auth installed and credentials configured.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        raise ImportError("Run: pip install gspread google-auth")

    creds_path = _find_credentials(credentials_path)
    if not creds_path:
        raise FileNotFoundError(
            "Google credentials not found. "
            "Set GOOGLE_CREDENTIALS_PATH=path/to/service_account.json in .env"
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds  = Credentials.from_service_account_file(creds_path, scopes=scopes)
    client = gspread.authorize(creds)

    workbook = client.open_by_key(sheet_id)
    sheet    = workbook.worksheet(tab_name) if tab_name else workbook.get_worksheet(0)
    records  = sheet.get_all_records(default_blank="")

    if not records:
        return [], []

    df      = pd.DataFrame(records).astype(str).fillna("")
    headers = list(df.columns)
    rows    = df.to_dict(orient="records")
    return headers, rows


def read_sheet_mock(tab_name: Optional[str] = None) -> tuple[list[str], list[dict]]:
    """
    Return a small mock dataset when Google credentials are not configured.
    Used in demo mode so the UI can show mapping previews.
    """
    headers = [
        "Employee Name", "Department", "Position", "Salary",
        "Start Date", "Email", "Phone", "Bank", "Account Number",
    ]
    rows = [
        {
            "Employee Name": "Chidi Okonkwo",  "Department": "Engineering",
            "Position": "Senior Engineer",      "Salary": "650000",
            "Start Date": "2023-01-15",          "Email": "chidi@demo.ng",
            "Phone": "08012345678",              "Bank": "GTBank",
            "Account Number": "0123456789",
        },
        {
            "Employee Name": "Amara Nwosu",    "Department": "Product",
            "Position": "Product Manager",      "Salary": "850000",
            "Start Date": "2022-06-01",          "Email": "amara@demo.ng",
            "Phone": "08098765432",              "Bank": "Access Bank",
            "Account Number": "0987654321",
        },
    ]
    return headers, rows


def detect_changes(
    sheet_id:         str,
    last_hash:        Optional[str],
    tab_name:         Optional[str] = None,
    credentials_path: Optional[str] = None,
) -> tuple[bool, str, list[str], list[dict]]:
    """
    Fetch sheet and compare hash to last known state.
    Returns (has_changed, new_hash, headers, rows).
    """
    headers, rows = read_sheet(sheet_id, tab_name, credentials_path)
    new_hash      = hashlib.sha256(
        json.dumps(rows, sort_keys=True, default=str).encode()
    ).hexdigest()
    has_changed   = (last_hash is None) or (new_hash != last_hash)
    return has_changed, new_hash, headers, rows


def compute_data_hash(rows: list[dict]) -> str:
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, default=str).encode()
    ).hexdigest()
