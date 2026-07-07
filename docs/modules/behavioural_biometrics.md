# Behavioural Biometrics

## 1. Role of the module

Behavioural Biometrics checks whether the way a user interacts with the application resembles their usual behavior.

It does not verify the device. It verifies the user interaction pattern.

The module never claims identity certainty. It only detects anomalies relative to a historical baseline.

## 2. Difference with Device Intelligence

- Device Intelligence: is the device trustworthy?
- Behavioural Biometrics: does the interaction pattern match the usual user behavior?

The two modules are complementary and can be combined before sensitive actions.

## 3. Behavioural data collected

- average key interval
- average touch duration
- typing speed
- tap pressure average and standard deviation
- error count
- correction count
- hesitation time
- swipe speed
- touch precision score
- orientation changes
- session duration

## 4. Forbidden data

- real PIN
- password
- exact typed content
- conversations
- facial biometric data
- real fingerprint sensor data
- personal contacts

## 5. Phase 1 mock payload

This phase uses mock payloads only. No real mobile SDK is required yet.

## 6. Scoring rules

- No historical profile: score 50, decision `REQUIRE_OTP`, reason `Profil comportemental insuffisant`
- Very few samples: +20
- Very different key interval: +25
- Very different touch duration: +15
- Very different typing speed: +20
- Error count above habit: +15
- Correction count above habit: +10
- Hesitation time too high: +15
- Low touch precision: +15
- Session duration anomalous: +10
- Mechanical rhythm: +20

The score is capped at `100`.

Risk levels:

- `0-29`: `LOW`
- `30-59`: `MEDIUM`
- `60-79`: `HIGH`
- `80-100`: `CRITICAL`

Decisions:

- `LOW` -> `ALLOW`
- `MEDIUM` -> `REQUIRE_OTP`
- `HIGH` -> `REQUIRE_STEP_UP`
- `CRITICAL` -> `DENY_OR_HOLD_ACTION`

## 7. Endpoints

- `POST /api/v1/behavioural-biometrics/enroll`
- `POST /api/v1/behavioural-biometrics/analyze`
- `GET /api/v1/behavioural-biometrics/users/{user_id}/profile`

## 8. Example payload

```json
{
  "user_id": "user-001",
  "session_id": "session-001",
  "action_type": "LOGIN",
  "avg_key_interval_ms": 180,
  "avg_touch_duration_ms": 120,
  "typing_speed_cps": 4.2,
  "tap_pressure_avg": 0.45,
  "tap_pressure_std": 0.08,
  "error_count": 1,
  "correction_count": 0,
  "hesitation_time_ms": 350,
  "swipe_speed_avg": 1.8,
  "touch_precision_score": 0.91,
  "device_orientation_changes": 2,
  "session_duration_ms": 42000,
  "platform": "ANDROID",
  "payload_version": "v1"
}
```

## 9. Example response

```json
{
  "module_name": "behavioural_biometrics",
  "user_id": "user-001",
  "session_id": "session-001",
  "score": 20,
  "risk_level": "MEDIUM",
  "decision": "REQUIRE_OTP",
  "reasons": ["Peu d'echantillons comportementaux"],
  "evidence": {},
  "profile_samples": 1,
  "adapter_mode": "RULE_BASED",
  "confidence_score": 100
}
```

## 10. Persistent storage

The behavioural profile is now persisted in SQLite through SQLAlchemy.

Stored:

- user profile metadata
- sample count
- behavioural baseline aggregates
- individual behavioural samples

Not stored:

- real PIN
- password
- exact typed content
- conversations
- facial biometric data
- personal contacts

SQLite is the development database for this phase. PostgreSQL plus Alembic migrations should be used for production.

## 11. Security API and anti-replay

Requests are protected with `X-Novaris-Client-Key`.

The behaviour-specific key comes from `NOVARIS_BEHAVIOURAL_CLIENT_KEY`.

For `POST /enroll` and `POST /analyze`, the payload also includes:

- `request_id`
- `timestamp`
- `nonce`

Rules:

- `timestamp` must stay within a 5-minute window
- `nonce` is persisted and cannot be reused
- missing `nonce` is rejected by payload validation
- replayed `nonce` returns `409 Conflict`

This is a lightweight protection layer. It reduces accidental replay and basic unauthorized calls, but it does not replace a real signed SDK payload.
Phase 5 will add HMAC signing.

## 12. SDK signature légère

`POST /enroll` and `POST /analyze` also require `X-Novaris-Signature`.

The signature is HMAC-SHA256 over the canonical payload:

`json.dumps(payload, sort_keys=True, separators=(",", ":"))`

The secret comes from `NOVARIS_BEHAVIOURAL_SIGNATURE_SECRET`.

Difference between the two headers:

- `X-Novaris-Client-Key` checks that the request comes from a known lightweight client
- `X-Novaris-Signature` checks that the payload was signed by the SDK layer

Limits of HMAC in a mobile app:

- the secret is still shipped in the client
- a rooted / instrumented device can extract it
- it is a useful step-up, but it is not a strong attestation

Future evolution:

- Play Integrity on Android
- App Attest on iOS
- server-side attestation checks

## 13. Difference between score and confidence_score

- `score` measures behavioural risk
- `confidence_score` measures trust in the request and SDK payload

The two are independent and should be interpreted separately.

## 14. SDK v1 contract

The payload is versioned so Android and iOS can stay compatible over time.

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

Behavioural metrics in contract v1:

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

- the behavioural metric fields when the SDK cannot compute them
- `language` when the client wants to send localization context later

Forbidden data:

- real PIN
- password
- exact typed content
- conversations
- facial biometric data
- real fingerprint data
- personal contacts

Phase 5 will introduce SDK payload signing with HMAC.

## 15. Current limits

- SQLite is still the development persistence layer.
- No real SDK.
- No real ML.

## 16. Next phases

- SDK integration
- stronger validation
- ML model integration
- PostgreSQL + Alembic
