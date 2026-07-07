from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.api.dependencies import get_db
from backend.app.main import app
from backend.app.modules.behavioural_biometrics.models import Base, BehaviouralProfile, BehaviouralRequestNonce, BehaviouralSample


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NOVARIS_BEHAVIOURAL_CLIENT_KEY", "test-behavioural-client-key")
    database_path = tmp_path / "behavioural_biometrics_test.sqlite3"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, TestingSessionLocal, database_path
    app.dependency_overrides.clear()
    engine.dispose()


def _headers() -> dict[str, str]:
    return {"X-Novaris-Client-Key": "test-behavioural-client-key"}


def _sample_payload(**overrides):
    payload = {
        "user_id": "user-001",
        "session_id": "session-001",
        "action_type": "LOGIN",
        "request_id": "req-001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": "nonce-001",
        "sdk_version": "1.0.0",
        "payload_version": "v1",
        "platform": "ANDROID",
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
    }
    payload.update(overrides)
    return payload


def _get_profile(SessionLocal, user_id: str) -> BehaviouralProfile | None:
    with SessionLocal() as db:
        return db.scalar(select(BehaviouralProfile).where(BehaviouralProfile.user_id == user_id))


def _get_samples(SessionLocal, user_id: str) -> list[BehaviouralSample]:
    with SessionLocal() as db:
        return list(db.scalars(select(BehaviouralSample).where(BehaviouralSample.user_id == user_id)).all())


def _get_nonces(SessionLocal) -> list[BehaviouralRequestNonce]:
    with SessionLocal() as db:
        return list(db.scalars(select(BehaviouralRequestNonce)).all())


def test_enroll_persists_a_sample_in_database(client):
    http_client, SessionLocal, _ = client

    response = http_client.post(
        "/api/v1/behavioural-biometrics/enroll",
        json=_sample_payload(user_id="user-db", session_id="session-db", request_id="req-db", nonce="nonce-db"),
        headers=_headers(),
    )
    assert response.status_code == 200

    profile = _get_profile(SessionLocal, "user-db")
    samples = _get_samples(SessionLocal, "user-db")
    nonces = _get_nonces(SessionLocal)

    assert profile is not None
    assert profile.samples_count == 1
    assert len(samples) == 1
    assert samples[0].session_id == "session-db"
    assert len(nonces) == 1
    assert nonces[0].nonce == "nonce-db"


def test_get_profile_returns_profile_from_database(client):
    http_client, SessionLocal, _ = client
    http_client.post(
        "/api/v1/behavioural-biometrics/enroll",
        json=_sample_payload(user_id="user-profile", session_id="session-profile", request_id="req-profile", nonce="nonce-profile"),
        headers=_headers(),
    )

    response = http_client.get(
        "/api/v1/behavioural-biometrics/users/user-profile/profile",
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user-profile"
    assert body["samples_count"] == 1
    assert "baseline" in body

    profile = _get_profile(SessionLocal, "user-profile")
    assert profile is not None
    assert profile.samples_count == 1


def test_analyze_uses_persisted_profile(client):
    http_client, SessionLocal, _ = client
    http_client.post(
        "/api/v1/behavioural-biometrics/enroll",
        json=_sample_payload(user_id="user-analyze", session_id="session-analyze-1", request_id="req-analyze-1", nonce="nonce-analyze-1"),
        headers=_headers(),
    )

    response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(user_id="user-analyze", session_id="session-analyze-2", request_id="req-analyze-2", nonce="nonce-analyze-2"),
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile_samples"] == 1
    assert body["evidence"]["profile"]["samples_count"] == 1

    profile = _get_profile(SessionLocal, "user-analyze")
    assert profile is not None


def test_profile_survives_new_sqlalchemy_session(client):
    http_client, SessionLocal, database_path = client
    http_client.post(
        "/api/v1/behavioural-biometrics/enroll",
        json=_sample_payload(user_id="user-reopen", session_id="session-reopen", request_id="req-reopen", nonce="nonce-reopen"),
        headers=_headers(),
    )

    new_engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    NewSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=new_engine)
    try:
        profile = _get_profile(NewSessionLocal, "user-reopen")
        assert profile is not None
        assert profile.samples_count == 1
    finally:
        new_engine.dispose()


def test_samples_count_increases_after_multiple_enrolls(client):
    http_client, SessionLocal, _ = client
    for idx in range(4):
        http_client.post(
            "/api/v1/behavioural-biometrics/enroll",
            json=_sample_payload(
                user_id="user-count",
                session_id=f"session-{idx}",
                request_id=f"req-count-{idx}",
                nonce=f"nonce-count-{idx}",
            ),
            headers=_headers(),
        )

    profile = _get_profile(SessionLocal, "user-count")
    assert profile is not None
    assert profile.samples_count == 4
    assert len(profile.samples) == 4


def test_no_sensitive_content_is_stored(client):
    _, _, _ = client
    sample_columns = set(BehaviouralSample.__table__.columns.keys())
    forbidden = {"pin", "password", "content", "conversation", "face", "fingerprint"}
    assert sample_columns.isdisjoint(forbidden)


def test_score_remains_bounded_between_0_and_100(client):
    http_client, _, _ = client
    for idx in range(3):
        http_client.post(
            "/api/v1/behavioural-biometrics/enroll",
            json=_sample_payload(
                user_id="user-score",
                session_id=f"baseline-{idx}",
                request_id=f"req-score-{idx}",
                nonce=f"nonce-score-{idx}",
            ),
            headers=_headers(),
        )

    response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(
            user_id="user-score",
            session_id="anomaly",
            request_id="req-score-anomaly",
            nonce="nonce-score-anomaly",
            avg_key_interval_ms=1000.0,
            avg_touch_duration_ms=5.0,
            typing_speed_cps=30.0,
            error_count=100,
            correction_count=100,
            hesitation_time_ms=10000.0,
            touch_precision_score=0.0,
            session_duration_ms=1.0,
        ),
        headers=_headers(),
    )
    assert response.status_code == 200
    assert 0 <= response.json()["score"] <= 100


def test_old_behavioural_contracts_still_pass(client):
    http_client, _, _ = client
    enroll_response = http_client.post(
        "/api/v1/behavioural-biometrics/enroll",
        json=_sample_payload(user_id="user-contract", session_id="session-contract-1", request_id="req-contract-1", nonce="nonce-contract-1"),
        headers=_headers(),
    )
    analyze_response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(user_id="user-contract", session_id="session-contract-2", request_id="req-contract-2", nonce="nonce-contract-2"),
        headers=_headers(),
    )
    profile_response = http_client.get(
        "/api/v1/behavioural-biometrics/users/user-contract/profile",
        headers=_headers(),
    )

    assert enroll_response.status_code == 200
    assert analyze_response.status_code == 200
    assert profile_response.status_code == 200


def test_analyze_response_contains_expected_fields(client):
    http_client, _, _ = client
    response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(user_id="user-response", session_id="session-response", request_id="req-response", nonce="nonce-response"),
        headers=_headers(),
    )
    assert response.status_code == 200
    assert set(response.json().keys()) == {
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


def test_enroll_without_key_is_rejected(client):
    http_client, _, _ = client
    response = http_client.post(
        "/api/v1/behavioural-biometrics/enroll",
        json=_sample_payload(user_id="user-no-key", session_id="session-no-key", request_id="req-no-key", nonce="nonce-no-key"),
    )
    assert response.status_code == 403


def test_enroll_with_key_is_accepted(client):
    http_client, _, _ = client
    response = http_client.post(
        "/api/v1/behavioural-biometrics/enroll",
        json=_sample_payload(user_id="user-with-key", session_id="session-with-key", request_id="req-with-key", nonce="nonce-with-key"),
        headers=_headers(),
    )
    assert response.status_code == 200


def test_payload_version_v1_is_accepted_on_enroll(client):
    http_client, _, _ = client
    response = http_client.post(
        "/api/v1/behavioural-biometrics/enroll",
        json=_sample_payload(user_id="user-v1-enroll", session_id="session-v1-enroll", request_id="req-v1-enroll", nonce="nonce-v1-enroll", payload_version="v1"),
        headers=_headers(),
    )
    assert response.status_code == 200


def test_payload_version_v1_is_accepted_on_analyze(client):
    http_client, _, _ = client
    response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(user_id="user-v1-analyze", session_id="session-v1-analyze", request_id="req-v1-analyze", nonce="nonce-v1-analyze", payload_version="v1"),
        headers=_headers(),
    )
    assert response.status_code == 200


def test_unknown_payload_version_is_rejected(client):
    http_client, _, _ = client
    response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(user_id="user-v2", session_id="session-v2", request_id="req-v2", nonce="nonce-v2", payload_version="v2"),
        headers=_headers(),
    )
    assert response.status_code == 422


@pytest.mark.parametrize("platform", ["ANDROID", "IOS", "WEB_MOCK"])
def test_supported_platforms_are_accepted(client, platform: str):
    http_client, _, _ = client
    response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(user_id=f"user-{platform}", session_id=f"session-{platform}", request_id=f"req-{platform}", nonce=f"nonce-{platform}", platform=platform),
        headers=_headers(),
    )
    assert response.status_code == 200


def test_unknown_platform_is_rejected(client):
    http_client, _, _ = client
    response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(user_id="user-platform-unknown", session_id="session-platform-unknown", request_id="req-platform-unknown", nonce="nonce-platform-unknown", platform="WINDOWS_PHONE"),
        headers=_headers(),
    )
    assert response.status_code == 422


def test_valid_action_type_is_accepted(client):
    http_client, _, _ = client
    response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(action_type="LOGIN", user_id="user-action-valid", session_id="session-action-valid", request_id="req-action-valid", nonce="nonce-action-valid"),
        headers=_headers(),
    )
    assert response.status_code == 200


def test_unknown_action_type_is_rejected(client):
    http_client, _, _ = client
    response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(action_type="SWIPE_LEFT", user_id="user-action-unknown", session_id="session-action-unknown", request_id="req-action-unknown", nonce="nonce-action-unknown"),
        headers=_headers(),
    )
    assert response.status_code == 422


def test_analyze_without_key_is_rejected(client):
    http_client, _, _ = client
    response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(user_id="user-analyze-no-key", session_id="session-analyze-no-key", request_id="req-analyze-no-key", nonce="nonce-analyze-no-key"),
    )
    assert response.status_code == 403


def test_analyze_with_key_is_accepted(client):
    http_client, _, _ = client
    response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(user_id="user-analyze-key", session_id="session-analyze-key", request_id="req-analyze-key", nonce="nonce-analyze-key"),
        headers=_headers(),
    )
    assert response.status_code == 200


def test_get_profile_without_key_is_rejected(client):
    http_client, _, _ = client
    response = http_client.get("/api/v1/behavioural-biometrics/users/user-profile-no-key/profile")
    assert response.status_code == 403


def test_get_profile_with_key_is_accepted(client):
    http_client, _, _ = client
    http_client.post(
        "/api/v1/behavioural-biometrics/enroll",
        json=_sample_payload(user_id="user-profile-key", session_id="session-profile-key", request_id="req-profile-key", nonce="nonce-profile-key"),
        headers=_headers(),
    )
    response = http_client.get(
        "/api/v1/behavioural-biometrics/users/user-profile-key/profile",
        headers=_headers(),
    )
    assert response.status_code == 200


def test_timestamp_expired_is_rejected(client):
    http_client, _, _ = client
    response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(
            user_id="user-expired",
            session_id="session-expired",
            request_id="req-expired",
            nonce="nonce-expired",
            timestamp=(datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat(),
        ),
        headers=_headers(),
    )
    assert response.status_code == 400


def test_nonce_reuse_on_analyze_is_rejected(client):
    http_client, _, _ = client
    payload = _sample_payload(
        user_id="user-replay-analyze",
        session_id="session-replay-1",
        request_id="req-replay-1",
        nonce="nonce-replay-analyze",
    )
    first = http_client.post("/api/v1/behavioural-biometrics/analyze", json=payload, headers=_headers())
    second = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(
            user_id="user-replay-analyze",
            session_id="session-replay-2",
            request_id="req-replay-2",
            nonce="nonce-replay-analyze",
        ),
        headers=_headers(),
    )
    assert first.status_code == 200
    assert second.status_code == 409


def test_nonce_reuse_on_enroll_is_rejected(client):
    http_client, _, _ = client
    payload = _sample_payload(
        user_id="user-replay-enroll",
        session_id="session-replay-enroll-1",
        request_id="req-replay-enroll-1",
        nonce="nonce-replay-enroll",
    )
    first = http_client.post("/api/v1/behavioural-biometrics/enroll", json=payload, headers=_headers())
    second = http_client.post(
        "/api/v1/behavioural-biometrics/enroll",
        json=_sample_payload(
            user_id="user-replay-enroll",
            session_id="session-replay-enroll-2",
            request_id="req-replay-enroll-2",
            nonce="nonce-replay-enroll",
        ),
        headers=_headers(),
    )
    assert first.status_code == 200
    assert second.status_code == 409


def test_missing_nonce_is_a_validation_error(client):
    http_client, _, _ = client
    payload = _sample_payload(user_id="user-missing-nonce", session_id="session-missing-nonce", request_id="req-missing-nonce")
    payload.pop("nonce")
    response = http_client.post("/api/v1/behavioural-biometrics/analyze", json=payload, headers=_headers())
    assert response.status_code == 422
