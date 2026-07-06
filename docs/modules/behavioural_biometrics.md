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
  "adapter_mode": "RULE_BASED"
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

## 11. Current limits

- SQLite is still the development persistence layer.
- No anti-replay.
- No signature.
- No real SDK.
- No real ML.

## 12. Next phases

- SDK integration
- stronger validation
- ML model integration
- PostgreSQL + Alembic
