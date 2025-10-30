"""Device registration endpoints for push notifications with raw SQL"""
from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from src import database as db
from src.api import auth
import sqlalchemy

router = APIRouter(
    prefix="/api/v1/devices",
    tags=["devices"],
    dependencies=[Depends(auth.get_current_user_id)]
)


class DeviceRegister(BaseModel):
    platform: str  # "ios" or "android"
    token: str  # APNs or FCM token
    bundle_id: str
    env: str = "production"  # "production" or "development"


class DeviceResponse(BaseModel):
    id: int
    platform: str
    token: str
    bundle_id: str
    env: str
    created_at: str
    last_seen_at: str


@router.post("", response_model=DeviceResponse)
def register_device(body: DeviceRegister, user_id: int = Depends(auth.get_current_user_id)):
    """Register or update a device for push notifications"""

    # Validate platform
    if body.platform not in ["ios", "android"]:
        raise HTTPException(status_code=400, detail="Invalid platform. Must be 'ios' or 'android'")

    # Validate env
    if body.env not in ["production", "development"]:
        raise HTTPException(status_code=400, detail="Invalid env. Must be 'production' or 'development'")

    with db.engine.begin() as conn:
        # Check if device already exists
        existing = conn.execute(
            sqlalchemy.text("""
                SELECT id FROM devices WHERE token = :token
            """),
            {"token": body.token}
        ).fetchone()

        now = datetime.utcnow().isoformat()

        if existing:
            # Update existing device
            conn.execute(
                sqlalchemy.text("""
                    UPDATE devices
                    SET user_id = :user_id, platform = :platform, bundle_id = :bundle_id,
                        env = :env, last_seen_at = :last_seen_at
                    WHERE token = :token
                """),
                {
                    "user_id": user_id,
                    "platform": body.platform,
                    "bundle_id": body.bundle_id,
                    "env": body.env,
                    "last_seen_at": now,
                    "token": body.token
                }
            )
            device_id = existing.id
        else:
            # Insert new device
            result = conn.execute(
                sqlalchemy.text("""
                    INSERT INTO devices (user_id, platform, token, bundle_id, env, created_at, last_seen_at)
                    VALUES (:user_id, :platform, :token, :bundle_id, :env, :created_at, :last_seen_at)
                """),
                {
                    "user_id": user_id,
                    "platform": body.platform,
                    "token": body.token,
                    "bundle_id": body.bundle_id,
                    "env": body.env,
                    "created_at": now,
                    "last_seen_at": now
                }
            )
            device_id = result.lastrowid

        # Fetch device
        device = conn.execute(
            sqlalchemy.text("""
                SELECT id, platform, token, bundle_id, env, created_at, last_seen_at
                FROM devices
                WHERE id = :device_id
            """),
            {"device_id": device_id}
        ).fetchone()

        return DeviceResponse(
            id=device.id,
            platform=device.platform,
            token=device.token,
            bundle_id=device.bundle_id,
            env=device.env,
            created_at=str(device.created_at),
            last_seen_at=str(device.last_seen_at)
        )


@router.get("", response_model=List[DeviceResponse])
def list_devices(user_id: int = Depends(auth.get_current_user_id)):
    """List all registered devices for the current user"""

    with db.engine.begin() as conn:
        devices = conn.execute(
            sqlalchemy.text("""
                SELECT id, platform, token, bundle_id, env, created_at, last_seen_at
                FROM devices
                WHERE user_id = :user_id
                ORDER BY last_seen_at DESC
            """),
            {"user_id": user_id}
        ).fetchall()

        return [
            DeviceResponse(
                id=d.id,
                platform=d.platform,
                token=d.token,
                bundle_id=d.bundle_id,
                env=d.env,
                created_at=str(d.created_at),
                last_seen_at=str(d.last_seen_at)
            )
            for d in devices
        ]


@router.delete("/{device_id}")
def delete_device(device_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Unregister a device"""

    with db.engine.begin() as conn:
        # Verify device ownership
        device = conn.execute(
            sqlalchemy.text("SELECT id FROM devices WHERE id = :device_id AND user_id = :user_id"),
            {"device_id": device_id, "user_id": user_id}
        ).fetchone()

        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        # Delete device
        conn.execute(
            sqlalchemy.text("DELETE FROM devices WHERE id = :device_id"),
            {"device_id": device_id}
        )

        return {"ok": True, "message": "Device unregistered successfully"}


@router.delete("/token/{token}")
def delete_device_by_token(token: str, user_id: int = Depends(auth.get_current_user_id)):
    """Unregister a device by token"""

    with db.engine.begin() as conn:
        # Verify device ownership
        device = conn.execute(
            sqlalchemy.text("SELECT id FROM devices WHERE token = :token AND user_id = :user_id"),
            {"token": token, "user_id": user_id}
        ).fetchone()

        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        # Delete device
        conn.execute(
            sqlalchemy.text("DELETE FROM devices WHERE token = :token"),
            {"token": token}
        )

        return {"ok": True, "message": "Device unregistered successfully"}
