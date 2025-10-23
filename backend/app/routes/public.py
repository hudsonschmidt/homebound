from fastapi import APIRouter

router = APIRouter()


@router.get("/{token}/checkin")
async def public_checkin(token: str):
    return {"token": token, "ok": True, "action": "checkin (stub)"}


@router.get("/{token}/checkout")
async def public_checkout(token: str):
    return {"token": token, "ok": True, "action": "checkout (stub)"}
