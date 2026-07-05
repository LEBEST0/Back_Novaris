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
from backend.app.modules.device_intelligence.models import Base, UserDeviceFingerprint
from backend.app.modules.device_intelligence.rules import evaluate_device_risk


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NOVARIS_DEVICE_CLIENT_KEY", "test-client-key")
    monkeypatch.setenv("NOVARIS_DEVICE_SIGNATURE_SECRET", "test-signature-secret")
    database_path = tmp_path / "device_intelligence_test.sqlite3"
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
        yield test_client
    app.dependency_overrides.clear()


def _payload(**overrides):
    payload = {
        "user_id": "user-001",
        "device_id": "device-001",
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
    payload.update(overrides)
    return payload


def _analyze_payload(**overrides):
    payload = _payload(**overrides)
    payload.update(
        {
            "request_id": "req-001",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "nonce-001",
            "sdk_version": "1.0.0",
            "payload_version": "v1",
            "platform": "ANDROID",
        }
    )
    payload.update(overrides)
    return payload


def _client_headers() -> dict[str, str]:
    return {"X-Novaris-Client-Key": "test-client-key"}


def _signed_post(client, url: str, payload: dict, *, extra_headers: dict[str, str] | None = None):
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    signature = hmac.new(
        b"test-signature-secret",
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    headers = _client_headers() | {"X-Novaris-Signature": signature}
    if extra_headers:
        headers |= extra_headers
    headers["Content-Type"] = "application/json"
    return client.post(url, headers=headers, content=body)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def test_normal_device_allows_pin():
    result = evaluate_device_risk(
        _payload(),
        {
            "latest_trusted_device": {
                "device_id": "device-001",
                "brand": "Samsung",
                "model": "Galaxy S23",
                "os_name": "Android",
                "os_version": "14",
                "country": "CI",
                "city": "Abidjan",
            }
        },
    )
    assert result["decision"] == "ALLOW_PIN"
    assert result["risk_level"] == "LOW"
    assert 0 <= result["score"] <= 100


def test_rooted_device_is_critical():
    result = evaluate_device_risk(_payload(is_rooted=True), {"latest_trusted_device": None})
    assert result["risk_level"] == "CRITICAL"
    assert result["decision"] == "DENY_PIN"
    assert result["score"] >= 80


def test_emulator_device_is_critical():
    result = evaluate_device_risk(_payload(is_emulator=True), {"latest_trusted_device": None})
    assert result["risk_level"] == "CRITICAL"
    assert result["decision"] == "DENY_PIN"
    assert result["score"] >= 80


def test_new_device_score_increases():
    result = evaluate_device_risk(
        _payload(device_id="device-002"),
        {
            "latest_trusted_device": {
                "device_id": "device-001",
                "brand": "Samsung",
                "model": "Galaxy S23",
                "os_name": "Android",
                "os_version": "14",
                "country": "CI",
                "city": "Abidjan",
            }
        },
    )
    assert result["score"] >= 30


def test_vpn_and_country_change_raise_risk():
    history = {
        "latest_trusted_device": {
            "device_id": "device-001",
            "brand": "Samsung",
            "model": "Galaxy S23",
            "os_name": "Android",
            "os_version": "14",
            "country": "CI",
            "city": "Abidjan",
        }
    }
    result = evaluate_device_risk(_payload(is_vpn=True, country="FR", city="Paris"), history)
    assert result["risk_level"] in {"HIGH", "CRITICAL"}
    assert result["score"] >= 60


def test_analyze_endpoint_returns_all_fields(client):
    response = _signed_post(client, "/api/v1/device-intelligence/analyze", _analyze_payload())
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "module_name",
        "user_id",
        "device_id",
        "score",
        "confidence_score",
        "risk_level",
        "decision",
        "reasons",
        "evidence",
        "adapter_mode",
    }


def test_enroll_endpoint_works(client):
    response = _signed_post(
        client,
        "/api/v1/device-intelligence/enroll",
        {
            "user_id": "user-001",
            "device": _payload(),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ENROLLED"
    assert body["user_id"] == "user-001"
    assert body["device_id"] == "device-001"


def test_enroll_persists_device_in_database(client, tmp_path: Path):
    response = _signed_post(
        client,
        "/api/v1/device-intelligence/enroll",
        {
            "user_id": "user-db",
            "device": _payload(user_id="user-db", device_id="device-db"),
        },
    )
    assert response.status_code == 200

    database_path = tmp_path / "device_intelligence_test.sqlite3"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with Session() as db:
        record = db.scalar(
            select(UserDeviceFingerprint).where(
                UserDeviceFingerprint.user_id == "user-db",
                UserDeviceFingerprint.device_id == "device-db",
            )
        )
        assert record is not None
        assert record.status == "TRUSTED"


def test_list_devices_returns_enrolled_device(client):
    _signed_post(
        client,
        "/api/v1/device-intelligence/enroll",
        {
            "user_id": "user-list",
            "device": _payload(user_id="user-list", device_id="device-list"),
        },
    )

    response = client.get(
        "/api/v1/device-intelligence/users/user-list/devices",
        headers=_client_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["device_id"] == "device-list"


def test_analyze_uses_persisted_history(client):
    _signed_post(
        client,
        "/api/v1/device-intelligence/enroll",
        {
            "user_id": "user-history",
            "device": _payload(user_id="user-history", device_id="device-history"),
        },
    )

    response = _signed_post(
        client,
        "/api/v1/device-intelligence/analyze",
        _analyze_payload(user_id="user-history", device_id="device-history"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "ALLOW_PIN"
    assert body["evidence"]["history"]["device_id"] == "device-history"


def test_persistence_survives_new_sqlalchemy_session(tmp_path: Path):
    database_path = tmp_path / "device_intelligence_test.sqlite3"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    with Session() as db:
        db.add(
            UserDeviceFingerprint(
                user_id="user-persist",
                device_id="device-persist",
                device_hash="hash",
                brand="Samsung",
                model="Galaxy S23",
                os_name="Android",
                os_version="14",
                ip_address="196.0.0.1",
                country="CI",
                city="Abidjan",
                status="TRUSTED",
                first_seen_at=_utcnow(),
                last_used_at=_utcnow(),
                created_at=_utcnow(),
                updated_at=_utcnow(),
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
        record = db.scalar(
            select(UserDeviceFingerprint).where(
                UserDeviceFingerprint.user_id == "user-persist",
                UserDeviceFingerprint.device_id == "device-persist",
            )
        )
        assert record is not None


def test_duplicate_enroll_does_not_create_second_record(client):
    payload = {
        "user_id": "user-dup",
        "device": _payload(user_id="user-dup", device_id="device-dup"),
    }
    first = _signed_post(client, "/api/v1/device-intelligence/enroll", payload)
    second = _signed_post(client, "/api/v1/device-intelligence/enroll", payload)
    assert first.status_code == 200
    assert second.status_code == 200

    response = client.get("/api/v1/device-intelligence/users/user-dup/devices", headers=_client_headers())
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_score_is_always_bounded():
    result = evaluate_device_risk(
        _payload(is_rooted=True, is_emulator=True, is_vpn=True, is_proxy=True, country="US"),
        {
            "latest_trusted_device": {
                "device_id": "device-001",
                "brand": "Apple",
                "model": "iPhone 12",
                "os_name": "iOS",
                "os_version": "17",
                "country": "CI",
                "city": "Abidjan",
            }
        },
    )
    assert 0 <= result["score"] <= 100


def test_valid_analyze_request_is_accepted(client):
    response = _signed_post(client, "/api/v1/device-intelligence/analyze", _analyze_payload())
    assert response.status_code == 200
    assert response.json()["decision"] == "ALLOW_PIN"
    assert response.json()["confidence_score"] == 100


def test_payload_v1_is_accepted(client):
    response = _signed_post(client, "/api/v1/device-intelligence/analyze", _analyze_payload(payload_version="v1"))
    assert response.status_code == 200


def test_unknown_payload_version_is_rejected(client):
    response = _signed_post(client, "/api/v1/device-intelligence/analyze", _analyze_payload(payload_version="v2"))
    assert response.status_code == 422
    assert "payload_version" in response.text


@pytest.mark.parametrize("platform", ["ANDROID", "IOS", "WEB_MOCK"])
def test_supported_platforms_are_accepted(client, platform: str):
    response = _signed_post(client, "/api/v1/device-intelligence/analyze", _analyze_payload(platform=platform))
    assert response.status_code == 200


def test_expired_timestamp_is_rejected(client):
    payload = _analyze_payload()
    payload["timestamp"] = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
    response = _signed_post(client, "/api/v1/device-intelligence/analyze", payload)
    assert response.status_code == 400


def test_nonce_reuse_is_rejected(client):
    payload = _analyze_payload(user_id="user-nonce", device_id="device-nonce")
    first = _signed_post(client, "/api/v1/device-intelligence/analyze", payload)
    second = _signed_post(client, "/api/v1/device-intelligence/analyze", payload)
    assert first.status_code == 200
    assert second.status_code == 409


def test_missing_client_key_is_rejected(client):
    response = client.post("/api/v1/device-intelligence/analyze", json=_analyze_payload())
    assert response.status_code == 403


def test_api_contract_is_conserved(client):
    response = _signed_post(client, "/api/v1/device-intelligence/analyze", _analyze_payload())
    assert set(response.json().keys()) == {
        "module_name",
        "user_id",
        "device_id",
        "score",
        "confidence_score",
        "risk_level",
        "decision",
        "reasons",
        "evidence",
        "adapter_mode",
    }


def test_enroll_without_key_is_rejected(client):
    response = client.post(
        "/api/v1/device-intelligence/enroll",
        json={
            "user_id": "user-no-key",
            "device": _payload(user_id="user-no-key", device_id="device-no-key"),
        },
    )
    assert response.status_code == 403


def test_enroll_with_key_is_accepted(client):
    response = _signed_post(
        client,
        "/api/v1/device-intelligence/enroll",
        {
            "user_id": "user-with-key",
            "device": _payload(user_id="user-with-key", device_id="device-with-key"),
        },
    )
    assert response.status_code == 200


def test_list_devices_without_key_is_rejected(client):
    response = client.get("/api/v1/device-intelligence/users/user-list/devices")
    assert response.status_code == 403


def test_list_devices_with_key_is_accepted(client):
    _signed_post(
        client,
        "/api/v1/device-intelligence/enroll",
        {
            "user_id": "user-list-key",
            "device": _payload(user_id="user-list-key", device_id="device-list-key"),
        },
    )
    response = client.get(
        "/api/v1/device-intelligence/users/user-list-key/devices",
        headers=_client_headers(),
    )
    assert response.status_code == 200


def test_analyze_without_signature_is_rejected(client):
    response = client.post(
        "/api/v1/device-intelligence/analyze",
        headers=_client_headers(),
        json=_analyze_payload(),
    )
    assert response.status_code == 403


def test_enroll_without_signature_is_rejected(client):
    response = client.post(
        "/api/v1/device-intelligence/enroll",
        headers=_client_headers(),
        json={
            "user_id": "user-no-signature",
            "device": _payload(user_id="user-no-signature", device_id="device-no-signature"),
        },
    )
    assert response.status_code == 403


def test_invalid_signature_is_rejected(client):
    body = json.dumps(_analyze_payload(), separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    response = client.post(
        "/api/v1/device-intelligence/analyze",
        headers=_client_headers() | {"X-Novaris-Signature": "bad-signature"},
        content=body,
    )
    assert response.status_code == 403


def test_confidence_score_is_bounded(client):
    response = _signed_post(client, "/api/v1/device-intelligence/analyze", _analyze_payload())
    assert 0 <= response.json()["confidence_score"] <= 100


def test_complete_valid_request_gets_full_confidence(client):
    response = _signed_post(client, "/api/v1/device-intelligence/analyze", _analyze_payload())
    assert response.json()["confidence_score"] == 100
