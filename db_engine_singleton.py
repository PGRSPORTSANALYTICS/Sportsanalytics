"""
Shared SQLAlchemy engine singleton for dashboard queries.
Replaces the 8 separate create_engine() calls in pgr_football_dashboard.py
with a single pool of 3 connections max, preventing Neon connection exhaustion.
"""
import os
import logging
from sqlalchemy import create_engine as _create_engine

logger = logging.getLogger(__name__)

_engine = None

def get_dashboard_engine():
    """Returns (or creates) the shared SQLAlchemy engine for dashboard use."""
    global _engine
    if _engine is not None:
        return _engine

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        return None

    try:
        _engine = _create_engine(
            db_url,
            pool_size=2,
            max_overflow=1,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={"connect_timeout": 8},
        )
        logger.info("✅ Dashboard SQLAlchemy engine initialized (pool_size=2, max_overflow=1)")
    except Exception as e:
        logger.error(f"❌ Failed to create dashboard engine: {e}")
        return None

    return _engine
