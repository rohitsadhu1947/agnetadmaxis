"""
Broadcasts API — central team composes & schedules training/product/incentive/
announcement messages, targets filtered subsets of agents, and tracks delivery.

v1 channel: Telegram only (agent bot is the sender). WhatsApp adapter slots in
later without schema changes.

Endpoints:
  GET    /broadcasts                       List + filter (admin/agency_dev)
  POST   /broadcasts                       Create draft / schedule / send now
  GET    /broadcasts/{id}                  Detail
  PATCH  /broadcasts/{id}                  Edit draft (status=draft only)
  DELETE /broadcasts/{id}                  Cancel scheduled OR delete draft
  POST   /broadcasts/{id}/send             Force-send a scheduled one immediately
  POST   /broadcasts/{id}/retry-failed     Re-queue failed recipients
  POST   /broadcasts/preview-recipients    Resolve filter → counts (no save)
  GET    /broadcasts/{id}/status           Live status board data
  POST   /broadcasts/upload-attachment     Multipart file upload → stored as bytes
  GET    /broadcasts/meta/types            Reference: 4 broadcast types
  GET    /broadcasts/meta/filter-options   Reference: cohorts, regions, ADMs, lifecycle

Privacy: role-gated on admin/agency_dev for now. ADM role can't compose.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import (
    APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form,
)
from pydantic import BaseModel, Field
from sqlalchemy import desc, distinct
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Agent,
    ADM,
    User,
    Broadcast,
    BroadcastRecipient,
)
from routes.auth import get_current_user
from services.agent_filter import resolve_filter, summarise_filter

router = APIRouter(prefix="/broadcasts", tags=["Broadcasts"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
BROADCAST_TYPES: Dict[str, Dict[str, str]] = {
    "training":      {"label": "Training",      "color": "#60A5FA", "icon": "GraduationCap"},
    "product":       {"label": "Product",       "color": "#A78BFA", "icon": "Package"},
    "incentive":     {"label": "Incentive",     "color": "#34D399", "icon": "Trophy"},
    "announcement": {"label": "Announcement",  "color": "#FACC15", "icon": "Megaphone"},
}
VALID_TYPES = set(BROADCAST_TYPES.keys())

VALID_STATUSES = {"draft", "scheduled", "dispatching", "completed", "cancelled", "failed"}
EDITABLE_STATUSES = {"draft"}

VALID_ATTACHMENT_KINDS = {"image", "voice", "document"}
COMPOSER_ROLES = {"admin", "agency_dev"}


def _require_composer(user: User) -> None:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if user.role not in COMPOSER_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Access denied. Broadcasts can only be composed by admin or agency_dev users.",
        )


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class TargetFilterSpec(BaseModel):
    """All fields optional, intersection semantics. See agent_filter.resolve_filter."""
    all_agents: Optional[bool] = False
    cohort_segments: Optional[List[str]] = None
    regions: Optional[List[str]] = None
    states: Optional[List[str]] = None
    lifecycle_states: Optional[List[str]] = None
    adm_ids: Optional[List[int]] = None
    score_min: Optional[float] = None
    score_max: Optional[float] = None
    agent_ids: Optional[List[int]] = None
    only_telegram_registered: Optional[bool] = True


class BroadcastBase(BaseModel):
    type: str
    title: str = Field(..., min_length=1, max_length=300)
    body: str = Field(..., min_length=1)
    link_url: Optional[str] = None
    link_label: Optional[str] = None
    target_filter: TargetFilterSpec
    scheduled_at: Optional[datetime] = None  # null = send immediately on dispatch
    channels: Optional[str] = "telegram"


class CreateBroadcastRequest(BroadcastBase):
    status: str = Field("draft", description="draft | scheduled")
    attachment_file_id: Optional[int] = Field(
        None,
        description=(
            "ID returned from /broadcasts/upload-attachment when an attachment is "
            "included. Internally maps to broadcast attachment_bytes."
        ),
    )


class PatchBroadcastRequest(BaseModel):
    """All fields optional — only updates what's provided."""
    type: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    link_url: Optional[str] = None
    link_label: Optional[str] = None
    target_filter: Optional[TargetFilterSpec] = None
    scheduled_at: Optional[datetime] = None
    status: Optional[str] = None
    # Special: pass attachment_file_id=null to clear an existing attachment
    attachment_file_id: Optional[int] = None
    clear_attachment: Optional[bool] = False


class PreviewRecipientsRequest(BaseModel):
    target_filter: TargetFilterSpec


# ---------------------------------------------------------------------------
# In-memory "attachment staging" — kept inside Broadcast rows we create as
# `status=draft, title="__attachment_stage__"` so we don't need a new table.
# When the composer references attachment_file_id, we copy the bytes into the
# real broadcast row and delete the staged row.
# ---------------------------------------------------------------------------
ATTACHMENT_STAGE_TITLE = "__attachment_stage__"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _generate_ref(db: Session) -> str:
    year = datetime.utcnow().year
    count = (
        db.query(Broadcast)
        .filter(Broadcast.broadcast_ref.like(f"BR-{year}-%"))
        .count()
    )
    return f"BR-{year}-{count + 1:05d}"


def _serialize_broadcast(b: Broadcast, include_recipients: bool = False) -> dict:
    type_meta = BROADCAST_TYPES.get(b.type, {})
    d = {
        "id": b.id,
        "broadcast_ref": b.broadcast_ref,
        "type": b.type,
        "type_label": type_meta.get("label"),
        "type_color": type_meta.get("color"),
        "type_icon": type_meta.get("icon"),
        "title": b.title,
        "body": b.body,
        "link_url": b.link_url,
        "link_label": b.link_label,
        "attachment_kind": b.attachment_kind,
        "attachment_file_name": b.attachment_file_name,
        "attachment_mime_type": b.attachment_mime_type,
        "attachment_size": b.attachment_size,
        "has_attachment": bool(b.attachment_bytes),
        "target_filter": json.loads(b.target_filter or "{}"),
        "status": b.status,
        "scheduled_at": b.scheduled_at.isoformat() if b.scheduled_at else None,
        "dispatched_at": b.dispatched_at.isoformat() if b.dispatched_at else None,
        "completed_at": b.completed_at.isoformat() if b.completed_at else None,
        "channels": b.channels,
        "recipient_count": b.recipient_count,
        "sent_count": b.sent_count,
        "failed_count": b.failed_count,
        "skipped_count": b.skipped_count,
        "created_by_name": b.created_by_name,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }
    if include_recipients:
        d["recipients"] = [_serialize_recipient(r) for r in b.recipients]
    return d


def _serialize_recipient(r: BroadcastRecipient) -> dict:
    return {
        "id": r.id,
        "agent_id": r.agent_id,
        "agent_name": r.agent.name if r.agent else None,
        "agent_phone": r.agent.phone if r.agent else None,
        "status": r.status,
        "telegram_message_id": r.telegram_message_id,
        "error_reason": r.error_reason,
        "attempts": r.attempts,
        "sent_at": r.sent_at.isoformat() if r.sent_at else None,
    }


def _validate_type(t: str) -> None:
    if t not in VALID_TYPES:
        raise HTTPException(400, f"Invalid type. Must be one of {sorted(VALID_TYPES)}")


def _validate_status(s: str) -> None:
    if s not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of {sorted(VALID_STATUSES)}")


def _validate_filter_not_empty(spec: dict) -> None:
    """Reject a filter that would resolve to "no agents specified" — i.e.,
    everything is empty AND all_agents is False. Avoids accidentally dispatching
    a broadcast with zero recipients."""
    if spec.get("all_agents"):
        return
    populated_fields = [
        spec.get("cohort_segments"),
        spec.get("regions"),
        spec.get("states"),
        spec.get("lifecycle_states"),
        spec.get("adm_ids"),
        spec.get("agent_ids"),
    ]
    has_any = any(v for v in populated_fields)
    score_set = (spec.get("score_min") is not None) or (spec.get("score_max") is not None)
    if not (has_any or score_set):
        raise HTTPException(
            400,
            "Target filter is empty. Choose at least one filter dimension or set all_agents=true.",
        )


def _apply_attachment_from_stage(db: Session, target: Broadcast, stage_id: int) -> None:
    """Copy attachment_bytes from a stage row to the target broadcast row, then
    delete the stage row. Stage rows are created via /upload-attachment."""
    stage = db.query(Broadcast).filter(
        Broadcast.id == stage_id,
        Broadcast.title == ATTACHMENT_STAGE_TITLE,
    ).first()
    if not stage:
        raise HTTPException(404, f"Attachment stage id {stage_id} not found")
    target.attachment_kind = stage.attachment_kind
    target.attachment_file_name = stage.attachment_file_name
    target.attachment_mime_type = stage.attachment_mime_type
    target.attachment_bytes = stage.attachment_bytes
    target.attachment_size = stage.attachment_size
    db.delete(stage)


# ---------------------------------------------------------------------------
# Reference data endpoints
# ---------------------------------------------------------------------------
@router.get("/meta/types")
def get_types(current_user: User = Depends(get_current_user)):
    _require_composer(current_user)
    return {
        "types": [
            {"key": k, "label": v["label"], "color": v["color"], "icon": v["icon"]}
            for k, v in BROADCAST_TYPES.items()
        ]
    }


@router.get("/meta/filter-options")
def get_filter_options(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the multi-select sources the composer needs to render dropdowns."""
    _require_composer(current_user)

    cohorts = (
        db.query(distinct(Agent.cohort_segment))
        .filter(Agent.cohort_segment.isnot(None))
        .all()
    )
    cohorts_list = sorted([c[0] for c in cohorts if c[0]])

    regions = (
        db.query(distinct(Agent.location))
        .filter(Agent.location.isnot(None))
        .all()
    )
    regions_list = sorted([r[0] for r in regions if r[0]])

    states = (
        db.query(distinct(Agent.state))
        .filter(Agent.state.isnot(None))
        .all()
    )
    states_list = sorted([s[0] for s in states if s[0]])

    lifecycle = (
        db.query(distinct(Agent.lifecycle_state))
        .filter(Agent.lifecycle_state.isnot(None))
        .all()
    )
    lifecycle_list = sorted([l[0] for l in lifecycle if l[0]])

    adms = db.query(ADM).order_by(ADM.name).all()
    adm_options = [{"id": a.id, "name": a.name, "region": a.region} for a in adms]

    return {
        "cohort_segments": cohorts_list,
        "regions": regions_list,
        "states": states_list,
        "lifecycle_states": lifecycle_list,
        "adms": adm_options,
        "score_range": {"min": 0, "max": 100},
        "telegram_registered_count": db.query(Agent)
            .filter(Agent.telegram_chat_id.isnot(None))
            .count(),
        "total_agents": db.query(Agent).count(),
    }


# ---------------------------------------------------------------------------
# Preview endpoint — composer hits this on every filter change
# ---------------------------------------------------------------------------
@router.post("/preview-recipients")
def preview_recipients(
    req: PreviewRecipientsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_composer(current_user)
    spec = req.target_filter.dict(exclude_none=True)
    summary = summarise_filter(db, spec)
    # Also return a small sample (first 8 names) so the composer can show them
    sample = resolve_filter(db, {**spec, "only_telegram_registered": True})[:8]
    return {
        **summary,
        "sample_recipients": [
            {"id": a.id, "name": a.name, "location": a.location, "cohort_segment": a.cohort_segment}
            for a in sample
        ],
    }


# ---------------------------------------------------------------------------
# Attachment upload — receives multipart file, stores bytes in a "stage" row
# ---------------------------------------------------------------------------
@router.post("/upload-attachment")
async def upload_attachment(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Receive a file from the composer. Persists bytes in a staging Broadcast
    row keyed by id; the composer references that id on create/patch."""
    _require_composer(current_user)

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    if len(raw) > 20 * 1024 * 1024:  # 20MB hard cap (Telegram document limit)
        raise HTTPException(400, "File exceeds 20MB Telegram limit")

    mime = (file.content_type or "").lower()
    fname = file.filename or "attachment"
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""

    # Classify attachment kind
    if mime.startswith("image/") or ext in ("png", "jpg", "jpeg", "webp", "gif"):
        kind = "image"
    elif mime in ("audio/ogg", "audio/opus") or ext in ("ogg", "opus"):
        kind = "voice"
    else:
        kind = "document"

    stage = Broadcast(
        broadcast_ref=f"STAGE-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
        type="announcement",  # filler — never sent
        title=ATTACHMENT_STAGE_TITLE,
        body="(staged attachment — not for sending)",
        status="draft",
        target_filter="{}",
        attachment_kind=kind,
        attachment_file_name=fname,
        attachment_mime_type=mime or None,
        attachment_bytes=base64.b64encode(raw).decode("ascii"),
        attachment_size=len(raw),
        created_by_user_id=current_user.id,
        created_by_name=current_user.name,
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return {
        "attachment_file_id": stage.id,
        "kind": kind,
        "file_name": fname,
        "mime_type": mime,
        "size": len(raw),
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.post("", status_code=201)
@router.post("/", status_code=201)
def create_broadcast(
    req: CreateBroadcastRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_composer(current_user)
    _validate_type(req.type)
    if req.status not in ("draft", "scheduled"):
        raise HTTPException(400, "On create, status must be 'draft' or 'scheduled'")

    spec_dict = req.target_filter.dict(exclude_none=True)

    if req.status == "scheduled":
        # Schedule mode: filter must be non-empty
        _validate_filter_not_empty(spec_dict)
        if req.scheduled_at is None:
            raise HTTPException(400, "scheduled_at required when status is 'scheduled'")
        if req.scheduled_at < datetime.utcnow():
            raise HTTPException(400, "scheduled_at must be in the future")

    bc = Broadcast(
        broadcast_ref=_generate_ref(db),
        type=req.type,
        title=req.title,
        body=req.body,
        link_url=req.link_url,
        link_label=req.link_label,
        target_filter=json.dumps(spec_dict),
        scheduled_at=req.scheduled_at,
        status=req.status,
        channels=req.channels or "telegram",
        created_by_user_id=current_user.id,
        created_by_name=current_user.name,
    )

    if req.attachment_file_id is not None:
        _apply_attachment_from_stage(db, bc, req.attachment_file_id)

    db.add(bc)
    db.commit()
    db.refresh(bc)

    logger.info(
        "Broadcast created: ref=%s type=%s status=%s by user_id=%s",
        bc.broadcast_ref, bc.type, bc.status, current_user.id,
    )
    return _serialize_broadcast(bc)


@router.get("")
@router.get("/")
def list_broadcasts(
    status_filter: Optional[str] = Query(None, alias="status"),
    type_filter: Optional[str] = Query(None, alias="type"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_composer(current_user)

    q = db.query(Broadcast).filter(Broadcast.title != ATTACHMENT_STAGE_TITLE)
    if status_filter:
        _validate_status(status_filter)
        q = q.filter(Broadcast.status == status_filter)
    if type_filter:
        _validate_type(type_filter)
        q = q.filter(Broadcast.type == type_filter)

    total = q.count()
    rows = (
        q.order_by(desc(Broadcast.created_at))
        .offset(offset).limit(limit).all()
    )
    return {
        "total": total,
        "count": len(rows),
        "broadcasts": [_serialize_broadcast(b) for b in rows],
    }


@router.get("/meta/stats")
def stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stat tiles for the broadcasts list page."""
    _require_composer(current_user)
    rows = (
        db.query(Broadcast.status)
        .filter(Broadcast.title != ATTACHMENT_STAGE_TITLE)
        .all()
    )
    by_status = {s: 0 for s in VALID_STATUSES}
    for (s,) in rows:
        by_status[s] = by_status.get(s, 0) + 1
    return {"by_status": by_status, "total": sum(by_status.values())}


@router.get("/{broadcast_id}")
def get_broadcast(
    broadcast_id: int,
    include_recipients: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_composer(current_user)
    bc = db.query(Broadcast).filter(
        Broadcast.id == broadcast_id,
        Broadcast.title != ATTACHMENT_STAGE_TITLE,
    ).first()
    if not bc:
        raise HTTPException(404, "Broadcast not found")
    return _serialize_broadcast(bc, include_recipients=include_recipients)


@router.patch("/{broadcast_id}")
def patch_broadcast(
    broadcast_id: int,
    req: PatchBroadcastRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_composer(current_user)
    bc = db.query(Broadcast).filter(
        Broadcast.id == broadcast_id,
        Broadcast.title != ATTACHMENT_STAGE_TITLE,
    ).first()
    if not bc:
        raise HTTPException(404, "Broadcast not found")
    if bc.status not in EDITABLE_STATUSES:
        raise HTTPException(400, f"Cannot edit broadcast in status '{bc.status}'")

    if req.type is not None:
        _validate_type(req.type)
        bc.type = req.type
    if req.title is not None:
        bc.title = req.title
    if req.body is not None:
        bc.body = req.body
    if req.link_url is not None:
        bc.link_url = req.link_url
    if req.link_label is not None:
        bc.link_label = req.link_label
    if req.target_filter is not None:
        bc.target_filter = json.dumps(req.target_filter.dict(exclude_none=True))
    if req.scheduled_at is not None:
        bc.scheduled_at = req.scheduled_at
    if req.status is not None:
        if req.status not in ("draft", "scheduled"):
            raise HTTPException(400, "Status can only be moved to draft or scheduled here")
        if req.status == "scheduled":
            spec = json.loads(bc.target_filter or "{}")
            _validate_filter_not_empty(spec)
            if bc.scheduled_at is None or bc.scheduled_at < datetime.utcnow():
                raise HTTPException(400, "Need a future scheduled_at to move to 'scheduled'")
        bc.status = req.status

    if req.clear_attachment:
        bc.attachment_kind = None
        bc.attachment_file_name = None
        bc.attachment_mime_type = None
        bc.attachment_bytes = None
        bc.attachment_size = None
        bc.cached_telegram_file_id = None
    elif req.attachment_file_id is not None:
        _apply_attachment_from_stage(db, bc, req.attachment_file_id)

    bc.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(bc)
    return _serialize_broadcast(bc)


@router.delete("/{broadcast_id}")
def delete_broadcast(
    broadcast_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_composer(current_user)
    bc = db.query(Broadcast).filter(
        Broadcast.id == broadcast_id,
        Broadcast.title != ATTACHMENT_STAGE_TITLE,
    ).first()
    if not bc:
        raise HTTPException(404, "Broadcast not found")

    if bc.status in ("draft",):
        db.delete(bc)
        db.commit()
        return {"ok": True, "action": "deleted"}
    if bc.status == "scheduled":
        bc.status = "cancelled"
        bc.updated_at = datetime.utcnow()
        db.commit()
        return {"ok": True, "action": "cancelled"}
    raise HTTPException(
        400, f"Cannot delete a broadcast in status '{bc.status}'. Only drafts can be deleted; scheduled ones are cancelled.",
    )


@router.post("/{broadcast_id}/send")
def send_now(
    broadcast_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Move a draft directly to scheduled-immediately so the dispatcher picks it up."""
    _require_composer(current_user)
    bc = db.query(Broadcast).filter(
        Broadcast.id == broadcast_id,
        Broadcast.title != ATTACHMENT_STAGE_TITLE,
    ).first()
    if not bc:
        raise HTTPException(404, "Broadcast not found")
    if bc.status not in ("draft", "scheduled"):
        raise HTTPException(400, f"Broadcast in status '{bc.status}' cannot be sent")

    spec = json.loads(bc.target_filter or "{}")
    _validate_filter_not_empty(spec)

    bc.scheduled_at = datetime.utcnow()
    bc.status = "scheduled"
    bc.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "status": bc.status, "scheduled_at": bc.scheduled_at.isoformat()}


@router.post("/{broadcast_id}/retry-failed")
def retry_failed(
    broadcast_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_composer(current_user)
    bc = db.query(Broadcast).filter(
        Broadcast.id == broadcast_id,
        Broadcast.title != ATTACHMENT_STAGE_TITLE,
    ).first()
    if not bc:
        raise HTTPException(404, "Broadcast not found")

    failed = db.query(BroadcastRecipient).filter(
        BroadcastRecipient.broadcast_id == bc.id,
        BroadcastRecipient.status == "failed",
    ).all()
    for r in failed:
        r.status = "queued"
        r.error_reason = None
    # Re-open the broadcast for the dispatcher
    if bc.status == "completed" and failed:
        bc.status = "dispatching"
    bc.failed_count = 0
    db.commit()
    return {"ok": True, "requeued": len(failed)}


@router.get("/{broadcast_id}/status")
def status_board(
    broadcast_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the live status board: counts + a sample of failed (with reasons)."""
    _require_composer(current_user)
    bc = db.query(Broadcast).filter(
        Broadcast.id == broadcast_id,
        Broadcast.title != ATTACHMENT_STAGE_TITLE,
    ).first()
    if not bc:
        raise HTTPException(404, "Broadcast not found")

    counts = {
        "queued": db.query(BroadcastRecipient).filter(
            BroadcastRecipient.broadcast_id == bc.id,
            BroadcastRecipient.status == "queued",
        ).count(),
        "sent": db.query(BroadcastRecipient).filter(
            BroadcastRecipient.broadcast_id == bc.id,
            BroadcastRecipient.status == "sent",
        ).count(),
        "failed": db.query(BroadcastRecipient).filter(
            BroadcastRecipient.broadcast_id == bc.id,
            BroadcastRecipient.status == "failed",
        ).count(),
        "skipped": db.query(BroadcastRecipient).filter(
            BroadcastRecipient.broadcast_id == bc.id,
            BroadcastRecipient.status == "skipped",
        ).count(),
    }
    failed_sample = db.query(BroadcastRecipient).filter(
        BroadcastRecipient.broadcast_id == bc.id,
        BroadcastRecipient.status == "failed",
    ).limit(10).all()
    return {
        "broadcast_id": bc.id,
        "ref": bc.broadcast_ref,
        "status": bc.status,
        "recipient_count": bc.recipient_count,
        "counts": counts,
        "scheduled_at": bc.scheduled_at.isoformat() if bc.scheduled_at else None,
        "dispatched_at": bc.dispatched_at.isoformat() if bc.dispatched_at else None,
        "completed_at": bc.completed_at.isoformat() if bc.completed_at else None,
        "failed_sample": [_serialize_recipient(r) for r in failed_sample],
    }
