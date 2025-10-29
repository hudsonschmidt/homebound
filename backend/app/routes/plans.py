"""
Enhanced plan management endpoints
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.db import get_session
from ..models import Plan, Event, Contact, User
from ..schemas import PlanOut, PlanCreate
from ..services.auth import get_current_user_id
from ..services.plans import create_plan
from ..services.tokens import sign_token

router = APIRouter(prefix="/api/v1", tags=["plans"])


@router.post("/plans", response_model=PlanOut)
async def create_plan_route(
    request: Request,
    payload: PlanCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new plan."""
    user_id = get_current_user_id(request)
    if payload.eta_at <= payload.start_at:
        raise HTTPException(status_code=400, detail="eta_at must be after start_at")

    plan = await create_plan(session, payload, user_id)

    exp = payload.eta_at + timedelta(days=1, minutes=payload.grace_minutes)
    checkin = sign_token(plan.id, "checkin", exp)
    checkout = sign_token(plan.id, "checkout", exp)

    return PlanOut(
        id=plan.id,
        title=plan.title,
        activity_type=plan.activity_type,
        start_at=plan.start_at,
        eta_at=plan.eta_at,
        grace_minutes=plan.grace_minutes,
        location_text=plan.location_text,
        notes=plan.notes,
        status=plan.status,
        checkin_token=checkin,
        checkout_token=checkout,
    )


@router.get("/plans/active", response_model=Optional[PlanOut])
async def get_active_plan(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Get the current active plan for the user."""
    user_id = get_current_user_id(request)

    # First check for any upcoming plans that should now be active
    from datetime import timezone
    now = datetime.now(timezone.utc)
    upcoming_result = await session.execute(
        select(Plan)
        .where(
            Plan.user_id == user_id,
            Plan.status == "upcoming",
            Plan.start_at <= now
        )
    )
    upcoming_plans = upcoming_result.scalars().all()

    # Update upcoming plans to active if their start time has passed
    for plan in upcoming_plans:
        plan.status = "active"
        session.add(Event(plan_id=plan.id, kind="started"))

    if upcoming_plans:
        await session.commit()

    result = await session.execute(
        select(Plan)
        .where(
            Plan.user_id == user_id,
            Plan.status.in_(["active", "overdue", "overdue_notified"])
        )
        .order_by(Plan.created_at.desc())
        .limit(1)
    )
    plan = result.scalar_one_or_none()

    if not plan:
        return None

    # Generate tokens
    exp = plan.eta_at + timedelta(days=1, minutes=plan.grace_minutes)
    checkin = sign_token(plan.id, "checkin", exp)
    checkout = sign_token(plan.id, "checkout", exp)

    return PlanOut(
        id=plan.id,
        title=plan.title,
        activity_type=plan.activity_type,
        start_at=plan.start_at,
        eta_at=plan.eta_at,
        grace_minutes=plan.grace_minutes,
        location_text=plan.location_text,
        notes=plan.notes,
        status=plan.status,
        checkin_token=checkin,
        checkout_token=checkout,
    )


@router.get("/plans", response_model=List[PlanOut])
async def get_all_plans(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Get all plans for the user."""
    user_id = get_current_user_id(request)

    result = await session.execute(
        select(Plan)
        .where(Plan.user_id == user_id)
        .order_by(Plan.created_at.desc())
    )
    plans = result.scalars().all()

    plan_outs = []
    for plan in plans:
        exp = plan.eta_at + timedelta(days=1, minutes=plan.grace_minutes)
        checkin = sign_token(plan.id, "checkin", exp)
        checkout = sign_token(plan.id, "checkout", exp)

        plan_outs.append(PlanOut(
            id=plan.id,
            title=plan.title,
            activity_type=plan.activity_type,
            start_at=plan.start_at,
            eta_at=plan.eta_at,
            grace_minutes=plan.grace_minutes,
            location_text=plan.location_text,
            notes=plan.notes,
            status=plan.status,
            checkin_token=checkin,
            checkout_token=checkout,
        ))

    return plan_outs


@router.get("/plans/recent", response_model=List[PlanOut])
async def get_recent_plans(
    request: Request,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    """Get recent plans for the user."""
    user_id = get_current_user_id(request)

    result = await session.execute(
        select(Plan)
        .where(Plan.user_id == user_id)
        .order_by(Plan.created_at.desc())
        .limit(limit)
    )
    plans = result.scalars().all()

    plan_outs = []
    for plan in plans:
        exp = plan.eta_at + timedelta(days=1, minutes=plan.grace_minutes)
        checkin = sign_token(plan.id, "checkin", exp)
        checkout = sign_token(plan.id, "checkout", exp)

        plan_outs.append(PlanOut(
            id=plan.id,
            title=plan.title,
            activity_type=plan.activity_type,
            start_at=plan.start_at,
            eta_at=plan.eta_at,
            grace_minutes=plan.grace_minutes,
            location_text=plan.location_text,
            notes=plan.notes,
            status=plan.status,
            checkin_token=checkin,
            checkout_token=checkout,
        ))

    return plan_outs


@router.get("/plans/stats")
async def get_plan_stats(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Get statistics about user's plans."""
    user_id = get_current_user_id(request)

    # Total trips
    total_result = await session.execute(
        select(func.count(Plan.id))
        .where(Plan.user_id == user_id)
    )
    total_trips = total_result.scalar() or 0

    # Completed trips (safe returns)
    completed_result = await session.execute(
        select(func.count(Plan.id))
        .where(
            Plan.user_id == user_id,
            Plan.status == "completed"
        )
    )
    completed_trips = completed_result.scalar() or 0

    # This week's trips
    week_ago = datetime.utcnow() - timedelta(days=7)
    week_result = await session.execute(
        select(func.count(Plan.id))
        .where(
            Plan.user_id == user_id,
            Plan.created_at >= week_ago
        )
    )
    week_trips = week_result.scalar() or 0

    # Most common activity
    activity_result = await session.execute(
        select(Plan.activity_type, func.count(Plan.id).label("count"))
        .where(Plan.user_id == user_id)
        .group_by(Plan.activity_type)
        .order_by(func.count(Plan.id).desc())
        .limit(1)
    )
    favorite_activity = activity_result.first()

    return {
        "total_trips": total_trips,
        "completed_trips": completed_trips,
        "safe_return_rate": f"{int((completed_trips / total_trips * 100) if total_trips > 0 else 100)}%",
        "week_trips": week_trips,
        "favorite_activity": favorite_activity[0] if favorite_activity else "other",
        "favorite_activity_count": favorite_activity[1] if favorite_activity else 0,
    }


from pydantic import BaseModel

class ExtendRequest(BaseModel):
    minutes: int = 30

@router.post("/plans/{plan_id}/extend")
async def extend_plan(
    plan_id: int,
    request: Request,
    extend_request: ExtendRequest = ExtendRequest(),
    session: AsyncSession = Depends(get_session),
):
    """Extend a plan's ETA."""
    user_id = get_current_user_id(request)
    minutes = extend_request.minutes

    plan = await session.get(Plan, plan_id)
    if not plan or plan.user_id != user_id:
        raise HTTPException(status_code=404, detail="Plan not found")

    if plan.status not in ["active", "overdue", "overdue_notified"]:
        raise HTTPException(status_code=400, detail="Can only extend active plans")

    # Update ETA
    plan.eta_at = plan.eta_at + timedelta(minutes=minutes)
    plan.extended_count += 1

    # Reset status to active if it was overdue
    if plan.status in ["overdue", "overdue_notified"]:
        plan.status = "active"

    # Add event
    event = Event(
        plan_id=plan.id,
        kind="extended",
        meta=f"Extended by {minutes} minutes"
    )
    session.add(event)

    await session.commit()
    await session.refresh(plan)

    return {
        "ok": True,
        "new_eta": plan.eta_at.isoformat(),
        "extended_count": plan.extended_count
    }


class EmptyRequest(BaseModel):
    pass

@router.post("/plans/{plan_id}/checkin")
async def checkin_plan(
    plan_id: int,
    request: Request,
    _: EmptyRequest = EmptyRequest(),
    session: AsyncSession = Depends(get_session),
):
    """Check in to a plan."""
    user_id = get_current_user_id(request)

    plan = await session.get(Plan, plan_id)
    if not plan or plan.user_id != user_id:
        raise HTTPException(status_code=404, detail="Plan not found")

    if plan.status not in ["active", "overdue", "overdue_notified"]:
        raise HTTPException(status_code=400, detail="Plan is not active")

    # Update last checkin time
    plan.last_checkin_at = datetime.utcnow()

    # Add event
    event = Event(
        plan_id=plan.id,
        kind="checkin"
    )
    session.add(event)

    await session.commit()

    return {"ok": True, "message": "Checked in successfully"}


@router.post("/plans/{plan_id}/complete")
async def complete_plan(
    plan_id: int,
    request: Request,
    _: EmptyRequest = EmptyRequest(),
    session: AsyncSession = Depends(get_session),
):
    """Mark a plan as completed (safe return)."""
    user_id = get_current_user_id(request)

    plan = await session.get(Plan, plan_id)
    if not plan or plan.user_id != user_id:
        raise HTTPException(status_code=404, detail="Plan not found")

    if plan.status == "completed":
        return {"ok": True, "message": "Plan already completed"}

    # Update plan status
    plan.status = "completed"
    plan.completed_at = datetime.utcnow()

    # Add event
    event = Event(
        plan_id=plan.id,
        kind="checkout"
    )
    session.add(event)

    await session.commit()

    return {"ok": True, "message": "Welcome back! Trip completed safely"}


@router.post("/plans/{plan_id}/cancel")
async def cancel_plan(
    plan_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Cancel an active plan."""
    user_id = get_current_user_id(request)

    plan = await session.get(Plan, plan_id)
    if not plan or plan.user_id != user_id:
        raise HTTPException(status_code=404, detail="Plan not found")

    if plan.status != "active":
        raise HTTPException(status_code=400, detail="Can only cancel active plans")

    # Update plan status
    plan.status = "cancelled"

    # Add event
    event = Event(
        plan_id=plan.id,
        kind="cancelled"
    )
    session.add(event)

    await session.commit()

    return {"ok": True, "message": "Plan cancelled"}


@router.get("/plans/by-activity/{activity_type}")
async def get_plans_by_activity(
    activity_type: str,
    request: Request,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    """Get plans filtered by activity type."""
    user_id = get_current_user_id(request)

    result = await session.execute(
        select(Plan)
        .where(
            Plan.user_id == user_id,
            Plan.activity_type == activity_type
        )
        .order_by(Plan.created_at.desc())
        .limit(limit)
    )
    plans = result.scalars().all()

    return {
        "activity_type": activity_type,
        "count": len(plans),
        "plans": [
            {
                "id": p.id,
                "title": p.title,
                "start_at": p.start_at.isoformat(),
                "eta_at": p.eta_at.isoformat(),
                "status": p.status,
                "location": p.location_text
            }
            for p in plans
        ]
    }


@router.delete("/plans/{plan_id}")
async def delete_plan(
    plan_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Delete a plan and all associated data."""
    user_id = get_current_user_id(request)

    # Get the plan first to verify ownership
    plan = await session.get(Plan, plan_id)
    if not plan or plan.user_id != user_id:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Delete the plan (cascading will handle related data)
    await session.delete(plan)
    await session.commit()

    return {"ok": True, "message": "Plan deleted successfully"}