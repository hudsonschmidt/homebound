# Homebound

A safety app for outdoor adventurers. Create trip plans, set check-in times, and automatically notify your emergency contacts if you don't return on schedule.

## What is Homebound?

Homebound helps solo hikers, climbers, divers, and other outdoor enthusiasts stay safe by creating a simple safety net. Before heading out:

1. **Create a trip** with your activity, location, start time, and expected return time
2. **Add emergency contacts** who will be notified if something goes wrong
3. **Check in** when you start your adventure
4. **Check out** when you return safely

If you don't check out by your ETA (plus a grace period), Homebound automatically notifies your emergency contacts with your trip details and last known location.

## Who is it for?

- **Hikers** venturing into backcountry trails
- **Climbers** heading out for a day on the rocks
- **Scuba divers** who need surface interval accountability
- **Cyclists** on long solo rides
- **Anyone** doing solo outdoor activities where safety matters

## Features

- **Activity-specific trips**: Choose from hiking, climbing, diving, cycling, running, skiing, and more - each with tailored safety tips and messaging
- **Smart notifications**: Emergency contacts receive detailed trip info including location, notes, and activity type
- **Flexible check-in**: Check in via the app or through tokenized web links (no login required for contacts)
- **Grace periods**: Configurable buffer time before overdue alerts trigger
- **Trip history**: View past adventures and statistics
- **Location support**: Add locations via search with map preview

## Tech Stack

### iOS App (SwiftUI)
- Native iOS app built with SwiftUI
- Secure token storage via iOS Keychain
- Apple Sign In + Magic Link authentication
- Push notifications via APNs
- Location search with MapKit integration

### Backend (Python/FastAPI)
- FastAPI REST API
- PostgreSQL database (Supabase in production, SQLite for local dev)
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
│           └── Resources/  # Theme, assets
├── backend/                # FastAPI backend
│   ├── src/
│   │   ├── api/           # REST endpoints
│   │   ├── services/      # Business logic
│   │   └── messaging/     # Email, push notifications
│   ├── alembic/           # Database migrations
│   └── tests/             # Test suite
├── frontend/               # Web frontend (Next.js)
└── docs/                   # Documentation
```

## Getting Started

### Backend Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Set up environment variables
cp backend/.env.example backend/.env
# Edit .env with your configuration

# Run database migrations
cd backend
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

### Profile
- `GET /api/v1/profile` - Get user profile
- `PUT /api/v1/profile` - Update profile

### Trips
- `GET /api/v1/trips` - List user's trips
- `POST /api/v1/trips` - Create new trip
- `GET /api/v1/trips/{id}` - Get trip details
- `POST /api/v1/trips/{id}/checkin` - Check in to trip
- `POST /api/v1/trips/{id}/checkout` - Check out from trip

### Contacts
- `GET /api/v1/contacts` - List emergency contacts
- `POST /api/v1/contacts` - Add contact
- `DELETE /api/v1/contacts/{id}` - Remove contact

### Activities
- `GET /api/v1/activities` - List available activity types

### Tokenized Actions (no auth required)
- `GET /t/{token}/checkin` - Check in via link
- `GET /t/{token}/checkout` - Check out via link

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
