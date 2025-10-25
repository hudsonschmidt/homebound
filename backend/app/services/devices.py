from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Device


async def upsert_device(
    session: AsyncSession,
    *,
    user_id: int,
    token: str,
    platform: str,
    bundle_id: str,
    env: str,
) -> Device:
    # Find by token
    res = await session.execute(select(Device).where(Device.token == token))
    dev = res.scalars().first()
    if dev:
        dev.user_id = user_id
        dev.platform = platform
        dev.bundle_id = bundle_id
        dev.env = env
        dev.last_seen_at = datetime.utcnow()
    else:
        dev = Device(
            user_id=user_id,
            token=token,
            platform=platform,
            bundle_id=bundle_id,
            env=env,
        )
        session.add(dev)

    await session.commit()
    await session.refresh(dev)
    return dev


async def list_devices_for_user(session: AsyncSession, user_id: int) -> list[Device]:
    res = await session.execute(select(Device).where(Device.user_id == user_id))
    return list(res.scalars().all())


async def delete_device(session: AsyncSession, user_id: int, device_id: int) -> bool:
    dev = await session.get(Device, device_id)
    if not dev or dev.user_id != user_id:
        return False
    await session.delete(dev)
    await session.commit()
    return True
