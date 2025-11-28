"""Public check-in/check-out endpoints using tokens (no auth required)"""
import asyncio
import logging
from datetime import UTC, datetime

import sqlalchemy
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel

from src import database as db
from src.services.notifications import (
    send_checkin_update_emails,
    send_overdue_resolved_emails,
    send_trip_completed_emails,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/t", tags=["checkin"])


class CheckinResponse(BaseModel):
    ok: bool
    message: str


@router.get("/{token}/checkin", response_model=CheckinResponse)
def checkin_with_token(
    token: str,
    background_tasks: BackgroundTasks,
    lat: float | None = Query(None, description="Latitude of check-in location"),
    lon: float | None = Query(None, description="Longitude of check-in location")
):
    """Check in to a trip using a magic token. Optionally include lat/lon coordinates."""
    with db.engine.begin() as connection:
        # Find trip by checkin_token with activity name, timezone, location, and ETA
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.status, t.contact1, t.contact2, t.contact3,
                       t.timezone, t.location_text, t.eta, a.name as activity_name
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
        now = datetime.now(UTC)
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
        all_contact_ids = [trip.contact1, trip.contact2, trip.contact3]
        contact_ids = [cid for cid in all_contact_ids if cid is not None]
        contacts_for_email = []
        if contact_ids:
            placeholders = ", ".join([f":id{i}" for i in range(len(contact_ids))])
            params = {f"id{i}": cid for i, cid in enumerate(contact_ids)}
            query = f"SELECT id, name, email FROM contacts WHERE id IN ({placeholders})"
            contacts_result = connection.execute(
                sqlalchemy.text(query),
                params
            ).fetchall()
            contacts_for_email = [dict(c._mapping) for c in contacts_result]

        # Build trip dict for email notification
        trip_data = {"title": trip.title, "location_text": trip.location_text, "eta": trip.eta}
        activity_name = trip.activity_name
        user_timezone = trip.timezone

        # Format coordinates if provided
        coordinates_str = None
        if lat is not None and lon is not None:
            coordinates_str = f"{lat:.6f}, {lon:.6f}"
            log.info(f"[Checkin] Received coordinates: {coordinates_str}")

        # Schedule background task to send checkin update emails to contacts
        def send_emails_sync():
            asyncio.run(send_checkin_update_emails(
                trip=trip_data,
                contacts=contacts_for_email,
                user_name=user_name,
                activity_name=activity_name,
                user_timezone=user_timezone,
                coordinates=coordinates_str
            ))

        background_tasks.add_task(send_emails_sync)
        num_contacts = len(contacts_for_email)
        log.info(f"[Checkin] Scheduled checkin update emails for {num_contacts} contacts")

        return CheckinResponse(
            ok=True,
            message=f"Successfully checked in to '{trip.title}'"
        )


@router.get("/{token}/checkout", response_model=CheckinResponse)
def checkout_with_token(token: str, background_tasks: BackgroundTasks):
    """Complete/check out of a trip using a magic token"""
    with db.engine.begin() as connection:
        # Find trip by checkout_token with activity name, timezone, and location
        # Allow checkout for active, overdue, and overdue_notified trips
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.status, t.contact1, t.contact2, t.contact3,
                       t.timezone, t.location_text, a.name as activity_name
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.checkout_token = :token
                AND t.status IN ('active', 'overdue', 'overdue_notified')
                """
            ),
            {"token": token}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid or expired check-out link"
            )

        # Check if trip was overdue (contacts were already notified)
        was_overdue = trip.status in ('overdue', 'overdue_notified')

        # Mark trip as completed
        now = datetime.now(UTC)
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
        all_contact_ids = [trip.contact1, trip.contact2, trip.contact3]
        contact_ids = [cid for cid in all_contact_ids if cid is not None]
        contacts_for_email = []
        if contact_ids:
            placeholders = ", ".join([f":id{i}" for i in range(len(contact_ids))])
            params = {f"id{i}": cid for i, cid in enumerate(contact_ids)}
            query = f"SELECT id, name, email FROM contacts WHERE id IN ({placeholders})"
            contacts_result = connection.execute(
                sqlalchemy.text(query),
                params
            ).fetchall()
            contacts_for_email = [dict(c._mapping) for c in contacts_result]

        # Build trip dict for email notification
        trip_data = {"title": trip.title, "location_text": trip.location_text}
        activity_name = trip.activity_name
        user_timezone = trip.timezone

        # Schedule background task to send emails to contacts
        # If trip was overdue, send "all clear" email from alerts@
        def send_emails_sync():
            if was_overdue:
                # Send urgent "all clear" email since contacts were already alerted
                asyncio.run(send_overdue_resolved_emails(
                    trip=trip_data,
                    contacts=contacts_for_email,
                    user_name=user_name,
                    activity_name=activity_name,
                    user_timezone=user_timezone
                ))
            else:
                # Normal completion email
                asyncio.run(send_trip_completed_emails(
                    trip=trip_data,
                    contacts=contacts_for_email,
                    user_name=user_name,
                    activity_name=activity_name,
                    user_timezone=user_timezone
                ))

        background_tasks.add_task(send_emails_sync)
        email_type = "overdue resolved" if was_overdue else "completion"
        log.info(f"[Checkout] Scheduled {email_type} emails for {len(contacts_for_email)} contacts")

        return CheckinResponse(
            ok=True,
            message=f"Successfully completed '{trip.title}' - you're safe!"
        )
