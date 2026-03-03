"""
Pydantic schemas for request/response validation.
"""

from datetime import datetime, date
from typing import Optional, List, Any
from pydantic import BaseModel, Field


# ============================= Agent Schemas =============================

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    phone: str = Field(..., min_length=10, max_length=20)
    email: Optional[str] = None
    location: str = Field(..., min_length=2)
    state: Optional[str] = None
    language: str = "Hindi"
    lifecycle_state: str = "dormant"
    dormancy_reason: Optional[str] = None
    dormancy_duration_days: int = 0
    last_contact_date: Optional[date] = None
    last_policy_sold_date: Optional[date] = None
    assigned_adm_id: Optional[int] = None
    engagement_score: float = 0.0
    license_number: Optional[str] = None
    date_of_joining: Optional[date] = None
    specialization: Optional[str] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    location: Optional[str] = None
    state: Optional[str] = None
    language: Optional[str] = None
    lifecycle_state: Optional[str] = None
    dormancy_reason: Optional[str] = None
    dormancy_duration_days: Optional[int] = None
    last_contact_date: Optional[date] = None
    last_policy_sold_date: Optional[date] = None
    assigned_adm_id: Optional[int] = None
    engagement_score: Optional[float] = None
    license_number: Optional[str] = None
    specialization: Optional[str] = None


class AgentResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: Optional[str] = None
    location: str
    state: Optional[str] = None
    language: str
    lifecycle_state: str
    dormancy_reason: Optional[str] = None
    dormancy_duration_days: int
    last_contact_date: Optional[date] = None
    last_policy_sold_date: Optional[date] = None
    assigned_adm_id: Optional[int] = None
    engagement_score: float
    license_number: Optional[str] = None
    date_of_joining: Optional[date] = None
    specialization: Optional[str] = None
    # Performance fields
    total_policies_sold: int = 0
    total_premium_generated: Optional[float] = None
    policies_last_12_months: int = 0
    premium_last_12_months: Optional[float] = None
    avg_ticket_size: Optional[float] = None
    best_month_premium: Optional[float] = None
    persistency_ratio: Optional[float] = None
    # Activity fields
    last_login_date: Optional[date] = None
    last_training_date: Optional[date] = None
    last_proposal_date: Optional[date] = None
    days_since_last_activity: Optional[int] = None
    # Contact fields
    contact_attempts: Optional[int] = None
    contact_responses: Optional[int] = None
    response_rate: float = 0.0
    avg_response_time_hours: Optional[float] = None
    preferred_channel: Optional[str] = None
    # Demographics
    age: Optional[int] = None
    education_level: Optional[str] = None
    years_in_insurance: float = 0.0
    previous_insurer: Optional[str] = None
    is_poached: Optional[bool] = None
    work_type: Optional[str] = None
    has_app_installed: Optional[bool] = None
    digital_savviness_score: Optional[float] = None
    # Cohort classification fields
    cohort_segment: Optional[str] = None
    reactivation_score: Optional[float] = None
    engagement_strategy: Optional[str] = None
    churn_risk_level: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentBulkImport(BaseModel):
    agents: List[AgentCreate]


# ============================= ADM Schemas =============================

class ADMCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    phone: str = Field(..., min_length=10, max_length=20)
    email: Optional[str] = None
    region: str
    language: str = "Hindi,English"
    max_capacity: int = 50
    telegram_chat_id: Optional[str] = None
    whatsapp_number: Optional[str] = None


class ADMUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    region: Optional[str] = None
    language: Optional[str] = None
    max_capacity: Optional[int] = None
    performance_score: Optional[float] = None
    telegram_chat_id: Optional[str] = None
    whatsapp_number: Optional[str] = None


class ADMResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: Optional[str] = None
    region: str
    language: str
    active_agent_count: int
    max_capacity: int
    performance_score: float
    telegram_chat_id: Optional[str] = None
    whatsapp_number: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ADMBulkImport(BaseModel):
    adms: List[ADMCreate]


class ADMPerformance(BaseModel):
    adm_id: int
    adm_name: str
    total_agents: int
    contacted_agents: int
    engaged_agents: int
    active_agents: int
    activation_rate: float
    avg_engagement_score: float
    total_interactions: int
    pending_followups: int
    overdue_followups: int


# ========================= Interaction Schemas =========================

class InteractionCreate(BaseModel):
    agent_id: int
    adm_id: int
    type: str = Field(..., pattern="^(call|whatsapp|visit|telegram)$")
    outcome: str
    notes: Optional[str] = None
    duration_minutes: Optional[int] = None
    feedback_category: Optional[str] = None
    feedback_subcategory: Optional[str] = None
    sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0)
    follow_up_date: Optional[date] = None


class InteractionUpdate(BaseModel):
    outcome: Optional[str] = None
    notes: Optional[str] = None
    follow_up_date: Optional[date] = None
    follow_up_status: Optional[str] = None


class InteractionResponse(BaseModel):
    id: int
    agent_id: int
    adm_id: int
    type: str
    outcome: str
    notes: Optional[str] = None
    duration_minutes: Optional[int] = None
    feedback_category: Optional[str] = None
    feedback_subcategory: Optional[str] = None
    sentiment_score: Optional[float] = None
    follow_up_date: Optional[date] = None
    follow_up_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# =========================== Feedback Schemas ===========================

class FeedbackCreate(BaseModel):
    agent_id: int
    adm_id: int
    interaction_id: Optional[int] = None
    category: str
    subcategory: Optional[str] = None
    raw_text: Optional[str] = None
    sentiment: Optional[str] = None
    priority: str = "medium"


class FeedbackUpdate(BaseModel):
    status: Optional[str] = None
    action_taken: Optional[str] = None
    priority: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: int
    agent_id: int
    adm_id: int
    interaction_id: Optional[int] = None
    category: str
    subcategory: Optional[str] = None
    raw_text: Optional[str] = None
    ai_summary: Optional[str] = None
    sentiment: Optional[str] = None
    priority: str
    status: str
    action_taken: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackAnalytics(BaseModel):
    total_feedbacks: int
    by_category: dict
    by_priority: dict
    by_status: dict
    by_sentiment: dict
    top_subcategories: list
    avg_resolution_time_hours: Optional[float] = None


# ======================== Diary Entry Schemas ========================

class DiaryEntryCreate(BaseModel):
    adm_id: int
    agent_id: Optional[int] = None
    scheduled_date: date
    scheduled_time: Optional[str] = None
    entry_type: str  # follow_up | first_contact | training | escalation | review
    notes: Optional[str] = None


class DiaryEntryUpdate(BaseModel):
    scheduled_date: Optional[date] = None
    scheduled_time: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    completion_notes: Optional[str] = None


class DiaryEntryResponse(BaseModel):
    id: int
    adm_id: int
    agent_id: Optional[int] = None
    scheduled_date: date
    scheduled_time: Optional[str] = None
    entry_type: str
    notes: Optional[str] = None
    status: str
    reminder_sent: bool
    completion_notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ====================== Daily Briefing Schemas ======================

class DailyBriefingResponse(BaseModel):
    id: int
    adm_id: int
    date: date
    priority_agents: Optional[Any] = None
    pending_followups: int
    new_assignments: int
    overdue_followups: int
    summary_text: Optional[str] = None
    action_items: Optional[Any] = None
    sent_via: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ===================== Training Progress Schemas =====================

class TrainingModuleInfo(BaseModel):
    module_name: str
    module_category: str
    description: str
    questions_count: int


class QuizAnswer(BaseModel):
    adm_id: int
    module_name: str
    module_category: str
    answers: dict  # question_id -> selected_answer


class TrainingProgressResponse(BaseModel):
    id: int
    adm_id: int
    module_name: str
    module_category: str
    score: float
    completed: bool
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LeaderboardEntry(BaseModel):
    adm_id: int
    adm_name: str
    region: str
    total_score: float
    modules_completed: int
    total_modules: int


# ======================== Analytics Schemas ========================

class DashboardKPIs(BaseModel):
    total_agents: int
    dormant_agents: int
    at_risk_agents: int
    contacted_agents: int
    engaged_agents: int
    trained_agents: int
    active_agents: int
    activation_rate: float
    total_adms: int
    total_interactions: int
    pending_followups: int
    overdue_followups: int
    avg_engagement_score: float


class ActivationFunnel(BaseModel):
    dormant: int
    at_risk: int
    contacted: int
    engaged: int
    trained: int
    active: int
    conversion_rates: dict  # stage -> percentage


class DormancyBreakdown(BaseModel):
    by_reason: dict
    by_duration: dict
    by_location: dict
    by_state: dict


class FeedbackTrend(BaseModel):
    period: str
    category: str
    count: int


# ======================== Assignment Schemas ========================

class AssignmentRequest(BaseModel):
    agent_ids: Optional[List[int]] = None  # if None, auto-select unassigned
    adm_id: Optional[int] = None  # if None, auto-assign
    strategy: str = "balanced"  # balanced | geographic | language


class AssignmentResult(BaseModel):
    assigned_count: int
    assignments: List[dict]  # [{agent_id, adm_id, reason}]
    errors: List[str]


# ======================== AI / Chat Schemas ========================

class ProductQARequest(BaseModel):
    question: str
    context: Optional[str] = None  # additional context like agent location, product interest


class ProductQAResponse(BaseModel):
    answer: str
    confidence: float
    suggested_products: Optional[List[str]] = None
    follow_up_questions: Optional[List[str]] = None


class FeedbackAnalysisRequest(BaseModel):
    raw_text: str
    agent_context: Optional[str] = None


class FeedbackAnalysisResponse(BaseModel):
    category: str
    subcategory: str
    sentiment: str
    priority: str
    summary: str
    recommended_actions: List[str]


class ActionRecommendationRequest(BaseModel):
    agent_id: int
    context: Optional[str] = None


class ActionRecommendationResponse(BaseModel):
    recommended_actions: List[dict]
    priority: str
    reasoning: str


# ======================== Auth Schemas ========================

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    adm_id: Optional[int] = None
    name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ======================== Product Schemas ========================

class ProductCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    category: str
    description: Optional[str] = None
    key_features: Optional[str] = None
    premium_range: Optional[str] = None
    commission_rate: Optional[str] = None
    target_audience: Optional[str] = None
    selling_tips: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    key_features: Optional[str] = None
    premium_range: Optional[str] = None
    commission_rate: Optional[str] = None
    target_audience: Optional[str] = None
    selling_tips: Optional[str] = None
    active: Optional[bool] = None


class ProductResponse(BaseModel):
    id: int
    name: str
    category: str
    description: Optional[str] = None
    key_features: Optional[str] = None
    premium_range: Optional[str] = None
    commission_rate: Optional[str] = None
    target_audience: Optional[str] = None
    selling_tips: Optional[str] = None
    active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ======================== Onboarding Schemas ========================

class OnboardingStart(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    phone: str = Field(..., min_length=10, max_length=20)
    email: Optional[str] = None
    location: str
    state: Optional[str] = None
    language: str = "Hindi"
    assigned_adm_id: Optional[int] = None


class OnboardingAdvance(BaseModel):
    new_status: str  # documents_submitted | verified | active | rejected


class OnboardingAgentResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: Optional[str] = None
    location: str
    state: Optional[str] = None
    onboarding_status: Optional[str] = None
    assigned_adm_id: Optional[int] = None
    assigned_adm_name: Optional[str] = None
    onboarding_started_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ==================== Feedback Ticket Schemas ====================

class FeedbackTicketSubmit(BaseModel):
    """ADM submits feedback — either selected reasons, free text, or both."""
    agent_id: int
    adm_id: int
    interaction_id: Optional[int] = None
    channel: str = "telegram"  # telegram | whatsapp | web
    selected_reason_codes: Optional[List[str]] = None  # e.g., ["UW-01", "FIN-03"]
    raw_feedback_text: Optional[str] = None  # free-text from ADM
    voice_file_id: Optional[str] = None  # Telegram voice note file ID


class FeedbackTicketResponse(BaseModel):
    id: int
    ticket_id: str
    agent_id: int
    adm_id: int
    interaction_id: Optional[int] = None
    channel: str
    selected_reasons: Optional[str] = None
    raw_feedback_text: Optional[str] = None
    parsed_summary: Optional[str] = None
    bucket: str
    reason_code: Optional[str] = None
    secondary_reason_codes: Optional[str] = None
    ai_confidence: Optional[float] = None
    priority: str
    urgency_score: Optional[float] = None
    churn_risk: Optional[str] = None
    sentiment: Optional[str] = None
    sla_hours: int
    sla_deadline: Optional[datetime] = None
    status: str
    department_response_text: Optional[str] = None
    department_responded_by: Optional[str] = None
    department_responded_at: Optional[datetime] = None
    generated_script: Optional[str] = None
    script_sent_at: Optional[datetime] = None
    adm_script_rating: Optional[str] = None
    voice_file_id: Optional[str] = None
    parent_ticket_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Enriched fields
    agent_name: Optional[str] = None
    adm_name: Optional[str] = None
    bucket_display: Optional[str] = None
    reason_display: Optional[str] = None
    sla_status: Optional[str] = None

    model_config = {"from_attributes": True}


class DepartmentResponseSubmit(BaseModel):
    """Department team responds to a feedback ticket."""
    response_text: str
    responded_by: str  # name or email of dept person


class ScriptRating(BaseModel):
    """ADM rates the generated script."""
    rating: str  # helpful | not_helpful
    feedback: Optional[str] = None


class ReasonTaxonomyResponse(BaseModel):
    id: int
    code: str
    bucket: str
    reason_name: str
    description: Optional[str] = None
    sub_reasons: Optional[str] = None
    typical_sla_hours: int
    display_order: int
    active: bool

    model_config = {"from_attributes": True}


class DepartmentQueueResponse(BaseModel):
    id: int
    department: str
    ticket_id: int
    assigned_to: Optional[str] = None
    status: str
    sla_status: str
    escalation_level: int
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AggregationAlertResponse(BaseModel):
    id: int
    pattern_type: str
    description: str
    affected_agents_count: int
    affected_adms_count: int
    region: Optional[str] = None
    bucket: Optional[str] = None
    reason_code: Optional[str] = None
    auto_escalated: bool
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketMessageCreate(BaseModel):
    """Create a message in a ticket thread."""
    sender_type: str  # "department" | "adm"
    sender_name: str
    message_text: str
    message_type: Optional[str] = "text"  # "text" | "clarification_request" | "photo" | "document" | "voice"
    voice_file_id: Optional[str] = None  # Telegram file_id for voice/photo/document
    metadata_json: Optional[str] = None  # JSON string for extra data (file name, mime type, etc.)


# ==================== Agent Portal Schemas ====================

class AgentRegister(BaseModel):
    """Agent registers via Telegram bot by providing phone number."""
    phone: str = Field(..., min_length=10, max_length=20)
    telegram_chat_id: str


class AgentProfileResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: Optional[str] = None
    location: str
    state: Optional[str] = None
    language: str
    lifecycle_state: str
    engagement_score: float
    cohort_segment: Optional[str] = None
    reactivation_score: float = 0.0
    engagement_strategy: Optional[str] = None
    churn_risk_level: Optional[str] = None
    assigned_adm_id: Optional[int] = None
    assigned_adm_name: Optional[str] = None
    total_policies_sold: int = 0
    premium_last_12_months: float = 0.0
    last_contact_date: Optional[date] = None
    last_training_date: Optional[date] = None
    telegram_registered: bool = False

    model_config = {"from_attributes": True}


class AgentFeedbackSubmit(BaseModel):
    """Agent submits feedback directly to a department."""
    agent_id: int
    channel: str = "telegram"
    selected_reason_codes: Optional[List[str]] = None
    raw_feedback_text: Optional[str] = None
    voice_file_id: Optional[str] = None


class AgentFeedbackTicketResponse(BaseModel):
    id: int
    ticket_id: str
    agent_id: int
    adm_id: Optional[int] = None
    channel: str
    selected_reasons: Optional[str] = None
    raw_feedback_text: Optional[str] = None
    parsed_summary: Optional[str] = None
    bucket: str
    reason_code: Optional[str] = None
    priority: str
    sentiment: Optional[str] = None
    sla_hours: int
    sla_deadline: Optional[datetime] = None
    status: str
    department_response_text: Optional[str] = None
    department_responded_at: Optional[datetime] = None
    adm_notified: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Enriched
    agent_name: Optional[str] = None
    adm_name: Optional[str] = None
    bucket_display: Optional[str] = None
    reason_display: Optional[str] = None
    sla_status: Optional[str] = None

    model_config = {"from_attributes": True}


class AgentTicketMessageCreate(BaseModel):
    """Agent or department creates a message on an agent ticket."""
    sender_type: str  # "agent" | "department"
    sender_name: str
    message_text: str
    message_type: Optional[str] = "text"
    voice_file_id: Optional[str] = None
    metadata_json: Optional[str] = None


# ==================== Cohort Analysis Schemas ====================

class CohortClassificationResult(BaseModel):
    """Result of classifying a single agent into a cohort."""
    agent_id: int
    agent_name: str
    cohort_segment: str
    reactivation_score: float
    engagement_strategy: str
    churn_risk_level: str
    score_breakdown: dict  # sub-scores
    first_message: Optional[str] = None


class CohortSummary(BaseModel):
    """Overview of cohort distribution across all agents."""
    total_agents: int
    segment_distribution: dict  # segment -> count
    avg_reactivation_score: float
    strategy_distribution: dict  # strategy -> count
    risk_distribution: dict  # risk_level -> count


class CohortSegmentDetail(BaseModel):
    """Detail for a specific cohort segment."""
    segment: str
    segment_display: str
    count: int
    avg_reactivation_score: float
    recommended_strategy: str
    agents: List[dict]


class BulkUploadResult(BaseModel):
    """Result of bulk agent upload with cohort classification."""
    total_uploaded: int
    created: int
    updated: int
    classified: int
    errors: List[str]
    segment_summary: dict  # segment -> count
