from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.api.dependencies import get_db
from backend.app.main import app
from backend.app.modules.behavioural_biometrics.models import (
    BehaviouralProfile,
    BehaviouralSample,
    Base,
)
from backend.app.modules.behavioural_biometrics.rules import evaluate_behavioural_risk
from backend.app.modules.behavioural_biometrics.schemas import BehaviouralSampleInput


CLIENT_KEY = "test-behavioural-client-key"
SIGNATURE_SECRET = "test-behavioural-signature-secret"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NOVARIS_BEHAVIOURAL_CLIENT_KEY", CLIENT_KEY)
    monkeypatch.setenv("NOVARIS_BEHAVIOURAL_SIGNATURE_SECRET", SIGNATURE_SECRET)
    database_path = tmp_path / "behavioural_biometrics_test.sqlite3"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    app.state.behavioural_testing_session_factory = TestingSessionLocal

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    delattr(app.state, "behavioural_testing_session_factory")


def _client_headers() -> dict[str, str]:
    return {"X-Novaris-Client-Key": CLIENT_KEY}


def _canonical_body(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _signature(payload: dict, *, secret: str = SIGNATURE_SECRET) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        _canonical_body(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _signed_post(client: TestClient, url: str, payload: dict, *, signature: str | None = None):
    headers = _client_headers()
    if signature is not None:
        headers["X-Novaris-Signature"] = signature
    headers["Content-Type"] = "application/json"
    return client.post(url, headers=headers, content=_canonical_body(payload))


def _payload(**overrides):
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


def _enroll_payload(**overrides):
    payload = _payload(**overrides)
    payload.update(
        {
            "brand": "Samsung",
            "model": "Galaxy S23",
            "os_name": "Android",
            "os_version": "14",
            "app_version": "1.0.0",
            "is_rooted": False,
            "is_emulator": False,
            "is_vpn": False,
            "is_proxy": False,
            "ip_address": "196.0.0.1",
            "country": "CI",
            "city": "Abidjan",
            "latitude": 5.36,
            "longitude": -4.01,
            "language": "fr",
        }
    )
    return payload


def test_enroll_without_signature_is_rejected(client):
    response = client.post(
        "/api/v1/behavioural-biometrics/enroll",
        headers=_client_headers(),
        json=_enroll_payload(),
    )
    assert response.status_code == 403


def test_enroll_with_invalid_signature_is_rejected(client):
    response = _signed_post(client, "/api/v1/behavioural-biometrics/enroll", _enroll_payload(), signature="bad-signature")
    assert response.status_code == 403


def test_enroll_with_signature_is_accepted(client):
    payload = _enroll_payload()
    response = _signed_post(client, "/api/v1/behavioural-biometrics/enroll", payload, signature=_signature(payload))
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user-001"
    assert body["samples_count"] == 1


def test_analyze_without_signature_is_rejected(client):
    response = client.post(
        "/api/v1/behavioural-biometrics/analyze",
        headers=_client_headers(),
        json=_payload(),
    )
    assert response.status_code == 403


def test_analyze_with_invalid_signature_is_rejected(client):
    response = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", _payload(), signature="bad-signature")
    assert response.status_code == 403


def test_analyze_with_signature_returns_confidence_score(client):
    payload = _payload()
    response = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", payload, signature=_signature(payload))
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "module_name",
        "user_id",
        "session_id",
        "score",
        "confidence_score",
        "risk_level",
        "decision",
        "reasons",
        "evidence",
        "profile_samples",
        "adapter_mode",
    }
    assert 0 <= body["confidence_score"] <= 100
    assert body["confidence_score"] == 100


def test_complete_valid_request_has_full_confidence(client):
    payload = _payload()
    response = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", payload, signature=_signature(payload))
    assert response.status_code == 200
    assert response.json()["confidence_score"] == 100


def test_score_is_always_bounded(client):
    payload = _payload(
        avg_key_interval_ms=900.0,
        avg_touch_duration_ms=900.0,
        typing_speed_cps=12.0,
        tap_pressure_avg=0.1,
        tap_pressure_std=0.01,
        error_count=12,
        correction_count=11,
        hesitation_time_ms=9000.0,
        swipe_speed_avg=0.2,
        touch_precision_score=0.2,
        device_orientation_changes=20,
        session_duration_ms=5.0,
    )
    result = evaluate_behavioural_risk(BehaviouralSampleInput.model_validate(payload), None)
    assert 0 <= result["score"] <= 100


def test_analyze_without_profile_returns_require_otp(client):
    payload = _payload(user_id="user-no-profile")
    response = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", payload, signature=_signature(payload))
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "REQUIRE_OTP"
    assert body["score"] == 50
    assert body["risk_level"] == "MEDIUM"
    assert body["reasons"] == ["Profil comportemental insuffisant"]


def test_enroll_persists_sample_and_profile(client):
    payload = _enroll_payload(user_id="user-persist", session_id="session-persist", nonce="nonce-persist", request_id="req-persist")
    response = _signed_post(client, "/api/v1/behavioural-biometrics/enroll", payload, signature=_signature(payload))
    assert response.status_code == 200

    db_factory = app.state.behavioural_testing_session_factory
    with db_factory() as db:
        profile = db.scalar(select(BehaviouralProfile).where(BehaviouralProfile.user_id == "user-persist"))
        sample = db.scalar(select(BehaviouralSample).where(BehaviouralSample.user_id == "user-persist"))
        assert profile is not None
        assert sample is not None
        assert profile.samples_count == 1


def test_profile_endpoint_returns_persisted_profile(client):
    payload = _enroll_payload(user_id="user-profile", session_id="session-profile", nonce="nonce-profile", request_id="req-profile")
    enroll_response = _signed_post(client, "/api/v1/behavioural-biometrics/enroll", payload, signature=_signature(payload))
    assert enroll_response.status_code == 200

    response = client.get("/api/v1/behavioural-biometrics/users/user-profile/profile", headers=_client_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user-profile"
    assert body["samples_count"] == 1


def test_analyze_uses_persisted_profile(client):
    first = _enroll_payload(
        user_id="user-history",
        session_id="session-history-1",
        nonce="nonce-history-1",
        request_id="req-history-1",
    )
    second = _enroll_payload(
        user_id="user-history",
        session_id="session-history-2",
        nonce="nonce-history-2",
        request_id="req-history-2",
        avg_key_interval_ms=185.0,
        avg_touch_duration_ms=121.0,
        typing_speed_cps=4.1,
    )
    assert _signed_post(client, "/api/v1/behavioural-biometrics/enroll", first, signature=_signature(first)).status_code == 200
    assert _signed_post(client, "/api/v1/behavioural-biometrics/enroll", second, signature=_signature(second)).status_code == 200

    analyze_payload = _payload(
        user_id="user-history",
        session_id="session-history-analyze",
        nonce="nonce-history-analyze",
        request_id="req-history-analyze",
        avg_key_interval_ms=188.0,
        avg_touch_duration_ms=123.0,
        typing_speed_cps=4.0,
    )
    response = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", analyze_payload, signature=_signature(analyze_payload))
    assert response.status_code == 200
    assert response.json()["profile_samples"] >= 2


def test_persistence_survives_new_sqlalchemy_session(tmp_path: Path):
    database_path = tmp_path / "behavioural_biometrics_test.sqlite3"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    payload = _enroll_payload(user_id="user-persist", session_id="session-persist", nonce="nonce-persist", request_id="req-persist")
    with Session() as db:
        profile = BehaviouralProfile(
            user_id="user-persist",
            samples_count=1,
            baseline_data={"samples_count": 1, "metrics": {}},
        )
        db.add(profile)
        db.add(
            BehaviouralSample(
                profile=profile,
                user_id="user-persist",
                session_id="session-persist",
                action_type=payload["action_type"],
                avg_key_interval_ms=payload["avg_key_interval_ms"],
                avg_touch_duration_ms=payload["avg_touch_duration_ms"],
                typing_speed_cps=payload["typing_speed_cps"],
                tap_pressure_avg=payload["tap_pressure_avg"],
                tap_pressure_std=payload["tap_pressure_std"],
                error_count=payload["error_count"],
                correction_count=payload["correction_count"],
                hesitation_time_ms=payload["hesitation_time_ms"],
                swipe_speed_avg=payload["swipe_speed_avg"],
                touch_precision_score=payload["touch_precision_score"],
                device_orientation_changes=payload["device_orientation_changes"],
                session_duration_ms=payload["session_duration_ms"],
                platform=payload["platform"],
                payload_version=payload["payload_version"],
            )
        )
        db.commit()

    engine.dispose()
    engine2 = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Session2 = sessionmaker(autocommit=False, autoflush=False, bind=engine2)
    with Session2() as db:
        record = db.scalar(select(BehaviouralProfile).where(BehaviouralProfile.user_id == "user-persist"))
        assert record is not None


def test_duplicate_enroll_does_not_create_second_record(client):
    payload = _enroll_payload(user_id="user-dup", session_id="session-dup", nonce="nonce-dup", request_id="req-dup")
    first = _signed_post(client, "/api/v1/behavioural-biometrics/enroll", payload, signature=_signature(payload))
    second = _signed_post(client, "/api/v1/behavioural-biometrics/enroll", payload, signature=_signature(payload))
    assert first.status_code == 200
    assert second.status_code == 409

    response = client.get("/api/v1/behavioural-biometrics/users/user-dup/profile", headers=_client_headers())
    assert response.status_code == 200
    assert response.json()["samples_count"] == 1


def test_nonce_reuse_is_rejected(client):
    payload = _payload(user_id="user-nonce", session_id="session-nonce", nonce="nonce-reuse", request_id="req-nonce")
    first = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", payload, signature=_signature(payload))
    second = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", payload, signature=_signature(payload))
    assert first.status_code == 200
    assert second.status_code == 409


def test_expired_timestamp_is_rejected(client):
    payload = _payload(timestamp=(datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat())
    response = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", payload, signature=_signature(payload))
    assert response.status_code == 400


def test_payload_version_v1_is_accepted(client):
    payload = _payload(payload_version="v1")
    response = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", payload, signature=_signature(payload))
    assert response.status_code == 200


def test_unknown_payload_version_is_rejected(client):
    payload = _payload(payload_version="v2")
    response = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", payload, signature=_signature(payload))
    assert response.status_code == 422


@pytest.mark.parametrize("platform", ["ANDROID", "IOS", "WEB_MOCK"])
def test_supported_platforms_are_accepted(client, platform: str):
    payload = _payload(platform=platform)
    response = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", payload, signature=_signature(payload))
    assert response.status_code == 200


def test_unknown_platform_is_rejected(client):
    payload = _payload(platform="DESKTOP")
    response = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", payload, signature=_signature(payload))
    assert response.status_code == 422


@pytest.mark.parametrize("action_type", ["LOGIN", "PIN_ENTRY", "TRANSACTION_CONFIRMATION", "PASSWORD_CHANGE", "BENEFICIARY_ADD"])
def test_supported_action_types_are_accepted(client, action_type: str):
    payload = _payload(action_type=action_type)
    response = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", payload, signature=_signature(payload))
    assert response.status_code == 200


def test_unknown_action_type_is_rejected(client):
    payload = _payload(action_type="WIRE_TRANSFER")
    response = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", payload, signature=_signature(payload))
    assert response.status_code == 422


def test_get_profile_without_key_is_rejected(client):
    response = client.get("/api/v1/behavioural-biometrics/users/user-profile/profile")
    assert response.status_code == 403


def test_get_profile_with_key_is_accepted(client):
    payload = _enroll_payload(user_id="user-get-profile", session_id="session-get-profile", nonce="nonce-get-profile", request_id="req-get-profile")
    assert _signed_post(client, "/api/v1/behavioural-biometrics/enroll", payload, signature=_signature(payload)).status_code == 200
    response = client.get("/api/v1/behavioural-biometrics/users/user-get-profile/profile", headers=_client_headers())
    assert response.status_code == 200


def test_contract_response_contains_expected_fields(client):
    payload = _payload()
    response = _signed_post(client, "/api/v1/behavioural-biometrics/analyze", payload, signature=_signature(payload))
    assert response.status_code == 200
    body = response.json()
    assert "module_name" in body
    assert "score" in body
    assert "risk_level" in body
    assert "decision" in body
    assert "reasons" in body
    assert "evidence" in body


def test_client_key_is_required(client):
    payload = _payload()
    response = client.post(
        "/api/v1/behavioural-biometrics/analyze",
        content=_canonical_body(payload),
        headers={"X-Novaris-Signature": _signature(payload)},
    )
    assert response.status_code == 403
