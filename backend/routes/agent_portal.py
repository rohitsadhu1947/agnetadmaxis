"""
Agent Portal routes — agent-facing API endpoints.

Handles agent registration, profile, feedback submission,
ticket tracking, training modules, and AI product Q&A.
"""

import json
import logging
from datetime import datetime
from typing import Optional, List

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from config import settings
from database import get_db
from models import (
    Agent, ADM, AgentFeedbackTicket, AgentTicketMessage,
    AgentDepartmentQueue, Product, ReasonTaxonomy,
)
from schemas import (
    AgentRegister, AgentProfileResponse, AgentFeedbackSubmit,
    AgentFeedbackTicketResponse, AgentTicketMessageCreate,
)
from services.feedback_classifier import feedback_classifier, FeedbackClassifier, BUCKET_DISPLAY_NAMES
from services.ai_service import ai_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Telegram notification helper
# ---------------------------------------------------------------------------

async def _notify_adm_of_agent_feedback(
    ticket: AgentFeedbackTicket,
    agent: Agent,
    adm: ADM,
):
    """Notify the ADM via Telegram that their agent submitted feedback."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — cannot notify ADM of agent feedback")
        return

    if not adm or not adm.telegram_chat_id:
        logger.warning(f"ADM {adm.id if adm else '?'} has no telegram_chat_id — cannot notify")
        return

    bucket_label = BUCKET_DISPLAY_NAMES.get(ticket.bucket, ticket.bucket or "")
    message = (
        f"📩 *Agent Feedback Received — {ticket.ticket_id}*\n\n"
        f"*Agent:* {agent.name}\n"
        f"*Phone:* {agent.phone}\n"
        f"*Department:* {bucket_label}\n"
        f"*Priority:* {ticket.priority}\n"
        f"*Reason:* {ticket.reason_code or '—'}\n\n"
        f"📝 *Summary:*\n{ticket.parsed_summary or ticket.raw_feedback_text or '—'}\n\n"
        f"_Ticket has been routed to the {bucket_label} department._"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": adm.telegram_chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                logger.info(f"ADM {adm.id} notified of agent feedback ticket {ticket.ticket_id}")
            else:
                logger.error(f"Telegram send failed ({resp.status_code}): {resp.text}")
    except Exception as e:
        logger.error(f"Error notifying ADM of agent feedback: {e}")


router = APIRouter(prefix="/agent-portal", tags=["Agent Portal"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_agent_ticket_id(db: Session) -> str:
    """Generate next agent feedback ticket ID: AFB-YYYY-NNNNN."""
    year = datetime.utcnow().year
    prefix = f"AFB-{year}-"
    last = (
        db.query(AgentFeedbackTicket)
        .filter(AgentFeedbackTicket.ticket_id.like(f"{prefix}%"))
        .order_by(desc(AgentFeedbackTicket.id))
        .first()
    )
    if last:
        last_num = int(last.ticket_id.split("-")[-1])
        next_num = last_num + 1
    else:
        next_num = 1
    return f"{prefix}{next_num:05d}"


def _enrich_agent_ticket(ticket: AgentFeedbackTicket, db: Session) -> dict:
    """Add display names and computed fields to an agent feedback ticket."""
    agent = db.query(Agent).filter(Agent.id == ticket.agent_id).first()
    adm = db.query(ADM).filter(ADM.id == ticket.adm_id).first() if ticket.adm_id else None

    # Build reason lookup
    _reason_lookup: dict = {}
    try:
        all_reasons = db.query(ReasonTaxonomy).all()
        _reason_lookup = {r.code: r.reason_name for r in all_reasons}
    except Exception:
        pass

    # Reason display name
    reason_display = None
    if ticket.reason_code:
        reason_display = _reason_lookup.get(ticket.reason_code, ticket.reason_code)

    # SLA status
    sla_status = "on_track"
    if ticket.sla_deadline:
        now = datetime.utcnow()
        if ticket.status in ("responded", "closed"):
            sla_status = "completed"
        elif now > ticket.sla_deadline:
            sla_status = "breached"
        elif now > ticket.sla_deadline - (ticket.sla_deadline - ticket.created_at) * 0.25:
            sla_status = "warning"

    data = {
        "id": ticket.id,
        "ticket_id": ticket.ticket_id,
        "agent_id": ticket.agent_id,
        "adm_id": ticket.adm_id,
        "channel": ticket.channel,
        "selected_reasons": ticket.selected_reasons,
        "raw_feedback_text": ticket.raw_feedback_text,
        "parsed_summary": ticket.parsed_summary,
        "bucket": ticket.bucket,
        "reason_code": ticket.reason_code,
        "priority": ticket.priority,
        "sentiment": ticket.sentiment,
        "sla_hours": ticket.sla_hours,
        "sla_deadline": ticket.sla_deadline,
        "status": ticket.status,
        "department_response_text": ticket.department_response_text,
        "department_responded_at": ticket.department_responded_at,
        "adm_notified": ticket.adm_notified,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        # Enriched
        "agent_name": agent.name if agent else None,
        "adm_name": adm.name if adm else None,
        "bucket_display": BUCKET_DISPLAY_NAMES.get(ticket.bucket, ticket.bucket),
        "reason_display": reason_display,
        "sla_status": sla_status,
    }

    # Message count
    try:
        message_count = (
            db.query(AgentTicketMessage)
            .filter(AgentTicketMessage.ticket_id == ticket.id)
            .count()
        )
        data["message_count"] = message_count
    except Exception:
        data["message_count"] = 0

    return data


# ---------------------------------------------------------------------------
# 1. Agent Registration
# ---------------------------------------------------------------------------

@router.post("/register")
def register_agent(
    data: AgentRegister,
    db: Session = Depends(get_db),
):
    """
    Agent registers by providing phone + telegram_chat_id.
    Looks up agent by phone, links telegram_chat_id, sets telegram_registered=True.
    """
    agent = db.query(Agent).filter(Agent.phone == data.phone).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found with this phone number")

    agent.telegram_chat_id = data.telegram_chat_id
    agent.telegram_registered = True
    agent.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(agent)

    # Build profile response
    adm = db.query(ADM).filter(ADM.id == agent.assigned_adm_id).first() if agent.assigned_adm_id else None

    return {
        "id": agent.id,
        "name": agent.name,
        "phone": agent.phone,
        "email": agent.email,
        "location": agent.location,
        "state": agent.state,
        "language": agent.language,
        "lifecycle_state": agent.lifecycle_state,
        "engagement_score": agent.engagement_score,
        "cohort_segment": agent.cohort_segment,
        "reactivation_score": agent.reactivation_score,
        "engagement_strategy": agent.engagement_strategy,
        "churn_risk_level": agent.churn_risk_level,
        "assigned_adm_id": agent.assigned_adm_id,
        "assigned_adm_name": adm.name if adm else None,
        "total_policies_sold": agent.total_policies_sold,
        "premium_last_12_months": agent.premium_last_12_months,
        "last_contact_date": agent.last_contact_date,
        "last_training_date": agent.last_training_date,
        "telegram_registered": agent.telegram_registered,
    }


# ---------------------------------------------------------------------------
# 2. Agent Profile
# ---------------------------------------------------------------------------

@router.get("/profile/{agent_id}")
def get_agent_profile(
    agent_id: int,
    db: Session = Depends(get_db),
):
    """Returns agent profile with cohort info and assigned ADM name."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    adm = db.query(ADM).filter(ADM.id == agent.assigned_adm_id).first() if agent.assigned_adm_id else None

    return {
        "id": agent.id,
        "name": agent.name,
        "phone": agent.phone,
        "email": agent.email,
        "location": agent.location,
        "state": agent.state,
        "language": agent.language,
        "lifecycle_state": agent.lifecycle_state,
        "engagement_score": agent.engagement_score,
        "cohort_segment": agent.cohort_segment,
        "reactivation_score": agent.reactivation_score,
        "engagement_strategy": agent.engagement_strategy,
        "churn_risk_level": agent.churn_risk_level,
        "assigned_adm_id": agent.assigned_adm_id,
        "assigned_adm_name": adm.name if adm else None,
        "total_policies_sold": agent.total_policies_sold,
        "premium_last_12_months": agent.premium_last_12_months,
        "last_contact_date": agent.last_contact_date,
        "last_training_date": agent.last_training_date,
        "telegram_registered": agent.telegram_registered,
    }


# ---------------------------------------------------------------------------
# 3. Agent Feedback Submission
# ---------------------------------------------------------------------------

@router.post("/feedback/submit", status_code=201)
async def submit_agent_feedback(
    data: AgentFeedbackSubmit,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Agent submits feedback directly to a department.

    AI classifies the feedback, creates a ticket, routes to the appropriate
    department queue, and notifies the agent's ADM via Telegram.
    """
    # Validate agent
    agent = db.query(Agent).filter(Agent.id == data.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not data.selected_reason_codes and not data.raw_feedback_text:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one reason code or feedback text",
        )

    # Auto-resolve ADM from agent's assignment
    adm_id = agent.assigned_adm_id
    adm = db.query(ADM).filter(ADM.id == adm_id).first() if adm_id else None

    # Classify feedback
    classification = await feedback_classifier.classify_feedback(
        raw_text=data.raw_feedback_text or "",
        selected_reason_codes=data.selected_reason_codes,
        agent_name=agent.name,
        agent_location=agent.location,
        agent_state=agent.lifecycle_state,
    )

    bucket = classification["bucket"]
    priority = classification.get("priority", "medium")
    sla_hours = feedback_classifier.get_sla_hours(bucket, priority)
    sla_deadline = FeedbackClassifier.compute_sla_deadline(bucket, priority)

    # Generate ticket ID
    ticket_id = _generate_agent_ticket_id(db)

    # Create ticket
    ticket = AgentFeedbackTicket(
        ticket_id=ticket_id,
        agent_id=data.agent_id,
        adm_id=adm_id,
        channel=data.channel,
        selected_reasons=json.dumps(data.selected_reason_codes) if data.selected_reason_codes else None,
        raw_feedback_text=data.raw_feedback_text,
        parsed_summary=classification.get("parsed_summary"),
        bucket=bucket,
        reason_code=classification.get("reason_code"),
        secondary_reason_codes=json.dumps(classification.get("secondary_reason_codes", [])),
        ai_confidence=classification.get("confidence"),
        priority=priority,
        urgency_score=classification.get("urgency_score", 5.0),
        churn_risk=classification.get("churn_risk"),
        sentiment=classification.get("sentiment"),
        sla_hours=sla_hours,
        sla_deadline=sla_deadline,
        status="routed",
        voice_file_id=data.voice_file_id,
    )
    db.add(ticket)
    db.flush()

    # Create initial agent message in the conversation thread
    try:
        initial_msg = AgentTicketMessage(
            ticket_id=ticket.id,
            sender_type="agent",
            sender_name=agent.name,
            message_text=data.raw_feedback_text or f"Submitted feedback with reason codes: {', '.join(data.selected_reason_codes or [])}",
            voice_file_id=data.voice_file_id,
            message_type="voice" if data.voice_file_id else "text",
        )
        db.add(initial_msg)
    except Exception as e:
        logger.warning(f"Could not create initial AgentTicketMessage: {e}")

    # Create department queue entry
    queue_entry = AgentDepartmentQueue(
        department=bucket,
        ticket_id=ticket.id,
        status="open",
        sla_status="on_track",
    )
    db.add(queue_entry)

    db.commit()
    db.refresh(ticket)

    # Notify ADM via Telegram (background task — non-blocking)
    if adm:
        background_tasks.add_task(_notify_adm_of_agent_feedback, ticket, agent, adm)

    return _enrich_agent_ticket(ticket, db)


# ---------------------------------------------------------------------------
# 4. List Agent Tickets
# ---------------------------------------------------------------------------

@router.get("/feedback/tickets/{agent_id}")
def list_agent_tickets(
    agent_id: int,
    status: Optional[str] = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List all feedback tickets for an agent."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    query = db.query(AgentFeedbackTicket).filter(
        AgentFeedbackTicket.agent_id == agent_id
    )
    if status:
        query = query.filter(AgentFeedbackTicket.status == status)

    total = query.count()
    tickets = (
        query.order_by(desc(AgentFeedbackTicket.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {
        "tickets": [_enrich_agent_ticket(t, db) for t in tickets],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


# ---------------------------------------------------------------------------
# 5. Single Ticket Detail
# ---------------------------------------------------------------------------

@router.get("/feedback/ticket/{ticket_id}")
def get_agent_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
):
    """Get a single agent feedback ticket by ticket_id (e.g., AFB-2026-00001) with messages."""
    ticket = db.query(AgentFeedbackTicket).filter(
        AgentFeedbackTicket.ticket_id == ticket_id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    enriched = _enrich_agent_ticket(ticket, db)

    # Include conversation messages
    try:
        messages = (
            db.query(AgentTicketMessage)
            .filter(AgentTicketMessage.ticket_id == ticket.id)
            .order_by(AgentTicketMessage.created_at.asc())
            .all()
        )
        enriched["messages"] = [
            {
                "id": m.id,
                "sender_type": m.sender_type,
                "sender_name": m.sender_name,
                "message_text": m.message_text,
                "voice_file_id": m.voice_file_id,
                "message_type": m.message_type,
                "metadata_json": m.metadata_json,
                "created_at": m.created_at,
            }
            for m in messages
        ]
    except Exception:
        enriched["messages"] = []

    return enriched


# ---------------------------------------------------------------------------
# 6. Ticket Reply (Agent or Department)
# ---------------------------------------------------------------------------

@router.post("/feedback/ticket/{ticket_id}/reply")
def reply_to_agent_ticket(
    ticket_id: str,
    data: AgentTicketMessageCreate,
    db: Session = Depends(get_db),
):
    """Agent or department replies to a ticket thread."""
    ticket = db.query(AgentFeedbackTicket).filter(
        AgentFeedbackTicket.ticket_id == ticket_id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    msg = AgentTicketMessage(
        ticket_id=ticket.id,
        sender_type=data.sender_type,
        sender_name=data.sender_name,
        message_text=data.message_text,
        message_type=data.message_type or "text",
        voice_file_id=data.voice_file_id,
        metadata_json=data.metadata_json,
    )
    db.add(msg)

    # Update ticket status based on sender
    if data.sender_type == "department":
        ticket.status = "responded"
        ticket.department_response_text = data.message_text
        ticket.department_responded_by = data.sender_name
        ticket.department_responded_at = datetime.utcnow()

        # Update queue entry
        queue = db.query(AgentDepartmentQueue).filter(
            AgentDepartmentQueue.ticket_id == ticket.id
        ).first()
        if queue:
            queue.status = "responded"

    elif data.sender_type == "agent":
        # Agent follow-up — reopen if needed
        if ticket.status in ("responded", "closed"):
            ticket.status = "received"
            queue = db.query(AgentDepartmentQueue).filter(
                AgentDepartmentQueue.ticket_id == ticket.id
            ).first()
            if queue:
                queue.status = "open"

    ticket.updated_at = datetime.utcnow()
    db.commit()

    return {"status": "ok", "message_id": msg.id, "ticket_id": ticket_id}


# ---------------------------------------------------------------------------
# 7. Training Modules
# ---------------------------------------------------------------------------

@router.get("/training/modules")
def list_training_modules(
    category: Optional[str] = Query(None, description="Filter by product category"),
    db: Session = Depends(get_db),
):
    """Returns available training modules based on product catalog."""
    query = db.query(Product).filter(Product.active == True)
    if category:
        query = query.filter(Product.category == category)

    products = query.order_by(Product.category, Product.name).all()

    modules = []
    for p in products:
        key_features = []
        if p.key_features:
            try:
                key_features = json.loads(p.key_features)
            except (json.JSONDecodeError, TypeError):
                key_features = []

        modules.append({
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "description": p.description,
            "key_features": key_features,
            "premium_range": p.premium_range,
            "commission_rate": p.commission_rate,
            "target_audience": p.target_audience,
            "selling_tips": p.selling_tips,
        })

    return {"modules": modules, "total": len(modules)}


# ---------------------------------------------------------------------------
# 8. AI Product Q&A
# ---------------------------------------------------------------------------

@router.post("/ask")
async def ask_product_question(
    data: dict,
    db: Session = Depends(get_db),
):
    """AI-powered product Q&A for agents. Accepts JSON body: {"question": "...", "context": "..."}."""
    question = data.get("question", "").strip()
    if not question or len(question) < 3:
        raise HTTPException(status_code=400, detail="question must be at least 3 characters")
    try:
        result = await ai_service.answer_product_question(
            question=question,
            context=data.get("context"),
        )
        return result
    except Exception as e:
        logger.error(f"AI product Q&A failed: {e}")
        raise HTTPException(
            status_code=503,
            detail="AI service temporarily unavailable. Please try again.",
        )
