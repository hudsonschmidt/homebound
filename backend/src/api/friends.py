"""Friend management endpoints"""

import asyncio
import secrets
from datetime import datetime, timedelta

import sqlalchemy
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from src import database as db
from src.api import auth
from src.services.notifications import send_friend_request_accepted_push

router = APIRouter(
    prefix="/api/v1/friends",
    tags=["friends"],
)

# How long invite tokens are valid (7 days)
INVITE_EXPIRY_DAYS = 7


# Response models
class FriendResponse(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    profile_photo_url: str | None
    member_since: str
    friendship_since: str


class FriendInviteResponse(BaseModel):
    token: str
    invite_url: str
    expires_at: str


class FriendInvitePreview(BaseModel):
    inviter_first_name: str
    inviter_profile_photo_url: str | None
    inviter_member_since: str
    expires_at: str
    is_valid: bool


class PendingInviteResponse(BaseModel):
    id: int
    token: str
    created_at: str
    expires_at: str
    status: str  # "pending", "accepted", "expired"
    accepted_by_name: str | None


def _generate_invite_token() -> str:
    """Generate a URL-safe invite token."""
    return secrets.token_urlsafe(32)


def _get_friendship(connection, user_id: int, other_user_id: int):
    """Check if two users are friends. Returns the friendship row or None."""
    # Ensure user_id_1 < user_id_2 for the query
    id1, id2 = min(user_id, other_user_id), max(user_id, other_user_id)
    return connection.execute(
        sqlalchemy.text(
            """
            SELECT id, user_id_1, user_id_2, created_at
            FROM friendships
            WHERE user_id_1 = :id1 AND user_id_2 = :id2
            """
        ),
        {"id1": id1, "id2": id2}
    ).fetchone()


def _create_friendship(connection, user_id: int, other_user_id: int) -> None:
    """Create a friendship between two users."""
    # Ensure user_id_1 < user_id_2 for the constraint
    id1, id2 = min(user_id, other_user_id), max(user_id, other_user_id)
    connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO friendships (user_id_1, user_id_2)
            VALUES (:id1, :id2)
            """
        ),
        {"id1": id1, "id2": id2}
    )


# ==================== Invite Endpoints ====================

@router.post("/invite", response_model=FriendInviteResponse)
def create_invite(user_id: int = Depends(auth.get_current_user_id)):
    """Generate a shareable friend invite link."""
    token = _generate_invite_token()
    expires_at = datetime.utcnow() + timedelta(days=INVITE_EXPIRY_DAYS)

    with db.engine.begin() as connection:
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO friend_invites (inviter_id, token, expires_at)
                VALUES (:inviter_id, :token, :expires_at)
                """
            ),
            {
                "inviter_id": user_id,
                "token": token,
                "expires_at": expires_at
            }
        )

    # Build the invite URL (will be used with universal links)
    invite_url = f"https://api.homeboundapp.com/f/{token}"

    return FriendInviteResponse(
        token=token,
        invite_url=invite_url,
        expires_at=expires_at.isoformat()
    )


@router.get("/invite/{token}", response_model=FriendInvitePreview)
def get_invite_preview(token: str):
    """Get invite details for preview before accepting (public endpoint)."""
    with db.engine.begin() as connection:
        invite = connection.execute(
            sqlalchemy.text(
                """
                SELECT fi.id, fi.inviter_id, fi.expires_at, fi.use_count, fi.max_uses,
                       u.first_name, u.profile_photo_url, u.created_at as member_since
                FROM friend_invites fi
                JOIN users u ON u.id = fi.inviter_id
                WHERE fi.token = :token
                """
            ),
            {"token": token}
        ).fetchone()

        if not invite:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invite not found"
            )

        now = datetime.utcnow()
        is_expired = invite.expires_at < now
        is_used_up = invite.use_count >= invite.max_uses
        is_valid = not is_expired and not is_used_up

        return FriendInvitePreview(
            inviter_first_name=invite.first_name or "A user",
            inviter_profile_photo_url=invite.profile_photo_url,
            inviter_member_since=invite.member_since.isoformat() if invite.member_since else "",
            expires_at=invite.expires_at.isoformat(),
            is_valid=is_valid
        )


@router.post("/invite/{token}/accept", response_model=FriendResponse)
def accept_invite(
    token: str,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Accept a friend invite and create the friendship."""
    with db.engine.begin() as connection:
        # Get the invite
        invite = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, inviter_id, expires_at, use_count, max_uses
                FROM friend_invites
                WHERE token = :token
                """
            ),
            {"token": token}
        ).fetchone()

        if not invite:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invite not found"
            )

        # Check if invite is still valid
        now = datetime.utcnow()
        if invite.expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Invite has expired"
            )

        if invite.use_count >= invite.max_uses:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Invite has already been used"
            )

        inviter_id = invite.inviter_id

        # Can't be friends with yourself
        if inviter_id == user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot accept your own invite"
            )

        # Check if already friends
        existing = _get_friendship(connection, user_id, inviter_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already friends with this user"
            )

        # Create the friendship (handle race condition where friendship was created between check and insert)
        try:
            _create_friendship(connection, user_id, inviter_id)
        except sqlalchemy.exc.IntegrityError:
            # Friendship already exists (race condition)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already friends with this user"
            )

        # Update invite usage
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE friend_invites
                SET use_count = use_count + 1,
                    accepted_by = :accepted_by,
                    accepted_at = :accepted_at
                WHERE id = :invite_id
                """
            ),
            {
                "invite_id": invite.id,
                "accepted_by": user_id,
                "accepted_at": now
            }
        )

        # Get the inviter's profile to return
        inviter = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, first_name, last_name, profile_photo_url, created_at
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": inviter_id}
        ).fetchone()

        if not inviter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inviter not found"
            )

        # Get friendship created_at
        friendship = _get_friendship(connection, user_id, inviter_id)

        # Get the accepter's name for the notification
        accepter = connection.execute(
            sqlalchemy.text(
                """
                SELECT first_name, last_name
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id}
        ).fetchone()

        accepter_name = "Someone"
        if accepter:
            accepter_name = f"{accepter.first_name or ''} {accepter.last_name or ''}".strip() or "Someone"

        # Send push notification to inviter in background
        def send_push_sync():
            asyncio.run(send_friend_request_accepted_push(
                inviter_user_id=inviter_id,
                accepter_name=accepter_name
            ))

        background_tasks.add_task(send_push_sync)

        return FriendResponse(
            user_id=inviter.id,
            first_name=inviter.first_name or "",
            last_name=inviter.last_name or "",
            profile_photo_url=inviter.profile_photo_url,
            member_since=inviter.created_at.isoformat() if inviter.created_at else "",
            friendship_since=friendship.created_at.isoformat() if friendship else ""
        )


@router.get("/invites/pending", response_model=list[PendingInviteResponse])
def get_pending_invites(user_id: int = Depends(auth.get_current_user_id)):
    """Get all invites sent by the current user with their status."""
    with db.engine.begin() as connection:
        invites = connection.execute(
            sqlalchemy.text(
                """
                SELECT fi.id, fi.token, fi.created_at, fi.expires_at,
                       fi.use_count, fi.max_uses, fi.accepted_by,
                       u.first_name as accepted_by_first_name,
                       u.last_name as accepted_by_last_name
                FROM friend_invites fi
                LEFT JOIN users u ON u.id = fi.accepted_by
                WHERE fi.inviter_id = :user_id
                ORDER BY fi.created_at DESC
                """
            ),
            {"user_id": user_id}
        ).fetchall()

        now = datetime.utcnow()
        result = []
        for inv in invites:
            # Determine status
            if inv.use_count >= inv.max_uses:
                invite_status = "accepted"
            elif inv.expires_at < now:
                invite_status = "expired"
            else:
                invite_status = "pending"

            # Build accepted_by name if available
            accepted_by_name = None
            if inv.accepted_by_first_name:
                accepted_by_name = f"{inv.accepted_by_first_name} {inv.accepted_by_last_name or ''}".strip()

            result.append(PendingInviteResponse(
                id=inv.id,
                token=inv.token,
                created_at=inv.created_at.isoformat(),
                expires_at=inv.expires_at.isoformat(),
                status=invite_status,
                accepted_by_name=accepted_by_name
            ))

        return result


# ==================== Friends List Endpoints ====================

@router.get("/", response_model=list[FriendResponse])
def get_friends(user_id: int = Depends(auth.get_current_user_id)):
    """Get all friends for the current user."""
    with db.engine.begin() as connection:
        # Query friendships where user is either user_id_1 or user_id_2
        friends = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    u.id as user_id,
                    u.first_name,
                    u.last_name,
                    u.profile_photo_url,
                    u.created_at as member_since,
                    f.created_at as friendship_since
                FROM friendships f
                JOIN users u ON (
                    (f.user_id_1 = :user_id AND u.id = f.user_id_2) OR
                    (f.user_id_2 = :user_id AND u.id = f.user_id_1)
                )
                ORDER BY f.created_at DESC
                """
            ),
            {"user_id": user_id}
        ).fetchall()

        return [
            FriendResponse(
                user_id=f.user_id,
                first_name=f.first_name or "",
                last_name=f.last_name or "",
                profile_photo_url=f.profile_photo_url,
                member_since=f.member_since.isoformat() if f.member_since else "",
                friendship_since=f.friendship_since.isoformat() if f.friendship_since else ""
            )
            for f in friends
        ]


@router.get("/{friend_user_id}", response_model=FriendResponse)
def get_friend(friend_user_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get a specific friend's profile."""
    with db.engine.begin() as connection:
        # Verify they are friends
        friendship = _get_friendship(connection, user_id, friend_user_id)
        if not friendship:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Friend not found"
            )

        # Get friend's profile
        friend = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, first_name, last_name, profile_photo_url, created_at
                FROM users
                WHERE id = :friend_id
                """
            ),
            {"friend_id": friend_user_id}
        ).fetchone()

        if not friend:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return FriendResponse(
            user_id=friend.id,
            first_name=friend.first_name or "",
            last_name=friend.last_name or "",
            profile_photo_url=friend.profile_photo_url,
            member_since=friend.created_at.isoformat() if friend.created_at else "",
            friendship_since=friendship.created_at.isoformat() if friendship.created_at else ""
        )


@router.delete("/{friend_user_id}")
def remove_friend(friend_user_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Remove a friend."""
    with db.engine.begin() as connection:
        # Verify they are friends and get the friendship
        friendship = _get_friendship(connection, user_id, friend_user_id)
        if not friendship:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Friend not found"
            )

        # Delete the friendship
        id1, id2 = min(user_id, friend_user_id), max(user_id, friend_user_id)
        connection.execute(
            sqlalchemy.text(
                """
                DELETE FROM friendships
                WHERE user_id_1 = :id1 AND user_id_2 = :id2
                """
            ),
            {"id1": id1, "id2": id2}
        )

        return {"ok": True, "message": "Friend removed"}
