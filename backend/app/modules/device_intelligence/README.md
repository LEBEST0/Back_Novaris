# Device Intelligence

Rule-based device trust scoring module for Novaris AI.

- Enrolls trusted devices per user.
- Analyzes a device and returns one of: `ALLOW_PIN`, `REQUIRE_OTP`, `REQUIRE_STEP_UP`, `DENY_PIN`.
- Uses SQLite persistence through SQLAlchemy for development.
- Keeps the API stable while the security layer evolves.

## SDK contract v1

The current payload contract is version `v1`.

Supported `platform` values:

- `ANDROID`
- `IOS`
- `WEB_MOCK`

Mandatory `analyze` fields:

- `user_id`
- `device_id`
- `brand`
- `model`
- `os_name`
- `os_version`
- `is_rooted`
- `is_emulator`
- `is_vpn`
- `is_proxy`
- `request_id`
- `timestamp`
- `nonce`
- `payload_version`
- `platform`

Optional fields:

- `app_version`
- `sdk_version`
- `ip_address`
- `country`
- `city`
- `latitude`
- `longitude`
- `language`

Forbidden fields:

- IMEI
- hardware serial number
- phone number
- SIM identifiers
- biometric data
- any unnecessary personal data

## Durable device history persistence

Device history is stored in SQLite so it survives backend restarts during development and local testing.

- `create_all()` is used only as a V1 bootstrap mechanism.
- This is acceptable until Alembic migrations are added.
- Production should move to PostgreSQL with Alembic-managed migrations.

Stored fields:

- user and device identifiers
- device hash
- brand, model, OS name, OS version
- IP, country, city
- trust status
- first seen, last used, created, and updated timestamps

Not stored:

- IMEI
- hardware serial number
- biometric data
- unrelated personal data

## Security layer V3

All device intelligence endpoints now require `X-Novaris-Client-Key`:

- `POST /enroll`
- `POST /analyze`
- `GET /users/{user_id}/devices`

The `analyze` payload also includes:

- `request_id`
- `timestamp`
- `nonce`
- `sdk_version`
- `payload_version`
- `platform`

Validation rules:

- timestamps older than 5 minutes are rejected;
- nonce reuse is rejected;
- missing or invalid client key is rejected;
- unsupported payload versions are rejected with a validation error.

This client key is a temporary lightweight guard. It is not a cryptographic signature and it can be replaced later by a real SDK signature plus Play Integrity / App Attest.

Configuration now lives under `backend/app/shared/config/` with `settings.py` and `constants.py`.
