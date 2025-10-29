from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Contact, Event, Plan
from ..schemas import ContactIn, PlanCreate


async def create_plan(session: AsyncSession, data: PlanCreate, user_id: int) -> Plan:
    # Determine initial status based on start time
    from datetime import datetime, timezone

    # Ensure we're comparing timezone-aware datetimes
    now = datetime.now(timezone.utc)
    start_time = data.start_at

    # If start_time is naive, make it timezone-aware (assume UTC)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    initial_status = "upcoming" if start_time > now else "active"

    plan = Plan(
        user_id=user_id,
        title=data.title,
        activity_type=data.activity_type,
        start_at=data.start_at,
        eta_at=data.eta_at,
        grace_minutes=data.grace_minutes,
        location_text=data.location_text,
        location_lat=data.location_lat,
        location_lng=data.location_lng,
        notes=data.notes,
        status=initial_status,
    )
    session.add(plan)
    await session.flush()  # get plan.id

    if data.contacts:
        contacts = [
            Contact(
                plan_id=plan.id,
                name=c.name,
                phone=c.phone,
                email=c.email,
                notify_on_overdue=c.notify_on_overdue,
            )
            for c in data.contacts
        ]
        session.add_all(contacts)

    session.add(Event(plan_id=plan.id, kind="created"))
    await session.commit()
    await session.refresh(plan)
    return plan


async def list_events(session: AsyncSession, plan_id: int) -> list[Event]:
    res = await session.execute(
        select(Event).where(Event.plan_id == plan_id).order_by(Event.at.asc())
    )
    return list(res.scalars().all())
