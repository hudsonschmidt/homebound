"""Seed demo data for App Store screenshots.

Run this to populate realistic demo data:
    python scripts/seed_demo_data.py

This script:
1. WIPES all existing data from the database
2. Seeds activities from the predefined list
3. Creates demo users, friends, contacts, and trips
"""
import secrets
import json
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
# ACTIVITIES DATA
# ============================================================================
ACTIVITIES = [
    {"name": "Hiking", "icon": "🥾", "default_grace_minutes": 45, "colors": {"accent": "#87CEEB", "primary": "#2D5016", "secondary": "#8B4513"}, "messages": {"start": "Happy trails!", "checkin": "Good job checking in! Keep going!", "overdue": "Haven't heard from you - everything OK? Make sure to check in when you can or extend your trip if you're still out there!", "checkout": "Trail conquered! Well done!", "encouragement": ["One step at a time!", "Nature is calling!", "Enjoy the journey!"]}, "safety_tips": ["Pack plenty of water and snacks", "Check weather conditions", "Know your limits", "Bring a first aid kit"], "order": 1},
    {"name": "Biking", "icon": "🚴", "default_grace_minutes": 30, "colors": {"accent": "#2ECC71", "primary": "#FF6B35", "secondary": "#4A90E2"}, "messages": {"start": "Ride safe!", "checkin": "Good job checking in! Keep going!", "overdue": "Checking in - how's the ride going?", "checkout": "Ride complete! Great job!", "encouragement": ["Wind in your hair!", "Keep those wheels turning!", "Enjoy the ride!"]}, "safety_tips": ["Always wear your helmet", "Check your brakes and tires", "Use lights in low visibility", "Stay hydrated"], "order": 2},
    {"name": "Running", "icon": "🏃", "default_grace_minutes": 20, "colors": {"accent": "#F39C12", "primary": "#E74C3C", "secondary": "#34495E"}, "messages": {"start": "Let's go! Feel the rhythm!", "checkin": "Good job checking in! Keep going!", "overdue": "Hope the run is going well - check in when you can!", "checkout": "Run complete! You crushed it!", "encouragement": ["You've got this!", "Keep that pace!", "Feel the burn!"]}, "safety_tips": ["Warm up before you start", "Stay visible with bright colors", "Run against traffic", "Stay hydrated"], "order": 3},
    {"name": "Walking", "icon": "🚶", "default_grace_minutes": 30, "colors": {"accent": "#A3B18A", "primary": "#2F6F3E", "secondary": "#1B4332"}, "messages": {"start": "Have fun, but stay aware!", "checkin": "Good job checking in!", "overdue": "Haven't heard from you - everything OK?", "checkout": "Walk conquered!", "encouragement": ["Fresh air!", "Good pace!", "You got this!"]}, "safety_tips": ["Stay visible near roads", "Bring water if it's warm", "Pay attention to your surroundings"], "order": 4},
    {"name": "Climbing", "icon": "🧗", "default_grace_minutes": 60, "colors": {"accent": "#3498DB", "primary": "#7F8C8D", "secondary": "#E67E22"}, "messages": {"start": "Time to send it! Climb safe!", "checkin": "Good job checking in! Keep going!", "overdue": "Haven't heard from you - everything good on the climb?", "checkout": "Summit reached! Amazing work!", "encouragement": ["Trust your grip!", "You're crushing it!", "The summit awaits!"]}, "safety_tips": ["Double-check all gear", "Never climb alone", "Know your limits", "Check anchor points"], "order": 5},
    {"name": "Camping", "icon": "🏕️", "default_grace_minutes": 90, "colors": {"accent": "#4CAF50", "primary": "#1A237E", "secondary": "#FF6F00"}, "messages": {"start": "Into the wild! Enjoy nature!", "checkin": "Good job checking in! Keep going!", "overdue": "Haven't heard from camp - everything good?", "checkout": "Back to civilization!", "encouragement": ["Under the stars!", "Wilderness mode: ON!", "Enjoy the peace!"]}, "safety_tips": ["Share your campsite location", "Check fire regulations", "Store food properly", "Bring weather-appropriate gear"], "order": 6},
    {"name": "Backpacking", "icon": "🎒", "default_grace_minutes": 60, "colors": {"accent": "#A1887F", "primary": "#795548", "secondary": "#8D6E63"}, "messages": {"start": "Pack light, adventure heavy!", "checkin": "Trail progress looking good!", "overdue": "Haven't heard from you - everything OK?", "checkout": "Epic journey complete!", "encouragement": ["Miles to go!", "Adventure continues!", "Pack's feeling lighter!"]}, "safety_tips": ["Pack light but essential gear", "Know water sources on your route", "Leave a detailed itinerary", "Check trail conditions ahead"], "order": 7},
    {"name": "Canyoneering", "icon": "🪢", "default_grace_minutes": 60, "colors": {"accent": "#9A8C98", "primary": "#3D405B", "secondary": "#2B2D42"}, "messages": {"start": "Have fun! Make sure to double check gear!", "checkin": "Good job checking in!", "overdue": "Haven't heard from you - everything OK?", "checkout": "Canyon conquered!", "encouragement": ["Smooth rappel!", "Stay steady!", "You've got this!"]}, "safety_tips": ["Check weather for flash floods", "Bring proper rappel gear and backup", "Make sure all equipment is in good condition"], "order": 8},
    {"name": "Skiing", "icon": "⛷️", "default_grace_minutes": 45, "colors": {"accent": "#B3E5FC", "primary": "#00BCD4", "secondary": "#E1F5FE"}, "messages": {"start": "Fresh powder awaits! Ski safe!", "checkin": "Carving those slopes!", "overdue": "Haven't heard from you - everything OK?", "checkout": "Slopes conquered! Well done!", "encouragement": ["Fresh tracks!", "Perfect turns!", "Mountain vibes!"]}, "safety_tips": ["Check binding adjustments", "Stay on marked trails", "Monitor avalanche conditions", "Wear appropriate layers"], "order": 9},
    {"name": "Snowboarding", "icon": "🏂", "default_grace_minutes": 45, "colors": {"accent": "#81D4FA", "primary": "#039BE5", "secondary": "#4FC3F7"}, "messages": {"start": "Shred the gnar! Board safe!", "checkin": "Shredding nicely!", "overdue": "Haven't heard from you - everything OK?", "checkout": "Session complete! Awesome runs!", "encouragement": ["Send it!", "Powder day!", "Mountain magic!"]}, "safety_tips": ["Wear wrist guards and helmet", "Check snow conditions", "Stay within your skill level", "Keep bindings properly adjusted"], "order": 10},
    {"name": "Snowshoeing", "icon": "❄️", "default_grace_minutes": 60, "colors": {"accent": "#A8E6FF", "primary": "#005F73", "secondary": "#94D2BD"}, "messages": {"start": "Strap in—fresh snow awaits!", "checkin": "Nice check-in—stay warm!", "overdue": "Haven't heard from you - everything OK?", "checkout": "Slopes conquered! Well done!", "encouragement": ["Keep going!", "Crisp air!", "Mountain vibes!"]}, "safety_tips": ["Watch for avalanche risk", "Dress in layers", "Stay hydrated even in the cold"], "order": 11},
    {"name": "Kayaking", "icon": "🛶", "default_grace_minutes": 45, "colors": {"accent": "#80DEEA", "primary": "#006064", "secondary": "#4DB6AC"}, "messages": {"start": "Paddle on! Enjoy the water!", "checkin": "Paddling strong!", "overdue": "Haven't heard from you - everything OK?", "checkout": "Back to shore! Great paddle!", "encouragement": ["Paddle strong!", "Go with the flow!", "Water therapy!"]}, "safety_tips": ["Always wear a life jacket", "Check weather and water conditions", "Know your exit points", "Bring a whistle and light"], "order": 12},
    {"name": "Sailing", "icon": "⛵", "default_grace_minutes": 60, "colors": {"accent": "#90CAF9", "primary": "#1976D2", "secondary": "#64B5F6"}, "messages": {"start": "Wind in your sails! Bon voyage!", "checkin": "Smooth sailing so far!", "overdue": "Haven't heard from you - everything OK?", "checkout": "Docked safely! Smooth sailing!", "encouragement": ["Catch the wind!", "Smooth sailing!", "Ocean freedom!"]}, "safety_tips": ["Check marine weather forecast", "Wear life jacket on deck", "Know emergency procedures", "Have backup navigation"], "order": 13},
    {"name": "River Rafting", "icon": "🚣", "default_grace_minutes": 60, "colors": {"accent": "#B7E4C7", "primary": "#1D4ED8", "secondary": "#0B3D91"}, "messages": {"start": "Have fun! Make sure to double check gear!", "checkin": "Good job checking in!", "overdue": "Haven't heard from you - everything OK?", "checkout": "River conquered!", "encouragement": ["Send it!", "Clean line!", "Strong strokes!"]}, "safety_tips": ["Wear a properly fitted PFD", "Scout rapids and know your limits", "Secure gear and know the exit points"], "order": 14},
    {"name": "Fishing", "icon": "🎣", "default_grace_minutes": 60, "colors": {"accent": "#B2DFDB", "primary": "#004D40", "secondary": "#80CBC4"}, "messages": {"start": "Tight lines! Hope they're biting!", "checkin": "Any luck out there?", "overdue": "Haven't heard from you - everything OK?", "checkout": "Lines are in! Hope you caught some!", "encouragement": ["Patience pays!", "Fish are waiting!", "Perfect day!"]}, "safety_tips": ["Check local regulations", "Wear sun protection", "Be aware of weather changes", "Handle hooks carefully"], "order": 15},
    {"name": "Surfing", "icon": "🏄", "default_grace_minutes": 30, "colors": {"accent": "#80DEEA", "primary": "#00ACC1", "secondary": "#4DD0E1"}, "messages": {"start": "Catch those waves! Surf's up!", "checkin": "Catching some good ones!", "overdue": "Haven't heard from you - everything OK?", "checkout": "Session done! Epic waves!", "encouragement": ["Next wave's yours!", "Ocean energy!", "Surf's always up!"]}, "safety_tips": ["Check surf conditions and tides", "Use a leash always", "Know local hazards and currents", "Respect local surf etiquette"], "order": 16},
    {"name": "Scuba Diving", "icon": "🤿", "default_grace_minutes": 45, "colors": {"accent": "#4FC3F7", "primary": "#01579B", "secondary": "#0288D1"}, "messages": {"start": "Dive deep! Explore the blue!", "checkin": "How's the underwater world?", "overdue": "Haven't heard from you - everything OK?", "checkout": "Surface reached! Amazing dive!", "encouragement": ["Breathe easy!", "Ocean wonders await!", "Dive deeper!"]}, "safety_tips": ["Never dive alone", "Check equipment thoroughly", "Monitor air supply constantly", "Know decompression limits"], "order": 17},
    {"name": "Free Diving", "icon": "🏊", "default_grace_minutes": 30, "colors": {"accent": "#81D4FA", "primary": "#0277BD", "secondary": "#29B6F6"}, "messages": {"start": "One breath, one dive! Be safe!", "checkin": "Great depth control!", "overdue": "Haven't heard from you - everything OK?", "checkout": "Dive complete! Impressive!", "encouragement": ["Mind over matter!", "One with the water!", "Pure focus!"]}, "safety_tips": ["Never freedive alone", "Know your limits", "Practice proper breathing technique", "Watch for signs of blackout"], "order": 18},
    {"name": "Snorkeling", "icon": "🥽", "default_grace_minutes": 30, "colors": {"accent": "#80DEEA", "primary": "#0097A7", "secondary": "#26C6DA"}, "messages": {"start": "Explore the shallows! Have fun!", "checkin": "Enjoying the marine life!", "overdue": "Haven't heard from you - everything OK?", "checkout": "Back on dry land!", "encouragement": ["Crystal clear!", "Marine paradise!", "Float on!"]}, "safety_tips": ["Check mask seal before entering", "Stay aware of currents", "Use fins for efficiency", "Apply reef-safe sunscreen"], "order": 19},
    {"name": "Horseback Riding", "icon": "🐎", "default_grace_minutes": 45, "colors": {"accent": "#BCAAA4", "primary": "#5D4037", "secondary": "#8D6E63"}, "messages": {"start": "Saddle up! Happy trails!", "checkin": "Riding steady!", "overdue": "Haven't heard from you - everything OK?", "checkout": "Ride complete! Well done!", "encouragement": ["Ride on!", "Trust your horse!", "Trail magic!"]}, "safety_tips": ["Wear a proper helmet", "Check tack before mounting", "Match horse to skill level", "Stay calm around horses"], "order": 20},
    {"name": "Driving", "icon": "🚗", "default_grace_minutes": 30, "colors": {"accent": "#ECF0F1", "primary": "#2C3E50", "secondary": "#16A085"}, "messages": {"start": "Safe travels! Drive carefully!", "checkin": "Good job checking in! Keep going!", "overdue": "Just checking you arrived safely - let us know!", "checkout": "Arrived safely! Journey complete!", "encouragement": ["Enjoy the drive!", "Safe and steady!", "Almost there!"]}, "safety_tips": ["Take breaks on long drives", "Check your route before starting", "Keep your phone charged", "Watch for weather conditions"], "order": 21},
    {"name": "Flying", "icon": "✈️", "default_grace_minutes": 120, "colors": {"accent": "#9B59B6", "primary": "#3498DB", "secondary": "#ECF0F1"}, "messages": {"start": "Bon voyage! Have a great flight!", "checkin": "Good job checking in! Keep going!", "overdue": "Flight should have landed - everything OK?", "checkout": "Welcome to your destination!", "encouragement": ["Adventure awaits!", "Enjoy the views!", "Safe travels!"]}, "safety_tips": ["Arrive at airport early", "Keep documents handy", "Stay hydrated during flight", "Account for delays"], "order": 22},
    {"name": "Drinking", "icon": "🍻", "default_grace_minutes": 45, "colors": {"accent": "#C0C0C0", "primary": "#F28E1C", "secondary": "#154734"}, "messages": {"start": "Have fun! Be smart!", "checkin": "Good job checking in!", "overdue": "Haven't heard from you - everything OK?", "checkout": "Night conquered!", "encouragement": ["Good job!", "Drink some water!", "Keep crushing it!"]}, "safety_tips": ["Do not drink and drive", "Know your limits", "Always watch your drink"], "order": 23},
    {"name": "Other Activity", "icon": "📍", "default_grace_minutes": 30, "colors": {"accent": "#4ECDC4", "primary": "#6C63FF", "secondary": "#A8A8A8"}, "messages": {"start": "Have a great adventure!", "checkin": "Thanks for checking in!", "overdue": "Just checking in - everything OK?", "checkout": "Welcome back! Hope it was great!", "encouragement": ["You're doing great!", "Stay safe!", "Enjoy!"]}, "safety_tips": ["Stay aware of your surroundings", "Keep your phone charged", "Share your location with someone", "Trust your instincts"], "order": 24},
]

# ============================================================================
# DEMO DATA CONFIGURATION 
# ============================================================================

# Main demo user (this will be "you" in the app)
DEMO_USER = {
    "email": "demo@homeboundapp.com",
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
    {"name": "Partner", "email": "partner@example.com"},
]

# Trips data - mix of statuses for different screenshots
# Times are relative to NOW for fresh data each time you run
NOW = datetime.now().replace(tzinfo=None)  # UTC without tzinfo for SQLite compatibility

DEMO_TRIPS = [
    # ACTIVE TRIP - This is the hero screenshot!
    # Shows green "On Time" status with ~2 hours remaining
    {
        "title": "Morning Trail Run",
        "activity": "Hiking",
        "start": NOW - timedelta(hours=1),
        "eta": NOW + timedelta(hours=2),
        "grace_min": 45,
        "location_text": "Runyon Canyon Park",
        "gen_lat": 34.1069,
        "gen_lon": -118.3506,
        "start_location_text": "Santa Monica, CA",
        "start_lat": 34.0195,
        "start_lon": -118.4912,
        "has_separate_locations": True,
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
        "has_separate_locations": False,
        "notes": "Stargazing and hiking with friends",
        "status": "planned",
    },
    # GROUP TRIP - Demonstrates group trip functionality
    {
        "title": "Friday Night Bar Hopping",
        "activity": "Drinking",
        "start": NOW - timedelta(days=5, hours=4),
        "eta": NOW - timedelta(days=5) + timedelta(hours=2),  # Late night return
        "grace_min": 60,
        "location_text": "Downtown LA",
        "gen_lat": 34.0407,
        "gen_lon": -118.2468,
        "start_location_text": "Hollywood, CA",
        "start_lat": 34.0928,
        "start_lon": -118.3287,
        "has_separate_locations": False,
        "notes": "Hitting up the best spots downtown with the crew!",
        "status": "completed",
        "completed_at": NOW - timedelta(days=5) + timedelta(hours=1, minutes=30),
        "is_group_trip": True,
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
        "has_separate_locations": True,
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
        "has_separate_locations": False,
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
        "has_separate_locations": True,
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
        "has_separate_locations": False,
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
        "has_separate_locations": False,
        "notes": "Early morning run to beat the crowds",
        "status": "completed",
        "completed_at": NOW - timedelta(days=21, hours=4, minutes=45),
    },
]

# ============================================================================
# SEED FUNCTIONS
# ============================================================================

def wipe_database():
    """Wipe all data from the database (except schema)."""
    print("\n[WIPE] Clearing all existing data...")

    # First, break circular references
    # trips.last_checkin references events, and events.trip_id references trips
    try:
        session.execute(text("UPDATE trips SET last_checkin = NULL"))
        session.commit()
        print("  Cleared trips.last_checkin references")
    except Exception as e:
        session.rollback()
        print(f"  Skipped last_checkin clear: {e}")

    # Also clear contact references from trips
    try:
        session.execute(text("UPDATE trips SET contact1 = NULL, contact2 = NULL, contact3 = NULL"))
        session.commit()
        print("  Cleared trips.contact references")
    except Exception as e:
        session.rollback()
        print(f"  Skipped contact clear: {e}")

    # Order matters due to foreign key constraints
    # Delete in reverse dependency order
    tables_to_clear = [
        "checkout_votes",
        "participant_trip_contacts",
        "trip_participants",
        "events",
        "trips",
        "friendships",
        "contacts",
        "devices",
        "login_tokens",
        "subscriptions",
        "users",
        "activities",
    ]

    for table in tables_to_clear:
        try:
            session.execute(text(f"DELETE FROM {table}"))
            session.commit()
            print(f"  Cleared {table}")
        except Exception as e:
            session.rollback()
            print(f"  Skipped {table}: {e}")

    print("[WIPE] Database cleared!")


def seed_activities():
    """Seed all activities."""
    print("\n[ACTIVITIES] Seeding activities...")

    for activity in ACTIVITIES:
        session.execute(
            text("""
                INSERT INTO activities (name, icon, default_grace_minutes, colors, messages, safety_tips, "order")
                VALUES (:name, :icon, :default_grace_minutes, :colors, :messages, :safety_tips, :order)
            """),
            {
                "name": activity["name"],
                "icon": activity["icon"],
                "default_grace_minutes": activity["default_grace_minutes"],
                "colors": json.dumps(activity["colors"]),
                "messages": json.dumps(activity["messages"]),
                "safety_tips": json.dumps(activity["safety_tips"]),
                "order": activity["order"],
            }
        )
    session.commit()
    print(f"  Seeded {len(ACTIVITIES)} activities")


def grant_subscription(user_id):
    """Grant plus subscription to a user."""
    # Set subscription to expire 1 year from now
    expires_at = NOW + timedelta(days=365)
    session.execute(
        text("""
            UPDATE users
            SET subscription_tier = 'plus', subscription_expires_at = :expires_at
            WHERE id = :user_id
        """),
        {"user_id": user_id, "expires_at": expires_at}
    )
    session.commit()
    print(f"  Granted plus subscription (expires {expires_at.strftime('%Y-%m-%d')})")


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


def add_trip_participant(trip_id, user_id, owner_id, role="participant"):
    """Add a participant to a group trip."""
    # Check if already exists
    result = session.execute(
        text("SELECT id FROM trip_participants WHERE trip_id = :trip_id AND user_id = :user_id"),
        {"trip_id": trip_id, "user_id": user_id}
    ).fetchone()

    if result:
        return result[0]

    session.execute(
        text("""
            INSERT INTO trip_participants (
                trip_id, user_id, role, status, invited_at, invited_by, joined_at,
                checkin_interval_min, notify_start_hour, notify_end_hour
            )
            VALUES (
                :trip_id, :user_id, :role, 'accepted', :now, :invited_by, :now,
                :checkin_interval_min, :notify_start_hour, :notify_end_hour
            )
        """),
        {
            "trip_id": trip_id,
            "user_id": user_id,
            "role": role,
            "invited_by": owner_id if role == "participant" else None,
            "now": NOW,
            "checkin_interval_min": 30,  # Default 30 min reminders
            "notify_start_hour": None,   # No quiet hours restriction
            "notify_end_hour": None,
        }
    )
    session.commit()
    result = session.execute(
        text("SELECT id FROM trip_participants WHERE trip_id = :trip_id AND user_id = :user_id"),
        {"trip_id": trip_id, "user_id": user_id}
    ).fetchone()
    return result[0]


def create_trip(user_id, trip_data, contact_ids):
    """Create a trip with events."""
    activity_id = get_activity_id(trip_data["activity"])

    # Generate tokens
    checkin_token = secrets.token_urlsafe(32)
    checkout_token = secrets.token_urlsafe(32)

    is_group_trip = trip_data.get("is_group_trip", False)

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
                start_location_text, start_lat, start_lon, has_separate_locations,
                notes, status, created_at, completed_at,
                checkin_token, checkout_token,
                contact1, contact2, contact3,
                timezone, notify_self, is_group_trip
            ) VALUES (
                :user_id, :title, :start, :eta, :activity, :grace_min,
                :location_text, :gen_lat, :gen_lon,
                :start_location_text, :start_lat, :start_lon, :has_separate_locations,
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
            "has_separate_locations": trip_data.get("has_separate_locations", False),
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
            "is_group_trip": is_group_trip,
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

    # 0. Wipe existing data
    wipe_database()

    # 1. Seed activities
    seed_activities()

    # 2. Create main demo user
    print("\n[2/8] Creating demo user...")
    demo_user_id = get_or_create_user(
        DEMO_USER["email"],
        DEMO_USER["first_name"],
        DEMO_USER["last_name"],
        DEMO_USER["age"],
    )
    grant_subscription(demo_user_id)

    # 3. Create demo friends
    print("\n[3/8] Creating demo friends...")
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

    # 4. Create emergency contacts
    print("\n[4/8] Creating emergency contacts...")
    contact_ids = []
    for contact in DEMO_CONTACTS:
        contact_id = create_contact(
            demo_user_id,
            contact["name"],
            contact["email"],
        )
        contact_ids.append(contact_id)

    # 5. Create trips
    print("\n[5/8] Creating demo trips...")
    group_trip_ids = []
    for trip in DEMO_TRIPS:
        trip_id = create_trip(demo_user_id, trip, contact_ids)
        if trip.get("is_group_trip"):
            group_trip_ids.append(trip_id)

    # 6. Add participants to group trips
    print("\n[6/8] Adding participants to group trips...")
    for trip_id in group_trip_ids:
        # Add owner as participant
        add_trip_participant(trip_id, demo_user_id, demo_user_id, role="owner")
        # Add friends as participants
        for friend_id in friend_ids:
            add_trip_participant(trip_id, friend_id, demo_user_id, role="participant")
        print(f"  Added {len(friend_ids) + 1} participants to group trip {trip_id}")

    # 7. Summary
    print("\n[7/8] Demo data seeded successfully!")
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
