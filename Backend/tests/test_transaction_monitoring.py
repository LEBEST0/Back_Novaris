from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from core.decision_engine import aggregate_final_score, decide
from main import app
from modules.transaction_monitoring.feature_engineering import ContextFeatures
from modules.transaction_monitoring.rules import evaluate_rules

client = TestClient(app)


def _features(**overrides) -> ContextFeatures:
    base = dict(
        amount=10_000,
        hour=14,
        day_of_week=2,
        day_of_month=14,
        is_payday_window=False,
        account_age_days=400,
        has_history=True,
        sender_avg_amount_30d=12_000,
        amount_to_avg_ratio=10_000 / 12_000,
        is_known_receiver=True,
        tx_count_last_10min=0,
        tx_count_last_1h=0,
        sum_amount_last_1h=0,
        distinct_receivers_last_1h=0,
        kyc_level="standard",
        transaction_type="transfer",
        channel="mobile_app",
    )
    base.update(overrides)
    return ContextFeatures(**base)


def test_rules_do_not_trigger_on_normal_transaction():
    results = evaluate_rules(_features())
    assert all(not r.triggered for r in results)


def test_amount_spike_rule_triggers():
    features = _features(
        amount=150_000,
        amount_to_avg_ratio=150_000 / 12_000,
        is_known_receiver=False,
    )
    results = evaluate_rules(features)
    triggered_codes = {r.code for r in results if r.triggered}
    assert "AMOUNT_SPIKE" in triggered_codes
    assert "UNKNOWN_RECEIVER_HIGH_AMOUNT" in triggered_codes


def test_structuring_rule_triggers_under_ceiling_with_velocity():
    features = _features(
        amount=480_000,
        tx_count_last_1h=5,
        sum_amount_last_1h=1_900_000,
        sender_avg_amount_30d=0,
        has_history=False,
        amount_to_avg_ratio=0,
    )
    results = evaluate_rules(features)
    triggered_codes = {r.code for r in results if r.triggered}
    assert "STRUCTURING_SUSPECTED" in triggered_codes


def test_decision_thresholds():
    assert decide(10)[0] == "ALLOW"
    assert decide(45)[0] == "MONITOR"
    assert decide(70)[0] == "REVIEW"
    assert decide(90)[0] == "TEMPORARY_BLOCK"


def test_critical_rule_floor_is_not_diluted_by_low_ml_score():
    # rule_score déjà >= au plancher critique (80) : le score final ne doit jamais
    # redescendre en dessous même si le ML est très bas.
    final_score = aggregate_final_score(rule_score=95, ml_score=2)
    assert final_score >= 80


def test_analyze_normal_transaction_is_low_risk():
    payload = {
        "sender_phone": "+225010000001",
        "receiver_phone": "+225010000002",
        "amount": 15000,
        "transaction_type": "transfer",
        "channel": "mobile_app",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    response = client.post("/api/v1/transactions/analyze", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] in {"ALLOW", "MONITOR"}
    assert 0 <= body["final_score"] <= 100


def test_analyze_suspicious_transaction_is_flagged():
    payload = {
        "sender_phone": "+225020000099",
        "receiver_phone": "+225099999999",
        "amount": 950000,
        "transaction_type": "transfer",
        "channel": "web",
        "timestamp": datetime.now(timezone.utc).replace(hour=2, minute=30).isoformat(),
    }
    response = client.post("/api/v1/transactions/analyze", json=payload)
    assert response.status_code == 200
    body = response.json()
    # nouveau client (créé à la volée) + montant très élevé + bénéficiaire inconnu + nuit
    assert body["decision"] in {"REVIEW", "TEMPORARY_BLOCK"}
    assert body["final_score"] > 60
    assert len(body["reasons"]) > 0


def test_get_transaction_after_analysis():
    payload = {
        "sender_phone": "+225030000001",
        "receiver_phone": "+225030000002",
        "amount": 5000,
        "transaction_type": "airtime_purchase",
        "channel": "ussd",
    }
    created = client.post("/api/v1/transactions/analyze", json=payload).json()
    fetched = client.get(f"/api/v1/transactions/{created['transaction_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["transaction_id"] == created["transaction_id"]
