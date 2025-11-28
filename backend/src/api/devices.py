"""Device registration endpoints for push notifications"""
from datetime import UTC, datetime

import sqlalchemy
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src import database as db
from src.api import auth

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


@router.post("/", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
def register_device(body: DeviceRegister, user_id: int = Depends(auth.get_current_user_id)):
    """Register or update a device for push notifications"""

    # Validate platform
    if body.platform not in ["ios", "android"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid platform. Must be 'ios' or 'android'"
        )

    # Validate env
    if body.env not in ["production", "development"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid env. Must be 'production' or 'development'"
        )

    with db.engine.begin() as connection:
        # Check if device already exists
        existing = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM devices
                WHERE token = :token
                """
            ),
            {"token": body.token}
        ).fetchone()

        now = datetime.now(UTC).isoformat()

        if existing:
            # Update existing device
            connection.execute(
                sqlalchemy.text(
                    """
                    UPDATE devices
                    SET user_id = :user_id, platform = :platform, bundle_id = :bundle_id,
                        env = :env, last_seen_at = :last_seen_at
                    WHERE token = :token
                    """
                ),
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
            result = connection.execute(
                sqlalchemy.text("""
                    INSERT INTO devices
                        (user_id, platform, token, bundle_id, env, created_at, last_seen_at)
                    VALUES
                        (:user_id, :platform, :token, :bundle_id, :env, :created_at, :last_seen_at)
                    RETURNING id
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
            row = result.fetchone()
            assert row is not None
            device_id = row[0]

        # Fetch device
        device = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, platform, token, bundle_id, env, created_at, last_seen_at
                FROM devices
                WHERE id = :device_id
                """
            ),
            {"device_id": device_id}
        ).fetchone()
        assert device is not None

        return DeviceResponse(
            id=device.id,
            platform=device.platform,
            token=device.token,
            bundle_id=device.bundle_id,
            env=device.env,
            created_at=str(device.created_at),
            last_seen_at=str(device.last_seen_at)
        )


@router.get("/", response_model=list[DeviceResponse])
def get_devices(user_id: int = Depends(auth.get_current_user_id)):
    """Get all registered devices for the current user"""
    with db.engine.begin() as connection:
        devices = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, platform, token, bundle_id, env, created_at, last_seen_at
                FROM devices
                WHERE user_id = :user_id
                ORDER BY last_seen_at DESC
                """
            ),
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
    with db.engine.begin() as connection:
        # Verify device ownership
        device = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM devices
                WHERE id = :device_id AND user_id = :user_id
                """
            ),
            {"device_id": device_id, "user_id": user_id}
        ).fetchone()

        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found"
            )

        # Delete device
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE id = :device_id"),
            {"device_id": device_id}
        )

        return {"ok": True, "message": "Device unregistered successfully"}


@router.delete("/token/{token}")
def delete_device_by_token(token: str, user_id: int = Depends(auth.get_current_user_id)):
    """Unregister a device by token"""
    with db.engine.begin() as connection:
        # Verify device ownership
        device = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM devices
                WHERE token = :token AND user_id = :user_id
                """
            ),
            {"token": token, "user_id": user_id}
        ).fetchone()

        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found"
            )

        # Delete device
        connection.execute(
            sqlalchemy.text("DELETE FROM devices WHERE token = :token"),
            {"token": token}
        )

        return {"ok": True, "message": "Device unregistered successfully"}
