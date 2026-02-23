"""
ADM Platform - FastAPI Application Entry Point

Axis Max Life Insurance Agent Activation & Re-engagement System.
Provides REST APIs for managing dormant agent activation through
ADMs (Agency Development Managers).
"""

import logging
import sys
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db, SessionLocal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("adm_platform")

# Track whether DB initialization is complete (for healthcheck)
_db_ready = threading.Event()


def _needs_db_reset(db) -> bool:
    """Check if the database contains stale demo data that needs to be wiped.

    Detects old demo ADMs (Suresh, Amitava, Rajiv, Priyanka, Meenakshi) that
    were part of the initial prototype. If any exist, the DB should be reset.
    Also resets if RESET_DB env var is set.
    """
    import os
    from models import ADM

    # Explicit reset via env var
    if os.environ.get("RESET_DB", "").lower() in ("true", "1", "yes"):
        logger.warning("RESET_DB=true env var detected.")
        return True

    # Detect stale demo ADMs by name fragments
    # Set 1: Original prototype ADMs (Feb 17 initial build)
    # Set 2: Demo agents from hardcoded agent list (AGT001-AGT008)
    stale_names = [
        "Suresh", "Amitava", "Rajiv", "Priyanka", "Meenakshi",  # Old demo ADMs
        "Priya Sharma", "Kavita Singh", "Deepak Gupta", "Anjali Reddy",  # Demo agents
        "Neeta Desai", "Rajesh Verma",  # More demo agents
    ]
    try:
        for name_frag in stale_names:
            if db.query(ADM).filter(ADM.name.contains(name_frag)).first():
                logger.warning(f"Stale demo data detected: '{name_frag}*'. DB needs reset.")
                return True
        # Also check Agent table for demo agents by name
        from models import Agent
        demo_agent_names = ["Suresh Patel", "Priya Sharma", "Amit Kumar", "Neeta Desai",
                           "Rajesh Verma", "Kavita Singh", "Deepak Gupta", "Anjali Reddy"]
        for name in demo_agent_names:
            if db.query(Agent).filter(Agent.name == name).first():
                logger.warning(f"Stale demo agent detected: '{name}'. DB needs reset.")
                return True
    except Exception:
        pass  # Table might not exist yet — that's fine

    return False


def run_seed_if_empty():
    """Seed reference data (products, admin user, ADM users) if not already present."""
    from models import Product, User

    db = SessionLocal()
    try:
        # Check for stale data (old demo ADMs) or explicit RESET_DB flag
        if _needs_db_reset(db):
            db.close()  # Close before dropping
            logger.warning("Dropping ALL tables and re-creating for clean slate...")
            from database import engine, Base
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            logger.warning("All tables dropped and re-created.")
            db = SessionLocal()  # Reopen after reset

        count = db.query(Product).count()
        if count == 0:
            logger.info("No products found. Seeding reference data...")
            from seed_data import seed_database
            seed_database(db)
            logger.info("Reference data seeded successfully.")
        else:
            logger.info(f"Database has {count} products. Skipping full seed.")
            # Still ensure key users exist even if products were already seeded
            _ensure_key_users(db)

        # Always ensure ReasonTaxonomy is populated (needed for feedback workflow)
        from models import ReasonTaxonomy
        reason_count = db.query(ReasonTaxonomy).count()
        if reason_count == 0:
            logger.info("No ReasonTaxonomy entries found. Seeding feedback reasons...")
            from seed_data import REASON_TAXONOMY
            for r_data in REASON_TAXONOMY:
                db.add(ReasonTaxonomy(**r_data))
            db.commit()
            logger.info(f"Seeded {len(REASON_TAXONOMY)} feedback reason taxonomy entries.")
        else:
            logger.info(f"ReasonTaxonomy has {reason_count} entries. OK.")
    except Exception as e:
        logger.error(f"Error during seeding: {e}")
        db.rollback()
    finally:
        db.close()


def _ensure_key_users(db):
    """Ensure admin and key ADM users exist in the database."""
    import hashlib
    from models import User, ADM

    def _hash(pw: str) -> str:
        return hashlib.sha256(pw.encode()).hexdigest()

    # Admin user
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(username="admin", password_hash=_hash("admin123"), role="admin", name="Platform Admin"))
        db.flush()
        logger.info("Created missing admin user (admin/admin123)")

    # Rohit Sadhu ADM
    if not db.query(User).filter(User.username == "rohit").first():
        rohit_adm = db.query(ADM).filter(ADM.telegram_chat_id == "8321786545").first()
        if not rohit_adm:
            rohit_adm = ADM(
                name="Rohit Sadhu", phone="7303474258", region="North",
                language="Hindi,English", max_capacity=50, performance_score=0.0,
                telegram_chat_id="8321786545",
            )
            db.add(rohit_adm)
            db.flush()
        db.add(User(username="rohit", password_hash=_hash("rohit123"), role="adm", name="Rohit Sadhu", adm_id=rohit_adm.id))
        db.commit()
        logger.info("Created missing ADM user: Rohit Sadhu (rohit/rohit123)")


def _background_db_init():
    """Run DB initialization and seeding in a background thread.

    This allows uvicorn to start serving requests (especially /health)
    immediately while the potentially slow DB reset + seed runs in the background.
    """
    try:
        logger.info("Background DB init: creating tables...")
        init_db()
        logger.info("Background DB init: tables created.")

        logger.info("Background DB init: checking seed data...")
        run_seed_if_empty()

        logger.info("Background DB init: complete!")
    except Exception as e:
        logger.error(f"Background DB init failed: {e}")
    finally:
        _db_ready.set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    # --- Startup ---
    logger.info("=" * 60)
    logger.info(f"  {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info("=" * 60)

    # Run DB init in background so healthcheck responds immediately
    db_thread = threading.Thread(target=_background_db_init, daemon=True)
    db_thread.start()

    logger.info("Application accepting requests (DB init running in background).")
    logger.info(f"API docs available at: http://localhost:8000/docs")
    logger.info("=" * 60)

    yield

    # --- Shutdown ---
    logger.info("Application shutting down...")


# ---------------------------------------------------------------------------
# Create FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "REST API for the ADM Platform - Axis Max Life Insurance "
        "Agent Activation & Re-engagement System. "
        "Manages dormant agent lifecycle, ADM assignments, interactions, "
        "feedback, training, analytics, and AI-powered insights."
    ),
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS Middleware (allow all for demo)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Include all route routers under /api/v1
# ---------------------------------------------------------------------------
from routes import (
    agents_router,
    adms_router,
    interactions_router,
    feedback_router,
    diary_router,
    briefings_router,
    analytics_router,
    training_router,
    assignment_router,
    telegram_bot_router,
    auth_router,
    products_router,
    onboarding_router,
    playbooks_router,
    communication_router,
    feedback_tickets_router,
)

API_PREFIX = "/api/v1"

all_routers = [
    telegram_bot_router,
    agents_router,
    adms_router,
    interactions_router,
    feedback_router,
    diary_router,
    briefings_router,
    analytics_router,
    training_router,
    assignment_router,
    auth_router,
    products_router,
    onboarding_router,
    playbooks_router,
    communication_router,
    feedback_tickets_router,
]

# Mount all routers under /api/v1 (primary)
for r in all_routers:
    app.include_router(r, prefix=API_PREFIX)

# Also mount all routers at root (no prefix) so the API works
# regardless of whether NEXT_PUBLIC_API_URL includes /api/v1 or not
for r in all_routers:
    app.include_router(r)


# ---------------------------------------------------------------------------
# Health check endpoint (at root, not under /api/v1)
# ---------------------------------------------------------------------------
@app.get("/", tags=["Health"])
def root():
    """Root endpoint - basic info."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "api_prefix": API_PREFIX,
    }


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint.

    Returns immediately with status=healthy so Railway healthcheck passes.
    DB details are included only after background init completes.
    """
    db_initialized = _db_ready.is_set()

    result = {
        "status": "healthy",
        "database": "ready" if db_initialized else "initializing",
        "ai_enabled": settings.ENABLE_AI_FEATURES and bool(settings.ANTHROPIC_API_KEY),
        "telegram_enabled": settings.ENABLE_TELEGRAM_BOT and bool(settings.TELEGRAM_BOT_TOKEN),
    }

    # Only query DB if background init is complete
    if db_initialized:
        try:
            from database import SessionLocal
            from models import Agent
            db = SessionLocal()
            result["agent_count"] = db.query(Agent).count()
            db.close()
        except Exception as e:
            result["agent_count"] = 0
            result["database"] = f"error: {str(e)}"

    return result


# ---------------------------------------------------------------------------
# Run with uvicorn when executed directly
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.environ.get("PORT", 8000))
    is_dev = os.environ.get("RAILWAY_ENVIRONMENT") is None

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=is_dev,
        log_level="info",
    )
