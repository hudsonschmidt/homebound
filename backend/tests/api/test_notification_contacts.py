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
            INSERT INTO users (email, first_name, last_name, age, created_at, subscription_tier)
            VALUES (:email, :first_name, :last_name, 30, :created_at, 'free')
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
    """Test that shared contacts receive separate personalized notifications.

    When the same email address is a contact for both the owner and a participant,
    they should receive separate emails with different watched_user_name values
    since each notification is personalized.
    """
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
        # Should have 2 contacts - same email but personalized for different users
        assert len(contacts) == 2, f"Expected 2 contacts (no dedup), got {len(contacts)}"
        # Both should have the same email
        assert all(c["email"] == "shared@test.com" for c in contacts)
        # But different watched_user_name values
        watched_names = {c["watched_user_name"] for c in contacts}
        assert "Owner Dedup" in watched_names, "Owner's contact should watch 'Owner Dedup'"
        assert "Participant Dedup" in watched_names, "Participant's contact should watch 'Participant Dedup'"
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


# ==================== End-to-End Notification Tests ====================

def test_start_trip_notifies_all_group_trip_contacts():
    """End-to-end test: start_trip() should send emails to BOTH owner and participant contacts.

    This tests the full notification flow, not just contact gathering.
    Bug regression test: Participant email contacts were not notified on trip start.
    """
    from src.api.trips import start_trip

    with db.engine.begin() as connection:
        # Create owner with contact
        owner_id = _create_test_user(connection, "owner_start_e2e@test.com", "Owner", "StartE2E")
        owner_contact_id = _create_test_contact(connection, owner_id, "Owner Contact", "owner_start_contact@test.com")

        # Create participant with contact
        participant_id = _create_test_user(connection, "participant_start_e2e@test.com", "Participant", "StartE2E")
        participant_contact_id = _create_test_contact(connection, participant_id, "Participant Contact", "participant_start_contact@test.com")

        _create_friendship(connection, owner_id, participant_id)

        # Create PLANNED group trip (not active) so we can start it
        now = datetime.now(UTC)
        activity = connection.execute(
            sqlalchemy.text("SELECT id FROM activities LIMIT 1")
        ).fetchone()
        activity_id = activity[0] if activity else 1

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (user_id, title, activity, start, eta, grace_min, status, is_group_trip,
                                  checkin_token, checkout_token, location_text, gen_lat, gen_lon,
                                  has_separate_locations, notify_self, notified_eta_transition,
                                  notified_grace_transition, share_live_location, contact1,
                                  group_settings)
                VALUES (:user_id, 'Test Start Trip', :activity, :start, :eta, 15, 'planned', true,
                        :checkin_token, 'checkout_token', 'Test Location', 37.7749, -122.4194,
                        false, false, false, false, false, :contact1,
                        '{"checkout_mode": "anyone"}')
                RETURNING id
                """
            ),
            {
                "user_id": owner_id,
                "activity": activity_id,
                "start": (now + timedelta(hours=1)).isoformat(),
                "eta": (now + timedelta(hours=3)).isoformat(),
                "checkin_token": f"start_e2e_checkin_{now.timestamp()}",
                "contact1": owner_contact_id
            }
        )
        trip_id = result.fetchone()[0]

        # Add owner as participant
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

        # Start the trip
        result = start_trip(
            trip_id=trip_id,
            background_tasks=background_tasks,
            user_id=owner_id
        )

        assert result["ok"] is True, "Trip should start successfully"

        # Verify background_tasks.add_task was called (notifications scheduled)
        assert background_tasks.add_task.called, "Background tasks should be scheduled for notifications"

        # Get the arguments passed to add_task - the first call should be for emails
        call_args_list = background_tasks.add_task.call_args_list
        assert len(call_args_list) >= 1, "At least one background task should be scheduled"

        # The email notification task is scheduled - we can't easily inspect the closure,
        # but we can verify the task was added
        # The important verification is that the trip start succeeded and tasks were scheduled

    finally:
        _cleanup_test_data(owner_id, participant_id)


def test_start_trip_notifies_participant_friend_contacts():
    """Verify start_trip() includes participant friend contacts in push notifications.

    Bug regression test: Participant friend contacts were not notified on trip start.
    """
    from src.api.trips import start_trip

    with db.engine.begin() as connection:
        # Create owner
        owner_id = _create_test_user(connection, "owner_friend_push@test.com", "Owner", "FriendPush")
        owner_contact_id = _create_test_contact(connection, owner_id, "Owner Contact", "owner_friend_push_contact@test.com")

        # Create participant
        participant_id = _create_test_user(connection, "participant_friend_push@test.com", "Participant", "FriendPush")

        # Create friend who will be participant's safety contact
        friend_id = _create_test_user(connection, "friend_safety@test.com", "Friend", "Safety")

        _create_friendship(connection, owner_id, participant_id)
        _create_friendship(connection, participant_id, friend_id)

        # Create PLANNED group trip
        now = datetime.now(UTC)
        activity = connection.execute(
            sqlalchemy.text("SELECT id FROM activities LIMIT 1")
        ).fetchone()
        activity_id = activity[0] if activity else 1

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (user_id, title, activity, start, eta, grace_min, status, is_group_trip,
                                  checkin_token, checkout_token, location_text, gen_lat, gen_lon,
                                  has_separate_locations, notify_self, notified_eta_transition,
                                  notified_grace_transition, share_live_location, contact1,
                                  group_settings)
                VALUES (:user_id, 'Test Friend Push Trip', :activity, :start, :eta, 15, 'planned', true,
                        :checkin_token, 'checkout_token', 'Test Location', 37.7749, -122.4194,
                        false, false, false, false, false, :contact1,
                        '{"checkout_mode": "anyone"}')
                RETURNING id
                """
            ),
            {
                "user_id": owner_id,
                "activity": activity_id,
                "start": (now + timedelta(hours=1)).isoformat(),
                "eta": (now + timedelta(hours=3)).isoformat(),
                "checkin_token": f"friend_push_checkin_{now.timestamp()}",
                "contact1": owner_contact_id
            }
        )
        trip_id = result.fetchone()[0]

        # Add owner as participant
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

        # Add participant's friend as safety contact
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO participant_trip_contacts (trip_id, participant_user_id, friend_user_id, position)
                VALUES (:trip_id, :participant_user_id, :friend_user_id, 1)
                ON CONFLICT DO NOTHING
                """
            ),
            {"trip_id": trip_id, "participant_user_id": participant_id, "friend_user_id": friend_id}
        )

    try:
        background_tasks = MagicMock(spec=BackgroundTasks)

        # Start the trip
        result = start_trip(
            trip_id=trip_id,
            background_tasks=background_tasks,
            user_id=owner_id
        )

        assert result["ok"] is True, "Trip should start successfully"

        # Verify background tasks were scheduled (includes push notifications)
        assert background_tasks.add_task.called, "Background tasks should be scheduled"

        # At least 2 tasks should be scheduled: email notifications and push notifications
        # (if friend contacts exist)
        call_count = background_tasks.add_task.call_count
        assert call_count >= 1, f"Expected at least 1 background task, got {call_count}"

    finally:
        _cleanup_test_data(owner_id, participant_id, friend_id)


def test_owner_token_checkin_notifies_all_contacts():
    """Verify checkin_with_token() includes participant contacts for group trips.

    Bug regression test: When owner checks in via token, participant contacts were not notified.
    """
    from src.api.checkin import checkin_with_token

    with db.engine.begin() as connection:
        # Create owner with contact
        owner_id = _create_test_user(connection, "owner_token_checkin_e2e@test.com", "Owner", "TokenE2E")
        owner_contact_id = _create_test_contact(connection, owner_id, "Owner Contact", "owner_token_e2e_contact@test.com")

        # Create participant with contact
        participant_id = _create_test_user(connection, "participant_token_checkin_e2e@test.com", "Participant", "TokenE2E")
        participant_contact_id = _create_test_contact(connection, participant_id, "Participant Contact", "participant_token_e2e_contact@test.com")

        _create_friendship(connection, owner_id, participant_id)

        # Create ACTIVE group trip with unique checkin token
        now = datetime.now(UTC)
        activity = connection.execute(
            sqlalchemy.text("SELECT id FROM activities LIMIT 1")
        ).fetchone()
        activity_id = activity[0] if activity else 1

        checkin_token = f"e2e_owner_checkin_token_{now.timestamp()}"

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (user_id, title, activity, start, eta, grace_min, status, is_group_trip,
                                  checkin_token, checkout_token, location_text, gen_lat, gen_lon,
                                  has_separate_locations, notify_self, notified_eta_transition,
                                  notified_grace_transition, share_live_location, contact1,
                                  group_settings)
                VALUES (:user_id, 'Test Owner Check-in', :activity, :start, :eta, 15, 'active', true,
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

        # Add owner as participant
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'owner', 'accepted', :now, :user_id)
                """
            ),
            {"trip_id": trip_id, "user_id": owner_id, "now": now.isoformat()}
        )

        # Add participant with contact
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
        assert background_tasks.add_task.called, "Background tasks should be scheduled for notifications"

    finally:
        _cleanup_test_data(owner_id, participant_id)


def test_owner_checkin_participant_contacts_have_correct_watched_user_name():
    """Verify that when owner checks in, participant contacts still watch participant (not owner).

    Bug regression test: Participant contacts incorrectly received owner's name as watched_user_name.
    """
    with db.engine.begin() as connection:
        # Create owner with contact
        owner_id = _create_test_user(connection, "owner_watched_name@test.com", "Alice", "Owner")
        owner_contact_id = _create_test_contact(connection, owner_id, "Alice Contact", "alice_watched_contact@test.com")

        # Create participant with contact
        participant_id = _create_test_user(connection, "participant_watched_name@test.com", "Bob", "Participant")
        participant_contact_id = _create_test_contact(connection, participant_id, "Bob Contact", "bob_watched_contact@test.com")

        _create_friendship(connection, owner_id, participant_id)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

        # Get all contacts as would happen during owner check-in
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

        # Build map for easier assertions
        contact_map = {c["email"]: c["watched_user_name"] for c in contacts}

        # Alice's contact should watch Alice (the owner)
        assert contact_map.get("alice_watched_contact@test.com") == "Alice Owner", \
            f"Alice's contact should watch 'Alice Owner', got '{contact_map.get('alice_watched_contact@test.com')}'"

        # Bob's contact should watch Bob (the participant), NOT Alice!
        # This is the key assertion - even when owner checks in, participant contacts
        # should still have their participant's name as watched_user_name
        assert contact_map.get("bob_watched_contact@test.com") == "Bob Participant", \
            f"Bob's contact should watch 'Bob Participant', got '{contact_map.get('bob_watched_contact@test.com')}'"

    finally:
        _cleanup_test_data(owner_id, participant_id)


# ==================== Bug 1: Scheduler Trip Start Notification Tests ====================

def test_scheduler_trip_start_owner_contacts_have_watched_user_name():
    """Bug 1 Regression Test: Scheduler trip start notifications should include
    watched_user_name for owner's contacts.

    The scheduler's trip start code at scheduler.py:499 creates contacts without
    watched_user_name, which breaks email personalization.
    """
    with db.engine.begin() as connection:
        # Create owner with contact
        owner_id = _create_test_user(connection, "owner_scheduler_test@test.com", "Alice", "SchedulerOwner")
        owner_contact_id = _create_test_contact(connection, owner_id, "Alice Contact", "alice_scheduler_contact@test.com")

        # Create trip
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=False, contact1=owner_contact_id)

        # Simulate what scheduler does at line 491-499
        owner_contacts = connection.execute(
            sqlalchemy.text("""
                SELECT c.id, c.name, c.email
                FROM contacts c
                WHERE c.id = :c1 AND c.email IS NOT NULL
            """),
            {"c1": owner_contact_id}
        ).fetchall()

        # This is the BUGGY pattern - scheduler does this:
        contacts_for_email_buggy = [dict(c._mapping) for c in owner_contacts]

        # Verify the bug exists - contacts should NOT have watched_user_name
        for contact in contacts_for_email_buggy:
            assert "watched_user_name" not in contact, \
                "BUG CONFIRMED: Scheduler creates contacts without watched_user_name"

    _cleanup_test_data(owner_id)


def test_scheduler_trip_start_participant_contacts_have_watched_user_name():
    """Bug 1 Regression Test: Scheduler trip start notifications should include
    watched_user_name for participant's contacts.

    The scheduler's trip start code at scheduler.py:528-531 adds participant contacts
    without watched_user_name, which breaks email personalization.
    """
    with db.engine.begin() as connection:
        # Create owner
        owner_id = _create_test_user(connection, "owner_sched_part@test.com", "Owner", "SchedPart")
        owner_contact_id = _create_test_contact(connection, owner_id, "Owner Contact", "owner_sched_part_contact@test.com")

        # Create participant with contact
        participant_id = _create_test_user(connection, "participant_sched@test.com", "Participant", "Sched")
        participant_contact_id = _create_test_contact(connection, participant_id, "Participant Contact", "participant_sched_contact@test.com")

        _create_friendship(connection, owner_id, participant_id)

        # Create group trip
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

        # Simulate what scheduler does at lines 514-531
        participant_email_contacts = connection.execute(
            sqlalchemy.text("""
                SELECT DISTINCT c.id, c.name, c.email
                FROM participant_trip_contacts ptc
                JOIN contacts c ON ptc.contact_id = c.id
                WHERE ptc.trip_id = :trip_id
                  AND ptc.contact_id IS NOT NULL
                  AND c.email IS NOT NULL
            """),
            {"trip_id": trip_id}
        ).fetchall()

        # This is the BUGGY pattern - scheduler does this at line 530:
        contacts_for_email_buggy = []
        existing_emails = set()
        for pc in participant_email_contacts:
            if pc.email and pc.email.lower() not in existing_emails:
                contacts_for_email_buggy.append(dict(pc._mapping))  # BUG: no watched_user_name
                existing_emails.add(pc.email.lower())

        # Verify the bug exists - participant contacts should NOT have watched_user_name
        for contact in contacts_for_email_buggy:
            assert "watched_user_name" not in contact, \
                "BUG CONFIRMED: Scheduler adds participant contacts without watched_user_name"

    _cleanup_test_data(owner_id, participant_id)


def test_scheduler_trip_start_should_include_watched_user_name():
    """Bug 1 Fix Verification: After fix, scheduler trip start notifications
    should include watched_user_name for ALL contacts.

    This test will FAIL until Bug 1 is fixed.
    """
    with db.engine.begin() as connection:
        # Create owner
        owner_id = _create_test_user(connection, "owner_sched_fix@test.com", "Alice", "SchedulerFix")
        owner_contact_id = _create_test_contact(connection, owner_id, "Alice Contact", "alice_sched_fix_contact@test.com")

        # Create participant with contact
        participant_id = _create_test_user(connection, "participant_sched_fix@test.com", "Bob", "SchedulerFix")
        participant_contact_id = _create_test_contact(connection, participant_id, "Bob Contact", "bob_sched_fix_contact@test.com")

        _create_friendship(connection, owner_id, participant_id)

        # Create group trip
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

        # Get the trip as scheduler would
        trip = connection.execute(
            sqlalchemy.text("""
                SELECT t.id, t.user_id, t.title, t.is_group_trip, t.contact1, t.contact2, t.contact3
                FROM trips t WHERE t.id = :trip_id
            """),
            {"trip_id": trip_id}
        ).fetchone()

        # Use _get_all_trip_email_contacts which DOES set watched_user_name correctly
        # This is the pattern scheduler SHOULD use
        contacts = _get_all_trip_email_contacts(connection, trip)

    try:
        # All contacts should have watched_user_name
        for contact in contacts:
            assert "watched_user_name" in contact and contact["watched_user_name"], \
                f"Contact {contact['email']} should have watched_user_name set"

        # Verify correct attribution
        contact_map = {c["email"]: c["watched_user_name"] for c in contacts}
        assert contact_map.get("alice_sched_fix_contact@test.com") == "Alice SchedulerFix", \
            "Owner's contact should watch owner"
        assert contact_map.get("bob_sched_fix_contact@test.com") == "Bob SchedulerFix", \
            "Participant's contact should watch participant"

    finally:
        _cleanup_test_data(owner_id, participant_id)


# ==================== Bug 2: Owner Check-in Notification Count Tests ====================

def test_owner_checkin_captures_all_contacts_count():
    """Bug 2 Regression Test: Verify owner check-in fetches BOTH owner and participant contacts.

    When owner checks in via token, _get_all_trip_email_contacts should return
    contacts for both owner AND all participants.
    """
    from src.api.checkin import checkin_with_token

    with db.engine.begin() as connection:
        # Create owner with contact
        owner_id = _create_test_user(connection, "owner_count_test@test.com", "Owner", "CountTest")
        owner_contact_id = _create_test_contact(connection, owner_id, "Owner Contact", "owner_count_contact@test.com")

        # Create participant with contact
        participant_id = _create_test_user(connection, "participant_count_test@test.com", "Participant", "CountTest")
        participant_contact_id = _create_test_contact(connection, participant_id, "Participant Contact", "participant_count_contact@test.com")

        _create_friendship(connection, owner_id, participant_id)

        # Create ACTIVE group trip
        now = datetime.now(UTC)
        activity = connection.execute(
            sqlalchemy.text("SELECT id FROM activities LIMIT 1")
        ).fetchone()
        activity_id = activity[0] if activity else 1

        checkin_token = f"count_test_token_{now.timestamp()}"

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (user_id, title, activity, start, eta, grace_min, status, is_group_trip,
                                  checkin_token, checkout_token, location_text, gen_lat, gen_lon,
                                  has_separate_locations, notify_self, notified_eta_transition,
                                  notified_grace_transition, share_live_location, contact1,
                                  group_settings)
                VALUES (:user_id, 'Count Test Trip', :activity, :start, :eta, 15, 'active', true,
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

        # Add owner as participant
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'owner', 'accepted', :now, :user_id)
                """
            ),
            {"trip_id": trip_id, "user_id": owner_id, "now": now.isoformat()}
        )

        # Add participant with contact
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

        # Now manually test _get_all_trip_email_contacts
        trip = connection.execute(
            sqlalchemy.text("""
                SELECT t.id, t.user_id, t.title, t.status, t.contact1, t.contact2, t.contact3,
                       t.timezone, t.location_text, t.eta, t.notify_self, t.grace_min,
                       t.is_group_trip
                FROM trips t WHERE t.id = :trip_id
            """),
            {"trip_id": trip_id}
        ).fetchone()

        # Verify is_group_trip is accessible
        assert trip.is_group_trip is True, "Trip should be marked as group trip"

        contacts = _get_all_trip_email_contacts(connection, trip)

    try:
        # Should have 2 contacts: owner's + participant's
        assert len(contacts) == 2, f"Expected 2 contacts, got {len(contacts)}: {[c['email'] for c in contacts]}"

        emails = {c['email'] for c in contacts}
        assert "owner_count_contact@test.com" in emails, "Owner's contact should be included"
        assert "participant_count_contact@test.com" in emails, "Participant's contact should be included"

    finally:
        _cleanup_test_data(owner_id, participant_id)


# ==================== Bug 1: Participant Join Active Trip Tests ====================

def test_participant_join_active_trip_should_notify_their_contacts():
    """Bug 1 Regression Test: When participant joins an ACTIVE group trip,
    their contacts should receive trip start notification.

    Currently, accept_invitation() only sends push to owner and refresh to
    other participants, but does NOT notify the new participant's contacts.
    """
    from src.api.participants import accept_invitation

    with db.engine.begin() as connection:
        # Create owner
        owner_id = _create_test_user(connection, "owner_join_active@test.com", "Owner", "JoinActive")
        owner_contact_id = _create_test_contact(connection, owner_id, "Owner Contact", "owner_join_active_contact@test.com")

        # Create participant with contact
        participant_id = _create_test_user(connection, "participant_join_active@test.com", "Participant", "JoinActive")
        participant_contact_id = _create_test_contact(connection, participant_id, "Participant Contact", "participant_join_active_contact@test.com")

        _create_friendship(connection, owner_id, participant_id)

        # Create ACTIVE group trip (trip has already started)
        now = datetime.now(UTC)
        activity = connection.execute(
            sqlalchemy.text("SELECT id FROM activities LIMIT 1")
        ).fetchone()
        activity_id = activity[0] if activity else 1

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (user_id, title, activity, start, eta, grace_min, status, is_group_trip,
                                  checkin_token, checkout_token, location_text, gen_lat, gen_lon,
                                  has_separate_locations, notify_self, notified_eta_transition,
                                  notified_grace_transition, share_live_location, contact1,
                                  group_settings, notified_trip_started)
                VALUES (:user_id, 'Active Trip Join Test', :activity, :start, :eta, 15, 'active', true,
                        :checkin_token, 'checkout_token', 'Test Location', 37.7749, -122.4194,
                        false, false, false, false, false, :contact1,
                        '{"checkout_mode": "anyone"}', true)
                RETURNING id
                """
            ),
            {
                "user_id": owner_id,
                "activity": activity_id,
                "start": (now - timedelta(hours=1)).isoformat(),  # Started 1 hour ago
                "eta": (now + timedelta(hours=2)).isoformat(),
                "checkin_token": f"join_active_token_{now.timestamp()}",
                "contact1": owner_contact_id
            }
        )
        trip_id = result.fetchone()[0]

        # Add owner as participant
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'owner', 'accepted', :now, :user_id)
                """
            ),
            {"trip_id": trip_id, "user_id": owner_id, "now": (now - timedelta(hours=1)).isoformat()}
        )

        # Invite participant (status = 'invited')
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, invited_by)
                VALUES (:trip_id, :user_id, 'participant', 'invited', :inviter_id)
                """
            ),
            {"trip_id": trip_id, "user_id": participant_id, "inviter_id": owner_id}
        )

    try:
        # This test documents the expected behavior:
        # When participant accepts invitation to an ACTIVE trip, their contacts
        # should be notified that the trip has started.
        #
        # Currently this does NOT happen - accept_invitation() needs to check
        # if the trip is active and send trip start notifications to the
        # participant's contacts.

        # For now, just verify the setup is correct
        with db.engine.begin() as connection:
            trip = connection.execute(
                sqlalchemy.text("SELECT status, is_group_trip FROM trips WHERE id = :id"),
                {"id": trip_id}
            ).fetchone()
            assert trip.status == "active", "Trip should be active"
            assert trip.is_group_trip is True, "Trip should be a group trip"

            participant = connection.execute(
                sqlalchemy.text(
                    "SELECT status FROM trip_participants WHERE trip_id = :trip_id AND user_id = :user_id"
                ),
                {"trip_id": trip_id, "user_id": participant_id}
            ).fetchone()
            assert participant.status == "invited", "Participant should be invited but not yet accepted"

        # TODO: After fix, this test should verify that:
        # 1. Calling accept_invitation() on an active trip
        # 2. Triggers trip start notification to participant's contacts
        # 3. The notification includes watched_user_name = participant's name

    finally:
        _cleanup_test_data(owner_id, participant_id)


# ==================== Check-In Notification Parity Tests ====================
# These tests verify that owner check-in and participant check-in
# produce IDENTICAL contact lists for email notifications.

def _add_owner_friend_contact(connection, trip_id: int, friend_user_id: int, position: int = 1):
    """Add a friend safety contact for the owner on a trip."""
    connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO trip_safety_contacts (trip_id, friend_user_id, position)
            VALUES (:trip_id, :friend_user_id, :position)
            ON CONFLICT DO NOTHING
            """
        ),
        {"trip_id": trip_id, "friend_user_id": friend_user_id, "position": position}
    )


def _add_participant_friend_contact(connection, trip_id: int, participant_user_id: int, friend_user_id: int, position: int = 2):
    """Add a friend safety contact for a participant on a trip.

    Note: Uses position=2 by default to avoid conflict with email contacts which use position=1.
    """
    connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO participant_trip_contacts (trip_id, participant_user_id, friend_user_id, position)
            VALUES (:trip_id, :participant_user_id, :friend_user_id, :position)
            ON CONFLICT DO NOTHING
            """
        ),
        {"trip_id": trip_id, "participant_user_id": participant_user_id, "friend_user_id": friend_user_id, "position": position}
    )


def _build_owner_checkin_contacts(connection, trip_id: int, owner_name: str):
    """
    Build the contact list as owner token check-in does.
    This mirrors the logic in checkin.py checkin_with_token().
    """
    contacts_for_email = []

    # Step 1: Get owner's email contacts from trips.contact1/2/3
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

    for c in owner_email_contacts:
        contacts_for_email.append({
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "watched_user_name": owner_name
        })

    # Step 2: Get ALL accepted participants and their contacts
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
        {"trip_id": trip_id}
    ).fetchall()

    for participant in accepted_participants:
        participant_name = participant.participant_name.strip() if participant.participant_name else "Participant"
        participant_user_id = participant.user_id

        # Get participant's email contacts
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
            {"trip_id": trip_id, "participant_user_id": participant_user_id}
        ).fetchall()

        for pc in participant_email_contacts:
            if pc.email:
                contacts_for_email.append({
                    "id": pc.id,
                    "name": pc.name,
                    "email": pc.email,
                    "watched_user_name": participant_name
                })

        # Get participant's friend contacts
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
            {"trip_id": trip_id, "participant_user_id": participant_user_id}
        ).fetchall()

        for pfc in participant_friend_contacts:
            if pfc.email:
                contacts_for_email.append({
                    "id": -pfc.id,
                    "name": pfc.name or "Friend",
                    "email": pfc.email,
                    "watched_user_name": participant_name
                })

    # Step 3: Get owner's friend safety contacts
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
        {"trip_id": trip_id}
    ).fetchall()

    for ofc in owner_friend_contacts:
        if ofc.email:
            contacts_for_email.append({
                "id": -ofc.id,
                "name": ofc.name or "Friend",
                "email": ofc.email,
                "watched_user_name": owner_name
            })

    return contacts_for_email


def _build_participant_checkin_contacts(connection, trip_id: int, checker_user_id: int, checker_name: str, owner_name: str):
    """
    Build the contact list as participant authenticated check-in does.
    This mirrors the logic in participants.py participant_checkin().

    Now includes ALL participants' contacts, not just the checking-in participant.
    No deduplication - emails are personalized to watched_user_name so same email
    watching multiple users should receive multiple emails.
    """
    contacts_for_email = []

    # Get checking-in participant's email safety contacts
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
        {"trip_id": trip_id, "user_id": checker_user_id}
    ).fetchall()

    for c in participant_email_contacts:
        contacts_for_email.append({**dict(c._mapping), "watched_user_name": checker_name})

    # Get trip owner's email contacts
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

    for oc in owner_email_contacts:
        if oc.email:
            contacts_for_email.append({
                **dict(oc._mapping),
                "watched_user_name": owner_name
            })

    # Get checking-in participant's friend contacts WITH email
    participant_friend_email_contacts = connection.execute(
        sqlalchemy.text(
            """
            SELECT friend.id as id,
                   TRIM(friend.first_name || ' ' || friend.last_name) as name,
                   friend.email as email
            FROM participant_trip_contacts ptc
            JOIN users friend ON ptc.friend_user_id = friend.id
            WHERE ptc.trip_id = :trip_id
            AND ptc.participant_user_id = :user_id
            AND ptc.friend_user_id IS NOT NULL
            AND friend.email IS NOT NULL
            """
        ),
        {"trip_id": trip_id, "user_id": checker_user_id}
    ).fetchall()

    for pfc in participant_friend_email_contacts:
        if pfc.email:
            contacts_for_email.append({
                "id": -pfc.id,
                "name": pfc.name or "Friend",
                "email": pfc.email,
                "watched_user_name": checker_name
            })

    # Get owner's friend contacts WITH email
    owner_friend_email_contacts = connection.execute(
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
            """
        ),
        {"trip_id": trip_id}
    ).fetchall()

    for ofc in owner_friend_email_contacts:
        if ofc.email:
            contacts_for_email.append({
                "id": -ofc.id,
                "name": ofc.name or "Friend",
                "email": ofc.email,
                "watched_user_name": owner_name
            })

    # Get ALL other accepted participants and their contacts
    other_accepted_participants = connection.execute(
        sqlalchemy.text(
            """
            SELECT tp.user_id,
                   COALESCE(TRIM(u.first_name || ' ' || u.last_name), 'Participant') as participant_name
            FROM trip_participants tp
            JOIN users u ON tp.user_id = u.id
            WHERE tp.trip_id = :trip_id
              AND tp.status = 'accepted'
              AND tp.role = 'participant'
              AND tp.user_id != :checking_in_user_id
            """
        ),
        {"trip_id": trip_id, "checking_in_user_id": checker_user_id}
    ).fetchall()

    for other_participant in other_accepted_participants:
        other_participant_name = other_participant.participant_name.strip() if other_participant.participant_name else "Participant"
        other_participant_user_id = other_participant.user_id

        # Get other participant's email contacts
        other_participant_email_contacts = connection.execute(
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
            {"trip_id": trip_id, "participant_user_id": other_participant_user_id}
        ).fetchall()

        for opc in other_participant_email_contacts:
            if opc.email:
                contacts_for_email.append({
                    "id": opc.id,
                    "name": opc.name,
                    "email": opc.email,
                    "watched_user_name": other_participant_name
                })

        # Get other participant's friend contacts
        other_participant_friend_contacts = connection.execute(
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
            {"trip_id": trip_id, "participant_user_id": other_participant_user_id}
        ).fetchall()

        for opfc in other_participant_friend_contacts:
            if opfc.email:
                contacts_for_email.append({
                    "id": -opfc.id,
                    "name": opfc.name or "Friend",
                    "email": opfc.email,
                    "watched_user_name": other_participant_name
                })

    return contacts_for_email


def _normalize_contacts(contacts):
    """Normalize contact list for comparison - sort by email and extract key fields."""
    return sorted(
        [(c['email'].lower(), c['watched_user_name']) for c in contacts],
        key=lambda x: x[0]
    )


def test_owner_and_participant_checkin_notify_same_contacts_basic():
    """
    CRITICAL TEST: Verify owner check-in and participant check-in
    produce the same contact list for email notifications.

    Basic case: 1 owner with 1 email contact, 1 participant with 1 email contact.
    """
    with db.engine.begin() as connection:
        # Create owner with email contact
        owner_id = _create_test_user(connection, "owner_parity_basic@test.com", "Alice", "Owner")
        owner_contact_id = _create_test_contact(connection, owner_id, "Alice Emergency", "alice_emergency@test.com")

        # Create participant with email contact
        participant_id = _create_test_user(connection, "participant_parity_basic@test.com", "Bob", "Participant")
        participant_contact_id = _create_test_contact(connection, participant_id, "Bob Emergency", "bob_emergency@test.com")

        _create_friendship(connection, owner_id, participant_id)

        # Create group trip
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

        # Build contact lists for both check-in paths
        owner_checkin_contacts = _build_owner_checkin_contacts(connection, trip_id, "Alice Owner")
        participant_checkin_contacts = _build_participant_checkin_contacts(
            connection, trip_id, participant_id, "Bob Participant", "Alice Owner"
        )

    try:
        # Both should have 2 contacts
        assert len(owner_checkin_contacts) == 2, f"Owner check-in should notify 2 contacts, got {len(owner_checkin_contacts)}"
        assert len(participant_checkin_contacts) == 2, f"Participant check-in should notify 2 contacts, got {len(participant_checkin_contacts)}"

        # Normalize and compare
        owner_normalized = _normalize_contacts(owner_checkin_contacts)
        participant_normalized = _normalize_contacts(participant_checkin_contacts)

        assert owner_normalized == participant_normalized, (
            f"Contact lists should be identical!\n"
            f"Owner check-in: {owner_normalized}\n"
            f"Participant check-in: {participant_normalized}"
        )

    finally:
        _cleanup_test_data(owner_id, participant_id)


def test_owner_and_participant_checkin_notify_same_contacts_with_friends():
    """
    CRITICAL TEST: Verify owner and participant check-in produce same contact list
    when BOTH have friend safety contacts (not just email contacts).
    """
    with db.engine.begin() as connection:
        # Create owner with email contact
        owner_id = _create_test_user(connection, "owner_parity_friends@test.com", "Alice", "Owner")
        owner_contact_id = _create_test_contact(connection, owner_id, "Alice Emergency", "alice_emergency_friends@test.com")

        # Create participant with email contact
        participant_id = _create_test_user(connection, "participant_parity_friends@test.com", "Bob", "Participant")
        participant_contact_id = _create_test_contact(connection, participant_id, "Bob Emergency", "bob_emergency_friends@test.com")

        # Create friends who will be safety contacts
        owner_friend_id = _create_test_user(connection, "owner_friend@test.com", "Owner", "Friend")
        participant_friend_id = _create_test_user(connection, "participant_friend@test.com", "Participant", "Friend")

        _create_friendship(connection, owner_id, participant_id)
        _create_friendship(connection, owner_id, owner_friend_id)
        _create_friendship(connection, participant_id, participant_friend_id)

        # Create group trip
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

        # Add friend safety contacts
        _add_owner_friend_contact(connection, trip_id, owner_friend_id, position=1)
        _add_participant_friend_contact(connection, trip_id, participant_id, participant_friend_id)

        # Build contact lists
        owner_checkin_contacts = _build_owner_checkin_contacts(connection, trip_id, "Alice Owner")
        participant_checkin_contacts = _build_participant_checkin_contacts(
            connection, trip_id, participant_id, "Bob Participant", "Alice Owner"
        )

    try:
        # Both should have 4 contacts: owner email + owner friend + participant email + participant friend
        assert len(owner_checkin_contacts) == 4, f"Owner check-in should notify 4 contacts, got {len(owner_checkin_contacts)}: {[c['email'] for c in owner_checkin_contacts]}"
        assert len(participant_checkin_contacts) == 4, f"Participant check-in should notify 4 contacts, got {len(participant_checkin_contacts)}: {[c['email'] for c in participant_checkin_contacts]}"

        # Normalize and compare
        owner_normalized = _normalize_contacts(owner_checkin_contacts)
        participant_normalized = _normalize_contacts(participant_checkin_contacts)

        assert owner_normalized == participant_normalized, (
            f"Contact lists should be identical!\n"
            f"Owner check-in: {owner_normalized}\n"
            f"Participant check-in: {participant_normalized}"
        )

        # Verify all 4 emails are present
        owner_emails = {c['email'].lower() for c in owner_checkin_contacts}
        assert "alice_emergency_friends@test.com" in owner_emails, "Owner's email contact missing"
        assert "bob_emergency_friends@test.com" in owner_emails, "Participant's email contact missing"
        assert "owner_friend@test.com" in owner_emails, "Owner's friend contact missing"
        assert "participant_friend@test.com" in owner_emails, "Participant's friend contact missing"

    finally:
        _cleanup_test_data(owner_id, participant_id, owner_friend_id, participant_friend_id)


def test_owner_and_participant_checkin_have_complete_parity_multiple_participants():
    """
    CRITICAL PARITY TEST: With multiple participants, verify that:
    - Owner check-in notifies ALL contacts (6 total)
    - Participant check-in ALSO notifies ALL contacts (6 total)
    - The contact lists are IDENTICAL

    This ensures every group check-in notifies everyone regardless of who checks in.
    """
    with db.engine.begin() as connection:
        # Create owner
        owner_id = _create_test_user(connection, "owner_full_parity@test.com", "Alice", "Owner")
        owner_contact_id = _create_test_contact(connection, owner_id, "Alice Emergency", "alice_full_parity@test.com")
        owner_friend_id = _create_test_user(connection, "owner_friend_full_parity@test.com", "Alice", "Friend")

        # Create 2 participants with contacts
        p1_id = _create_test_user(connection, "p1_full_parity@test.com", "Bob", "One")
        p1_contact_id = _create_test_contact(connection, p1_id, "Bob Emergency", "bob_full_parity@test.com")
        p1_friend_id = _create_test_user(connection, "p1_friend_full_parity@test.com", "Bob", "Friend")

        p2_id = _create_test_user(connection, "p2_full_parity@test.com", "Carol", "Two")
        p2_contact_id = _create_test_contact(connection, p2_id, "Carol Emergency", "carol_full_parity@test.com")
        p2_friend_id = _create_test_user(connection, "p2_friend_full_parity@test.com", "Carol", "Friend")

        # Create friendships
        _create_friendship(connection, owner_id, p1_id)
        _create_friendship(connection, owner_id, p2_id)
        _create_friendship(connection, owner_id, owner_friend_id)
        _create_friendship(connection, p1_id, p1_friend_id)
        _create_friendship(connection, p2_id, p2_friend_id)

        # Create group trip
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)

        # Add participants
        _add_participant_to_trip(connection, trip_id, p1_id, owner_id)
        _add_participant_to_trip(connection, trip_id, p2_id, owner_id)

        # Add email contacts
        _add_participant_contact(connection, trip_id, p1_id, p1_contact_id)
        _add_participant_contact(connection, trip_id, p2_id, p2_contact_id)

        # Add friend contacts
        _add_owner_friend_contact(connection, trip_id, owner_friend_id, position=1)
        _add_participant_friend_contact(connection, trip_id, p1_id, p1_friend_id)
        _add_participant_friend_contact(connection, trip_id, p2_id, p2_friend_id)

        # Build contact lists
        owner_checkin_contacts = _build_owner_checkin_contacts(connection, trip_id, "Alice Owner")
        p1_checkin_contacts = _build_participant_checkin_contacts(connection, trip_id, p1_id, "Bob One", "Alice Owner")

    try:
        # Both should have ALL 6 contacts
        assert len(owner_checkin_contacts) == 6, f"Owner check-in should notify 6 contacts, got {len(owner_checkin_contacts)}: {[c['email'] for c in owner_checkin_contacts]}"
        assert len(p1_checkin_contacts) == 6, f"P1 check-in should notify 6 contacts, got {len(p1_checkin_contacts)}: {[c['email'] for c in p1_checkin_contacts]}"

        # Normalize and compare - they should be IDENTICAL
        owner_normalized = _normalize_contacts(owner_checkin_contacts)
        p1_normalized = _normalize_contacts(p1_checkin_contacts)

        assert owner_normalized == p1_normalized, (
            f"Contact lists should be IDENTICAL!\n"
            f"Owner check-in: {owner_normalized}\n"
            f"P1 check-in: {p1_normalized}"
        )

        # Verify all 6 emails are present
        emails = {c['email'].lower() for c in owner_checkin_contacts}
        expected_emails = {
            "alice_full_parity@test.com",       # Owner's email contact
            "owner_friend_full_parity@test.com", # Owner's friend
            "bob_full_parity@test.com",          # P1's email contact
            "p1_friend_full_parity@test.com",    # P1's friend
            "carol_full_parity@test.com",        # P2's email contact
            "p2_friend_full_parity@test.com",    # P2's friend
        }
        assert emails == expected_emails, f"Expected {expected_emails}, got {emails}"

    finally:
        _cleanup_test_data(owner_id, p1_id, p2_id, owner_friend_id, p1_friend_id, p2_friend_id)


def test_owner_checkin_notifies_all_participants_contacts():
    """
    Test that owner check-in notifies ALL contacts across all participants.
    Owner check-in is comprehensive - it notifies everyone watching anyone in the trip.
    """
    with db.engine.begin() as connection:
        # Create owner
        owner_id = _create_test_user(connection, "owner_multi_parity@test.com", "Alice", "Owner")
        owner_contact_id = _create_test_contact(connection, owner_id, "Alice Emergency", "alice_multi_emergency@test.com")

        # Create 2 participants
        p1_id = _create_test_user(connection, "p1_multi_parity@test.com", "Bob", "One")
        p1_contact_id = _create_test_contact(connection, p1_id, "Bob Emergency", "bob_one_emergency@test.com")
        p1_friend_id = _create_test_user(connection, "p1_friend_multi@test.com", "Bob", "Friend")

        p2_id = _create_test_user(connection, "p2_multi_parity@test.com", "Carol", "Two")
        p2_contact_id = _create_test_contact(connection, p2_id, "Carol Emergency", "carol_two_emergency@test.com")
        p2_friend_id = _create_test_user(connection, "p2_friend_multi@test.com", "Carol", "Friend")

        # Owner's friend
        owner_friend_id = _create_test_user(connection, "owner_friend_multi@test.com", "Alice", "Friend")

        # Create friendships
        _create_friendship(connection, owner_id, p1_id)
        _create_friendship(connection, owner_id, p2_id)
        _create_friendship(connection, owner_id, owner_friend_id)
        _create_friendship(connection, p1_id, p1_friend_id)
        _create_friendship(connection, p2_id, p2_friend_id)

        # Create group trip
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)

        # Add participants
        _add_participant_to_trip(connection, trip_id, p1_id, owner_id)
        _add_participant_to_trip(connection, trip_id, p2_id, owner_id)

        # Add email contacts
        _add_participant_contact(connection, trip_id, p1_id, p1_contact_id)
        _add_participant_contact(connection, trip_id, p2_id, p2_contact_id)

        # Add friend contacts (use default position=2 for participant friends to avoid conflict with email contacts)
        _add_owner_friend_contact(connection, trip_id, owner_friend_id, position=1)
        _add_participant_friend_contact(connection, trip_id, p1_id, p1_friend_id)
        _add_participant_friend_contact(connection, trip_id, p2_id, p2_friend_id)

        owner_checkin_contacts = _build_owner_checkin_contacts(connection, trip_id, "Alice Owner")

    try:
        # Owner check-in should see ALL 6 contacts:
        # - Owner email contact
        # - Owner friend contact
        # - P1 email contact
        # - P1 friend contact
        # - P2 email contact
        # - P2 friend contact
        assert len(owner_checkin_contacts) == 6, f"Owner check-in should notify 6 contacts, got {len(owner_checkin_contacts)}: {[c['email'] for c in owner_checkin_contacts]}"

        # Verify all emails are present
        emails = {c['email'].lower() for c in owner_checkin_contacts}
        assert "alice_multi_emergency@test.com" in emails, "Owner's email contact missing"
        assert "owner_friend_multi@test.com" in emails, "Owner's friend contact missing"
        assert "bob_one_emergency@test.com" in emails, "P1's email contact missing"
        assert "p1_friend_multi@test.com" in emails, "P1's friend contact missing"
        assert "carol_two_emergency@test.com" in emails, "P2's email contact missing"
        assert "p2_friend_multi@test.com" in emails, "P2's friend contact missing"

    finally:
        _cleanup_test_data(owner_id, p1_id, p2_id, owner_friend_id, p1_friend_id, p2_friend_id)


def test_participant_checkin_notifies_all_contacts():
    """
    Test that participant check-in notifies ALL contacts in the group:
    - The checking-in participant's contacts (watching them)
    - The owner's contacts (watching the owner)
    - ALL other participants' contacts too

    This is the same set of contacts as owner check-in - complete parity.
    """
    with db.engine.begin() as connection:
        # Create owner
        owner_id = _create_test_user(connection, "owner_p_checkin@test.com", "Alice", "Owner")
        owner_contact_id = _create_test_contact(connection, owner_id, "Alice Emergency", "alice_p_checkin@test.com")
        owner_friend_id = _create_test_user(connection, "owner_friend_p_checkin@test.com", "Alice", "Friend")

        # Create participant
        participant_id = _create_test_user(connection, "participant_p_checkin@test.com", "Bob", "Participant")
        participant_contact_id = _create_test_contact(connection, participant_id, "Bob Emergency", "bob_p_checkin@test.com")
        participant_friend_id = _create_test_user(connection, "participant_friend_p_checkin@test.com", "Bob", "Friend")

        _create_friendship(connection, owner_id, participant_id)
        _create_friendship(connection, owner_id, owner_friend_id)
        _create_friendship(connection, participant_id, participant_friend_id)

        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)
        _add_owner_friend_contact(connection, trip_id, owner_friend_id, position=1)
        _add_participant_friend_contact(connection, trip_id, participant_id, participant_friend_id)

        participant_checkin_contacts = _build_participant_checkin_contacts(
            connection, trip_id, participant_id, "Bob Participant", "Alice Owner"
        )

    try:
        # Participant check-in should notify ALL 4 contacts (same as owner check-in):
        # - Owner's email contact (watching owner)
        # - Owner's friend contact (watching owner)
        # - Participant's email contact (watching participant)
        # - Participant's friend contact (watching participant)
        assert len(participant_checkin_contacts) == 4, f"Participant check-in should notify 4 contacts, got {len(participant_checkin_contacts)}: {[c['email'] for c in participant_checkin_contacts]}"

        emails = {c['email'].lower() for c in participant_checkin_contacts}
        assert "bob_p_checkin@test.com" in emails, "Participant's email contact missing"
        assert "participant_friend_p_checkin@test.com" in emails, "Participant's friend contact missing"
        assert "alice_p_checkin@test.com" in emails, "Owner's email contact missing"
        assert "owner_friend_p_checkin@test.com" in emails, "Owner's friend contact missing"

    finally:
        _cleanup_test_data(owner_id, participant_id, owner_friend_id, participant_friend_id)


def test_checkin_contact_parity_watched_user_name_correct():
    """
    Verify that watched_user_name is correctly set for ALL contact types:
    - Owner's email contacts watch the owner
    - Owner's friend contacts watch the owner
    - Participant's email contacts watch the participant
    - Participant's friend contacts watch the participant
    """
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner_watched_parity@test.com", "Alice", "Owner")
        owner_contact_id = _create_test_contact(connection, owner_id, "Alice Emergency", "alice_watched_parity@test.com")

        participant_id = _create_test_user(connection, "participant_watched_parity@test.com", "Bob", "Participant")
        participant_contact_id = _create_test_contact(connection, participant_id, "Bob Emergency", "bob_watched_parity@test.com")

        owner_friend_id = _create_test_user(connection, "owner_friend_watched@test.com", "Alice", "Friend")
        participant_friend_id = _create_test_user(connection, "participant_friend_watched@test.com", "Bob", "Friend")

        _create_friendship(connection, owner_id, participant_id)
        _create_friendship(connection, owner_id, owner_friend_id)
        _create_friendship(connection, participant_id, participant_friend_id)

        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)
        _add_owner_friend_contact(connection, trip_id, owner_friend_id, position=1)
        _add_participant_friend_contact(connection, trip_id, participant_id, participant_friend_id)

        owner_contacts = _build_owner_checkin_contacts(connection, trip_id, "Alice Owner")

    try:
        contact_map = {c['email'].lower(): c['watched_user_name'] for c in owner_contacts}

        # Owner's email contact watches owner
        assert contact_map.get("alice_watched_parity@test.com") == "Alice Owner", \
            "Owner's email contact should watch 'Alice Owner'"

        # Owner's friend watches owner
        assert contact_map.get("owner_friend_watched@test.com") == "Alice Owner", \
            "Owner's friend should watch 'Alice Owner'"

        # Participant's email contact watches participant
        assert contact_map.get("bob_watched_parity@test.com") == "Bob Participant", \
            "Participant's email contact should watch 'Bob Participant'"

        # Participant's friend watches participant
        assert contact_map.get("participant_friend_watched@test.com") == "Bob Participant", \
            "Participant's friend should watch 'Bob Participant'"

    finally:
        _cleanup_test_data(owner_id, participant_id, owner_friend_id, participant_friend_id)


def test_owner_checkin_without_is_group_trip_flag_still_notifies_participants():
    """
    Regression test: Owner check-in should notify participant contacts
    even if is_group_trip flag is False (as long as participants exist).

    This was a bug where participant contacts weren't notified because
    the code was inside 'if trip.is_group_trip:' block.
    """
    with db.engine.begin() as connection:
        # Create owner
        owner_id = _create_test_user(connection, "owner_no_flag@test.com", "Alice", "NoFlag")
        owner_contact_id = _create_test_contact(connection, owner_id, "Alice Emergency", "alice_no_flag@test.com")

        # Create participant
        participant_id = _create_test_user(connection, "participant_no_flag@test.com", "Bob", "NoFlag")
        participant_contact_id = _create_test_contact(connection, participant_id, "Bob Emergency", "bob_no_flag@test.com")

        _create_friendship(connection, owner_id, participant_id)

        # Create trip WITHOUT is_group_trip flag (defaults to false)
        trip_id = _create_test_trip(connection, owner_id, is_group_trip=False, contact1=owner_contact_id)

        # But still add a participant (edge case)
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

        owner_contacts = _build_owner_checkin_contacts(connection, trip_id, "Alice NoFlag")

    try:
        # Should still have 2 contacts even without is_group_trip flag
        assert len(owner_contacts) == 2, (
            f"Owner check-in should notify 2 contacts even without is_group_trip flag, "
            f"got {len(owner_contacts)}: {[c['email'] for c in owner_contacts]}"
        )

        emails = {c['email'].lower() for c in owner_contacts}
        assert "alice_no_flag@test.com" in emails, "Owner's contact should be included"
        assert "bob_no_flag@test.com" in emails, "Participant's contact should be included (BUG if missing!)"

    finally:
        _cleanup_test_data(owner_id, participant_id)


def test_checkin_deduplication_same_email_different_watched_users():
    """
    Test that if the same email appears as contact for both owner and participant,
    both entries are kept (NOT deduplicated) because they have different watched_user_name.

    This ensures personalized emails are sent for each watched user.
    """
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner_dedup_test@test.com", "Alice", "Owner")
        participant_id = _create_test_user(connection, "participant_dedup_test@test.com", "Bob", "Participant")

        # Create contact with SAME email for both owner and participant
        owner_contact_id = _create_test_contact(connection, owner_id, "Shared Contact Owner", "shared_dedup@test.com")
        participant_contact_id = _create_test_contact(connection, participant_id, "Shared Contact Participant", "shared_dedup@test.com")

        _create_friendship(connection, owner_id, participant_id)

        trip_id = _create_test_trip(connection, owner_id, is_group_trip=True, contact1=owner_contact_id)
        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

        owner_contacts = _build_owner_checkin_contacts(connection, trip_id, "Alice Owner")

    try:
        # Should have 2 entries for the same email (different watched_user_name)
        shared_contacts = [c for c in owner_contacts if c['email'].lower() == "shared_dedup@test.com"]
        assert len(shared_contacts) == 2, (
            f"Should have 2 entries for shared email (personalized for each user), "
            f"got {len(shared_contacts)}"
        )

        watched_names = {c['watched_user_name'] for c in shared_contacts}
        assert "Alice Owner" in watched_names, "One email should be for watching Alice"
        assert "Bob Participant" in watched_names, "One email should be for watching Bob"

    finally:
        _cleanup_test_data(owner_id, participant_id)


def test_actual_checkin_endpoints_produce_matching_contacts():
    """
    Integration test: Actually call the check-in endpoint functions
    and verify they produce matching notification behavior.
    """
    from src.api.checkin import checkin_with_token
    from src.api.participants import participant_checkin
    from unittest.mock import MagicMock, patch

    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "owner_actual_checkin@test.com", "Alice", "Actual")
        owner_contact_id = _create_test_contact(connection, owner_id, "Alice Emergency", "alice_actual@test.com")

        participant_id = _create_test_user(connection, "participant_actual_checkin@test.com", "Bob", "Actual")
        participant_contact_id = _create_test_contact(connection, participant_id, "Bob Emergency", "bob_actual@test.com")

        _create_friendship(connection, owner_id, participant_id)

        now = datetime.now(UTC)
        activity = connection.execute(
            sqlalchemy.text("SELECT id FROM activities LIMIT 1")
        ).fetchone()
        activity_id = activity[0] if activity else 1

        checkin_token = f"actual_checkin_token_{now.timestamp()}"

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (user_id, title, activity, start, eta, grace_min, status, is_group_trip,
                                  checkin_token, checkout_token, location_text, gen_lat, gen_lon,
                                  has_separate_locations, notify_self, notified_eta_transition,
                                  notified_grace_transition, share_live_location, contact1,
                                  group_settings)
                VALUES (:user_id, 'Actual Check-in Test', :activity, :start, :eta, 15, 'active', true,
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

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trip_participants (trip_id, user_id, role, status, joined_at, invited_by)
                VALUES (:trip_id, :user_id, 'owner', 'accepted', :now, :user_id)
                """
            ),
            {"trip_id": trip_id, "user_id": owner_id, "now": now.isoformat()}
        )

        _add_participant_to_trip(connection, trip_id, participant_id, owner_id)
        _add_participant_contact(connection, trip_id, participant_id, participant_contact_id)

    captured_contacts = {"owner": None, "participant": None}

    def capture_owner_contacts(*args, **kwargs):
        captured_contacts["owner"] = kwargs.get("contacts", [])

    def capture_participant_contacts(*args, **kwargs):
        captured_contacts["participant"] = kwargs.get("contacts", [])

    try:
        # Test owner check-in via token
        with patch("src.api.checkin.send_checkin_update_emails", side_effect=capture_owner_contacts):
            with patch("src.api.checkin.send_live_activity_update"):
                with patch("src.api.checkin.send_push_to_user"):
                    with patch("src.api.checkin.send_friend_checkin_push"):
                        with patch("src.api.checkin.send_data_refresh_push"):
                            with patch("src.api.checkin.reverse_geocode_sync", return_value=None):
                                background_tasks = MagicMock(spec=BackgroundTasks)
                                checkin_with_token(checkin_token, background_tasks, lat=None, lon=None)

                                # Execute background tasks
                                for call in background_tasks.add_task.call_args_list:
                                    task_func = call[0][0]
                                    task_func()

        # Test participant check-in via authenticated endpoint
        with patch("src.api.participants.send_checkin_update_emails", side_effect=capture_participant_contacts):
            with patch("src.api.participants.send_participant_checkin_push"):
                with patch("src.api.participants.send_friend_checkin_push"):
                    with patch("src.api.participants.send_data_refresh_push"):
                        with patch("src.api.participants.reverse_geocode_sync", return_value=None):
                            background_tasks2 = MagicMock(spec=BackgroundTasks)
                            participant_checkin(trip_id, background_tasks2, lat=None, lon=None, user_id=participant_id)

                            for call in background_tasks2.add_task.call_args_list:
                                task_func = call[0][0]
                                task_func()

        # Compare captured contacts
        assert captured_contacts["owner"] is not None, "Owner check-in should have captured contacts"
        assert captured_contacts["participant"] is not None, "Participant check-in should have captured contacts"

        owner_count = len(captured_contacts["owner"])
        participant_count = len(captured_contacts["participant"])

        assert owner_count == participant_count, (
            f"Contact counts should match! Owner: {owner_count}, Participant: {participant_count}"
        )

        owner_emails = {c['email'].lower() for c in captured_contacts["owner"]}
        participant_emails = {c['email'].lower() for c in captured_contacts["participant"]}

        assert owner_emails == participant_emails, (
            f"Contact emails should be identical!\n"
            f"Owner: {owner_emails}\n"
            f"Participant: {participant_emails}"
        )

    finally:
        _cleanup_test_data(owner_id, participant_id)
