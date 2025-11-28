# Push Notifications Setup

This document describes how to configure push notifications for Homebound.

## Environment Variables

### Backend (Required for Production)

Add these to your Render environment or `.env` file:

```bash
# APNs Configuration
APNS_KEY_ID=<your-key-id>           # Key ID from Apple Developer Portal
APNS_TEAM_ID=<your-team-id>         # Apple Developer Team ID
APNS_BUNDLE_ID=com.homeboundapp.Homebound
APNS_PRIVATE_KEY=<contents-of-.p8>  # The full .p8 key contents (with newlines)
APNS_USE_SANDBOX=false              # Set to true for development/TestFlight

# Backend settings
PUSH_BACKEND=apns                   # Use "dummy" for local testing
```

### Local Development

For local development, you can use a file path instead of the key contents:

```bash
APNS_AUTH_KEY_PATH=/path/to/AuthKey_XXXXXXXX.p8
APNS_USE_SANDBOX=true
PUSH_BACKEND=dummy  # or "apns" to test real notifications
```

## Getting APNs Keys

1. Go to [Apple Developer Portal](https://developer.apple.com/account/resources/authkeys/list)
2. Create a new key with "Apple Push Notifications service (APNs)" enabled
3. Download the `.p8` file (you can only download once!)
4. Note the Key ID shown on the download page
5. Your Team ID is in the top right of the developer portal

## Notification Types

The scheduler checks for and sends these notifications:

| Notification | When | Purpose |
|--------------|------|---------|
| Trip Starting Soon | 15 min before scheduled start | Remind user about upcoming trip |
| Trip Started | When planned trip becomes active | Confirm trip has begun |
| Approaching ETA | 15 min before ETA | Remind to prepare for check-out |
| ETA Reached | When ETA passes | Prompt to check out or extend |
| Check-in Reminder | Every 30 min during active trip | Periodic safety check-in |
| Grace Warning | Every 5 min during grace period | Urgent: contacts will be notified |

## Database Tracking

The `trips` table includes these columns for notification tracking:

- `notified_starting_soon` - Boolean, set when starting soon notification sent
- `notified_trip_started` - Boolean, set when trip started notification sent
- `notified_approaching_eta` - Boolean, set when approaching ETA notification sent
- `notified_eta_reached` - Boolean, set when ETA reached notification sent
- `last_checkin_reminder` - DateTime, tracks last check-in reminder
- `last_grace_warning` - DateTime, tracks last grace period warning

## iOS Settings

Users can control notification preferences in Settings > Notifications:

- **Trip Reminders** - Starting soon, approaching ETA notifications
- **Check-in Alerts** - Periodic check-in reminders
- **Emergency Notifications** - Overdue/grace period warnings

Note: User preferences are stored locally on the device. The backend sends all notifications; filtering based on preferences would require syncing these settings to the server (future enhancement).

## Testing

1. Set `PUSH_BACKEND=dummy` to log notifications without sending
2. Check backend logs for `[DUMMY PUSH]` or `[APNS]` messages
3. Use TestFlight with `APNS_USE_SANDBOX=true` for real device testing
