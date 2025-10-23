from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.db import get_session
from ..models import Plan
from ..schemas import ContactIn, PlanCreate
from ..services.plans import create_plan, list_events
from ..services.tokens import sign_token

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/plans/new")
async def new_plan_form(request: Request):
    return templates.TemplateResponse(
        "owner_create.html",
        {"request": request, "now": datetime.utcnow().isoformat(timespec="minutes")},
    )


@router.post("/plans")
async def create_plan_action(
    request: Request,
    title: str = Form(...),
    start_at: str = Form(...),
    eta_at: str = Form(...),
    grace_minutes: int = Form(30),
    location_text: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    contact_name: Optional[str] = Form(None),
    contact_phone: Optional[str] = Form(None),
    contact_email: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session),
):
    try:
        start_dt = datetime.fromisoformat(start_at)
        eta_dt = datetime.fromisoformat(eta_at)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format (use ISO 8601)")

    contacts = []
    if contact_name or contact_phone or contact_email:
        contacts.append(
            ContactIn(
                name=contact_name or "Contact",
                phone=contact_phone or None,
                email=contact_email or None,
            )
        )

    payload = PlanCreate(
        title=title,
        start_at=start_dt,
        eta_at=eta_dt,
        grace_minutes=grace_minutes,
        location_text=location_text,
        notes=notes,
        contacts=contacts,
    )

    plan = await create_plan(session, payload)
    return RedirectResponse(url=f"/web/plans/{plan.id}", status_code=303)


@router.get("/plans/{plan_id}")
async def owner_plan_view(plan_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    plan = await session.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")

    # recompute tokens (stateless) with ETA + 1d + grace
    exp = plan.eta_at + timedelta(days=1, minutes=plan.grace_minutes or 0)
    checkin_token = sign_token(plan.id, "checkin", exp)
    checkout_token = sign_token(plan.id, "checkout", exp)

    events = await list_events(session, plan.id)
    return templates.TemplateResponse(
        "owner_plan.html",
        {
            "request": request,
            "plan": plan,
            "events": events,
            "checkin_url": f"{settings.PUBLIC_BASE_URL}/t/{checkin_token}/checkin",
            "checkout_url": f"{settings.PUBLIC_BASE_URL}/t/{checkout_token}/checkout",
        },
    )
