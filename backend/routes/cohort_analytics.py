"""
Cohort analytics endpoints.
Provides cohort distribution, segment detail, agent-level analysis,
reclassification triggers, engagement plans, and trend data.
"""

from __future__ import annotations

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import Agent
from services.cohort_classifier import (
    cohort_classifier,
    CohortClassifier,
    SEGMENT_INFO,
    FIRST_MESSAGE_TEMPLATES,
)
from domain.enums import CohortSegment, EngagementStrategy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cohort", tags=["Cohort Analytics"])


# ---------------------------------------------------------------------------
# Request / response helpers
# ---------------------------------------------------------------------------

class ReclassifyRequest(BaseModel):
    """Optional list of agent IDs to reclassify. If None, reclassify all."""
    agent_ids: Optional[List[int]] = None


# ---------------------------------------------------------------------------
# 1. GET /cohort/summary
# ---------------------------------------------------------------------------

@router.get("/summary")
def get_cohort_summary(
    adm_id: Optional[int] = Query(None, description="Filter by assigned ADM ID"),
    db: Session = Depends(get_db),
):
    """
    Return cohort distribution summary.

    Provides total agent count, classified count, segment array with
    per-segment stats, average reactivation score, strategy distribution,
    and risk-level distribution.
    """
    base_query = db.query(Agent)
    if adm_id is not None:
        base_query = base_query.filter(Agent.assigned_adm_id == adm_id)

    agents = base_query.all()
    total_agents = len(agents)

    if total_agents == 0:
        return {
            "total_agents": 0,
            "classified_count": 0,
            "segments": [],
            "avg_reactivation_score": 0.0,
            "strategy_distribution": {},
            "risk_distribution": {},
        }

    # Build per-segment stats
    seg_data: dict[str, dict] = {}     # segment → {count, score_sum}
    strategy_distribution: dict[str, int] = {}
    risk_distribution: dict[str, int] = {}
    score_sum = 0.0
    classified_count = 0

    for agent in agents:
        seg = agent.cohort_segment or "unclassified"
        if seg not in seg_data:
            seg_data[seg] = {"count": 0, "score_sum": 0.0}
        seg_data[seg]["count"] += 1
        seg_data[seg]["score_sum"] += agent.reactivation_score or 0.0

        strat = agent.engagement_strategy or "unassigned"
        strategy_distribution[strat] = strategy_distribution.get(strat, 0) + 1

        risk = agent.churn_risk_level or "unknown"
        risk_distribution[risk] = risk_distribution.get(risk, 0) + 1

        score_sum += agent.reactivation_score or 0.0

        if agent.cohort_segment:
            classified_count += 1

    avg_reactivation_score = round(score_sum / total_agents, 1) if total_agents > 0 else 0.0

    # Build segments array with avg_score and strategy from SEGMENT_INFO
    segments = []
    for seg_key, data in seg_data.items():
        if seg_key == "unclassified":
            continue
        avg_seg_score = round(data["score_sum"] / data["count"], 1) if data["count"] > 0 else 0.0
        # Get recommended strategy from SEGMENT_INFO
        try:
            seg_enum = CohortSegment(seg_key)
            info = SEGMENT_INFO.get(seg_enum, {})
            strategy = info.get("strategy", EngagementStrategy.WHATSAPP_FIRST).value
        except ValueError:
            strategy = "whatsapp_first"
        segments.append({
            "segment": seg_key,
            "count": data["count"],
            "avg_score": avg_seg_score,
            "strategy": strategy,
        })
    segments.sort(key=lambda x: x["count"], reverse=True)

    return {
        "total_agents": total_agents,
        "classified_count": classified_count,
        "segments": segments,
        "avg_reactivation_score": avg_reactivation_score,
        "strategy_distribution": strategy_distribution,
        "risk_distribution": risk_distribution,
    }


# ---------------------------------------------------------------------------
# 2. GET /cohort/segments/{segment}
# ---------------------------------------------------------------------------

@router.get("/segments/{segment}")
def get_segment_agents(
    segment: str,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    db: Session = Depends(get_db),
):
    """
    Return agents belonging to a specific cohort segment with pagination.

    Includes segment metadata (display name, description, recommended
    strategy), total count, average reactivation score, and a paginated
    list of agents with basic profile information.
    """
    # Validate segment value
    try:
        seg_enum = CohortSegment(segment)
    except ValueError:
        valid = [s.value for s in CohortSegment]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid segment '{segment}'. Valid segments: {valid}",
        )

    # Segment metadata
    info = SEGMENT_INFO.get(seg_enum, {})
    segment_meta = {
        "segment": segment,
        "display_name": info.get("display", segment),
        "description": info.get("description", ""),
        "recommended_strategy": info.get("strategy", EngagementStrategy.WHATSAPP_FIRST).value
        if info.get("strategy") else "whatsapp_first",
    }

    # Count
    total_count = (
        db.query(func.count(Agent.id))
        .filter(Agent.cohort_segment == segment)
        .scalar()
    ) or 0

    # Average reactivation score
    avg_score = (
        db.query(func.avg(Agent.reactivation_score))
        .filter(Agent.cohort_segment == segment)
        .scalar()
    ) or 0.0

    # Paginated agent list
    agents = (
        db.query(Agent)
        .filter(Agent.cohort_segment == segment)
        .order_by(Agent.reactivation_score.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    agent_list = [
        {
            "id": a.id,
            "name": a.name,
            "phone": a.phone,
            "location": a.location,
            "lifecycle_state": a.lifecycle_state,
            "reactivation_score": a.reactivation_score,
            "engagement_strategy": a.engagement_strategy,
            "churn_risk_level": a.churn_risk_level,
            "dormancy_duration_days": a.dormancy_duration_days,
            "total_policies_sold": a.total_policies_sold,
            "response_rate": a.response_rate,
            "assigned_adm_id": a.assigned_adm_id,
        }
        for a in agents
    ]

    return {
        "segment": segment_meta,
        "total_count": total_count,
        "avg_reactivation_score": round(float(avg_score), 1),
        "agents": agent_list,
    }


# ---------------------------------------------------------------------------
# 3. GET /cohort/agent/{agent_id}/analysis
# ---------------------------------------------------------------------------

@router.get("/agent/{agent_id}/analysis")
def get_agent_cohort_analysis(
    agent_id: int,
    reclassify: bool = Query(False, description="Re-run classifier to get fresh results"),
    db: Session = Depends(get_db),
):
    """
    Return individual agent cohort classification detail.

    Includes full agent profile, current cohort classification, score
    breakdown, and the recommended first-message template.  If
    ``reclassify=true`` the classifier is re-run live (results are NOT
    persisted — use the /reclassify endpoint to persist).
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # Either use stored classification or re-run classifier
    # Always run classifier to get score_breakdown + reasoning (computed live)
    reasoning = None
    try:
        result = cohort_classifier.classify_agent(agent)
        reasoning = result.reasoning
    except Exception:
        result = None

    if reclassify and result:
        classification = {
            "cohort_segment": result.cohort_segment,
            "reactivation_score": result.reactivation_score,
            "engagement_strategy": result.engagement_strategy,
            "churn_risk_level": result.churn_risk_level,
            "score_breakdown": result.score_breakdown,
            "first_message": result.first_message,
            "reasoning": reasoning,
            "source": "live_classification",
        }
    else:
        classification = {
            "cohort_segment": agent.cohort_segment,
            "reactivation_score": agent.reactivation_score,
            "engagement_strategy": agent.engagement_strategy,
            "churn_risk_level": agent.churn_risk_level,
            "score_breakdown": result.score_breakdown if result else {},
            "first_message": result.first_message if result else "",
            "reasoning": reasoning,
            "source": "stored",
        }

    # Segment display info
    seg_info = {}
    seg_display_name = ""
    seg_description = ""
    if classification["cohort_segment"]:
        seg_info = CohortClassifier.get_segment_info(classification["cohort_segment"])
        seg_display_name = seg_info.get("display", classification["cohort_segment"])
        seg_description = seg_info.get("description", "")

    # Agent profile (nested under "agent" key for frontend compatibility)
    agent_profile = {
        "id": agent.id,
        "name": agent.name,
        "phone": agent.phone,
        "location": agent.location,
        "state": agent.state,
        "language": agent.language,
        "lifecycle_state": agent.lifecycle_state,
        "dormancy_reason": agent.dormancy_reason,
        "dormancy_duration_days": agent.dormancy_duration_days,
        "total_policies_sold": agent.total_policies_sold,
        "policies_last_12_months": agent.policies_last_12_months,
        "avg_ticket_size": agent.avg_ticket_size,
        "premium_last_12_months": agent.premium_last_12_months,
        "persistency_ratio": agent.persistency_ratio,
        "response_rate": agent.response_rate,
        "contact_attempts": agent.contact_attempts,
        "contact_responses": agent.contact_responses,
        "years_in_insurance": agent.years_in_insurance,
        "work_type": agent.work_type,
        "education_level": agent.education_level,
        "age": agent.age,
        "digital_savviness_score": agent.digital_savviness_score,
        "has_app_installed": agent.has_app_installed,
        "days_since_last_activity": agent.days_since_last_activity,
        "last_contact_date": agent.last_contact_date.isoformat() if agent.last_contact_date else None,
        "last_policy_sold_date": agent.last_policy_sold_date.isoformat() if agent.last_policy_sold_date else None,
        "assigned_adm_id": agent.assigned_adm_id,
    }

    # Return flat structure matching frontend expectations
    return {
        "agent_id": agent.id,
        "agent": agent_profile,
        # Classification fields at root level
        "segment": classification["cohort_segment"],
        "segment_display_name": seg_display_name,
        "segment_description": seg_description,
        "reactivation_score": classification["reactivation_score"],
        "engagement_strategy": classification["engagement_strategy"],
        "churn_risk": classification["churn_risk_level"],
        "score_breakdown": classification["score_breakdown"],
        "first_message": classification["first_message"],
        "reasoning": classification.get("reasoning"),
        # Also keep nested versions for backward compat
        "profile": agent_profile,
        "classification": classification,
        "segment_info": seg_info,
    }


# ---------------------------------------------------------------------------
# 4. POST /cohort/reclassify
# ---------------------------------------------------------------------------

@router.post("/reclassify")
def reclassify_agents(
    body: ReclassifyRequest,
    db: Session = Depends(get_db),
):
    """
    Trigger cohort re-classification and persist results to the database.

    If ``agent_ids`` is provided, only those agents are reclassified.
    If omitted or ``null``, all agents are reclassified.  Returns a summary
    of the operation including per-segment counts after reclassification.
    """
    if body.agent_ids:
        agents = db.query(Agent).filter(Agent.id.in_(body.agent_ids)).all()
        if not agents:
            raise HTTPException(status_code=404, detail="No agents found for the provided IDs")
    else:
        agents = db.query(Agent).all()

    if not agents:
        return {
            "total_processed": 0,
            "success": 0,
            "failed": 0,
            "errors": [],
            "segment_distribution": {},
        }

    success = 0
    failed = 0
    errors: list[dict] = []
    segment_counts: dict[str, int] = {}

    for agent in agents:
        try:
            result = cohort_classifier.classify_agent(agent)
            cohort_classifier.apply_classification(agent, result)

            seg = result.cohort_segment
            segment_counts[seg] = segment_counts.get(seg, 0) + 1
            success += 1
        except Exception as e:
            failed += 1
            errors.append({"agent_id": agent.id, "error": str(e)})
            logger.error(f"Reclassification failed for agent {agent.id}: {e}")

    # Commit all changes in one transaction
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database commit failed after reclassification: {str(e)}",
        )

    return {
        "total_processed": len(agents),
        "classified": success,
        "success": success,
        "failed": failed,
        "errors": errors[:20],  # Cap error details to avoid huge payloads
        "segment_distribution": segment_counts,
    }


# ---------------------------------------------------------------------------
# 5. GET /cohort/engagement-plan
# ---------------------------------------------------------------------------

@router.get("/engagement-plan")
def get_engagement_plan(db: Session = Depends(get_db)):
    """
    Agent-level engagement plan grouped by strategy.

    Returns an array of strategy groups, each containing the list of
    agents assigned to that strategy with their segment, score, and
    personalised first message.  Excludes no_contact agents.
    """
    # Fetch all classified agents (exclude no_contact)
    agents = (
        db.query(Agent)
        .filter(
            Agent.cohort_segment.isnot(None),
            Agent.engagement_strategy != "no_contact",
        )
        .order_by(Agent.reactivation_score.desc())
        .all()
    )

    # Group by strategy
    strategy_groups: dict[str, list] = {}
    for agent in agents:
        strat = agent.engagement_strategy or "whatsapp_first"
        if strat not in strategy_groups:
            strategy_groups[strat] = []

        # Build personalised first message
        first_msg = ""
        try:
            seg_enum = CohortSegment(agent.cohort_segment)
            template = FIRST_MESSAGE_TEMPLATES.get(seg_enum, "")
            if template:
                first_msg = template.format(name=agent.name)
        except (ValueError, KeyError):
            pass

        strategy_groups[strat].append({
            "id": agent.id,
            "name": agent.name,
            "phone": agent.phone,
            "location": agent.location or "",
            "segment": agent.cohort_segment,
            "score": agent.reactivation_score or 0.0,
            "first_message": first_msg,
        })

    # Convert to ordered list (direct_call first, then whatsapp, then telegram)
    strategy_order = ["direct_call", "whatsapp_first", "telegram_only"]
    result = []
    for strat in strategy_order:
        if strat in strategy_groups:
            result.append({
                "strategy": strat,
                "agents": strategy_groups[strat],
            })
    # Add any remaining strategies not in the predefined order
    for strat, agents_list in strategy_groups.items():
        if strat not in strategy_order:
            result.append({
                "strategy": strat,
                "agents": agents_list,
            })

    return result


# ---------------------------------------------------------------------------
# 6. GET /cohort/trends
# ---------------------------------------------------------------------------

@router.get("/trends")
def get_cohort_trends(db: Session = Depends(get_db)):
    """
    Cohort segment trends (placeholder).

    Since historical segment migration data is not yet tracked, this
    endpoint returns the current-state snapshot: segment distribution,
    risk-level distribution, strategy distribution, and score statistics.
    These can serve as the baseline (t=0) once periodic snapshots are
    implemented.
    """
    # Current segment counts
    segment_rows = (
        db.query(
            Agent.cohort_segment,
            func.count(Agent.id).label("count"),
            func.avg(Agent.reactivation_score).label("avg_score"),
        )
        .filter(Agent.cohort_segment.isnot(None))
        .group_by(Agent.cohort_segment)
        .all()
    )

    segments: list[dict] = []
    for seg_value, count, avg_score in segment_rows:
        try:
            seg_enum = CohortSegment(seg_value)
            display = SEGMENT_INFO.get(seg_enum, {}).get("display", seg_value)
        except ValueError:
            display = seg_value
        segments.append({
            "segment": seg_value,
            "display_name": display,
            "count": count,
            "avg_reactivation_score": round(float(avg_score or 0), 1),
        })
    segments.sort(key=lambda x: x["count"], reverse=True)

    # Risk distribution
    risk_rows = (
        db.query(Agent.churn_risk_level, func.count(Agent.id))
        .filter(Agent.churn_risk_level.isnot(None))
        .group_by(Agent.churn_risk_level)
        .all()
    )
    risk_distribution = {level: count for level, count in risk_rows}

    # Strategy distribution
    strategy_rows = (
        db.query(Agent.engagement_strategy, func.count(Agent.id))
        .filter(Agent.engagement_strategy.isnot(None))
        .group_by(Agent.engagement_strategy)
        .all()
    )
    strategy_distribution = {strat: count for strat, count in strategy_rows}

    # Global score statistics
    score_stats_row = db.query(
        func.count(Agent.id),
        func.avg(Agent.reactivation_score),
        func.min(Agent.reactivation_score),
        func.max(Agent.reactivation_score),
    ).filter(Agent.cohort_segment.isnot(None)).first()

    total_classified = score_stats_row[0] or 0
    score_stats = {
        "total_classified": total_classified,
        "avg_score": round(float(score_stats_row[1] or 0), 1),
        "min_score": round(float(score_stats_row[2] or 0), 1),
        "max_score": round(float(score_stats_row[3] or 0), 1),
    }

    # Unclassified count
    unclassified_count = (
        db.query(func.count(Agent.id))
        .filter(Agent.cohort_segment.is_(None))
        .scalar()
    ) or 0

    return {
        "snapshot_type": "current_state",
        "note": "Historical trend tracking not yet implemented. This is the current baseline.",
        "total_agents": total_classified + unclassified_count,
        "total_classified": total_classified,
        "unclassified": unclassified_count,
        "segments": segments,
        "risk_distribution": risk_distribution,
        "strategy_distribution": strategy_distribution,
        "score_statistics": score_stats,
    }
