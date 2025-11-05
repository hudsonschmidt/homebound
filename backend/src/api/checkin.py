"""Public check-in/check-out endpoints using tokens (no auth required)"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from src import database as db
import sqlalchemy

router = APIRouter(prefix="/t", tags=["checkin"])


class CheckinResponse(BaseModel):
    ok: bool
    message: str


@router.get("/{token}/checkin", response_model=CheckinResponse)
def checkin_with_token(token: str):
    """Check in to a trip using a magic token"""
    with db.engine.begin() as connection:
        # Find trip by checkin_token
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, user_id, title, status
                FROM trips
                WHERE checkin_token = :token
                AND status = 'active'
                """
            ),
            {"token": token}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid or expired check-in link"
            )

        # Log the check-in event
        now = datetime.now(timezone.utc)
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO events (user_id, trip_id, what, timestamp)
                VALUES (:user_id, :trip_id, 'checkin', :timestamp)
                RETURNING id
                """
            ),
            {"user_id": trip.user_id, "trip_id": trip.id, "timestamp": now.isoformat()}
        )
        event_id = result.fetchone()[0]

        # Update last check-in reference
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trips
                SET last_checkin = :event_id
                WHERE id = :trip_id
                """
            ),
            {"event_id": event_id, "trip_id": trip.id}
        )

        return CheckinResponse(
            ok=True,
            message=f"Successfully checked in to '{trip.title}'"
        )


@router.get("/{token}/checkout", response_model=CheckinResponse)
def checkout_with_token(token: str):
    """Complete/check out of a trip using a magic token"""
    with db.engine.begin() as connection:
        # Find trip by checkout_token
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, user_id, title, status
                FROM trips
                WHERE checkout_token = :token
                AND status = 'active'
                """
            ),
            {"token": token}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid or expired check-out link"
            )

        # Mark trip as completed
        now = datetime.now(timezone.utc)
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trips
                SET status = 'completed',
                    completed_at = :now
                WHERE id = :trip_id
                """
            ),
            {"now": now.isoformat(), "trip_id": trip.id}
        )

        # Log the checkout event
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO events (user_id, trip_id, what, timestamp)
                VALUES (:user_id, :trip_id, 'complete', :timestamp)
                """
            ),
            {"user_id": trip.user_id, "trip_id": trip.id, "timestamp": now.isoformat()}
        )

        return CheckinResponse(
            ok=True,
            message=f"Successfully completed '{trip.title}' - you're safe!"
        )
