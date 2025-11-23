"""Trip management endpoints"""
from datetime import datetime, timezone
import secrets
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from src import database as db
from src.api import auth
import sqlalchemy

router = APIRouter(
    prefix="/api/v1/trips",
    tags=["trips"],
    dependencies=[Depends(auth.get_current_user_id)]
)


class TripCreate(BaseModel):
    title: str
    activity: str  # Activity name reference
    start: datetime
    eta: datetime
    grace_min: int
    location_text: Optional[str] = None
    gen_lat: Optional[float] = None
    gen_lon: Optional[float] = None
    notes: Optional[str] = None
    contact1: Optional[int] = None  # Contact ID reference
    contact2: Optional[int] = None
    contact3: Optional[int] = None


class TripResponse(BaseModel):
    id: int
    user_id: int
    title: str
    activity: str
    start: str
    eta: str
    grace_min: int
    location_text: Optional[str]
    gen_lat: Optional[float]
    gen_lon: Optional[float]
    notes: Optional[str]
    status: str
    completed_at: Optional[str]
    last_checkin: Optional[str]
    created_at: str
    contact1: Optional[int]
    contact2: Optional[int]
    contact3: Optional[int]
    checkin_token: Optional[str]
    checkout_token: Optional[str]


class TimelineEvent(BaseModel):
    id: int
    what: str
    timestamp: str
    lat: Optional[float]
    lon: Optional[float]
    extended_by: Optional[int]


@router.post("/", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
def create_trip(body: TripCreate, user_id: int = Depends(auth.get_current_user_id)):
    """Create a new trip"""
    # Validate that at least contact1 is provided (required by database)
    if body.contact1 is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one emergency contact (contact1) is required"
        )

    with db.engine.begin() as connection:
        # Verify activity exists and get its ID
        activity = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM activities
                WHERE LOWER(name) = LOWER(:activity)
                """
            ),
            {"activity": body.activity}
        ).fetchone()

        if not activity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found"
            )

        activity_id = activity.id

        # Verify contacts exist if provided
        for contact_id in [body.contact1, body.contact2, body.contact3]:
            if contact_id is not None:
                contact = connection.execute(
                    sqlalchemy.text(
                        """
                        SELECT id
                        FROM contacts
                        WHERE id = :contact_id AND user_id = :user_id
                        """
                    ),
                    {"contact_id": contact_id, "user_id": user_id}
                ).fetchone()

                if not contact:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Contact {contact_id} not found"
                    )

        # Generate unique tokens for checkin/checkout
        checkin_token = secrets.token_urlsafe(32)
        checkout_token = secrets.token_urlsafe(32)

        # Determine initial status based on start time
        current_time = datetime.now(timezone.utc)
        # Ensure start time is timezone-aware for comparison
        start_time = body.start if body.start.tzinfo else body.start.replace(tzinfo=timezone.utc)
        initial_status = 'planned' if start_time > current_time else 'active'

        # Insert trip
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO trips (
                    user_id, title, activity, start, eta, grace_min,
                    location_text, gen_lat, gen_lon, notes, status,
                    contact1, contact2, contact3, created_at,
                    checkin_token, checkout_token
                ) VALUES (
                    :user_id, :title, :activity, :start, :eta, :grace_min,
                    :location_text, :gen_lat, :gen_lon, :notes, :status,
                    :contact1, :contact2, :contact3, :created_at,
                    :checkin_token, :checkout_token
                )
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "title": body.title,
                "activity": activity_id,
                "start": body.start.isoformat(),
                "eta": body.eta.isoformat(),
                "grace_min": body.grace_min,
                "location_text": body.location_text or "Unknown Location",  # Default if not provided
                "gen_lat": body.gen_lat if body.gen_lat is not None else 0.0,  # Default to 0.0
                "gen_lon": body.gen_lon if body.gen_lon is not None else 0.0,  # Default to 0.0
                "notes": body.notes,
                "status": initial_status,
                "contact1": body.contact1,
                "contact2": body.contact2,
                "contact3": body.contact3,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "checkin_token": checkin_token,
                "checkout_token": checkout_token
            }
        )
        trip_id = result.fetchone()[0]

        # Fetch created trip with activity name
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, a.name as activity, t.start, t.eta, t.grace_min,
                       t.location_text, t.gen_lat, t.gen_lon, t.notes, t.status, t.completed_at,
                       t.last_checkin, t.created_at, t.contact1, t.contact2, t.contact3,
                       t.checkin_token, t.checkout_token
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.id = :trip_id
                """
            ),
            {"trip_id": trip_id}
        ).fetchone()

        return TripResponse(
            id=trip.id,
            user_id=trip.user_id,
            title=trip.title,
            activity=trip.activity,
            start=str(trip.start),
            eta=str(trip.eta),
            grace_min=trip.grace_min,
            location_text=trip.location_text,
            gen_lat=trip.gen_lat,
            gen_lon=trip.gen_lon,
            notes=trip.notes,
            status=trip.status,
            completed_at=str(trip.completed_at) if trip.completed_at else None,
            last_checkin=str(trip.last_checkin) if trip.last_checkin else None,
            created_at=str(trip.created_at),
            contact1=trip.contact1,
            contact2=trip.contact2,
            contact3=trip.contact3,
            checkin_token=trip.checkin_token,
            checkout_token=trip.checkout_token
        )


@router.get("/", response_model=List[TripResponse])
def get_trips(user_id: int = Depends(auth.get_current_user_id)):
    """Get all trips for the current user"""
    with db.engine.begin() as connection:
        trips = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, a.name as activity, t.start, t.eta, t.grace_min,
                       t.location_text, t.gen_lat, t.gen_lon, t.notes, t.status, t.completed_at,
                       t.last_checkin, t.created_at, t.contact1, t.contact2, t.contact3,
                       t.checkin_token, t.checkout_token
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.user_id = :user_id
                ORDER BY t.created_at DESC
                """
            ),
            {"user_id": user_id}
        ).fetchall()

        return [
            TripResponse(
                id=t.id,
                user_id=t.user_id,
                title=t.title,
                activity=t.activity,
                start=str(t.start),
                eta=str(t.eta),
                grace_min=t.grace_min,
                location_text=t.location_text,
                gen_lat=t.gen_lat,
                gen_lon=t.gen_lon,
                notes=t.notes,
                status=t.status,
                completed_at=str(t.completed_at) if t.completed_at else None,
                last_checkin=str(t.last_checkin) if t.last_checkin else None,
                created_at=str(t.created_at),
                contact1=t.contact1,
                contact2=t.contact2,
                contact3=t.contact3,
                checkin_token=t.checkin_token,
                checkout_token=t.checkout_token
            )
            for t in trips
        ]


@router.get("/active", response_model=Optional[TripResponse])
def get_active_trip(user_id: int = Depends(auth.get_current_user_id)):
    """Get the current active trip"""
    with db.engine.begin() as connection:
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, a.name as activity, t.start, t.eta, t.grace_min,
                       t.location_text, t.gen_lat, t.gen_lon, t.notes, t.status, t.completed_at,
                       t.last_checkin, t.created_at, t.contact1, t.contact2, t.contact3,
                       t.checkin_token, t.checkout_token
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.user_id = :user_id AND t.status = 'active'
                ORDER BY t.created_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id}
        ).fetchone()

        if not trip:
            return None

        return TripResponse(
            id=trip.id,
            user_id=trip.user_id,
            title=trip.title,
            activity=trip.activity,
            start=str(trip.start),
            eta=str(trip.eta),
            grace_min=trip.grace_min,
            location_text=trip.location_text,
            gen_lat=trip.gen_lat,
            gen_lon=trip.gen_lon,
            notes=trip.notes,
            status=trip.status,
            completed_at=str(trip.completed_at) if trip.completed_at else None,
            last_checkin=str(trip.last_checkin) if trip.last_checkin else None,
            created_at=str(trip.created_at),
            contact1=trip.contact1,
            contact2=trip.contact2,
            contact3=trip.contact3,
            checkin_token=trip.checkin_token,
            checkout_token=trip.checkout_token
        )


@router.get("/{trip_id}", response_model=TripResponse)
def get_trip(trip_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get a specific trip"""
    with db.engine.begin() as connection:
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT t.id, t.user_id, t.title, a.name as activity, t.start, t.eta, t.grace_min,
                       t.location_text, t.gen_lat, t.gen_lon, t.notes, t.status, t.completed_at,
                       t.last_checkin, t.created_at, t.contact1, t.contact2, t.contact3,
                       t.checkin_token, t.checkout_token
                FROM trips t
                JOIN activities a ON t.activity = a.id
                WHERE t.id = :trip_id AND t.user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        return TripResponse(
            id=trip.id,
            user_id=trip.user_id,
            title=trip.title,
            activity=trip.activity,
            start=str(trip.start),
            eta=str(trip.eta),
            grace_min=trip.grace_min,
            location_text=trip.location_text,
            gen_lat=trip.gen_lat,
            gen_lon=trip.gen_lon,
            notes=trip.notes,
            status=trip.status,
            completed_at=str(trip.completed_at) if trip.completed_at else None,
            last_checkin=str(trip.last_checkin) if trip.last_checkin else None,
            created_at=str(trip.created_at),
            contact1=trip.contact1,
            contact2=trip.contact2,
            contact3=trip.contact3,
            checkin_token=trip.checkin_token,
            checkout_token=trip.checkout_token
        )


@router.post("/{trip_id}/complete")
def complete_trip(trip_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Mark a trip as completed"""
    with db.engine.begin() as connection:
        # Verify trip ownership and status
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, status
                FROM trips
                WHERE id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        if trip.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trip is not active"
            )

        # Update trip status
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trips
                SET status = 'completed', completed_at = :completed_at
                WHERE id = :trip_id
                """
            ),
            {"trip_id": trip_id, "completed_at": datetime.now(timezone.utc).isoformat()}
        )

        return {"ok": True, "message": "Trip completed successfully"}


@router.post("/{trip_id}/extend")
def extend_trip(trip_id: int, minutes: int, user_id: int = Depends(auth.get_current_user_id)):
    """Extend the ETA of an active trip by the specified number of minutes"""
    with db.engine.begin() as connection:
        # Verify trip ownership and status
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, status, eta
                FROM trips
                WHERE id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        if trip.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only extend active trips"
            )

        # Parse current ETA and add minutes
        from datetime import timedelta
        current_eta = datetime.fromisoformat(trip.eta)
        new_eta = current_eta + timedelta(minutes=minutes)

        # Update trip ETA
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE trips
                SET eta = :new_eta
                WHERE id = :trip_id
                """
            ),
            {"trip_id": trip_id, "new_eta": new_eta.isoformat()}
        )

        # Log timeline event
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO events (user_id, trip_id, what, timestamp, extended_by)
                VALUES (:user_id, :trip_id, 'extended', :timestamp, :extended_by)
                """
            ),
            {
                "user_id": user_id,
                "trip_id": trip_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "extended_by": minutes
            }
        )

        return {"ok": True, "message": f"Trip extended by {minutes} minutes", "new_eta": new_eta.isoformat()}


@router.delete("/{trip_id}")
def delete_trip(trip_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Delete a trip"""
    with db.engine.begin() as connection:
        # Verify trip ownership
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM trips
                WHERE id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        # Delete trip (events will cascade)
        connection.execute(
            sqlalchemy.text("DELETE FROM trips WHERE id = :trip_id"),
            {"trip_id": trip_id}
        )

        return {"ok": True, "message": "Trip deleted successfully"}


@router.get("/{trip_id}/timeline", response_model=List[TimelineEvent])
def get_trip_timeline(trip_id: int, user_id: int = Depends(auth.get_current_user_id)):
    """Get timeline events for a specific trip"""
    with db.engine.begin() as connection:
        # Verify trip ownership
        trip = connection.execute(
            sqlalchemy.text(
                """
                SELECT id
                FROM trips
                WHERE id = :trip_id AND user_id = :user_id
                """
            ),
            {"trip_id": trip_id, "user_id": user_id}
        ).fetchone()

        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )

        # Fetch timeline events
        events = connection.execute(
            sqlalchemy.text(
                """
                SELECT id, what, timestamp, lat, lon, extended_by
                FROM events
                WHERE trip_id = :trip_id
                ORDER BY timestamp DESC
                """
            ),
            {"trip_id": trip_id}
        ).fetchall()

        return [
            TimelineEvent(
                id=e.id,
                what=e.what,
                timestamp=str(e.timestamp),
                lat=e.lat,
                lon=e.lon,
                extended_by=e.extended_by
            )
            for e in events
        ]
