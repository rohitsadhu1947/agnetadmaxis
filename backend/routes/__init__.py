"""
Routes package for the ADM Platform API.
Import all routers here for use in main.py.
"""

from routes.agents import router as agents_router
from routes.adms import router as adms_router
from routes.interactions import router as interactions_router
from routes.feedback import router as feedback_router
from routes.diary import router as diary_router
from routes.briefings import router as briefings_router
from routes.analytics import router as analytics_router
from routes.training import router as training_router
from routes.assignment import router as assignment_router
from routes.telegram_bot import router as telegram_bot_router
from routes.auth import router as auth_router
from routes.products import router as products_router
from routes.onboarding import router as onboarding_router
from routes.playbooks import router as playbooks_router
from routes.communication import router as communication_router
from routes.feedback_tickets import router as feedback_tickets_router
from routes.agent_portal import router as agent_portal_router
from routes.cohort_analytics import router as cohort_analytics_router
from routes.outreach import router as outreach_router
# voice_call is an optional POC module — gracefully skipped if its source
# (or its deps like livekit-api) is not deployed. Avoids hard failures in
# environments where the POC isn't enabled.
try:
    from routes.voice_call import router as voice_call_router  # type: ignore
    HAS_VOICE_CALL = True
except ImportError:
    voice_call_router = None  # type: ignore
    HAS_VOICE_CALL = False

from routes.people_feedback import router as people_feedback_router
from routes.broadcasts import router as broadcasts_router

__all__ = [
    "agents_router",
    "adms_router",
    "interactions_router",
    "feedback_router",
    "diary_router",
    "briefings_router",
    "analytics_router",
    "training_router",
    "assignment_router",
    "telegram_bot_router",
    "auth_router",
    "products_router",
    "onboarding_router",
    "playbooks_router",
    "communication_router",
    "feedback_tickets_router",
    "agent_portal_router",
    "cohort_analytics_router",
    "outreach_router",
    "voice_call_router",
    "HAS_VOICE_CALL",
    "people_feedback_router",
    "broadcasts_router",
]
