"""
Database setup using SQLAlchemy.

Supports two backends:
  - SQLite  (local development, default)
  - PostgreSQL / Neon DB  (production on Railway)

The backend is chosen automatically based on the DATABASE_URL env var.
"""

import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Build engine with the right options for the chosen backend
# ---------------------------------------------------------------------------

_connect_args = {}
_engine_kwargs = {
    "echo": settings.DEBUG,
    "pool_pre_ping": True,  # Auto-reconnect stale connections (important for Neon)
}

if settings.is_postgres:
    # PostgreSQL / Neon — use connection pooling settings suitable for serverless PG
    logger.info("Using PostgreSQL backend (Neon DB)")
    _engine_kwargs.update({
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 300,  # Recycle connections every 5 min (Neon idle timeout)
    })
else:
    # SQLite — needs check_same_thread=False for FastAPI's async
    logger.info("Using SQLite backend (local development)")
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    **_engine_kwargs,
)


# ---------------------------------------------------------------------------
# SQLite-specific pragmas (only when using SQLite)
# ---------------------------------------------------------------------------
if not settings.is_postgres:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables (safe for both SQLite and PostgreSQL)."""
    from models import (
        Agent, ADM, Interaction, Feedback,
        TrainingProgress, DiaryEntry, DailyBriefing,
        User, Product,
        ReasonTaxonomy, FeedbackTicket, DepartmentQueue, AggregationAlert,
        TicketMessage,
        AgentFeedbackTicket, AgentTicketMessage, AgentDepartmentQueue,
    )
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created / verified.")
