"""
SQLAlchemy ORM models for the ADM Platform.
"""

import json
from datetime import datetime, date, time
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, Date, Time,
    DateTime, ForeignKey, Enum as SAEnum, JSON,
)
from sqlalchemy.orm import relationship
from database import Base


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    phone = Column(String(20), nullable=False, unique=True, index=True)
    email = Column(String(200), nullable=True)
    location = Column(String(200), nullable=False)  # City / District
    state = Column(String(100), nullable=True)       # Indian state
    language = Column(String(50), default="Hindi")    # Preferred language

    lifecycle_state = Column(
        String(30),
        default="dormant",
        index=True,
    )  # dormant | at_risk | contacted | engaged | trained | active

    dormancy_reason = Column(String(300), nullable=True)
    dormancy_duration_days = Column(Integer, default=0)
    last_contact_date = Column(Date, nullable=True)
    last_policy_sold_date = Column(Date, nullable=True)

    assigned_adm_id = Column(Integer, ForeignKey("adms.id"), nullable=True, index=True)
    engagement_score = Column(Float, default=0.0)  # 0-100

    license_number = Column(String(50), nullable=True)
    date_of_joining = Column(Date, nullable=True)
    specialization = Column(String(200), nullable=True)  # e.g., "term,ulip"

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    onboarding_status = Column(String(30), default="active")  # pending | documents_submitted | verified | active | rejected
    onboarding_started_at = Column(DateTime, nullable=True)
    onboarding_completed_at = Column(DateTime, nullable=True)

    # ----- Cohort Analysis Fields -----

    # Historical Performance
    total_policies_sold = Column(Integer, default=0)
    total_premium_generated = Column(Float, default=0.0)
    policies_last_12_months = Column(Integer, default=0)
    premium_last_12_months = Column(Float, default=0.0)
    avg_ticket_size = Column(Float, default=0.0)
    best_month_premium = Column(Float, default=0.0)
    persistency_ratio = Column(Float, default=0.0)  # % policies renewed

    # Activity & Recency
    last_login_date = Column(Date, nullable=True)
    last_training_date = Column(Date, nullable=True)
    last_proposal_date = Column(Date, nullable=True)
    days_since_last_activity = Column(Integer, default=0)

    # Responsiveness
    contact_attempts = Column(Integer, default=0)
    contact_responses = Column(Integer, default=0)
    response_rate = Column(Float, default=0.0)  # responses / attempts
    avg_response_time_hours = Column(Float, nullable=True)
    preferred_channel = Column(String(30), nullable=True)  # call | whatsapp | telegram

    # Career & Demographics
    age = Column(Integer, nullable=True)
    education_level = Column(String(50), nullable=True)
    years_in_insurance = Column(Float, default=0.0)
    previous_insurer = Column(String(100), nullable=True)
    is_poached = Column(Boolean, default=False)
    work_type = Column(String(30), default="full_time")  # full_time | part_time | side_hustle
    other_occupation = Column(String(200), nullable=True)

    # Digital
    has_app_installed = Column(Boolean, default=False)
    digital_savviness_score = Column(Float, default=0.0)  # 0-10
    last_app_login = Column(Date, nullable=True)

    # Cohort Classification (computed by cohort_classifier)
    cohort_segment = Column(String(50), nullable=True, index=True)
    reactivation_score = Column(Float, default=0.0)  # 0-100
    engagement_strategy = Column(String(30), nullable=True)  # direct_call | whatsapp | telegram | no_contact
    churn_risk_level = Column(String(20), nullable=True)  # high | medium | low | lost

    # Agent Telegram Bot
    telegram_chat_id = Column(String(50), nullable=True)
    telegram_registered = Column(Boolean, default=False)

    # Relationships
    assigned_adm = relationship("ADM", back_populates="agents")
    interactions = relationship("Interaction", back_populates="agent", cascade="all, delete-orphan")
    feedbacks = relationship("Feedback", back_populates="agent", cascade="all, delete-orphan")
    diary_entries = relationship("DiaryEntry", back_populates="agent")
    agent_feedback_tickets = relationship("AgentFeedbackTicket", back_populates="agent")


# ---------------------------------------------------------------------------
# ADM (Agency Development Manager)
# ---------------------------------------------------------------------------
class ADM(Base):
    __tablename__ = "adms"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    phone = Column(String(20), nullable=False, unique=True)
    email = Column(String(200), nullable=True)
    region = Column(String(200), nullable=False)   # e.g., "West - Mumbai"
    language = Column(String(100), default="Hindi,English")  # Comma-separated

    active_agent_count = Column(Integer, default=0)
    max_capacity = Column(Integer, default=50)
    performance_score = Column(Float, default=0.0)  # 0-100

    telegram_chat_id = Column(String(50), nullable=True)
    whatsapp_number = Column(String(20), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    agents = relationship("Agent", back_populates="assigned_adm")
    interactions = relationship("Interaction", back_populates="adm")
    feedbacks = relationship("Feedback", back_populates="adm")
    training_progress = relationship("TrainingProgress", back_populates="adm", cascade="all, delete-orphan")
    diary_entries = relationship("DiaryEntry", back_populates="adm", cascade="all, delete-orphan")
    daily_briefings = relationship("DailyBriefing", back_populates="adm", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Interaction
# ---------------------------------------------------------------------------
class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    adm_id = Column(Integer, ForeignKey("adms.id"), nullable=False, index=True)

    type = Column(String(30), nullable=False)  # call | whatsapp | visit | telegram
    outcome = Column(String(50), nullable=False)
    # connected | not_answered | busy | callback_requested | follow_up_scheduled | declined

    notes = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=True)  # for calls

    feedback_category = Column(String(100), nullable=True)
    feedback_subcategory = Column(String(100), nullable=True)
    sentiment_score = Column(Float, nullable=True)  # -1.0 to 1.0

    follow_up_date = Column(Date, nullable=True)
    follow_up_status = Column(String(30), default="pending")
    # pending | completed | overdue

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    agent = relationship("Agent", back_populates="interactions")
    adm = relationship("ADM", back_populates="interactions")
    feedbacks = relationship("Feedback", back_populates="interaction")


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    adm_id = Column(Integer, ForeignKey("adms.id"), nullable=False, index=True)
    interaction_id = Column(Integer, ForeignKey("interactions.id"), nullable=True)

    category = Column(String(100), nullable=False)
    # system_issues | commission_concerns | market_conditions |
    # product_complexity | personal_reasons | competition | support_issues

    subcategory = Column(String(200), nullable=True)
    raw_text = Column(Text, nullable=True)
    ai_summary = Column(Text, nullable=True)
    sentiment = Column(String(30), nullable=True)  # positive | neutral | negative
    priority = Column(String(20), default="medium")  # low | medium | high | critical
    status = Column(String(30), default="new")  # new | in_review | actioned | resolved

    action_taken = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    agent = relationship("Agent", back_populates="feedbacks")
    adm = relationship("ADM", back_populates="feedbacks")
    interaction = relationship("Interaction", back_populates="feedbacks")


# ---------------------------------------------------------------------------
# Training Progress
# ---------------------------------------------------------------------------
class TrainingProgress(Base):
    __tablename__ = "training_progress"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    adm_id = Column(Integer, ForeignKey("adms.id"), nullable=False, index=True)

    module_name = Column(String(200), nullable=False)
    module_category = Column(String(100), nullable=False)
    # product_knowledge | sales_techniques | compliance |
    # digital_tools | soft_skills | objection_handling

    score = Column(Float, default=0.0)  # 0-100
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    adm = relationship("ADM", back_populates="training_progress")


# ---------------------------------------------------------------------------
# Diary Entry
# ---------------------------------------------------------------------------
class DiaryEntry(Base):
    __tablename__ = "diary_entries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    adm_id = Column(Integer, ForeignKey("adms.id"), nullable=False, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True, index=True)

    scheduled_date = Column(Date, nullable=False, index=True)
    scheduled_time = Column(String(10), nullable=True)  # HH:MM format

    entry_type = Column(String(30), nullable=False)
    # follow_up | first_contact | training | escalation | review

    notes = Column(Text, nullable=True)
    status = Column(String(30), default="scheduled")
    # scheduled | completed | missed | rescheduled

    reminder_sent = Column(Boolean, default=False)
    completion_notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    adm = relationship("ADM", back_populates="diary_entries")
    agent = relationship("Agent", back_populates="diary_entries")


# ---------------------------------------------------------------------------
# Daily Briefing
# ---------------------------------------------------------------------------
class DailyBriefing(Base):
    __tablename__ = "daily_briefings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    adm_id = Column(Integer, ForeignKey("adms.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)

    priority_agents = Column(Text, nullable=True)     # JSON string of agent IDs + reasons
    pending_followups = Column(Integer, default=0)
    new_assignments = Column(Integer, default=0)
    overdue_followups = Column(Integer, default=0)

    summary_text = Column(Text, nullable=True)
    action_items = Column(Text, nullable=True)         # JSON string
    sent_via = Column(String(50), nullable=True)       # telegram | whatsapp | email | in_app

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    adm = relationship("ADM", back_populates="daily_briefings")


# ---------------------------------------------------------------------------
# User (Authentication)
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="adm")  # admin | adm
    adm_id = Column(Integer, ForeignKey("adms.id"), nullable=True)
    name = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    adm = relationship("ADM")


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Reason Taxonomy (reference data for feedback classification)
# ---------------------------------------------------------------------------
class ReasonTaxonomy(Base):
    __tablename__ = "reason_taxonomy"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(10), nullable=False, unique=True, index=True)  # UW-01, FIN-03, etc.
    bucket = Column(String(30), nullable=False, index=True)  # underwriting | finance | contest | operations | product
    reason_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    sub_reasons = Column(Text, nullable=True)  # JSON list of sub-reason variants
    keywords = Column(Text, nullable=True)  # JSON list of keywords for AI matching
    suggested_data_points = Column(Text, nullable=True)  # JSON list of data to pull
    typical_sla_hours = Column(Integer, default=48)
    display_order = Column(Integer, default=0)  # for UI ordering within bucket
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Feedback Ticket (the core workflow entity)
# ---------------------------------------------------------------------------
class FeedbackTicket(Base):
    __tablename__ = "feedback_tickets"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ticket_id = Column(String(20), nullable=False, unique=True, index=True)  # FB-YYYY-NNNNN

    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    adm_id = Column(Integer, ForeignKey("adms.id"), nullable=False, index=True)
    interaction_id = Column(Integer, ForeignKey("interactions.id"), nullable=True)

    channel = Column(String(20), nullable=False, default="telegram")  # telegram | whatsapp | web

    # Feedback input
    selected_reasons = Column(Text, nullable=True)  # JSON list of reason codes picked by ADM
    raw_feedback_text = Column(Text, nullable=True)  # free-text from ADM
    parsed_summary = Column(Text, nullable=True)  # AI-generated summary

    # AI classification
    bucket = Column(String(30), nullable=False, index=True)  # underwriting | finance | contest | operations | product
    reason_code = Column(String(10), nullable=True, index=True)  # primary reason code
    secondary_reason_codes = Column(Text, nullable=True)  # JSON list of secondary codes
    ai_confidence = Column(Float, nullable=True)  # 0.0-1.0

    # Priority & risk
    priority = Column(String(20), default="medium", index=True)  # low | medium | high | critical
    urgency_score = Column(Float, default=5.0)  # 0-10
    churn_risk = Column(String(20), nullable=True)  # high | medium | low
    sentiment = Column(String(30), nullable=True)  # frustrated | neutral | positive

    # SLA
    sla_hours = Column(Integer, default=48)
    sla_deadline = Column(DateTime, nullable=True)

    # Status tracking
    status = Column(
        String(30), default="received", index=True,
    )  # received | classified | routed | pending_dept | responded | script_generated | script_sent | closed

    # Department response
    department_response_text = Column(Text, nullable=True)
    department_responded_by = Column(String(200), nullable=True)
    department_responded_at = Column(DateTime, nullable=True)

    # AI-generated script
    generated_script = Column(Text, nullable=True)
    script_sent_at = Column(DateTime, nullable=True)

    # ADM feedback on the script
    adm_script_rating = Column(String(20), nullable=True)  # helpful | not_helpful
    adm_script_feedback = Column(Text, nullable=True)

    # Voice note
    voice_file_id = Column(String(200), nullable=True)  # Telegram voice note file ID

    # Related tickets (for multi-bucket or repeat cases)
    related_ticket_ids = Column(Text, nullable=True)  # JSON list of ticket IDs
    parent_ticket_id = Column(String(20), nullable=True)  # if this is a split ticket

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    agent = relationship("Agent")
    adm = relationship("ADM")
    interaction = relationship("Interaction")
    queue_entry = relationship("DepartmentQueue", back_populates="ticket", uselist=False)
    messages = relationship("TicketMessage", back_populates="ticket", order_by="TicketMessage.created_at")


# ---------------------------------------------------------------------------
# Ticket Message (conversation threading)
# ---------------------------------------------------------------------------
class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey("feedback_tickets.id"), nullable=False, index=True)

    sender_type = Column(String(20), nullable=False)  # "adm" | "department" | "system" | "ai"
    sender_name = Column(String(200), nullable=True)
    message_text = Column(Text, nullable=True)
    voice_file_id = Column(String(200), nullable=True)  # Telegram voice file ID if voice message

    message_type = Column(String(30), default="text")
    # "text" | "voice" | "script" | "status_change" | "escalation" | "clarification_request"

    metadata_json = Column(Text, nullable=True)  # JSON for extra data

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    ticket = relationship("FeedbackTicket", back_populates="messages")


# ---------------------------------------------------------------------------
# Department Queue (tracks ticket assignment within departments)
# ---------------------------------------------------------------------------
class DepartmentQueue(Base):
    __tablename__ = "department_queue"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    department = Column(String(30), nullable=False, index=True)  # underwriting | finance | contest | operations | product
    ticket_id = Column(Integer, ForeignKey("feedback_tickets.id"), nullable=False, index=True)
    assigned_to = Column(String(200), nullable=True)  # department user name/email
    status = Column(String(30), default="open", index=True)  # open | in_progress | responded | escalated
    sla_status = Column(String(20), default="on_track")  # on_track | warning | breached
    escalation_level = Column(Integer, default=0)  # 0=none, 1=dept head, 2=CXO

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    ticket = relationship("FeedbackTicket", back_populates="queue_entry")


# ---------------------------------------------------------------------------
# Aggregation Alert (pattern detection across feedbacks)
# ---------------------------------------------------------------------------
class AggregationAlert(Base):
    __tablename__ = "aggregation_alerts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    pattern_type = Column(String(30), nullable=False)  # district | reason | bucket
    description = Column(Text, nullable=False)
    affected_agents_count = Column(Integer, default=0)
    affected_adms_count = Column(Integer, default=0)
    region = Column(String(200), nullable=True)
    bucket = Column(String(30), nullable=True)
    reason_code = Column(String(10), nullable=True)
    ticket_ids = Column(Text, nullable=True)  # JSON list of feedback_ticket IDs
    auto_escalated = Column(Boolean, default=False)
    status = Column(String(30), default="active")  # active | reviewed | resolved
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    category = Column(String(100), nullable=False)  # term | savings | ulip | pension | child | group | health
    description = Column(Text, nullable=True)
    key_features = Column(Text, nullable=True)  # JSON string
    premium_range = Column(String(100), nullable=True)
    commission_rate = Column(String(50), nullable=True)
    target_audience = Column(String(200), nullable=True)
    selling_tips = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Agent Feedback Ticket (agent-submitted, direct to department)
# ---------------------------------------------------------------------------
class AgentFeedbackTicket(Base):
    __tablename__ = "agent_feedback_tickets"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ticket_id = Column(String(20), nullable=False, unique=True, index=True)  # AFB-YYYY-NNNNN

    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    adm_id = Column(Integer, ForeignKey("adms.id"), nullable=True, index=True)  # auto-resolved from agent's ADM

    channel = Column(String(20), nullable=False, default="telegram")  # telegram | whatsapp | web

    # Feedback input
    selected_reasons = Column(Text, nullable=True)  # JSON list of reason codes
    raw_feedback_text = Column(Text, nullable=True)
    parsed_summary = Column(Text, nullable=True)  # AI-generated summary

    # AI classification (reuses FeedbackClassifier)
    bucket = Column(String(30), nullable=False, index=True)
    reason_code = Column(String(10), nullable=True, index=True)
    secondary_reason_codes = Column(Text, nullable=True)  # JSON list
    ai_confidence = Column(Float, nullable=True)

    # Priority & risk
    priority = Column(String(20), default="medium", index=True)
    urgency_score = Column(Float, default=5.0)
    churn_risk = Column(String(20), nullable=True)
    sentiment = Column(String(30), nullable=True)

    # SLA
    sla_hours = Column(Integer, default=48)
    sla_deadline = Column(DateTime, nullable=True)

    # Status
    status = Column(
        String(30), default="received", index=True,
    )  # received | classified | routed | pending_dept | responded | closed

    # Department response
    department_response_text = Column(Text, nullable=True)
    department_responded_by = Column(String(200), nullable=True)
    department_responded_at = Column(DateTime, nullable=True)

    # ADM notification
    adm_notified = Column(Boolean, default=False)
    adm_notified_at = Column(DateTime, nullable=True)

    # Voice note
    voice_file_id = Column(String(200), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    agent = relationship("Agent", back_populates="agent_feedback_tickets")
    adm = relationship("ADM")
    queue_entry = relationship("AgentDepartmentQueue", back_populates="ticket", uselist=False)
    messages = relationship("AgentTicketMessage", back_populates="ticket", order_by="AgentTicketMessage.created_at")


# ---------------------------------------------------------------------------
# Agent Ticket Message (conversation threading for agent tickets)
# ---------------------------------------------------------------------------
class AgentTicketMessage(Base):
    __tablename__ = "agent_ticket_messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey("agent_feedback_tickets.id"), nullable=False, index=True)

    sender_type = Column(String(20), nullable=False)  # "agent" | "department" | "system" | "ai"
    sender_name = Column(String(200), nullable=True)
    message_text = Column(Text, nullable=True)
    voice_file_id = Column(String(200), nullable=True)

    message_type = Column(String(30), default="text")
    # "text" | "voice" | "photo" | "document" | "status_change"

    metadata_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    ticket = relationship("AgentFeedbackTicket", back_populates="messages")


# ---------------------------------------------------------------------------
# Agent Department Queue (tracks agent ticket assignment in departments)
# ---------------------------------------------------------------------------
class AgentDepartmentQueue(Base):
    __tablename__ = "agent_department_queue"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    department = Column(String(30), nullable=False, index=True)
    ticket_id = Column(Integer, ForeignKey("agent_feedback_tickets.id"), nullable=False, index=True)
    assigned_to = Column(String(200), nullable=True)
    status = Column(String(30), default="open", index=True)  # open | in_progress | responded | escalated
    sla_status = Column(String(20), default="on_track")
    escalation_level = Column(Integer, default=0)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    ticket = relationship("AgentFeedbackTicket", back_populates="queue_entry")
