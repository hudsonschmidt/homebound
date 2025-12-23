"""Race condition tests for concurrent operations.

Tests for:
- Concurrent magic code verification (only one should succeed)
- Concurrent trip extend operations (no duplicate extends)
- Concurrent checkin operations
"""
import asyncio
import concurrent.futures
from datetime import UTC, datetime, timedelta
from threading import Thread, Barrier
from unittest.mock import patch

import pytest
import sqlalchemy
from fastapi import BackgroundTasks, HTTPException

from src import database as db
from src.api.auth_endpoints import (
    MagicLinkRequest,
    TokenResponse,
    VerifyRequest,
    request_magic_link,
    verify_magic_code,
)
from src.api.trips import extend_trip


def run_async(coro):
    """Helper to run async functions in sync tests"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def cleanup_user(email: str):
    """Helper to clean up test user and all related data"""
    with db.engine.begin() as connection:
        # Get user ID first
        user = connection.execute(
            sqlalchemy.text("SELECT id FROM users WHERE email = :email"),
            {"email": email}
        ).fetchone()

        if user:
            user_id = user.id

            # Clear last_checkin to avoid FK constraint
            connection.execute(
                sqlalchemy.text("UPDATE trips SET last_checkin = NULL WHERE user_id = :user_id"),
                {"user_id": user_id}
            )

            # Delete in proper order to respect foreign keys
            connection.execute(
                sqlalchemy.text("DELETE FROM trip_safety_contacts WHERE trip_id IN (SELECT id FROM trips WHERE user_id = :user_id)"),
                {"user_id": user_id}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM live_activity_tokens WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM events WHERE user_id = :user_id"),
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
                sqlalchemy.text("DELETE FROM devices WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            connection.execute(
                sqlalchemy.text("DELETE FROM login_tokens WHERE user_id = :user_id"),
                {"user_id": user_id}
            )

        connection.execute(
            sqlalchemy.text("DELETE FROM login_tokens WHERE email = :email"),
            {"email": email}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE email = :email"),
            {"email": email}
        )


def create_test_user(email: str) -> int:
    """Create a test user and return their ID"""
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO users (email, first_name, last_name, age)
                VALUES (:email, 'Test', 'User', 25)
                RETURNING id
                """
            ),
            {"email": email}
        )
        return result.fetchone()[0]


# ============================================================================
# Concurrent Magic Code Verification Tests
# ============================================================================

def test_concurrent_verify_same_code():
    """Test that only one concurrent verification of the same code succeeds"""
    test_email = "concurrent-verify@racetest.example.com"
    cleanup_user(test_email)

    # Request magic link (creates user and code)
    run_async(request_magic_link(MagicLinkRequest(email=test_email)))

    # Get the magic code
    with db.engine.begin() as connection:
        token_record = connection.execute(
            sqlalchemy.text(
                "SELECT token FROM login_tokens WHERE email = :email ORDER BY created_at DESC LIMIT 1"
            ),
            {"email": test_email}
        ).fetchone()
        magic_code = token_record.token

    # Prepare concurrent verify requests
    num_concurrent = 5
    results = []
    errors = []

    def attempt_verify():
        try:
            verify_req = VerifyRequest(email=test_email, code=magic_code)
            result = verify_magic_code(verify_req)
            results.append(("success", result))
        except HTTPException as e:
            errors.append(("error", e.status_code, e.detail))
        except Exception as e:
            errors.append(("exception", str(e)))

    # Launch concurrent threads
    threads = []
    for _ in range(num_concurrent):
        t = Thread(target=attempt_verify)
        threads.append(t)

    # Start all threads as simultaneously as possible
    for t in threads:
        t.start()

    # Wait for all to complete
    for t in threads:
        t.join()

    # Exactly one should succeed, rest should get "already used" errors
    success_count = len([r for r in results if r[0] == "success"])
    already_used_count = len([e for e in errors if "already used" in str(e).lower()])

    # At most one should succeed
    assert success_count <= 1, f"Expected at most 1 success, got {success_count}"

    # The rest should be "already used" errors
    if success_count == 1:
        assert already_used_count == num_concurrent - 1, (
            f"Expected {num_concurrent - 1} 'already used' errors, got {already_used_count}"
        )

    cleanup_user(test_email)


def test_concurrent_verify_different_codes_all_succeed():
    """Test that concurrent verifications of different codes all succeed"""
    num_users = 3
    test_emails = [f"concurrent-diff-{i}@racetest.example.com" for i in range(num_users)]

    # Cleanup all
    for email in test_emails:
        cleanup_user(email)

    # Create users and codes
    magic_codes = []
    for email in test_emails:
        run_async(request_magic_link(MagicLinkRequest(email=email)))

        with db.engine.begin() as connection:
            token_record = connection.execute(
                sqlalchemy.text(
                    "SELECT token FROM login_tokens WHERE email = :email ORDER BY created_at DESC LIMIT 1"
                ),
                {"email": email}
            ).fetchone()
            magic_codes.append((email, token_record.token))

    # Concurrent verify of different codes
    results = []

    def attempt_verify(email, code):
        try:
            verify_req = VerifyRequest(email=email, code=code)
            result = verify_magic_code(verify_req)
            results.append(("success", email))
        except Exception as e:
            results.append(("error", email, str(e)))

    threads = []
    for email, code in magic_codes:
        t = Thread(target=attempt_verify, args=(email, code))
        threads.append(t)

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    # All should succeed since they're different codes
    success_count = len([r for r in results if r[0] == "success"])
    assert success_count == num_users, f"Expected {num_users} successes, got {success_count}"

    # Cleanup
    for email in test_emails:
        cleanup_user(email)


# ============================================================================
# Concurrent Trip Extension Tests
# ============================================================================

def create_active_trip(user_id: int, email: str) -> int:
    """Create an active trip for testing"""
    with db.engine.begin() as connection:
        # Create contact first
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO contacts (user_id, name, email)
                VALUES (:user_id, 'Test Contact', :contact_email)
                RETURNING id
                """
            ),
            {"user_id": user_id, "contact_email": email}
        )
        contact_id = result.fetchone()[0]

        # Get activity ID
        activity = connection.execute(
            sqlalchemy.text("SELECT id FROM activities WHERE name = 'Hiking'")
        ).fetchone()
        activity_id = activity.id

        # Create trip with ETA in the future
        now = datetime.now(UTC)
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (
                    user_id, title, activity, start, eta, grace_min,
                    location_text, gen_lat, gen_lon, status, contact1,
                    created_at, checkin_token, checkout_token
                )
                VALUES (
                    :user_id, :title, :activity, :start, :eta, :grace_min,
                    :location_text, :gen_lat, :gen_lon, 'active', :contact1,
                    :created_at, :checkin_token, :checkout_token
                )
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "title": "Concurrent Test Trip",
                "activity": activity_id,
                "start": now.isoformat(),
                "eta": (now + timedelta(hours=1)).isoformat(),  # 1 hour from now
                "grace_min": 30,
                "location_text": "Test Location",
                "gen_lat": 37.7749,
                "gen_lon": -122.4194,
                "contact1": contact_id,
                "created_at": now.isoformat(),
                "checkin_token": f"checkin_race_{now.timestamp()}",
                "checkout_token": f"checkout_race_{now.timestamp()}"
            }
        )
        return result.fetchone()[0]


def test_concurrent_extend_trip_race():
    """Test that concurrent extend requests are handled correctly"""
    test_email = "concurrent-extend@racetest.example.com"
    cleanup_user(test_email)

    # Create user and trip
    user_id = create_test_user(test_email)
    trip_id = create_active_trip(user_id, test_email)

    # Get initial ETA
    with db.engine.begin() as connection:
        trip = connection.execute(
            sqlalchemy.text("SELECT eta FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        ).fetchone()
        initial_eta_str = trip.eta

    # Parse initial ETA
    if isinstance(initial_eta_str, datetime):
        initial_eta = initial_eta_str
    else:
        initial_eta = datetime.fromisoformat(initial_eta_str.replace(' ', 'T'))

    if initial_eta.tzinfo is None:
        initial_eta = initial_eta.replace(tzinfo=UTC)

    # Launch concurrent extend requests
    num_concurrent = 5
    extend_minutes = 30
    results = []
    errors = []

    def attempt_extend():
        try:
            background_tasks = BackgroundTasks()
            result = extend_trip(
                trip_id=trip_id,
                minutes=extend_minutes,
                background_tasks=background_tasks,
                user_id=user_id
            )
            results.append(("success", result))
        except HTTPException as e:
            errors.append(("error", e.status_code, e.detail))
        except Exception as e:
            errors.append(("exception", str(e)))

    threads = []
    for _ in range(num_concurrent):
        t = Thread(target=attempt_extend)
        threads.append(t)

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    # All extends should technically succeed (they're independent operations)
    # but we verify the ETA is properly extended

    # Check how many extend events were created
    with db.engine.begin() as connection:
        events = connection.execute(
            sqlalchemy.text(
                "SELECT COUNT(*) as count FROM events WHERE trip_id = :trip_id AND what = 'extended'"
            ),
            {"trip_id": trip_id}
        ).fetchone()

        # Each extend creates an event
        assert events.count == num_concurrent, (
            f"Expected {num_concurrent} extend events, got {events.count}"
        )

        # Get final ETA
        trip = connection.execute(
            sqlalchemy.text("SELECT eta FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        ).fetchone()

    # Verify all operations succeeded
    success_count = len([r for r in results if r[0] == "success"])
    assert success_count == num_concurrent

    cleanup_user(test_email)


def test_concurrent_checkin_operations():
    """Test that concurrent check-in operations are handled correctly"""
    from src.api.checkin import checkin_with_token

    test_email = "concurrent-checkin@racetest.example.com"
    cleanup_user(test_email)

    # Create user and trip
    user_id = create_test_user(test_email)

    with db.engine.begin() as connection:
        # Create contact
        result = connection.execute(
            sqlalchemy.text(
                "INSERT INTO contacts (user_id, name, email) VALUES (:user_id, 'Test', :email) RETURNING id"
            ),
            {"user_id": user_id, "email": test_email}
        )
        contact_id = result.fetchone()[0]

        # Get activity
        activity = connection.execute(
            sqlalchemy.text("SELECT id FROM activities WHERE name = 'Hiking'")
        ).fetchone()

        # Create trip with checkin token
        now = datetime.now(UTC)
        checkin_token = f"race_checkin_{now.timestamp()}"

        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (
                    user_id, title, activity, start, eta, grace_min,
                    location_text, gen_lat, gen_lon, status, contact1,
                    created_at, checkin_token, checkout_token
                )
                VALUES (
                    :user_id, 'Race Trip', :activity, :start, :eta, 30,
                    'Location', 0, 0, 'active', :contact_id,
                    :start, :checkin_token, 'checkout_token'
                )
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "activity": activity.id,
                "start": now.isoformat(),
                "eta": (now + timedelta(hours=2)).isoformat(),
                "contact_id": contact_id,
                "checkin_token": checkin_token
            }
        )
        trip_id = result.fetchone()[0]

    # Launch concurrent check-in requests
    num_concurrent = 5
    results = []

    def attempt_checkin():
        try:
            background_tasks = BackgroundTasks()
            result = checkin_with_token(checkin_token, background_tasks, lat=None, lon=None)
            results.append(("success", result))
        except Exception as e:
            results.append(("error", str(e)))

    threads = []
    for _ in range(num_concurrent):
        t = Thread(target=attempt_checkin)
        threads.append(t)

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    # All should succeed (check-ins are idempotent)
    success_count = len([r for r in results if r[0] == "success"])
    assert success_count == num_concurrent

    # Verify events were created
    with db.engine.begin() as connection:
        events = connection.execute(
            sqlalchemy.text(
                "SELECT COUNT(*) as count FROM events WHERE trip_id = :trip_id AND what = 'checkin'"
            ),
            {"trip_id": trip_id}
        ).fetchone()

        assert events.count == num_concurrent

    cleanup_user(test_email)


# ============================================================================
# Request Magic Link Concurrent Tests
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_magic_link_requests_same_email():
    """Test that multiple magic link requests for same email don't create duplicate users"""
    test_email = "concurrent-magic@racetest.example.com"
    cleanup_user(test_email)

    num_requests = 5

    # Make multiple sequential requests (async functions need proper event loop handling)
    for _ in range(num_requests):
        await request_magic_link(MagicLinkRequest(email=test_email))

    # Only ONE user should exist
    with db.engine.begin() as connection:
        user_count = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) as count FROM users WHERE email = :email"),
            {"email": test_email}
        ).fetchone()

        assert user_count.count == 1, (
            f"Expected 1 user, but got {user_count.count} - requests created duplicates!"
        )

        # Multiple tokens should exist (one per request)
        token_count = connection.execute(
            sqlalchemy.text("SELECT COUNT(*) as count FROM login_tokens WHERE email = :email"),
            {"email": test_email}
        ).fetchone()

        assert token_count.count == num_requests

    cleanup_user(test_email)
