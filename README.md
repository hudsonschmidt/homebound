# Homebound

A safety app for outdoor adventurers. Create trip plans, set check-in times, and automatically notify your emergency contacts if you don't return on schedule.

## What is Homebound?

Homebound helps solo hikers, climbers, divers, and other outdoor enthusiasts stay safe by creating a simple safety net. Before heading out:

1. **Create a trip** with your activity, location, start time, and expected return time
2. **Add emergency contacts** who will be notified if something goes wrong
3. **Check in** periodically to let contacts know you're safe
4. **Tap "I'm Safe"** when you return home

If you don't check out by your ETA (plus a grace period), Homebound automatically notifies your emergency contacts with your trip details and last known location.

## Features

### Core Safety
- **Activity-specific trips**: Choose from hiking, climbing, diving, cycling, running, skiing, and more
- **Smart notifications**: Emergency contacts receive detailed trip info including location, notes, and activity type
- **Flexible check-ins**: Check in via the app to reset your timer and share your location
- **Grace periods**: Configurable buffer time before overdue alerts trigger
- **Extend time**: Running late? Extend your trip with one tap

### Friends & Social
- **Add friends**: Connect via invite links or QR code scanning
- **Live trip tracking**: See friends' active trips with real-time countdown timers
- **Request updates**: Send a notification asking friends to check in
- **View on map**: See friends' trip locations and check-in points
- **Friend groups**: Organize friends into custom groups (Plus feature)

### Group Trips
- **Multi-participant trips**: Create trips with multiple people
- **Vote to end**: Configurable checkout modes - anyone can end, owner only, or vote-based
- **Trip invitations**: Invite friends to join your adventures

### Trip History & Achievements
- **Trip history**: Browse and search all past adventures
- **Statistics**: View your adventure stats and trends
- **40+ achievements**: Earn badges for milestones like "First Trip", "Night Owl", "Weekend Warrior"
- **Celebration animations**: Get rewarded when you unlock new achievements

### Premium (Homebound+)
- **Trip Map**: See all your adventures plotted on an interactive map
- **Extended time options**: More flexibility with 2hr, 3hr, 4hr extensions
- **Contact groups**: Organize friends into groups for quick trip setup
- **Monthly or yearly subscription**

## App Structure

The app has four main tabs:

1. **Home**: Create new trips, manage your active trip with live countdown, view upcoming scheduled trips
2. **History**: Browse past trips, view statistics, search through your adventure history
3. **Friends**: Manage friends, see their active trips, accept trip invitations
4. **Map**: View all trips on an interactive map (Plus feature)

## Tech Stack

### iOS App (SwiftUI)
- Native iOS app built with SwiftUI
- Secure token storage via iOS Keychain
- Apple Sign In + Magic Link authentication
- Push notifications via APNs
- Location search with MapKit integration
- StoreKit 2 for in-app subscriptions
- Offline support with automatic sync

### Backend (Python/FastAPI)
- FastAPI REST API
- PostgreSQL database (SQLite for local dev)
- SQLAlchemy ORM with Alembic migrations
- JWT authentication (python-jose)
- Background job scheduling with APScheduler
- Email notifications via Resend
- Push notifications via APNs

## Project Structure

```
homebound/
├── ios/                    # iOS SwiftUI app
│   └── Homebound/
│       └── Homebound/
│           ├── Core/       # App entry point
│           ├── Models/     # Data models
│           ├── Services/   # API, auth, storage
│           ├── Views/      # SwiftUI views
│           │   ├── Auth/         # Login, onboarding
│           │   ├── Home/         # Main tab view
│           │   ├── Trip/         # Trip creation, detail, history
│           │   ├── Friends/      # Friends list, profiles, invites
│           │   ├── Map/          # Trip map views
│           │   ├── Profile/      # Achievements, contacts
│           │   ├── Settings/     # App settings
│           │   ├── Subscription/ # Paywall, premium
│           │   └── Components/   # Reusable UI components
│           └── Resources/  # Theme, assets
├── backend/                # FastAPI backend
│   ├── src/
│   │   ├── api/           # REST endpoints
│   │   ├── services/      # Business logic
│   │   └── messaging/     # Email, push notifications
│   ├── alembic/           # Database migrations
│   └── tests/             # Test suite
├── frontend/              # Web frontend (Next.js)
└── docs/                  # Documentation
```

## Getting Started

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# Run database migrations
alembic upgrade head

# Start the server
python -m uvicorn src.api.server:app --reload --port 3000
```

### iOS Setup

1. Open `ios/Homebound/Homebound.xcodeproj` in Xcode
2. Update the `BASE_URL` in Info.plist to point to your backend
3. Configure your Apple Developer account for push notifications
4. Build and run on a device or simulator

## API Overview

### Authentication
- `POST /api/v1/auth/request-magic-link` - Request login code
- `POST /api/v1/auth/verify` - Exchange code for tokens
- `POST /api/v1/auth/refresh` - Refresh access token
- `POST /api/v1/auth/apple` - Apple Sign In

### Trips
- `GET /api/v1/trips` - List user's trips
- `POST /api/v1/trips` - Create new trip
- `GET /api/v1/trips/{id}` - Get trip details
- `PUT /api/v1/trips/{id}` - Update trip
- `POST /api/v1/trips/{id}/checkin` - Check in to trip
- `POST /api/v1/trips/{id}/checkout` - Complete trip
- `POST /api/v1/trips/{id}/extend` - Extend trip ETA

### Friends
- `GET /api/v1/friends` - List friends
- `POST /api/v1/friends/invite` - Create invite link
- `POST /api/v1/friends/accept` - Accept friend invite
- `GET /api/v1/friends/active-trips` - Get friends' active trips

### Contacts
- `GET /api/v1/contacts` - List emergency contacts
- `POST /api/v1/contacts` - Add contact
- `DELETE /api/v1/contacts/{id}` - Remove contact

### Activities
- `GET /api/v1/activities` - List available activity types

## Environment Variables

| Variable | Description |
|----------|-------------|
| `POSTGRES_URI` | Database connection string |
| `JWT_SECRET` | Secret key for JWT tokens |
| `RESEND_API_KEY` | Resend API key for emails |
| `APNS_KEY_ID` | Apple Push Notification key ID |
| `APNS_TEAM_ID` | Apple Developer Team ID |
| `APNS_BUNDLE_ID` | iOS app bundle identifier |
| `BASE_URL` | Public URL for the backend |

## Development

### Running Tests

```bash
cd backend
pytest tests/ -v
```

### Database Migrations

```bash
cd backend

# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

### Linting

```bash
cd backend
ruff check src/
```

## License

MIT
