# Device Intelligence

## 1. Role of the module

Device Intelligence evaluates whether a device is trustworthy before a sensitive action such as login, PIN entry, transaction, or password change.

## 2. Production flow

In production, the backend receives device metadata collected by a mobile SDK, compares it with the user history, computes a risk score, and returns a decision.

## 3. Real SDK vs mock payload

The real Android/iOS SDK collects signals locally on the device. In this sprint, the backend receives mock payloads sent directly by API so the contract can be validated before native integration.

## 4. Collected data

- `user_id`
- `device_id`
- brand, model
- OS name and version
- root / emulator / VPN / proxy flags
- IP address, country, city
- latitude, longitude
- language
- app version

## 5. Scoring rules

- Rooted: +40
- Emulator: +45
- VPN: +20
- Proxy: +20
- New device: +30
- Brand change: +25
- Model change: +20
- Country change: +25
- City change: +10
- Very different OS: +10

Critical cases:

- `is_rooted = true` or `is_emulator = true` forces a critical risk level.
- `is_rooted = true` and `is_emulator = true` triggers an immediate block.
- `is_vpn = true` with a country change raises the risk to at least `HIGH`.

The final score is always bounded to `0..100`.

## 6. Possible decisions

- `ALLOW_PIN`
- `REQUIRE_OTP`
- `REQUIRE_STEP_UP`
- `DENY_PIN`

## 7. API endpoints

- `POST /api/v1/device-intelligence/enroll`
- `POST /api/v1/device-intelligence/analyze`
- `GET /api/v1/device-intelligence/users/{user_id}/devices`

## 8. Example payload

```json
{
  "user_id": "user-001",
  "device_id": "device-001",
  "brand": "Samsung",
  "model": "Galaxy S23",
  "os_name": "Android",
  "os_version": "14",
  "app_version": "1.0.0",
  "is_rooted": false,
  "is_emulator": false,
  "is_vpn": false,
  "is_proxy": false,
  "ip_address": "196.0.0.1",
  "country": "CI",
  "city": "Abidjan",
  "latitude": 5.36,
  "longitude": -4.01,
  "language": "fr",
  "request_id": "req-001",
  "timestamp": "2026-07-05T10:00:00Z",
  "nonce": "nonce-001"
}
```

## 9. Example response

```json
{
  "module_name": "device_intelligence",
  "user_id": "user-001",
  "device_id": "device-001",
  "score": 0,
  "risk_level": "LOW",
  "decision": "ALLOW_PIN",
  "reasons": [],
  "evidence": {},
  "adapter_mode": "RULE_BASED"
}
```

## 10. Current limits

- No real mobile SDK integration.
- No trained ML model.
- No advanced network correlation.
- Development persistence uses SQLite.

## Durable device history persistence

The device history must survive backend restarts so the risk engine can compare the current event with past trusted devices.

Stored data:

- user and device identifiers;
- device hash;
- brand, model, OS, OS version;
- IP, country, city;
- trust status;
- first seen, last used, created, and updated timestamps.

Not stored:

- IMEI;
- hardware serial number;
- biometric data;
- unrelated personal data.

Current limitation:

- SQLite is acceptable for V1 development and local testing.
- `Base.metadata.create_all()` is used for bootstrap only.

Future evolution:

- PostgreSQL for production;
- Alembic for versioned migrations;
- clearer separation between V1 bootstrap and production schema management.

## 11. Android / iOS future work

- Native SDK collector integration.
- Device integrity and attestation signals.
- OS version bucketing.
- Behavioral enrichment.

## 12. Security and privacy

- Do not collect IMEI or hardware serial.
- Do not request `READ_PHONE_STATE`.
- Minimize raw device data sent to backend.
- Hash sensitive device attributes on the SDK side when possible.
- IP and country can also be resolved by the backend from the request.

## 13. Security layer V3

All device intelligence endpoints now expect `X-Novaris-Client-Key`:

- `POST /api/v1/device-intelligence/enroll`
- `POST /api/v1/device-intelligence/analyze`
- `GET /api/v1/device-intelligence/users/{user_id}/devices`

The `analyze` payload now also expects:

- `request_id`
- `timestamp`
- `nonce`

Validation rules:

- requests older than 5 minutes are rejected;
- nonce reuse is rejected;
- missing or invalid client key is rejected.

The client key is a lightweight guard for now. It is not a cryptographic signature. It will later be replaced by a real SDK signature and attestation flow using Play Integrity on Android and App Attest on iOS.
