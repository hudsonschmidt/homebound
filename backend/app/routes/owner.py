from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_session
from ..models import Plan
from ..schemas import PlanCreate, PlanOut
from ..services.plans import create_plan, list_events
from ..services.tokens import sign_token

router = APIRouter()


@router.post("/plans", response_model=PlanOut)
async def create_plan_route(
    payload: PlanCreate, session: AsyncSession = Depends(get_session)
):
    if payload.eta_at <= payload.start_at:
        raise HTTPException(status_code=400, detail="eta_at must be after start_at")

    plan = await create_plan(session, payload)

    exp = payload.eta_at + timedelta(days=1, minutes=payload.grace_minutes)
    checkin = sign_token(plan.id, "checkin", exp)
    checkout = sign_token(plan.id, "checkout", exp)

    return PlanOut(
        id=plan.id,
        title=plan.title,
        start_at=plan.start_at,
        eta_at=plan.eta_at,
        grace_minutes=plan.grace_minutes,
        location_text=plan.location_text,
        notes=plan.notes,
        status=plan.status,
        checkin_token=checkin,
        checkout_token=checkout,
    )


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: int, session: AsyncSession = Depends(get_session)):
    plan = await session.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    return {"id": plan.id, "title": plan.title, "eta": plan.eta_at.isoformat()}


@router.get("/plans/{plan_id}/timeline")
async def timeline(plan_id: int, session: AsyncSession = Depends(get_session)):
    events = await list_events(session, plan_id)
    return {
        "plan_id": plan_id,
        "events": [{"kind": e.kind, "at": e.at.isoformat(), "meta": e.meta} for e in events],
    }
