"""Seed demo data for App Store screenshots.

Run this after init_db.py to populate realistic demo data:
    python seed_demo_data.py

This creates:
- 1 main demo user (you) with complete profile
- 3 demo friends with profiles
- 3 emergency contacts
- 1 active trip (for hero screenshot)
- 5 completed trips (for history)
- 1 upcoming trip (for upcoming section)
- Friendships and achievements data
"""
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from dotenv import load_dotenv
load_dotenv()

import os
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./homebound.db")

print(f"[seed_demo] Using database: {DATABASE_URL}")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

Session = sessionmaker(bind=engine)
session = Session()

# ============================================================================
# DEMO DATA CONFIGURATION - Edit these values for your screenshots
# ============================================================================

# Main demo user (this will be "you" in the app)
DEMO_USER = {
    "email": "demo@homebound.app",
    "first_name": "Hudson",
    "last_name": "Schmidt",
    "age": 28,
}

# Demo friends
DEMO_FRIENDS = [
    {"email": "kate@example.com", "first_name": "Kate", "last_name": "Evans", "age": 26},
    {"email": "chase@example.com", "first_name": "Chase", "last_name": "McClelland", "age": 31},
    {"email": "jonny@example.com", "first_name": "Jonny", "last_name": "Michaels", "age": 24},
]

# Emergency contacts for the demo user (email only - no phone in app)
DEMO_CONTACTS = [
    {"name": "Mom", "email": "mom@family.com"},
    {"name": "Dad", "email": "dad@family.com"},
    {"name": "Partner", "email": "partner@email.com"},
]

# Trips data - mix of statuses for different screenshots
# Times are relative to NOW for fresh data each time you run
NOW = datetime.now(timezone.utc).replace(tzinfo=None)  # UTC without tzinfo for SQLite compatibility

DEMO_TRIPS = [
    # ACTIVE TRIP - This is the hero screenshot!
    # Shows green "On Time" status with ~2 hours remaining
    {
        "title": "Morning Trail Run",
        "activity": "Hiking",  # Activity name (will be looked up)
        "start": NOW - timedelta(hours=1),
        "eta": NOW + timedelta(hours=2),  # 2 hours from now = green status
        "grace_min": 45,
        "location_text": "Runyon Canyon Park",
        "gen_lat": 34.1069,
        "gen_lon": -118.3506,
        "start_location_text": "Santa Monica, CA",
        "start_lat": 34.0195,
        "start_lon": -118.4912,
        "notes": "Taking the scenic route today!",
        "status": "active",
    },
    # UPCOMING TRIP - Shows in upcoming section
    {
        "title": "Weekend Camping Trip",
        "activity": "Camping",
        "start": NOW + timedelta(days=2, hours=8),
        "eta": NOW + timedelta(days=4, hours=18),
        "grace_min": 90,
        "location_text": "Joshua Tree National Park",
        "gen_lat": 33.8734,
        "gen_lon": -115.9010,
        "start_location_text": "Los Angeles, CA",
        "start_lat": 34.0522,
        "start_lon": -118.2437,
        "notes": "Stargazing and hiking with friends",
        "status": "planned",
    },
    # COMPLETED TRIPS - For history view
    {
        "title": "Pacific Coast Highway Drive",
        "activity": "Driving",
        "start": NOW - timedelta(days=3, hours=10),
        "eta": NOW - timedelta(days=3, hours=4),
        "grace_min": 30,
        "location_text": "Big Sur, CA",
        "gen_lat": 36.2704,
        "gen_lon": -121.8081,
        "start_location_text": "San Francisco, CA",
        "start_lat": 37.7749,
        "start_lon": -122.4194,
        "notes": "Road trip down the coast",
        "status": "completed",
        "completed_at": NOW - timedelta(days=3, hours=3),
    },
    {
        "title": "Mount Wilson Summit",
        "activity": "Hiking",
        "start": NOW - timedelta(days=7, hours=14),
        "eta": NOW - timedelta(days=7, hours=6),
        "grace_min": 60,
        "location_text": "Mount Wilson, CA",
        "gen_lat": 34.2261,
        "gen_lon": -118.0598,
        "start_location_text": "Pasadena, CA",
        "start_lat": 34.1478,
        "start_lon": -118.1445,
        "notes": "Training hike for bigger adventures",
        "status": "completed",
        "completed_at": NOW - timedelta(days=7, hours=5),
    },
    {
        "title": "Beach Bike Ride",
        "activity": "Biking",
        "start": NOW - timedelta(days=10, hours=8),
        "eta": NOW - timedelta(days=10, hours=5),
        "grace_min": 30,
        "location_text": "Venice Beach, CA",
        "gen_lat": 33.9850,
        "gen_lon": -118.4695,
        "start_location_text": "Santa Monica Pier",
        "start_lat": 34.0094,
        "start_lon": -118.4973,
        "notes": "Sunset ride along the boardwalk",
        "status": "completed",
        "completed_at": NOW - timedelta(days=10, hours=4, minutes=30),
    },
    {
        "title": "Rock Climbing Session",
        "activity": "Climbing",
        "start": NOW - timedelta(days=14, hours=10),
        "eta": NOW - timedelta(days=14, hours=6),
        "grace_min": 60,
        "location_text": "Malibu Creek State Park",
        "gen_lat": 34.1032,
        "gen_lon": -118.7279,
        "start_location_text": "Calabasas, CA",
        "start_lat": 34.1367,
        "start_lon": -118.6606,
        "notes": "Bouldering with the climbing crew",
        "status": "completed",
        "completed_at": NOW - timedelta(days=14, hours=5),
    },
    {
        "title": "Trail Running at Griffith",
        "activity": "Running",
        "start": NOW - timedelta(days=21, hours=7),
        "eta": NOW - timedelta(days=21, hours=5),
        "grace_min": 20,
        "location_text": "Griffith Observatory",
        "gen_lat": 34.1184,
        "gen_lon": -118.3004,
        "start_location_text": "Los Feliz, CA",
        "start_lat": 34.1062,
        "start_lon": -118.2889,
        "notes": "Early morning run to beat the crowds",
        "status": "completed",
        "completed_at": NOW - timedelta(days=21, hours=4, minutes=45),
    },
]

# ============================================================================
# SEED FUNCTIONS
# ============================================================================

def get_or_create_user(email, first_name, last_name, age):
    """Get existing user or create new one."""
    result = session.execute(
        text("SELECT id FROM users WHERE email = :email"),
        {"email": email}
    ).fetchone()

    if result:
        user_id = result[0]
        # Update profile
        session.execute(
            text("""
                UPDATE users
                SET first_name = :first_name, last_name = :last_name, age = :age
                WHERE id = :id
            """),
            {"id": user_id, "first_name": first_name, "last_name": last_name, "age": age}
        )
        print(f"  Updated user: {first_name} {last_name} (ID: {user_id})")
        return user_id
    else:
        session.execute(
            text("""
                INSERT INTO users (email, first_name, last_name, age, created_at)
                VALUES (:email, :first_name, :last_name, :age, :created_at)
            """),
            {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "age": age,
                "created_at": NOW,
            }
        )
        session.commit()
        result = session.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email}
        ).fetchone()
        user_id = result[0]
        print(f"  Created user: {first_name} {last_name} (ID: {user_id})")
        return user_id


def get_activity_id(activity_name):
    """Look up activity ID by name."""
    result = session.execute(
        text("SELECT id FROM activities WHERE name = :name"),
        {"name": activity_name}
    ).fetchone()
    if result:
        return result[0]
    # Fallback to "Other Activity"
    result = session.execute(
        text("SELECT id FROM activities WHERE name = 'Other Activity'")
    ).fetchone()
    return result[0] if result else 1


def create_contact(user_id, name, email):
    """Create an emergency contact for a user."""
    # Check if already exists
    result = session.execute(
        text("SELECT id FROM contacts WHERE user_id = :user_id AND email = :email"),
        {"user_id": user_id, "email": email}
    ).fetchone()

    if result:
        print(f"  Contact exists: {name}")
        return result[0]

    session.execute(
        text("""
            INSERT INTO contacts (user_id, name, email)
            VALUES (:user_id, :name, :email)
        """),
        {"user_id": user_id, "name": name, "email": email}
    )
    session.commit()
    result = session.execute(
        text("SELECT id FROM contacts WHERE user_id = :user_id AND email = :email"),
        {"user_id": user_id, "email": email}
    ).fetchone()
    print(f"  Created contact: {name}")
    return result[0]


def create_friendship(user_id_1, user_id_2):
    """Create a mutual friendship between two users."""
    # Ensure consistent ordering (user_id_1 < user_id_2)
    if user_id_1 > user_id_2:
        user_id_1, user_id_2 = user_id_2, user_id_1

    # Check if exists
    result = session.execute(
        text("""
            SELECT id FROM friendships
            WHERE user_id_1 = :u1 AND user_id_2 = :u2
        """),
        {"u1": user_id_1, "u2": user_id_2}
    ).fetchone()

    if result:
        return

    session.execute(
        text("""
            INSERT INTO friendships (user_id_1, user_id_2, created_at)
            VALUES (:u1, :u2, :now)
        """),
        {"u1": user_id_1, "u2": user_id_2, "now": NOW}
    )
    session.commit()


def create_trip(user_id, trip_data, contact_ids):
    """Create a trip with events."""
    activity_id = get_activity_id(trip_data["activity"])

    # Generate tokens
    checkin_token = secrets.token_urlsafe(32)
    checkout_token = secrets.token_urlsafe(32)

    # Check if trip with same title exists for user
    result = session.execute(
        text("SELECT id FROM trips WHERE user_id = :user_id AND title = :title"),
        {"user_id": user_id, "title": trip_data["title"]}
    ).fetchone()

    if result:
        print(f"  Trip exists: {trip_data['title']}")
        return result[0]

    session.execute(
        text("""
            INSERT INTO trips (
                user_id, title, start, eta, activity, grace_min,
                location_text, gen_lat, gen_lon,
                start_location_text, start_lat, start_lon,
                notes, status, created_at, completed_at,
                checkin_token, checkout_token,
                contact1, contact2, contact3,
                timezone, notify_self, is_group_trip
            ) VALUES (
                :user_id, :title, :start, :eta, :activity, :grace_min,
                :location_text, :gen_lat, :gen_lon,
                :start_location_text, :start_lat, :start_lon,
                :notes, :status, :created_at, :completed_at,
                :checkin_token, :checkout_token,
                :contact1, :contact2, :contact3,
                :timezone, :notify_self, :is_group_trip
            )
        """),
        {
            "user_id": user_id,
            "title": trip_data["title"],
            "start": trip_data["start"],
            "eta": trip_data["eta"],
            "activity": activity_id,
            "grace_min": trip_data["grace_min"],
            "location_text": trip_data["location_text"],
            "gen_lat": trip_data["gen_lat"],
            "gen_lon": trip_data["gen_lon"],
            "start_location_text": trip_data.get("start_location_text"),
            "start_lat": trip_data.get("start_lat"),
            "start_lon": trip_data.get("start_lon"),
            "notes": trip_data.get("notes"),
            "status": trip_data["status"],
            "created_at": NOW,
            "completed_at": trip_data.get("completed_at"),
            "checkin_token": checkin_token,
            "checkout_token": checkout_token,
            "contact1": contact_ids[0] if len(contact_ids) > 0 else None,
            "contact2": contact_ids[1] if len(contact_ids) > 1 else None,
            "contact3": contact_ids[2] if len(contact_ids) > 2 else None,
            "timezone": "America/Los_Angeles",
            "notify_self": False,
            "is_group_trip": False,
        }
    )
    session.commit()

    result = session.execute(
        text("SELECT id FROM trips WHERE user_id = :user_id AND title = :title"),
        {"user_id": user_id, "title": trip_data["title"]}
    ).fetchone()
    trip_id = result[0]

    # Create events for completed trips
    if trip_data["status"] == "completed":
        # Start event
        session.execute(
            text("""
                INSERT INTO events (user_id, trip_id, what, timestamp, lat, lon)
                VALUES (:user_id, :trip_id, 'started', :timestamp, :lat, :lon)
            """),
            {
                "user_id": user_id,
                "trip_id": trip_id,
                "timestamp": trip_data["start"],
                "lat": trip_data.get("start_lat"),
                "lon": trip_data.get("start_lon"),
            }
        )
        # Checkout event
        session.execute(
            text("""
                INSERT INTO events (user_id, trip_id, what, timestamp, lat, lon)
                VALUES (:user_id, :trip_id, 'checkout', :timestamp, :lat, :lon)
            """),
            {
                "user_id": user_id,
                "trip_id": trip_id,
                "timestamp": trip_data["completed_at"],
                "lat": trip_data["gen_lat"],
                "lon": trip_data["gen_lon"],
            }
        )
        session.commit()
    elif trip_data["status"] == "active":
        # Start event for active trip
        session.execute(
            text("""
                INSERT INTO events (user_id, trip_id, what, timestamp, lat, lon)
                VALUES (:user_id, :trip_id, 'started', :timestamp, :lat, :lon)
            """),
            {
                "user_id": user_id,
                "trip_id": trip_id,
                "timestamp": trip_data["start"],
                "lat": trip_data.get("start_lat"),
                "lon": trip_data.get("start_lon"),
            }
        )
        # Add a check-in event (30 mins ago)
        session.execute(
            text("""
                INSERT INTO events (user_id, trip_id, what, timestamp, lat, lon)
                VALUES (:user_id, :trip_id, 'checkin', :timestamp, :lat, :lon)
            """),
            {
                "user_id": user_id,
                "trip_id": trip_id,
                "timestamp": NOW - timedelta(minutes=30),
                "lat": 34.1050,  # Mid-point coordinates
                "lon": -118.3600,
            }
        )
        session.commit()

        # Get the check-in event ID and update last_checkin (it's a FK to events)
        checkin_event = session.execute(
            text("""
                SELECT id FROM events
                WHERE trip_id = :trip_id AND what = 'checkin'
                ORDER BY timestamp DESC LIMIT 1
            """),
            {"trip_id": trip_id}
        ).fetchone()

        if checkin_event:
            session.execute(
                text("UPDATE trips SET last_checkin = :event_id WHERE id = :id"),
                {"event_id": checkin_event[0], "id": trip_id}
            )
            session.commit()

    print(f"  Created trip: {trip_data['title']} ({trip_data['status']})")
    return trip_id


def seed_all():
    """Run all seed functions."""
    print("\n" + "="*60)
    print("SEEDING DEMO DATA FOR APP STORE SCREENSHOTS")
    print("="*60)

    # 1. Create main demo user
    print("\n[1/5] Creating demo user...")
    demo_user_id = get_or_create_user(
        DEMO_USER["email"],
        DEMO_USER["first_name"],
        DEMO_USER["last_name"],
        DEMO_USER["age"],
    )

    # 2. Create demo friends
    print("\n[2/5] Creating demo friends...")
    friend_ids = []
    for friend in DEMO_FRIENDS:
        friend_id = get_or_create_user(
            friend["email"],
            friend["first_name"],
            friend["last_name"],
            friend["age"],
        )
        friend_ids.append(friend_id)
        create_friendship(demo_user_id, friend_id)
    print(f"  Created {len(friend_ids)} friendships")

    # 3. Create emergency contacts
    print("\n[3/5] Creating emergency contacts...")
    contact_ids = []
    for contact in DEMO_CONTACTS:
        contact_id = create_contact(
            demo_user_id,
            contact["name"],
            contact["email"],
        )
        contact_ids.append(contact_id)

    # 4. Create trips
    print("\n[4/5] Creating demo trips...")
    for trip in DEMO_TRIPS:
        create_trip(demo_user_id, trip, contact_ids)

    # 5. Summary
    print("\n[5/5] Demo data seeded successfully!")
    print("\n" + "="*60)
    print("DEMO ACCOUNT CREDENTIALS")
    print("="*60)
    print(f"  Email: {DEMO_USER['email']}")
    print(f"  Name:  {DEMO_USER['first_name']} {DEMO_USER['last_name']}")
    print("\nTo login:")
    print("  1. Use magic link with this email")
    print("  2. Check console output for the 6-digit code")
    print("="*60 + "\n")


if __name__ == "__main__":
    seed_all()
    session.close()
