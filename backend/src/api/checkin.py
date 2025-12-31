"""Public check-in/check-out endpoints using tokens (no auth required)"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta

import sqlalchemy
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel

from src import database as db
from src.services.geocoding import reverse_geocode_sync
from src.services.notifications import (
    send_checkin_update_emails,
    send_friend_checkin_push,
    send_friend_overdue_resolved_push,
    send_friend_trip_completed_push,
    send_live_activity_update,
    send_overdue_resolved_emails,
    send_push_to_user,
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
        # Find trip by checkin_token with activity name, timezone, location, ETA, and grace period
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.status, t.contact1, t.contact2, t.contact3,
                       t.timezone, t.location_text, t.eta, t.notify_self, t.grace_min,
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

        # Log the check-in event with location coordinates
        now = datetime.now(UTC)
        log.info(f"[Checkin] About to INSERT event with lat={lat}, lon={lon}, types: lat={type(lat)}, lon={type(lon)}")
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO events (user_id, trip_id, what, timestamp, lat, lon)
                VALUES (:user_id, :trip_id, 'checkin', :timestamp, :lat, :lon)
                RETURNING id
                """
            ),
            {"user_id": trip.user_id, "trip_id": trip.id, "timestamp": now.isoformat(), "lat": lat, "lon": lon}
        )
        row = result.fetchone()
        assert row is not None
        event_id = row[0]
        log.info(f"[Checkin] Created event id={event_id} with lat={lat}, lon={lon}")

        # Update last check-in event reference, reset status to active, and clear warning timestamps
        # Also reset transition flags so Live Activity updates work if trip extends past new ETA
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trips
                SET last_checkin = :last_checkin_event_id,
                    status = 'active',
                    last_grace_warning = NULL,
                    last_checkin_reminder = :now,
                    notified_eta_transition = false,
                    notified_grace_transition = false
                WHERE id = :trip_id
                """
            ),
            {"last_checkin_event_id": event_id, "trip_id": trip.id, "now": now.isoformat()}
        )

        # Fetch user name and email for notification
        user = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name, email FROM users WHERE id = :user_id"),
            {"user_id": trip.user_id}
        ).fetchone()
        user_name = f"{user.first_name} {user.last_name}".strip() if user else "Someone"
        if not user_name:
            user_name = "A Homebound user"
        owner_email = user.email if user and trip.notify_self else None

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

        # Format coordinates if provided and perform reverse geocoding
        coordinates_str = None
        location_name = None
        if lat is not None and lon is not None:
            coordinates_str = f"{lat:.6f}, {lon:.6f}"
            log.info(f"[Checkin] Received coordinates: {coordinates_str}")
            # Reverse geocode to get human-readable location name
            location_name = reverse_geocode_sync(lat, lon)
            if location_name:
                log.info(f"[Checkin] Reverse geocoded to: {location_name}")
            else:
                log.info("[Checkin] Reverse geocoding returned no result")

        # Get check-in count for Live Activity update
        checkin_count_row = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM events WHERE trip_id = :trip_id AND what = 'checkin'"),
            {"trip_id": trip.id}
        ).fetchone()
        checkin_count = checkin_count_row[0] if checkin_count_row else 1

        # Parse ETA for Live Activity update
        eta_dt = None
        if trip.eta:
            try:
                eta_str = str(trip.eta).replace(' ', 'T').replace('Z', '').replace('+00:00', '')
                eta_dt = datetime.fromisoformat(eta_str)
            except Exception:
                eta_dt = now

        # Capture values for background tasks
        trip_id_for_la = trip.id
        eta_for_la = eta_dt or now
        now_for_la = now
        checkin_count_for_la = checkin_count

        # After check-in, user is no longer overdue - they just confirmed they're okay
        # The trip status is reset to 'active', so is_overdue should be False
        grace_min = trip.grace_min or 15  # Default 15 minutes if not set
        is_overdue_for_la = False  # User just checked in, so not overdue
        grace_min_for_la = grace_min

        # Always send Live Activity update (runs in background)
        def send_live_activity_sync():
            asyncio.run(send_live_activity_update(
                trip_id=trip_id_for_la,
                status="active",
                eta=eta_for_la,
                last_checkin_time=now_for_la,
                is_overdue=is_overdue_for_la,
                checkin_count=checkin_count_for_la,
                grace_min=grace_min_for_la
            ))

        background_tasks.add_task(send_live_activity_sync)

        # Schedule background task to send checkin update emails to contacts and push to user
        def send_notifications_sync():
            # Send push notification to user confirming check-in
            asyncio.run(send_push_to_user(
                trip.user_id,
                "Checked In",
                f"You've checked in to '{trip.title}'. Stay safe!"
            ))

            # Send emails to contacts
            asyncio.run(send_checkin_update_emails(
                trip=trip_data,
                contacts=contacts_for_email,
                user_name=user_name,
                activity_name=activity_name,
                user_timezone=user_timezone,
                coordinates=coordinates_str,
                location_name=location_name,
                owner_email=owner_email
            ))

        if contacts_for_email or owner_email:
            background_tasks.add_task(send_notifications_sync)
        num_contacts = len(contacts_for_email)
        log.info(f"[Checkin] Scheduled checkin update emails for {num_contacts} contacts")

        # Send push notifications to friend safety contacts
        friend_contacts = connection.execute(
            sqlalchemy.text(
                """
                SELECT friend_user_id FROM trip_safety_contacts
                WHERE trip_id = :trip_id AND friend_user_id IS NOT NULL
                ORDER BY position
                """
            ),
            {"trip_id": trip.id}
        ).fetchall()
        friend_user_ids = [f.friend_user_id for f in friend_contacts]

        if friend_user_ids:
            trip_title_for_push = trip.title
            user_name_for_push = user_name
            def send_friend_checkin_sync():
                for friend_id in friend_user_ids:
                    asyncio.run(send_friend_checkin_push(
                        friend_user_id=friend_id,
                        user_name=user_name_for_push,
                        trip_title=trip_title_for_push
                    ))

            background_tasks.add_task(send_friend_checkin_sync)
            log.info(f"[Checkin] Scheduled check-in push notifications for {len(friend_user_ids)} friend contacts")

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
                       t.timezone, t.location_text, t.notify_self, a.name as activity_name
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

        # Fetch user name and email for notification
        user = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name, email FROM users WHERE id = :user_id"),
            {"user_id": trip.user_id}
        ).fetchone()
        user_name = f"{user.first_name} {user.last_name}".strip() if user else "Someone"
        if not user_name:
            user_name = "A Homebound user"
        owner_email = user.email if user and trip.notify_self else None

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

        # Capture trip ID for Live Activity end
        trip_id_for_la = trip.id

        # Send Live Activity "end" event to dismiss the widget
        def send_live_activity_end_sync():
            asyncio.run(send_live_activity_update(
                trip_id=trip_id_for_la,
                status="completed",
                eta=now,
                last_checkin_time=None,
                is_overdue=False,
                checkin_count=0,
                event="end"
            ))

        background_tasks.add_task(send_live_activity_end_sync)

        # Schedule background task to send emails to contacts
        # If trip was overdue, send "all clear" email from alerts@
        def send_notifications_sync():
            # Send emails to contacts
            if was_overdue:
                # Send urgent "all clear" email since contacts were already alerted
                asyncio.run(send_overdue_resolved_emails(
                    trip=trip_data,
                    contacts=contacts_for_email,
                    user_name=user_name,
                    activity_name=activity_name,
                    user_timezone=user_timezone,
                    owner_email=owner_email
                ))
            else:
                # Normal completion email
                asyncio.run(send_trip_completed_emails(
                    trip=trip_data,
                    contacts=contacts_for_email,
                    user_name=user_name,
                    activity_name=activity_name,
                    user_timezone=user_timezone,
                    owner_email=owner_email
                ))

        if contacts_for_email or owner_email:
            background_tasks.add_task(send_notifications_sync)
        email_type = "overdue resolved" if was_overdue else "completion"
        log.info(f"[Checkout] Scheduled {email_type} emails for {len(contacts_for_email)} contacts")

        # Send push notifications to friend safety contacts
        friend_contacts = connection.execute(
            sqlalchemy.text(
                """
                SELECT friend_user_id FROM trip_safety_contacts
                WHERE trip_id = :trip_id AND friend_user_id IS NOT NULL
                ORDER BY position
                """
            ),
            {"trip_id": trip.id}
        ).fetchall()
        friend_user_ids = [f.friend_user_id for f in friend_contacts]

        if friend_user_ids:
            trip_title_for_push = trip.title
            user_name_for_push = user_name
            was_overdue_for_push = was_overdue
            def send_friend_push_sync():
                for friend_id in friend_user_ids:
                    if was_overdue_for_push:
                        asyncio.run(send_friend_overdue_resolved_push(
                            friend_user_id=friend_id,
                            user_name=user_name_for_push,
                            trip_title=trip_title_for_push
                        ))
                    else:
                        asyncio.run(send_friend_trip_completed_push(
                            friend_user_id=friend_id,
                            user_name=user_name_for_push,
                            trip_title=trip_title_for_push
                        ))

            background_tasks.add_task(send_friend_push_sync)
            push_type = "overdue resolved" if was_overdue else "completed"
            log.info(f"[Checkout] Scheduled {push_type} push notifications for {len(friend_user_ids)} friend contacts")

        return CheckinResponse(
            ok=True,
            message=f"Successfully completed '{trip.title}' - you're safe!"
        )
