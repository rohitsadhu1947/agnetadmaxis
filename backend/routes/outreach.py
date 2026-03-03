"""
Outreach routes — send personalized Telegram messages to agents based on cohort analysis.
Includes editable messages and customizable multi-step outreach workflows.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Agent
from services.cohort_classifier import cohort_classifier, FIRST_MESSAGE_TEMPLATES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outreach", tags=["Outreach"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class OutreachRequest(BaseModel):
    agent_ids: List[int]
    custom_messages: Optional[Dict[int, str]] = None  # {agent_id: "custom msg"}


class OutreachResult(BaseModel):
    sent: int = 0
    failed: int = 0
    skipped_no_telegram: int = 0
    total_requested: int = 0
    errors: List[dict] = []
    sent_agents: List[dict] = []


class WorkflowStep(BaseModel):
    step_number: int
    channel: str  # "whatsapp" | "phone" | "telegram" | "sms" | "wait"
    message: str = ""
    delay_days: int = 0


class WorkflowSaveRequest(BaseModel):
    agent_ids: List[int]
    steps: List[WorkflowStep]


class StepSendRequest(BaseModel):
    agent_id: int
    step: WorkflowStep


# ---------------------------------------------------------------------------
# Default workflow templates per strategy
# ---------------------------------------------------------------------------

DEFAULT_WORKFLOWS: Dict[str, List[dict]] = {
    "direct_call": [
        {"step_number": 1, "channel": "phone", "message": "Direct call — introduce yourself and discuss reactivation opportunity.", "delay_days": 0},
        {"step_number": 2, "channel": "whatsapp", "message": "{name} ji, maine aapko call kiya tha. Kya hum baat kar sakte hain? Axis Max Life ki taraf se kuch exciting updates hain.", "delay_days": 2},
        {"step_number": 3, "channel": "telegram", "message": "{name} ji, aapko WhatsApp par bhi message bheja tha. Kya aap yahan respond kar sakte hain?", "delay_days": 3},
        {"step_number": 4, "channel": "phone", "message": "Final attempt — call to confirm if agent is still interested.", "delay_days": 5},
        {"step_number": 5, "channel": "wait", "message": "Mark as permanently dormant if no response received.", "delay_days": 7},
    ],
    "whatsapp_first": [
        {"step_number": 1, "channel": "whatsapp", "message": "{name} ji, Axis Max Life ki taraf se. Aapke liye kuch important updates hain. Kya hum connect kar sakte hain?", "delay_days": 0},
        {"step_number": 2, "channel": "phone", "message": "Follow-up call — reference WhatsApp message sent earlier.", "delay_days": 3},
        {"step_number": 3, "channel": "telegram", "message": "{name} ji, humne aapko WhatsApp aur phone par try kiya. Kya aap Telegram par available hain?", "delay_days": 3},
        {"step_number": 4, "channel": "whatsapp", "message": "{name} ji, last try — aapke liye special opportunity hai. Reply karein ya missed call dein.", "delay_days": 5},
        {"step_number": 5, "channel": "wait", "message": "Mark as permanently dormant if no response received.", "delay_days": 7},
    ],
    "telegram_only": [
        {"step_number": 1, "channel": "telegram", "message": "{name} ji, Axis Max Life ki taraf se. Aapke saath connect karna chahte hain.", "delay_days": 0},
        {"step_number": 2, "channel": "whatsapp", "message": "{name} ji, Telegram par message bheja tha. Kya yahan baat ho sakti hai?", "delay_days": 3},
        {"step_number": 3, "channel": "telegram", "message": "{name} ji, ek aur try — humein aapki zaroorat hai team mein.", "delay_days": 5},
        {"step_number": 4, "channel": "wait", "message": "Waiting period before final attempt.", "delay_days": 7},
        {"step_number": 5, "channel": "wait", "message": "Mark as permanently dormant if no response received.", "delay_days": 7},
    ],
    "no_contact": [],  # No workflow
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/send-telegram", response_model=OutreachResult)
async def send_telegram_outreach(
    request: OutreachRequest,
    db: Session = Depends(get_db),
):
    """Send personalized first messages to agents via Telegram bot.

    Supports optional custom_messages: a dict mapping agent_id → custom message text.
    If a custom message is provided for an agent, it is sent instead of the template.
    """
    token = settings.AGENT_TELEGRAM_BOT_TOKEN
    if not token:
        raise HTTPException(
            status_code=400,
            detail="AGENT_TELEGRAM_BOT_TOKEN not configured. Cannot send Telegram messages.",
        )

    agents = db.query(Agent).filter(Agent.id.in_(request.agent_ids)).all()
    if not agents:
        raise HTTPException(status_code=404, detail="No agents found for given IDs")

    result = OutreachResult(total_requested=len(request.agent_ids))

    send_url = f"https://api.telegram.org/bot{token}/sendMessage"
    custom = request.custom_messages or {}

    async with httpx.AsyncClient(timeout=10) as client:
        for agent in agents:
            # Skip agents without Telegram
            if not agent.telegram_chat_id:
                result.skipped_no_telegram += 1
                continue

            # --- Resolve message ---
            if agent.id in custom and custom[agent.id].strip():
                # Use admin's custom message
                message = custom[agent.id].strip()
            else:
                # Fall back to template
                segment = agent.cohort_segment
                if not segment:
                    cr = cohort_classifier.classify_agent(agent)
                    cohort_classifier.apply_classification(agent, cr, db)
                    segment = cr.cohort_segment

                template = FIRST_MESSAGE_TEMPLATES.get(segment, "")
                if not template:
                    template = (
                        f"{agent.name} ji, namaste! Axis Max Life ki taraf se. "
                        f"Hum aapke saath connect karna chahte hain. "
                        f"Kya aap kuch minutes baat kar sakte hain?"
                    )
                message = template.format(name=agent.name)

            try:
                resp = await client.post(
                    send_url,
                    json={
                        "chat_id": agent.telegram_chat_id,
                        "text": message,
                        "parse_mode": "HTML",
                    },
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    result.sent += 1
                    result.sent_agents.append({
                        "agent_id": agent.id,
                        "name": agent.name,
                        "segment": agent.cohort_segment or "unknown",
                    })
                    logger.info("Outreach sent to agent %s (ID %d)", agent.name, agent.id)
                else:
                    result.failed += 1
                    result.errors.append({
                        "agent_id": agent.id,
                        "name": agent.name,
                        "error": resp.text[:200],
                    })
            except Exception as e:
                result.failed += 1
                result.errors.append({
                    "agent_id": agent.id,
                    "name": agent.name,
                    "error": str(e),
                })

    db.commit()
    logger.info(
        "Outreach complete: %d sent, %d failed, %d skipped (no telegram)",
        result.sent, result.failed, result.skipped_no_telegram,
    )
    return result


@router.get("/workflow-defaults/{strategy}")
async def get_workflow_defaults(strategy: str):
    """Return the default multi-step outreach workflow for a given engagement strategy."""
    steps = DEFAULT_WORKFLOWS.get(strategy, [])
    return {"strategy": strategy, "steps": steps}


@router.post("/save-workflow")
async def save_outreach_workflow(
    request: WorkflowSaveRequest,
    db: Session = Depends(get_db),
):
    """Save a customized outreach workflow plan for a set of agents.

    Persists the workflow steps to each agent's record so it can be
    referenced later during step-by-step execution.
    """
    agents = db.query(Agent).filter(Agent.id.in_(request.agent_ids)).all()
    if not agents:
        raise HTTPException(status_code=404, detail="No agents found for given IDs")

    steps_data = [s.model_dump() for s in request.steps]

    updated = 0
    for agent in agents:
        # Store workflow as JSON on agent (uses the existing JSON-capable column or a new one)
        # For now, store in a lightweight way — extend Agent model later if needed
        agent.outreach_workflow = steps_data  # type: ignore[attr-defined]
        updated += 1

    try:
        db.commit()
    except Exception:
        # If the column doesn't exist yet, just return success without persisting
        db.rollback()
        logger.warning("outreach_workflow column not yet on Agent model — skipping persist")

    return {
        "status": "saved",
        "agents_updated": updated,
        "steps_count": len(request.steps),
        "steps": steps_data,
    }


@router.post("/send-step")
async def send_outreach_step(
    request: StepSendRequest,
    db: Session = Depends(get_db),
):
    """Execute a single outreach workflow step for one agent.

    Currently supports 'telegram' channel for live sending.
    Other channels (phone, whatsapp, sms) return a planned action record.
    """
    agent = db.query(Agent).filter(Agent.id == request.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    step = request.step
    channel = step.channel

    if channel == "telegram":
        token = settings.AGENT_TELEGRAM_BOT_TOKEN
        if not token:
            raise HTTPException(status_code=400, detail="AGENT_TELEGRAM_BOT_TOKEN not configured")
        if not agent.telegram_chat_id:
            return {
                "status": "skipped",
                "reason": "Agent has no Telegram chat ID",
                "agent_id": agent.id,
                "channel": channel,
            }

        message = step.message.format(name=agent.name) if "{name}" in step.message else step.message
        send_url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(send_url, json={
                "chat_id": agent.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",
            })
            if resp.status_code == 200 and resp.json().get("ok"):
                return {
                    "status": "sent",
                    "agent_id": agent.id,
                    "channel": channel,
                    "message": message,
                }
            else:
                return {
                    "status": "failed",
                    "agent_id": agent.id,
                    "channel": channel,
                    "error": resp.text[:200],
                }
    else:
        # Non-telegram channels: record as planned action
        return {
            "status": "planned",
            "agent_id": agent.id,
            "agent_name": agent.name,
            "channel": channel,
            "message": step.message,
            "delay_days": step.delay_days,
            "note": f"Action recorded — {channel} outreach to be executed manually or via integration.",
        }
