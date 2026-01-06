"""Live Activity token registration endpoints for iOS Live Activity push updates"""
import logging
from datetime import UTC, datetime

import sqlalchemy
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src import database as db
from src.api import auth

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/live-activity-tokens",
    tags=["live-activity"],
    dependencies=[Depends(auth.get_current_user_id)]
)


class LiveActivityTokenRegister(BaseModel):
    token: str  # Live Activity push token (different from device APNs token)
    trip_id: int
    bundle_id: str
    env: str = "production"  # "production" or "development"


class LiveActivityTokenResponse(BaseModel):
    id: int
    trip_id: int
    token: str
    bundle_id: str
    env: str
    created_at: str
    updated_at: str


@router.post("/", response_model=LiveActivityTokenResponse, status_code=status.HTTP_201_CREATED)
def register_live_activity_token(
    body: LiveActivityTokenRegister,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Register or update a Live Activity push token for a trip.

    This token is used to send push updates to the Live Activity widget
    displayed on the iOS lock screen and Dynamic Island.
    """

    # Validate env
    if body.env not in ["production", "development"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid env. Must be 'production' or 'development'"
        )

    with db.engine.begin() as conn:
        # Verify trip ownership OR accepted participant status
        trip = conn.execute(
            sqlalchemy.text("""
                SELECT id FROM trips WHERE id = :trip_id
                AND (
                    user_id = :user_id
                    OR EXISTS (
                        SELECT 1 FROM trip_participants
                        WHERE trip_id = :trip_id AND user_id = :user_id AND status = 'accepted'
                    )
                )
            """),
            {"trip_id": body.trip_id, "user_id": user_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        now = datetime.now(UTC).isoformat()

        # Upsert token (one per trip) using ON CONFLICT on the unique index
        result = conn.execute(
            sqlalchemy.text("""
                INSERT INTO live_activity_tokens
                    (trip_id, user_id, token, bundle_id, env, created_at, updated_at)
                VALUES
                    (:trip_id, :user_id, :token, :bundle_id, :env, :created_at, :updated_at)
                ON CONFLICT (trip_id) DO UPDATE SET
                    token = EXCLUDED.token,
                    bundle_id = EXCLUDED.bundle_id,
                    env = EXCLUDED.env,
                    updated_at = EXCLUDED.updated_at
                RETURNING id, trip_id, token, bundle_id, env, created_at, updated_at
            """),
            {
                "trip_id": body.trip_id,
                "user_id": user_id,
                "token": body.token,
                "bundle_id": body.bundle_id,
                "env": body.env,
                "created_at": now,
                "updated_at": now,
            }
        )
        row = result.fetchone()
        assert row is not None

        log.info(
            f"[LiveActivity] Token registered: trip_id={row.trip_id}, user_id={user_id}, "
            f"env={row.env}, token_prefix={row.token[:20]}..."
        )

        return LiveActivityTokenResponse(
            id=row.id,
            trip_id=row.trip_id,
            token=row.token,
            bundle_id=row.bundle_id,
            env=row.env,
            created_at=str(row.created_at),
            updated_at=str(row.updated_at)
        )


@router.delete("/{trip_id}")
def delete_live_activity_token(
    trip_id: int,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Remove a Live Activity token when the activity ends.

    Called when the user completes their trip or the Live Activity is dismissed.
    """
    with db.engine.begin() as conn:
        # Verify ownership and delete
        result = conn.execute(
            sqlalchemy.text("""
                DELETE FROM live_activity_tokens
                WHERE trip_id = :trip_id AND user_id = :user_id
            """),
            {"trip_id": trip_id, "user_id": user_id}
        )

        if result.rowcount == 0:
            # Token may already be deleted, don't error
            log.info(f"[LiveActivity] Token delete requested but not found: trip_id={trip_id}, user_id={user_id}")
            return {"ok": True, "message": "Token not found or already removed"}

        log.info(f"[LiveActivity] Token deleted: trip_id={trip_id}, user_id={user_id}")
        return {"ok": True, "message": "Token removed successfully"}


@router.get("/{trip_id}", response_model=LiveActivityTokenResponse)
def get_live_activity_token(
    trip_id: int,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Get the Live Activity token for a trip (mainly for debugging)."""
    with db.engine.begin() as conn:
        row = conn.execute(
            sqlalchemy.text("""
                SELECT id, trip_id, token, bundle_id, env, created_at, updated_at
                FROM live_activity_tokens
                WHERE trip_id = :trip_id AND user_id = :user_id
            """),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Live Activity token not found for this trip"
            )

        return LiveActivityTokenResponse(
            id=row.id,
            trip_id=row.trip_id,
            token=row.token,
            bundle_id=row.bundle_id,
            env=row.env,
            created_at=str(row.created_at),
            updated_at=str(row.updated_at)
        )


@router.get("/debug/{trip_id}")
def debug_token_status(trip_id: int):
    """Debug endpoint to check token status for a trip (no auth required for debugging)."""
    with db.engine.connect() as conn:
        # Get token for this trip
        token_row = conn.execute(
            sqlalchemy.text("""
                SELECT id, trip_id, user_id, token, bundle_id, env, created_at, updated_at
                FROM live_activity_tokens
                WHERE trip_id = :trip_id
            """),
            {"trip_id": trip_id}
        ).fetchone()

        # Get count of all tokens
        total_count = conn.execute(
            sqlalchemy.text("SELECT COUNT(*) as cnt FROM live_activity_tokens")
        ).fetchone()

        if not token_row:
            return {
                "found": False,
                "trip_id": trip_id,
                "message": f"No token found for trip {trip_id}",
                "total_tokens_in_db": total_count.cnt if total_count else 0
            }

        return {
            "found": True,
            "id": token_row.id,
            "trip_id": token_row.trip_id,
            "user_id": token_row.user_id,
            "env": token_row.env,
            "bundle_id": token_row.bundle_id,
            "token_prefix": token_row.token[:20] + "...",
            "created_at": str(token_row.created_at),
            "updated_at": str(token_row.updated_at),
            "total_tokens_in_db": total_count.cnt if total_count else 0
        }
