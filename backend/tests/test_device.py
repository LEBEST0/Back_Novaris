from __future__ import annotations

from datetime import datetime, timezone
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
def client(tmp_path: Path):
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
    response = client.post("/api/v1/device-intelligence/analyze", json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "module_name",
        "user_id",
        "device_id",
        "score",
        "risk_level",
        "decision",
        "reasons",
        "evidence",
        "adapter_mode",
    }


def test_enroll_endpoint_works(client):
    response = client.post(
        "/api/v1/device-intelligence/enroll",
        json={
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
    response = client.post(
        "/api/v1/device-intelligence/enroll",
        json={
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
    client.post(
        "/api/v1/device-intelligence/enroll",
        json={
            "user_id": "user-list",
            "device": _payload(user_id="user-list", device_id="device-list"),
        },
    )

    response = client.get("/api/v1/device-intelligence/users/user-list/devices")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["device_id"] == "device-list"


def test_analyze_uses_persisted_history(client):
    client.post(
        "/api/v1/device-intelligence/enroll",
        json={
            "user_id": "user-history",
            "device": _payload(user_id="user-history", device_id="device-history"),
        },
    )

    response = client.post(
        "/api/v1/device-intelligence/analyze",
        json=_payload(user_id="user-history", device_id="device-history"),
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
    first = client.post("/api/v1/device-intelligence/enroll", json=payload)
    second = client.post("/api/v1/device-intelligence/enroll", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200

    response = client.get("/api/v1/device-intelligence/users/user-dup/devices")
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
