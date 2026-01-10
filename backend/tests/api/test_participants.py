"""Tests for group trip participants API endpoints"""
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
import sqlalchemy
from fastapi import BackgroundTasks, HTTPException

from src import database as db
from src.api.participants import (
    AcceptInvitationRequest,
    CheckinResponse,
    CheckoutVoteResponse,
    GroupSettings,
    ParticipantInviteRequest,
    ParticipantListResponse,
    ParticipantResponse,
    accept_invitation,
    decline_invitation,
    get_participant_locations,
    get_participants,
    get_pending_invitations,
    invite_participants,
    leave_trip,
    participant_checkin,
    remove_participant,
    vote_checkout,
)
from src.api.trips import TripCreate, TripResponse, create_trip, get_trips, get_active_trip


# ==================== Test Helpers ====================

def _create_test_user(connection, email: str, first_name: str = "Test", last_name: str = "User", premium: bool = True) -> int:
    """Create a test user and return their ID.

    Args:
        premium: If True (default), creates user with Homebound+ subscription.
                 Group trips require premium subscription.
    """
    # Clean up existing data first
    connection.execute(
        sqlalchemy.text("DELETE FROM trip_participants WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
        {"email": email}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM checkout_votes WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
        {"email": email}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM friend_invites WHERE inviter_id IN (SELECT id FROM users WHERE email = :email)"),
        {"email": email}
    )
    connection.execute(
        sqlalchemy.text(
            """DELETE FROM friendships WHERE user_id_1 IN (SELECT id FROM users WHERE email = :email)
               OR user_id_2 IN (SELECT id FROM users WHERE email = :email)"""
        ),
        {"email": email}
    )
    connection.execute(
        sqlalchemy.text("UPDATE trips SET last_checkin = NULL WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
        {"email": email}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM events WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
        {"email": email}
    )
    # Delete events that reference trips owned by this user
    connection.execute(
        sqlalchemy.text("DELETE FROM events WHERE trip_id IN (SELECT id FROM trips WHERE user_id IN (SELECT id FROM users WHERE email = :email))"),
        {"email": email}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM trips WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
        {"email": email}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM contacts WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
        {"email": email}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM users WHERE email = :email"),
        {"email": email}
    )

    tier = "plus" if premium else "free"
    result = connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO users (email, first_name, last_name, age, created_at, subscription_tier)
            VALUES (:email, :first_name, :last_name, 30, :created_at, :tier)
            RETURNING id
            """
        ),
        {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "created_at": datetime.utcnow(),
            "tier": tier
        }
    )
    return result.fetchone()[0]


def _create_friendship(connection, user_id_1: int, user_id_2: int):
    """Create a friendship between two users."""
    # Ensure user_id_1 < user_id_2 for unique constraint
    if user_id_1 > user_id_2:
        user_id_1, user_id_2 = user_id_2, user_id_1
    connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO friendships (user_id_1, user_id_2, created_at)
            VALUES (:user_id_1, :user_id_2, :created_at)
            ON CONFLICT DO NOTHING
            """
        ),
        {"user_id_1": user_id_1, "user_id_2": user_id_2, "created_at": datetime.utcnow()}
    )


def _create_test_trip(connection, user_id: int, is_group_trip: bool = False) -> int:
    """Create a test trip and return its ID."""
    now = datetime.now(UTC)
    # Get hiking activity ID
    activity = connection.execute(
        sqlalchemy.text("SELECT id FROM activities WHERE name = 'Hiking' LIMIT 1")
    ).fetchone()
    activity_id = activity[0] if activity else 1

    group_settings = None
    if is_group_trip:
        group_settings = '{"checkout_mode": "anyone", "vote_threshold": 0.5, "allow_participant_invites": false, "share_locations_between_participants": true}'

    result = connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO trips (user_id, title, activity, start, eta, grace_min, status, is_group_trip, group_settings, checkin_token, checkout_token, location_text, gen_lat, gen_lon, has_separate_locations, notify_self, notified_eta_transition, notified_grace_transition, share_live_location)
            VALUES (:user_id, :title, :activity, :start, :eta, :grace_min, 'active', :is_group_trip, :group_settings, :checkin_token, :checkout_token, :location_text, :gen_lat, :gen_lon, false, false, false, false, false)
            RETURNING id
            """
        ),
        {
            "user_id": user_id,
            "title": "Test Group Trip",
            "activity": activity_id,
            "start": now.isoformat(),
            "eta": (now + timedelta(hours=2)).isoformat(),
            "grace_min": 15,
            "is_group_trip": is_group_trip,
            "group_settings": group_settings,
            "checkin_token": "test_checkin_token",
            "checkout_token": "test_checkout_token",
            "location_text": "Test Location",
            "gen_lat": 37.7749,
            "gen_lon": -122.4194
        }
    )
    trip_id = result.fetchone()[0]

    # If group trip, add owner as participant
    if is_group_trip:
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'owner', 'accepted', :now, :user_id)
                """
            ),
            {"trip_id": trip_id, "user_id": user_id, "now": now.isoformat()}
        )

    return trip_id


def _cleanup_test_data(*user_ids):
    """Clean up test data for given user IDs."""
    with db.engine.begin() as connection:
        for user_id in user_ids:
            connection.execute(
                sqlalchemy.text("DELETE FROM checkout_votes WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM trip_participants WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM live_locations WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM friend_invites WHERE inviter_id = :user_id OR accepted_by = :user_id"),
                {"user_id": user_id}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM friendships WHERE user_id_1 = :user_id OR user_id_2 = :user_id"),
                {"user_id": user_id}
            )
            connection.execute(
                sqlalchemy.text("UPDATE trips SET last_checkin = NULL WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM events WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            # Also delete events referencing user's trips by trip_id
            connection.execute(
                sqlalchemy.text("DELETE FROM events WHERE trip_id IN (SELECT id FROM trips WHERE user_id = :user_id)"),
                {"user_id": user_id}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM trips WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM contacts WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )


# ==================== Invite Participants Tests ====================

def test_invite_participants_success():
    """Test successfully inviting friends to a group trip."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        request = ParticipantInviteRequest(friend_user_ids=[friend_id])

        result = invite_participants(trip_id, request, background_tasks, user_id=owner_id)

        assert isinstance(result, list)
        # Should return all participants (owner + invited friend)
        assert len(result) >= 1

        # Verify friend was invited
        with db.engine.begin() as connection:
            participant = connection.execute(
                sqlalchemy.text(
                    "SELECT * FROM trip_participants WHERE trip_id = :trip_id AND user_id = :user_id"
                ),
                {"trip_id": trip_id, "user_id": friend_id}
            ).fetchone()
            assert participant is not None
            assert participant.status == "invited"
            assert participant.role == "participant"
            assert participant.invitation_expires_at is not None

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_invite_non_friend_fails():
    """Test that inviting a non-friend fails."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner2@test.com", "Owner", "User")
        stranger_id = _create_test_user(connection, "stranger@test.com", "Stranger", "User")
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        request = ParticipantInviteRequest(friend_user_ids=[stranger_id])

        with pytest.raises(HTTPException) as exc_info:
            invite_participants(trip_id, request, background_tasks, user_id=owner_id)

        assert exc_info.value.status_code == 400
        assert "not in your friends list" in exc_info.value.detail

    finally:
        _cleanup_test_data(owner_id, stranger_id)


def test_invite_already_invited_skipped():
    """Test that inviting an already-invited user is skipped."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner3@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend3@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        request = ParticipantInviteRequest(friend_user_ids=[friend_id])

        # First invite
        invite_participants(trip_id, request, background_tasks, user_id=owner_id)

        # Second invite should not error (just skip)
        result = invite_participants(trip_id, request, background_tasks, user_id=owner_id)
        assert isinstance(result, list)

    finally:
        _cleanup_test_data(owner_id, friend_id)


# ==================== Accept/Decline Invitation Tests ====================

def test_accept_invitation():
    """Test accepting a trip invitation."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner4@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend4@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        # Create invitation
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, invited_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'invited', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

        # Create a safety contact for the friend
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO contacts (user_id, name, email)
                VALUES (:user_id, :name, :email)
                RETURNING id
                """
            ),
            {
                "user_id": friend_id,
                "name": "Test Contact",
                "email": "testcontact4@test.com"
            }
        )
        contact_id = result.fetchone()[0]

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        request = AcceptInvitationRequest(
            safety_contact_ids=[contact_id],
            checkin_interval_min=30
        )
        result = accept_invitation(trip_id, request, background_tasks, user_id=friend_id)

        assert result["ok"] is True
        assert "accepted" in result["message"].lower() or "joined" in result["message"].lower()

        # Verify status updated
        with db.engine.begin() as connection:
            participant = connection.execute(
                sqlalchemy.text(
                    "SELECT * FROM trip_participants WHERE trip_id = :trip_id AND user_id = :user_id"
                ),
                {"trip_id": trip_id, "user_id": friend_id}
            ).fetchone()
            assert participant.status == "accepted"
            assert participant.joined_at is not None

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_decline_invitation():
    """Test declining a trip invitation."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner5@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend5@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, invited_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'invited', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        result = decline_invitation(trip_id, background_tasks, user_id=friend_id)

        assert result["ok"] is True

        with db.engine.begin() as connection:
            participant = connection.execute(
                sqlalchemy.text(
                    "SELECT * FROM trip_participants WHERE trip_id = :trip_id AND user_id = :user_id"
                ),
                {"trip_id": trip_id, "user_id": friend_id}
            ).fetchone()
            assert participant.status == "declined"

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_accept_without_invitation_fails():
    """Test that accepting without a pending invitation fails."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner6@test.com", "Owner", "User")
        stranger_id = _create_test_user(connection, "stranger6@test.com", "Stranger", "User")
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        # Create a safety contact for the stranger so request is valid
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO contacts (user_id, name, email)
                VALUES (:user_id, :name, :email)
                RETURNING id
                """
            ),
            {
                "user_id": stranger_id,
                "name": "Test Contact",
                "email": "testcontact6@test.com"
            }
        )
        contact_id = result.fetchone()[0]

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        request = AcceptInvitationRequest(
            safety_contact_ids=[contact_id],
            checkin_interval_min=30
        )

        with pytest.raises(HTTPException) as exc_info:
            accept_invitation(trip_id, request, background_tasks, user_id=stranger_id)

        assert exc_info.value.status_code in [403, 404]

    finally:
        _cleanup_test_data(owner_id, stranger_id)


# ==================== Leave Trip Tests ====================

def test_leave_trip():
    """Test participant leaving a group trip."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner7@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend7@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        # Add friend as accepted participant
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'accepted', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        result = leave_trip(trip_id, background_tasks, user_id=friend_id)

        assert result["ok"] is True

        with db.engine.begin() as connection:
            participant = connection.execute(
                sqlalchemy.text(
                    "SELECT * FROM trip_participants WHERE trip_id = :trip_id AND user_id = :user_id"
                ),
                {"trip_id": trip_id, "user_id": friend_id}
            ).fetchone()
            assert participant.status == "left"
            assert participant.left_at is not None

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_owner_cannot_leave():
    """Test that the trip owner cannot leave their own trip."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner8@test.com", "Owner", "User")
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)

        with pytest.raises(HTTPException) as exc_info:
            leave_trip(trip_id, background_tasks, user_id=owner_id)

        assert exc_info.value.status_code == 400  # 400 Bad Request for owner trying to leave

    finally:
        _cleanup_test_data(owner_id)


# ==================== Remove Participant Tests ====================

def test_owner_remove_participant():
    """Test owner removing a participant from the trip."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner9@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend9@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'accepted', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        result = remove_participant(trip_id, friend_id, user_id=owner_id)

        assert result["ok"] is True

        with db.engine.begin() as connection:
            participant = connection.execute(
                sqlalchemy.text(
                    "SELECT * FROM trip_participants WHERE trip_id = :trip_id AND user_id = :user_id"
                ),
                {"trip_id": trip_id, "user_id": friend_id}
            ).fetchone()
            assert participant is None  # Should be deleted

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_non_owner_cannot_remove():
    """Test that non-owners cannot remove participants."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner10@test.com", "Owner", "User")
        friend1_id = _create_test_user(connection, "friend10a@test.com", "Friend1", "User")
        friend2_id = _create_test_user(connection, "friend10b@test.com", "Friend2", "User")
        _create_friendship(connection, owner_id, friend1_id)
        _create_friendship(connection, owner_id, friend2_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        # Add both friends as participants
        for fid in [friend1_id, friend2_id]:
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                    VALUES (:trip_id, :user_id, 'participant', 'accepted', :now, :owner_id)
                    """
                ),
                {"trip_id": trip_id, "user_id": fid, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
            )

    try:
        # Friend1 tries to remove Friend2 - should fail
        with pytest.raises(HTTPException) as exc_info:
            remove_participant(trip_id, friend2_id, user_id=friend1_id)

        assert exc_info.value.status_code == 403

    finally:
        _cleanup_test_data(owner_id, friend1_id, friend2_id)


# ==================== Authenticated Check-in Tests ====================

def test_participant_checkin_success():
    """Test participant checking in to a group trip."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner11@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend11@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'accepted', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        result = participant_checkin(trip_id, background_tasks, lat=37.7749, lon=-122.4194, user_id=friend_id)

        assert isinstance(result, CheckinResponse)
        assert result.ok is True

        # Verify participant location was updated
        with db.engine.begin() as connection:
            participant = connection.execute(
                sqlalchemy.text(
                    "SELECT * FROM trip_participants WHERE trip_id = :trip_id AND user_id = :user_id"
                ),
                {"trip_id": trip_id, "user_id": friend_id}
            ).fetchone()
            assert participant.last_checkin_at is not None
            assert participant.last_lat == 37.7749
            assert participant.last_lon == -122.4194

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_checkin_not_participant_fails():
    """Test that non-participants cannot check in."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner12@test.com", "Owner", "User")
        stranger_id = _create_test_user(connection, "stranger12@test.com", "Stranger", "User")
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)

        with pytest.raises(HTTPException) as exc_info:
            participant_checkin(trip_id, background_tasks, lat=37.7749, lon=-122.4194, user_id=stranger_id)

        assert exc_info.value.status_code == 403

    finally:
        _cleanup_test_data(owner_id, stranger_id)


def test_checkin_invited_not_accepted_fails():
    """Test that invited but not accepted participants cannot check in."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner13@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend13@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        # Create invitation but don't accept
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, invited_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'invited', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)

        with pytest.raises(HTTPException) as exc_info:
            participant_checkin(trip_id, background_tasks, lat=37.7749, lon=-122.4194, user_id=friend_id)

        assert exc_info.value.status_code == 403
        assert "invited" in exc_info.value.detail.lower()

    finally:
        _cleanup_test_data(owner_id, friend_id)


# ==================== Vote Checkout Tests ====================

def test_vote_checkout_anyone_mode():
    """Test vote checkout in 'anyone' mode - single vote completes trip."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner14@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend14@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'accepted', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        result = vote_checkout(trip_id, background_tasks, user_id=friend_id)

        assert isinstance(result, CheckoutVoteResponse)
        assert result.ok is True
        assert result.trip_completed is True

        # Verify trip is completed
        with db.engine.begin() as connection:
            trip = connection.execute(
                sqlalchemy.text("SELECT status FROM trips WHERE id = :trip_id"),
                {"trip_id": trip_id}
            ).fetchone()
            assert trip.status == "completed"

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_vote_checkout_vote_mode():
    """Test vote checkout in 'vote' mode - needs threshold."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner15@test.com", "Owner", "User")
        friend1_id = _create_test_user(connection, "friend15a@test.com", "Friend1", "User")
        friend2_id = _create_test_user(connection, "friend15b@test.com", "Friend2", "User")
        _create_friendship(connection, owner_id, friend1_id)
        _create_friendship(connection, owner_id, friend2_id)

        # Create trip with vote mode (50% threshold)
        now = datetime.now(UTC)
        activity = connection.execute(
            sqlalchemy.text("SELECT id FROM activities WHERE name = 'Hiking' LIMIT 1")
        ).fetchone()
        activity_id = activity[0] if activity else 1

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (user_id, title, activity, start, eta, grace_min, status, is_group_trip, group_settings, checkin_token, checkout_token, location_text, gen_lat, gen_lon, has_separate_locations, notify_self, notified_eta_transition, notified_grace_transition, share_live_location)
                VALUES (:user_id, :title, :activity, :start, :eta, :grace_min, 'active', true, :group_settings, :checkin_token, :checkout_token, :location_text, :gen_lat, :gen_lon, false, false, false, false, false)
                RETURNING id
                """
            ),
            {
                "user_id": owner_id,
                "title": "Vote Mode Trip",
                "activity": activity_id,
                "start": now.isoformat(),
                "eta": (now + timedelta(hours=2)).isoformat(),
                "grace_min": 15,
                "group_settings": '{"checkout_mode": "vote", "vote_threshold": 0.5}',
                "checkin_token": "test_token",
                "checkout_token": "test_checkout",
                "location_text": "Test Location",
                "gen_lat": 37.7749,
                "gen_lon": -122.4194
            }
        )
        trip_id = result.fetchone()[0]

        # Add all participants
        for user_id, role in [(owner_id, 'owner'), (friend1_id, 'participant'), (friend2_id, 'participant')]:
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                    VALUES (:trip_id, :user_id, :role, 'accepted', :now, :owner_id)
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id, "role": role, "now": now.isoformat(), "owner_id": owner_id}
            )

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)

        # First vote - should not complete (1/3 < 50%)
        result1 = vote_checkout(trip_id, background_tasks, user_id=friend1_id)
        assert result1.trip_completed is False
        assert result1.votes_cast == 1

        # Second vote - should complete (2/3 >= 50%)
        result2 = vote_checkout(trip_id, background_tasks, user_id=friend2_id)
        assert result2.trip_completed is True

    finally:
        _cleanup_test_data(owner_id, friend1_id, friend2_id)


def test_vote_checkout_owner_only_mode():
    """Test vote checkout in 'owner_only' mode - only owner can complete."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner16@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend16@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)

        now = datetime.now(UTC)
        activity = connection.execute(
            sqlalchemy.text("SELECT id FROM activities WHERE name = 'Hiking' LIMIT 1")
        ).fetchone()
        activity_id = activity[0] if activity else 1

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (user_id, title, activity, start, eta, grace_min, status, is_group_trip, group_settings, checkin_token, checkout_token, location_text, gen_lat, gen_lon, has_separate_locations, notify_self, notified_eta_transition, notified_grace_transition, share_live_location)
                VALUES (:user_id, :title, :activity, :start, :eta, :grace_min, 'active', true, :group_settings, :checkin_token, :checkout_token, :location_text, :gen_lat, :gen_lon, false, false, false, false, false)
                RETURNING id
                """
            ),
            {
                "user_id": owner_id,
                "title": "Owner Only Trip",
                "activity": activity_id,
                "start": now.isoformat(),
                "eta": (now + timedelta(hours=2)).isoformat(),
                "grace_min": 15,
                "group_settings": '{"checkout_mode": "owner_only"}',
                "checkin_token": "test_token",
                "checkout_token": "test_checkout",
                "location_text": "Test Location",
                "gen_lat": 37.7749,
                "gen_lon": -122.4194
            }
        )
        trip_id = result.fetchone()[0]

        for user_id, role in [(owner_id, 'owner'), (friend_id, 'participant')]:
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                    VALUES (:trip_id, :user_id, :role, 'accepted', :now, :owner_id)
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id, "role": role, "now": now.isoformat(), "owner_id": owner_id}
            )

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)

        # Non-owner vote should fail
        with pytest.raises(HTTPException) as exc_info:
            vote_checkout(trip_id, background_tasks, user_id=friend_id)
        assert exc_info.value.status_code == 403

        # Owner vote should succeed
        result = vote_checkout(trip_id, background_tasks, user_id=owner_id)
        assert result.trip_completed is True

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_vote_idempotent_after_completion():
    """Test that voting after trip is completed returns success (idempotent)."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner17@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend17@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'accepted', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)

        # First vote completes trip
        vote_checkout(trip_id, background_tasks, user_id=friend_id)

        # Second vote should still return success (idempotent)
        result = vote_checkout(trip_id, background_tasks, user_id=owner_id)
        assert result.ok is True
        assert result.trip_completed is True

    finally:
        _cleanup_test_data(owner_id, friend_id)


# ==================== Pending Invitations Tests ====================

def test_get_pending_invitations():
    """Test getting pending invitations for a user."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner18@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend18@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        now = datetime.now(UTC)
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, invited_at, invited_by, invitation_expires_at)
                VALUES (:trip_id, :user_id, 'participant', 'invited', :now, :owner_id, :expires)
                """
            ),
            {
                "trip_id": trip_id,
                "user_id": friend_id,
                "now": now.isoformat(),
                "owner_id": owner_id,
                "expires": (now + timedelta(days=7)).isoformat()
            }
        )

    try:
        result = get_pending_invitations(user_id=friend_id)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["trip_id"] == trip_id
        assert result[0]["trip_title"] == "Test Group Trip"

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_expired_invitations_filtered():
    """Test that expired invitations are filtered out."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner19@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend19@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        # Create expired invitation
        now = datetime.now(UTC)
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, invited_at, invited_by, invitation_expires_at)
                VALUES (:trip_id, :user_id, 'participant', 'invited', :now, :owner_id, :expires)
                """
            ),
            {
                "trip_id": trip_id,
                "user_id": friend_id,
                "now": now.isoformat(),
                "owner_id": owner_id,
                "expires": (now - timedelta(days=1)).isoformat()  # Expired yesterday
            }
        )

    try:
        result = get_pending_invitations(user_id=friend_id)

        assert isinstance(result, list)
        assert len(result) == 0  # Should be empty

    finally:
        _cleanup_test_data(owner_id, friend_id)


# ==================== Get Participants Tests ====================

def test_get_participants():
    """Test getting all participants for a group trip."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner20@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend20@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'accepted', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        result = get_participants(trip_id, user_id=owner_id)

        assert isinstance(result, ParticipantListResponse)
        assert len(result.participants) == 2  # Owner + friend

        # Check that we have both owner and participant
        roles = {p.role for p in result.participants}
        assert "owner" in roles
        assert "participant" in roles

    finally:
        _cleanup_test_data(owner_id, friend_id)


# ==================== Get Participant Locations Tests ====================

def test_get_participant_locations():
    """Test getting participant locations for a group trip."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner21@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend21@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        now = datetime.now(UTC)
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by, last_checkin_at, last_lat, last_lon)
                VALUES (:trip_id, :user_id, 'participant', 'accepted', :now, :owner_id, :now, 37.7749, -122.4194)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": now.isoformat(), "owner_id": owner_id}
        )

    try:
        result = get_participant_locations(trip_id, user_id=owner_id)

        assert isinstance(result, list)
        assert len(result) >= 1

        # Find friend's location
        friend_loc = next((l for l in result if l.user_id == friend_id), None)
        assert friend_loc is not None
        assert friend_loc.last_lat == 37.7749
        assert friend_loc.last_lon == -122.4194

    finally:
        _cleanup_test_data(owner_id, friend_id)


# ==================== Edge Case Tests ====================

def test_reinvite_after_decline():
    """Test re-inviting a user who previously declined."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner22@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend22@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        # Create declined invitation
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, invited_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'declined', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        request = ParticipantInviteRequest(friend_user_ids=[friend_id])

        # Re-invite should work
        result = invite_participants(trip_id, request, background_tasks, user_id=owner_id)
        assert isinstance(result, list)

        # Verify status is now 'invited'
        with db.engine.begin() as connection:
            participant = connection.execute(
                sqlalchemy.text(
                    "SELECT * FROM trip_participants WHERE trip_id = :trip_id AND user_id = :user_id"
                ),
                {"trip_id": trip_id, "user_id": friend_id}
            ).fetchone()
            assert participant.status == "invited"

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_reinvite_after_left():
    """Test re-inviting a user who previously left."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner23@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend23@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, left_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'left', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        request = ParticipantInviteRequest(friend_user_ids=[friend_id])

        result = invite_participants(trip_id, request, background_tasks, user_id=owner_id)
        assert isinstance(result, list)

        with db.engine.begin() as connection:
            participant = connection.execute(
                sqlalchemy.text(
                    "SELECT * FROM trip_participants WHERE trip_id = :trip_id AND user_id = :user_id"
                ),
                {"trip_id": trip_id, "user_id": friend_id}
            ).fetchone()
            assert participant.status == "invited"
            assert participant.left_at is None  # Should be cleared

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_leave_clears_checkout_vote():
    """Test that leaving a trip clears the user's checkout vote."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner24@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend24@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)

        now = datetime.now(UTC)
        activity = connection.execute(
            sqlalchemy.text("SELECT id FROM activities WHERE name = 'Hiking' LIMIT 1")
        ).fetchone()
        activity_id = activity[0] if activity else 1

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (user_id, title, activity, start, eta, grace_min, status, is_group_trip, group_settings, checkin_token, checkout_token, location_text, gen_lat, gen_lon, has_separate_locations, notify_self, notified_eta_transition, notified_grace_transition, share_live_location)
                VALUES (:user_id, :title, :activity, :start, :eta, :grace_min, 'active', true, :group_settings, :checkin_token, :checkout_token, :location_text, :gen_lat, :gen_lon, false, false, false, false, false)
                RETURNING id
                """
            ),
            {
                "user_id": owner_id,
                "title": "Vote Test Trip",
                "activity": activity_id,
                "start": now.isoformat(),
                "eta": (now + timedelta(hours=2)).isoformat(),
                "grace_min": 15,
                "group_settings": '{"checkout_mode": "vote", "vote_threshold": 1.0}',  # 100% threshold
                "checkin_token": "test_token",
                "checkout_token": "test_checkout",
                "location_text": "Test Location",
                "gen_lat": 37.7749,
                "gen_lon": -122.4194
            }
        )
        trip_id = result.fetchone()[0]

        for user_id, role in [(owner_id, 'owner'), (friend_id, 'participant')]:
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                    VALUES (:trip_id, :user_id, :role, 'accepted', :now, :owner_id)
                    """
                ),
                {"trip_id": trip_id, "user_id": user_id, "role": role, "now": now.isoformat(), "owner_id": owner_id}
            )

        # Friend votes
        connection.execute(
            sqlalchemy.text(
                "INSERT INTO checkout_votes (trip_id, user_id, voted_at) VALUES (:trip_id, :user_id, :now)"
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": now.isoformat()}
        )

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)

        # Friend leaves
        leave_trip(trip_id, background_tasks, user_id=friend_id)

        # Verify vote was deleted
        with db.engine.begin() as connection:
            vote = connection.execute(
                sqlalchemy.text(
                    "SELECT * FROM checkout_votes WHERE trip_id = :trip_id AND user_id = :user_id"
                ),
                {"trip_id": trip_id, "user_id": friend_id}
            ).fetchone()
            assert vote is None

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_trip_not_found():
    """Test accessing a non-existent trip."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "user25@test.com", "User", "Test")

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)

        with pytest.raises(HTTPException) as exc_info:
            participant_checkin(99999, background_tasks, user_id=user_id)
        assert exc_info.value.status_code == 404

    finally:
        _cleanup_test_data(user_id)


def test_checkin_inactive_trip_fails():
    """Test that checking into an inactive trip fails."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner26@test.com", "Owner", "User")

        now = datetime.now(UTC)
        activity = connection.execute(
            sqlalchemy.text("SELECT id FROM activities WHERE name = 'Hiking' LIMIT 1")
        ).fetchone()
        activity_id = activity[0] if activity else 1

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (user_id, title, activity, start, eta, grace_min, status, is_group_trip, checkin_token, checkout_token, location_text, gen_lat, gen_lon, has_separate_locations, notify_self, notified_eta_transition, notified_grace_transition, share_live_location)
                VALUES (:user_id, :title, :activity, :start, :eta, :grace_min, 'completed', true, :checkin_token, :checkout_token, :location_text, :gen_lat, :gen_lon, false, false, false, false, false)
                RETURNING id
                """
            ),
            {
                "user_id": owner_id,
                "title": "Completed Trip",
                "activity": activity_id,
                "start": now.isoformat(),
                "eta": (now + timedelta(hours=2)).isoformat(),
                "grace_min": 15,
                "checkin_token": "test_token",
                "checkout_token": "test_checkout",
                "location_text": "Test Location",
                "gen_lat": 37.7749,
                "gen_lon": -122.4194
            }
        )
        trip_id = result.fetchone()[0]

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'owner', 'accepted', :now, :user_id)
                """
            ),
            {"trip_id": trip_id, "user_id": owner_id, "now": now.isoformat()}
        )

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)

        with pytest.raises(HTTPException) as exc_info:
            participant_checkin(trip_id, background_tasks, user_id=owner_id)
        assert exc_info.value.status_code == 404  # Trip not found (not active)

    finally:
        _cleanup_test_data(owner_id)


# ==================== Accept Invitation with Contacts Tests ====================

def test_accept_invitation_with_safety_contacts():
    """Test accepting an invitation with safety contacts and notification settings."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner27@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend27@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        # Create invitation
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, invited_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'invited', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

        # Create safety contacts for the friend
        contact_ids = []
        for i in range(2):
            result = connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO contacts (user_id, name, email)
                    VALUES (:user_id, :name, :email)
                    RETURNING id
                    """
                ),
                {
                    "user_id": friend_id,
                    "name": f"Contact {i}",
                    "email": f"contact{i}@test.com"
                }
            )
            contact_ids.append(result.fetchone()[0])

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        request = AcceptInvitationRequest(
            safety_contact_ids=contact_ids,
            checkin_interval_min=45,
            notify_start_hour=8,
            notify_end_hour=22
        )
        result = accept_invitation(trip_id, request, background_tasks, user_id=friend_id)

        assert result["ok"] is True

        # Verify participant was updated with notification settings
        with db.engine.begin() as connection:
            participant = connection.execute(
                sqlalchemy.text(
                    "SELECT * FROM trip_participants WHERE trip_id = :trip_id AND user_id = :user_id"
                ),
                {"trip_id": trip_id, "user_id": friend_id}
            ).fetchone()
            assert participant.status == "accepted"
            assert participant.joined_at is not None
            assert participant.checkin_interval_min == 45
            assert participant.notify_start_hour == 8
            assert participant.notify_end_hour == 22

            # Verify safety contacts were stored
            contacts = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT * FROM participant_trip_contacts
                    WHERE trip_id = :trip_id AND participant_user_id = :user_id
                    ORDER BY position
                    """
                ),
                {"trip_id": trip_id, "user_id": friend_id}
            ).fetchall()
            assert len(contacts) == 2
            assert contacts[0].contact_id == contact_ids[0]
            assert contacts[1].contact_id == contact_ids[1]

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_accept_invitation_requires_contacts():
    """Test that accepting invitation without safety contacts fails."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner28@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend28@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, invited_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'invited', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        request = AcceptInvitationRequest(
            safety_contact_ids=[],  # Empty contacts
            checkin_interval_min=30
        )

        with pytest.raises(HTTPException) as exc_info:
            accept_invitation(trip_id, request, background_tasks, user_id=friend_id)
        assert exc_info.value.status_code == 400
        assert "safety contact" in exc_info.value.detail.lower()

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_accept_invitation_max_three_contacts():
    """Test that accepting invitation with more than 3 contacts fails."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner29@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend29@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, invited_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'invited', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

        # Create 4 contacts
        contact_ids = []
        for i in range(4):
            result = connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO contacts (user_id, name, email)
                    VALUES (:user_id, :name, :email)
                    RETURNING id
                    """
                ),
                {
                    "user_id": friend_id,
                    "name": f"Contact {i}",
                    "email": f"contact29_{i}@test.com"
                }
            )
            contact_ids.append(result.fetchone()[0])

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        request = AcceptInvitationRequest(
            safety_contact_ids=contact_ids,  # 4 contacts - should fail
            checkin_interval_min=30
        )

        with pytest.raises(HTTPException) as exc_info:
            accept_invitation(trip_id, request, background_tasks, user_id=friend_id)
        assert exc_info.value.status_code == 400
        assert "3" in exc_info.value.detail  # Should mention max 3 contacts

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_accept_invitation_contacts_must_belong_to_user():
    """Test that contacts must belong to the accepting user."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner30@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend30@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, invited_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'invited', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

        # Create contact belonging to OWNER (not friend)
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO contacts (user_id, name, email)
                VALUES (:user_id, :name, :email)
                RETURNING id
                """
            ),
            {
                "user_id": owner_id,  # Contact belongs to owner, not friend
                "name": "Owner Contact",
                "email": "ownercontact@test.com"
            }
        )
        contact_id = result.fetchone()[0]

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)
        request = AcceptInvitationRequest(
            safety_contact_ids=[contact_id],  # This contact doesn't belong to friend
            checkin_interval_min=30
        )

        with pytest.raises(HTTPException) as exc_info:
            accept_invitation(trip_id, request, background_tasks, user_id=friend_id)
        assert exc_info.value.status_code == 400
        assert "do not belong to you" in exc_info.value.detail.lower()

    finally:
        _cleanup_test_data(owner_id, friend_id)


# ==================== Get Trips / Get Active Trip with Participants Tests ====================

def test_get_trips_includes_trips_as_participant():
    """Test that get_trips returns trips where user is an accepted participant."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner31@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend31@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        # Add friend as accepted participant
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'accepted', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        # Friend should see the trip in their trips list
        result = get_trips(user_id=friend_id)

        assert isinstance(result, list)
        assert len(result) >= 1

        # Find our trip
        trip_ids = [t.id for t in result]
        assert trip_id in trip_ids

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_get_trips_excludes_invited_trips():
    """Test that get_trips does NOT return trips where user is only invited (not accepted)."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner32@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend32@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        # Add friend as INVITED (not accepted) participant
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, invited_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'invited', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        # Friend should NOT see the trip in their trips list (only invited)
        result = get_trips(user_id=friend_id)

        trip_ids = [t.id for t in result]
        assert trip_id not in trip_ids

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_get_active_trip_includes_participant_trips():
    """Test that get_active_trip returns trips where user is an accepted participant."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner33@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend33@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        # Add friend as accepted participant
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'accepted', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        # Friend should see the trip as their active trip
        result = get_active_trip(user_id=friend_id)

        assert result is not None
        assert result.id == trip_id

    finally:
        _cleanup_test_data(owner_id, friend_id)


def test_get_active_trip_excludes_invited_participant():
    """Test that get_active_trip does NOT return trips where user is only invited."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner34@test.com", "Owner", "User")
        friend_id = _create_test_user(connection, "friend34@test.com", "Friend", "User")
        _create_friendship(connection, owner_id, friend_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True)

        # Add friend as INVITED (not accepted) participant
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, invited_at, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'invited', :now, :owner_id)
                """
            ),
            {"trip_id": trip_id, "user_id": friend_id, "now": datetime.now(UTC).isoformat(), "owner_id": owner_id}
        )

    try:
        # Friend should NOT see the trip as active (only invited, not accepted)
        result = get_active_trip(user_id=friend_id)

        # Should be None since friend has no accepted trips
        assert result is None

    finally:
        _cleanup_test_data(owner_id, friend_id)
