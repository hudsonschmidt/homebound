"""Public check-in/check-out endpoints using tokens (no auth required)"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta

import sqlalchemy
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel

from src import database as db
from src.api.trips import _get_all_trip_email_contacts
from src.services.geocoding import reverse_geocode_sync
from src.services.notifications import (
    send_checkin_update_emails,
    send_data_refresh_push,
    send_friend_checkin_push,
    send_friend_overdue_resolved_push,
    send_friend_trip_completed_push,
    send_live_activity_update,
    send_overdue_resolved_emails,
    send_push_to_user,
    send_trip_completed_emails,
    send_trip_completed_push,
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
                       t.is_group_trip, a.name as activity_name
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

        # For group trips, also update the participant's location
        # Check if trip is a group trip and if user is a participant
        is_group = connection.execute(
            sqlalchemy.text("SELECT is_group_trip FROM trips WHERE id = :trip_id"),
            {"trip_id": trip.id}
        ).fetchone()

        if is_group and is_group.is_group_trip:
            # Update or insert owner's check-in location using upsert
            # This handles the case where the owner's trip_participants record doesn't exist yet
            # (it's only created when the first participant is invited)
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO trip_participants (trip_id, user_id, role, status, last_checkin_at, last_lat, last_lon, joined_at, invited_by)
                    VALUES (:trip_id, :user_id, 'owner', 'accepted', :now, :lat, :lon, :now, :user_id)
                    ON CONFLICT (trip_id, user_id)
                    DO UPDATE SET last_checkin_at = :now, last_lat = :lat, last_lon = :lon
                    """
                ),
                {"trip_id": trip.id, "user_id": trip.user_id, "now": now.isoformat(), "lat": lat, "lon": lon}
            )
            log.info(f"[Checkin] Updated/inserted participant location for owner {trip.user_id} in group trip {trip.id}")

        # Fetch user name and email for notification
        user = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name, email FROM users WHERE id = :user_id"),
            {"user_id": trip.user_id}
        ).fetchone()
        user_name = f"{user.first_name} {user.last_name}".strip() if user else "Someone"
        if not user_name:
            user_name = "A Homebound user"
        owner_email = user.email if user and trip.notify_self else None

        # Fetch all contact emails - following the same pattern as participant check-in
        # which is known to work correctly
        log.info(f"[Checkin] Fetching contacts for trip {trip.id}, is_group_trip={trip.is_group_trip}")

        # Step 1: Get owner's email contacts from trips.contact1/2/3
        # Owner's contacts watch the owner
        owner_email_contacts = connection.execute(
            sqlalchemy.text(
                """
                SELECT c.id, c.name, c.email
                FROM contacts c
                JOIN trips t ON (c.id = t.contact1 OR c.id = t.contact2 OR c.id = t.contact3)
                WHERE t.id = :trip_id AND c.email IS NOT NULL
                """
            ),
            {"trip_id": trip.id}
        ).fetchall()

        contacts_for_email = [
            {**dict(c._mapping), "watched_user_name": user_name}
            for c in owner_email_contacts
        ]
        log.info(f"[Checkin] Found {len(contacts_for_email)} owner email contacts")

        # Step 2: For group trips, get ALL accepted participants and their contacts
        if trip.is_group_trip:
            # Get all accepted participants (excluding owner)
            accepted_participants = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT tp.user_id,
                           COALESCE(TRIM(u.first_name || ' ' || u.last_name), 'Participant') as participant_name
                    FROM trip_participants tp
                    JOIN users u ON tp.user_id = u.id
                    WHERE tp.trip_id = :trip_id
                      AND tp.status = 'accepted'
                      AND tp.role = 'participant'
                    """
                ),
                {"trip_id": trip.id}
            ).fetchall()
            log.info(f"[Checkin] Found {len(accepted_participants)} accepted participants")

            # For each participant, get their email contacts
            for participant in accepted_participants:
                participant_name = participant.participant_name.strip() if participant.participant_name else "Participant"
                participant_user_id = participant.user_id
                log.info(f"[Checkin] Fetching contacts for participant {participant_user_id} ({participant_name})")

                # Get this participant's email contacts from participant_trip_contacts
                participant_email_contacts = connection.execute(
                    sqlalchemy.text(
                        """
                        SELECT c.id, c.name, c.email
                        FROM participant_trip_contacts ptc
                        JOIN contacts c ON ptc.contact_id = c.id
                        WHERE ptc.trip_id = :trip_id
                          AND ptc.participant_user_id = :participant_user_id
                          AND ptc.contact_id IS NOT NULL
                          AND c.email IS NOT NULL
                        """
                    ),
                    {"trip_id": trip.id, "participant_user_id": participant_user_id}
                ).fetchall()

                # Add to contacts list with participant's name as watched_user_name
                for pc in participant_email_contacts:
                    if pc.email:
                        contacts_for_email.append({
                            "id": pc.id,
                            "name": pc.name,
                            "email": pc.email,
                            "watched_user_name": participant_name
                        })
                log.info(f"[Checkin] Found {len(participant_email_contacts)} email contacts for participant {participant_name}")

                # Get this participant's friend contacts (friends who have email)
                participant_friend_contacts = connection.execute(
                    sqlalchemy.text(
                        """
                        SELECT friend.id as id,
                               TRIM(friend.first_name || ' ' || friend.last_name) as name,
                               friend.email as email
                        FROM participant_trip_contacts ptc
                        JOIN users friend ON ptc.friend_user_id = friend.id
                        WHERE ptc.trip_id = :trip_id
                          AND ptc.participant_user_id = :participant_user_id
                          AND ptc.friend_user_id IS NOT NULL
                          AND friend.email IS NOT NULL
                        """
                    ),
                    {"trip_id": trip.id, "participant_user_id": participant_user_id}
                ).fetchall()

                # Add to contacts list with participant's name as watched_user_name
                for pfc in participant_friend_contacts:
                    if pfc.email:
                        contacts_for_email.append({
                            "id": -pfc.id,  # Negative to indicate it's a user, not a contact
                            "name": pfc.name or "Friend",
                            "email": pfc.email,
                            "watched_user_name": participant_name
                        })
                log.info(f"[Checkin] Found {len(participant_friend_contacts)} friend contacts for participant {participant_name}")

        # Step 3: Get owner's friend safety contacts (friends who have email)
        # Owner's friends also watch the owner
        owner_friend_contacts = connection.execute(
            sqlalchemy.text(
                """
                SELECT friend.id as id,
                       TRIM(friend.first_name || ' ' || friend.last_name) as name,
                       friend.email as email
                FROM trip_safety_contacts tsc
                JOIN users friend ON tsc.friend_user_id = friend.id
                WHERE tsc.trip_id = :trip_id
                  AND tsc.friend_user_id IS NOT NULL
                  AND friend.email IS NOT NULL
                ORDER BY tsc.position
                """
            ),
            {"trip_id": trip.id}
        ).fetchall()

        # Add owner's friends to contacts list (they watch the owner)
        for ofc in owner_friend_contacts:
            if ofc.email:
                contacts_for_email.append({
                    "id": -ofc.id,  # Negative to indicate it's a user, not a contact
                    "name": ofc.name or "Friend",
                    "email": ofc.email,
                    "watched_user_name": user_name  # Owner's friends watch the owner
                })
        log.info(f"[Checkin] Found {len(owner_friend_contacts)} owner friend contacts")

        log.info(f"[Checkin] Total {len(contacts_for_email)} contacts for email notifications")
        for c in contacts_for_email:
            log.info(f"[Checkin] Contact: {c.get('email')} watching {c.get('watched_user_name')}")

        # Build trip dict for email notification
        trip_data = {"title": trip.title, "location_text": trip.location_text, "eta": trip.eta}
        activity_name = trip.activity_name
        user_timezone = trip.timezone

        # Format coordinates if provided (geocoding moved to background to avoid blocking response)
        coordinates_str = None
        coordinates_for_background = None
        if lat is not None and lon is not None:
            coordinates_str = f"{lat:.6f}, {lon:.6f}"
            coordinates_for_background = (lat, lon)
            log.info(f"[Checkin] Received coordinates: {coordinates_str}")

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

            # Do geocoding in background to avoid blocking the response
            location_name = None
            if coordinates_for_background:
                location_name = reverse_geocode_sync(coordinates_for_background[0], coordinates_for_background[1])
                if location_name:
                    log.info(f"[Checkin] Reverse geocoded to: {location_name}")

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

        # For group trips, also include participant friend contacts
        if trip.is_group_trip:
            participant_friend_contacts = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT DISTINCT friend_user_id FROM participant_trip_contacts
                    WHERE trip_id = :trip_id AND friend_user_id IS NOT NULL
                    """
                ),
                {"trip_id": trip.id}
            ).fetchall()
            existing_friend_ids = set(friend_user_ids)
            for pfc in participant_friend_contacts:
                if pfc.friend_user_id not in existing_friend_ids:
                    friend_user_ids.append(pfc.friend_user_id)
                    existing_friend_ids.add(pfc.friend_user_id)
            log.info(f"[Checkin] Added {len(participant_friend_contacts)} participant friend contacts")

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

        # For group trips, send refresh push to all participants so they see updated check-in count
        if is_group and is_group.is_group_trip:
            all_participant_ids = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT user_id FROM trip_participants
                    WHERE trip_id = :trip_id AND status = 'accepted'
                    """
                ),
                {"trip_id": trip.id}
            ).fetchall()

            if all_participant_ids:
                trip_id_for_refresh = trip.id

                def send_refresh_pushes():
                    for p in all_participant_ids:
                        asyncio.run(send_data_refresh_push(p.user_id, "trip", trip_id_for_refresh))

                background_tasks.add_task(send_refresh_pushes)
                log.info(f"[Checkin] Scheduled refresh pushes for {len(all_participant_ids)} participants")

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
                       t.timezone, t.location_text, t.notify_self, t.is_group_trip,
                       a.name as activity_name
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

        # Fetch all contact emails (owner + participants for group trips)
        contacts_for_email = _get_all_trip_email_contacts(connection, trip)

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

        # For group trips, also include participant friend contacts
        if trip.is_group_trip:
            participant_friend_contacts = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT DISTINCT friend_user_id FROM participant_trip_contacts
                    WHERE trip_id = :trip_id AND friend_user_id IS NOT NULL
                    """
                ),
                {"trip_id": trip.id}
            ).fetchall()
            existing_friend_ids = set(friend_user_ids)
            for pfc in participant_friend_contacts:
                if pfc.friend_user_id not in existing_friend_ids:
                    friend_user_ids.append(pfc.friend_user_id)
                    existing_friend_ids.add(pfc.friend_user_id)
            log.info(f"[Checkout] Added {len(participant_friend_contacts)} participant friend contacts")

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

        # For group trips, notify all other accepted participants
        if trip.is_group_trip:
            group_participants = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT user_id FROM trip_participants
                    WHERE trip_id = :trip_id AND user_id != :owner_id AND status = 'accepted'
                    """
                ),
                {"trip_id": trip.id, "owner_id": trip.user_id}
            ).fetchall()
            participant_ids = [p.user_id for p in group_participants]

            if participant_ids:
                trip_title_for_participants = trip.title
                owner_name_for_participants = user_name
                trip_id_for_participants = trip.id

                def send_participant_completion_push():
                    for pid in participant_ids:
                        asyncio.run(send_trip_completed_push(
                            participant_user_id=pid,
                            completer_name=owner_name_for_participants,
                            trip_title=trip_title_for_participants,
                            trip_id=trip_id_for_participants
                        ))
                        # Also send refresh push so their UI updates immediately
                        asyncio.run(send_data_refresh_push(pid, "trip", trip_id_for_participants))

                background_tasks.add_task(send_participant_completion_push)
                log.info(f"[Checkout] Scheduled completion push and refresh to {len(participant_ids)} group trip participants")

        return CheckinResponse(
            ok=True,
            message=f"Successfully completed '{trip.title}' - you're safe!"
        )
