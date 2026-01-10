# Privacy Policy

**Last Updated: January 10, 2026**

Hudson Schmidt ("we," "us," or "our") operates the Homebound mobile application (the "App"). This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use our App.

By using Homebound, you agree to the collection and use of information in accordance with this policy.

---

## 1. Information We Collect

### 1.1 Account Information
When you create an account, we collect:
- **Email address** (required for authentication)
- **First and last name** (for personalization and to share with emergency contacts)
- **Age** (for service customization)
- **Apple ID identifier** (if you sign in with Apple)
- **Notification preferences** (trip reminders, check-in alerts)
- **Friend visibility settings** (controls what friends can see about you, such as your location, trip notes, achievements, and profile stats)

### 1.2 Trip & Safety Plan Data
When you create a trip or safety plan, we collect:
- Trip title and activity type
- Start time and estimated time of arrival (ETA)
- Grace period preferences
- Location information (address or coordinates)
    - Starting location
    - Destination location (optional)
    - Can be as broad or specific as you wish
- Optional notes about your trip
- Timezone information
- Check-in interval preferences (how often you want reminders)
- Quiet hours settings (when to pause notifications)
- Live location sharing preference (see Section 1.4)
- Custom notification messages *(Homebound+ only)*

**Group Trips** *(Homebound+ only)*:
When you create or join a group trip, we also collect:
- Participant list and roles (owner, participant)
- Invitation and join timestamps
- Group checkout settings (voting preferences)
- Each participant's check-in status and location

### 1.3 Emergency Contact Information
You may add emergency contacts to your account:
- Contact names
- Contact email addresses
- Contact phone numbers (optional)
- Contact groups for organization *(Homebound+ only)*

You can also add friends (other Homebound users) as safety contacts for your trips.

**Note:** We only store the information you provide. We do not access your device's contact list.

### 1.4 Location Data

#### Trip Locations
We collect location data when:
- You explicitly set a trip location (start and/or destination) using the map
- You choose to use your current location for a trip
- You check in during a trip (we record your location at that moment)

#### Live Location Sharing (Optional)
If you enable **Live Location Sharing** for a trip, we collect real-time location data including:
- Latitude and longitude coordinates
- Altitude
- Horizontal accuracy (GPS precision)
- Speed
- Timestamps

**Important:** Live Location Sharing is:
- **Completely optional** - you must explicitly enable it for each trip
- **User-controlled** - you can disable it at any time in your profile settings or per-trip
- **Limited sharing** - your live location is only shared with the safety contacts you choose for that specific trip
- **Not shared with third parties** - we do not sell or share your location data with advertisers or data brokers

You can control live location sharing:
- **Per-trip**: Toggle "Share Live Location" when creating a trip
- **Globally**: Disable in Settings > Privacy > "Allow Live Location Sharing with Friends"

#### What We Do NOT Do
- Sell your location data
- Share your location with advertisers
- Track your location when you're not on an active trip with live location enabled
- Access your location without your explicit permission

### 1.5 Device Information
To send push notifications, we collect:
- Device push notification token
- Device platform (iOS)
- App bundle identifier
- App environment (development/production)
- Live Activity tokens (for iOS lock screen widgets showing trip status)
- Last activity timestamp (when your device last connected)

### 1.6 Automatically Collected Information
When you use the App, we automatically collect:
- Timestamps of account creation and last login
- Trip creation and completion timestamps
- Check-in and check-out events
- ETA extension events
- Notification delivery logs (for troubleshooting)

### 1.7 Subscription Information
If you subscribe to Homebound+, we collect:
- App Store transaction identifiers
- Product/plan purchased
- Purchase and expiration dates
- Subscription status (active, expired, grace period)
- Auto-renewal status
- Family sharing status (if applicable)
- Free trial status (if applicable)

This information is processed through Apple's App Store and is used to provide and manage your subscription.

### 1.8 Social & Friend Data
If you use social features, we collect:
- Friend connections (who you're friends with)
- Friend requests (sent and received)
- Friend invite links you create
- Your visibility preferences (what friends can see)
- Achievements and statistics visible to friends

### 1.9 Homebound+ Features
Homebound+ subscribers have access to additional features that may collect:
- **Custom Messages**: Personalized notification text you create
- **Contact Groups**: Organization names for your contacts
- **Group Trips**: Participant data, voting records, and shared locations
- **Data Export**: We generate exports of your data upon request
- **Pinned Activities**: Your favorite activities for quick access
- **Enhanced Privacy Controls**: Additional friend visibility settings

---

## 2. How We Use Your Information

We use the information we collect to:

- **Provide the Service**: Create and manage your safety plans, send notifications to you and your emergency contacts
- **Send Notifications**: Alert you about trip status, remind you to check in, and notify your emergency contacts if needed
- **Authenticate Your Account**: Verify your identity via magic link codes or Apple Sign In
- **Improve the App**: Understand how the service is used and make improvements
- **Communicate with You**: Send service-related emails (magic link codes, trip notifications)

---

## 3. Information Sharing & Third Parties

### 3.1 Emergency Contacts
When you add emergency contacts to a trip, they will receive emails about:
- Trip creation and details
- Trip start notifications
- Check-in updates
- Trip completion
- Overdue alerts (if you don't check out by your ETA + grace period)

When you check-in, they will also receive your current coordinates/location.
If you go over-due, they will receive last known coordinates/location.

### 3.2 Third-Party Service Providers
We use the following third-party services:

| Service | Purpose | Data Shared |
|---------|---------|-------------|
| **Resend** | Email delivery | Email addresses, names, trip details |
| **Apple Push Notification Service** | Push notifications | Device tokens, notification content |
| **OpenStreetMap/Nominatim** | Convert coordinates to place names | Location coordinates only |
| **Apple Sign In** | Authentication (optional) | Apple user ID |
| **App Store Server API** | Subscription verification | Transaction IDs, product IDs |

### 3.3 We Do NOT
- Sell your personal information
- Share your data with advertisers
- Use third-party analytics or tracking services
- Share your information with data brokers

### 3.4 Legal Requirements
We may disclose your information if required by law, such as in response to a subpoena or court order, or if we believe disclosure is necessary to protect our rights, your safety, or the safety of others.

---

## 4. Data Security

We implement appropriate security measures to protect your information:

- **Encryption in Transit**: All data transmitted between the App and our servers uses HTTPS/TLS encryption
- **Secure Authentication**: JWT tokens with cryptographic signatures
- **Secure Storage**: Sensitive data (tokens, credentials) stored in iOS Keychain with `kSecAttrAccessibleAfterFirstUnlock` protection
- **Access Controls**: Authentication required for all personal data access
- **No Plain-Text Passwords**: We use magic link authentication meaning no passwords are stored

While we strive to protect your personal information, no method of electronic transmission or storage is 100% secure. We cannot guarantee absolute security.

---

## 5. Data Retention & Deletion

### 5.1 Retention
- **Account Data**: Retained until you delete your account
- **Trip Data**: Retained until you delete the trip or your account
- **Event History**: Retained for your trip timeline and safety records

### 5.2 Account Deletion
You can delete your account at any time through the App:
1. Go to Settings > Account
2. Tap "Delete Account"
3. Confirm deletion

When you delete your account, we permanently delete:
- Your profile information
- All your trips and trip history
- All your emergency contacts and contact groups
- All your devices and push tokens
- All login tokens
- All friendships and friend data
- All live location history
- All notification logs
- All subscription records (note: you must cancel your subscription separately through the App Store)
- All group trip participation data
- All achievements and statistics

This deletion is immediate and irreversible.

### 5.3 Local Data
The App caches some data locally on your device for offline access. You can clear this data:
1. Go to Settings > Resources
2. Tap "Clear Cache"

---

## 6. Your Privacy Rights

### 6.1 California Residents (CCPA)
If you are a California resident, you have the right to:

- **Know**: Request what personal information we collect, use, and disclose
- **Delete**: Request deletion of your personal information
- **Non-Discrimination**: Exercise your rights without discriminatory treatment

We do not sell personal information, so the right to opt-out of sale does not apply.

To exercise your rights, contact us at privacy@homeboundapp.com.

### 6.2 All Users
Regardless of location, you can:
- Access your data through the App
- Update your profile information
- Delete your account and all associated data
- Opt out of non-essential emails

---

## 7. Children's Privacy

Homebound is not intended for children under 13 years of age. We do not knowingly collect personal information from children under 13. If you are a parent or guardian and believe your child has provided us with personal information, please contact us at privacy@homeboundapp.com, and we will delete such information.

---

## 8. International Data Transfers

Our servers are located in the United States. If you access the App from outside the United States, your information will be transferred to and processed in the United States, where data protection laws may differ from those in your country.

---

## 9. Changes to This Privacy Policy

We may update this Privacy Policy from time to time. We will notify you of any changes by:
- Updating the "Last Updated" date at the top of this policy
- Sending you a notification through the App for material changes

Your continued use of the App after changes are posted constitutes your acceptance of the updated policy.

---

## 10. Contact Us

If you have questions about this Privacy Policy or our privacy practices, please contact us:

**Email**: privacy@homeboundapp.com

**For California Privacy Rights requests**: privacy@homeboundapp.com

---

*This Privacy Policy is effective as of January 10, 2026.*
