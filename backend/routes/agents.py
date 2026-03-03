"""
Agent CRUD routes.
"""

import io
import csv
import logging
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import Agent, ADM
from schemas import AgentCreate, AgentUpdate, AgentResponse, AgentBulkImport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("/", response_model=List[AgentResponse])
def list_agents(
    lifecycle_state: Optional[str] = Query(None, description="Filter by lifecycle state"),
    location: Optional[str] = Query(None, description="Filter by location (city)"),
    assigned_adm_id: Optional[int] = Query(None, description="Filter by assigned ADM"),
    unassigned: Optional[bool] = Query(None, description="Show only unassigned agents"),
    search: Optional[str] = Query(None, description="Search by name or phone"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List agents with optional filters."""
    query = db.query(Agent)

    if lifecycle_state:
        query = query.filter(Agent.lifecycle_state == lifecycle_state)
    if location:
        query = query.filter(Agent.location.ilike(f"%{location}%"))
    if assigned_adm_id:
        query = query.filter(Agent.assigned_adm_id == assigned_adm_id)
    if unassigned:
        query = query.filter(Agent.assigned_adm_id.is_(None))
    if search:
        query = query.filter(
            (Agent.name.ilike(f"%{search}%")) | (Agent.phone.ilike(f"%{search}%"))
        )

    total = query.count()
    agents = query.order_by(Agent.dormancy_duration_days.desc()).offset(skip).limit(limit).all()

    return agents


@router.get("/count")
def count_agents(
    lifecycle_state: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get count of agents, optionally by state."""
    query = db.query(func.count(Agent.id))
    if lifecycle_state:
        query = query.filter(Agent.lifecycle_state == lifecycle_state)
    return {"count": query.scalar()}


@router.get("/states-summary")
def states_summary(db: Session = Depends(get_db)):
    """Get count of agents by lifecycle state."""
    results = db.query(
        Agent.lifecycle_state,
        func.count(Agent.id),
    ).group_by(Agent.lifecycle_state).all()

    return {state: count for state, count in results}


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    """Get a single agent by ID."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/", response_model=AgentResponse, status_code=201)
def create_agent(agent_data: AgentCreate, db: Session = Depends(get_db)):
    """Create a new agent."""
    # Check for duplicate phone
    existing = db.query(Agent).filter(Agent.phone == agent_data.phone).first()
    if existing:
        raise HTTPException(status_code=400, detail="Agent with this phone number already exists")

    # Validate ADM if specified
    if agent_data.assigned_adm_id:
        adm = db.query(ADM).filter(ADM.id == agent_data.assigned_adm_id).first()
        if not adm:
            raise HTTPException(status_code=400, detail="Assigned ADM not found")

    agent = Agent(**agent_data.model_dump())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
def update_agent(agent_id: int, agent_data: AgentUpdate, db: Session = Depends(get_db)):
    """Update an agent."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_dict = agent_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(agent, key, value)

    agent.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}")
def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    """Delete an agent."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    db.delete(agent)
    db.commit()
    return {"detail": "Agent deleted", "id": agent_id}


@router.post("/{agent_id}/assign/{adm_id}", response_model=AgentResponse)
def assign_agent_to_adm(agent_id: int, adm_id: int, db: Session = Depends(get_db)):
    """Assign an agent to an ADM."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    adm = db.query(ADM).filter(ADM.id == adm_id).first()
    if not adm:
        raise HTTPException(status_code=404, detail="ADM not found")

    # Check capacity
    current_count = db.query(func.count(Agent.id)).filter(
        Agent.assigned_adm_id == adm_id
    ).scalar() or 0
    if current_count >= adm.max_capacity:
        raise HTTPException(status_code=400, detail=f"ADM {adm.name} is at full capacity ({adm.max_capacity})")

    agent.assigned_adm_id = adm_id
    agent.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(agent)
    return agent


@router.post("/{agent_id}/unassign", response_model=AgentResponse)
def unassign_agent(agent_id: int, db: Session = Depends(get_db)):
    """Remove ADM assignment from an agent."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.assigned_adm_id = None
    agent.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(agent)
    return agent


@router.post("/{agent_id}/transition")
def transition_state(
    agent_id: int,
    new_state: str = Query(..., description="New lifecycle state"),
    db: Session = Depends(get_db),
):
    """Transition agent to a new lifecycle state."""
    valid_states = ["dormant", "at_risk", "contacted", "engaged", "trained", "active"]
    if new_state not in valid_states:
        raise HTTPException(status_code=400, detail=f"Invalid state. Must be one of: {valid_states}")

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    old_state = agent.lifecycle_state
    agent.lifecycle_state = new_state
    agent.updated_at = datetime.utcnow()

    if new_state == "contacted":
        agent.last_contact_date = datetime.utcnow().date()

    db.commit()
    db.refresh(agent)

    return {
        "agent_id": agent_id,
        "old_state": old_state,
        "new_state": new_state,
        "name": agent.name,
    }


@router.post("/bulk-import")
def bulk_import_agents(data: AgentBulkImport, db: Session = Depends(get_db)):
    """Bulk import agents."""
    created = []
    errors = []

    for i, agent_data in enumerate(data.agents):
        try:
            existing = db.query(Agent).filter(Agent.phone == agent_data.phone).first()
            if existing:
                errors.append({"index": i, "phone": agent_data.phone, "error": "Duplicate phone"})
                continue

            agent = Agent(**agent_data.model_dump())
            db.add(agent)
            db.flush()
            created.append({"index": i, "id": agent.id, "name": agent.name})
        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    db.commit()

    return {
        "total_submitted": len(data.agents),
        "created": len(created),
        "errors_count": len(errors),
        "created_agents": created,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Bulk Upload with Cohort Classification
# ---------------------------------------------------------------------------

# CSV column name → Agent model attribute mapping
_CSV_FIELD_MAP = {
    "name": "name",
    "phone": "phone",
    "email": "email",
    "location": "location",
    "state": "state",
    "language": "language",
    "lifecycle_state": "lifecycle_state",
    "dormancy_reason": "dormancy_reason",
    "dormancy_duration_days": "dormancy_duration_days",
    "license_number": "license_number",
    "date_of_joining": "date_of_joining",
    "specialization": "specialization",
    "total_policies_sold": "total_policies_sold",
    "total_premium_generated": "total_premium_generated",
    "policies_last_12_months": "policies_last_12_months",
    "premium_last_12_months": "premium_last_12_months",
    "avg_ticket_size": "avg_ticket_size",
    "best_month_premium": "best_month_premium",
    "persistency_ratio": "persistency_ratio",
    "last_contact_date": "last_contact_date",
    "last_policy_sold_date": "last_policy_sold_date",
    "last_login_date": "last_login_date",
    "last_training_date": "last_training_date",
    "last_proposal_date": "last_proposal_date",
    "days_since_last_activity": "days_since_last_activity",
    "contact_attempts": "contact_attempts",
    "contact_responses": "contact_responses",
    "response_rate": "response_rate",
    "avg_response_time_hours": "avg_response_time_hours",
    "preferred_channel": "preferred_channel",
    "age": "age",
    "education_level": "education_level",
    "years_in_insurance": "years_in_insurance",
    "previous_insurer": "previous_insurer",
    "is_poached": "is_poached",
    "work_type": "work_type",
    "other_occupation": "other_occupation",
    "has_app_installed": "has_app_installed",
    "digital_savviness_score": "digital_savviness_score",
    "engagement_score": "engagement_score",
    "assigned_adm_id": "assigned_adm_id",
}

# Fields that are integers
_INT_FIELDS = {
    "dormancy_duration_days", "total_policies_sold", "policies_last_12_months",
    "days_since_last_activity", "contact_attempts", "contact_responses",
    "age", "assigned_adm_id",
}

# Fields that are floats
_FLOAT_FIELDS = {
    "total_premium_generated", "premium_last_12_months", "avg_ticket_size",
    "best_month_premium", "persistency_ratio", "response_rate",
    "avg_response_time_hours", "digital_savviness_score", "engagement_score",
    "years_in_insurance",
}

# Fields that are dates (YYYY-MM-DD)
_DATE_FIELDS = {
    "date_of_joining", "last_contact_date", "last_policy_sold_date",
    "last_login_date", "last_training_date", "last_proposal_date",
}

# Fields that are booleans
_BOOL_FIELDS = {"is_poached", "has_app_installed"}


def _parse_csv_value(field: str, value: str):
    """Parse a CSV string value into the correct Python type."""
    value = value.strip()
    if not value or value.lower() in ("", "null", "none", "na", "n/a"):
        return None

    if field in _INT_FIELDS:
        return int(float(value))
    elif field in _FLOAT_FIELDS:
        return float(value)
    elif field in _DATE_FIELDS:
        return date.fromisoformat(value)
    elif field in _BOOL_FIELDS:
        return value.lower() in ("true", "1", "yes", "y")
    else:
        return value


@router.post("/bulk-upload-cohort")
async def bulk_upload_with_cohort(
    file: UploadFile = File(..., description="CSV file with agent data"),
    classify: bool = Query(True, description="Run cohort classification after upload"),
    db: Session = Depends(get_db),
):
    """
    Bulk upload agents from CSV with automatic cohort classification.

    CSV must have a header row. At minimum: name, phone, location.
    All other fields from the cohort data model are optional.
    Agents matched by phone number are updated; new phones create new agents.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # Handle BOM
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    created_count = 0
    updated_count = 0
    errors = []
    processed_agents = []

    # Track which CSV fields were explicitly provided per agent
    # so post-processing doesn't overwrite them.
    agent_provided_fields: list[set[str]] = []

    for row_num, row in enumerate(reader, start=2):  # Row 2+ (header is row 1)
        try:
            # Normalize column names
            normalized = {k.strip().lower().replace(" ", "_"): v for k, v in row.items()}

            # Required fields
            name = normalized.get("name", "").strip()
            phone = normalized.get("phone", "").strip()
            location = normalized.get("location", "").strip()

            if not name or not phone or not location:
                errors.append(f"Row {row_num}: Missing required field (name, phone, or location)")
                continue

            # Track which fields this CSV row explicitly provides
            provided_fields: set[str] = set()

            # Check if agent already exists by phone
            existing = db.query(Agent).filter(Agent.phone == phone).first()

            if existing:
                # Update existing agent with new data
                for csv_col, model_attr in _CSV_FIELD_MAP.items():
                    if csv_col in normalized and normalized[csv_col].strip():
                        try:
                            parsed = _parse_csv_value(csv_col, normalized[csv_col])
                            # Set even if parsed is None — this lets "NA" clear a field
                            setattr(existing, model_attr, parsed)
                            if parsed is not None:
                                provided_fields.add(csv_col)
                        except (ValueError, TypeError) as e:
                            errors.append(f"Row {row_num}: Invalid value for {csv_col}: {e}")

                existing.updated_at = datetime.utcnow()
                processed_agents.append(existing)
                agent_provided_fields.append(provided_fields)
                updated_count += 1
            else:
                # Create new agent
                agent = Agent(name=name, phone=phone, location=location)
                for csv_col, model_attr in _CSV_FIELD_MAP.items():
                    if csv_col in ("name", "phone", "location"):
                        continue  # Already set
                    if csv_col in normalized and normalized[csv_col].strip():
                        try:
                            parsed = _parse_csv_value(csv_col, normalized[csv_col])
                            if parsed is not None:
                                setattr(agent, model_attr, parsed)
                                provided_fields.add(csv_col)
                        except (ValueError, TypeError) as e:
                            errors.append(f"Row {row_num}: Invalid value for {csv_col}: {e}")

                db.add(agent)
                db.flush()
                processed_agents.append(agent)
                agent_provided_fields.append(provided_fields)
                created_count += 1

        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    # ------------------------------------------------------------------
    # Post-processing: fill in derived fields before classification
    # Only auto-calculate fields that were NOT explicitly provided in CSV.
    # ------------------------------------------------------------------
    today = date.today()
    for idx, agent in enumerate(processed_agents):
        provided = agent_provided_fields[idx] if idx < len(agent_provided_fields) else set()

        # Default lifecycle_state to "dormant" if not explicitly set
        if not agent.lifecycle_state or agent.lifecycle_state == "unknown":
            agent.lifecycle_state = "dormant"

        # Gather all activity dates for calculations
        activity_dates = [
            d for d in [
                agent.last_contact_date,
                agent.last_policy_sold_date,
                agent.last_login_date,
                agent.last_training_date,
                agent.last_proposal_date,
            ] if d is not None
        ]

        # Auto-calculate days_since_last_activity from dates ONLY if not provided in CSV
        if "days_since_last_activity" not in provided:
            if activity_dates:
                most_recent = max(activity_dates)
                agent.days_since_last_activity = max(0, (today - most_recent).days)
            elif agent.date_of_joining:
                agent.days_since_last_activity = max(0, (today - agent.date_of_joining).days)

        # Auto-calculate dormancy_duration_days from dates if not provided
        if "dormancy_duration_days" not in provided:
            # If days_since_last_activity was explicitly provided, sync dormancy_duration_days
            if "days_since_last_activity" in provided and agent.days_since_last_activity:
                agent.dormancy_duration_days = agent.days_since_last_activity
            elif not agent.dormancy_duration_days or agent.dormancy_duration_days == 0:
                if activity_dates:
                    most_recent = max(activity_dates)
                    agent.dormancy_duration_days = max(0, (today - most_recent).days)
                elif agent.date_of_joining:
                    agent.dormancy_duration_days = max(0, (today - agent.date_of_joining).days)
                elif agent.days_since_last_activity and agent.days_since_last_activity > 0:
                    # Use days_since_last_activity as fallback when no dates available
                    agent.dormancy_duration_days = agent.days_since_last_activity

        # Recalculate response_rate if contact fields were updated OR if rate is missing
        contact_fields_changed = "contact_attempts" in provided or "contact_responses" in provided
        if "response_rate" not in provided:
            if contact_fields_changed or (not agent.response_rate or agent.response_rate == 0.0):
                if agent.contact_attempts and agent.contact_attempts > 0:
                    agent.response_rate = min(1.0, round(
                        (agent.contact_responses or 0) / agent.contact_attempts, 2
                    ))

        # Auto-calculate avg_ticket_size if not provided and we have the inputs
        if "avg_ticket_size" not in provided:
            if (not agent.avg_ticket_size or agent.avg_ticket_size == 0.0) and agent.total_policies_sold and agent.total_policies_sold > 0:
                total_premium = agent.total_premium_generated or 0.0
                if total_premium > 0:
                    agent.avg_ticket_size = round(total_premium / agent.total_policies_sold, 2)

    db.commit()

    # Run cohort classification if requested
    classified_count = 0
    segment_summary = {}

    if classify and processed_agents:
        from services.cohort_classifier import cohort_classifier

        for agent in processed_agents:
            try:
                result = cohort_classifier.classify_agent(agent)
                cohort_classifier.apply_classification(agent, result)
                classified_count += 1
                seg = result.cohort_segment
                segment_summary[seg] = segment_summary.get(seg, 0) + 1
            except Exception as e:
                errors.append(f"Classification failed for agent {agent.id} ({agent.name}): {e}")

        db.commit()

    return {
        "total_uploaded": created_count + updated_count,
        "created": created_count,
        "updated": updated_count,
        "classified": classified_count,
        "errors": errors,
        "segment_summary": segment_summary,
    }


# ---------------------------------------------------------------------------
# Detect dormancy reasons from free text
# ---------------------------------------------------------------------------

@router.post("/detect-dormancy")
def detect_dormancy(body: dict):
    """Parse free text to detect dormancy reasons using keyword matching.

    Uses the existing dormancy taxonomy detection engine which supports
    both Hindi and English text.
    """
    text = body.get("text", "")
    if not text.strip():
        raise HTTPException(status_code=400, detail="'text' field is required and cannot be empty")

    from domain.dormancy_taxonomy import detect_dormancy_reason

    matches = detect_dormancy_reason(text)
    return {
        "text": text[:500],
        "matches": [
            {
                "code": m.get("code"),
                "name": m.get("name"),
                "category": m.get("category"),
                "description": m.get("description"),
                "match_score": m.get("match_score"),
            }
            for m in matches[:10]
        ],
        "total_matches": len(matches),
    }
