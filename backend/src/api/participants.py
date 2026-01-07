"""Group trip participant management endpoints"""
import asyncio
import json
import logging
import math
from datetime import UTC, datetime
from typing import Optional

import sqlalchemy
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src import database as db
from src.api import auth
from src.services.geocoding import reverse_geocode_sync
from src.services.notifications import (
    send_checkin_update_emails,
    send_checkout_vote_push,
    send_data_refresh_push,
    send_friend_checkin_push,
    send_participant_checkin_push,
    send_participant_left_push,
    send_trip_completed_by_vote_push,
    send_trip_invitation_accepted_push,
    send_trip_invitation_declined_push,
    send_trip_invitation_push,
)

log = logging.getLogger(__name__)


# ==================== Pydantic Schemas ====================

class GroupSettings(BaseModel):
    """Settings for group trip behavior, configurable by trip owner."""
    checkout_mode: str = "anyone"  # "anyone" | "vote" | "owner_only"
    vote_threshold: float = 0.5  # For vote mode: percentage needed (0.0-1.0)
    allow_participant_invites: bool = False  # Can participants invite others?
    share_locations_between_participants: bool = True  # Can participants see each other's locations?


class ParticipantInviteRequest(BaseModel):
    """Request to invite friends to a group trip."""
    friend_user_ids: list[int]  # List of friend user IDs to invite


class AcceptInvitationRequest(BaseModel):
    """Request to accept a group trip invitation with safety contacts and notification settings."""
    safety_contact_ids: list[int] = []  # Email contact IDs (from contacts table)
    safety_friend_ids: list[int] = []   # Friend user IDs (from users table)
    # Personal notification settings (optional, defaults applied if not provided)
    checkin_interval_min: int = 30  # How often to send check-in reminders (minutes)
    notify_start_hour: int | None = None  # Quiet hours start (0-23), None = no quiet hours
    notify_end_hour: int | None = None  # Quiet hours end (0-23), None = no quiet hours


class ParticipantResponse(BaseModel):
    """Response model for a trip participant."""
    id: int
    user_id: int
    role: str  # 'owner' or 'participant'
    status: str  # 'invited', 'accepted', 'declined', 'left'
    invited_at: str
    invited_by: int | None
    joined_at: str | None
    left_at: str | None
    last_checkin_at: str | None
    last_lat: float | None
    last_lon: float | None
    # User info
    user_name: str | None = None
    user_email: str | None = None
    profile_photo_url: str | None = None


class ParticipantListResponse(BaseModel):
    """Response model for listing participants."""
    participants: list[ParticipantResponse]
    checkout_votes: int  # Number of checkout votes cast
    checkout_votes_needed: int  # Number needed to trigger checkout (if vote mode)
    group_settings: GroupSettings
    user_has_voted: bool = False  # Whether the current user has voted


class CheckoutVoteResponse(BaseModel):
    """Response for checkout vote action."""
    ok: bool
    message: str
    votes_cast: int
    votes_needed: int
    trip_completed: bool
    user_has_voted: bool = False  # Whether the current user has a vote


class CheckinResponse(BaseModel):
    """Response for check-in action."""
    ok: bool
    message: str


class ParticipantLocationResponse(BaseModel):
    """Location data for a participant."""
    user_id: int
    user_name: str | None
    last_checkin_at: str | None
    last_lat: float | None
    last_lon: float | None
    live_lat: float | None = None
    live_lon: float | None = None
    live_timestamp: str | None = None


# ==================== Helper Functions ====================

def _is_friend(connection, user_id: int, friend_user_id: int) -> bool:
    """Check if two users are friends."""
    id1, id2 = min(user_id, friend_user_id), max(user_id, friend_user_id)
    result = connection.execute(
        sqlalchemy.text(
            """
            SELECT id FROM friendships
            WHERE user_id_1 = :id1 AND user_id_2 = :id2
            """
        ),
        {"id1": id1, "id2": id2}
    ).fetchone()
    return result is not None


def _get_trip_with_access(connection, trip_id: int, user_id: int):
    """Get trip if user has access (owner or accepted participant).

    Returns the trip row or None if no access.
    """
    # Check if user is owner
    trip = connection.execute(
        sqlalchemy.text(
            """
            SELECT id, user_id, is_group_trip, group_settings, status
            FROM trips
            WHERE id = :trip_id
            """
        ),
        {"trip_id": trip_id}
    ).fetchone()

    if not trip:
        return None

    # Owner always has access
    if trip.user_id == user_id:
        return trip

    # Check if user is an accepted participant
    participant = connection.execute(
        sqlalchemy.text(
            """
            SELECT id FROM trip_participants
            WHERE trip_id = :trip_id AND user_id = :user_id AND status = 'accepted'
            """
        ),
        {"trip_id": trip_id, "user_id": user_id}
    ).fetchone()

    if participant:
        return trip

    return None


def _is_trip_owner(connection, trip_id: int, user_id: int) -> bool:
    """Check if user is the trip owner."""
    trip = connection.execute(
        sqlalchemy.text("SELECT user_id FROM trips WHERE id = :trip_id"),
        {"trip_id": trip_id}
    ).fetchone()
    return trip is not None and trip.user_id == user_id


def parse_group_settings(settings_json) -> GroupSettings:
    """Parse group settings from JSON.

    This function is used across multiple modules (participants.py, trips.py, scheduler.py)
    to consistently parse group_settings from the database.

    Args:
        settings_json: Either None, a dict, or a JSON string

    Returns:
        GroupSettings object with parsed settings or defaults
    """
    if settings_json is None:
        return GroupSettings()
    try:
        if isinstance(settings_json, dict):
            return GroupSettings(**settings_json)
        return GroupSettings(**json.loads(settings_json))
    except Exception as e:
        log.warning(f"Failed to parse group_settings: {e}")
        return GroupSettings()


# Backwards compatibility alias
_parse_group_settings = parse_group_settings


def _to_iso8601(dt) -> str | None:
    """Convert datetime to ISO8601 string."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    if isinstance(dt, str):
        return dt
    return str(dt)


# ==================== Router ====================

router = APIRouter(
    prefix="/api/v1/trips",
    tags=["participants"],
    dependencies=[Depends(auth.get_current_user_id)]
)


@router.post("/{trip_id}/participants", response_model=list[ParticipantResponse])
def invite_participants(
    trip_id: int,
    body: ParticipantInviteRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Invite friends to join a group trip.

    Only the trip owner (or participants if allowed by settings) can invite others.
    The invited friends must be in the inviter's friends list.
    """
    log.info(f"[Participants] Inviting {len(body.friend_user_ids)} friends to trip {trip_id}")

    with db.engine.begin() as connection:
        # Get trip and verify access
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, user_id, is_group_trip, group_settings, status
                FROM trips
                WHERE id = :trip_id
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()

        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found")

        is_owner = trip.user_id == user_id
        settings = _parse_group_settings(trip.group_settings)

        # Check permission to invite
        if not is_owner:
            # Check if user is an accepted participant
            participant = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id FROM trip_participants
                    WHERE trip_id = :trip_id AND user_id = :user_id AND status = 'accepted'
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id}
            ).fetchone()

            if not participant:
                raise HTTPException(status_code=403, detail="You are not part of this trip")

            if not settings.allow_participant_invites:
                raise HTTPException(
                    status_code=403,
                    detail="Only the trip owner can invite participants"
                )

        # If this is the first invite and trip isn't marked as group trip, mark it
        if not trip.is_group_trip:
            connection.execute(
                sqlalchemy.text(
                    """
                    UPDATE trips
                    SET is_group_trip = TRUE, group_settings = :settings
                    WHERE id = :trip_id
                    """
                ),
                {"trip_id": trip_id, "settings": json.dumps(settings.model_dump())}
            )

            # Add owner as a participant with 'owner' role
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                    VALUES (:trip_id, :user_id, 'owner', 'accepted', :now, :user_id)
                    ON CONFLICT (trip_id, user_id) DO NOTHING
                    """
                ),
                {"trip_id": trip_id, "user_id": trip.user_id, "now": datetime.now(UTC).isoformat()}
            )

        # Validate all friend IDs
        for friend_id in body.friend_user_ids:
            if not _is_friend(connection, user_id, friend_id):
                raise HTTPException(
                    status_code=400,
                    detail=f"User {friend_id} is not in your friends list"
                )

        now = datetime.now(UTC)
        now_iso = now.isoformat()
        # Invitations expire in 7 days by default
        from datetime import timedelta
        expires_at = (now + timedelta(days=7)).isoformat()
        invited_participants = []

        for friend_id in body.friend_user_ids:
            # Check if already a participant
            existing = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id, status FROM trip_participants
                    WHERE trip_id = :trip_id AND user_id = :friend_id
                    """
                ),
                {"trip_id": trip_id, "friend_id": friend_id}
            ).fetchone()

            if existing:
                if existing.status in ('invited', 'accepted'):
                    log.info(f"[Participants] User {friend_id} already a participant")
                    continue
                elif existing.status in ('declined', 'left', 'expired'):
                    # Re-invite
                    connection.execute(
                        sqlalchemy.text(
                            """
                            UPDATE trip_participants
                            SET status = 'invited', invited_at = :now, invited_by = :invited_by,
                                invitation_expires_at = :expires_at, left_at = NULL
                            WHERE trip_id = :trip_id AND user_id = :friend_id
                            """
                        ),
                        {"trip_id": trip_id, "friend_id": friend_id, "now": now_iso, "invited_by": user_id, "expires_at": expires_at}
                    )
            else:
                # Insert new participant
                connection.execute(
                    sqlalchemy.text(
                        """
                        INSERT INTO trip_participants (trip_id, user_id, role, status, invited_at, invited_by, invitation_expires_at)
                        VALUES (:trip_id, :friend_id, 'participant', 'invited', :now, :invited_by, :expires_at)
                        """
                    ),
                    {"trip_id": trip_id, "friend_id": friend_id, "now": now_iso, "invited_by": user_id, "expires_at": expires_at}
                )

            invited_participants.append(friend_id)

        # Fetch all participants with user info
        participants = connection.execute(
            sqlalchemy.text(
                """
                SELECT p.*, u.first_name, u.last_name, u.email, u.profile_photo_url
                FROM trip_participants p
                JOIN users u ON p.user_id = u.id
                WHERE p.trip_id = :trip_id
                ORDER BY p.role DESC, p.invited_at
                """
            ),
            {"trip_id": trip_id}
        ).fetchall()

        # Get inviter name and trip title for notifications
        inviter = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        inviter_name = f"{inviter.first_name} {inviter.last_name}".strip() if inviter else "Someone"

        trip_info = connection.execute(
            sqlalchemy.text("SELECT title FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        ).fetchone()
        trip_title = trip_info.title if trip_info else "a trip"

        # Send push notifications to invited friends
        if invited_participants:
            def send_invites_sync():
                for friend_id in invited_participants:
                    asyncio.run(send_trip_invitation_push(
                        invited_user_id=friend_id,
                        inviter_name=inviter_name,
                        trip_title=trip_title,
                        trip_id=trip_id
                    ))

            background_tasks.add_task(send_invites_sync)
            log.info(f"[Participants] Scheduled invitation push for {len(invited_participants)} friends")

        return [
            ParticipantResponse(
                id=p.id,
                user_id=p.user_id,
                role=p.role,
                status=p.status,
                invited_at=_to_iso8601(p.invited_at) or "",
                invited_by=p.invited_by,
                joined_at=_to_iso8601(p.joined_at),
                left_at=_to_iso8601(p.left_at),
                last_checkin_at=_to_iso8601(p.last_checkin_at),
                last_lat=p.last_lat,
                last_lon=p.last_lon,
                user_name=f"{p.first_name} {p.last_name}".strip() or None,
                user_email=p.email,
                profile_photo_url=p.profile_photo_url
            )
            for p in participants
        ]


@router.get("/{trip_id}/participants", response_model=ParticipantListResponse)
def get_participants(
    trip_id: int,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Get all participants for a group trip."""
    with db.engine.begin() as connection:
        trip = _get_trip_with_access(connection, trip_id, user_id)

        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found or access denied")

        settings = _parse_group_settings(trip.group_settings)

        # Fetch participants with user info
        participants = connection.execute(
            sqlalchemy.text(
                """
                SELECT p.*, u.first_name, u.last_name, u.email, u.profile_photo_url
                FROM trip_participants p
                JOIN users u ON p.user_id = u.id
                WHERE p.trip_id = :trip_id
                ORDER BY p.role DESC, p.joined_at NULLS LAST, p.invited_at
                """
            ),
            {"trip_id": trip_id}
        ).fetchall()

        # Count checkout votes
        votes = connection.execute(
            sqlalchemy.text(
                "SELECT COUNT(*) as count FROM checkout_votes WHERE trip_id = :trip_id"
            ),
            {"trip_id": trip_id}
        ).fetchone()
        vote_count = votes.count if votes else 0

        # Check if current user has voted
        user_vote = connection.execute(
            sqlalchemy.text(
                "SELECT id FROM checkout_votes WHERE trip_id = :trip_id AND user_id = :user_id"
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()
        has_voted = user_vote is not None

        # Calculate votes needed (use ceiling to ensure threshold is met)
        # e.g., 3 participants * 50% = 1.5 -> 2 votes needed
        accepted_count = sum(1 for p in participants if p.status == 'accepted')
        votes_needed = max(1, math.ceil(accepted_count * settings.vote_threshold)) if settings.checkout_mode == "vote" else 0

        return ParticipantListResponse(
            participants=[
                ParticipantResponse(
                    id=p.id,
                    user_id=p.user_id,
                    role=p.role,
                    status=p.status,
                    invited_at=_to_iso8601(p.invited_at) or "",
                    invited_by=p.invited_by,
                    joined_at=_to_iso8601(p.joined_at),
                    left_at=_to_iso8601(p.left_at),
                    last_checkin_at=_to_iso8601(p.last_checkin_at),
                    last_lat=p.last_lat,
                    last_lon=p.last_lon,
                    user_name=f"{p.first_name} {p.last_name}".strip() or None,
                    user_email=p.email,
                    profile_photo_url=p.profile_photo_url
                )
                for p in participants
            ],
            checkout_votes=vote_count,
            checkout_votes_needed=votes_needed,
            group_settings=settings,
            user_has_voted=has_voted
        )


@router.post("/{trip_id}/participants/accept")
def accept_invitation(
    trip_id: int,
    request: AcceptInvitationRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Accept an invitation to join a group trip with safety contacts."""
    log.info(f"[ACCEPT] User {user_id} accepting trip {trip_id} with contacts={request.safety_contact_ids}, friends={request.safety_friend_ids}")

    # Validate total safety contacts (email + friends)
    total_contacts = len(request.safety_contact_ids) + len(request.safety_friend_ids)
    if total_contacts == 0:
        raise HTTPException(
            status_code=400,
            detail="At least one safety contact is required to join a group trip"
        )
    if total_contacts > 3:
        raise HTTPException(
            status_code=400,
            detail="Maximum of 3 safety contacts allowed"
        )

    with db.engine.begin() as connection:
        # Verify all email contacts belong to this user
        if request.safety_contact_ids:
            placeholders = ", ".join([f":contact_id_{i}" for i in range(len(request.safety_contact_ids))])
            params = {"user_id": user_id}
            for i, cid in enumerate(request.safety_contact_ids):
                params[f"contact_id_{i}"] = cid

            contact_count = connection.execute(
                sqlalchemy.text(
                    f"""
                    SELECT COUNT(*) FROM contacts
                    WHERE id IN ({placeholders}) AND user_id = :user_id
                    """
                ),
                params
            ).scalar()

            if contact_count != len(request.safety_contact_ids):
                raise HTTPException(
                    status_code=400,
                    detail="One or more contacts do not belong to you"
                )

        # Verify all friend IDs are actually friends
        if request.safety_friend_ids:
            for friend_id in request.safety_friend_ids:
                id1, id2 = min(user_id, friend_id), max(user_id, friend_id)
                is_friend = connection.execute(
                    sqlalchemy.text(
                        "SELECT 1 FROM friends WHERE user_id_1 = :id1 AND user_id_2 = :id2"
                    ),
                    {"id1": id1, "id2": id2}
                ).fetchone()
                if not is_friend:
                    raise HTTPException(
                        status_code=400,
                        detail=f"User {friend_id} is not your friend"
                    )

        # Check if user has a pending invitation
        participant = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, status FROM trip_participants
                WHERE trip_id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not participant:
            log.warning(f"[ACCEPT] No invitation found for trip {trip_id}, user {user_id}")
            raise HTTPException(status_code=404, detail="No invitation found for this trip")

        log.info(f"[ACCEPT] Found participant record: trip={trip_id}, user={user_id}, current_status='{participant.status}'")

        if participant.status == 'accepted':
            log.info(f"[ACCEPT] Already accepted for trip {trip_id}, user {user_id}")
            return {"ok": True, "message": "Already accepted"}

        # Allow accepting from 'invited' or 'declined' status (re-accepting after decline)
        if participant.status not in ('invited', 'declined'):
            log.warning(f"[ACCEPT] Cannot accept - invalid status '{participant.status}' for trip {trip_id}, user {user_id}")
            raise HTTPException(
                status_code=400,
                detail=f"Cannot accept invitation with status '{participant.status}'"
            )

        # Accept the invitation and store personal notification settings
        now = datetime.now(UTC).isoformat()
        log.info(f"[ACCEPT] Updating status to 'accepted' for trip {trip_id}, user {user_id}")
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trip_participants
                SET status = 'accepted',
                    joined_at = :now,
                    checkin_interval_min = :checkin_interval,
                    notify_start_hour = :notify_start,
                    notify_end_hour = :notify_end
                WHERE trip_id = :trip_id AND user_id = :user_id
                """
            ),
            {
                "trip_id": trip_id,
                "user_id": user_id,
                "now": now,
                "checkin_interval": request.checkin_interval_min,
                "notify_start": request.notify_start_hour,
                "notify_end": request.notify_end_hour
            }
        )
        log.info(f"[ACCEPT] Status updated successfully for trip {trip_id}, user {user_id}")

        # Clear any existing contacts (in case of re-acceptance)
        connection.execute(
            sqlalchemy.text(
                "DELETE FROM participant_trip_contacts WHERE trip_id = :trip_id AND participant_user_id = :user_id"
            ),
            {"trip_id": trip_id, "user_id": user_id}
        )

        # Store participant's safety contacts (email contacts first, then friends)
        position = 1
        for contact_id in request.safety_contact_ids:
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO participant_trip_contacts (trip_id, participant_user_id, contact_id, position)
                    VALUES (:trip_id, :user_id, :contact_id, :position)
                    """
                ),
                {
                    "trip_id": trip_id,
                    "user_id": user_id,
                    "contact_id": contact_id,
                    "position": position
                }
            )
            position += 1

        # Store friend contacts
        for friend_id in request.safety_friend_ids:
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO participant_trip_contacts (trip_id, participant_user_id, friend_user_id, position)
                    VALUES (:trip_id, :user_id, :friend_user_id, :position)
                    """
                ),
                {
                    "trip_id": trip_id,
                    "user_id": user_id,
                    "friend_user_id": friend_id,
                    "position": position
                }
            )
            position += 1

        # Get trip owner and trip title for notification
        trip = connection.execute(
            sqlalchemy.text("SELECT user_id, title FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        ).fetchone()

        # Get accepter's name
        accepter = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        accepter_name = f"{accepter.first_name} {accepter.last_name}".strip() if accepter else "Someone"

        # Send push notification to trip owner
        if trip and trip.user_id != user_id:
            owner_id = trip.user_id
            trip_title = trip.title
            def send_accepted_push():
                asyncio.run(send_trip_invitation_accepted_push(
                    owner_user_id=owner_id,
                    accepter_name=accepter_name,
                    trip_title=trip_title,
                    trip_id=trip_id
                ))

            background_tasks.add_task(send_accepted_push)

        # Send data refresh push to all other accepted participants
        other_participants = connection.execute(
            sqlalchemy.text(
                """
                SELECT user_id FROM trip_participants
                WHERE trip_id = :trip_id AND user_id != :user_id AND status = 'accepted'
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchall()

        for participant in other_participants:
            def send_refresh(uid=participant.user_id):
                asyncio.run(send_data_refresh_push(uid, "trip", trip_id))
            background_tasks.add_task(send_refresh)

        return {"ok": True, "message": "Invitation accepted"}


@router.post("/{trip_id}/participants/decline")
def decline_invitation(
    trip_id: int,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Decline an invitation to join a group trip."""
    log.info(f"[DECLINE] User {user_id} declining trip {trip_id}")
    with db.engine.begin() as connection:
        # Check if user has a pending invitation
        participant = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, status FROM trip_participants
                WHERE trip_id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not participant:
            raise HTTPException(status_code=404, detail="No invitation found for this trip")

        if participant.status == 'declined':
            return {"ok": True, "message": "Already declined"}

        if participant.status not in ('invited',):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot decline invitation with status '{participant.status}'"
            )

        # Decline the invitation
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trip_participants
                SET status = 'declined'
                WHERE trip_id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        )

        # Get trip owner and trip title for notification
        trip = connection.execute(
            sqlalchemy.text("SELECT user_id, title FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        ).fetchone()

        # Get decliner's name
        decliner = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        decliner_name = f"{decliner.first_name} {decliner.last_name}".strip() if decliner else "Someone"

        # Send push notification to trip owner
        if trip and trip.user_id != user_id:
            owner_id = trip.user_id
            trip_title = trip.title
            def send_declined_push():
                asyncio.run(send_trip_invitation_declined_push(
                    owner_user_id=owner_id,
                    decliner_name=decliner_name,
                    trip_title=trip_title,
                    trip_id=trip_id
                ))

            background_tasks.add_task(send_declined_push)

        return {"ok": True, "message": "Invitation declined"}


@router.post("/{trip_id}/participants/leave")
def leave_trip(
    trip_id: int,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Leave a group trip."""
    with db.engine.begin() as connection:
        # Check if user is a participant
        participant = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, status, role FROM trip_participants
                WHERE trip_id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not participant:
            raise HTTPException(status_code=404, detail="You are not part of this trip")

        if participant.role == 'owner':
            raise HTTPException(
                status_code=400,
                detail="Trip owner cannot leave. Delete the trip instead."
            )

        if participant.status == 'left':
            return {"ok": True, "message": "Already left"}

        # Leave the trip
        now = datetime.now(UTC).isoformat()
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trip_participants
                SET status = 'left', left_at = :now
                WHERE trip_id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id, "now": now}
        )

        # Remove any checkout votes by this user
        connection.execute(
            sqlalchemy.text(
                "DELETE FROM checkout_votes WHERE trip_id = :trip_id AND user_id = :user_id"
            ),
            {"trip_id": trip_id, "user_id": user_id}
        )

        # Get trip owner and trip title for notification
        trip = connection.execute(
            sqlalchemy.text("SELECT user_id, title FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        ).fetchone()

        # Get leaver's name
        leaver = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        leaver_name = f"{leaver.first_name} {leaver.last_name}".strip() if leaver else "Someone"

        # Send push notification to trip owner
        if trip:
            owner_id = trip.user_id
            trip_title = trip.title
            def send_left_push():
                asyncio.run(send_participant_left_push(
                    owner_user_id=owner_id,
                    leaver_name=leaver_name,
                    trip_title=trip_title,
                    trip_id=trip_id
                ))

            background_tasks.add_task(send_left_push)

        # Send data refresh push to all other accepted participants
        other_participants = connection.execute(
            sqlalchemy.text(
                """
                SELECT user_id FROM trip_participants
                WHERE trip_id = :trip_id AND user_id != :user_id AND status = 'accepted'
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchall()

        for participant in other_participants:
            def send_refresh(uid=participant.user_id):
                asyncio.run(send_data_refresh_push(uid, "trip", trip_id))
            background_tasks.add_task(send_refresh)

        return {"ok": True, "message": "Left the trip"}


@router.delete("/{trip_id}/participants/{target_user_id}")
def remove_participant(
    trip_id: int,
    target_user_id: int,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Remove a participant from a group trip (owner only)."""
    with db.engine.begin() as connection:
        # Verify caller is trip owner
        if not _is_trip_owner(connection, trip_id, user_id):
            raise HTTPException(status_code=403, detail="Only the trip owner can remove participants")

        if target_user_id == user_id:
            raise HTTPException(status_code=400, detail="Cannot remove yourself. Delete the trip instead.")

        # Check if target is a participant
        participant = connection.execute(
            sqlalchemy.text(
                """
                SELECT id FROM trip_participants
                WHERE trip_id = :trip_id AND user_id = :target_user_id
                """
            ),
            {"trip_id": trip_id, "target_user_id": target_user_id}
        ).fetchone()

        if not participant:
            raise HTTPException(status_code=404, detail="Participant not found")

        # Remove the participant
        connection.execute(
            sqlalchemy.text(
                "DELETE FROM trip_participants WHERE trip_id = :trip_id AND user_id = :target_user_id"
            ),
            {"trip_id": trip_id, "target_user_id": target_user_id}
        )

        # Remove any checkout votes by this user
        connection.execute(
            sqlalchemy.text(
                "DELETE FROM checkout_votes WHERE trip_id = :trip_id AND user_id = :target_user_id"
            ),
            {"trip_id": trip_id, "target_user_id": target_user_id}
        )

        return {"ok": True, "message": "Participant removed"}


@router.get("/{trip_id}/locations", response_model=list[ParticipantLocationResponse])
def get_participant_locations(
    trip_id: int,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Get location data for all participants in a group trip."""
    with db.engine.begin() as connection:
        trip = _get_trip_with_access(connection, trip_id, user_id)

        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found or access denied")

        settings = _parse_group_settings(trip.group_settings)

        # If location sharing between participants is disabled and user is not owner
        if not settings.share_locations_between_participants and trip.user_id != user_id:
            # Only return the user's own location
            participant = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT p.user_id, p.last_checkin_at, p.last_lat, p.last_lon,
                           u.first_name, u.last_name
                    FROM trip_participants p
                    JOIN users u ON p.user_id = u.id
                    WHERE p.trip_id = :trip_id AND p.user_id = :user_id AND p.status = 'accepted'
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id}
            ).fetchone()

            if not participant:
                return []

            return [
                ParticipantLocationResponse(
                    user_id=participant.user_id,
                    user_name=f"{participant.first_name} {participant.last_name}".strip() or None,
                    last_checkin_at=_to_iso8601(participant.last_checkin_at),
                    last_lat=participant.last_lat,
                    last_lon=participant.last_lon
                )
            ]

        # Get all accepted participants with their locations
        participants = connection.execute(
            sqlalchemy.text(
                """
                SELECT p.user_id, p.last_checkin_at, p.last_lat, p.last_lon,
                       u.first_name, u.last_name
                FROM trip_participants p
                JOIN users u ON p.user_id = u.id
                WHERE p.trip_id = :trip_id AND p.status = 'accepted'
                """
            ),
            {"trip_id": trip_id}
        ).fetchall()

        # Also get live locations if available
        live_locations = {}
        live_rows = connection.execute(
            sqlalchemy.text(
                """
                SELECT DISTINCT ON (user_id) user_id, latitude, longitude, timestamp
                FROM live_locations
                WHERE trip_id = :trip_id
                ORDER BY user_id, timestamp DESC
                """
            ),
            {"trip_id": trip_id}
        ).fetchall()

        for row in live_rows:
            live_locations[row.user_id] = {
                "lat": row.latitude,
                "lon": row.longitude,
                "timestamp": _to_iso8601(row.timestamp)
            }

        return [
            ParticipantLocationResponse(
                user_id=p.user_id,
                user_name=f"{p.first_name} {p.last_name}".strip() or None,
                last_checkin_at=_to_iso8601(p.last_checkin_at),
                last_lat=p.last_lat,
                last_lon=p.last_lon,
                live_lat=live_locations.get(p.user_id, {}).get("lat"),
                live_lon=live_locations.get(p.user_id, {}).get("lon"),
                live_timestamp=live_locations.get(p.user_id, {}).get("timestamp")
            )
            for p in participants
        ]


@router.post("/{trip_id}/checkin", response_model=CheckinResponse)
def participant_checkin(
    trip_id: int,
    background_tasks: BackgroundTasks,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Check in to a group trip as a participant.

    This authenticated endpoint allows group trip participants to check in,
    updating their location and the trip's check-in status.
    """
    with db.engine.begin() as connection:
        # Get trip details with activity name for notifications
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.status, t.is_group_trip,
                       t.timezone, t.location_text, t.eta,
                       a.name as activity_name
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.id = :trip_id
                AND t.status IN ('active', 'overdue', 'overdue_notified')
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found or not active"
            )

        # Check if user is an accepted participant (or owner)
        participant = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, role, status FROM trip_participants
                WHERE trip_id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        # Allow owner even if not in trip_participants (for non-group trips)
        is_owner = trip.user_id == user_id

        if not is_owner:
            if not participant:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not a participant in this trip"
                )
            if participant.status != 'accepted':
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Cannot check in with participant status '{participant.status}'"
                )

        now = datetime.now(UTC)
        now_iso = now.isoformat()

        # Create check-in event
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO events (user_id, trip_id, what, timestamp, lat, lon)
                VALUES (:user_id, :trip_id, 'checkin', :timestamp, :lat, :lon)
                RETURNING id
                """
            ),
            {"user_id": user_id, "trip_id": trip_id, "timestamp": now_iso, "lat": lat, "lon": lon}
        )
        event_row = result.fetchone()
        event_id = event_row[0] if event_row else None

        # Update trip's last check-in and reset status
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trips
                SET last_checkin = :event_id,
                    status = 'active',
                    last_grace_warning = NULL,
                    last_checkin_reminder = :now,
                    notified_eta_transition = false,
                    notified_grace_transition = false
                WHERE id = :trip_id
                """
            ),
            {"event_id": event_id, "trip_id": trip_id, "now": now_iso}
        )

        # Update participant's check-in location (if participant record exists)
        if participant or is_owner:
            connection.execute(
                sqlalchemy.text(
                    """
                    UPDATE trip_participants
                    SET last_checkin_at = :now, last_lat = :lat, last_lon = :lon
                    WHERE trip_id = :trip_id AND user_id = :user_id
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id, "now": now_iso, "lat": lat, "lon": lon}
            )

        # Get checker's name for notifications
        checker = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        checker_name = f"{checker.first_name} {checker.last_name}".strip() if checker else "Someone"
        if not checker_name:
            checker_name = "A participant"

        # Get all other accepted participants for notifications (if group trip)
        if trip.is_group_trip:
            other_participants = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT user_id FROM trip_participants
                    WHERE trip_id = :trip_id AND user_id != :checker_id AND status = 'accepted'
                    """
                ),
                {"trip_id": trip_id, "checker_id": user_id}
            ).fetchall()

            other_participant_ids = [p.user_id for p in other_participants]

            if other_participant_ids:
                trip_title = trip.title
                coordinates = (lat, lon) if lat is not None and lon is not None else None

                def send_checkin_notifications():
                    for pid in other_participant_ids:
                        asyncio.run(send_participant_checkin_push(
                            participant_user_id=pid,
                            checker_name=checker_name,
                            trip_title=trip_title,
                            trip_id=trip_id,
                            coordinates=coordinates
                        ))

                background_tasks.add_task(send_checkin_notifications)
                log.info(f"[Participants] Scheduled check-in notifications for {len(other_participant_ids)} participants")

        # Get checking-in participant's email safety contacts for this trip
        participant_email_contacts = connection.execute(
            sqlalchemy.text(
                """
                SELECT c.id, c.name, c.email
                FROM participant_trip_contacts ptc
                JOIN contacts c ON ptc.contact_id = c.id
                WHERE ptc.trip_id = :trip_id
                AND ptc.participant_user_id = :user_id
                AND c.email IS NOT NULL
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchall()

        contacts_for_email = [dict(c._mapping) for c in participant_email_contacts]

        # Also get trip owner's email contacts so they're notified of participant check-ins
        owner_email_contacts = connection.execute(
            sqlalchemy.text(
                """
                SELECT c.id, c.name, c.email
                FROM contacts c
                JOIN trips t ON (c.id = t.contact1 OR c.id = t.contact2 OR c.id = t.contact3)
                WHERE t.id = :trip_id AND c.email IS NOT NULL
                """
            ),
            {"trip_id": trip_id}
        ).fetchall()

        # Deduplicate by email
        existing_emails = {c['email'].lower() for c in contacts_for_email if c.get('email')}
        for oc in owner_email_contacts:
            if oc.email and oc.email.lower() not in existing_emails:
                contacts_for_email.append(dict(oc._mapping))
                existing_emails.add(oc.email.lower())

        # Get checking-in participant's friend safety contacts
        participant_friend_contacts = connection.execute(
            sqlalchemy.text(
                """
                SELECT friend_user_id FROM participant_trip_contacts
                WHERE trip_id = :trip_id
                AND participant_user_id = :user_id
                AND friend_user_id IS NOT NULL
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchall()

        friend_user_ids = [f.friend_user_id for f in participant_friend_contacts]

        # Also get trip owner's friend contacts
        owner_friend_contacts = connection.execute(
            sqlalchemy.text(
                """
                SELECT friend_user_id FROM trip_safety_contacts
                WHERE trip_id = :trip_id AND friend_user_id IS NOT NULL
                """
            ),
            {"trip_id": trip_id}
        ).fetchall()

        existing_friend_ids = set(friend_user_ids)
        for ofc in owner_friend_contacts:
            if ofc.friend_user_id not in existing_friend_ids:
                friend_user_ids.append(ofc.friend_user_id)
                existing_friend_ids.add(ofc.friend_user_id)

        # Prepare location info for notifications (geocoding moved to background)
        coordinates_str = f"{lat:.6f}, {lon:.6f}" if lat is not None and lon is not None else None
        coordinates_for_background = (lat, lon) if lat is not None and lon is not None else None

        # Send check-in emails to participant's contacts (in background, including geocoding)
        if contacts_for_email:
            trip_data = {"title": trip.title, "location_text": trip.location_text, "eta": trip.eta}
            activity_name = trip.activity_name
            user_timezone = trip.timezone
            checker_name_for_email = checker_name

            def send_contact_emails():
                # Do geocoding in background to avoid blocking the response
                location_name = None
                if coordinates_for_background:
                    location_name = reverse_geocode_sync(coordinates_for_background[0], coordinates_for_background[1])
                    if location_name:
                        log.info(f"[Participants] Reverse geocoded to: {location_name}")

                asyncio.run(send_checkin_update_emails(
                    trip=trip_data,
                    contacts=contacts_for_email,
                    user_name=checker_name_for_email,
                    activity_name=activity_name,
                    user_timezone=user_timezone,
                    coordinates=coordinates_str,
                    location_name=location_name
                ))

            background_tasks.add_task(send_contact_emails)
            log.info(f"[Participants] Scheduled check-in emails for {len(contacts_for_email)} contacts")

        # Send friend check-in pushes (in background, including geocoding)
        if friend_user_ids:
            trip_title_for_friends = trip.title
            checker_name_for_friends = checker_name

            def send_friend_pushes():
                # Do geocoding in background to avoid blocking the response
                location_name = None
                if coordinates_for_background:
                    location_name = reverse_geocode_sync(coordinates_for_background[0], coordinates_for_background[1])

                for friend_id in friend_user_ids:
                    asyncio.run(send_friend_checkin_push(
                        friend_user_id=friend_id,
                        user_name=checker_name_for_friends,
                        trip_title=trip_title_for_friends,
                        location_name=location_name,
                        coordinates=coordinates_for_background
                    ))

            background_tasks.add_task(send_friend_pushes)
            log.info(f"[Participants] Scheduled check-in pushes for {len(friend_user_ids)} friend contacts")

        # Send refresh pushes to owner and other participants so they see updated check-in count
        if trip.is_group_trip:
            refresh_user_ids = []

            # Add owner if checker is not the owner
            if not is_owner:
                refresh_user_ids.append(trip.user_id)

            # Add all other accepted participants
            other_participants_for_refresh = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT user_id FROM trip_participants
                    WHERE trip_id = :trip_id AND user_id != :checker_id AND status = 'accepted'
                    """
                ),
                {"trip_id": trip_id, "checker_id": user_id}
            ).fetchall()
            refresh_user_ids.extend([p.user_id for p in other_participants_for_refresh])

            if refresh_user_ids:
                trip_id_for_refresh = trip_id

                def send_refresh_pushes():
                    for uid in refresh_user_ids:
                        asyncio.run(send_data_refresh_push(uid, "trip", trip_id_for_refresh))

                background_tasks.add_task(send_refresh_pushes)
                log.info(f"[Participants] Scheduled refresh pushes for {len(refresh_user_ids)} users")

        log.info(f"[Participants] User {user_id} checked in to group trip {trip_id}")

        return CheckinResponse(
            ok=True,
            message=f"Successfully checked in to '{trip.title}'"
        )


@router.post("/{trip_id}/checkout/vote", response_model=CheckoutVoteResponse)
def vote_checkout(
    trip_id: int,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Cast a vote to checkout (end) the group trip.

    In 'vote' mode, the trip is completed when the vote threshold is reached.
    In 'anyone' mode, this immediately completes the trip.
    In 'owner_only' mode, only the owner can complete the trip.

    Uses SELECT FOR UPDATE to prevent race conditions when multiple
    participants vote simultaneously.
    """
    with db.engine.begin() as connection:
        # Lock the trip row to prevent race conditions
        # This ensures only one vote can complete the trip at a time
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, user_id, status, is_group_trip, group_settings
                FROM trips
                WHERE id = :trip_id
                FOR UPDATE
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()

        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found")

        # Check if user has access (owner or accepted participant)
        is_owner = trip.user_id == user_id
        if not is_owner:
            participant = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id FROM trip_participants
                    WHERE trip_id = :trip_id AND user_id = :user_id AND status = 'accepted'
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id}
            ).fetchone()
            if not participant:
                raise HTTPException(status_code=403, detail="Access denied")

        # Handle idempotency: if trip is already completed, return success
        if trip.status == 'completed':
            return CheckoutVoteResponse(
                ok=True,
                message="Trip already completed",
                votes_cast=0,
                votes_needed=0,
                trip_completed=True
            )

        if trip.status not in ('active', 'overdue', 'overdue_notified'):
            raise HTTPException(status_code=400, detail="Trip is not active")

        settings = _parse_group_settings(trip.group_settings)
        is_owner = trip.user_id == user_id

        # Check permission based on checkout mode
        if settings.checkout_mode == "owner_only" and not is_owner:
            raise HTTPException(
                status_code=403,
                detail="Only the trip owner can end this trip"
            )

        # Count accepted participants
        accepted_count_result = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*) as count FROM trip_participants
                WHERE trip_id = :trip_id AND status = 'accepted'
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()
        accepted_count = accepted_count_result.count if accepted_count_result else 1

        # Calculate votes needed
        if settings.checkout_mode == "vote":
            # Use ceiling to ensure threshold is met (e.g., 3 participants * 50% = 1.5 -> 2 votes needed)
            votes_needed = max(1, math.ceil(accepted_count * settings.vote_threshold))
        else:
            # "anyone" mode - 1 vote is enough
            votes_needed = 1

        # Check if user already voted
        existing_vote = connection.execute(
            sqlalchemy.text(
                "SELECT id FROM checkout_votes WHERE trip_id = :trip_id AND user_id = :user_id"
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not existing_vote:
            # Record the vote
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO checkout_votes (trip_id, user_id, voted_at)
                    VALUES (:trip_id, :user_id, :now)
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id, "now": datetime.now(UTC).isoformat()}
            )

        # Count total votes (only from currently accepted participants)
        vote_count_result = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*) as count FROM checkout_votes cv
                JOIN trip_participants tp ON cv.trip_id = tp.trip_id AND cv.user_id = tp.user_id
                WHERE cv.trip_id = :trip_id AND tp.status = 'accepted'
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()
        vote_count = vote_count_result.count if vote_count_result else 0

        # Check if threshold is reached
        trip_completed = vote_count >= votes_needed

        # Get voter name and trip title for notifications
        voter = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        voter_name = f"{voter.first_name} {voter.last_name}".strip() if voter else "Someone"

        trip_info = connection.execute(
            sqlalchemy.text("SELECT title FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        ).fetchone()
        trip_title = trip_info.title if trip_info else "the trip"

        # Get all accepted participant IDs for notifications
        all_participants = connection.execute(
            sqlalchemy.text(
                """
                SELECT user_id FROM trip_participants
                WHERE trip_id = :trip_id AND status = 'accepted' AND user_id != :voter_id
                """
            ),
            {"trip_id": trip_id, "voter_id": user_id}
        ).fetchall()
        other_participant_ids = [p.user_id for p in all_participants]

        if trip_completed:
            # Complete the trip
            connection.execute(
                sqlalchemy.text(
                    """
                    UPDATE trips
                    SET status = 'completed', completed_at = :now
                    WHERE id = :trip_id
                    """
                ),
                {"trip_id": trip_id, "now": datetime.now(UTC).isoformat()}
            )

            # Clear checkout votes
            connection.execute(
                sqlalchemy.text("DELETE FROM checkout_votes WHERE trip_id = :trip_id"),
                {"trip_id": trip_id}
            )

            # Send completion notifications to all participants
            if other_participant_ids:
                def send_completed_pushes():
                    for pid in other_participant_ids:
                        asyncio.run(send_trip_completed_by_vote_push(
                            participant_user_id=pid,
                            trip_title=trip_title,
                            trip_id=trip_id
                        ))
                        # Also send refresh push to update UI
                        asyncio.run(send_data_refresh_push(pid, "trip", trip_id))

                background_tasks.add_task(send_completed_pushes)

            log.info(f"[Participants] Group trip {trip_id} completed via checkout vote")

            return CheckoutVoteResponse(
                ok=True,
                message="Trip completed!",
                votes_cast=vote_count,
                votes_needed=votes_needed,
                trip_completed=True,
                user_has_voted=True
            )

        # Trip not completed yet - send vote notification to other participants
        if other_participant_ids and settings.checkout_mode == "vote":
            def send_vote_pushes():
                for pid in other_participant_ids:
                    asyncio.run(send_checkout_vote_push(
                        participant_user_id=pid,
                        voter_name=voter_name,
                        trip_title=trip_title,
                        trip_id=trip_id,
                        votes_count=vote_count,
                        votes_needed=votes_needed
                    ))
                    # Also send refresh push to update vote count in UI
                    asyncio.run(send_data_refresh_push(pid, "trip", trip_id))

            background_tasks.add_task(send_vote_pushes)

        return CheckoutVoteResponse(
            ok=True,
            message=f"Vote recorded ({vote_count}/{votes_needed})",
            votes_cast=vote_count,
            votes_needed=votes_needed,
            trip_completed=False,
            user_has_voted=True
        )


@router.delete("/{trip_id}/checkout/vote", response_model=CheckoutVoteResponse)
def remove_vote(
    trip_id: int,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Remove a previously cast checkout vote.

    Allows a participant to change their mind about ending the trip.
    """
    with db.engine.begin() as connection:
        # Verify trip exists and user is participant
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, user_id, status, title, group_settings, is_group_trip
                FROM trips
                WHERE id = :trip_id
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()

        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found")

        if trip.status not in ('active', 'overdue', 'overdue_notified'):
            raise HTTPException(status_code=400, detail="Trip is not active")

        # Parse group settings
        settings = _parse_group_settings(trip.group_settings)

        # Count accepted participants + owner
        accepted_count_result = connection.execute(
            sqlalchemy.text(
                """
                SELECT COUNT(*) as count FROM trip_participants
                WHERE trip_id = :trip_id AND status = 'accepted'
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()
        accepted_count = (accepted_count_result.count if accepted_count_result else 0) + 1  # +1 for owner

        # Calculate votes needed based on mode
        if settings.checkout_mode == "vote":
            votes_needed = max(1, math.ceil(accepted_count * settings.vote_threshold))
        else:
            votes_needed = 1

        # Check if user has a vote to remove
        existing_vote = connection.execute(
            sqlalchemy.text(
                "SELECT id FROM checkout_votes WHERE trip_id = :trip_id AND user_id = :user_id"
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not existing_vote:
            # No vote to remove - return current vote count
            vote_count = connection.execute(
                sqlalchemy.text("SELECT COUNT(*) FROM checkout_votes WHERE trip_id = :trip_id"),
                {"trip_id": trip_id}
            ).scalar() or 0

            return CheckoutVoteResponse(
                ok=True,
                message="No vote to remove",
                votes_cast=vote_count,
                votes_needed=votes_needed,
                trip_completed=False,
                user_has_voted=False
            )

        # Remove the vote
        connection.execute(
            sqlalchemy.text("DELETE FROM checkout_votes WHERE trip_id = :trip_id AND user_id = :user_id"),
            {"trip_id": trip_id, "user_id": user_id}
        )

        # Get updated vote count
        vote_count = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) FROM checkout_votes WHERE trip_id = :trip_id"),
            {"trip_id": trip_id}
        ).scalar() or 0

        log.info(f"[Participants] User {user_id} removed vote from trip {trip_id} ({vote_count}/{votes_needed})")

        # Send refresh push to other participants
        other_participant_ids = connection.execute(
            sqlalchemy.text(
                """
                SELECT user_id FROM trip_participants
                WHERE trip_id = :trip_id AND user_id != :user_id AND status = 'accepted'
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchall()

        # Also include owner if not the current user
        if trip.user_id != user_id:
            other_participant_ids = list(other_participant_ids) + [type('obj', (object,), {'user_id': trip.user_id})]

        if other_participant_ids:
            trip_id_for_refresh = trip_id

            def send_refresh_pushes():
                for p in other_participant_ids:
                    asyncio.run(send_data_refresh_push(p.user_id, "trip", trip_id_for_refresh))

            background_tasks.add_task(send_refresh_pushes)

        return CheckoutVoteResponse(
            ok=True,
            message=f"Vote removed ({vote_count}/{votes_needed})",
            votes_cast=vote_count,
            votes_needed=votes_needed,
            trip_completed=False,
            user_has_voted=False
        )


# ==================== Pending Invitations ====================

@router.get("/invitations/pending", response_model=list[dict])
def get_pending_invitations(
    user_id: int = Depends(auth.get_current_user_id)
):
    """Get all pending trip invitations for the current user.

    Filters out expired invitations (where invitation_expires_at is in the past).
    """
    now = datetime.now(UTC).isoformat()
    with db.engine.begin() as connection:
        invitations = connection.execute(
            sqlalchemy.text(
                """
                SELECT p.id, p.trip_id, p.invited_at, p.invited_by,
                       t.title as trip_title, t.start, t.eta, t.location_text,
                       a.name as activity_name, a.icon as activity_icon,
                       u.first_name as inviter_first_name, u.last_name as inviter_last_name
                FROM trip_participants p
                JOIN trips t ON p.trip_id = t.id
                JOIN activities a ON t.activity = a.id
                LEFT JOIN users u ON p.invited_by = u.id
                WHERE p.user_id = :user_id AND p.status = 'invited'
                AND (p.invitation_expires_at IS NULL OR p.invitation_expires_at > :now)
                ORDER BY p.invited_at DESC
                """
            ),
            {"user_id": user_id, "now": now}
        ).fetchall()

        result = []
        for inv in invitations:
            # Get all participant user IDs for this trip (to filter out from friend contacts)
            participants = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT user_id FROM trip_participants
                    WHERE trip_id = :trip_id
                    """
                ),
                {"trip_id": inv.trip_id}
            ).fetchall()
            participant_user_ids = [p.user_id for p in participants]

            result.append({
                "id": inv.id,
                "trip_id": inv.trip_id,
                "invited_at": _to_iso8601(inv.invited_at),
                "invited_by": inv.invited_by,
                "inviter_name": f"{inv.inviter_first_name} {inv.inviter_last_name}".strip() if inv.inviter_first_name else None,
                "trip_title": inv.trip_title,
                "trip_start": _to_iso8601(inv.start),
                "trip_eta": _to_iso8601(inv.eta),
                "trip_location": inv.location_text,
                "activity_name": inv.activity_name,
                "activity_icon": inv.activity_icon,
                "participant_user_ids": participant_user_ids
            })

        return result
