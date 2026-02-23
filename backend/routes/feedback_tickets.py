"""
Feedback Ticket routes — the core workflow API.

Handles ticket submission, classification, department response,
script generation, and delivery.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List

import io
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from config import settings
from database import get_db, SessionLocal
from models import (
    FeedbackTicket, DepartmentQueue, ReasonTaxonomy,
    AggregationAlert, Agent, ADM, TicketMessage,
)
from schemas import (
    FeedbackTicketSubmit, FeedbackTicketResponse,
    DepartmentResponseSubmit, ScriptRating,
    ReasonTaxonomyResponse, DepartmentQueueResponse,
    AggregationAlertResponse, TicketMessageCreate,
)
from services.feedback_classifier import feedback_classifier, BUCKET_DISPLAY_NAMES

logger = logging.getLogger(__name__)


async def _push_script_to_adm(ticket: FeedbackTicket, script: str, db: Session):
    """Send the generated communication script to the ADM via Telegram."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — cannot push script to ADM")
        return

    adm = db.query(ADM).filter(ADM.id == ticket.adm_id).first()
    if not adm or not adm.telegram_chat_id:
        logger.warning(f"ADM {ticket.adm_id} has no telegram_chat_id — cannot push script")
        return

    agent = db.query(Agent).filter(Agent.id == ticket.agent_id).first()
    agent_name = agent.name if agent else "Agent"
    bucket_label = BUCKET_DISPLAY_NAMES.get(ticket.bucket, ticket.bucket or "")

    message = (
        f"📋 *Response Ready — {ticket.ticket_id}*\n\n"
        f"*Agent:* {agent_name}\n"
        f"*Department:* {bucket_label}\n"
        f"*Reason:* {ticket.reason_code or '—'}\n\n"
        f"📝 *Communication Script:*\n\n"
        f"{script}\n\n"
        f"_Use this script when speaking to the agent. "
        f"Reply /feedback to submit new feedback._"
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
                # Mark script as sent
                ticket.script_sent_at = datetime.utcnow()
                ticket.status = "script_sent"
                db.commit()
                logger.info(f"Script pushed to ADM {adm.id} for ticket {ticket.ticket_id}")
            else:
                logger.error(f"Telegram send failed ({resp.status_code}): {resp.text}")
    except Exception as e:
        logger.error(f"Error pushing script to ADM: {e}")

router = APIRouter(prefix="/feedback-tickets", tags=["Feedback Tickets"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_ticket_id(db: Session) -> str:
    """Generate next ticket ID: FB-YYYY-NNNNN."""
    year = datetime.utcnow().year
    prefix = f"FB-{year}-"
    last = (
        db.query(FeedbackTicket)
        .filter(FeedbackTicket.ticket_id.like(f"{prefix}%"))
        .order_by(desc(FeedbackTicket.id))
        .first()
    )
    if last:
        last_num = int(last.ticket_id.split("-")[-1])
        next_num = last_num + 1
    else:
        next_num = 1
    return f"{prefix}{next_num:05d}"


def _reason_name(db: Session, code: str) -> str:
    """Look up human-readable reason name for a code. Returns the code itself as fallback."""
    try:
        r = db.query(ReasonTaxonomy).filter(ReasonTaxonomy.code == code).first()
        return r.reason_name if r else code
    except Exception:
        return code


def _enrich_ticket(ticket: FeedbackTicket, db: Session) -> dict:
    """Add display names and computed fields to a ticket."""
    agent = db.query(Agent).filter(Agent.id == ticket.agent_id).first()
    adm = db.query(ADM).filter(ADM.id == ticket.adm_id).first()

    # Build a lookup of all reason codes → display names (single query)
    _reason_lookup: dict = {}
    try:
        all_reasons = db.query(ReasonTaxonomy).all()
        _reason_lookup = {r.code: r.reason_name for r in all_reasons}
    except Exception:
        pass  # Table may not exist yet

    # Reason display name
    reason_display = None
    if ticket.reason_code:
        reason_display = _reason_lookup.get(ticket.reason_code, ticket.reason_code)

    # SLA status
    sla_status = "on_track"
    if ticket.sla_deadline:
        now = datetime.utcnow()
        if ticket.status in ("responded", "script_generated", "script_sent", "closed"):
            sla_status = "completed"
        elif now > ticket.sla_deadline:
            sla_status = "breached"
        elif now > ticket.sla_deadline - (ticket.sla_deadline - ticket.created_at) * 0.25:
            sla_status = "warning"

    # Build response dict from ORM object
    data = {
        "id": ticket.id,
        "ticket_id": ticket.ticket_id,
        "agent_id": ticket.agent_id,
        "adm_id": ticket.adm_id,
        "interaction_id": ticket.interaction_id,
        "channel": ticket.channel,
        "selected_reasons": [
            {"code": c, "name": _reason_lookup.get(c, c)}
            for c in (json.loads(ticket.selected_reasons) if ticket.selected_reasons else [])
        ],
        "raw_feedback_text": ticket.raw_feedback_text,
        "parsed_summary": ticket.parsed_summary,
        "bucket": ticket.bucket,
        "reason_code": ticket.reason_code,
        "secondary_reason_codes": [
            {"code": c, "name": _reason_lookup.get(c, c)}
            for c in (json.loads(ticket.secondary_reason_codes) if ticket.secondary_reason_codes else [])
        ],
        "ai_confidence": ticket.ai_confidence,
        "priority": ticket.priority,
        "urgency_score": ticket.urgency_score,
        "churn_risk": ticket.churn_risk,
        "sentiment": ticket.sentiment,
        "sla_hours": ticket.sla_hours,
        "sla_deadline": ticket.sla_deadline,
        "status": ticket.status,
        "department_response_text": ticket.department_response_text,
        "department_responded_by": ticket.department_responded_by,
        "department_responded_at": ticket.department_responded_at,
        "generated_script": ticket.generated_script,
        "script_sent_at": ticket.script_sent_at,
        "adm_script_rating": ticket.adm_script_rating,
        "voice_file_id": ticket.voice_file_id,
        "parent_ticket_id": ticket.parent_ticket_id,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        # Enriched
        "agent_name": agent.name if agent else None,
        "adm_name": adm.name if adm else None,
        "bucket_display": BUCKET_DISPLAY_NAMES.get(ticket.bucket, ticket.bucket),
        "reason_display": reason_display,
        "sla_status": sla_status,
    }

    # Message count for conversation indicator (safe — table may not exist on first deploy)
    try:
        message_count = db.query(TicketMessage).filter(TicketMessage.ticket_id == ticket.id).count()
        data["message_count"] = message_count
    except Exception:
        data["message_count"] = 0

    return data


# ---------------------------------------------------------------------------
# Reason Taxonomy endpoints (for ADM UI — pick-and-choose reasons)
# ---------------------------------------------------------------------------

@router.get("/reasons", response_model=List[ReasonTaxonomyResponse])
def list_reasons(
    bucket: Optional[str] = Query(None, description="Filter by bucket"),
    db: Session = Depends(get_db),
):
    """List all active feedback reasons, grouped by bucket. Used by ADM UI for pick-and-choose."""
    query = db.query(ReasonTaxonomy).filter(ReasonTaxonomy.active == True)
    if bucket:
        query = query.filter(ReasonTaxonomy.bucket == bucket)
    return query.order_by(ReasonTaxonomy.bucket, ReasonTaxonomy.display_order).all()


@router.get("/reasons/by-bucket")
def reasons_by_bucket(db: Session = Depends(get_db)):
    """Get reasons organized by bucket for UI rendering."""
    reasons = (
        db.query(ReasonTaxonomy)
        .filter(ReasonTaxonomy.active == True)
        .order_by(ReasonTaxonomy.bucket, ReasonTaxonomy.display_order)
        .all()
    )
    result = {}
    for r in reasons:
        bucket = r.bucket
        if bucket not in result:
            result[bucket] = {
                "bucket": bucket,
                "display_name": BUCKET_DISPLAY_NAMES.get(bucket, bucket),
                "reasons": [],
            }
        result[bucket]["reasons"].append({
            "code": r.code,
            "reason_name": r.reason_name,
            "description": r.description,
            "sub_reasons": json.loads(r.sub_reasons) if r.sub_reasons else [],
        })
    return list(result.values())


# ---------------------------------------------------------------------------
# Ticket submission (ADM submits feedback)
# ---------------------------------------------------------------------------

@router.post("/submit", status_code=201)
async def submit_feedback_ticket(
    data: FeedbackTicketSubmit,
    db: Session = Depends(get_db),
):
    """
    ADM submits agent feedback. AI classifies it and routes to department.

    ADM can:
    1. Pick one or more reason codes (selected_reason_codes)
    2. Provide free text (raw_feedback_text)
    3. Both — reasons + additional context
    """
    # Validate agent and ADM
    agent = db.query(Agent).filter(Agent.id == data.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    adm = db.query(ADM).filter(ADM.id == data.adm_id).first()
    if not adm:
        raise HTTPException(status_code=404, detail="ADM not found")

    if not data.selected_reason_codes and not data.raw_feedback_text:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one reason code or feedback text",
        )

    # ---------------------------------------------------------------
    # Duplicate ticket prevention: check for existing open ticket
    # for the same agent_id + adm_id + bucket (determined from reason
    # codes or, if none, deferred until after classification).
    # ---------------------------------------------------------------

    # Pre-determine bucket from selected reason codes so we can check
    # before running classification (which costs an AI call).
    candidate_bucket = None
    if data.selected_reason_codes:
        candidate_bucket = feedback_classifier._bucket_from_code(data.selected_reason_codes[0])

    # Only proceed with dedup check if we have a candidate bucket
    # (from reason codes). If not, we'll check after classification.
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    def _find_open_ticket(bucket_to_check: str) -> Optional[FeedbackTicket]:
        """Find an existing open ticket for this agent+adm+bucket within 30 days."""
        return (
            db.query(FeedbackTicket)
            .filter(
                FeedbackTicket.agent_id == data.agent_id,
                FeedbackTicket.adm_id == data.adm_id,
                FeedbackTicket.bucket == bucket_to_check,
                FeedbackTicket.status != "closed",
                FeedbackTicket.created_at >= thirty_days_ago,
            )
            .order_by(desc(FeedbackTicket.created_at))
            .first()
        )

    def _add_followup_to_ticket(existing: FeedbackTicket) -> dict:
        """Append follow-up feedback to an existing open ticket."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        new_text = data.raw_feedback_text or ""

        # Append to raw_feedback_text
        if existing.raw_feedback_text:
            existing.raw_feedback_text = (
                existing.raw_feedback_text
                + f"\n---\nFollow-up ({timestamp}):\n{new_text}"
            )
        else:
            existing.raw_feedback_text = new_text

        # Merge new reason codes into selected_reasons
        if data.selected_reason_codes:
            current_reasons = (
                json.loads(existing.selected_reasons)
                if existing.selected_reasons
                else []
            )
            merged = list(current_reasons)
            for code in data.selected_reason_codes:
                if code not in merged:
                    merged.append(code)
            existing.selected_reasons = json.dumps(merged)

        # Reset status to "received" so department sees it again
        existing.status = "received"

        # Reset SLA deadline
        sla_hours = feedback_classifier.get_sla_hours(
            existing.bucket, existing.priority or "medium"
        )
        existing.sla_deadline = datetime.utcnow() + timedelta(hours=sla_hours)

        # Update the queue entry status back to open
        queue = db.query(DepartmentQueue).filter(
            DepartmentQueue.ticket_id == existing.id
        ).first()
        if queue:
            queue.status = "open"
            queue.sla_status = "on_track"

        # Create follow-up message in the conversation thread (non-critical)
        try:
            followup_msg = TicketMessage(
                ticket_id=existing.id,
                sender_type="adm",
                sender_name=adm.name if adm else "ADM",
                message_text=data.raw_feedback_text or f"Follow-up with reason codes: {', '.join(data.selected_reason_codes or [])}",
                voice_file_id=data.voice_file_id,
                message_type="voice" if data.voice_file_id else "text",
            )
            db.add(followup_msg)
        except Exception as e:
            logger.warning(f"Could not create follow-up TicketMessage: {e}")

        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)

        return {
            "tickets": [_enrich_ticket(existing, db)],
            "message": f"Follow-up added to existing ticket {existing.ticket_id}",
            "is_followup": True,
            "original_ticket_id": existing.ticket_id,
        }

    # If we already know the bucket from reason codes, check now
    if candidate_bucket:
        existing_ticket = _find_open_ticket(candidate_bucket)
        if existing_ticket:
            return _add_followup_to_ticket(existing_ticket)

    # Classify
    classification = await feedback_classifier.classify_feedback(
        raw_text=data.raw_feedback_text or "",
        selected_reason_codes=data.selected_reason_codes,
        agent_name=agent.name,
        agent_location=agent.location,
        agent_state=agent.lifecycle_state,
    )

    # If we didn't have reason codes, check for duplicate now using
    # the AI-classified bucket
    if not candidate_bucket:
        existing_ticket = _find_open_ticket(classification["bucket"])
        if existing_ticket:
            return _add_followup_to_ticket(existing_ticket)

    # Check for multi-bucket — split into separate tickets
    tickets_created = []
    buckets_to_process = [classification["bucket"]]
    if classification.get("multi_bucket") and classification.get("additional_buckets"):
        buckets_to_process.extend(classification["additional_buckets"])

    parent_ticket_id = None

    for idx, bucket in enumerate(buckets_to_process):
        ticket_id = _generate_ticket_id(db)
        sla_hours = feedback_classifier.get_sla_hours(bucket, classification["priority"])
        sla_deadline = feedback_classifier.compute_sla_deadline(bucket, classification["priority"])

        # For split tickets, filter reason codes to this bucket
        bucket_codes = []
        if data.selected_reason_codes:
            for code in data.selected_reason_codes:
                if feedback_classifier._bucket_from_code(code) == bucket:
                    bucket_codes.append(code)

        ticket = FeedbackTicket(
            ticket_id=ticket_id,
            agent_id=data.agent_id,
            adm_id=data.adm_id,
            interaction_id=data.interaction_id,
            channel=data.channel,
            selected_reasons=json.dumps(bucket_codes) if bucket_codes else (
                json.dumps(data.selected_reason_codes) if idx == 0 and data.selected_reason_codes else None
            ),
            raw_feedback_text=data.raw_feedback_text,
            parsed_summary=classification.get("parsed_summary"),
            bucket=bucket,
            reason_code=bucket_codes[0] if bucket_codes else classification.get("reason_code"),
            secondary_reason_codes=json.dumps(
                bucket_codes[1:] if len(bucket_codes) > 1 else classification.get("secondary_reason_codes", [])
            ),
            ai_confidence=classification.get("confidence"),
            priority=classification.get("priority", "medium"),
            urgency_score=classification.get("urgency_score", 5.0),
            churn_risk=classification.get("churn_risk"),
            sentiment=classification.get("sentiment"),
            sla_hours=sla_hours,
            sla_deadline=sla_deadline,
            status="routed",
            parent_ticket_id=parent_ticket_id,
            voice_file_id=data.voice_file_id,
        )
        db.add(ticket)
        db.flush()

        # Create initial ADM message in the conversation thread (non-critical — don't fail ticket creation)
        try:
            initial_msg = TicketMessage(
                ticket_id=ticket.id,
                sender_type="adm",
                sender_name=adm.name if adm else "ADM",
                message_text=data.raw_feedback_text or f"Submitted feedback with reason codes: {', '.join(data.selected_reason_codes or [])}",
                voice_file_id=data.voice_file_id,
                message_type="voice" if data.voice_file_id else "text",
            )
            db.add(initial_msg)
        except Exception as e:
            logger.warning(f"Could not create initial TicketMessage: {e}")

        if idx == 0:
            parent_ticket_id = ticket.ticket_id

        # Create department queue entry
        queue_entry = DepartmentQueue(
            department=bucket,
            ticket_id=ticket.id,
            status="open",
            sla_status="on_track",
        )
        db.add(queue_entry)

        tickets_created.append(ticket)

    # Link related tickets if multi-bucket
    if len(tickets_created) > 1:
        all_ids = [t.ticket_id for t in tickets_created]
        for t in tickets_created:
            t.related_ticket_ids = json.dumps([tid for tid in all_ids if tid != t.ticket_id])

    db.commit()

    # Return enriched responses
    result = []
    for t in tickets_created:
        db.refresh(t)
        result.append(_enrich_ticket(t, db))

    # Check for aggregation patterns (async-safe, runs after commit)
    _check_aggregation_patterns(db, tickets_created[0])

    return {
        "tickets": result,
        "message": f"Feedback routed to {', '.join(BUCKET_DISPLAY_NAMES.get(b, b) for b in buckets_to_process)}",
        "sla_info": {b: f"{feedback_classifier.get_sla_hours(b, classification['priority'])} hours"
                     for b in buckets_to_process},
    }


# ---------------------------------------------------------------------------
# List / filter tickets
# ---------------------------------------------------------------------------

@router.get("/", response_model=None)
def list_tickets(
    adm_id: Optional[int] = Query(None),
    agent_id: Optional[int] = Query(None),
    bucket: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    department: Optional[str] = Query(None, description="Filter by department queue"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List feedback tickets with filters. Used by ADM view and department dashboard."""
    query = db.query(FeedbackTicket)

    if adm_id:
        query = query.filter(FeedbackTicket.adm_id == adm_id)
    if agent_id:
        query = query.filter(FeedbackTicket.agent_id == agent_id)
    if bucket:
        query = query.filter(FeedbackTicket.bucket == bucket)
    if status:
        query = query.filter(FeedbackTicket.status == status)
    if priority:
        query = query.filter(FeedbackTicket.priority == priority)
    if department:
        query = query.join(DepartmentQueue).filter(DepartmentQueue.department == department)

    total = query.count()
    tickets = query.order_by(desc(FeedbackTicket.created_at)).offset(skip).limit(limit).all()

    return {
        "tickets": [_enrich_ticket(t, db) for t in tickets],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


# ---------------------------------------------------------------------------
# Department queue view (must be before /{ticket_id} catch-all)
# ---------------------------------------------------------------------------

@router.get("/queue/{department}")
def department_queue(
    department: str,
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Get department's ticket queue with SLA status."""
    query = db.query(DepartmentQueue).filter(DepartmentQueue.department == department)
    if status:
        query = query.filter(DepartmentQueue.status == status)

    total = query.count()
    entries = query.order_by(DepartmentQueue.created_at.desc()).offset(skip).limit(limit).all()

    result = []
    for entry in entries:
        ticket = db.query(FeedbackTicket).filter(FeedbackTicket.id == entry.ticket_id).first()
        if ticket:
            enriched = _enrich_ticket(ticket, db)
            enriched["queue_status"] = entry.status
            enriched["queue_sla_status"] = entry.sla_status
            enriched["escalation_level"] = entry.escalation_level
            enriched["assigned_to"] = entry.assigned_to
            result.append(enriched)

    return {"tickets": result, "total": total, "department": department}


# ---------------------------------------------------------------------------
# Analytics (must be before /{ticket_id} catch-all)
# ---------------------------------------------------------------------------

@router.get("/analytics/summary")
def ticket_analytics(
    adm_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get feedback ticket analytics."""
    base = db.query(FeedbackTicket)
    if adm_id:
        base = base.filter(FeedbackTicket.adm_id == adm_id)

    total = base.count()

    by_bucket = dict(
        base.with_entities(FeedbackTicket.bucket, func.count(FeedbackTicket.id))
        .group_by(FeedbackTicket.bucket).all()
    )
    by_priority = dict(
        base.with_entities(FeedbackTicket.priority, func.count(FeedbackTicket.id))
        .group_by(FeedbackTicket.priority).all()
    )
    by_status = dict(
        base.with_entities(FeedbackTicket.status, func.count(FeedbackTicket.id))
        .group_by(FeedbackTicket.status).all()
    )

    # SLA compliance
    resolved = base.filter(FeedbackTicket.department_responded_at.isnot(None)).all()
    sla_met = sum(
        1 for t in resolved
        if t.sla_deadline and t.department_responded_at and t.department_responded_at <= t.sla_deadline
    )
    sla_compliance = round(sla_met / len(resolved) * 100, 1) if resolved else 0.0

    # Avg resolution time
    avg_hours = None
    if resolved:
        total_hours = sum(
            (t.department_responded_at - t.created_at).total_seconds() / 3600
            for t in resolved if t.department_responded_at and t.created_at
        )
        avg_hours = round(total_hours / len(resolved), 1)

    # Top reason codes
    top_reasons = (
        base.with_entities(FeedbackTicket.reason_code, func.count(FeedbackTicket.id).label("cnt"))
        .filter(FeedbackTicket.reason_code.isnot(None))
        .group_by(FeedbackTicket.reason_code)
        .order_by(func.count(FeedbackTicket.id).desc())
        .limit(10).all()
    )

    return {
        "total_tickets": total,
        "by_bucket": {k: {"count": v, "display": BUCKET_DISPLAY_NAMES.get(k, k)} for k, v in by_bucket.items()},
        "by_priority": by_priority,
        "by_status": by_status,
        "sla_compliance_pct": sla_compliance,
        "avg_resolution_hours": avg_hours,
        "top_reason_codes": [
            {"code": code, "name": _reason_name(db, code), "count": cnt}
            for code, cnt in top_reasons
        ],
    }


# ---------------------------------------------------------------------------
# Aggregation alerts (must be before /{ticket_id} catch-all)
# ---------------------------------------------------------------------------

@router.get("/alerts")
def list_alerts(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List aggregation/pattern alerts."""
    query = db.query(AggregationAlert)
    if status:
        query = query.filter(AggregationAlert.status == status)
    alerts = query.order_by(desc(AggregationAlert.created_at)).limit(50).all()

    # Enrich with reason display names
    enriched = []
    for a in alerts:
        d = {c.name: getattr(a, c.name) for c in a.__table__.columns}
        if a.reason_code:
            d["reason_name"] = _reason_name(db, a.reason_code)
        enriched.append(d)
    return enriched


# ---------------------------------------------------------------------------
# Voice note proxy (must be before /{ticket_id} catch-all)
# ---------------------------------------------------------------------------

@router.get("/{ticket_id}/voice")
async def get_voice_note(ticket_id: str, db: Session = Depends(get_db)):
    """Proxy Telegram voice note for browser playback."""
    from fastapi.responses import StreamingResponse

    ticket = db.query(FeedbackTicket).filter(
        FeedbackTicket.ticket_id == ticket_id
    ).first()
    if not ticket or not ticket.voice_file_id:
        raise HTTPException(status_code=404, detail="Voice note not found")

    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        raise HTTPException(status_code=503, detail="Telegram not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        file_resp = await client.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": ticket.voice_file_id},
        )
        file_data = file_resp.json()
        if not file_data.get("ok"):
            raise HTTPException(status_code=404, detail="Voice file expired or not found on Telegram")

        file_path = file_data["result"]["file_path"]
        audio_resp = await client.get(
            f"https://api.telegram.org/file/bot{token}/{file_path}"
        )

    return StreamingResponse(
        io.BytesIO(audio_resp.content),
        media_type="audio/ogg",
        headers={"Content-Disposition": f"inline; filename={ticket_id}-voice.ogg"},
    )


# ---------------------------------------------------------------------------
# Close / Reopen ticket (must be before /{ticket_id} catch-all)
# ---------------------------------------------------------------------------

@router.post("/{ticket_id}/close")
def close_ticket(ticket_id: str, db: Session = Depends(get_db)):
    """Close a feedback ticket."""
    ticket = db.query(FeedbackTicket).filter(
        FeedbackTicket.ticket_id == ticket_id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.status == "closed":
        raise HTTPException(status_code=400, detail="Ticket already closed")

    ticket.status = "closed"
    ticket.updated_at = datetime.utcnow()

    queue = db.query(DepartmentQueue).filter(
        DepartmentQueue.ticket_id == ticket.id
    ).first()
    if queue:
        queue.status = "closed"

    db.commit()
    return {"status": "ok", "ticket_id": ticket_id, "message": "Ticket closed"}


@router.post("/{ticket_id}/reopen")
def reopen_ticket(ticket_id: str, db: Session = Depends(get_db)):
    """Reopen a closed ticket."""
    ticket = db.query(FeedbackTicket).filter(
        FeedbackTicket.ticket_id == ticket_id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.status != "closed":
        raise HTTPException(status_code=400, detail="Ticket is not closed")

    ticket.status = "routed"
    ticket.updated_at = datetime.utcnow()

    queue = db.query(DepartmentQueue).filter(
        DepartmentQueue.ticket_id == ticket.id
    ).first()
    if queue:
        queue.status = "open"
        queue.sla_status = "on_track"

    # Reset SLA
    sla_hours = feedback_classifier.get_sla_hours(ticket.bucket, ticket.priority or "medium")
    ticket.sla_deadline = datetime.utcnow() + timedelta(hours=sla_hours)

    db.commit()
    return {"status": "ok", "ticket_id": ticket_id, "message": "Ticket reopened"}


# ---------------------------------------------------------------------------
# Conversation thread (messages) endpoints
# ---------------------------------------------------------------------------

@router.get("/{ticket_id}/messages")
def get_ticket_messages(ticket_id: str, db: Session = Depends(get_db)):
    """Get conversation thread for a ticket."""
    ticket = db.query(FeedbackTicket).filter(
        FeedbackTicket.ticket_id == ticket_id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    try:
        messages = (
            db.query(TicketMessage)
            .filter(TicketMessage.ticket_id == ticket.id)
            .order_by(TicketMessage.created_at.asc())
            .all()
        )
    except Exception:
        # Table may not exist yet on first deploy
        messages = []

    return {
        "ticket_id": ticket_id,
        "messages": [
            {
                "id": m.id,
                "sender_type": m.sender_type,
                "sender_name": m.sender_name,
                "message_text": m.message_text,
                "voice_file_id": m.voice_file_id,
                "message_type": m.message_type,
                "created_at": m.created_at,
            }
            for m in messages
        ],
    }


@router.post("/{ticket_id}/messages")
async def add_ticket_message(
    ticket_id: str,
    data: TicketMessageCreate,
    db: Session = Depends(get_db),
):
    """Add a message to the ticket thread (department follow-up or clarification)."""
    ticket = db.query(FeedbackTicket).filter(
        FeedbackTicket.ticket_id == ticket_id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    msg = TicketMessage(
        ticket_id=ticket.id,
        sender_type=data.sender_type,
        sender_name=data.sender_name,
        message_text=data.message_text,
        message_type=data.message_type or "text",
    )
    db.add(msg)

    # Department sends message → always notify ADM via Telegram
    if data.sender_type == "department":
        if data.message_type == "clarification_request":
            ticket.status = "pending_adm"
        else:
            # Regular department message — keep status or move to pending_adm
            if ticket.status not in ("responded", "script_generated", "script_sent", "closed"):
                ticket.status = "pending_adm"

        # Notify ADM via Telegram (fire and forget)
        asyncio.create_task(
            _notify_adm_department_message(
                ticket_id=ticket.ticket_id,
                message_text=data.message_text,
                is_clarification=(data.message_type == "clarification_request"),
            )
        )

    # ADM sends message via web (rare but possible) → notify department
    elif data.sender_type == "adm":
        if ticket.status not in ("closed",):
            ticket.status = "received"  # Reset so department sees it again
        # Update queue entry
        queue = db.query(DepartmentQueue).filter(
            DepartmentQueue.ticket_id == ticket.id
        ).first()
        if queue:
            queue.status = "open"

    db.commit()
    return {"status": "ok", "message_id": msg.id}


# ---------------------------------------------------------------------------
# Single ticket by ID (catch-all — MUST be after all fixed-path routes)
# ---------------------------------------------------------------------------

@router.get("/{ticket_id}")
def get_ticket(ticket_id: str, db: Session = Depends(get_db)):
    """Get a single ticket by ticket_id (e.g., FB-2026-00001)."""
    ticket = db.query(FeedbackTicket).filter(
        FeedbackTicket.ticket_id == ticket_id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _enrich_ticket(ticket, db)


# ---------------------------------------------------------------------------
# Department response
# ---------------------------------------------------------------------------

@router.post("/{ticket_id}/respond")
async def department_respond(
    ticket_id: str,
    data: DepartmentResponseSubmit,
    db: Session = Depends(get_db),
):
    """Department responds to a feedback ticket. Triggers AI script generation in background."""
    ticket = db.query(FeedbackTicket).filter(
        FeedbackTicket.ticket_id == ticket_id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.status in ("script_sent", "closed"):
        raise HTTPException(status_code=400, detail="Ticket already resolved")

    # Save department response immediately
    ticket.department_response_text = data.response_text
    ticket.department_responded_by = data.responded_by
    ticket.department_responded_at = datetime.utcnow()
    ticket.status = "responded"

    # Update queue entry immediately
    queue = db.query(DepartmentQueue).filter(
        DepartmentQueue.ticket_id == ticket.id
    ).first()
    if queue:
        queue.status = "responded"
        now = datetime.utcnow()
        if ticket.sla_deadline and now > ticket.sla_deadline:
            queue.sla_status = "breached"
        else:
            queue.sla_status = "on_track"

    # Create department response message in thread (non-critical)
    try:
        dept_msg = TicketMessage(
            ticket_id=ticket.id,
            sender_type="department",
            sender_name=data.responded_by,
            message_text=data.response_text,
            message_type="text",
        )
        db.add(dept_msg)
    except Exception as e:
        logger.warning(f"Could not create dept TicketMessage: {e}")

    db.commit()
    db.refresh(ticket)

    # Fire off script generation + Telegram push in the background
    asyncio.create_task(
        _background_generate_and_push(
            ticket_id=ticket.ticket_id,
            response_text=data.response_text,
        )
    )

    return {
        "ticket": _enrich_ticket(ticket, db),
        "script_status": "generating",
        "message": "Response recorded. Script generation in progress.",
    }


async def _background_generate_and_push(ticket_id: str, response_text: str):
    """Background task: generate communication script and push to ADM via Telegram.

    Opens its own DB session since the request session is closed after response.
    """
    db = SessionLocal()
    try:
        ticket = db.query(FeedbackTicket).filter(
            FeedbackTicket.ticket_id == ticket_id
        ).first()
        if not ticket:
            logger.error(f"Background task: ticket {ticket_id} not found")
            return

        agent = db.query(Agent).filter(Agent.id == ticket.agent_id).first()

        # Generate communication script (with timeout)
        try:
            script = await asyncio.wait_for(
                feedback_classifier.generate_script(
                    agent_name=agent.name if agent else "Agent",
                    original_feedback=ticket.raw_feedback_text or ticket.parsed_summary or "",
                    reason_code=ticket.reason_code or "",
                    bucket=ticket.bucket,
                    department_response=response_text,
                    agent_location=agent.location if agent else "",
                ),
                timeout=25.0,
            )
        except asyncio.TimeoutError:
            logger.warning(f"AI script generation timed out for {ticket_id}, using template")
            script = feedback_classifier._template_script(
                agent_name=agent.name if agent else "Agent",
                original_feedback=ticket.raw_feedback_text or ticket.parsed_summary or "",
                bucket=ticket.bucket,
                department_response=response_text,
            )

        ticket.generated_script = script
        ticket.status = "script_generated"

        # Create AI script message in thread (non-critical)
        try:
            script_msg = TicketMessage(
                ticket_id=ticket.id,
                sender_type="ai",
                sender_name="Script Generator",
                message_text=script,
                message_type="script",
            )
            db.add(script_msg)
        except Exception as e:
            logger.warning(f"Could not create AI TicketMessage: {e}")

        db.commit()

        # Push script to ADM via Telegram
        await _push_script_to_adm(ticket, script, db)

        logger.info(f"Background script generation complete for {ticket_id}")
    except Exception as e:
        logger.error(f"Background script generation failed for {ticket_id}: {e}")
    finally:
        db.close()


async def _notify_adm_department_message(
    ticket_id: str, message_text: str, is_clarification: bool = False,
):
    """Notify ADM via Telegram when department sends any message on a ticket."""
    db = SessionLocal()
    try:
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            return

        ticket = db.query(FeedbackTicket).filter(
            FeedbackTicket.ticket_id == ticket_id
        ).first()
        if not ticket:
            return

        adm = db.query(ADM).filter(ADM.id == ticket.adm_id).first()
        if not adm or not adm.telegram_chat_id:
            return

        agent = db.query(Agent).filter(Agent.id == ticket.agent_id).first()
        agent_name = agent.name if agent else "Agent"
        bucket_label = BUCKET_DISPLAY_NAMES.get(ticket.bucket, ticket.bucket or "")

        if is_clarification:
            emoji = "\u2753"
            header = "Clarification Needed"
            dept_label = "Department asks"
        else:
            emoji = "\U0001F4AC"
            header = "Department Update"
            dept_label = "Department says"

        message = (
            f"{emoji} *{header} \u2014 {ticket_id}*\n\n"
            f"*Agent:* {agent_name}\n"
            f"*Department:* {bucket_label}\n\n"
            f"\U0001F4DD *{dept_label}:*\n"
            f"{message_text}\n\n"
            f"_Use /cases to view your open cases and reply._"
        )

        # Add inline button to view case
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": adm.telegram_chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "reply_markup": {
                "inline_keyboard": [
                    [{"text": "\U0001F4CB View Case", "callback_data": f"view_case:{ticket_id}"}],
                    [{"text": "\u2705 Close Ticket", "callback_data": f"close_ticket:{ticket_id}"}],
                ]
            },
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                logger.info(f"Department message notification sent to ADM for {ticket_id}")
            else:
                logger.error(f"Telegram notification failed: {resp.text}")
    except Exception as e:
        logger.error(f"Error notifying ADM about department message: {e}")
    finally:
        db.close()


# Keep backward compat alias
async def _notify_adm_clarification(ticket_id: str, clarification_text: str):
    """Backward compat — redirects to the generic department message notifier."""
    await _notify_adm_department_message(ticket_id, clarification_text, is_clarification=True)


# ---------------------------------------------------------------------------
# Mark script as sent (called after bot delivers to ADM)
# ---------------------------------------------------------------------------

@router.post("/{ticket_id}/script-sent")
def mark_script_sent(ticket_id: str, db: Session = Depends(get_db)):
    """Mark that the script has been delivered to the ADM."""
    ticket = db.query(FeedbackTicket).filter(
        FeedbackTicket.ticket_id == ticket_id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.script_sent_at = datetime.utcnow()
    ticket.status = "script_sent"
    db.commit()
    return {"status": "ok", "ticket_id": ticket_id}


# ---------------------------------------------------------------------------
# ADM rates the script
# ---------------------------------------------------------------------------

@router.post("/{ticket_id}/rate-script")
def rate_script(
    ticket_id: str,
    data: ScriptRating,
    db: Session = Depends(get_db),
):
    """ADM rates the generated communication script."""
    ticket = db.query(FeedbackTicket).filter(
        FeedbackTicket.ticket_id == ticket_id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.adm_script_rating = data.rating
    ticket.adm_script_feedback = data.feedback
    if data.rating == "helpful":
        ticket.status = "closed"
    db.commit()
    return {"status": "ok", "ticket_id": ticket_id}


# ---------------------------------------------------------------------------
# Pattern detection (internal helper)
# ---------------------------------------------------------------------------

def _check_aggregation_patterns(db: Session, ticket: FeedbackTicket):
    """Check if this ticket creates a pattern worth alerting on."""
    try:
        # Count similar tickets in last 30 days
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=30)

        # Same reason code pattern
        if ticket.reason_code:
            similar = (
                db.query(FeedbackTicket)
                .filter(
                    FeedbackTicket.reason_code == ticket.reason_code,
                    FeedbackTicket.created_at >= cutoff,
                )
                .all()
            )
            if len(similar) >= 5:
                # Check if alert already exists
                existing = (
                    db.query(AggregationAlert)
                    .filter(
                        AggregationAlert.reason_code == ticket.reason_code,
                        AggregationAlert.status == "active",
                    )
                    .first()
                )
                if not existing:
                    unique_agents = len({t.agent_id for t in similar})
                    unique_adms = len({t.adm_id for t in similar})
                    alert = AggregationAlert(
                        pattern_type="reason",
                        description=(
                            f"Pattern detected: {len(similar)} tickets with reason {ticket.reason_code} "
                            f"in last 30 days from {unique_agents} agents across {unique_adms} ADMs"
                        ),
                        affected_agents_count=unique_agents,
                        affected_adms_count=unique_adms,
                        bucket=ticket.bucket,
                        reason_code=ticket.reason_code,
                        ticket_ids=json.dumps([t.ticket_id for t in similar]),
                    )
                    db.add(alert)
                    db.commit()
                    logger.info(f"Aggregation alert created for {ticket.reason_code}")
    except Exception as e:
        logger.error(f"Error checking aggregation patterns: {e}")
