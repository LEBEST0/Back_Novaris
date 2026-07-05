from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from backend.app.api.dependencies import get_db
from backend.app.main import app
from backend.app.modules.device_intelligence.models import Base
from backend.app.modules.device_intelligence.rules import evaluate_device_risk
from backend.app.shared.database.session import SessionLocal


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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
