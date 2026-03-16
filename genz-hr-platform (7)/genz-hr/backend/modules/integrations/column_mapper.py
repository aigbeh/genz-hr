"""
GENZ HR — Smart Column Mapper
═══════════════════════════════════════════════════════════════
Automatically maps spreadsheet column names to GENZ HR fields.

Logic:
  1. Exact match  → confidence 1.0
  2. Normalised match (lowercase, strip punctuation) → 0.9
  3. Alias lookup (known synonyms) → 0.85
  4. Fuzzy substring match → 0.6–0.8
  5. No match → confidence 0.0, flagged for manual mapping

Every mapping decision is logged.
Esther can override any auto-mapping from the Data Integrations UI.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("genz.mapper")

# ─── Canonical HR Fields ──────────────────────────────────────────────────────
# Maps system_field → (module, description, required)

HR_FIELDS: dict[str, dict] = {
    # Employee core
    "employee_id":       {"module": "employees", "label": "Employee ID",       "required": False},
    "first_name":        {"module": "employees", "label": "First Name",         "required": True},
    "last_name":         {"module": "employees", "label": "Last Name",          "required": True},
    "full_name":         {"module": "employees", "label": "Full Name",          "required": False},  # split on import
    "email":             {"module": "employees", "label": "Email",              "required": False},
    "phone":             {"module": "employees", "label": "Phone",              "required": False},
    "department":        {"module": "employees", "label": "Department",         "required": False},
    "position":          {"module": "employees", "label": "Job Title / Position","required": False},
    "employment_type":   {"module": "employees", "label": "Employment Type",    "required": False},
    "start_date":        {"module": "employees", "label": "Start Date",         "required": False},
    "end_date":          {"module": "employees", "label": "End Date",           "required": False},
    "status":            {"module": "employees", "label": "Employment Status",  "required": False},
    "bank_name":         {"module": "employees", "label": "Bank Name",          "required": False},
    "account_number":    {"module": "employees", "label": "Bank Account Number","required": False},
    "pension_pin":       {"module": "employees", "label": "Pension PIN",        "required": False},
    "tax_id":            {"module": "employees", "label": "Tax ID (TIN)",       "required": False},

    # Payroll
    "gross_salary":      {"module": "payroll",   "label": "Gross Salary (₦/mo)","required": False},
    "basic_salary":      {"module": "payroll",   "label": "Basic Salary",       "required": False},
    "housing_allowance": {"module": "payroll",   "label": "Housing Allowance",  "required": False},
    "transport_allowance":{"module":"payroll",   "label": "Transport Allowance","required": False},
    "other_allowances":  {"module": "payroll",   "label": "Other Allowances",   "required": False},
    "performance_bonus": {"module": "payroll",   "label": "Performance Bonus",  "required": False},
    "annual_rent":       {"module": "payroll",   "label": "Annual Rent (for tax relief)","required": False},

    # Leave / HR
    "leave_type":        {"module": "leave",     "label": "Leave Type",         "required": False},
    "leave_start":       {"module": "leave",     "label": "Leave Start Date",   "required": False},
    "leave_end":         {"module": "leave",     "label": "Leave End Date",     "required": False},

    # Performance
    "performance_score": {"module": "performance","label": "Performance Score", "required": False},
    "manager_notes":     {"module": "performance","label": "Manager Notes",     "required": False},
}

# ─── Alias Dictionary ─────────────────────────────────────────────────────────
# Maps known synonyms → system_field

ALIASES: dict[str, str] = {
    # Name variants
    "name":              "full_name",
    "emp_name":          "full_name",
    "employee_name":     "full_name",
    "staff_name":        "full_name",
    "worker_name":       "full_name",
    "fullname":          "full_name",
    "full name":         "full_name",
    "firstname":         "first_name",
    "first":             "first_name",
    "surname":           "last_name",
    "lastname":          "last_name",
    "last":              "last_name",

    # ID variants
    "id":                "employee_id",
    "emp_id":            "employee_id",
    "staff_id":          "employee_id",
    "worker_id":         "employee_id",
    "employee id":       "employee_id",
    "staff no":          "employee_id",
    "payroll_no":        "employee_id",

    # Department
    "dept":              "department",
    "team":              "department",
    "division":          "department",
    "unit":              "department",

    # Job
    "job":               "position",
    "role":              "position",
    "title":             "position",
    "job_title":         "position",
    "job title":         "position",
    "designation":       "position",

    # Salary
    "salary":            "gross_salary",
    "pay":               "gross_salary",
    "wage":              "gross_salary",
    "compensation":      "gross_salary",
    "monthly_salary":    "gross_salary",
    "monthly salary":    "gross_salary",
    "gross":             "gross_salary",
    "gross pay":         "gross_salary",
    "total salary":      "gross_salary",
    "basic":             "basic_salary",
    "base salary":       "basic_salary",
    "base pay":          "basic_salary",
    "housing":           "housing_allowance",
    "transport":         "transport_allowance",
    "transportation":    "transport_allowance",
    "bonus":             "performance_bonus",
    "allowance":         "other_allowances",

    # Dates
    "date_joined":       "start_date",
    "join_date":         "start_date",
    "joining_date":      "start_date",
    "date joined":       "start_date",
    "commencement":      "start_date",
    "hire_date":         "start_date",
    "date_hired":        "start_date",
    "exit_date":         "end_date",
    "termination_date":  "end_date",
    "date left":         "end_date",

    # Contact
    "mail":              "email",
    "email_address":     "email",
    "e-mail":            "email",
    "mobile":            "phone",
    "phone_number":      "phone",
    "telephone":         "phone",
    "tel":               "phone",
    "contact":           "phone",

    # Bank
    "bank":              "bank_name",
    "bank_account":      "account_number",
    "account":           "account_number",
    "acct":              "account_number",
    "acct_no":           "account_number",
    "nuban":             "account_number",

    # Status
    "employment_status": "status",
    "staff_status":      "status",
    "active":            "status",

    # Tax / pension
    "tin":               "tax_id",
    "tax_number":        "tax_id",
    "pfa":               "pension_pin",
    "rsa_pin":           "pension_pin",
    "pension":           "pension_pin",
    "rent":              "annual_rent",
    "annual_rent_paid":  "annual_rent",

    # Performance
    "score":             "performance_score",
    "perf_score":        "performance_score",
    "rating":            "performance_score",
    "notes":             "manager_notes",
    "feedback":          "manager_notes",
    "comments":          "manager_notes",
}


# ─── Mapping Result ───────────────────────────────────────────────────────────

@dataclass
class ColumnMapping:
    sheet_column: str           # Original column name from the sheet
    system_field: Optional[str] # Mapped system field (None = unmapped)
    confidence:   float         # 0.0–1.0
    method:       str           # exact / normalized / alias / fuzzy / manual / skip
    module:       str           # employees / payroll / leave / performance
    label:        str           # Human-readable system field label
    overridden:   bool = False  # True if Esther manually adjusted this mapping

    def to_dict(self) -> dict:
        return {
            "sheet_column": self.sheet_column,
            "system_field": self.system_field,
            "confidence":   round(self.confidence, 2),
            "method":       self.method,
            "module":       self.module,
            "label":        self.label,
            "overridden":   self.overridden,
        }


@dataclass
class MappingResult:
    mappings:       list[ColumnMapping]
    unmapped:       list[str]           # Column names with no match
    low_confidence: list[str]           # Columns mapped but confidence < 0.7
    needs_review:   bool                # True if any unmapped or low-confidence

    def to_dict(self) -> dict:
        return {
            "mappings":       [m.to_dict() for m in self.mappings],
            "unmapped":       self.unmapped,
            "low_confidence": self.low_confidence,
            "needs_review":   self.needs_review,
            "summary": {
                "total_columns":       len(self.mappings),
                "mapped":              sum(1 for m in self.mappings if m.system_field),
                "unmapped":            len(self.unmapped),
                "auto_high_confidence":sum(1 for m in self.mappings if m.confidence >= 0.85 and m.system_field),
                "needs_manual":        len(self.low_confidence) + len(self.unmapped),
            },
        }


# ─── Core Mapper ──────────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    """Lowercase, strip spaces, punctuation and common noise words."""
    t = text.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", " ", t)   # punctuation → space
    t = re.sub(r"\s+", "_", t.strip())    # spaces → underscore
    # strip common noise suffixes
    for noise in ("_no", "_number", "_id", "_name"):
        if t.endswith(noise) and len(t) > len(noise) + 2:
            t = t[: -len(noise)]
    return t


def map_columns(sheet_columns: list[str]) -> MappingResult:
    """
    Auto-map a list of sheet column names to GENZ HR system fields.

    Strategy (in order):
      1. Exact match against system field keys
      2. Normalised match
      3. Alias lookup (exact and normalised)
      4. Fuzzy substring match
    """
    mappings       = []
    unmapped       = []
    low_confidence = []

    for col in sheet_columns:
        mapping = _map_single(col)
        mappings.append(mapping)
        if not mapping.system_field:
            unmapped.append(col)
        elif mapping.confidence < 0.7:
            low_confidence.append(col)

    result = MappingResult(
        mappings       = mappings,
        unmapped       = unmapped,
        low_confidence = low_confidence,
        needs_review   = bool(unmapped or low_confidence),
    )
    logger.info(
        f"Column mapping complete: {len(sheet_columns)} columns → "
        f"{result.to_dict()['summary']['mapped']} mapped, "
        f"{len(unmapped)} unmapped, {len(low_confidence)} low-confidence"
    )
    return result


def _map_single(col: str) -> ColumnMapping:
    norm = _normalise(col)

    def make(field: Optional[str], confidence: float, method: str) -> ColumnMapping:
        info = HR_FIELDS.get(field, {}) if field else {}
        return ColumnMapping(
            sheet_column = col,
            system_field = field,
            confidence   = confidence,
            method       = method,
            module       = info.get("module", ""),
            label        = info.get("label", field or ""),
        )

    # 1. Exact match on system field keys
    if col in HR_FIELDS:
        return make(col, 1.0, "exact")

    # 2. Normalised match on system field keys
    for field_key in HR_FIELDS:
        if norm == _normalise(field_key):
            return make(field_key, 0.9, "normalized")

    # 3. Alias lookup — exact col name
    col_lower = col.lower().strip()
    if col_lower in ALIASES:
        return make(ALIASES[col_lower], 0.85, "alias")

    # 4. Alias lookup — normalised col name
    if norm in ALIASES:
        return make(ALIASES[norm], 0.82, "alias_normalized")

    # 5. Fuzzy: system field key is a substring of the column (or vice versa)
    for field_key in HR_FIELDS:
        fk_norm = _normalise(field_key)
        if fk_norm and (fk_norm in norm or norm in fk_norm):
            score = len(fk_norm) / max(len(norm), 1)
            if score > 0.5:
                return make(field_key, round(0.5 + score * 0.3, 2), "fuzzy_substring")

    # 6. Alias fuzzy: alias key is a substring of normalised column
    for alias_key, field_key in ALIASES.items():
        ak_norm = _normalise(alias_key)
        if ak_norm and ak_norm in norm:
            return make(field_key, 0.60, "fuzzy_alias")

    return make(None, 0.0, "unmatched")


def apply_override(
    mapping_result: MappingResult,
    sheet_column:   str,
    system_field:   Optional[str],
) -> MappingResult:
    """
    Apply a manual override from Esther.
    system_field=None means 'skip this column'.
    """
    for m in mapping_result.mappings:
        if m.sheet_column == sheet_column:
            info = HR_FIELDS.get(system_field, {}) if system_field else {}
            m.system_field = system_field
            m.confidence   = 1.0 if system_field else 0.0
            m.method       = "manual"
            m.module       = info.get("module", "")
            m.label        = info.get("label", system_field or "skipped")
            m.overridden   = True
            logger.info(f"Manual override: '{sheet_column}' → '{system_field}'")
            break

    # Refresh unmapped / low_confidence lists
    mapping_result.unmapped       = [m.sheet_column for m in mapping_result.mappings if not m.system_field]
    mapping_result.low_confidence = [m.sheet_column for m in mapping_result.mappings
                                     if m.system_field and m.confidence < 0.7]
    mapping_result.needs_review   = bool(mapping_result.unmapped or mapping_result.low_confidence)
    return mapping_result


def get_all_system_fields() -> list[dict]:
    """Return full field catalogue for the mapping UI dropdown."""
    return [
        {"field": k, "label": v["label"], "module": v["module"], "required": v["required"]}
        for k, v in HR_FIELDS.items()
    ]
