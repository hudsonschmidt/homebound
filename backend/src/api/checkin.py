"""Public check-in/check-out endpoints using tokens (no auth required)"""
import asyncio
from datetime import datetime, timezone
import logging
from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from src import database as db
from src.services.notifications import send_trip_completed_emails, send_checkin_update_emails
import sqlalchemy

log = logging.getLogger(__name__)

router = APIRouter(prefix="/t", tags=["checkin"])


class CheckinResponse(BaseModel):
    ok: bool
    message: str


@router.get("/{token}/checkin", response_model=CheckinResponse)
def checkin_with_token(token: str, background_tasks: BackgroundTasks):
    """Check in to a trip using a magic token"""
    with db.engine.begin() as connection:
        # Find trip by checkin_token with activity name
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.status, t.contact1, t.contact2, t.contact3,
                       a.name as activity_name
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.checkin_token = :token
                AND t.status IN ('active', 'overdue', 'overdue_notified')
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

        # Update last check-in reference and reset status to active
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trips
                SET last_checkin = :event_id, status = 'active'
                WHERE id = :trip_id
                """
            ),
            {"event_id": event_id, "trip_id": trip.id}
        )

        # Fetch user name for email notification
        user = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": trip.user_id}
        ).fetchone()
        user_name = f"{user.first_name} {user.last_name}".strip() if user else "Someone"
        if not user_name:
            user_name = "A Homebound user"

        # Fetch contacts with email for notification
        contact_ids = [cid for cid in [trip.contact1, trip.contact2, trip.contact3] if cid is not None]
        contacts_for_email = []
        if contact_ids:
            placeholders = ", ".join([f":id{i}" for i in range(len(contact_ids))])
            params = {f"id{i}": cid for i, cid in enumerate(contact_ids)}
            contacts_result = connection.execute(
                sqlalchemy.text(f"SELECT id, name, email FROM contacts WHERE id IN ({placeholders})"),
                params
            ).fetchall()
            contacts_for_email = [dict(c._mapping) for c in contacts_result]

        # Build trip dict for email notification
        trip_data = {"title": trip.title}
        activity_name = trip.activity_name

        # Schedule background task to send checkin update emails to contacts
        def send_emails_sync():
            asyncio.run(send_checkin_update_emails(
                trip=trip_data,
                contacts=contacts_for_email,
                user_name=user_name,
                activity_name=activity_name
            ))

        background_tasks.add_task(send_emails_sync)
        log.info(f"[Checkin] Scheduled checkin update emails for {len(contacts_for_email)} contacts")

        return CheckinResponse(
            ok=True,
            message=f"Successfully checked in to '{trip.title}'"
        )


@router.get("/{token}/checkout", response_model=CheckinResponse)
def checkout_with_token(token: str, background_tasks: BackgroundTasks):
    """Complete/check out of a trip using a magic token"""
    with db.engine.begin() as connection:
        # Find trip by checkout_token with activity name
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.status, t.contact1, t.contact2, t.contact3,
                       a.name as activity_name
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.checkout_token = :token
                AND t.status = 'active'
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

        # Fetch user name for email notification
        user = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": trip.user_id}
        ).fetchone()
        user_name = f"{user.first_name} {user.last_name}".strip() if user else "Someone"
        if not user_name:
            user_name = "A Homebound user"

        # Fetch contacts with email for notification
        contact_ids = [cid for cid in [trip.contact1, trip.contact2, trip.contact3] if cid is not None]
        contacts_for_email = []
        if contact_ids:
            placeholders = ", ".join([f":id{i}" for i in range(len(contact_ids))])
            params = {f"id{i}": cid for i, cid in enumerate(contact_ids)}
            contacts_result = connection.execute(
                sqlalchemy.text(f"SELECT id, name, email FROM contacts WHERE id IN ({placeholders})"),
                params
            ).fetchall()
            contacts_for_email = [dict(c._mapping) for c in contacts_result]

        # Build trip dict for email notification
        trip_data = {"title": trip.title}
        activity_name = trip.activity_name

        # Schedule background task to send emails to contacts
        def send_emails_sync():
            asyncio.run(send_trip_completed_emails(
                trip=trip_data,
                contacts=contacts_for_email,
                user_name=user_name,
                activity_name=activity_name
            ))

        background_tasks.add_task(send_emails_sync)
        log.info(f"[Checkout] Scheduled completion emails for {len(contacts_for_email)} contacts")

        return CheckinResponse(
            ok=True,
            message=f"Successfully completed '{trip.title}' - you're safe!"
        )
