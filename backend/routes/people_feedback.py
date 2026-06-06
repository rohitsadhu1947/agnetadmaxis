"""
People Feedback API — agent feedback about the ADM / Branch Manager assigned
to them. Routes strictly to the Agency Development team.

PRIVACY MODEL (enforce on every read endpoint):
  - "agent" users (we don't actually have logins for agents but the bot acts
     on their behalf) can read ONLY their own tickets.
  - "agency_dev" + "admin" users can read everything.
  - "adm" users are EXPLICITLY BLOCKED (HTTP 403) from every read endpoint —
    they MUST NEVER see feedback the agent submitted about them.

Endpoints:
  Agent-facing (called by the agent Telegram bot):
    POST   /people-feedback/submit          — Create a new ticket
    GET    /people-feedback/agent/{agent_id}/list   — Agent's own tickets
    GET    /people-feedback/agent/{agent_id}/{ticket_id}    — Agent reads own ticket
    POST   /people-feedback/agent/{agent_id}/{ticket_id}/reply  — Agent replies

  Agency Development team (requires auth: admin | agency_dev):
    GET    /people-feedback              — List all (filterable)
    GET    /people-feedback/{ticket_id}  — Detail with full thread
    POST   /people-feedback/{ticket_id}/reply  — Team reply (visible to agent)
    POST   /people-feedback/{ticket_id}/note   — Internal note (NEVER shown to agent)
    PATCH  /people-feedback/{ticket_id}/status — Change status
    GET    /people-feedback/meta/categories    — Category tree (for bot UI)
    GET    /people-feedback/meta/stats         — Counts by status / SLA

Reference data (the locked-in category tree from the spec):
  support_unavailable:
      not_responding | too_busy_own_targets | long_delays | other
  first_meeting:
      did_not_join | joined_but_no_help | joined_and_helped | other
  training_guidance:
      no_product_training | no_process_guidance | wrong_advice | other
  other:
      (no subcategory — free text required)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from config import settings
from database import get_db
from models import (
    Agent,
    ADM,
    User,
    AgentPeopleFeedback,
    AgentPeopleFeedbackMessage,
)
from routes.auth import get_current_user, get_current_user_optional

router = APIRouter(prefix="/people-feedback", tags=["People Feedback"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reference data: locked-in category tree
# ---------------------------------------------------------------------------
CATEGORY_TREE: dict = {
    "support_unavailable": {
        "label": "Support not available",
        "subcategories": {
            "not_responding": "Not responding to calls / messages",
            "too_busy_own_targets": "Too busy with own targets",
            "long_delays": "Long delays in answering queries",
            "other": "Other (please specify)",
        },
    },
    "first_meeting": {
        "label": "First Client Meeting",
        "subcategories": {
            "did_not_join": "Did not join the meeting",
            "joined_but_no_help": "Joined but did not help",
            "joined_and_helped": "Joined and helped (positive feedback)",
            "other": "Other (please specify)",
        },
    },
    "training_guidance": {
        "label": "Training & Guidance",
        "subcategories": {
            "no_product_training": "No product training provided",
            "no_process_guidance": "No process guidance given",
            "wrong_advice": "Incorrect / conflicting advice",
            "other": "Other (please specify)",
        },
    },
    "other": {
        "label": "Anything else",
        "subcategories": {},  # Free text only — no sub-cats
    },
}

SLA_DAYS = 3

VALID_STATUSES = {"new", "reviewed", "in_progress", "action_taken", "closed", "escalated"}
AGENCY_DEV_ROLES = {"admin", "agency_dev"}


# ---------------------------------------------------------------------------
# Pydantic schemas (kept local to this module so unrelated callers stay clean)
# ---------------------------------------------------------------------------
class SubmitRequest(BaseModel):
    agent_id: int
    category: str = Field(..., description="One of the keys in CATEGORY_TREE")
    subcategory: Optional[str] = Field(None, description="Required unless category == 'other'")
    other_text: Optional[str] = Field(None, description="Required when sub is 'other' or category == 'other'")
    initial_text: Optional[str] = None
    voice_file_id: Optional[str] = None
    attachment_file_id: Optional[str] = None
    attachment_file_name: Optional[str] = None
    attachment_mime_type: Optional[str] = None
    channel: str = "telegram"


class ReplyRequest(BaseModel):
    text: Optional[str] = None
    voice_file_id: Optional[str] = None
    attachment_file_id: Optional[str] = None
    attachment_file_name: Optional[str] = None
    attachment_mime_type: Optional[str] = None


class InternalNoteRequest(BaseModel):
    text: str = Field(..., min_length=1)


class StatusChangeRequest(BaseModel):
    new_status: str = Field(..., description="One of VALID_STATUSES")
    note: Optional[str] = None  # Optional internal note describing the action


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _require_agency_dev(user: User) -> None:
    """Raise 403 if the user is not allowed to see Agency Development tickets.

    Critically: ADM users are ALWAYS blocked here.
    """
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if user.role not in AGENCY_DEV_ROLES:
        # Log the attempt — if an ADM ever hits this it's a real signal
        logger.warning(
            "BLOCKED: user_id=%s role=%s attempted people-feedback access",
            user.id, user.role,
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Access denied. People feedback is visible only to the Agency Development team.",
        )


def _generate_ticket_ref(db: Session) -> str:
    """PF-YYYY-NNNNN — sequential within year."""
    year = datetime.utcnow().year
    count = (
        db.query(AgentPeopleFeedback)
        .filter(AgentPeopleFeedback.ticket_ref.like(f"PF-{year}-%"))
        .count()
    )
    return f"PF-{year}-{count + 1:05d}"


def _validate_category(category: str, subcategory: Optional[str], other_text: Optional[str]) -> None:
    if category not in CATEGORY_TREE:
        raise HTTPException(400, f"Invalid category. Must be one of: {list(CATEGORY_TREE)}")

    sub_map = CATEGORY_TREE[category]["subcategories"]
    if category == "other":
        if not (other_text and other_text.strip()):
            raise HTTPException(400, "Free text is required when category is 'other'.")
        return

    if not sub_map:  # Category exists but has no sub-cats
        return

    if not subcategory or subcategory not in sub_map:
        raise HTTPException(
            400, f"Invalid subcategory for {category}. Must be one of: {list(sub_map)}",
        )
    if subcategory == "other" and not (other_text and other_text.strip()):
        raise HTTPException(400, "Free text is required when subcategory is 'other'.")


def _ticket_to_dict(t: AgentPeopleFeedback, include_internal: bool, include_messages: bool = False) -> dict:
    """Serialise a ticket for response.

    include_internal=True → returns internal_notes and assigned_to (Agency Dev view).
    include_internal=False → omits those fields (agent view).
    """
    d = {
        "id": t.id,
        "ticket_ref": t.ticket_ref,
        "agent_id": t.agent_id,
        "agent_name": t.agent.name if t.agent else None,
        "agent_phone": t.agent.phone if t.agent else None,
        "target_adm_id": t.target_adm_id,
        "target_adm_name": t.target_adm.name if t.target_adm else None,
        "category": t.category,
        "category_label": CATEGORY_TREE.get(t.category, {}).get("label"),
        "subcategory": t.subcategory,
        "subcategory_label": CATEGORY_TREE.get(t.category, {}).get("subcategories", {}).get(t.subcategory or ""),
        "other_text": t.other_text,
        "initial_text": t.initial_text,
        "has_voice": bool(t.voice_file_id),
        "has_attachment": bool(t.attachment_file_id),
        "attachment_file_name": t.attachment_file_name,
        "status": t.status,
        "sla_due_at": t.sla_due_at.isoformat() if t.sla_due_at else None,
        "is_sla_breached": bool(
            t.sla_due_at and t.status not in ("action_taken", "closed") and datetime.utcnow() > t.sla_due_at
        ),
        "channel": t.channel,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }
    if include_internal:
        d["internal_notes"] = t.internal_notes
        d["assigned_to_user_id"] = t.assigned_to_user_id
        d["assigned_to_name"] = t.assigned_to.name if t.assigned_to else None
        # Expose file_ids so the dashboard can fetch /people-feedback/file/{id}
        # for playback. Only returned in the Agency Dev view (never to agent).
        d["voice_file_id"] = t.voice_file_id
        d["attachment_file_id"] = t.attachment_file_id
        d["attachment_mime_type"] = t.attachment_mime_type

    if include_messages:
        d["messages"] = [_message_to_dict(m, include_internal=include_internal) for m in t.messages]
    return d


def _message_to_dict(m: AgentPeopleFeedbackMessage, include_internal: bool) -> Optional[dict]:
    """Serialise a thread message. Returns None to skip messages the caller shouldn't see."""
    # Internal notes are NEVER returned to the agent
    if m.message_type == "note" and not include_internal:
        return None
    d = {
        "id": m.id,
        "sender_role": m.sender_role,
        "sender_name": m.sender_name,
        "text": m.text,
        "has_voice": bool(m.voice_file_id),
        "has_attachment": bool(m.attachment_file_id),
        "attachment_file_name": m.attachment_file_name,
        "message_type": m.message_type,
        "is_status_change": m.is_status_change,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }
    # Expose file_ids for the Agency Dev view so the dashboard can render playback
    if include_internal:
        d["voice_file_id"] = m.voice_file_id
        d["attachment_file_id"] = m.attachment_file_id
        d["attachment_mime_type"] = m.attachment_mime_type
    return d


def _strip_none_messages(d: dict) -> dict:
    if "messages" in d:
        d["messages"] = [m for m in d["messages"] if m is not None]
    return d


# =================================================================
# Agent-facing endpoints (no auth — called by the agent Telegram bot,
# which authenticates the agent by their phone -> agent_id mapping).
# We deliberately don't require JWT here because agents don't have
# platform logins; the bot is the trust boundary.
# =================================================================

@router.get("/meta/categories")
def get_categories():
    """Public reference data — the category tree the bot renders."""
    return {
        "categories": [
            {
                "key": cat_key,
                "label": cat["label"],
                "subcategories": [
                    {"key": sub_key, "label": sub_label}
                    for sub_key, sub_label in cat["subcategories"].items()
                ],
            }
            for cat_key, cat in CATEGORY_TREE.items()
        ],
        "sla_days": SLA_DAYS,
    }


@router.post("/submit")
def submit_ticket(req: SubmitRequest, db: Session = Depends(get_db)):
    """Create a new people-feedback ticket. Called by the agent bot."""
    _validate_category(req.category, req.subcategory, req.other_text)

    agent = db.query(Agent).filter(Agent.id == req.agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    # Look up the assigned ADM (this is who the feedback is implicitly about)
    target_adm_id = agent.assigned_adm_id

    ticket = AgentPeopleFeedback(
        ticket_ref=_generate_ticket_ref(db),
        agent_id=req.agent_id,
        target_adm_id=target_adm_id,
        category=req.category,
        subcategory=req.subcategory,
        other_text=req.other_text,
        initial_text=req.initial_text,
        voice_file_id=req.voice_file_id,
        attachment_file_id=req.attachment_file_id,
        attachment_file_name=req.attachment_file_name,
        attachment_mime_type=req.attachment_mime_type,
        status="new",
        sla_due_at=datetime.utcnow() + timedelta(days=SLA_DAYS),
        channel=req.channel,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    logger.info(
        "PF ticket submitted: ref=%s agent=%s target_adm=%s category=%s/%s",
        ticket.ticket_ref, agent.name, target_adm_id, req.category, req.subcategory,
    )

    return {
        "ok": True,
        "ticket_ref": ticket.ticket_ref,
        "ticket_id": ticket.id,
        "sla_due_at": ticket.sla_due_at.isoformat(),
        "message": f"Submitted as {ticket.ticket_ref}. The Agency Development team will respond within {SLA_DAYS} days.",
    }


@router.get("/agent/{agent_id}/list")
def agent_list_own_tickets(agent_id: int, db: Session = Depends(get_db)):
    """Agent reads their own tickets. The bot calls this with the agent's resolved id."""
    tickets = (
        db.query(AgentPeopleFeedback)
        .filter(AgentPeopleFeedback.agent_id == agent_id)
        .order_by(desc(AgentPeopleFeedback.created_at))
        .all()
    )
    return {"count": len(tickets), "tickets": [_ticket_to_dict(t, include_internal=False) for t in tickets]}


@router.get("/agent/{agent_id}/{ticket_id}")
def agent_get_own_ticket(agent_id: int, ticket_id: int, db: Session = Depends(get_db)):
    """Agent reads one of their own tickets with thread (internal notes hidden)."""
    ticket = (
        db.query(AgentPeopleFeedback)
        .filter(
            AgentPeopleFeedback.id == ticket_id,
            AgentPeopleFeedback.agent_id == agent_id,
        )
        .first()
    )
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    return _strip_none_messages(_ticket_to_dict(ticket, include_internal=False, include_messages=True))


@router.post("/agent/{agent_id}/{ticket_id}/reply")
def agent_reply(agent_id: int, ticket_id: int, req: ReplyRequest, db: Session = Depends(get_db)):
    """Agent posts a reply on their own ticket. Cannot reply if closed."""
    ticket = (
        db.query(AgentPeopleFeedback)
        .filter(
            AgentPeopleFeedback.id == ticket_id,
            AgentPeopleFeedback.agent_id == agent_id,
        )
        .first()
    )
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    if ticket.status == "closed":
        raise HTTPException(400, "Ticket is closed; cannot reply.")

    if not (req.text or req.voice_file_id or req.attachment_file_id):
        raise HTTPException(400, "Reply must include text, voice, or attachment.")

    agent_name = ticket.agent.name if ticket.agent else f"Agent {agent_id}"
    msg_type = (
        "voice" if req.voice_file_id
        else "document" if req.attachment_file_id
        else "text"
    )

    msg = AgentPeopleFeedbackMessage(
        ticket_id=ticket.id,
        sender_role="agent",
        sender_name=agent_name,
        text=req.text,
        voice_file_id=req.voice_file_id,
        attachment_file_id=req.attachment_file_id,
        attachment_file_name=req.attachment_file_name,
        attachment_mime_type=req.attachment_mime_type,
        message_type=msg_type,
    )
    db.add(msg)
    # Touch ticket so list sorts by last activity correctly
    ticket.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message_id": msg.id}


# =================================================================
# Agency Development team endpoints (require JWT auth + role check)
# =================================================================

@router.get("")
@router.get("/")
def list_tickets(
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = None,
    sla_breached_only: bool = False,
    search: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all people-feedback tickets — Agency Development team view."""
    _require_agency_dev(current_user)

    q = db.query(AgentPeopleFeedback)

    if status_filter:
        if status_filter not in VALID_STATUSES:
            raise HTTPException(400, f"Invalid status. Must be one of {sorted(VALID_STATUSES)}")
        q = q.filter(AgentPeopleFeedback.status == status_filter)
    if category:
        if category not in CATEGORY_TREE:
            raise HTTPException(400, "Invalid category")
        q = q.filter(AgentPeopleFeedback.category == category)
    if sla_breached_only:
        q = q.filter(
            AgentPeopleFeedback.sla_due_at < datetime.utcnow(),
            AgentPeopleFeedback.status.notin_(["action_taken", "closed"]),
        )
    if search:
        like = f"%{search}%"
        q = q.join(Agent, AgentPeopleFeedback.agent_id == Agent.id).filter(
            or_(
                AgentPeopleFeedback.ticket_ref.ilike(like),
                Agent.name.ilike(like),
                AgentPeopleFeedback.initial_text.ilike(like),
                AgentPeopleFeedback.other_text.ilike(like),
            )
        )

    total = q.count()
    tickets = (
        q.order_by(desc(AgentPeopleFeedback.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "count": len(tickets),
        "tickets": [_ticket_to_dict(t, include_internal=True) for t in tickets],
    }


@router.get("/meta/stats")
def get_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dashboard summary: counts by status + SLA-breach count."""
    _require_agency_dev(current_user)

    rows = (
        db.query(AgentPeopleFeedback.status)
        .all()
    )
    by_status = {s: 0 for s in VALID_STATUSES}
    for (s,) in rows:
        by_status[s] = by_status.get(s, 0) + 1

    sla_breached = (
        db.query(AgentPeopleFeedback)
        .filter(
            AgentPeopleFeedback.sla_due_at < datetime.utcnow(),
            AgentPeopleFeedback.status.notin_(["action_taken", "closed"]),
        )
        .count()
    )

    return {
        "by_status": by_status,
        "total": sum(by_status.values()),
        "sla_breached": sla_breached,
        "sla_days": SLA_DAYS,
    }


@router.get("/{ticket_id}")
def get_ticket_detail(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Full ticket detail with thread (including internal notes)."""
    _require_agency_dev(current_user)

    ticket = db.query(AgentPeopleFeedback).filter(AgentPeopleFeedback.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    return _ticket_to_dict(ticket, include_internal=True, include_messages=True)


@router.post("/{ticket_id}/reply")
def agency_dev_reply(
    ticket_id: int,
    req: ReplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Agency Development team posts a reply visible to the agent."""
    _require_agency_dev(current_user)

    ticket = db.query(AgentPeopleFeedback).filter(AgentPeopleFeedback.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    if not (req.text or req.voice_file_id or req.attachment_file_id):
        raise HTTPException(400, "Reply must include text, voice, or attachment.")

    msg_type = (
        "voice" if req.voice_file_id
        else "document" if req.attachment_file_id
        else "text"
    )
    msg = AgentPeopleFeedbackMessage(
        ticket_id=ticket.id,
        sender_role="agency_dev",
        sender_user_id=current_user.id,
        sender_name=current_user.name,
        text=req.text,
        voice_file_id=req.voice_file_id,
        attachment_file_id=req.attachment_file_id,
        attachment_file_name=req.attachment_file_name,
        attachment_mime_type=req.attachment_mime_type,
        message_type=msg_type,
    )
    # On first reply move "new" → "reviewed" automatically
    if ticket.status == "new":
        ticket.status = "reviewed"
    ticket.updated_at = datetime.utcnow()
    db.add(msg)
    db.commit()
    return {"ok": True, "message_id": msg.id, "ticket_status": ticket.status}


@router.post("/{ticket_id}/note")
def add_internal_note(
    ticket_id: int,
    req: InternalNoteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add an INTERNAL note. NEVER shown to the agent."""
    _require_agency_dev(current_user)

    ticket = db.query(AgentPeopleFeedback).filter(AgentPeopleFeedback.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    msg = AgentPeopleFeedbackMessage(
        ticket_id=ticket.id,
        sender_role="agency_dev",
        sender_user_id=current_user.id,
        sender_name=current_user.name,
        text=req.text,
        message_type="note",
    )
    db.add(msg)
    db.commit()
    return {"ok": True, "message_id": msg.id}


@router.get("/file/{file_id}")
async def get_people_feedback_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Proxy a Telegram voice note / document attached to a people-feedback ticket.

    Privacy: requires admin or agency_dev role. ADM users get 403 (same as
    every other read endpoint in this module).

    Security: verifies the file_id actually exists on a people-feedback ticket
    or message before pulling from Telegram. Prevents this endpoint from
    becoming an open proxy for arbitrary Telegram files.
    """
    _require_agency_dev(current_user)

    # Verify the file_id is one we own — either initial submission or any reply
    exists_on_ticket = db.query(AgentPeopleFeedback).filter(
        or_(
            AgentPeopleFeedback.voice_file_id == file_id,
            AgentPeopleFeedback.attachment_file_id == file_id,
        )
    ).first()
    exists_on_msg = db.query(AgentPeopleFeedbackMessage).filter(
        or_(
            AgentPeopleFeedbackMessage.voice_file_id == file_id,
            AgentPeopleFeedbackMessage.attachment_file_id == file_id,
        )
    ).first()
    if not (exists_on_ticket or exists_on_msg):
        raise HTTPException(404, "File not found on any people-feedback record")

    # Build list of bot tokens to try — voice could be from agent bot OR ADM bot
    tokens = []
    if settings.AGENT_TELEGRAM_BOT_TOKEN:
        tokens.append(settings.AGENT_TELEGRAM_BOT_TOKEN)
    if settings.TELEGRAM_BOT_TOKEN:
        tokens.append(settings.TELEGRAM_BOT_TOKEN)
    if not tokens:
        raise HTTPException(503, "Telegram integration not configured on the server")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: ask Telegram for the file_path — try each token
            data = None
            winning_token = tokens[0]
            for t in tokens:
                resp = await client.get(
                    f"https://api.telegram.org/bot{t}/getFile",
                    params={"file_id": file_id},
                )
                if resp.status_code == 200:
                    d = resp.json()
                    if d.get("ok"):
                        data = d
                        winning_token = t
                        break

            if not data or not data.get("ok"):
                raise HTTPException(404, "File not found on Telegram")

            file_path = data["result"].get("file_path", "")
            if not file_path:
                raise HTTPException(404, "Telegram returned no file_path")

            # Step 2: download the actual bytes
            file_resp = await client.get(
                f"https://api.telegram.org/file/bot{winning_token}/{file_path}"
            )
            if file_resp.status_code != 200:
                raise HTTPException(502, "Failed to fetch file bytes from Telegram")

            # Step 3: pick a content-type by extension
            ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
            content_type_map = {
                "ogg": "audio/ogg",
                "oga": "audio/ogg",
                "opus": "audio/ogg",
                "mp3": "audio/mpeg",
                "m4a": "audio/mp4",
                "wav": "audio/wav",
                "pdf": "application/pdf",
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "gif": "image/gif",
                "webp": "image/webp",
                "mp4": "video/mp4",
                "doc": "application/msword",
                "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "xls": "application/vnd.ms-excel",
                "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "csv": "text/csv",
                "txt": "text/plain",
                "zip": "application/zip",
            }
            content_type = content_type_map.get(ext, "application/octet-stream")
            filename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path

            return StreamingResponse(
                iter([file_resp.content]),
                media_type=content_type,
                headers={
                    "Content-Disposition": f'inline; filename="{filename}"',
                    "Content-Length": str(len(file_resp.content)),
                    "Cache-Control": "private, max-age=300",
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("people-feedback file proxy error: %s", e)
        raise HTTPException(500, "Failed to retrieve file")


# Also serialise the file_ids in ticket/message responses so the frontend
# can construct playback URLs. We patch the existing serialisers to include
# voice_file_id / attachment_file_id (these are the values needed to call
# /people-feedback/file/{file_id}).
@router.patch("/{ticket_id}/status")
def change_status(
    ticket_id: int,
    req: StatusChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Move ticket through the workflow lifecycle."""
    _require_agency_dev(current_user)

    if req.new_status not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of {sorted(VALID_STATUSES)}")

    ticket = db.query(AgentPeopleFeedback).filter(AgentPeopleFeedback.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    old_status = ticket.status
    ticket.status = req.new_status
    if req.new_status == "escalated" and not ticket.escalated_at:
        ticket.escalated_at = datetime.utcnow()
    ticket.updated_at = datetime.utcnow()

    # Audit trail in the thread
    audit_text = f"Status: {old_status} → {req.new_status}"
    if req.note:
        audit_text += f"\nNote: {req.note}"
    audit_msg = AgentPeopleFeedbackMessage(
        ticket_id=ticket.id,
        sender_role="agency_dev",
        sender_user_id=current_user.id,
        sender_name=current_user.name,
        text=audit_text,
        message_type="status_change",
        is_status_change=True,
    )
    db.add(audit_msg)
    db.commit()
    return {"ok": True, "old_status": old_status, "new_status": req.new_status}
