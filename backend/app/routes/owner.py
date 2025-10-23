from datetime import datetime, timedelta

from fastapi import APIRouter

router = APIRouter()


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: int):
    # placeholder owner view
    eta = (datetime.utcnow() + timedelta(hours=4)).isoformat()
    return {"id": plan_id, "title": "Demo Plan", "eta": eta}


@router.post("/plans")
async def create_plan():
    # placeholder create
    return {"id": 1, "message": "plan created (stub)"}


@router.get("/plans/{plan_id}/timeline")
async def timeline(plan_id: int):
    return {"plan_id": plan_id, "events": [{"kind": "created"}]}
