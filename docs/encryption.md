The app only uses:
  - HTTPS/TLS - handled by Apple's URLSession (iOS system encryption)
  - iOS Keychain - uses Apple's built-in encryption for token storage
  - JWT tokens - standard encoding, not custom encryption