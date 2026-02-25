"""
Diary / Schedule management routes for ADMs.
"""

from datetime import datetime, date as date_type
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import DiaryEntry, Agent, ADM
from schemas import DiaryEntryCreate, DiaryEntryUpdate, DiaryEntryResponse

router = APIRouter(prefix="/diary", tags=["Diary"])


@router.get("/", response_model=List[DiaryEntryResponse])
def list_diary_entries(
    adm_id: Optional[int] = Query(None),
    agent_id: Optional[int] = Query(None),
    scheduled_date: Optional[date_type] = Query(None),
    status: Optional[str] = Query(None),
    entry_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List diary entries with optional filters."""
    query = db.query(DiaryEntry)

    if adm_id:
        query = query.filter(DiaryEntry.adm_id == adm_id)
    if agent_id:
        query = query.filter(DiaryEntry.agent_id == agent_id)
    if scheduled_date:
        query = query.filter(DiaryEntry.scheduled_date == scheduled_date)
    if status:
        query = query.filter(DiaryEntry.status == status)
    if entry_type:
        query = query.filter(DiaryEntry.entry_type == entry_type)

    return (
        query.order_by(DiaryEntry.scheduled_date, DiaryEntry.scheduled_time)
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/today/{adm_id}")
def get_today_schedule(
    adm_id: int,
    date: Optional[date_type] = Query(None, description="Specific date to fetch (defaults to today)"),
    db: Session = Depends(get_db),
):
    """Get schedule for an ADM on a specific date (defaults to today)."""
    adm = db.query(ADM).filter(ADM.id == adm_id).first()
    if not adm:
        raise HTTPException(status_code=404, detail="ADM not found")

    target_date = date or date_type.today()
    entries = db.query(DiaryEntry).filter(
        DiaryEntry.adm_id == adm_id,
        DiaryEntry.scheduled_date == target_date,
    ).order_by(DiaryEntry.scheduled_time).all()

    schedule = []
    for entry in entries:
        agent_name = None
        agent_phone = None
        if entry.agent_id:
            agent = db.query(Agent).filter(Agent.id == entry.agent_id).first()
            if agent:
                agent_name = agent.name
                agent_phone = agent.phone

        schedule.append({
            "id": entry.id,
            "time": entry.scheduled_time or "",
            "type": entry.entry_type,
            "status": entry.status,
            "agent_id": entry.agent_id,
            "agent_name": agent_name,
            "agent_phone": agent_phone,
            "notes": entry.notes,
        })

    return {
        "adm_id": adm_id,
        "adm_name": adm.name,
        "date": target_date.isoformat(),
        "total_entries": len(schedule),
        "completed": sum(1 for s in schedule if s["status"] == "completed"),
        "pending": sum(1 for s in schedule if s["status"] == "scheduled"),
        "schedule": schedule,
    }


@router.get("/upcoming/{adm_id}")
def get_upcoming_entries(
    adm_id: int,
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """Get upcoming diary entries for an ADM for the next N days."""
    from datetime import timedelta
    today = date_type.today()
    end_date = today + timedelta(days=days)

    entries = db.query(DiaryEntry).filter(
        DiaryEntry.adm_id == adm_id,
        DiaryEntry.scheduled_date >= today,
        DiaryEntry.scheduled_date <= end_date,
    ).order_by(DiaryEntry.scheduled_date, DiaryEntry.scheduled_time).all()

    results = []
    for entry in entries:
        agent_name = None
        if entry.agent_id:
            agent = db.query(Agent).filter(Agent.id == entry.agent_id).first()
            agent_name = agent.name if agent else None

        results.append({
            "id": entry.id,
            "date": entry.scheduled_date.isoformat(),
            "time": entry.scheduled_time or "",
            "type": entry.entry_type,
            "status": entry.status,
            "agent_id": entry.agent_id,
            "agent_name": agent_name,
            "notes": entry.notes,
        })

    return {"adm_id": adm_id, "days_ahead": days, "entries": results}


@router.get("/{entry_id}", response_model=DiaryEntryResponse)
def get_diary_entry(entry_id: int, db: Session = Depends(get_db)):
    """Get a single diary entry."""
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Diary entry not found")
    return entry


@router.post("/", response_model=DiaryEntryResponse, status_code=201)
def create_diary_entry(data: DiaryEntryCreate, db: Session = Depends(get_db)):
    """Create a new diary entry."""
    # Validate ADM
    adm = db.query(ADM).filter(ADM.id == data.adm_id).first()
    if not adm:
        raise HTTPException(status_code=404, detail="ADM not found")

    # Validate agent if provided
    if data.agent_id:
        agent = db.query(Agent).filter(Agent.id == data.agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

    valid_types = ["follow_up", "first_contact", "training", "escalation", "review"]
    if data.entry_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid entry type. Must be one of: {valid_types}")

    entry = DiaryEntry(**data.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=DiaryEntryResponse)
def update_diary_entry(
    entry_id: int,
    data: DiaryEntryUpdate,
    db: Session = Depends(get_db),
):
    """Update a diary entry."""
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Diary entry not found")

    update_dict = data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(entry, key, value)

    db.commit()
    db.refresh(entry)
    return entry


@router.post("/{entry_id}/complete")
def mark_diary_complete(
    entry_id: int,
    completion_notes: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Mark a diary entry as completed."""
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Diary entry not found")

    entry.status = "completed"
    if completion_notes:
        entry.completion_notes = completion_notes

    db.commit()
    db.refresh(entry)
    return {"detail": "Diary entry marked as completed", "id": entry_id}


@router.post("/{entry_id}/reschedule")
def reschedule_diary_entry(
    entry_id: int,
    new_date: date_type = Query(...),
    new_time: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Reschedule a diary entry."""
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Diary entry not found")

    old_date = entry.scheduled_date
    entry.scheduled_date = new_date
    if new_time:
        entry.scheduled_time = new_time
    # Keep status as "scheduled" so entry appears in diary queries for the new date
    entry.status = "scheduled"

    db.commit()
    db.refresh(entry)

    return {
        "detail": "Diary entry rescheduled",
        "id": entry_id,
        "old_date": old_date.isoformat(),
        "new_date": new_date.isoformat(),
    }


@router.delete("/{entry_id}")
def delete_diary_entry(entry_id: int, db: Session = Depends(get_db)):
    """Delete a diary entry."""
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Diary entry not found")

    db.delete(entry)
    db.commit()
    return {"detail": "Diary entry deleted", "id": entry_id}
