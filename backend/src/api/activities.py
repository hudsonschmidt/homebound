"""
Activity type configurations and metadata
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["activities"])


# Activity configurations with themes, messages, and defaults
ACTIVITIES = {
    "hiking": {
        "name": "Hiking",
        "icon": "🥾",
        "default_grace_minutes": 45,
        "colors": {
            "primary": "#2D5016",  # Forest green
            "secondary": "#8B4513",  # Earth brown
            "accent": "#87CEEB"  # Sky blue
        },
        "messages": {
            "start": "Happy trails! Adventure awaits!",
            "checkin": "Great progress on the trail!",
            "checkout": "Trail conquered! Well done!",
            "encouragement": ["One step at a time!", "Nature is calling!", "Enjoy the journey!"],
            "overdue": "Haven't heard from you - everything OK on the trail?"
        },
        "safety_tips": [
            "Pack plenty of water and snacks",
            "Check weather conditions",
            "Tell someone your route",
            "Bring a first aid kit"
        ]
    },
    "biking": {
        "name": "Biking",
        "icon": "🚴",
        "default_grace_minutes": 30,
        "colors": {
            "primary": "#FF6B35",  # Vibrant orange
            "secondary": "#4A90E2",  # Sky blue
            "accent": "#2ECC71"  # Fresh green
        },
        "messages": {
            "start": "Pedal power activated! Ride safe!",
            "checkin": "Crushing those miles!",
            "checkout": "Ride complete! Great job!",
            "encouragement": ["Wind in your hair!", "Keep those wheels turning!", "Enjoy the ride!"],
            "overdue": "Checking in - how's the ride going?"
        },
        "safety_tips": [
            "Always wear your helmet",
            "Check your brakes and tires",
            "Use lights in low visibility",
            "Stay hydrated"
        ]
    },
    "running": {
        "name": "Running",
        "icon": "🏃",
        "default_grace_minutes": 20,
        "colors": {
            "primary": "#E74C3C",  # Energy red
            "secondary": "#34495E",  # Cool gray
            "accent": "#F39C12"  # Energetic yellow
        },
        "messages": {
            "start": "Let's go! Feel the rhythm!",
            "checkin": "Runner's high incoming!",
            "checkout": "Run complete! You crushed it!",
            "encouragement": ["You've got this!", "Keep that pace!", "Feel the burn!"],
            "overdue": "Hope the run is going well - check in when you can!"
        },
        "safety_tips": [
            "Warm up before you start",
            "Stay visible with bright colors",
            "Run against traffic",
            "Stay hydrated"
        ]
    },
    "climbing": {
        "name": "Climbing",
        "icon": "🧗",
        "default_grace_minutes": 60,
        "colors": {
            "primary": "#7F8C8D",  # Rock gray
            "secondary": "#E67E22",  # Sunset orange
            "accent": "#3498DB"  # Clear sky blue
        },
        "messages": {
            "start": "Time to send it! Climb safe!",
            "checkin": "Making great progress up there!",
            "checkout": "Summit reached! Amazing work!",
            "encouragement": ["Trust your grip!", "You're crushing it!", "The summit awaits!"],
            "overdue": "Haven't heard from you - everything good on the climb?"
        },
        "safety_tips": [
            "Double-check all gear",
            "Never climb alone",
            "Know your limits",
            "Check anchor points"
        ]
    },
    "driving": {
        "name": "Driving",
        "icon": "🚗",
        "default_grace_minutes": 30,
        "colors": {
            "primary": "#2C3E50",  # Road gray
            "secondary": "#16A085",  # Teal
            "accent": "#ECF0F1"  # Light gray
        },
        "messages": {
            "start": "Safe travels! Drive carefully!",
            "checkin": "Making good progress on the road!",
            "checkout": "Arrived safely! Journey complete!",
            "encouragement": ["Enjoy the drive!", "Safe and steady!", "Almost there!"],
            "overdue": "Just checking you arrived safely - let us know!"
        },
        "safety_tips": [
            "Take breaks on long drives",
            "Check your route before starting",
            "Keep your phone charged",
            "Watch for weather conditions"
        ]
    },
    "flying": {
        "name": "Flying",
        "icon": "✈️",
        "default_grace_minutes": 120,
        "colors": {
            "primary": "#3498DB",  # Sky blue
            "secondary": "#ECF0F1",  # Cloud white
            "accent": "#9B59B6"  # Sunset purple
        },
        "messages": {
            "start": "Bon voyage! Have a great flight!",
            "checkin": "Hope you're enjoying the journey!",
            "checkout": "Welcome to your destination!",
            "encouragement": ["Adventure awaits!", "Enjoy the views!", "Safe travels!"],
            "overdue": "Flight should have landed - everything OK?"
        },
        "safety_tips": [
            "Arrive at airport early",
            "Keep documents handy",
            "Stay hydrated during flight",
            "Account for delays"
        ]
    },
    "camping": {
        "name": "Camping",
        "icon": "🏕️",
        "default_grace_minutes": 90,
        "colors": {
            "primary": "#1A237E",  # Midnight blue
            "secondary": "#FF6F00",  # Campfire orange
            "accent": "#4CAF50"  # Nature green
        },
        "messages": {
            "start": "Into the wild! Enjoy nature!",
            "checkin": "Camp life is good!",
            "checkout": "Back to civilization!",
            "encouragement": ["Under the stars!", "Wilderness mode: ON!", "Enjoy the peace!"],
            "overdue": "Haven't heard from camp - everything good?"
        },
        "safety_tips": [
            "Share your campsite location",
            "Check fire regulations",
            "Store food properly",
            "Bring weather-appropriate gear"
        ]
    },
    "other": {
        "name": "Other Activity",
        "icon": "📍",
        "default_grace_minutes": 30,
        "colors": {
            "primary": "#6C63FF",  # Default purple
            "secondary": "#A8A8A8",  # Neutral gray
            "accent": "#4ECDC4"  # Teal accent
        },
        "messages": {
            "start": "Have a great adventure!",
            "checkin": "Thanks for checking in!",
            "checkout": "Welcome back! Hope it was great!",
            "encouragement": ["You're doing great!", "Stay safe!", "Enjoy!"],
            "overdue": "Just checking in - everything OK?"
        },
        "safety_tips": [
            "Stay aware of your surroundings",
            "Keep your phone charged",
            "Share your location with someone",
            "Trust your instincts"
        ]
    }
}


@router.get("/activities")
async def get_activities():
    """Get all available activity types with their configurations."""
    return {
        "activities": [
            {
                "id": key,
                "name": value["name"],
                "icon": value["icon"],
                "default_grace_minutes": value["default_grace_minutes"],
                "colors": value["colors"]
            }
            for key, value in ACTIVITIES.items()
        ]
    }


@router.get("/activities/{activity_type}")
async def get_activity_detail(activity_type: str):
    """Get detailed configuration for a specific activity type."""
    if activity_type not in ACTIVITIES:
        activity_type = "other"

    activity = ACTIVITIES[activity_type]
    return {
        "id": activity_type,
        **activity
    }