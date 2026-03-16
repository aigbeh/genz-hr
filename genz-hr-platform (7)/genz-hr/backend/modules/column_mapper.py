"""
GENZ HR — Column Mapper (top-level re-export + proposal helpers)
Wraps backend/modules/integrations/column_mapper.py and adds
the higher-level proposal/confirmation API used by the UI.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("genz.mapper")

# Re-export core mapper
from backend.modules.integrations.column_mapper import (
    HR_FIELDS,
    map_columns,
    apply_override,
    MappingResult,
    ColumnMap,
)

# ── Field Registry (for UI dropdowns) ────────────────────────────────────────
FIELD_REGISTRY = {
    field_key: meta["label"]
    for field_key, meta in HR_FIELDS.items()
}


@dataclass
class MappingProposal:
    """Single proposed mapping surfaced to the UI for confirmation."""
    sheet_column:  str
    system_field:  str                      # "" = unmapped
    label:         str = ""
    target_module: str = "employees"
    confidence:    float = 0.0
    method:        str = "auto"             # exact | alias | fuzzy | manual | skip
    needs_review:  bool = False
    is_key_field:  bool = False
    field_type:    str = "string"           # string | date | float | integer

    def to_dict(self) -> dict:
        return {
            "sheet_column":  self.sheet_column,
            "system_field":  self.system_field,
            "label":         self.label,
            "target_module": self.target_module,
            "confidence":    round(self.confidence, 2),
            "method":        self.method,
            "needs_review":  self.needs_review,
            "is_key_field":  self.is_key_field,
            "field_type":    self.field_type,
        }


def propose_mappings(headers: list[str]) -> list[MappingProposal]:
    """
    Given a list of column headers, return one MappingProposal per column.
    Delegates to the core mapper then wraps in MappingProposal objects.
    """
    result = map_columns(headers)
    proposals = []
    for cm in result.mappings:
        meta = HR_FIELDS.get(cm.system_field, {})
        proposals.append(MappingProposal(
            sheet_column  = cm.sheet_column,
            system_field  = cm.system_field or "",
            label         = meta.get("label", cm.system_field or ""),
            target_module = meta.get("module", "employees"),
            confidence    = cm.confidence,
            method        = cm.method,
            needs_review  = cm.confidence < 0.7 or not cm.system_field,
            is_key_field  = cm.system_field in ("employee_id", "email"),
            field_type    = _infer_type(cm.system_field),
        ))
    return proposals


def apply_confirmed_mappings(
    proposals: list[MappingProposal],
    overrides: dict,   # {sheet_column: system_field | None}
) -> list[MappingProposal]:
    """
    Apply Esther's manual overrides on top of auto-proposals.
    Pass system_field=None or "" to explicitly unmap a column.
    """
    confirmed = []
    for p in proposals:
        if p.sheet_column in overrides:
            new_field = overrides[p.sheet_column]
            if not new_field:
                p.method       = "skip"
                p.system_field = ""
                p.needs_review = False
            else:
                meta           = HR_FIELDS.get(new_field, {})
                p.system_field = new_field
                p.label        = meta.get("label", new_field)
                p.target_module= meta.get("module", "employees")
                p.confidence   = 1.0
                p.method       = "manual"
                p.needs_review = False
                p.field_type   = _infer_type(new_field)
        confirmed.append(p)
    return confirmed


def _infer_type(field_key: Optional[str]) -> str:
    if not field_key:
        return "string"
    if any(x in field_key for x in ("salary", "allowance", "bonus", "deduction", "score", "pct")):
        return "float"
    if any(x in field_key for x in ("date",)):
        return "date"
    if any(x in field_key for x in ("count", "headcount")):
        return "integer"
    return "string"
