# Device Intelligence

Rule-based device trust scoring module for Novaris AI.

- Enrolls trusted devices per user.
- Analyzes a device and returns one of: `ALLOW_PIN`, `REQUIRE_OTP`, `REQUIRE_STEP_UP`, `DENY_PIN`.
- Uses SQLite persistence through SQLAlchemy for development.
- Keeps the API stable while the security layer evolves.

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

The `analyze` payload now includes:

- `request_id`
- `timestamp`
- `nonce`

The request must also include `X-Novaris-Client-Key`.

Validation rules:

- timestamps older than 5 minutes are rejected;
- nonce reuse is rejected;
- missing or invalid client key is rejected.

This client key is a temporary lightweight guard. It will later be replaced by a real SDK signature and attestation flow.

