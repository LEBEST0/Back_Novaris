# Behavioural Biometrics

Phase 1 backend module for Novaris AI.

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

## Operating mode

- in-memory repository
- rule-based statistical scoring
- no real ML model yet
- no mobile SDK yet

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

- durable persistence
- SQLAlchemy repository
- SDK mobile integration
- stronger validation
- ML predictor

