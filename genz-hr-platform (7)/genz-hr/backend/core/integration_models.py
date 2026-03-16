"""
GENZ HR — Integration Models (re-exports)
The actual models now live in database.py for consistency.
This module re-exports them for backwards compatibility.
"""
from backend.core.database import (
    Base,
    DataIntegrationConfig,
    IntegrationLog,
)
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey
from backend.core.database import Base


class DataSource(Base):
    """
    Registered data source — uploaded Excel or linked Google Sheet.
    """
    __tablename__ = "data_sources"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    name           = Column(String, nullable=False)
    source_type    = Column(String, nullable=False)   # "excel" | "google_sheet"
    file_path      = Column(String)
    sheet_url      = Column(String)
    sheet_id       = Column(String)
    tab_name       = Column(String)
    status         = Column(String, default="pending")  # pending|active|error|paused
    row_count      = Column(Integer, default=0)
    last_synced_at = Column(DateTime)
    last_hash      = Column(String)
    auto_sync      = Column(Boolean, default=True)
    sync_interval  = Column(Integer, default=3600)  # seconds
    created_at     = Column(DateTime, default=datetime.utcnow)
    created_by     = Column(String, default="Esther")
    error_message  = Column(Text)


class ColumnMapping(Base):
    """Confirmed column-to-field mapping for a DataSource."""
    __tablename__ = "column_mappings"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    data_source_id = Column(Integer, ForeignKey("data_sources.id"), nullable=False)
    sheet_column   = Column(String, nullable=False)
    system_field   = Column(String, nullable=False)
    target_module  = Column(String, nullable=False)
    transform      = Column(String, default="auto")
    is_key_field   = Column(Boolean, default=False)
    confirmed_by   = Column(String)
    created_at     = Column(DateTime, default=datetime.utcnow)


class SyncLog(Base):
    """One row per sync run — summary of what happened."""
    __tablename__ = "sync_logs"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    data_source_id = Column(Integer, ForeignKey("data_sources.id"), nullable=False)
    sync_type      = Column(String, default="full")    # full | delta
    trigger        = Column(String, default="manual")  # manual | schedule | upload
    status         = Column(String, default="running") # running | complete | failed | skipped
    rows_total     = Column(Integer, default=0)
    rows_inserted  = Column(Integer, default=0)
    rows_updated   = Column(Integer, default=0)
    rows_skipped   = Column(Integer, default=0)
    rows_errored   = Column(Integer, default=0)
    approvals_queued = Column(Integer, default=0)
    error_details  = Column(Text)
    triggered_by   = Column(String, default="manual")
    started_at     = Column(DateTime, default=datetime.utcnow)
    completed_at   = Column(DateTime)
    duration_ms    = Column(Integer, default=0)
