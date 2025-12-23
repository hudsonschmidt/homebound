"""New tables

Revision ID: a7818caa48a6
Revises: ae8f29841bb8
Create Date: 2025-10-31 16:56:43.466311

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'a7818caa48a6'
down_revision: Union[str, Sequence[str], None] = 'ae8f29841bb8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop old tables that will be replaced with new schema
    op.drop_table("events")
    op.drop_table("contacts")
    op.drop_table("devices")
    op.drop_index(op.f('ix_login_tokens_email'), table_name='login_tokens')
    op.drop_table("login_tokens")
    op.drop_table("plans")
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table("users")

    # Create users table with new schema
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("first_name", sa.Text, nullable=False),
        sa.Column("last_name", sa.Text, nullable=False),
        sa.Column("age", sa.Integer, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", sa.TIMESTAMP, nullable=True),
    )

    activities_table = op.create_table(
        "activities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("icon", sa.Text, nullable=False),
        sa.Column("default_grace_minutes", sa.Integer, nullable=False),
        sa.Column("colors", JSONB, nullable=False),
        sa.Column("messages", JSONB, nullable=False),
        sa.Column("safety_tips", JSONB, nullable=False),
        sa.Column("order", sa.Integer, nullable=False, autoincrement=True),
    )

    op.bulk_insert(activities_table, [
        {
            'name': 'Hiking',
            'icon': '🥾',
            'default_grace_minutes': 45,
            'colors': {"accent": "#87CEEB", "primary": "#2D5016", "secondary": "#8B4513"},
            'messages': {"start": "Happy trails!", "checkin": "Good job checking in! Keep going!", "overdue": "Haven't heard from you - everything OK? Make sure to check in when you can or extend your trip if you're still out there!", "checkout": "Trail conquered! Well done!", "encouragement": ["One step at a time!", "Nature is calling!", "Enjoy the journey!"]},
            'safety_tips': ["Pack plenty of water and snacks", "Check weather conditions", "Know your limits", "Bring a first aid kit"],
            'order': 1,
        },
        {
            'name': 'Biking',
            'icon': '🚴',
            'default_grace_minutes': 30,
            'colors': {"accent": "#2ECC71", "primary": "#FF6B35", "secondary": "#4A90E2"},
            'messages': {"start": "Ride safe!", "checkin": "Good job checking in! Keep going!", "overdue": "Checking in - how's the ride going?", "checkout": "Ride complete! Great job!", "encouragement": ["Wind in your hair!", "Keep those wheels turning!", "Enjoy the ride!"]},
            'safety_tips': ["Always wear your helmet", "Check your brakes and tires", "Use lights in low visibility", "Stay hydrated"],
            'order': 2,
        },
        {
            'name': 'Running',
            'icon': '🏃',
            'default_grace_minutes': 20,
            'colors': {"accent": "#F39C12", "primary": "#E74C3C", "secondary": "#34495E"},
            'messages': {"start": "Let's go! Feel the rhythm!", "checkin": "Good job checking in! Keep going!", "overdue": "Hope the run is going well - check in when you can!", "checkout": "Run complete! You crushed it!", "encouragement": ["You've got this!", "Keep that pace!", "Feel the burn!"]},
            'safety_tips': ["Warm up before you start", "Stay visible with bright colors", "Run against traffic", "Stay hydrated"],
            'order': 3,
        },
        {
            'name': 'Climbing',
            'icon': '🧗',
            'default_grace_minutes': 60,
            'colors': {"accent": "#3498DB", "primary": "#7F8C8D", "secondary": "#E67E22"},
            'messages': {"start": "Time to send it! Climb safe!", "checkin": "Good job checking in! Keep going!", "overdue": "Haven't heard from you - everything good on the climb?", "checkout": "Summit reached! Amazing work!", "encouragement": ["Trust your grip!", "You're crushing it!", "The summit awaits!"]},
            'safety_tips': ["Double-check all gear", "Never climb alone", "Know your limits", "Check anchor points"],
            'order': 4,
        },
        {
            'name': 'Camping',
            'icon': '🏕️',
            'default_grace_minutes': 90,
            'colors': {"accent": "#4CAF50", "primary": "#1A237E", "secondary": "#FF6F00"},
            'messages': {"start": "Into the wild! Enjoy nature!", "checkin": "Good job checking in! Keep going!", "overdue": "Haven't heard from camp - everything good?", "checkout": "Back to civilization!", "encouragement": ["Under the stars!", "Wilderness mode: ON!", "Enjoy the peace!"]},
            'safety_tips': ["Share your campsite location", "Check fire regulations", "Store food properly", "Bring weather-appropriate gear"],
            'order': 5,
        },
        {
            'name': 'Backpacking',
            'icon': '🎒',
            'default_grace_minutes': 60,
            'colors': {"accent": "#A1887F", "primary": "#795548", "secondary": "#8D6E63"},
            'messages': {"start": "Pack light, adventure heavy!", "checkin": "Trail progress looking good!", "overdue": "Haven't heard from you - everything OK? Make sure to check in when you can or extend your trip if you're still out there!", "checkout": "Epic journey complete!", "encouragement": ["Miles to go!", "Adventure continues!", "Pack's feeling lighter!"]},
            'safety_tips': ["Pack light but essential gear", "Know water sources on your route", "Leave a detailed itinerary", "Check trail conditions ahead"],
            'order': 6,
        },
        {
            'name': 'Skiing',
            'icon': '⛷️',
            'default_grace_minutes': 45,
            'colors': {"accent": "#B3E5FC", "primary": "#00BCD4", "secondary": "#E1F5FE"},
            'messages': {"start": "Fresh powder awaits! Ski safe!", "checkin": "Carving those slopes!", "overdue": "Haven't heard from you - everything OK? Make sure to check in when you can or extend your trip if you're still out there!", "checkout": "Slopes conquered! Well done!", "encouragement": ["Fresh tracks!", "Perfect turns!", "Mountain vibes!"]},
            'safety_tips': ["Check binding adjustments", "Stay on marked trails", "Monitor avalanche conditions", "Wear appropriate layers"],
            'order': 7,
        },
        {
            'name': 'Snowboarding',
            'icon': '🏂',
            'default_grace_minutes': 45,
            'colors': {"accent": "#81D4FA", "primary": "#039BE5", "secondary": "#4FC3F7"},
            'messages': {"start": "Shred the gnar! Board safe!", "checkin": "Shredding nicely!", "overdue": "Haven't heard from you - everything OK? Make sure to check in when you can or extend your trip if you're still out there!", "checkout": "Session complete! Awesome runs!", "encouragement": ["Send it!", "Powder day!", "Mountain magic!"]},
            'safety_tips': ["Wear wrist guards and helmet", "Check snow conditions", "Stay within your skill level", "Keep bindings properly adjusted"],
            'order': 8,
        },
        {
            'name': 'Kayaking',
            'icon': '🛶',
            'default_grace_minutes': 45,
            'colors': {"accent": "#80DEEA", "primary": "#006064", "secondary": "#4DB6AC"},
            'messages': {"start": "Paddle on! Enjoy the water!", "checkin": "Paddling strong!", "overdue": "Haven't heard from you - everything OK? Make sure to check in when you can or extend your trip if you're still out there!", "checkout": "Back to shore! Great paddle!", "encouragement": ["Paddle strong!", "Go with the flow!", "Water therapy!"]},
            'safety_tips': ["Always wear a life jacket", "Check weather and water conditions", "Know your exit points", "Bring a whistle and light"],
            'order': 9,
        },
        {
            'name': 'Sailing',
            'icon': '⛵',
            'default_grace_minutes': 60,
            'colors': {"accent": "#90CAF9", "primary": "#1976D2", "secondary": "#64B5F6"},
            'messages': {"start": "Wind in your sails! Bon voyage!", "checkin": "Smooth sailing so far!", "overdue": "Haven't heard from you - everything OK? Make sure to check in when you can or extend your trip if you're still out there!", "checkout": "Docked safely! Smooth sailing!", "encouragement": ["Catch the wind!", "Smooth sailing!", "Ocean freedom!"]},
            'safety_tips': ["Check marine weather forecast", "Wear life jacket on deck", "Know emergency procedures", "Have backup navigation"],
            'order': 10,
        },
        {
            'name': 'Fishing',
            'icon': '🎣',
            'default_grace_minutes': 60,
            'colors': {"accent": "#B2DFDB", "primary": "#004D40", "secondary": "#80CBC4"},
            'messages': {"start": "Tight lines! Hope they're biting!", "checkin": "Any luck out there?", "overdue": "Haven't heard from you - everything OK? Make sure to check in when you can or extend your trip if you're still out there!", "checkout": "Lines are in! Hope you caught some!", "encouragement": ["Patience pays!", "Fish are waiting!", "Perfect day!"]},
            'safety_tips': ["Check local regulations", "Wear sun protection", "Be aware of weather changes", "Handle hooks carefully"],
            'order': 11,
        },
        {
            'name': 'Surfing',
            'icon': '🏄',
            'default_grace_minutes': 30,
            'colors': {"accent": "#80DEEA", "primary": "#00ACC1", "secondary": "#4DD0E1"},
            'messages': {"start": "Catch those waves! Surf's up!", "checkin": "Catching some good ones!", "overdue": "Haven't heard from you - everything OK? Make sure to check in when you can or extend your trip if you're still out there!", "checkout": "Session done! Epic waves!", "encouragement": ["Next wave's yours!", "Ocean energy!", "Surf's always up!"]},
            'safety_tips': ["Check surf conditions and tides", "Use a leash always", "Know local hazards and currents", "Respect local surf etiquette"],
            'order': 12,
        },
        {
            'name': 'Scuba Diving',
            'icon': '🤿',
            'default_grace_minutes': 45,
            'colors': {"accent": "#4FC3F7", "primary": "#01579B", "secondary": "#0288D1"},
            'messages': {"start": "Dive deep! Explore the blue!", "checkin": "How's the underwater world?", "overdue": "Haven't heard from you - everything OK? Make sure to check in when you can or extend your trip if you're still out there!", "checkout": "Surface reached! Amazing dive!", "encouragement": ["Breathe easy!", "Ocean wonders await!", "Dive deeper!"]},
            'safety_tips': ["Never dive alone", "Check equipment thoroughly", "Monitor air supply constantly", "Know decompression limits"],
            'order': 13,
        },
        {
            'name': 'Free Diving',
            'icon': '🏊',
            'default_grace_minutes': 30,
            'colors': {"accent": "#81D4FA", "primary": "#0277BD", "secondary": "#29B6F6"},
            'messages': {"start": "One breath, one dive! Be safe!", "checkin": "Great depth control!", "overdue": "Haven't heard from you - everything OK? Make sure to check in when you can or extend your trip if you're still out there!", "checkout": "Dive complete! Impressive!", "encouragement": ["Mind over matter!", "One with the water!", "Pure focus!"]},
            'safety_tips': ["Never freedive alone", "Know your limits", "Practice proper breathing technique", "Watch for signs of blackout"],
            'order': 14,
        },
        {
            'name': 'Snorkeling',
            'icon': '🥽',
            'default_grace_minutes': 30,
            'colors': {"accent": "#80DEEA", "primary": "#0097A7", "secondary": "#26C6DA"},
            'messages': {"start": "Explore the shallows! Have fun!", "checkin": "Enjoying the marine life!", "overdue": "Haven't heard from you - everything OK? Make sure to check in when you can or extend your trip if you're still out there!", "checkout": "Back on dry land!", "encouragement": ["Crystal clear!", "Marine paradise!", "Float on!"]},
            'safety_tips': ["Check mask seal before entering", "Stay aware of currents", "Use fins for efficiency", "Apply reef-safe sunscreen"],
            'order': 15,
        },
        {
            'name': 'Horseback Riding',
            'icon': '🐎',
            'default_grace_minutes': 45,
            'colors': {"accent": "#BCAAA4", "primary": "#5D4037", "secondary": "#8D6E63"},
            'messages': {"start": "Saddle up! Happy trails!", "checkin": "Riding steady!", "overdue": "Haven't heard from you - everything OK? Make sure to check in when you can or extend your trip if you're still out there!", "checkout": "Ride complete! Well done!", "encouragement": ["Ride on!", "Trust your horse!", "Trail magic!"]},
            'safety_tips': ["Wear a proper helmet", "Check tack before mounting", "Match horse to skill level", "Stay calm around horses"],
            'order': 16,
        },
        {
            'name': 'Driving',
            'icon': '🚗',
            'default_grace_minutes': 30,
            'colors': {"accent": "#ECF0F1", "primary": "#2C3E50", "secondary": "#16A085"},
            'messages': {"start": "Safe travels! Drive carefully!", "checkin": "Good job checking in! Keep going!", "overdue": "Just checking you arrived safely - let us know!", "checkout": "Arrived safely! Journey complete!", "encouragement": ["Enjoy the drive!", "Safe and steady!", "Almost there!"]},
            'safety_tips': ["Take breaks on long drives", "Check your route before starting", "Keep your phone charged", "Watch for weather conditions"],
            'order': 17,
        },
        {
            'name': 'Flying',
            'icon': '✈️',
            'default_grace_minutes': 120,
            'colors': {"accent": "#9B59B6", "primary": "#3498DB", "secondary": "#ECF0F1"},
            'messages': {"start": "Bon voyage! Have a great flight!", "checkin": "Good job checking in! Keep going!", "overdue": "Flight should have landed - everything OK?", "checkout": "Welcome to your destination!", "encouragement": ["Adventure awaits!", "Enjoy the views!", "Safe travels!"]},
            'safety_tips': ["Arrive at airport early", "Keep documents handy", "Stay hydrated during flight", "Account for delays"],
            'order': 18,
        },
        {
            'name': 'Other Activity',
            'icon': '📍',
            'default_grace_minutes': 30,
            'colors': {"accent": "#4ECDC4", "primary": "#6C63FF", "secondary": "#A8A8A8"},
            'messages': {"start": "Have a great adventure!", "checkin": "Thanks for checking in!", "overdue": "Just checking in - everything OK?", "checkout": "Welcome back! Hope it was great!", "encouragement": ["You're doing great!", "Stay safe!", "Enjoy!"]},
            'safety_tips': ["Stay aware of your surroundings", "Keep your phone charged", "Share your location with someone", "Trust your instincts"],
            'order': 19,
        },
    ])

    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("phone", sa.Text, nullable=False),
        sa.Column("email", sa.Text, nullable=True),
    )

    op.create_table(
        "trips",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("eta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activity", sa.Integer, sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("grace_min", sa.Integer, nullable=False),
        sa.Column("location_text", sa.Text, nullable=False),
        sa.Column("gen_lat", sa.Float, nullable=False),
        sa.Column("gen_lon", sa.Float, nullable=False),
        sa.Column("contact1", sa.Integer, sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("contact2", sa.Integer, sa.ForeignKey("contacts.id"), nullable=True),
        sa.Column("contact3", sa.Integer, sa.ForeignKey("contacts.id"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="scheduled"),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP, nullable=True),
        sa.Column("last_checkin", sa.Integer, nullable=True),  # FK added later due to circular dependency
        sa.Column("checkin_token", sa.Text, nullable=True),
        sa.Column("checkout_token", sa.Text, nullable=True),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trip_id", sa.Integer, sa.ForeignKey("trips.id"), nullable=False),
        sa.Column("what", sa.Text, nullable=False),
        sa.Column("timestamp", sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("lat", sa.Float, nullable=True),
        sa.Column("lon", sa.Float, nullable=True),
        sa.Column("extended_by", sa.Integer, nullable=True),
    )

    # Add the foreign key constraint after both tables exist
    op.create_foreign_key(
        "fk_trips_last_checkin_events",
        "trips", "events",
        ["last_checkin"], ["id"]
    )

    op.create_table(
        "login_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.Text, nullable=False),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP, nullable=False),
        sa.Column("used_at", sa.TIMESTAMP, nullable=True),
    )

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("platform", sa.Text, nullable=False),
        sa.Column("token", sa.Text, nullable=False, unique=True),
        sa.Column("bundle_id", sa.Text, nullable=False),
        sa.Column("env", sa.Text, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("devices")
    op.drop_table("login_tokens")
    op.drop_constraint("fk_trips_last_checkin_events", "trips", type_="foreignkey")
    op.drop_table("events")
    op.drop_table("trips")
    op.drop_table("contacts")
    # users table dropped by initial migration downgrade
    op.drop_table("activities")
