from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.modules.behavioural_biometrics import repository


@pytest.fixture(autouse=True)
def reset_behavioural_repository():
    repository.reset_repository()
    yield
    repository.reset_repository()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def _sample_payload(**overrides):
    payload = {
        "user_id": "user-001",
        "session_id": "session-001",
        "action_type": "LOGIN",
        "avg_key_interval_ms": 180.0,
        "avg_touch_duration_ms": 120.0,
        "typing_speed_cps": 4.2,
        "tap_pressure_avg": 0.45,
        "tap_pressure_std": 0.08,
        "error_count": 1,
        "correction_count": 0,
        "hesitation_time_ms": 350.0,
        "swipe_speed_avg": 1.8,
        "touch_precision_score": 0.91,
        "device_orientation_changes": 2,
        "session_duration_ms": 42000.0,
        "platform": "ANDROID",
        "payload_version": "v1",
    }
    payload.update(overrides)
    return payload


def test_enroll_returns_correct_response(client: TestClient):
    response = client.post("/api/v1/behavioural-biometrics/enroll", json=_sample_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user-001"
    assert body["samples_count"] == 1
    assert "baseline" in body
    assert "created_at" in body
    assert "updated_at" in body


def test_get_profile_returns_user_profile(client: TestClient):
    client.post("/api/v1/behavioural-biometrics/enroll", json=_sample_payload())
    response = client.get("/api/v1/behavioural-biometrics/users/user-001/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user-001"
    assert body["samples_count"] == 1
    assert "baseline" in body


def test_analyze_without_profile_returns_require_otp(client: TestClient):
    response = client.post("/api/v1/behavioural-biometrics/analyze", json=_sample_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 50
    assert body["risk_level"] == "MEDIUM"
    assert body["decision"] == "REQUIRE_OTP"
    assert "Profil comportemental insuffisant" in body["reasons"]


def test_analyze_after_normal_enrolls_returns_low_or_medium(client: TestClient):
    for idx in range(4):
        client.post(
            "/api/v1/behavioural-biometrics/enroll",
            json=_sample_payload(session_id=f"session-normal-{idx}", error_count=1, correction_count=0),
        )

    response = client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(session_id="session-check", error_count=1, correction_count=0),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["risk_level"] in {"LOW", "MEDIUM"}
    assert body["decision"] in {"ALLOW", "REQUIRE_OTP"}


def test_very_different_behaviour_returns_high_or_critical(client: TestClient):
    for idx in range(4):
        client.post(
            "/api/v1/behavioural-biometrics/enroll",
            json=_sample_payload(
                session_id=f"session-baseline-{idx}",
                avg_key_interval_ms=180.0,
                avg_touch_duration_ms=120.0,
                typing_speed_cps=4.2,
                error_count=1,
                correction_count=0,
                hesitation_time_ms=350.0,
                touch_precision_score=0.91,
                session_duration_ms=42000.0,
            ),
        )

    response = client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(
            session_id="session-anomalous",
            avg_key_interval_ms=420.0,
            avg_touch_duration_ms=40.0,
            typing_speed_cps=11.5,
            error_count=8,
            correction_count=5,
            hesitation_time_ms=2400.0,
            touch_precision_score=0.2,
            session_duration_ms=6000.0,
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["risk_level"] in {"HIGH", "CRITICAL"}
    assert body["decision"] in {"REQUIRE_STEP_UP", "DENY_OR_HOLD_ACTION"}


def test_score_is_always_between_0_and_100(client: TestClient):
    for idx in range(3):
        client.post("/api/v1/behavioural-biometrics/enroll", json=_sample_payload(session_id=f"session-score-{idx}"))

    response = client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(
            session_id="session-score-check",
            avg_key_interval_ms=1000.0,
            avg_touch_duration_ms=5.0,
            typing_speed_cps=30.0,
            error_count=100,
            correction_count=100,
            hesitation_time_ms=10000.0,
            touch_precision_score=0.0,
            session_duration_ms=1.0,
        ),
    )
    assert response.status_code == 200
    assert 0 <= response.json()["score"] <= 100


def test_response_contains_expected_fields(client: TestClient):
    response = client.post("/api/v1/behavioural-biometrics/analyze", json=_sample_payload())
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "module_name",
        "user_id",
        "session_id",
        "score",
        "risk_level",
        "decision",
        "reasons",
        "evidence",
        "profile_samples",
        "adapter_mode",
    }


def test_valid_endpoints_return_http_200(client: TestClient):
    enroll_response = client.post("/api/v1/behavioural-biometrics/enroll", json=_sample_payload())
    analyze_response = client.post("/api/v1/behavioural-biometrics/analyze", json=_sample_payload())
    profile_response = client.get("/api/v1/behavioural-biometrics/users/user-001/profile")

    assert enroll_response.status_code == 200
    assert analyze_response.status_code == 200
    assert profile_response.status_code == 200

