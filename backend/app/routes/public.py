from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_session
from ..models import Event, Plan
from ..services.tokens import verify_token

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def wants_html(request: Request) -> bool:
    return "text/html" in (request.headers.get("accept") or "")


@router.get("/{token}/checkin")
async def public_checkin(token: str, request: Request, session: AsyncSession = Depends(get_session)):
    try:
        plan_id, _ = verify_token(token, expected_purpose="checkin")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    plan = await session.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")

    session.add(Event(plan_id=plan_id, kind="checkin"))
    await session.commit()

    if wants_html(request):
        return templates.TemplateResponse(
            "public_done.html",
            {"request": request, "action": "Check-In", "plan": plan},
        )
    return {"ok": True, "plan_id": plan_id, "action": "checkin"}


@router.get("/{token}/checkout")
async def public_checkout(token: str, request: Request, session: AsyncSession = Depends(get_session)):
    try:
        plan_id, _ = verify_token(token, expected_purpose="checkout")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    plan = await session.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")

    session.add(Event(plan_id=plan_id, kind="checkout"))
    plan.status = "complete"
    await session.commit()

    if wants_html(request):
        return templates.TemplateResponse(
            "public_done.html",
            {"request": request, "action": "Check-Out", "plan": plan},
        )
    return {"ok": True, "plan_id": plan_id, "action": "checkout"}
