# Behavioural Biometrics

Phase 2 backend module for Novaris AI.

This module evaluates whether an application session looks like the user's usual interaction pattern.
It does not identify a person with certainty and it does not inspect the device. It only looks for
anomalies in behaviour.

## What it does

- enrolls a normal behavioural session into a user profile
- analyzes a new behavioural session against the historical profile
- returns a risk score, a risk level, a decision, reasons, and evidence
- exposes the known profile for a user

## Difference with Device Intelligence

- Device Intelligence answers: is the device trustworthy?
- Behavioural Biometrics answers: does the interaction pattern look normal for this user?

## Phase 1 data

Collected signals are mock payload fields only:

- key interval
- touch duration
- typing speed
- tap pressure
- error count
- correction count
- hesitation time
- swipe speed
- touch precision
- orientation changes
- session duration

## Forbidden data

- real PIN
- password
- exact typed content
- conversations
- facial biometric data
- real fingerprint data
- personal contacts

## Persistent profile storage

The behavioural profile is stored durably in SQLite through SQLAlchemy.

Stored data:

- user profile metadata
- sample count
- behavioural baseline aggregates
- per-session behavioural samples

Not stored:

- real PIN
- password
- exact typed content
- conversations
- facial biometric data
- personal contacts

SQLite is acceptable for development and local testing. PostgreSQL with Alembic migrations is the expected production path later.

## Operating mode

- durable SQLite repository
- rule-based statistical scoring
- no real ML model yet
- no mobile SDK yet

## Security API and anti-replay

Requests are protected with `X-Novaris-Client-Key`, backed by the environment variable
`NOVARIS_BEHAVIOURAL_CLIENT_KEY`.

For `enroll` and `analyze`, the payload also carries:

- `request_id`
- `timestamp`
- `nonce`

Rules:

- `timestamp` must stay within a 5-minute window
- `nonce` is stored and cannot be reused
- missing `nonce` is rejected by payload validation
- reused `nonce` returns `409 Conflict`

This is a lightweight protection layer only. It is useful for local and staged deployments, but it is not a substitute for a real SDK signature. Phase 5 will add HMAC signing.

## SDK signature légère

`POST /enroll` and `POST /analyze` now require `X-Novaris-Signature` in addition to the client key.

The signature is computed with HMAC-SHA256 over the canonical JSON payload using
`NOVARIS_BEHAVIOURAL_SIGNATURE_SECRET`.

Difference between the two headers:

- `X-Novaris-Client-Key` checks that the caller knows the lightweight client key
- `X-Novaris-Signature` checks that the payload was signed with the SDK secret

Limitations:

- the signature is still embedded in a mobile app
- a mobile secret can be extracted by a determined attacker
- this is stronger than a plain key, but weaker than attestation

Phase 5 will later evolve toward Play Integrity on Android and App Attest on iOS.

## Difference between score and confidence_score

- `score` measures behavioural risk
- `confidence_score` measures trust in the SDK request itself

Both are returned independently and must not be mixed.

## SDK Collector mock

The repository already includes a mock collector example so mobile teams can see how the metrics are produced before a real SDK exists.

Why it exists:

- to document the measurement flow now
- to keep the backend contract testable
- to separate collection logic from risk scoring

Mock collector flow:

- `startSession()` / `endSession()` measure total session duration
- `startAction()` / `endAction()` measure the duration of a logical user action
- `recordTouchDown()` / `recordTouchUp()` measure touch duration and capture pressure
- `recordKeyPress()` stores timestamps used to compute key intervals
- `recordError()` and `recordCorrection()` increment counters used by the risk model

The mock collector only produces statistics. It never records:

- the real PIN
- the password
- the exact typed content
- conversations
- facial biometric data
- real fingerprint data
- personal contacts

The payload is signed with the lightweight HMAC layer described above, using the canonical JSON payload and `NOVARIS_BEHAVIOURAL_SIGNATURE_SECRET`.

## SDK v1 contract

The SDK payload is versioned to keep Android and iOS integrations stable.

Required fields:

- `user_id`
- `session_id`
- `action_type`
- `request_id`
- `timestamp`
- `nonce`
- `sdk_version`
- `payload_version`
- `platform`

Supported platforms:

- `ANDROID`
- `IOS`
- `WEB_MOCK`

Supported payload version:

- `v1`

Supported action types:

- `LOGIN`
- `PIN_ENTRY`
- `TRANSACTION_CONFIRMATION`
- `PASSWORD_CHANGE`
- `BENEFICIARY_ADD`

Behavioural metrics carried by the contract v1:

- `avg_key_interval_ms`
- `avg_touch_duration_ms`
- `typing_speed_cps`
- `tap_pressure_avg`
- `tap_pressure_std`
- `error_count`
- `correction_count`
- `hesitation_time_ms`
- `swipe_speed_avg`
- `touch_precision_score`
- `device_orientation_changes`
- `session_duration_ms`

Optional fields:

- the behavioural metric fields above when the SDK cannot measure them

Forbidden data:

- real PIN
- password
- exact typed content
- conversations
- facial biometric data
- real fingerprint data
- personal contacts

Phase 5 will add SDK payload signing with HMAC.

## Decisions

- `ALLOW`
- `REQUIRE_OTP`
- `REQUIRE_STEP_UP`
- `DENY_OR_HOLD_ACTION`

## API

- `POST /api/v1/behavioural-biometrics/enroll`
- `POST /api/v1/behavioural-biometrics/analyze`
- `GET /api/v1/behavioural-biometrics/users/{user_id}/profile`

## Future phases

- SDK mobile integration
- stronger validation
- ML predictor
- PostgreSQL + Alembic
