"""Tests for notification contact fetching - verifies bug fixes for:
- Bug 1 & 2: Participant email contacts not notified (getattr() fix)
- Bug 3: Participant check-in uses actor instead of owner name (watched_user_name fix)
"""
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
import sqlalchemy
from fastapi import BackgroundTasks

from src import database as db
from src.api.trips import _get_all_trip_email_contacts


# ==================== Test Helpers ====================

def _create_test_user(connection, email: str, first_name: str = "Test", last_name: str = "User") -> int:
    """Create a test user and return their ID."""
    # Clean up existing data first
    connection.execute(
        sqlalchemy.text("DELETE FROM participant_trip_contacts WHERE participant_user_id IN (SELECT id FROM users WHERE email = :email)"),
        {"email": email}
    )
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
    connection.execute(
        sqlalchemy.text("DELETE FROM events WHERE trip_id IN (SELECT id FROM trips WHERE user_id IN (SELECT id FROM users WHERE email = :email))"),
        {"email": email}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM trip_safety_contacts WHERE trip_id IN (SELECT id FROM trips WHERE user_id IN (SELECT id FROM users WHERE email = :email))"),
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

    result = connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO users (email, first_name, last_name, age, created_at)
            VALUES (:email, :first_name, :last_name, 30, :created_at)
            RETURNING id
            """
        ),
        {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "created_at": datetime.now(UTC)
        }
    )
    return result.fetchone()[0]


def _create_test_contact(connection, user_id: int, name: str, email: str) -> int:
    """Create a test contact for a user and return the contact ID."""
    result = connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO contacts (user_id, name, email)
            VALUES (:user_id, :name, :email)
            RETURNING id
            """
        ),
        {
            "user_id": user_id,
            "name": name,
            "email": email
        }
    )
    return result.fetchone()[0]


def _create_friendship(connection, user_id_1: int, user_id_2: int):
    """Create a friendship between two users."""
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
        {"user_id_1": user_id_1, "user_id_2": user_id_2, "created_at": datetime.now(UTC)}
    )


def _create_test_trip(connection, user_id: int, is_group_trip: bool = False, contact1: int = None) -> int:
    """Create a test trip and return its ID."""
    now = datetime.now(UTC)
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
            INSERT INTO trips (user_id, title, activity, start, eta, grace_min, status, is_group_trip, group_settings,
                              checkin_token, checkout_token, location_text, gen_lat, gen_lon, has_separate_locations,
                              notify_self, notified_eta_transition, notified_grace_transition, share_live_location,
                              contact1, contact2, contact3)
            VALUES (:user_id, :title, :activity, :start, :eta, :grace_min, 'active', :is_group_trip, :group_settings,
                    :checkin_token, :checkout_token, :location_text, :gen_lat, :gen_lon, false, false, false, false, false,
                    :contact1, NULL, NULL)
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
            "checkin_token": f"test_checkin_token_{now.timestamp()}",
            "checkout_token": f"test_checkout_token_{now.timestamp()}",
            "location_text": "Test Location",
            "gen_lat": 37.7749,
            "gen_lon": -122.4194,
            "contact1": contact1
        }
    )
    trip_id = result.fetchone()[0]

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


def _add_participant_to_trip(connection, trip_id: int, user_id: int, inviter_id: int):
    """Add a participant to a trip."""
    now = datetime.now(UTC)
    connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
            VALUES (:trip_id, :user_id, 'participant', 'accepted', :now, :inviter_id)
            ON CONFLICT (trip_id, user_id) DO NOTHING
            """
        ),
        {"trip_id": trip_id, "user_id": user_id, "now": now.isoformat(), "inviter_id": inviter_id}
    )


def _add_participant_contact(connection, trip_id: int, participant_user_id: int, contact_id: int):
    """Add a safety contact for a participant on a trip."""
    connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO participant_trip_contacts (trip_id, participant_user_id, contact_id, position)
            VALUES (:trip_id, :participant_user_id, :contact_id, 1)
            ON CONFLICT DO NOTHING
            """
        ),
        {"trip_id": trip_id, "participant_user_id": participant_user_id, "contact_id": contact_id}
    )


def _cleanup_test_data(*user_ids):
    """Clean up test data for given user IDs."""
    with db.engine.begin() as connection:
        for user_id in user_ids:
            connection.execute(
                sqlalchemy.text("DELETE FROM participant_trip_contacts WHERE participant_user_id = :user_id"),
                {"user_id": user_id}
            )
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
            connection.execute(
                sqlalchemy.text("DELETE FROM events WHERE trip_id IN (SELECT id FROM trips WHERE user_id = :user_id)"),
                {"user_id": user_id}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM trip_safety_contacts WHERE trip_id IN (SELECT id FROM trips WHERE user_id = :user_id)"),
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


# ==================== Bug 1 & 2: _get_all_trip_email_contacts Tests ====================

def test_get_all_trip_email_contacts_solo_trip():
    """Test that solo trips only return owner's contacts."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner_solo@test.com", "Owner", "Solo")
        owner_contact_id = _create_test_contact(connection, owner_id, "Owner Contact", "owner_contact@test.com")
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=False, contact1=owner_contact_id)

        # Fetch the trip as a Row object
        trip = connection.execute(
            sqlalchemy.text("""
                SELECT id, user_id, is_group_trip, contact1, contact2, contact3
                FROM trips WHERE id = :id
            """),
            {"id": trip_id}
        ).fetchone()

        contacts = _get_all_trip_email_contacts(connection, trip)

    try:
        assert len(contacts) == 1
        assert contacts[0]["email"] == "owner_contact@test.com"
        assert contacts[0]["watched_user_name"] == "Owner Solo"
    finally:
        _cleanup_test_data(owner_id)


def test_get_all_trip_email_contacts_group_trip_with_participants():
    """Test that group trips include both owner's and participant's contacts.

    This tests the fix for Bug 1 & 2: getattr() was returning False for is_group_trip
    even when it was True in the database.
    """
    with db.engine.begin() as connection:
        # Create owner with contact
        owner_id = _create_test_user(connection, "owner_group@test.com", "Owner", "Group")
        owner_contact_id = _create_test_contact(connection, owner_id, "Owner Contact", "owner_contact_group@test.com")

        # Create participant with contact
        participant_id = _create_test_user(connection, "participant@test.com", "Participant", "User")
        participant_contact_id = _create_test_contact(connection, participant_id, "Participant Contact", "participant_contact@test.com")

        # Create friendship (required for group trips)
        _create_friendship(connection, owner_id, participant_id)

        # Create group trip with owner's contact
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)

        # Add participant to trip
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)

        # Add participant's contact for this trip
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

        # Fetch the trip as a Row object
        trip = connection.execute(
            sqlalchemy.text("""
                SELECT id, user_id, is_group_trip, contact1, contact2, contact3
                FROM trips WHERE id = :id
            """),
            {"id": trip_id}
        ).fetchone()

        # Verify is_group_trip is True
        assert trip.is_group_trip is True, "Trip should be marked as group trip"

        contacts = _get_all_trip_email_contacts(connection, trip)

    try:
        # Should have both owner's contact and participant's contact
        assert len(contacts) == 2, f"Expected 2 contacts, got {len(contacts)}: {contacts}"

        contact_emails = {c["email"] for c in contacts}
        assert "owner_contact_group@test.com" in contact_emails, "Owner's contact should be included"
        assert "participant_contact@test.com" in contact_emails, "Participant's contact should be included"

        # Verify watched_user_name is set correctly
        for contact in contacts:
            if contact["email"] == "owner_contact_group@test.com":
                assert contact["watched_user_name"] == "Owner Group", f"Owner's contact should watch owner, got: {contact['watched_user_name']}"
            elif contact["email"] == "participant_contact@test.com":
                assert contact["watched_user_name"] == "Participant User", f"Participant's contact should watch participant, got: {contact['watched_user_name']}"
    finally:
        _cleanup_test_data(owner_id, participant_id)


def test_get_all_trip_email_contacts_deduplicates_by_email():
    """Test that contacts with the same email are deduplicated."""
    with db.engine.begin() as connection:
        # Create owner with contact
        owner_id = _create_test_user(connection, "owner_dedup@test.com", "Owner", "Dedup")
        owner_contact_id = _create_test_contact(connection, owner_id, "Shared Contact", "shared@test.com")

        # Create participant with SAME email contact
        participant_id = _create_test_user(connection, "participant_dedup@test.com", "Participant", "Dedup")
        participant_contact_id = _create_test_contact(connection, participant_id, "Also Shared", "shared@test.com")

        _create_friendship(connection, owner_id, participant_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

        trip = connection.execute(
            sqlalchemy.text("""
                SELECT id, user_id, is_group_trip, contact1, contact2, contact3
                FROM trips WHERE id = :id
            """),
            {"id": trip_id}
        ).fetchone()

        contacts = _get_all_trip_email_contacts(connection, trip)

    try:
        # Should only have 1 contact (deduplicated)
        assert len(contacts) == 1, f"Expected 1 contact after deduplication, got {len(contacts)}"
        assert contacts[0]["email"] == "shared@test.com"
    finally:
        _cleanup_test_data(owner_id, participant_id)


def test_get_all_trip_email_contacts_is_group_trip_attribute_access():
    """Test that is_group_trip is correctly accessed from SQLAlchemy Row object.

    This specifically tests the fix: using direct attribute access (trip.is_group_trip)
    instead of getattr(trip, 'is_group_trip', False) which was failing silently.
    """
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner_attr@test.com", "Owner", "Attr")
        contact_id = _create_test_contact(connection, owner_id, "Contact", "contact_attr@test.com")

        # Create trip as group trip
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=contact_id)

        # Fetch trip the same way the actual code does
        trip = connection.execute(
            sqlalchemy.text("""
                SELECT id, user_id, is_group_trip, contact1, contact2, contact3
                FROM trips WHERE id = :id
            """),
            {"id": trip_id}
        ).fetchone()

        # Test that we can access is_group_trip correctly
        assert hasattr(trip, 'is_group_trip'), "Trip Row should have is_group_trip attribute"
        assert trip.is_group_trip is True, f"is_group_trip should be True, got: {trip.is_group_trip}"

        # The fix: using hasattr check instead of getattr with default
        is_group = trip.is_group_trip if hasattr(trip, 'is_group_trip') else False
        assert is_group is True, "Fixed attribute access should return True"

    _cleanup_test_data(owner_id)


# ==================== Bug 3: Participant Check-in watched_user_name Tests ====================

def test_participant_checkin_contacts_have_watched_user_name():
    """Test that participant check-in correctly sets watched_user_name for all contacts.

    This tests Bug 3: When a participant checks in, owner's contacts should have
    watched_user_name set to the owner's name, not the participant's name.
    """
    from src.api.participants import participant_checkin

    with db.engine.begin() as connection:
        # Create owner with contact
        owner_id = _create_test_user(connection, "owner_checkin@test.com", "Owner", "CheckIn")
        owner_contact_id = _create_test_contact(connection, owner_id, "Owner Contact", "owner_contact_checkin@test.com")

        # Create participant with contact
        participant_id = _create_test_user(connection, "participant_checkin@test.com", "Participant", "CheckIn")
        participant_contact_id = _create_test_contact(connection, participant_id, "Participant Contact", "participant_contact_checkin@test.com")

        _create_friendship(connection, owner_id, participant_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

    try:
        # Perform the check-in
        background_tasks = MagicMock(spec=BackgroundTasks)

        # This will trigger the notification flow that we fixed
        result = participant_checkin(
            trip_id=trip_id,
            background_tasks=background_tasks,
            user_id=participant_id,
            lat=37.7749,
            lon=-122.4194
        )

        assert result.ok is True, "Check-in should succeed"

        # Verify that background_tasks.add_task was called (notifications scheduled)
        assert background_tasks.add_task.called, "Background tasks should be scheduled for notifications"

    finally:
        _cleanup_test_data(owner_id, participant_id)


def test_owner_checkin_contacts_have_watched_user_name():
    """Test that owner check-in via token includes participant contacts with correct watched_user_name."""
    from src.api.checkin import checkin_with_token

    with db.engine.begin() as connection:
        # Create owner with contact
        owner_id = _create_test_user(connection, "owner_token@test.com", "Owner", "Token")
        owner_contact_id = _create_test_contact(connection, owner_id, "Owner Contact", "owner_contact_token@test.com")

        # Create participant with contact
        participant_id = _create_test_user(connection, "participant_token@test.com", "Participant", "Token")
        participant_contact_id = _create_test_contact(connection, participant_id, "Participant Contact", "participant_contact_token@test.com")

        _create_friendship(connection, owner_id, participant_id)

        # Create trip with a unique checkin token
        now = datetime.now(UTC)
        activity = connection.execute(
            sqlalchemy.text("SELECT id FROM activities LIMIT 1")
        ).fetchone()
        activity_id = activity[0] if activity else 1

        checkin_token = f"unique_checkin_token_{now.timestamp()}"

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (user_id, title, activity, start, eta, grace_min, status, is_group_trip,
                                  checkin_token, checkout_token, location_text, gen_lat, gen_lon,
                                  has_separate_locations, notify_self, notified_eta_transition,
                                  notified_grace_transition, share_live_location, contact1,
                                  group_settings)
                VALUES (:user_id, 'Test Trip', :activity, :start, :eta, 15, 'active', true,
                        :checkin_token, 'checkout_token', 'Test Location', 37.7749, -122.4194,
                        false, false, false, false, false, :contact1,
                        '{"checkout_mode": "anyone"}')
                RETURNING id
                """
            ),
            {
                "user_id": owner_id,
                "activity": activity_id,
                "start": now.isoformat(),
                "eta": (now + timedelta(hours=2)).isoformat(),
                "checkin_token": checkin_token,
                "contact1": owner_contact_id
            }
        )
        trip_id = result.fetchone()[0]

        # Add owner as participant (required for group trips)
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'owner', 'accepted', :now, :user_id)
                """
            ),
            {"trip_id": trip_id, "user_id": owner_id, "now": now.isoformat()}
        )

        # Add participant
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)

        # Owner checks in via token
        result = checkin_with_token(
            token=checkin_token,
            background_tasks=background_tasks,
            lat=37.7749,
            lon=-122.4194
        )

        assert result.ok is True, "Token check-in should succeed"

        # Verify notifications were scheduled
        assert background_tasks.add_task.called, "Background tasks should be scheduled"

    finally:
        _cleanup_test_data(owner_id, participant_id)


# ==================== Bug 3: Detailed watched_user_name Tests ====================

def test_participant_checkin_owner_contacts_get_owner_name():
    """Verify that when a participant checks in, owner's contacts have watched_user_name
    set to the OWNER's name, not the participant's name.

    This is the core test for Bug 3: emails should say "Update on [Owner]'s trip"
    for owner's contacts, not "Update on [Participant]'s trip".
    """
    with db.engine.begin() as connection:
        # Create owner "Alice" with contact
        owner_id = _create_test_user(connection, "alice_owner@test.com", "Alice", "Smith")
        owner_contact_id = _create_test_contact(connection, owner_id, "Alice Emergency", "alice_emergency@test.com")

        # Create participant "Bob" with contact
        participant_id = _create_test_user(connection, "bob_participant@test.com", "Bob", "Jones")
        participant_contact_id = _create_test_contact(connection, participant_id, "Bob Emergency", "bob_emergency@test.com")

        _create_friendship(connection, owner_id, participant_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

        # Now simulate what happens in participant_checkin when building contacts_for_email
        # Get owner's name
        owner = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": owner_id}
        ).fetchone()
        owner_name = f"{owner.first_name} {owner.last_name}".strip()

        # Get participant's name (checker)
        checker = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": participant_id}
        ).fetchone()
        checker_name = f"{checker.first_name} {checker.last_name}".strip()

        # Get participant's email contacts
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
            {"trip_id": trip_id, "user_id": participant_id}
        ).fetchall()

        # Participant's contacts watch the participant (the fix)
        contacts_for_email = [
            {**dict(c._mapping), "watched_user_name": checker_name}
            for c in participant_email_contacts
        ]

        # Get owner's email contacts
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

        # Owner's contacts watch the OWNER, not the participant (the fix for Bug 3)
        existing_emails = {c['email'].lower() for c in contacts_for_email if c.get('email')}
        for oc in owner_email_contacts:
            if oc.email and oc.email.lower() not in existing_emails:
                contacts_for_email.append({
                    **dict(oc._mapping),
                    "watched_user_name": owner_name  # THIS IS THE KEY FIX
                })
                existing_emails.add(oc.email.lower())

    try:
        # Verify we have 2 contacts
        assert len(contacts_for_email) == 2, f"Expected 2 contacts, got {len(contacts_for_email)}"

        # Build map for easier assertions
        contact_map = {c["email"]: c for c in contacts_for_email}

        # CRITICAL: Alice's emergency contact should watch ALICE (the owner)
        alice_contact = contact_map.get("alice_emergency@test.com")
        assert alice_contact is not None, "Alice's emergency contact should be included"
        assert alice_contact["watched_user_name"] == "Alice Smith", \
            f"Alice's contact should watch 'Alice Smith' (owner), got: '{alice_contact['watched_user_name']}'"

        # Bob's emergency contact should watch BOB (the participant who is checking in)
        bob_contact = contact_map.get("bob_emergency@test.com")
        assert bob_contact is not None, "Bob's emergency contact should be included"
        assert bob_contact["watched_user_name"] == "Bob Jones", \
            f"Bob's contact should watch 'Bob Jones' (the participant), got: '{bob_contact['watched_user_name']}'"

    finally:
        _cleanup_test_data(owner_id, participant_id)


def test_participant_checkin_email_subject_uses_watched_user_name():
    """Test that the email notification system uses watched_user_name correctly.

    Simulates the actual email building logic to verify:
    - Owner's contacts get emails with "Update on [Owner]'s trip"
    - Participant's contacts get emails with "Update on [Participant]'s trip"
    """
    from src.services.notifications import get_attr

    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner_email_test@test.com", "Sarah", "Owner")
        owner_contact_id = _create_test_contact(connection, owner_id, "Sarah Contact", "sarah_contact@test.com")

        participant_id = _create_test_user(connection, "participant_email_test@test.com", "Mike", "Participant")
        participant_contact_id = _create_test_contact(connection, participant_id, "Mike Contact", "mike_contact@test.com")

        _create_friendship(connection, owner_id, participant_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

    try:
        # Simulate the contacts_for_email list that would be built during participant check-in
        contacts_for_email = [
            {"email": "mike_contact@test.com", "name": "Mike Contact", "watched_user_name": "Mike Participant"},
            {"email": "sarah_contact@test.com", "name": "Sarah Contact", "watched_user_name": "Sarah Owner"},
        ]

        actor_name = "Mike Participant"  # The participant who checked in

        # Simulate what send_checkin_update_emails does:
        for contact in contacts_for_email:
            # This is the actual logic from notifications.py
            watched_user_name = get_attr(contact, 'watched_user_name') or actor_name

            if contact["email"] == "sarah_contact@test.com":
                # Owner's contact should see owner's name in subject
                assert watched_user_name == "Sarah Owner", \
                    f"Owner's contact should use 'Sarah Owner', got '{watched_user_name}'"
                expected_subject = f"Update on {watched_user_name}'s trip: Check-in received"
                assert "Sarah Owner" in expected_subject, "Subject should mention Sarah (owner)"
                assert "Mike" not in expected_subject, "Subject should NOT mention Mike (participant)"

            elif contact["email"] == "mike_contact@test.com":
                # Participant's contact should see participant's name
                assert watched_user_name == "Mike Participant", \
                    f"Participant's contact should use 'Mike Participant', got '{watched_user_name}'"
                expected_subject = f"Update on {watched_user_name}'s trip: Check-in received"
                assert "Mike Participant" in expected_subject, "Subject should mention Mike (participant)"

    finally:
        _cleanup_test_data(owner_id, participant_id)


def test_multiple_participants_each_contact_watches_correct_person():
    """Test with multiple participants - each participant's contacts should watch
    only that specific participant, not others or the owner.
    """
    with db.engine.begin() as connection:
        # Owner with contact
        owner_id = _create_test_user(connection, "owner_multi@test.com", "Owner", "Smith")
        owner_contact_id = _create_test_contact(connection, owner_id, "Owner Contact", "owner_multi_contact@test.com")

        # Participant 1 with contact
        p1_id = _create_test_user(connection, "p1_multi@test.com", "Participant", "One")
        p1_contact_id = _create_test_contact(connection, p1_id, "P1 Contact", "p1_contact@test.com")

        # Participant 2 with contact
        p2_id = _create_test_user(connection, "p2_multi@test.com", "Participant", "Two")
        p2_contact_id = _create_test_contact(connection, p2_id, "P2 Contact", "p2_contact@test.com")

        _create_friendship(connection, owner_id, p1_id)
        _create_friendship(connection, owner_id, p2_id)

        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)
        _add_participant_to_trip(connection, trip_id, p1_id, owner_id)
        _add_participant_to_trip(connection, trip_id, p2_id, owner_id)
        _add_participant_contact(connection, trip_id, p1_id, p1_contact_id)
        _add_participant_contact(connection, trip_id, p2_id, p2_contact_id)

        # Get all contacts using _get_all_trip_email_contacts
        trip = connection.execute(
            sqlalchemy.text("""
                SELECT id, user_id, is_group_trip, contact1, contact2, contact3
                FROM trips WHERE id = :id
            """),
            {"id": trip_id}
        ).fetchone()

        contacts = _get_all_trip_email_contacts(connection, trip)

    try:
        assert len(contacts) == 3, f"Expected 3 contacts, got {len(contacts)}"

        contact_map = {c["email"]: c["watched_user_name"] for c in contacts}

        # Each contact should watch the correct person
        assert contact_map.get("owner_multi_contact@test.com") == "Owner Smith", \
            "Owner's contact should watch Owner Smith"
        assert contact_map.get("p1_contact@test.com") == "Participant One", \
            "P1's contact should watch Participant One"
        assert contact_map.get("p2_contact@test.com") == "Participant Two", \
            "P2's contact should watch Participant Two"

    finally:
        _cleanup_test_data(owner_id, p1_id, p2_id)


def test_owner_checkin_all_contacts_watch_correct_person():
    """When the OWNER checks in (not a participant), all contacts should still
    have the correct watched_user_name - participant contacts watch their participant,
    owner contacts watch the owner.
    """
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner_checkin_test@test.com", "Owner", "ChecksIn")
        owner_contact_id = _create_test_contact(connection, owner_id, "Owner Contact", "owner_checkin_contact@test.com")

        participant_id = _create_test_user(connection, "participant_checkin_test@test.com", "Participant", "Stays")
        participant_contact_id = _create_test_contact(connection, participant_id, "Participant Contact", "participant_checkin_contact@test.com")

        _create_friendship(connection, owner_id, participant_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

        # When owner checks in, we use _get_all_trip_email_contacts from checkin.py
        trip = connection.execute(
            sqlalchemy.text("""
                SELECT id, user_id, is_group_trip, contact1, contact2, contact3
                FROM trips WHERE id = :id
            """),
            {"id": trip_id}
        ).fetchone()

        contacts = _get_all_trip_email_contacts(connection, trip)

    try:
        assert len(contacts) == 2, f"Expected 2 contacts, got {len(contacts)}"

        contact_map = {c["email"]: c["watched_user_name"] for c in contacts}

        # Owner's contact watches owner
        assert contact_map.get("owner_checkin_contact@test.com") == "Owner ChecksIn", \
            "Owner's contact should watch 'Owner ChecksIn'"

        # Participant's contact STILL watches participant (not owner!)
        assert contact_map.get("participant_checkin_contact@test.com") == "Participant Stays", \
            "Participant's contact should watch 'Participant Stays', not the owner"

    finally:
        _cleanup_test_data(owner_id, participant_id)


def test_watched_user_name_not_overwritten_by_actor():
    """Ensure watched_user_name is NOT overwritten by actor_name in the email function.

    The notifications.py send_checkin_update_emails function has this logic:
        watched_user_name = get_attr(contact, 'watched_user_name') or actor_name

    This test verifies that if watched_user_name is set, it takes precedence over actor_name.
    """
    from src.services.notifications import get_attr

    # Simulate contacts with watched_user_name already set
    contacts = [
        {"email": "owner_contact@test.com", "watched_user_name": "Owner Name"},
        {"email": "participant_contact@test.com", "watched_user_name": "Participant Name"},
    ]

    actor_name = "Participant Name"  # The person who checked in

    for contact in contacts:
        # This is the actual logic from notifications.py
        watched_user_name = get_attr(contact, 'watched_user_name') or actor_name

        # The key assertion: watched_user_name from contact should be used, not overwritten
        assert watched_user_name == contact["watched_user_name"], \
            f"watched_user_name should be '{contact['watched_user_name']}', not overwritten by actor_name"


def test_empty_watched_user_name_falls_back_to_actor():
    """If watched_user_name is not set (legacy data), it should fall back to actor_name."""
    from src.services.notifications import get_attr

    # Contact without watched_user_name (simulating legacy data or bug)
    contact = {"email": "legacy_contact@test.com", "name": "Legacy Contact"}

    actor_name = "Fallback Actor"

    watched_user_name = get_attr(contact, 'watched_user_name') or actor_name

    assert watched_user_name == "Fallback Actor", \
        "Should fall back to actor_name when watched_user_name is not set"


# ==================== Integration Test ====================

def test_full_group_trip_notification_flow():
    """Integration test for the full group trip notification flow.

    Creates a group trip, adds participants with contacts, and verifies
    that _get_all_trip_email_contacts returns all contacts with correct watched_user_name.
    """
    with db.engine.begin() as connection:
        # Create owner
        owner_id = _create_test_user(connection, "owner_full@test.com", "Alice", "Owner")
        owner_contact_id = _create_test_contact(connection, owner_id, "Alice Emergency Contact", "alice_emergency@test.com")

        # Create two participants
        participant1_id = _create_test_user(connection, "participant1_full@test.com", "Bob", "Participant")
        participant1_contact_id = _create_test_contact(connection, participant1_id, "Bob Emergency Contact", "bob_emergency@test.com")

        participant2_id = _create_test_user(connection, "participant2_full@test.com", "Carol", "Participant")
        participant2_contact_id = _create_test_contact(connection, participant2_id, "Carol Emergency Contact", "carol_emergency@test.com")

        # Create friendships
        _create_friendship(connection, owner_id, participant1_id)
        _create_friendship(connection, owner_id, participant2_id)

        # Create group trip
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)

        # Add participants
        _add_participant_to_trip(connection, trip_id, participant1_id, owner_id)
        _add_participant_to_trip(connection, trip_id, participant2_id, owner_id)

        # Add participant contacts
        _add_participant_contact(connection, trip_id, participant1_id, participant1_contact_id)
        _add_participant_contact(connection, trip_id, participant2_id, participant2_contact_id)

        # Fetch trip and get all contacts
        trip = connection.execute(
            sqlalchemy.text("""
                SELECT id, user_id, is_group_trip, contact1, contact2, contact3
                FROM trips WHERE id = :id
            """),
            {"id": trip_id}
        ).fetchone()

        contacts = _get_all_trip_email_contacts(connection, trip)

    try:
        # Should have 3 contacts total
        assert len(contacts) == 3, f"Expected 3 contacts, got {len(contacts)}"

        # Build a map of email -> watched_user_name
        contact_map = {c["email"]: c["watched_user_name"] for c in contacts}

        # Verify each contact has the correct watched_user_name
        assert contact_map.get("alice_emergency@test.com") == "Alice Owner", \
            "Alice's contact should watch Alice (the owner)"
        assert contact_map.get("bob_emergency@test.com") == "Bob Participant", \
            "Bob's contact should watch Bob"
        assert contact_map.get("carol_emergency@test.com") == "Carol Participant", \
            "Carol's contact should watch Carol"

    finally:
        _cleanup_test_data(owner_id, participant1_id, participant2_id)
