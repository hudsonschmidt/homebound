from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.db import get_session
from ..core.security import get_current_user_id
from ..messaging.apns import get_push_sender
from ..schemas import DeviceOut, DeviceRegisterIn
from ..services.devices import delete_device, list_devices_for_user, upsert_device

router = APIRouter()


@router.get("/devices", response_model=list[DeviceOut])
async def list_my_devices(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user_id = get_current_user_id(request)
    devices = await list_devices_for_user(session, user_id)
    return [DeviceOut.model_validate(d, from_attributes=True) for d in devices]


@router.post("/devices", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
async def register_device(
    payload: DeviceRegisterIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user_id = get_current_user_id(request)

    bundle_id = payload.bundle_id or settings.IOS_BUNDLE_ID
    dev = await upsert_device(
        session,
        user_id=user_id,
        token=payload.token,
        platform=payload.platform,
        bundle_id=bundle_id,
        env=payload.env,
    )
    return DeviceOut.model_validate(dev, from_attributes=True)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_device(
    device_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user_id = get_current_user_id(request)
    ok = await delete_device(session, user_id, device_id)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return None


@router.post("/devices/test", status_code=200)
async def test_push_to_my_devices(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Sends a test push to all of the user's devices.
    Requires Authorization: Bearer <access-token>.
    """
    user_id = get_current_user_id(request)
    devices = await list_devices_for_user(session, user_id)
    if not devices:
        return {"sent": 0, "results": []}

    sender = get_push_sender()
    results = []
    for d in devices:
        res = await sender.send(d.token, "Homebound", "Test push", {"kind": "test"})
        results.append({"device_id": d.id, **res.dict()})

    # Close APNs httpx client if used
    try:
        await sender.close()  # type: ignore[attr-defined]
    except Exception:
        pass

    return {"sent": len(results), "results": results}
