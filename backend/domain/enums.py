"""
domain/enums.py — All domain enumerations for the ADM Platform.

Ported from AARS core/enums.py. Uses StrEnum so values serialize cleanly
to JSON and can be stored directly in SQLite TEXT columns.
"""
from __future__ import annotations

import sys
if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum
    class StrEnum(str, Enum):
        """Backport of StrEnum for Python < 3.11."""
        pass


# ---------------------------------------------------------------------------
# Agent Lifecycle
# ---------------------------------------------------------------------------
class AgentLifecycleState(StrEnum):
    """The lifecycle funnel every agent moves through.

    Progression: ONBOARDED -> LICENSED -> FIRST_SALE -> ACTIVE -> PRODUCTIVE
    Risk path:   ACTIVE/PRODUCTIVE -> AT_RISK -> DORMANT -> LAPSED
    Terminal:     TERMINATED (manual only)
    """
    ONBOARDED = "onboarded"
    LICENSED = "licensed"
    FIRST_SALE = "first_sale"
    ACTIVE = "active"
    PRODUCTIVE = "productive"
    AT_RISK = "at_risk"
    DORMANT = "dormant"
    LAPSED = "lapsed"
    TERMINATED = "terminated"


# ---------------------------------------------------------------------------
# Dormancy Reasons
# ---------------------------------------------------------------------------
class DormancyReasonCategory(StrEnum):
    """Seven high-level categories that explain WHY an agent went dormant."""
    TRAINING_GAP = "training_gap"
    ENGAGEMENT_GAP = "engagement_gap"
    ECONOMIC = "economic"
    OPERATIONAL = "operational"
    PERSONAL = "personal"
    REGULATORY = "regulatory"
    UNKNOWN = "unknown"


class DormancyReasonCode(StrEnum):
    """27 specific dormancy reason codes, namespaced under their category.

    Format: {category}.{specific_reason}
    """
    # Training Gap (5)
    PRODUCT_KNOWLEDGE_INSUFFICIENT = "training_gap.product_knowledge_insufficient"
    SALES_SKILLS_LACKING = "training_gap.sales_skills_lacking"
    EXAM_NOT_ATTEMPTED = "training_gap.exam_not_attempted"
    EXAM_FAILED = "training_gap.exam_failed"
    PROCESS_UNCLEAR = "training_gap.process_unclear"

    # Engagement Gap (4)
    ADM_NEVER_CONTACTED = "engagement_gap.adm_never_contacted"
    ADM_NO_FOLLOWTHROUGH = "engagement_gap.adm_no_followthrough"
    FEELS_UNSUPPORTED = "engagement_gap.feels_unsupported"
    NO_RECOGNITION = "engagement_gap.no_recognition"

    # Economic (4)
    COMMISSION_TOO_LOW = "economic.commission_too_low"
    COMPETITOR_BETTER_COMMISSION = "economic.competitor_better_commission"
    IRREGULAR_PAYMENTS = "economic.irregular_payments"
    INSUFFICIENT_INCOME = "economic.insufficient_income"

    # Operational (5)
    PROPOSAL_PROCESS_COMPLEX = "operational.proposal_process_complex"
    TECHNOLOGY_BARRIERS = "operational.technology_barriers"
    CLAIM_EXPERIENCE_BAD = "operational.claim_experience_bad"
    SLOW_ISSUANCE = "operational.slow_issuance"
    KYC_ISSUES = "operational.kyc_issues"

    # Personal (5)
    HEALTH_ISSUES = "personal.health_issues"
    RELOCATED = "personal.relocated"
    FAMILY_OBLIGATIONS = "personal.family_obligations"
    LOST_INTEREST = "personal.lost_interest"
    OTHER_EMPLOYMENT = "personal.other_employment"

    # Regulatory (3)
    LICENSE_EXPIRED = "regulatory.license_expired"
    LICENSE_EXPIRING_SOON = "regulatory.license_expiring_soon"
    COMPLIANCE_ISSUE = "regulatory.compliance_issue"

    # Unknown (1)
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Contact & Communication
# ---------------------------------------------------------------------------
class ContactOutcome(StrEnum):
    """Outcome of any outreach attempt (call, message, visit)."""
    ANSWERED = "answered"
    NOT_ANSWERED = "not_answered"
    BUSY = "busy"
    SWITCHED_OFF = "switched_off"
    WRONG_NUMBER = "wrong_number"
    DND_BLOCKED = "dnd_blocked"
    OPTED_OUT = "opted_out"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED_TECHNICAL = "failed_technical"


class SentimentLabel(StrEnum):
    """Sentiment detected from agent communication."""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    FRUSTRATED = "frustrated"
    INTERESTED = "interested"
    CONFUSED = "confused"


class ChannelType(StrEnum):
    """Communication channels used to reach agents."""
    VOICE_AI = "voice_ai"
    WHATSAPP_BOT = "whatsapp_bot"
    WHATSAPP_ADM = "whatsapp_adm"
    ADM_CALL = "adm_call"
    ADM_VISIT = "adm_visit"
    TELEGRAM = "telegram"
    SMS = "sms"
    EMAIL = "email"
    SELF_SERVICE = "self_service"


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
class TrainingTopic(StrEnum):
    """Training content topic categories for agent skill development."""
    # Product knowledge
    PRODUCT_TERM_LIFE = "product_term_life"
    PRODUCT_ENDOWMENT = "product_endowment"
    PRODUCT_ULIP = "product_ulip"
    PRODUCT_HEALTH = "product_health"
    PRODUCT_PENSION = "product_pension"

    # Sales skills
    SALES_PROSPECTING = "sales_prospecting"
    SALES_PITCH = "sales_pitch"
    SALES_OBJECTION_HANDLING = "sales_objection_handling"
    SALES_CLOSING = "sales_closing"

    # Process knowledge
    PROCESS_PROPOSAL_FILLING = "process_proposal_filling"
    PROCESS_KYC = "process_kyc"
    PROCESS_DIGITAL_TOOLS = "process_digital_tools"

    # Compliance
    COMPLIANCE_BASICS = "compliance_basics"
    COMPLIANCE_MIS_SELLING = "compliance_mis_selling"

    # Soft skills
    SOFT_SKILLS_COMMUNICATION = "soft_skills_communication"
    SOFT_SKILLS_TRUST_BUILDING = "soft_skills_trust_building"


# ---------------------------------------------------------------------------
# Insurance Products
# ---------------------------------------------------------------------------
class ProductCategory(StrEnum):
    """Insurance product categories."""
    TERM_LIFE = "term_life"
    ENDOWMENT = "endowment"
    ULIP = "ulip"
    WHOLE_LIFE = "whole_life"
    PENSION = "pension"
    HEALTH = "health"
    GROUP = "group"


# ---------------------------------------------------------------------------
# Playbook & Decision
# ---------------------------------------------------------------------------
class PlaybookActionType(StrEnum):
    """Types of actions a playbook step can execute."""
    VOICE_CALL = "voice_call"
    WHATSAPP_MESSAGE = "whatsapp_message"
    WHATSAPP_TRAINING = "whatsapp_training"
    ADM_NUDGE = "adm_nudge"
    TELEGRAM_MESSAGE = "telegram_message"
    WAIT = "wait"
    ESCALATE = "escalate"


class DecisionAction(StrEnum):
    """Actions the decision engine can recommend."""
    DO_NOTHING = "do_nothing"
    START_PLAYBOOK = "start_playbook"
    CONTINUE_PLAYBOOK = "continue_playbook"
    SEND_NUDGE_TO_ADM = "send_nudge_to_adm"
    SCHEDULE_VOICE_CALL = "schedule_voice_call"
    SEND_WHATSAPP = "send_whatsapp"
    SEND_TELEGRAM = "send_telegram"
    SEND_TRAINING = "send_training"
    ESCALATE = "escalate"
    CELEBRATE = "celebrate"
    PAUSE_OUTREACH = "pause_outreach"
    CLOSE_AND_ARCHIVE = "close_and_archive"


# ---------------------------------------------------------------------------
# Signal types (simplified for ADM platform — no full signal stream)
# ---------------------------------------------------------------------------
class SignalType(StrEnum):
    """Key signal types that drive lifecycle transitions."""
    # Business events
    POLICY_SOLD = "policy_sold"
    LICENSE_STATUS_CHANGED = "license_status_changed"
    COMMISSION_CREDITED = "commission_credited"
    TRAINING_COMPLETED = "training_completed"

    # Communication events
    WHATSAPP_AGENT_REPLIED = "whatsapp_agent_replied"
    VOICE_CALL_OUTCOME = "voice_call_outcome"
    ADM_AGENT_CALL_LOGGED = "adm_agent_call_logged"
    ADM_AGENT_VISIT_LOGGED = "adm_agent_visit_logged"
    WHATSAPP_TRAINING_INTERACTION = "whatsapp_training_interaction"

    # System events
    LIFECYCLE_STATE_CHANGED = "lifecycle_state_changed"
    PLAYBOOK_STARTED = "playbook_started"
    PLAYBOOK_COMPLETED = "playbook_completed"


# ---------------------------------------------------------------------------
# Cohort Segments (agent classification)
# ---------------------------------------------------------------------------
class CohortSegment(StrEnum):
    """16 named cohort segments for agent classification."""
    PROMISING_ROOKIES = "promising_rookies"
    STALLED_STARTERS = "stalled_starters"
    SLEEPING_GIANTS = "sleeping_giants"
    FADING_STARS = "fading_stars"
    WEEKEND_WARRIORS = "weekend_warriors"
    ECONOMIC_DEFECTORS = "economic_defectors"
    SYSTEM_FRUSTRATED = "system_frustrated"
    ABANDONED_BY_ADM = "abandoned_by_adm"
    CHRONIC_NEVER_ACTIVATORS = "chronic_never_activators"
    LIFE_EVENT_PAUSED = "life_event_paused"
    REGULATORY_BLOCKED = "regulatory_blocked"
    DIGITAL_ORPHANS = "digital_orphans"
    HIGH_POTENTIAL_UNPOLISHED = "high_potential_unpolished"
    COMPETITOR_POACHED = "competitor_poached"
    SATISFIED_PASSIVES = "satisfied_passives"
    LOST_CAUSES = "lost_causes"


class EngagementStrategy(StrEnum):
    """Engagement strategy decided by cohort classifier."""
    DIRECT_CALL = "direct_call"
    WHATSAPP_FIRST = "whatsapp_first"
    TELEGRAM_ONLY = "telegram_only"
    NO_CONTACT = "no_contact"


class WorkType(StrEnum):
    """Agent work orientation."""
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    SIDE_HUSTLE = "side_hustle"


class MarketTier(StrEnum):
    """Market tier based on agent location."""
    METRO = "metro"
    TIER_2 = "tier_2"
    SEMI_URBAN = "semi_urban"
    RURAL = "rural"


class CareerStage(StrEnum):
    """Agent career stage in insurance."""
    ROOKIE = "rookie"          # < 1 year
    DEVELOPING = "developing"  # 1-3 years
    EXPERIENCED = "experienced"  # 3+ years
