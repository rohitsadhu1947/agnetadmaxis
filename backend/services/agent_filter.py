"""
Agent filter engine — resolves a JSON filter spec to a list of agent rows.

Used by:
  - /broadcasts/preview-recipients (returns the resolved list to the composer)
  - The dispatcher when materialising broadcast_recipients rows

Filter spec shape (all fields optional; intersection semantics):

    {
        "all_agents": false,                        // shortcut for "everyone telegram-registered"
        "cohort_segments": ["sleeping_giants", ...],
        "regions": ["Mumbai", "Delhi"],             // matches agents.location case-insensitive
        "states": ["Maharashtra"],                  // matches agents.state
        "lifecycle_states": ["active", "productive"],
        "adm_ids": [1, 2, 3],
        "score_min": 60,                            // reactivation_score >= 60
        "score_max": 100,
        "agent_ids": [123, 456],                    // explicit list (CSV upload path)
        "only_telegram_registered": true            // default true — agents with chat_id only
    }

Returns: list of Agent rows.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any

from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from models import Agent


def resolve_filter(db: Session, spec: Dict[str, Any]) -> List[Agent]:
    """Apply the filter spec to the agents table and return matching rows.

    Always intersects with `telegram_chat_id IS NOT NULL` unless the caller
    explicitly opts out via `only_telegram_registered: false`. We do this
    because broadcasts on the Telegram channel can't reach agents who never
    linked their phone to the bot.
    """
    q = db.query(Agent)

    only_tg = spec.get("only_telegram_registered", True)
    if only_tg:
        q = q.filter(Agent.telegram_chat_id.isnot(None))

    # all_agents shortcut — just return everything that passed the tg filter
    if spec.get("all_agents"):
        return q.all()

    cohort_segments = spec.get("cohort_segments") or []
    if cohort_segments:
        q = q.filter(Agent.cohort_segment.in_(cohort_segments))

    regions = spec.get("regions") or []
    if regions:
        norm = [r.strip().lower() for r in regions if r]
        if norm:
            q = q.filter(func.lower(Agent.location).in_(norm))

    states = spec.get("states") or []
    if states:
        q = q.filter(Agent.state.in_(states))

    lifecycle_states = spec.get("lifecycle_states") or []
    if lifecycle_states:
        q = q.filter(Agent.lifecycle_state.in_(lifecycle_states))

    adm_ids = spec.get("adm_ids") or []
    if adm_ids:
        q = q.filter(Agent.assigned_adm_id.in_(adm_ids))

    score_min = spec.get("score_min")
    score_max = spec.get("score_max")
    if score_min is not None:
        q = q.filter(Agent.reactivation_score >= float(score_min))
    if score_max is not None:
        q = q.filter(Agent.reactivation_score <= float(score_max))

    agent_ids = spec.get("agent_ids") or []
    if agent_ids:
        q = q.filter(Agent.id.in_(agent_ids))

    return q.all()


def summarise_filter(db: Session, spec: Dict[str, Any]) -> Dict[str, int]:
    """Return counts useful for the composer preview.

    Returns dict with:
      total_matched       — agents matching all filter dimensions
      reachable_telegram  — of those, how many have a telegram_chat_id
      skipped_no_chat     — total_matched - reachable_telegram
    """
    # Run twice: once without the tg filter, once with it.
    full_spec = {**spec, "only_telegram_registered": False}
    all_matched = resolve_filter(db, full_spec)
    reachable = [a for a in all_matched if a.telegram_chat_id]
    return {
        "total_matched": len(all_matched),
        "reachable_telegram": len(reachable),
        "skipped_no_chat": len(all_matched) - len(reachable),
    }
