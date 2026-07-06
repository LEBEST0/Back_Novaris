from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.api.dependencies import get_db
from backend.app.main import app
from backend.app.modules.behavioural_biometrics.models import Base, BehaviouralProfile, BehaviouralSample


@pytest.fixture()
def client(tmp_path: Path):
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


def _get_profile(SessionLocal, user_id: str) -> BehaviouralProfile | None:
    with SessionLocal() as db:
        return db.scalar(select(BehaviouralProfile).where(BehaviouralProfile.user_id == user_id))


def _get_samples(SessionLocal, user_id: str) -> list[BehaviouralSample]:
    with SessionLocal() as db:
        return list(db.scalars(select(BehaviouralSample).where(BehaviouralSample.user_id == user_id)).all())


def test_enroll_persists_a_sample_in_database(client):
    http_client, SessionLocal, _ = client

    response = http_client.post("/api/v1/behavioural-biometrics/enroll", json=_sample_payload())
    assert response.status_code == 200

    profile = _get_profile(SessionLocal, "user-001")
    samples = _get_samples(SessionLocal, "user-001")

    assert profile is not None
    assert profile.samples_count == 1
    assert len(samples) == 1
    assert samples[0].session_id == "session-001"


def test_get_profile_returns_profile_from_database(client):
    http_client, SessionLocal, _ = client
    http_client.post("/api/v1/behavioural-biometrics/enroll", json=_sample_payload())

    response = http_client.get("/api/v1/behavioural-biometrics/users/user-001/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user-001"
    assert body["samples_count"] == 1
    assert "baseline" in body

    profile = _get_profile(SessionLocal, "user-001")
    assert profile is not None
    assert profile.samples_count == 1


def test_analyze_uses_persisted_profile(client):
    http_client, SessionLocal, _ = client
    http_client.post("/api/v1/behavioural-biometrics/enroll", json=_sample_payload())

    response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(session_id="session-002"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile_samples"] == 1
    assert body["evidence"]["profile"]["samples_count"] == 1

    profile = _get_profile(SessionLocal, "user-001")
    assert profile is not None


def test_profile_survives_new_sqlalchemy_session(client):
    http_client, SessionLocal, database_path = client
    http_client.post("/api/v1/behavioural-biometrics/enroll", json=_sample_payload(user_id="user-reopen"))

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
            json=_sample_payload(user_id="user-count", session_id=f"session-{idx}"),
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
        http_client.post("/api/v1/behavioural-biometrics/enroll", json=_sample_payload(session_id=f"baseline-{idx}"))

    response = http_client.post(
        "/api/v1/behavioural-biometrics/analyze",
        json=_sample_payload(
            session_id="anomaly",
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


def test_old_behavioural_contracts_still_pass(client):
    http_client, _, _ = client
    enroll_response = http_client.post("/api/v1/behavioural-biometrics/enroll", json=_sample_payload())
    analyze_response = http_client.post("/api/v1/behavioural-biometrics/analyze", json=_sample_payload())
    profile_response = http_client.get("/api/v1/behavioural-biometrics/users/user-001/profile")

    assert enroll_response.status_code == 200
    assert analyze_response.status_code == 200
    assert profile_response.status_code == 200


def test_analyze_response_contains_expected_fields(client):
    http_client, _, _ = client
    response = http_client.post("/api/v1/behavioural-biometrics/analyze", json=_sample_payload())
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
