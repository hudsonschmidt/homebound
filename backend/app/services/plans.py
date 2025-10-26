from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Contact, Event, Plan
from ..schemas import ContactIn, PlanCreate


async def create_plan(session: AsyncSession, data: PlanCreate, user_id: int) -> Plan:
    plan = Plan(
        user_id=user_id,
        title=data.title,
        start_at=data.start_at,
        eta_at=data.eta_at,
        grace_minutes=data.grace_minutes,
        location_text=data.location_text,
        notes=data.notes,
        status="active",
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
