"""Tests for friends API endpoints"""
import pytest
import sqlalchemy
from datetime import datetime, timedelta
from fastapi import BackgroundTasks, HTTPException

from src import database as db
from src.api.friends import (
    FriendResponse,
    FriendInviteResponse,
    FriendInvitePreview,
    PendingInviteResponse,
    create_invite,
    get_invite_preview,
    accept_invite,
    get_pending_invites,
    get_friends,
    get_friend,
    remove_friend,
)


def _create_test_user(connection, email: str, first_name: str = "Test", last_name: str = "User") -> int:
    """Create a test user and return their ID."""
    # Clean up existing data first
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
            "created_at": datetime.utcnow()
        }
    )
    return result.fetchone()[0]


def _cleanup_user(connection, user_id: int):
    """Clean up a test user and all related data."""
    connection.execute(
        sqlalchemy.text("DELETE FROM friend_invites WHERE inviter_id = :user_id OR accepted_by = :user_id"),
        {"user_id": user_id}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM friendships WHERE user_id_1 = :user_id OR user_id_2 = :user_id"),
        {"user_id": user_id}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
        {"user_id": user_id}
    )


# ==================== Invite Tests ====================

def test_create_invite():
    """Test creating a friend invite (permanent, reusable)."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "inviter@test.com", "Alice", "Inviter")

    try:
        invite = create_invite(user_id=user_id)

        assert isinstance(invite, FriendInviteResponse)
        assert invite.token is not None
        assert len(invite.token) > 20  # URL-safe tokens are reasonably long
        assert "api.homeboundapp.com/f/" in invite.invite_url
        # Permanent invites have no expiry
        assert invite.expires_at is None

        # Verify invite was stored in database
        with db.engine.begin() as connection:
            stored = connection.execute(
                sqlalchemy.text("SELECT * FROM friend_invites WHERE token = :token"),
                {"token": invite.token}
            ).fetchone()
            assert stored is not None
            assert stored.inviter_id == user_id
            assert stored.use_count == 0
            # Permanent invites have NULL max_uses and expires_at
            assert stored.max_uses is None
            assert stored.expires_at is None
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)


def test_create_invite_returns_existing():
    """Test that calling create_invite returns existing permanent invite."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "reuse@test.com", "Reuse", "Test")

    try:
        # Create first invite
        invite1 = create_invite(user_id=user_id)
        token1 = invite1.token

        # Calling again should return the same invite
        invite2 = create_invite(user_id=user_id)
        assert invite2.token == token1  # Same token returned
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)


def test_create_invite_regenerate():
    """Test that regenerate=True creates a new invite and invalidates the old one."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "regen@test.com", "Regen", "Test")

    try:
        # Create first invite
        invite1 = create_invite(user_id=user_id)
        token1 = invite1.token

        # Regenerate should create a new invite with different token
        invite2 = create_invite(regenerate=True, user_id=user_id)
        assert invite2.token != token1  # Different token

        # Old token should no longer exist
        with db.engine.begin() as connection:
            old_invite = connection.execute(
                sqlalchemy.text("SELECT * FROM friend_invites WHERE token = :token"),
                {"token": token1}
            ).fetchone()
            assert old_invite is None  # Old invite was deleted

            # New invite exists
            new_invite = connection.execute(
                sqlalchemy.text("SELECT * FROM friend_invites WHERE token = :token"),
                {"token": invite2.token}
            ).fetchone()
            assert new_invite is not None
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)


def test_get_invite_preview():
    """Test getting invite preview (public endpoint)."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "preview@test.com", "Bob", "Preview")

    try:
        # Create invite
        invite = create_invite(user_id=user_id)

        # Get preview
        preview = get_invite_preview(invite.token)

        assert isinstance(preview, FriendInvitePreview)
        assert preview.inviter_first_name == "Bob"
        assert preview.is_valid is True
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)


def test_get_invite_preview_expired():
    """Test that expired invites show is_valid=False."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "expired@test.com", "Charlie", "Expired")

        # Create an expired invite directly
        expired_time = datetime.utcnow() - timedelta(days=1)
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO friend_invites (inviter_id, token, expires_at)
                VALUES (:inviter_id, :token, :expires_at)
                """
            ),
            {"inviter_id": user_id, "token": "expired_token_123", "expires_at": expired_time}
        )

    try:
        preview = get_invite_preview("expired_token_123")
        assert preview.is_valid is False
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)


def test_get_invite_preview_not_found():
    """Test getting preview for nonexistent invite."""
    with pytest.raises(HTTPException) as exc_info:
        get_invite_preview("nonexistent_token")
    assert exc_info.value.status_code == 404


def test_accept_invite():
    """Test accepting a friend invite."""
    with db.engine.begin() as connection:
        inviter_id = _create_test_user(connection, "inviter2@test.com", "Dave", "Inviter")
        accepter_id = _create_test_user(connection, "accepter@test.com", "Eve", "Accepter")

    try:
        # Create invite
        invite = create_invite(user_id=inviter_id)

        # Accept invite
        friend = accept_invite(invite.token, BackgroundTasks(), user_id=accepter_id)

        assert isinstance(friend, FriendResponse)
        assert friend.user_id == inviter_id
        assert friend.first_name == "Dave"
        assert friend.last_name == "Inviter"

        # Verify friendship was created
        with db.engine.begin() as connection:
            id1, id2 = min(inviter_id, accepter_id), max(inviter_id, accepter_id)
            friendship = connection.execute(
                sqlalchemy.text(
                    "SELECT * FROM friendships WHERE user_id_1 = :id1 AND user_id_2 = :id2"
                ),
                {"id1": id1, "id2": id2}
            ).fetchone()
            assert friendship is not None

            # Verify invite was marked as used
            used_invite = connection.execute(
                sqlalchemy.text("SELECT * FROM friend_invites WHERE token = :token"),
                {"token": invite.token}
            ).fetchone()
            assert used_invite.use_count == 1
            assert used_invite.accepted_by == accepter_id
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, inviter_id)
            _cleanup_user(connection, accepter_id)


def test_accept_own_invite_fails():
    """Test that accepting your own invite fails."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "selfaccept@test.com", "Frank", "Self")

    try:
        invite = create_invite(user_id=user_id)

        with pytest.raises(HTTPException) as exc_info:
            accept_invite(invite.token, BackgroundTasks(), user_id=user_id)
        assert exc_info.value.status_code == 400
        assert "own invite" in exc_info.value.detail.lower()
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)


def test_accept_expired_invite_fails():
    """Test that accepting an expired invite fails."""
    with db.engine.begin() as connection:
        inviter_id = _create_test_user(connection, "expiredinviter@test.com", "Grace", "Inviter")
        accepter_id = _create_test_user(connection, "expiredaccepter@test.com", "Henry", "Accepter")

        # Create an expired invite
        expired_time = datetime.utcnow() - timedelta(days=1)
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO friend_invites (inviter_id, token, expires_at)
                VALUES (:inviter_id, :token, :expires_at)
                """
            ),
            {"inviter_id": inviter_id, "token": "expired_accept_token", "expires_at": expired_time}
        )

    try:
        with pytest.raises(HTTPException) as exc_info:
            accept_invite("expired_accept_token", BackgroundTasks(), user_id=accepter_id)
        assert exc_info.value.status_code == 410
        assert "expired" in exc_info.value.detail.lower()
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, inviter_id)
            _cleanup_user(connection, accepter_id)


def test_accept_already_friends_fails():
    """Test that accepting an invite when already friends fails."""
    with db.engine.begin() as connection:
        inviter_id = _create_test_user(connection, "alreadyfriend1@test.com", "Ivy", "One")
        accepter_id = _create_test_user(connection, "alreadyfriend2@test.com", "Jack", "Two")

        # Create existing friendship
        id1, id2 = min(inviter_id, accepter_id), max(inviter_id, accepter_id)
        connection.execute(
            sqlalchemy.text(
                "INSERT INTO friendships (user_id_1, user_id_2) VALUES (:id1, :id2)"
            ),
            {"id1": id1, "id2": id2}
        )

    try:
        invite = create_invite(user_id=inviter_id)

        with pytest.raises(HTTPException) as exc_info:
            accept_invite(invite.token, BackgroundTasks(), user_id=accepter_id)
        assert exc_info.value.status_code == 409
        assert "already friends" in exc_info.value.detail.lower()
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, inviter_id)
            _cleanup_user(connection, accepter_id)


# ==================== Pending Invites Tests ====================

def test_get_pending_invites():
    """Test getting list of invites (now returns permanent invite)."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "pending@test.com", "Kate", "Pending")

    try:
        # Create invite (calling twice returns the same permanent invite)
        create_invite(user_id=user_id)
        create_invite(user_id=user_id)

        pending = get_pending_invites(user_id=user_id)

        assert isinstance(pending, list)
        # Only 1 permanent invite (reused)
        assert len(pending) == 1
        assert isinstance(pending[0], PendingInviteResponse)
        # Permanent invites have status "active"
        assert pending[0].status == "active"
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)


def test_pending_invites_shows_accepted():
    """Test that permanent invite remains active after acceptance."""
    with db.engine.begin() as connection:
        inviter_id = _create_test_user(connection, "pendinginviter@test.com", "Leo", "Inviter")
        accepter_id = _create_test_user(connection, "pendingaccepter@test.com", "Mia", "Accepter")

    try:
        invite = create_invite(user_id=inviter_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=accepter_id)

        pending = get_pending_invites(user_id=inviter_id)

        assert len(pending) == 1
        # Permanent invites stay "active" even after being used
        assert pending[0].status == "active"
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, inviter_id)
            _cleanup_user(connection, accepter_id)


# ==================== Friends List Tests ====================

def test_get_friends():
    """Test getting list of friends."""
    with db.engine.begin() as connection:
        user1_id = _create_test_user(connection, "friend1@test.com", "Noah", "Friend1")
        user2_id = _create_test_user(connection, "friend2@test.com", "Olivia", "Friend2")

    try:
        # Create friendship via invite
        invite = create_invite(user_id=user1_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=user2_id)

        # Both users should see each other as friends
        friends1 = get_friends(user_id=user1_id)
        friends2 = get_friends(user_id=user2_id)

        assert len(friends1) == 1
        assert friends1[0].user_id == user2_id
        assert friends1[0].first_name == "Olivia"

        assert len(friends2) == 1
        assert friends2[0].user_id == user1_id
        assert friends2[0].first_name == "Noah"
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user1_id)
            _cleanup_user(connection, user2_id)


def test_get_friends_empty():
    """Test getting friends when user has none."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "nofriends@test.com", "Paul", "Lonely")

    try:
        friends = get_friends(user_id=user_id)
        assert friends == []
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)


def test_get_friend_profile():
    """Test getting a specific friend's profile."""
    with db.engine.begin() as connection:
        user1_id = _create_test_user(connection, "profile1@test.com", "Quinn", "Profile1")
        user2_id = _create_test_user(connection, "profile2@test.com", "Rose", "Profile2")

    try:
        invite = create_invite(user_id=user1_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=user2_id)

        friend = get_friend(user2_id, user_id=user1_id)

        assert isinstance(friend, FriendResponse)
        assert friend.user_id == user2_id
        assert friend.first_name == "Rose"
        assert friend.last_name == "Profile2"
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user1_id)
            _cleanup_user(connection, user2_id)


def test_get_friend_not_friends():
    """Test getting profile of non-friend fails."""
    with db.engine.begin() as connection:
        user1_id = _create_test_user(connection, "notfriend1@test.com", "Sam", "NotFriend1")
        user2_id = _create_test_user(connection, "notfriend2@test.com", "Tina", "NotFriend2")

    try:
        with pytest.raises(HTTPException) as exc_info:
            get_friend(user2_id, user_id=user1_id)
        assert exc_info.value.status_code == 404
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user1_id)
            _cleanup_user(connection, user2_id)


# ==================== Remove Friend Tests ====================

def test_remove_friend():
    """Test removing a friend."""
    with db.engine.begin() as connection:
        user1_id = _create_test_user(connection, "remove1@test.com", "Uma", "Remove1")
        user2_id = _create_test_user(connection, "remove2@test.com", "Victor", "Remove2")

    try:
        # Create friendship
        invite = create_invite(user_id=user1_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=user2_id)

        # Remove friend
        result = remove_friend(user2_id, user_id=user1_id)
        assert result["ok"] is True

        # Verify friendship is removed
        friends = get_friends(user_id=user1_id)
        assert len(friends) == 0

        friends2 = get_friends(user_id=user2_id)
        assert len(friends2) == 0
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user1_id)
            _cleanup_user(connection, user2_id)


def test_remove_friend_not_friends():
    """Test removing non-friend fails."""
    with db.engine.begin() as connection:
        user1_id = _create_test_user(connection, "removefail1@test.com", "Wendy", "RemoveFail1")
        user2_id = _create_test_user(connection, "removefail2@test.com", "Xavier", "RemoveFail2")

    try:
        with pytest.raises(HTTPException) as exc_info:
            remove_friend(user2_id, user_id=user1_id)
        assert exc_info.value.status_code == 404
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user1_id)
            _cleanup_user(connection, user2_id)


def test_either_user_can_remove_friendship():
    """Test that either user in a friendship can remove it."""
    with db.engine.begin() as connection:
        user1_id = _create_test_user(connection, "either1@test.com", "Yuki", "Either1")
        user2_id = _create_test_user(connection, "either2@test.com", "Zara", "Either2")

    try:
        # Create friendship (user1 invites, user2 accepts)
        invite = create_invite(user_id=user1_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=user2_id)

        # User2 removes the friendship (not the inviter)
        result = remove_friend(user1_id, user_id=user2_id)
        assert result["ok"] is True

        # Verify friendship is removed for both
        assert len(get_friends(user_id=user1_id)) == 0
        assert len(get_friends(user_id=user2_id)) == 0
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user1_id)
            _cleanup_user(connection, user2_id)


# ==================== Edge Cases ====================

def test_multiple_friendships():
    """Test user can have multiple friends."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "multi@test.com", "Alex", "Multi")
        friend1_id = _create_test_user(connection, "multifriend1@test.com", "Ben", "Friend1")
        friend2_id = _create_test_user(connection, "multifriend2@test.com", "Cara", "Friend2")
        friend3_id = _create_test_user(connection, "multifriend3@test.com", "Dan", "Friend3")

    try:
        # Create friendships
        for friend_id in [friend1_id, friend2_id, friend3_id]:
            invite = create_invite(user_id=user_id)
            accept_invite(invite.token, BackgroundTasks(), user_id=friend_id)

        friends = get_friends(user_id=user_id)
        assert len(friends) == 3
        friend_names = [f.first_name for f in friends]
        assert "Ben" in friend_names
        assert "Cara" in friend_names
        assert "Dan" in friend_names
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)
            _cleanup_user(connection, friend1_id)
            _cleanup_user(connection, friend2_id)
            _cleanup_user(connection, friend3_id)


def test_permanent_invite_allows_multiple_accepts():
    """Test that permanent invites allow multiple different users to accept."""
    with db.engine.begin() as connection:
        inviter_id = _create_test_user(connection, "maxuses@test.com", "Max", "Uses")
        accepter1_id = _create_test_user(connection, "accepter1@test.com", "First", "Accepter")
        accepter2_id = _create_test_user(connection, "accepter2@test.com", "Second", "Accepter")

    try:
        # Create permanent invite (max_uses=NULL = unlimited)
        invite = create_invite(user_id=inviter_id)

        # First user accepts successfully
        accept_invite(invite.token, BackgroundTasks(), user_id=accepter1_id)

        # Second user should also succeed (permanent invites have unlimited uses)
        friend = accept_invite(invite.token, BackgroundTasks(), user_id=accepter2_id)
        assert friend.user_id == inviter_id
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, inviter_id)
            _cleanup_user(connection, accepter1_id)
            _cleanup_user(connection, accepter2_id)


def test_permanent_invite_preview_stays_valid_after_use():
    """Test that permanent invite preview stays valid after acceptance."""
    with db.engine.begin() as connection:
        inviter_id = _create_test_user(connection, "usedupinviter@test.com", "Used", "Inviter")
        accepter_id = _create_test_user(connection, "usedupaccepter@test.com", "Up", "Accepter")

    try:
        invite = create_invite(user_id=inviter_id)

        # Preview before acceptance should be valid
        preview_before = get_invite_preview(invite.token)
        assert preview_before.is_valid is True

        # Accept the invite
        accept_invite(invite.token, BackgroundTasks(), user_id=accepter_id)

        # Preview after acceptance should STILL be valid (permanent invites)
        preview_after = get_invite_preview(invite.token)
        assert preview_after.is_valid is True
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, inviter_id)
            _cleanup_user(connection, accepter_id)


def test_accept_nonexistent_invite_fails():
    """Test accepting a nonexistent invite returns 404."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "acceptnonexist@test.com", "Accept", "Nothing")

    try:
        with pytest.raises(HTTPException) as exc_info:
            accept_invite("totally_fake_token_12345", BackgroundTasks(), user_id=user_id)
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)


def test_pending_invites_shows_expired():
    """Test that expired invites show correct status in pending list."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "pendingexpired@test.com", "Pending", "Expired")

        # Create an expired invite directly
        expired_time = datetime.utcnow() - timedelta(days=1)
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO friend_invites (inviter_id, token, expires_at, created_at)
                VALUES (:inviter_id, :token, :expires_at, :created_at)
                """
            ),
            {
                "inviter_id": user_id,
                "token": "pending_expired_token",
                "expires_at": expired_time,
                "created_at": datetime.utcnow() - timedelta(days=8)
            }
        )

    try:
        pending = get_pending_invites(user_id=user_id)
        assert len(pending) == 1
        assert pending[0].status == "expired"
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)


def test_friend_profile_includes_all_fields():
    """Test that friend profile response includes all expected fields."""
    with db.engine.begin() as connection:
        user1_id = _create_test_user(connection, "fullprofile1@test.com", "Full", "Profile1")
        user2_id = _create_test_user(connection, "fullprofile2@test.com", "Complete", "Profile2")

        # Add profile photo to user2
        connection.execute(
            sqlalchemy.text("UPDATE users SET profile_photo_url = :url WHERE id = :id"),
            {"url": "https://example.com/photo.jpg", "id": user2_id}
        )

    try:
        invite = create_invite(user_id=user1_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=user2_id)

        friend = get_friend(user2_id, user_id=user1_id)

        assert friend.user_id == user2_id
        assert friend.first_name == "Complete"
        assert friend.last_name == "Profile2"
        assert friend.profile_photo_url == "https://example.com/photo.jpg"
        assert friend.member_since is not None
        assert friend.friendship_since is not None
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user1_id)
            _cleanup_user(connection, user2_id)


def test_create_invite_returns_same_permanent_invite():
    """Test that calling create_invite returns the same permanent invite."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "multiinvite@test.com", "Multi", "Invite")

    try:
        invite1 = create_invite(user_id=user_id)
        invite2 = create_invite(user_id=user_id)
        invite3 = create_invite(user_id=user_id)

        # All invites should have the same token (permanent, reused)
        assert invite1.token == invite2.token
        assert invite2.token == invite3.token

        pending = get_pending_invites(user_id=user_id)
        # Only 1 permanent invite exists
        assert len(pending) == 1
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)


def test_remove_friend_idempotent():
    """Test that removing a friend twice fails the second time."""
    with db.engine.begin() as connection:
        user1_id = _create_test_user(connection, "idempotent1@test.com", "Idem", "Potent1")
        user2_id = _create_test_user(connection, "idempotent2@test.com", "Idem", "Potent2")

    try:
        invite = create_invite(user_id=user1_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=user2_id)

        # First removal succeeds
        result = remove_friend(user2_id, user_id=user1_id)
        assert result["ok"] is True

        # Second removal fails (no longer friends)
        with pytest.raises(HTTPException) as exc_info:
            remove_friend(user2_id, user_id=user1_id)
        assert exc_info.value.status_code == 404
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user1_id)
            _cleanup_user(connection, user2_id)


def test_friendship_symmetry():
    """Test that friendships work symmetrically for both users."""
    with db.engine.begin() as connection:
        user1_id = _create_test_user(connection, "symmetry1@test.com", "Sym", "One")
        user2_id = _create_test_user(connection, "symmetry2@test.com", "Sym", "Two")

    try:
        invite = create_invite(user_id=user1_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=user2_id)

        # Both users can see each other
        friend1 = get_friend(user2_id, user_id=user1_id)
        friend2 = get_friend(user1_id, user_id=user2_id)

        assert friend1.user_id == user2_id
        assert friend2.user_id == user1_id

        # Both users can get their friends list
        friends1 = get_friends(user_id=user1_id)
        friends2 = get_friends(user_id=user2_id)

        assert len(friends1) == 1
        assert len(friends2) == 1
        assert friends1[0].user_id == user2_id
        assert friends2[0].user_id == user1_id
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user1_id)
            _cleanup_user(connection, user2_id)


def test_inviter_user_not_found():
    """Test that invite preview handles deleted inviter gracefully."""
    with db.engine.begin() as connection:
        inviter_id = _create_test_user(connection, "deletedinviter@test.com", "Deleted", "Inviter")

        # Create invite
        invite_result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO friend_invites (inviter_id, token, expires_at)
                VALUES (:inviter_id, :token, :expires_at)
                RETURNING token
                """
            ),
            {
                "inviter_id": inviter_id,
                "token": "orphaned_invite_token",
                "expires_at": datetime.utcnow() + timedelta(days=7)
            }
        )
        token = invite_result.fetchone()[0]

        # Delete the inviter (this should cascade delete the invite due to FK)
        connection.execute(
            sqlalchemy.text("DELETE FROM friend_invites WHERE inviter_id = :inviter_id"),
            {"inviter_id": inviter_id}
        )
        connection.execute(
            sqlalchemy.text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": inviter_id}
        )

    # Preview should return 404 since invite was cascade deleted
    with pytest.raises(HTTPException) as exc_info:
        get_invite_preview(token)
    assert exc_info.value.status_code == 404


def test_friend_with_empty_name():
    """Test friend profile handles users with empty names."""
    with db.engine.begin() as connection:
        user1_id = _create_test_user(connection, "emptyname1@test.com", "", "")
        user2_id = _create_test_user(connection, "emptyname2@test.com", "Has", "Name")

    try:
        invite = create_invite(user_id=user1_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=user2_id)

        # Getting friend with empty name should return empty strings
        friend = get_friend(user1_id, user_id=user2_id)
        assert friend.first_name == ""
        assert friend.last_name == ""
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user1_id)
            _cleanup_user(connection, user2_id)


def test_accept_invite_same_token_twice_by_same_user():
    """Test that same user can't accept same invite twice (already friends)."""
    with db.engine.begin() as connection:
        inviter_id = _create_test_user(connection, "sametwice1@test.com", "Same", "Twice1")
        accepter_id = _create_test_user(connection, "sametwice2@test.com", "Same", "Twice2")

    try:
        invite = create_invite(user_id=inviter_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=accepter_id)

        # Try to accept again with new invite - should fail (already friends)
        invite2 = create_invite(user_id=inviter_id)
        with pytest.raises(HTTPException) as exc_info:
            accept_invite(invite2.token, BackgroundTasks(), user_id=accepter_id)
        assert exc_info.value.status_code == 409
        assert "already friends" in exc_info.value.detail.lower()
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, inviter_id)
            _cleanup_user(connection, accepter_id)


def test_pending_invites_empty():
    """Test pending invites returns empty list when no invites."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "noinvites@test.com", "No", "Invites")

    try:
        pending = get_pending_invites(user_id=user_id)
        assert pending == []
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)


def test_friends_list_ordered_by_friendship_date():
    """Test that friends list is ordered by friendship date (most recent first)."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "ordered@test.com", "Order", "Main")
        friend1_id = _create_test_user(connection, "ordered1@test.com", "First", "Friend")
        friend2_id = _create_test_user(connection, "ordered2@test.com", "Second", "Friend")
        friend3_id = _create_test_user(connection, "ordered3@test.com", "Third", "Friend")

    try:
        # Create friendships in order
        invite1 = create_invite(user_id=user_id)
        accept_invite(invite1.token, BackgroundTasks(), user_id=friend1_id)

        invite2 = create_invite(user_id=user_id)
        accept_invite(invite2.token, BackgroundTasks(), user_id=friend2_id)

        invite3 = create_invite(user_id=user_id)
        accept_invite(invite3.token, BackgroundTasks(), user_id=friend3_id)

        friends = get_friends(user_id=user_id)

        # Most recently added friend should be first
        assert len(friends) == 3
        assert friends[0].first_name == "Third"
        assert friends[1].first_name == "Second"
        assert friends[2].first_name == "First"
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)
            _cleanup_user(connection, friend1_id)
            _cleanup_user(connection, friend2_id)
            _cleanup_user(connection, friend3_id)


# ==================== Request Update Tests ====================

from src.api.friends import request_trip_update, get_friend_active_trips


def _create_trip_for_user(connection, user_id: int, title: str = "Test Trip", status: str = "active") -> int:
    """Helper to create a trip for testing."""
    now = datetime.utcnow()
    # Get a valid activity ID from the database
    activity = connection.execute(
        sqlalchemy.text("SELECT id FROM activities LIMIT 1")
    ).fetchone()
    activity_id = activity[0] if activity else 1

    result = connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO trips (user_id, title, activity, start, eta, grace_min, location_text,
                              gen_lat, gen_lon, status, created_at)
            VALUES (:user_id, :title, :activity_id, :start, :eta, 30, 'Test Location',
                   37.7749, -122.4194, :status, :created_at)
            RETURNING id
            """
        ),
        {
            "user_id": user_id,
            "title": title,
            "activity_id": activity_id,
            "start": now,
            "eta": now + timedelta(hours=2),
            "status": status,
            "created_at": now
        }
    )
    return result.fetchone()[0]


def _add_friend_to_trip(connection, trip_id: int, friend_user_id: int):
    """Helper to add a friend as a safety contact for a trip."""
    connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO trip_safety_contacts (trip_id, friend_user_id)
            VALUES (:trip_id, :friend_user_id)
            """
        ),
        {"trip_id": trip_id, "friend_user_id": friend_user_id}
    )


def _cleanup_trip(connection, trip_id: int):
    """Helper to clean up a trip."""
    connection.execute(
        sqlalchemy.text("DELETE FROM update_requests WHERE trip_id = :trip_id"),
        {"trip_id": trip_id}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM trip_safety_contacts WHERE trip_id = :trip_id"),
        {"trip_id": trip_id}
    )
    connection.execute(
        sqlalchemy.text("UPDATE trips SET last_checkin = NULL WHERE id = :trip_id"),
        {"trip_id": trip_id}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM events WHERE trip_id = :trip_id"),
        {"trip_id": trip_id}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM live_locations WHERE trip_id = :trip_id"),
        {"trip_id": trip_id}
    )
    connection.execute(
        sqlalchemy.text("DELETE FROM trips WHERE id = :trip_id"),
        {"trip_id": trip_id}
    )


def test_request_update_success():
    """Test successfully requesting an update from trip owner."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "tripowner@test.com", "Trip", "Owner")
        friend_id = _create_test_user(connection, "tripfriend@test.com", "Trip", "Friend")

    trip_id = None
    try:
        # Create friendship
        invite = create_invite(user_id=owner_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=friend_id)

        # Create trip and add friend as safety contact
        with db.engine.begin() as connection:
            trip_id = _create_trip_for_user(connection, owner_id, "Mountain Hike")
            _add_friend_to_trip(connection, trip_id, friend_id)

        # Request update
        result = request_trip_update(trip_id, BackgroundTasks(), user_id=friend_id)

        assert result.ok is True
        # On success, cooldown_remaining_seconds shows the 10min cooldown for next request
    finally:
        with db.engine.begin() as connection:
            if trip_id:
                _cleanup_trip(connection, trip_id)
            _cleanup_user(connection, owner_id)
            _cleanup_user(connection, friend_id)


def test_request_update_not_friend():
    """Test that non-friend cannot request update."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "notfriendowner@test.com", "Not", "Friend")
        stranger_id = _create_test_user(connection, "stranger@test.com", "Random", "Stranger")

    trip_id = None
    try:
        # Create trip (no friendship, stranger not a safety contact)
        with db.engine.begin() as connection:
            trip_id = _create_trip_for_user(connection, owner_id, "Solo Trip")

        # Stranger tries to request update - should fail
        with pytest.raises(HTTPException) as exc_info:
            request_trip_update(trip_id, BackgroundTasks(), user_id=stranger_id)
        assert exc_info.value.status_code == 403
    finally:
        with db.engine.begin() as connection:
            if trip_id:
                _cleanup_trip(connection, trip_id)
            _cleanup_user(connection, owner_id)
            _cleanup_user(connection, stranger_id)


def test_request_update_cooldown():
    """Test that request update has a cooldown period."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "cooldownowner@test.com", "Cooldown", "Owner")
        friend_id = _create_test_user(connection, "cooldownfriend@test.com", "Cooldown", "Friend")

    trip_id = None
    try:
        # Create friendship
        invite = create_invite(user_id=owner_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=friend_id)

        # Create trip and add friend as safety contact
        with db.engine.begin() as connection:
            trip_id = _create_trip_for_user(connection, owner_id, "Cooldown Trip")
            _add_friend_to_trip(connection, trip_id, friend_id)

        # First request - should succeed
        result1 = request_trip_update(trip_id, BackgroundTasks(), user_id=friend_id)
        assert result1.ok is True

        # Second request immediately - should fail with cooldown
        result2 = request_trip_update(trip_id, BackgroundTasks(), user_id=friend_id)
        assert result2.ok is False
        assert result2.cooldown_remaining_seconds is not None
        assert result2.cooldown_remaining_seconds > 0
    finally:
        with db.engine.begin() as connection:
            if trip_id:
                _cleanup_trip(connection, trip_id)
            _cleanup_user(connection, owner_id)
            _cleanup_user(connection, friend_id)


def test_request_update_trip_not_found():
    """Test request update for non-existent trip."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "notfoundtrip@test.com", "NotFound", "Trip")

    try:
        with pytest.raises(HTTPException) as exc_info:
            request_trip_update(999999, BackgroundTasks(), user_id=user_id)
        # API returns 403 (not a safety contact) for non-existent trips
        assert exc_info.value.status_code == 403
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)


def test_request_update_completed_trip():
    """Test that cannot request update for completed trip."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "completedowner@test.com", "Completed", "Owner")
        friend_id = _create_test_user(connection, "completedfriend@test.com", "Completed", "Friend")

    trip_id = None
    try:
        # Create friendship
        invite = create_invite(user_id=owner_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=friend_id)

        # Create completed trip and add friend
        with db.engine.begin() as connection:
            trip_id = _create_trip_for_user(connection, owner_id, "Done Trip", status="completed")
            _add_friend_to_trip(connection, trip_id, friend_id)

        # Request update for completed trip - should fail
        with pytest.raises(HTTPException) as exc_info:
            request_trip_update(trip_id, BackgroundTasks(), user_id=friend_id)
        # API returns 404 for non-active trips ("Trip not found or not active")
        assert exc_info.value.status_code == 404
    finally:
        with db.engine.begin() as connection:
            if trip_id:
                _cleanup_trip(connection, trip_id)
            _cleanup_user(connection, owner_id)
            _cleanup_user(connection, friend_id)


# ==================== Active Trips with Check-in Locations Tests ====================

def test_get_active_friend_trips_basic():
    """Test getting active trips for friends."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "activeowner@test.com", "Active", "Owner")
        friend_id = _create_test_user(connection, "activefriend@test.com", "Active", "Friend")

    trip_id = None
    try:
        # Create friendship
        invite = create_invite(user_id=owner_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=friend_id)

        # Create active trip and add friend as safety contact
        with db.engine.begin() as connection:
            trip_id = _create_trip_for_user(connection, owner_id, "Active Trip")
            _add_friend_to_trip(connection, trip_id, friend_id)

        # Get active trips as friend
        trips = get_friend_active_trips(user_id=friend_id)

        assert len(trips) >= 1
        trip = next((t for t in trips if t.id == trip_id), None)
        assert trip is not None
        assert trip.title == "Active Trip"
        assert trip.owner.first_name == "Active"
    finally:
        with db.engine.begin() as connection:
            if trip_id:
                _cleanup_trip(connection, trip_id)
            _cleanup_user(connection, owner_id)
            _cleanup_user(connection, friend_id)


def test_get_active_friend_trips_with_checkin_locations():
    """Test that active trips include check-in locations when owner allows."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "checkinowner@test.com", "Checkin", "Owner")
        friend_id = _create_test_user(connection, "checkinfriend@test.com", "Checkin", "Friend")

    trip_id = None
    try:
        # Create friendship
        invite = create_invite(user_id=owner_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=friend_id)

        # Create active trip with friend as safety contact
        with db.engine.begin() as connection:
            trip_id = _create_trip_for_user(connection, owner_id, "Checkin Trip")
            _add_friend_to_trip(connection, trip_id, friend_id)

            # Add a check-in event with location
            now = datetime.utcnow()
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO events (user_id, trip_id, what, timestamp, lat, lon)
                    VALUES (:user_id, :trip_id, 'checkin', :timestamp, :lat, :lon)
                    """
                ),
                {
                    "user_id": owner_id,
                    "trip_id": trip_id,
                    "timestamp": now,
                    "lat": 37.7749,
                    "lon": -122.4194
                }
            )

        # Get active trips as friend
        trips = get_friend_active_trips(user_id=friend_id)

        trip = next((t for t in trips if t.id == trip_id), None)
        assert trip is not None

        # Check that check-in locations are included
        assert trip.checkin_locations is not None
        assert len(trip.checkin_locations) >= 1
        assert trip.checkin_locations[0].latitude == 37.7749
        assert trip.checkin_locations[0].longitude == -122.4194
    finally:
        with db.engine.begin() as connection:
            if trip_id:
                _cleanup_trip(connection, trip_id)
            _cleanup_user(connection, owner_id)
            _cleanup_user(connection, friend_id)


def test_get_active_friend_trips_no_trips():
    """Test getting active trips when no friends have active trips."""
    with db.engine.begin() as connection:
        user_id = _create_test_user(connection, "noactivetrips@test.com", "NoActive", "Trips")

    try:
        trips = get_friend_active_trips(user_id=user_id)
        assert trips == []
    finally:
        with db.engine.begin() as connection:
            _cleanup_user(connection, user_id)


def test_get_active_friend_trips_only_active_status():
    """Test that active and planned trips are returned, but not completed."""
    with db.engine.begin() as connection:
        owner_id = _create_test_user(connection, "statusowner@test.com", "Status", "Owner")
        friend_id = _create_test_user(connection, "statusfriend@test.com", "Status", "Friend")

    active_trip_id = None
    planned_trip_id = None
    completed_trip_id = None
    try:
        # Create friendship
        invite = create_invite(user_id=owner_id)
        accept_invite(invite.token, BackgroundTasks(), user_id=friend_id)

        # Create trips with different statuses
        with db.engine.begin() as connection:
            active_trip_id = _create_trip_for_user(connection, owner_id, "Active Trip", status="active")
            _add_friend_to_trip(connection, active_trip_id, friend_id)

            planned_trip_id = _create_trip_for_user(connection, owner_id, "Planned Trip", status="planned")
            _add_friend_to_trip(connection, planned_trip_id, friend_id)

            completed_trip_id = _create_trip_for_user(connection, owner_id, "Completed Trip", status="completed")
            _add_friend_to_trip(connection, completed_trip_id, friend_id)

        # Get active trips - should see active and planned, but not completed
        trips = get_friend_active_trips(user_id=friend_id)

        trip_ids = [t.id for t in trips]
        assert active_trip_id in trip_ids
        assert planned_trip_id in trip_ids  # Planned trips are included for friends
        assert completed_trip_id not in trip_ids
    finally:
        with db.engine.begin() as connection:
            if active_trip_id:
                _cleanup_trip(connection, active_trip_id)
            if planned_trip_id:
                _cleanup_trip(connection, planned_trip_id)
            if completed_trip_id:
                _cleanup_trip(connection, completed_trip_id)
            _cleanup_user(connection, owner_id)
            _cleanup_user(connection, friend_id)
