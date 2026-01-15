"""Friend management endpoints"""

import asyncio
import secrets
from datetime import datetime, timedelta

import sqlalchemy
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from src import database as db
from src.api import auth
from src.services.notifications import send_data_refresh_push, send_friend_request_accepted_push

router = APIRouter(
    prefix="/api/v1/friends",
    tags=["friends"],
)

# Reusable invites are permanent (no expiry)
# Legacy one-time invites still respect their expiry


# Response models
class FriendResponse(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    profile_photo_url: str | None
    member_since: str
    friendship_since: str
    # Mini profile stats
    age: int | None = None
    achievements_count: int | None = None
    total_achievements: int | None = None  # Total available achievements for display
    total_trips: int | None = None
    total_adventure_hours: int | None = None
    favorite_activity_name: str | None = None
    favorite_activity_icon: str | None = None


class FriendInviteResponse(BaseModel):
    token: str
    invite_url: str
    expires_at: str | None = None  # None for permanent invites


class FriendInvitePreview(BaseModel):
    inviter_first_name: str
    inviter_profile_photo_url: str | None
    inviter_member_since: str
    expires_at: str | None = None  # None for permanent invites
    is_valid: bool
    is_own_invite: bool = False  # True if the viewing user is the inviter


class PendingInviteResponse(BaseModel):
    id: int
    token: str
    created_at: str
    expires_at: str | None = None  # None for permanent invites
    status: str  # "pending", "accepted", "expired" (permanent invites are always "pending")
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


def _get_friend_privacy_settings(connection, friend_user_id: int) -> dict:
    """Get a friend's mini profile privacy settings."""
    result = connection.execute(
        sqlalchemy.text(
            """
            SELECT friend_share_age, friend_share_total_trips,
                   friend_share_adventure_time, friend_share_favorite_activity,
                   friend_share_achievements
            FROM users WHERE id = :user_id
            """
        ),
        {"user_id": friend_user_id}
    ).fetchone()

    if not result:
        # Default to all visible if user not found
        return {
            "share_age": True,
            "share_total_trips": True,
            "share_adventure_time": True,
            "share_favorite_activity": True,
            "share_achievements": True,
        }

    return {
        "share_age": getattr(result, 'friend_share_age', True) if result else True,
        "share_total_trips": getattr(result, 'friend_share_total_trips', True) if result else True,
        "share_adventure_time": getattr(result, 'friend_share_adventure_time', True) if result else True,
        "share_favorite_activity": getattr(result, 'friend_share_favorite_activity', True) if result else True,
        "share_achievements": getattr(result, 'friend_share_achievements', True) if result else True,
    }


def _compute_friend_stats(connection, friend_user_id: int) -> dict:
    """Compute stats for a friend's mini profile.

    Returns dict with: age, achievements_count, total_trips,
    total_adventure_hours, favorite_activity_name, favorite_activity_icon

    Respects the friend's privacy settings - if a stat is hidden,
    it will be returned as None.
    """
    # Get privacy settings for this friend
    privacy = _get_friend_privacy_settings(connection, friend_user_id)

    # Get user age (only if allowed)
    age = None
    if privacy["share_age"]:
        user = connection.execute(
            sqlalchemy.text("SELECT age FROM users WHERE id = :user_id"),
            {"user_id": friend_user_id}
        ).fetchone()
        age = user.age if user and user.age and user.age > 0 else None

    # Get total completed trips count (needed for achievements calc even if hidden)
    trips_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COUNT(*) as count
            FROM trips
            WHERE user_id = :user_id AND status = 'completed'
            """
        ),
        {"user_id": friend_user_id}
    ).fetchone()
    total_trips_raw = trips_result.count if trips_result else 0

    # Get total adventure hours (needed for achievements calc even if hidden)
    hours_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COALESCE(
                SUM(EXTRACT(EPOCH FROM (completed_at - start)) / 3600),
                0
            ) as total_hours
            FROM trips
            WHERE user_id = :user_id
            AND status = 'completed'
            AND completed_at IS NOT NULL
            """
        ),
        {"user_id": friend_user_id}
    ).fetchone()
    total_adventure_hours_raw = int(hours_result.total_hours) if hours_result else 0

    # Calculate achievements count (only if allowed)
    achievements_count = None
    if privacy["share_achievements"]:
        achievements_count = _calculate_achievements_count(
            total_trips_raw, total_adventure_hours_raw, connection, friend_user_id
        )

    # Only expose stats if privacy settings allow
    total_trips = total_trips_raw if privacy["share_total_trips"] else None
    total_adventure_hours = total_adventure_hours_raw if privacy["share_adventure_time"] else None

    # Get favorite activity (only if allowed)
    favorite_activity_name = None
    favorite_activity_icon = None
    if privacy["share_favorite_activity"]:
        favorite_result = connection.execute(
            sqlalchemy.text(
                """
                SELECT a.name, a.icon, COUNT(*) as trip_count
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.user_id = :user_id AND t.status = 'completed'
                GROUP BY a.id, a.name, a.icon
                ORDER BY trip_count DESC
                LIMIT 1
                """
            ),
            {"user_id": friend_user_id}
        ).fetchone()
        favorite_activity_name = favorite_result.name if favorite_result else None
        favorite_activity_icon = favorite_result.icon if favorite_result else None

    # Total achievements is always 40 (or len(ACHIEVEMENTS) if defined)
    total_achievements = 40 if privacy["share_achievements"] else None

    return {
        "age": age,
        "achievements_count": achievements_count,
        "total_achievements": total_achievements,
        "total_trips": total_trips,
        "total_adventure_hours": total_adventure_hours,
        "favorite_activity_name": favorite_activity_name,
        "favorite_activity_icon": favorite_activity_icon,
    }


def _calculate_achievements_count(
    total_trips: int, total_hours: int, connection, user_id: int
) -> int:
    """Calculate achievements earned based on trip data (mirrors iOS logic)."""
    count = 0

    # Total Trips achievements
    for threshold in [1, 5, 10, 25, 50, 100, 150, 200, 250, 500, 1000]:
        if total_trips >= threshold:
            count += 1

    # Adventure Time achievements (hours)
    for threshold in [1, 10, 50, 100, 250, 500, 1000, 2500]:
        if total_hours >= threshold:
            count += 1

    # Activities tried achievements
    activities_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COUNT(DISTINCT activity) as count
            FROM trips
            WHERE user_id = :user_id AND status = 'completed'
            """
        ),
        {"user_id": user_id}
    ).fetchone()
    unique_activities = activities_result.count if activities_result else 0
    for threshold in [1, 3, 5, 10, 15, 20]:
        if unique_activities >= threshold:
            count += 1

    # Locations achievements
    locations_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COUNT(DISTINCT location_text) as count
            FROM trips
            WHERE user_id = :user_id
            AND status = 'completed'
            AND location_text IS NOT NULL
            AND location_text != ''
            """
        ),
        {"user_id": user_id}
    ).fetchone()
    unique_locations = locations_result.count if locations_result else 0
    for threshold in [1, 5, 10, 25, 50, 100, 250]:
        if unique_locations >= threshold:
            count += 1

    return count


def _compute_friend_stats_batch(connection, friend_user_ids: list[int]) -> dict[int, dict]:
    """Compute stats for multiple friends in batched queries.

    Returns dict mapping user_id -> stats dict
    This reduces N+1 queries to a fixed number of batch queries.
    """
    if not friend_user_ids:
        return {}

    # Initialize result with default values
    result = {uid: {
        "age": None,
        "achievements_count": None,
        "total_achievements": None,
        "total_trips": None,
        "total_adventure_hours": None,
        "favorite_activity_name": None,
        "favorite_activity_icon": None,
    } for uid in friend_user_ids}

    # 1. Batch get privacy settings and ages for all friends
    privacy_rows = connection.execute(
        sqlalchemy.text(
            """
            SELECT id, age,
                   friend_share_age, friend_share_total_trips,
                   friend_share_adventure_time, friend_share_favorite_activity,
                   friend_share_achievements
            FROM users WHERE id = ANY(:user_ids)
            """
        ),
        {"user_ids": friend_user_ids}
    ).fetchall()

    privacy_map = {}
    for row in privacy_rows:
        privacy_map[row.id] = {
            "share_age": getattr(row, 'friend_share_age', True) if row else True,
            "share_total_trips": getattr(row, 'friend_share_total_trips', True) if row else True,
            "share_adventure_time": getattr(row, 'friend_share_adventure_time', True) if row else True,
            "share_favorite_activity": getattr(row, 'friend_share_favorite_activity', True) if row else True,
            "share_achievements": getattr(row, 'friend_share_achievements', True) if row else True,
            "age": row.age if row.age and row.age > 0 else None,
        }

    # 2. Batch get trip counts and adventure hours for all friends
    trip_stats = connection.execute(
        sqlalchemy.text(
            """
            SELECT user_id,
                   COUNT(*) as total_trips,
                   COALESCE(SUM(EXTRACT(EPOCH FROM (completed_at - start)) / 3600), 0) as total_hours
            FROM trips
            WHERE user_id = ANY(:user_ids) AND status = 'completed'
            GROUP BY user_id
            """
        ),
        {"user_ids": friend_user_ids}
    ).fetchall()

    trips_map = {row.user_id: {"trips": row.total_trips, "hours": int(row.total_hours)} for row in trip_stats}

    # 3. Batch get unique activities count for achievement calculation
    activities_stats = connection.execute(
        sqlalchemy.text(
            """
            SELECT user_id, COUNT(DISTINCT activity) as count
            FROM trips
            WHERE user_id = ANY(:user_ids) AND status = 'completed'
            GROUP BY user_id
            """
        ),
        {"user_ids": friend_user_ids}
    ).fetchall()

    activities_map = {row.user_id: row.count for row in activities_stats}

    # 4. Batch get unique locations count for achievement calculation
    locations_stats = connection.execute(
        sqlalchemy.text(
            """
            SELECT user_id, COUNT(DISTINCT location_text) as count
            FROM trips
            WHERE user_id = ANY(:user_ids)
            AND status = 'completed'
            AND location_text IS NOT NULL
            AND location_text != ''
            GROUP BY user_id
            """
        ),
        {"user_ids": friend_user_ids}
    ).fetchall()

    locations_map = {row.user_id: row.count for row in locations_stats}

    # 5. Batch get favorite activities (using window function for efficiency)
    favorite_activities = connection.execute(
        sqlalchemy.text(
            """
            WITH ranked_activities AS (
                SELECT t.user_id, a.name, a.icon, COUNT(*) as trip_count,
                       ROW_NUMBER() OVER (PARTITION BY t.user_id ORDER BY COUNT(*) DESC) as rn
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.user_id = ANY(:user_ids) AND t.status = 'completed'
                GROUP BY t.user_id, a.id, a.name, a.icon
            )
            SELECT user_id, name, icon FROM ranked_activities WHERE rn = 1
            """
        ),
        {"user_ids": friend_user_ids}
    ).fetchall()

    favorites_map = {row.user_id: {"name": row.name, "icon": row.icon} for row in favorite_activities}

    # 6. Calculate final stats for each friend
    for uid in friend_user_ids:
        privacy = privacy_map.get(uid, {
            "share_age": True, "share_total_trips": True,
            "share_adventure_time": True, "share_favorite_activity": True,
            "share_achievements": True, "age": None
        })

        trip_data = trips_map.get(uid, {"trips": 0, "hours": 0})
        total_trips_raw = trip_data["trips"]
        total_hours_raw = trip_data["hours"]

        # Age (if privacy allows)
        if privacy["share_age"]:
            result[uid]["age"] = privacy.get("age")

        # Trips and hours (if privacy allows)
        if privacy["share_total_trips"]:
            result[uid]["total_trips"] = total_trips_raw
        if privacy["share_adventure_time"]:
            result[uid]["total_adventure_hours"] = total_hours_raw

        # Achievements calculation (if privacy allows)
        if privacy["share_achievements"]:
            unique_activities = activities_map.get(uid, 0)
            unique_locations = locations_map.get(uid, 0)
            achievements = _calculate_achievements_count_from_data(
                total_trips_raw, total_hours_raw, unique_activities, unique_locations
            )
            result[uid]["achievements_count"] = achievements
            result[uid]["total_achievements"] = 40

        # Favorite activity (if privacy allows)
        if privacy["share_favorite_activity"]:
            fav = favorites_map.get(uid)
            if fav:
                result[uid]["favorite_activity_name"] = fav["name"]
                result[uid]["favorite_activity_icon"] = fav["icon"]

    return result


def _calculate_achievements_count_from_data(
    total_trips: int, total_hours: int, unique_activities: int, unique_locations: int
) -> int:
    """Calculate achievements from pre-fetched data (no DB queries)."""
    count = 0

    # Total Trips achievements
    for threshold in [1, 5, 10, 25, 50, 100, 150, 200, 250, 500, 1000]:
        if total_trips >= threshold:
            count += 1

    # Adventure Time achievements (hours)
    for threshold in [1, 10, 50, 100, 250, 500, 1000, 2500]:
        if total_hours >= threshold:
            count += 1

    # Activities tried achievements
    for threshold in [1, 3, 5, 10, 15, 20]:
        if unique_activities >= threshold:
            count += 1

    # Locations achievements
    for threshold in [1, 5, 10, 25, 50, 100, 250]:
        if unique_locations >= threshold:
            count += 1

    return count


# ==================== Invite Endpoints ====================

@router.post("/invite", response_model=FriendInviteResponse)
def create_invite(
    regenerate: bool = False,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Get or create a reusable friend invite link.

    Each user has one permanent invite link that can be used unlimited times.
    Pass regenerate=true to invalidate the old link and create a new one.
    """
    with db.engine.begin() as connection:
        # Check for existing reusable invite (max_uses IS NULL = permanent)
        if not regenerate:
            existing = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT token FROM friend_invites
                    WHERE inviter_id = :user_id AND max_uses IS NULL
                    LIMIT 1
                    """
                ),
                {"user_id": user_id}
            ).fetchone()

            if existing:
                invite_url = f"https://api.homeboundapp.com/f/{existing.token}"
                return FriendInviteResponse(
                    token=existing.token,
                    invite_url=invite_url,
                    expires_at=None  # Permanent
                )

        # Regenerate: invalidate old permanent invite by deleting it
        if regenerate:
            connection.execute(
                sqlalchemy.text(
                    """
                    DELETE FROM friend_invites
                    WHERE inviter_id = :user_id AND max_uses IS NULL
                    """
                ),
                {"user_id": user_id}
            )

        # Create new permanent invite (max_uses=NULL, expires_at=NULL)
        token = _generate_invite_token()
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO friend_invites (inviter_id, token, expires_at, max_uses)
                VALUES (:inviter_id, :token, NULL, NULL)
                """
            ),
            {"inviter_id": user_id, "token": token}
        )

    invite_url = f"https://api.homeboundapp.com/f/{token}"

    return FriendInviteResponse(
        token=token,
        invite_url=invite_url,
        expires_at=None  # Permanent
    )


@router.get("/invite/{token}", response_model=FriendInvitePreview)
def get_invite_preview(token: str, current_user_id: int | None = Depends(auth.get_optional_user_id)):
    """Get invite details for preview before accepting.

    This endpoint is public but optionally accepts authentication.
    When authenticated, returns is_own_invite=True if the viewer is the inviter.
    """
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
        # Permanent invites (max_uses IS NULL) never expire and have unlimited uses
        is_permanent = invite.max_uses is None
        is_expired = False if is_permanent else (invite.expires_at and invite.expires_at < now)
        is_used_up = False if is_permanent else (invite.use_count >= invite.max_uses)
        is_valid = not is_expired and not is_used_up

        # Check if the authenticated user is the inviter
        is_own_invite = current_user_id is not None and invite.inviter_id == current_user_id

        return FriendInvitePreview(
            inviter_first_name=invite.first_name or "A user",
            inviter_profile_photo_url=invite.profile_photo_url,
            inviter_member_since=invite.member_since.isoformat() if invite.member_since else "",
            expires_at=invite.expires_at.isoformat() if invite.expires_at else None,
            is_valid=is_valid,
            is_own_invite=is_own_invite
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
        # Permanent invites (max_uses IS NULL) never expire and have unlimited uses
        is_permanent = invite.max_uses is None
        now = datetime.utcnow()

        if not is_permanent:
            # Legacy one-time invites have expiry and use limits
            if invite.expires_at and invite.expires_at < now:
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
            # Also send refresh push to update friends list
            asyncio.run(send_data_refresh_push(inviter_id, "friends"))

        background_tasks.add_task(send_push_sync)

        # Compute stats for the inviter
        stats = _compute_friend_stats(connection, inviter_id)

        return FriendResponse(
            user_id=inviter.id,
            first_name=inviter.first_name or "",
            last_name=inviter.last_name or "",
            profile_photo_url=inviter.profile_photo_url,
            member_since=inviter.created_at.isoformat() if inviter.created_at else "",
            friendship_since=friendship.created_at.isoformat() if friendship else "",
            age=stats["age"],
            achievements_count=stats["achievements_count"],
            total_achievements=stats["total_achievements"],
            total_trips=stats["total_trips"],
            total_adventure_hours=stats["total_adventure_hours"],
            favorite_activity_name=stats["favorite_activity_name"],
            favorite_activity_icon=stats["favorite_activity_icon"],
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
            # Permanent invites (max_uses IS NULL) are always "active" (reusable)
            is_permanent = inv.max_uses is None
            if is_permanent:
                invite_status = "active"  # Permanent, reusable invite
            elif inv.use_count >= inv.max_uses:
                invite_status = "accepted"
            elif inv.expires_at and inv.expires_at < now:
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
                expires_at=inv.expires_at.isoformat() if inv.expires_at else None,
                status=invite_status,
                accepted_by_name=accepted_by_name
            ))

        return result


# ==================== Friends List Endpoints ====================

@router.get("/", response_model=list[FriendResponse])
def get_friends(user_id: int = Depends(auth.get_current_user_id)):
    """Get all friends for the current user with their stats."""
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

        # Batch compute stats for all friends (reduces N+1 queries)
        friend_ids = [f.user_id for f in friends]
        stats_map = _compute_friend_stats_batch(connection, friend_ids)

        result = []
        for f in friends:
            stats = stats_map.get(f.user_id, {})
            result.append(FriendResponse(
                user_id=f.user_id,
                first_name=f.first_name or "",
                last_name=f.last_name or "",
                profile_photo_url=f.profile_photo_url,
                member_since=f.member_since.isoformat() if f.member_since else "",
                friendship_since=f.friendship_since.isoformat() if f.friendship_since else "",
                age=stats.get("age"),
                achievements_count=stats.get("achievements_count"),
                total_achievements=stats.get("total_achievements"),
                total_trips=stats.get("total_trips"),
                total_adventure_hours=stats.get("total_adventure_hours"),
                favorite_activity_name=stats.get("favorite_activity_name"),
                favorite_activity_icon=stats.get("favorite_activity_icon"),
            ))
        return result


# ==================== Friend's Active Trips ====================
# NOTE: This must be defined BEFORE /{friend_user_id} to avoid route conflicts

class FriendActiveTripOwner(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    profile_photo_url: str | None


class CheckinLocation(BaseModel):
    """A check-in event with location data for friends to see on a map."""
    timestamp: str
    latitude: float | None
    longitude: float | None
    location_name: str | None


class LiveLocationData(BaseModel):
    """Real-time location data for friends to track during a trip."""
    latitude: float
    longitude: float
    timestamp: str
    speed: float | None


class MonitoredParticipant(BaseModel):
    """Info about a participant being monitored in a group trip."""
    user_id: int
    first_name: str
    last_name: str
    profile_photo_url: str | None


class FriendActiveTrip(BaseModel):
    id: int
    owner: FriendActiveTripOwner
    title: str
    activity_name: str
    activity_icon: str
    activity_colors: dict
    status: str
    start: str
    eta: str
    grace_min: int
    location_text: str | None
    start_location_text: str | None
    notes: str | None
    timezone: str | None
    last_checkin_at: str | None
    # Enhanced friend visibility fields
    checkin_locations: list[CheckinLocation] | None = None
    live_location: LiveLocationData | None = None
    destination_lat: float | None = None
    destination_lon: float | None = None
    start_lat: float | None = None
    start_lon: float | None = None
    has_pending_update_request: bool = False
    # Group trip fields
    is_group_trip: bool = False
    monitored_participant: MonitoredParticipant | None = None


@router.get("/active-trips", response_model=list[FriendActiveTrip])
def get_friend_active_trips(user_id: int = Depends(auth.get_current_user_id)):
    """Get all active/planned trips where the current user is a friend safety contact.

    This allows friends to see the status of trips they're monitoring.
    Friends get enhanced visibility compared to email contacts, including:
    - Check-in locations on a map
    - Live location (if owner has enabled it)
    - Trip coordinates for map display

    For group trips, also returns trips where the user is a safety contact for
    a participant (via participant_trip_contacts). In this case, the check-in
    and live location data shown is for the monitored participant, not the owner.
    """
    import json
    import logging
    from src.services.geocoding import reverse_geocode_sync
    log = logging.getLogger(__name__)
    log.info(f"[Friends] get_friend_active_trips called for user_id={user_id}")

    with db.engine.begin() as connection:
        # Query 1: Solo trips where user is owner's friend safety contact
        solo_trips = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, t.start, t.eta, t.grace_min,
                       t.location_text, t.start_location_text, t.notes, t.status, t.timezone,
                       t.gen_lat, t.gen_lon, t.start_lat, t.start_lon, t.share_live_location,
                       t.is_group_trip,
                       a.name as activity_name, a.icon as activity_icon, a.colors as activity_colors,
                       u.first_name, u.last_name, u.profile_photo_url,
                       u.friend_share_checkin_locations, u.friend_share_live_location,
                       u.friend_share_notes, u.friend_allow_update_requests,
                       e.timestamp as last_checkin_at,
                       NULL::integer as monitored_user_id,
                       NULL::text as monitored_first_name,
                       NULL::text as monitored_last_name,
                       NULL::text as monitored_profile_photo_url
                FROM trips t
                JOIN trip_safety_contacts tsc ON tsc.trip_id = t.id
                JOIN activities a ON t.activity = a.id
                JOIN users u ON t.user_id = u.id
                LEFT JOIN events e ON t.last_checkin = e.id
                WHERE tsc.friend_user_id = :current_user_id
                AND t.status IN ('active', 'overdue', 'overdue_notified', 'planned')
                """
            ),
            {"current_user_id": user_id}
        ).mappings().fetchall()

        # Query 2: Group trips where user is a participant's friend safety contact
        group_trips = connection.execute(
            sqlalchemy.text(
                """
                SELECT DISTINCT ON (t.id)
                       t.id, t.user_id, t.title, t.start, t.eta, t.grace_min,
                       t.location_text, t.start_location_text, t.notes, t.status, t.timezone,
                       t.gen_lat, t.gen_lon, t.start_lat, t.start_lon,
                       COALESCE(tp.share_location, false) as share_live_location,
                       t.is_group_trip,
                       a.name as activity_name, a.icon as activity_icon, a.colors as activity_colors,
                       owner.first_name, owner.last_name, owner.profile_photo_url,
                       participant.friend_share_checkin_locations,
                       participant.friend_share_live_location,
                       participant.friend_share_notes,
                       participant.friend_allow_update_requests,
                       tp.last_checkin_at,
                       ptc.participant_user_id as monitored_user_id,
                       participant.first_name as monitored_first_name,
                       participant.last_name as monitored_last_name,
                       participant.profile_photo_url as monitored_profile_photo_url
                FROM trips t
                JOIN participant_trip_contacts ptc ON ptc.trip_id = t.id
                JOIN trip_participants tp ON tp.trip_id = t.id AND tp.user_id = ptc.participant_user_id
                JOIN activities a ON t.activity = a.id
                JOIN users owner ON t.user_id = owner.id
                JOIN users participant ON ptc.participant_user_id = participant.id
                WHERE ptc.friend_user_id = :current_user_id
                AND t.status IN ('active', 'overdue', 'overdue_notified', 'planned')
                AND tp.status = 'accepted'
                ORDER BY t.id, t.start ASC
                """
            ),
            {"current_user_id": user_id}
        ).mappings().fetchall()

        # Combine trips, avoiding duplicates (solo trips take precedence)
        solo_trip_ids = {trip["id"] for trip in solo_trips}
        all_trips = list(solo_trips) + [t for t in group_trips if t["id"] not in solo_trip_ids]

        if not all_trips:
            return []

        # Extract trip IDs for batch queries
        trip_ids = [trip["id"] for trip in all_trips]

        # Build map of trip_id -> monitored_user_id for group trips
        monitored_user_map = {
            trip["id"]: trip["monitored_user_id"]
            for trip in all_trips if trip["monitored_user_id"]
        }

        # Batch load check-in events for all trips
        # For group trips with monitored participant, filter by user_id
        checkin_events_raw = connection.execute(
            sqlalchemy.text(
                """
                SELECT trip_id, user_id, timestamp, lat, lon
                FROM events
                WHERE trip_id = ANY(:trip_ids) AND what = 'checkin' AND lat IS NOT NULL
                ORDER BY trip_id, timestamp DESC
                """
            ),
            {"trip_ids": trip_ids}
        ).fetchall()

        # Group check-in events by trip_id (limit 10 per trip)
        # Show all check-ins for the trip (not filtered by user)
        checkin_map: dict[int, list] = {tid: [] for tid in trip_ids}
        for event in checkin_events_raw:
            if len(checkin_map[event.trip_id]) < 10:
                checkin_map[event.trip_id].append(event)

        # Batch load live locations for all trips
        # For group trips, we need to get participant's live location
        live_locations_raw = connection.execute(
            sqlalchemy.text(
                """
                SELECT DISTINCT ON (trip_id, user_id) trip_id, user_id, latitude, longitude, speed, timestamp
                FROM live_locations
                WHERE trip_id = ANY(:trip_ids)
                ORDER BY trip_id, user_id, timestamp DESC
                """
            ),
            {"trip_ids": trip_ids}
        ).fetchall()

        # Map: trip_id -> (user_id -> live_location)
        live_loc_by_trip_user: dict[int, dict[int, object]] = {}
        for row in live_locations_raw:
            if row.trip_id not in live_loc_by_trip_user:
                live_loc_by_trip_user[row.trip_id] = {}
            live_loc_by_trip_user[row.trip_id][row.user_id] = row

        # Batch load pending update requests for all trips
        pending_requests_raw = connection.execute(
            sqlalchemy.text(
                """
                SELECT trip_id FROM update_requests
                WHERE trip_id = ANY(:trip_ids) AND requester_user_id = :user_id
                AND resolved_at IS NULL
                AND requested_at > NOW() - INTERVAL '10 minutes'
                """
            ),
            {"trip_ids": trip_ids, "user_id": user_id}
        ).fetchall()

        pending_map = {row.trip_id for row in pending_requests_raw}

        result = []
        for trip in all_trips:
            # Parse activity colors (may be JSON string or dict)
            colors = trip["activity_colors"]
            if isinstance(colors, str):
                colors = json.loads(colors)

            # Format datetime fields
            start_str = trip["start"]
            if hasattr(start_str, 'isoformat'):
                start_str = start_str.isoformat()
            eta_str = trip["eta"]
            if hasattr(eta_str, 'isoformat'):
                eta_str = eta_str.isoformat()
            last_checkin_str = trip["last_checkin_at"]
            if last_checkin_str is not None and hasattr(last_checkin_str, 'isoformat'):
                last_checkin_str = last_checkin_str.isoformat()

            # Get visibility settings (from owner for solo, from participant for group)
            share_checkin_locations = trip.get("friend_share_checkin_locations", True)
            share_live_location = trip.get("friend_share_live_location", False)
            share_notes = trip.get("friend_share_notes", True)
            allow_update_requests = trip.get("friend_allow_update_requests", True)

            # Build check-in locations from batch-loaded data
            checkin_locations = None
            if share_checkin_locations:
                events = checkin_map.get(trip["id"], [])
                if events:
                    checkin_locations = []
                    for event in events:
                        ts = event.timestamp
                        if hasattr(ts, 'isoformat'):
                            ts = ts.isoformat()
                        # Try to reverse geocode the location
                        location_name = None
                        if event.lat and event.lon:
                            try:
                                location_name = reverse_geocode_sync(event.lat, event.lon)
                            except Exception:
                                pass
                        checkin_locations.append(CheckinLocation(
                            timestamp=ts,
                            latitude=event.lat,
                            longitude=event.lon,
                            location_name=location_name
                        ))

            # Build live location from batch-loaded data
            live_location = None
            trip_has_live_location = trip.get("share_live_location", False)
            if share_live_location and trip_has_live_location:
                trip_live_locs = live_loc_by_trip_user.get(trip["id"], {})
                monitored_user = trip.get("monitored_user_id")
                # For group trips, get the monitored participant's live location
                # For solo trips, get the owner's live location
                target_user = monitored_user if monitored_user else trip["user_id"]
                live_loc = trip_live_locs.get(target_user)
                if live_loc:
                    ts = live_loc.timestamp
                    if hasattr(ts, 'isoformat'):
                        ts = ts.isoformat()
                    live_location = LiveLocationData(
                        latitude=live_loc.latitude,
                        longitude=live_loc.longitude,
                        speed=live_loc.speed,
                        timestamp=ts
                    )

            # Check for pending update requests from batch-loaded data
            has_pending_update = False
            if allow_update_requests:
                has_pending_update = trip["id"] in pending_map

            # Build monitored participant info for group trips
            monitored_participant = None
            is_group_trip = trip.get("is_group_trip", False) or trip.get("monitored_user_id") is not None
            if trip.get("monitored_user_id"):
                monitored_participant = MonitoredParticipant(
                    user_id=trip["monitored_user_id"],
                    first_name=trip["monitored_first_name"] or "",
                    last_name=trip["monitored_last_name"] or "",
                    profile_photo_url=trip["monitored_profile_photo_url"]
                )

            result.append(FriendActiveTrip(
                id=trip["id"],
                owner=FriendActiveTripOwner(
                    user_id=trip["user_id"],
                    first_name=trip["first_name"] or "",
                    last_name=trip["last_name"] or "",
                    profile_photo_url=trip["profile_photo_url"]
                ),
                title=trip["title"],
                activity_name=trip["activity_name"],
                activity_icon=trip["activity_icon"],
                activity_colors=colors,
                status=trip["status"],
                start=start_str,
                eta=eta_str,
                grace_min=trip["grace_min"],
                location_text=trip["location_text"],
                start_location_text=trip["start_location_text"],
                notes=trip["notes"] if share_notes else None,
                timezone=trip["timezone"],
                last_checkin_at=last_checkin_str,
                # Enhanced friend visibility fields
                checkin_locations=checkin_locations,
                live_location=live_location,
                destination_lat=trip["gen_lat"],
                destination_lon=trip["gen_lon"],
                start_lat=trip.get("start_lat"),
                start_lon=trip.get("start_lon"),
                has_pending_update_request=has_pending_update,
                # Group trip fields
                is_group_trip=is_group_trip,
                monitored_participant=monitored_participant
            ))

        # Sort by start time
        result.sort(key=lambda t: t.start)
        return result


# ==================== Update Request Endpoint ====================

class UpdateRequestResponse(BaseModel):
    ok: bool
    message: str
    cooldown_remaining_seconds: int | None = None


@router.post("/trips/{trip_id}/request-update", response_model=UpdateRequestResponse)
def request_trip_update(
    trip_id: int,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Request an update from the trip owner.

    Friends can use this to "ping" the trip owner when they're worried.
    Rate limited to 1 request per 10 minutes per trip per user.
    """
    from datetime import timezone
    from src.services.notifications import send_update_request_push
    import asyncio

    with db.engine.begin() as connection:
        # Verify user is a friend safety contact for this trip
        is_contact = connection.execute(
            sqlalchemy.text(
                """
                SELECT 1 FROM trip_safety_contacts
                WHERE trip_id = :trip_id AND friend_user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not is_contact:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a safety contact for this trip"
            )

        # Get trip info and owner settings
        trip_info = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.title, t.user_id as owner_id, t.status,
                       u.first_name as owner_first_name, u.friend_allow_update_requests
                FROM trips t
                JOIN users u ON t.user_id = u.id
                WHERE t.id = :trip_id
                AND t.status IN ('active', 'overdue', 'overdue_notified', 'planned')
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()

        if not trip_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found or not active"
            )

        # Check if owner allows update requests (default True for backwards compatibility)
        allow_requests = trip_info.friend_allow_update_requests
        if allow_requests is not None and not allow_requests:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Trip owner has disabled update requests"
            )

        # Check for recent request from this user (rate limiting)
        now = datetime.now(timezone.utc)
        recent = connection.execute(
            sqlalchemy.text(
                """
                SELECT requested_at FROM update_requests
                WHERE trip_id = :trip_id AND requester_user_id = :user_id
                AND requested_at > :cutoff
                ORDER BY requested_at DESC LIMIT 1
                """
            ),
            {"trip_id": trip_id, "user_id": user_id, "cutoff": (now - timedelta(minutes=10)).isoformat()}
        ).fetchone()

        if recent:
            # Calculate remaining cooldown
            recent_at = recent.requested_at
            if hasattr(recent_at, 'replace'):
                recent_at = recent_at.replace(tzinfo=timezone.utc)
            cooldown_seconds = int(600 - (now - recent_at).total_seconds())
            return UpdateRequestResponse(
                ok=False,
                message="Please wait before requesting another update",
                cooldown_remaining_seconds=max(0, cooldown_seconds)
            )

        # Get requester's name for the notification
        requester = connection.execute(
            sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        requester_name = f"{requester.first_name} {requester.last_name}".strip() if requester else "A friend"

        # Create the update request
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO update_requests (trip_id, requester_user_id, owner_user_id, requested_at)
                VALUES (:trip_id, :requester_id, :owner_id, :requested_at)
                """
            ),
            {
                "trip_id": trip_id,
                "requester_id": user_id,
                "owner_id": trip_info.owner_id,
                "requested_at": now.isoformat()
            }
        )

        # Send push notification to trip owner
        def send_push_sync():
            asyncio.run(send_update_request_push(
                owner_user_id=trip_info.owner_id,
                requester_name=requester_name,
                trip_title=trip_info.title,
                trip_id=trip_id
            ))

        background_tasks.add_task(send_push_sync)

        return UpdateRequestResponse(
            ok=True,
            message="Update request sent",
            cooldown_remaining_seconds=600  # 10 minute cooldown starts now
        )


# ==================== Individual Friend Endpoints ====================

@router.get("/{friend_user_id}", response_model=FriendResponse)
def get_friend(friend_user_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get a specific friend's profile with stats."""
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

        stats = _compute_friend_stats(connection, friend_user_id)

        return FriendResponse(
            user_id=friend.id,
            first_name=friend.first_name or "",
            last_name=friend.last_name or "",
            profile_photo_url=friend.profile_photo_url,
            member_since=friend.created_at.isoformat() if friend.created_at else "",
            friendship_since=friendship.created_at.isoformat() if friendship.created_at else "",
            age=stats["age"],
            achievements_count=stats["achievements_count"],
            total_achievements=stats["total_achievements"],
            total_trips=stats["total_trips"],
            total_adventure_hours=stats["total_adventure_hours"],
            favorite_activity_name=stats["favorite_activity_name"],
            favorite_activity_icon=stats["favorite_activity_icon"],
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


# ==================== Friend Achievements Endpoint ====================

class FriendAchievementResponse(BaseModel):
    """A single achievement with earned status and date."""
    id: str
    title: str
    description: str
    category: str
    sf_symbol: str
    threshold: int
    unit: str
    is_earned: bool
    earned_date: str | None = None
    current_value: int


class FriendAchievementsResponse(BaseModel):
    """Full achievement details for a friend."""
    user_id: int
    friend_name: str
    achievements: list[FriendAchievementResponse]
    earned_count: int
    total_count: int


# Achievement definitions (mirrors iOS TripStats.swift - 40 total)
ACHIEVEMENTS = [
    # Total Trips (11 achievements)
    {"id": "first_trip", "sf_symbol": "flag.fill", "title": "First Steps", "description": "Complete 1 trip", "category": "totalTrips", "threshold": 1, "unit": "trips"},
    {"id": "getting_started", "sf_symbol": "figure.walk", "title": "Getting Started", "description": "Complete 5 trips", "category": "totalTrips", "threshold": 5, "unit": "trips"},
    {"id": "explorer", "sf_symbol": "binoculars.fill", "title": "Explorer", "description": "Complete 10 trips", "category": "totalTrips", "threshold": 10, "unit": "trips"},
    {"id": "pathfinder", "sf_symbol": "point.bottomleft.forward.to.point.topright.scurvepath.fill", "title": "Pathfinder", "description": "Complete 25 trips", "category": "totalTrips", "threshold": 25, "unit": "trips"},
    {"id": "adventurer", "sf_symbol": "mountain.2.fill", "title": "Adventurer", "description": "Complete 50 trips", "category": "totalTrips", "threshold": 50, "unit": "trips"},
    {"id": "century", "sf_symbol": "trophy.fill", "title": "Century", "description": "Complete 100 trips", "category": "totalTrips", "threshold": 100, "unit": "trips"},
    {"id": "dedicated", "sf_symbol": "medal.fill", "title": "Dedicated", "description": "Complete 150 trips", "category": "totalTrips", "threshold": 150, "unit": "trips"},
    {"id": "committed", "sf_symbol": "star.circle.fill", "title": "Committed", "description": "Complete 200 trips", "category": "totalTrips", "threshold": 200, "unit": "trips"},
    {"id": "elite", "sf_symbol": "rosette", "title": "Elite", "description": "Complete 250 trips", "category": "totalTrips", "threshold": 250, "unit": "trips"},
    {"id": "master", "sf_symbol": "crown.fill", "title": "Master", "description": "Complete 500 trips", "category": "totalTrips", "threshold": 500, "unit": "trips"},
    {"id": "legendary", "sf_symbol": "sparkle.magnifyingglass", "title": "Legendary", "description": "Complete 1000 trips", "category": "totalTrips", "threshold": 1000, "unit": "trips"},

    # Adventure Time (8 achievements)
    {"id": "first_hour", "sf_symbol": "clock", "title": "First Hour", "description": "1 hour", "category": "adventureTime", "threshold": 1, "unit": "hours"},
    {"id": "getting_outdoors", "sf_symbol": "clock.fill", "title": "Getting Out", "description": "10 hours", "category": "adventureTime", "threshold": 10, "unit": "hours"},
    {"id": "timekeeper", "sf_symbol": "timer", "title": "Time Keeper", "description": "50 hours", "category": "adventureTime", "threshold": 50, "unit": "hours"},
    {"id": "timemaster", "sf_symbol": "hourglass", "title": "Time Master", "description": "100 hours", "category": "adventureTime", "threshold": 100, "unit": "hours"},
    {"id": "time_devotee", "sf_symbol": "hourglass.circle.fill", "title": "Devotee", "description": "250 hours", "category": "adventureTime", "threshold": 250, "unit": "hours"},
    {"id": "time_legend", "sf_symbol": "hourglass.badge.plus", "title": "Time Legend", "description": "500 hours", "category": "adventureTime", "threshold": 500, "unit": "hours"},
    {"id": "time_titan", "sf_symbol": "star.fill", "title": "Time Titan", "description": "1000 hours", "category": "adventureTime", "threshold": 1000, "unit": "hours"},
    {"id": "eternal", "sf_symbol": "infinity", "title": "Eternal", "description": "2500 hours", "category": "adventureTime", "threshold": 2500, "unit": "hours"},

    # Activities (6 achievements)
    {"id": "first_activity", "sf_symbol": "leaf", "title": "Starter", "description": "Try 1 activity type", "category": "activitiesTried", "threshold": 1, "unit": "activities"},
    {"id": "curious", "sf_symbol": "sparkle", "title": "Curious", "description": "Try 3 activity types", "category": "activitiesTried", "threshold": 3, "unit": "activities"},
    {"id": "diverse", "sf_symbol": "star.fill", "title": "Diverse", "description": "Try 5 activity types", "category": "activitiesTried", "threshold": 5, "unit": "activities"},
    {"id": "variety", "sf_symbol": "sparkles", "title": "Variety", "description": "Try 10 activity types", "category": "activitiesTried", "threshold": 10, "unit": "activities"},
    {"id": "well_rounded", "sf_symbol": "circle.hexagongrid.fill", "title": "Well Rounded", "description": "Try 15 activity types", "category": "activitiesTried", "threshold": 15, "unit": "activities"},
    {"id": "jack_of_all", "sf_symbol": "seal.fill", "title": "Jack of All", "description": "Try 20 activity types", "category": "activitiesTried", "threshold": 20, "unit": "activities"},

    # Locations (7 achievements)
    {"id": "first_place", "sf_symbol": "mappin", "title": "First Place", "description": "Visit 1 location", "category": "locations", "threshold": 1, "unit": "locations"},
    {"id": "local", "sf_symbol": "mappin.circle.fill", "title": "Local", "description": "Visit 5 locations", "category": "locations", "threshold": 5, "unit": "locations"},
    {"id": "explorer_loc", "sf_symbol": "map", "title": "Explorer", "description": "Visit 10 locations", "category": "locations", "threshold": 10, "unit": "locations"},
    {"id": "wanderer", "sf_symbol": "map.fill", "title": "Wanderer", "description": "Visit 25 locations", "category": "locations", "threshold": 25, "unit": "locations"},
    {"id": "traveler", "sf_symbol": "airplane", "title": "Traveler", "description": "Visit 50 locations", "category": "locations", "threshold": 50, "unit": "locations"},
    {"id": "globetrotter", "sf_symbol": "globe.americas.fill", "title": "Globetrotter", "description": "Visit 100 locations", "category": "locations", "threshold": 100, "unit": "locations"},
    {"id": "world_explorer", "sf_symbol": "globe", "title": "World Explorer", "description": "Visit 250 locations", "category": "locations", "threshold": 250, "unit": "locations"},

    # Time-Based (8 achievements)
    {"id": "earlybird", "sf_symbol": "sunrise.fill", "title": "Early Bird", "description": "5 trips before 8 AM", "category": "timeBased", "threshold": 5, "unit": "trips"},
    {"id": "earlybird_pro", "sf_symbol": "sunrise.circle.fill", "title": "Dawn Patrol", "description": "25 trips before 8 AM", "category": "timeBased", "threshold": 25, "unit": "trips"},
    {"id": "nightowl", "sf_symbol": "moon.stars.fill", "title": "Night Owl", "description": "5 trips after 8 PM", "category": "timeBased", "threshold": 5, "unit": "trips"},
    {"id": "nightowl_pro", "sf_symbol": "moon.circle.fill", "title": "Nocturnal", "description": "25 trips after 8 PM", "category": "timeBased", "threshold": 25, "unit": "trips"},
    {"id": "weekendwarrior", "sf_symbol": "sun.max.fill", "title": "Weekender", "description": "10 weekend trips", "category": "timeBased", "threshold": 10, "unit": "trips"},
    {"id": "weekendwarrior_pro", "sf_symbol": "sun.max.circle.fill", "title": "Weekend Pro", "description": "50 weekend trips", "category": "timeBased", "threshold": 50, "unit": "trips"},
    {"id": "consistent", "sf_symbol": "calendar", "title": "Consistent", "description": "Trips in 5 months", "category": "timeBased", "threshold": 5, "unit": "months"},
    {"id": "year_round", "sf_symbol": "calendar.badge.checkmark", "title": "Year Round", "description": "Trips in 12 months", "category": "timeBased", "threshold": 12, "unit": "months"},
]


def _compute_achievement_details(connection, user_id: int) -> dict:
    """Compute detailed achievement info for a user."""
    # Get base stats
    trips_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COUNT(*) as count
            FROM trips
            WHERE user_id = :user_id AND status = 'completed'
            """
        ),
        {"user_id": user_id}
    ).fetchone()
    total_trips = trips_result.count if trips_result else 0

    hours_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COALESCE(
                SUM(EXTRACT(EPOCH FROM (completed_at - start)) / 3600),
                0
            ) as total_hours
            FROM trips
            WHERE user_id = :user_id AND status = 'completed' AND completed_at IS NOT NULL
            """
        ),
        {"user_id": user_id}
    ).fetchone()
    total_hours = int(hours_result.total_hours) if hours_result else 0

    activities_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COUNT(DISTINCT activity) as count
            FROM trips WHERE user_id = :user_id AND status = 'completed'
            """
        ),
        {"user_id": user_id}
    ).fetchone()
    unique_activities = activities_result.count if activities_result else 0

    locations_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COUNT(DISTINCT location_text) as count
            FROM trips
            WHERE user_id = :user_id AND status = 'completed'
            AND location_text IS NOT NULL AND location_text != ''
            """
        ),
        {"user_id": user_id}
    ).fetchone()
    unique_locations = locations_result.count if locations_result else 0

    # Time-based stats
    early_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COUNT(*) as count FROM trips
            WHERE user_id = :user_id AND status = 'completed'
            AND EXTRACT(HOUR FROM start) < 8
            """
        ),
        {"user_id": user_id}
    ).fetchone()
    early_trips = early_result.count if early_result else 0

    night_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COUNT(*) as count FROM trips
            WHERE user_id = :user_id AND status = 'completed'
            AND EXTRACT(HOUR FROM start) >= 20
            """
        ),
        {"user_id": user_id}
    ).fetchone()
    night_trips = night_result.count if night_result else 0

    weekend_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COUNT(*) as count FROM trips
            WHERE user_id = :user_id AND status = 'completed'
            AND EXTRACT(DOW FROM start) IN (0, 6)
            """
        ),
        {"user_id": user_id}
    ).fetchone()
    weekend_trips = weekend_result.count if weekend_result else 0

    months_result = connection.execute(
        sqlalchemy.text(
            """
            SELECT COUNT(DISTINCT TO_CHAR(start, 'YYYY-MM')) as count
            FROM trips
            WHERE user_id = :user_id AND status = 'completed'
            """
        ),
        {"user_id": user_id}
    ).fetchone()
    unique_months = months_result.count if months_result else 0

    # Get completed_at dates for earned date calculation
    completed_dates = connection.execute(
        sqlalchemy.text(
            """
            SELECT completed_at FROM trips
            WHERE user_id = :user_id AND status = 'completed' AND completed_at IS NOT NULL
            ORDER BY completed_at ASC
            """
        ),
        {"user_id": user_id}
    ).fetchall()
    sorted_dates = [d.completed_at for d in completed_dates]

    achievements = []
    earned_count = 0

    for ach in ACHIEVEMENTS:
        # Get current value based on category
        if ach["category"] == "totalTrips":
            current_value = total_trips
        elif ach["category"] == "adventureTime":
            current_value = total_hours
        elif ach["category"] == "activitiesTried":
            current_value = unique_activities
        elif ach["category"] == "locations":
            current_value = unique_locations
        elif ach["category"] == "timeBased":
            # Determine which time-based metric
            if "before 8 AM" in ach["description"]:
                current_value = early_trips
            elif "after 8 PM" in ach["description"]:
                current_value = night_trips
            elif "weekend" in ach["description"]:
                current_value = weekend_trips
            elif "months" in ach["unit"]:
                current_value = unique_months
            else:
                current_value = 0
        else:
            current_value = 0

        is_earned = current_value >= ach["threshold"]
        earned_date = None

        if is_earned:
            earned_count += 1
            # Calculate earned date (when threshold was met)
            if ach["category"] == "totalTrips" and sorted_dates:
                index = min(ach["threshold"] - 1, len(sorted_dates) - 1)
                if index >= 0:
                    earned_date = sorted_dates[index].isoformat()

        achievements.append(FriendAchievementResponse(
            id=ach["id"],
            title=ach["title"],
            description=ach["description"],
            category=ach["category"],
            sf_symbol=ach["sf_symbol"],
            threshold=ach["threshold"],
            unit=ach["unit"],
            is_earned=is_earned,
            earned_date=earned_date,
            current_value=min(current_value, ach["threshold"])
        ))

    return {
        "achievements": achievements,
        "earned_count": earned_count,
        "total_count": len(ACHIEVEMENTS)
    }


@router.get("/{friend_user_id}/achievements", response_model=FriendAchievementsResponse)
def get_friend_achievements(
    friend_user_id: int,
    user_id: int = Depends(auth.get_current_user_id)
):
    """Get detailed achievements for a friend.

    Only returns achievements if:
    1. The users are friends
    2. The friend has enabled friend_share_achievements
    """
    with db.engine.begin() as connection:
        # Verify friendship exists
        friendship = _get_friendship(connection, user_id, friend_user_id)
        if not friendship:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Friend not found"
            )

        # Check if friend allows sharing achievements
        friend_settings = connection.execute(
            sqlalchemy.text(
                """
                SELECT first_name, last_name, friend_share_achievements
                FROM users
                WHERE id = :friend_id
                """
            ),
            {"friend_id": friend_user_id}
        ).fetchone()

        if not friend_settings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Check privacy setting (default True for backwards compatibility)
        share_achievements = getattr(friend_settings, 'friend_share_achievements', True)
        if share_achievements is not None and not share_achievements:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This user has disabled achievement sharing"
            )

        # Get achievement details
        stats = _compute_achievement_details(connection, friend_user_id)

        friend_name = f"{friend_settings.first_name or ''} {friend_settings.last_name or ''}".strip() or "Friend"

        return FriendAchievementsResponse(
            user_id=friend_user_id,
            friend_name=friend_name,
            achievements=stats["achievements"],
            earned_count=stats["earned_count"],
            total_count=stats["total_count"]
        )
