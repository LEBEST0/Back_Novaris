import random
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from core.decision_engine import aggregate_final_score, decide
from main import app
from modules.transaction_monitoring.feature_engineering import ContextFeatures
from modules.transaction_monitoring.rules import evaluate_rules

client = TestClient(app)


def _unique_ci_phone() -> str:
    # Numéro CI garanti inédit (préfixe Orange 09 + suffixe aléatoire) : la base de dev
    # persiste entre les exécutions de test, un numéro réutilisé ne serait plus "neuf".
    return "+22509" + "".join(str(random.randint(0, 9)) for _ in range(6))


def _features(**overrides) -> ContextFeatures:
    base = dict(
        amount=10_000,
        currency="XOF",
        amount_xof_equivalent=10_000,
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
        is_batch_operation=False,
        batch_size_so_far=0,
        batch_unknown_receiver_ratio=0.0,
        is_cross_border=False,
        minutes_since_last_incoming=999_999.0,
        incoming_amount_ratio=0.0,
        is_cross_border_passthrough=False,
        is_new_device=False,
        is_balance_drained=False,
        agent_tx_count_last_1h=0,
        agent_distinct_senders_last_1h=0,
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
        amount_xof_equivalent=150_000,
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
        amount_xof_equivalent=480_000,
        tx_count_last_1h=5,
        sum_amount_last_1h=1_900_000,
        sender_avg_amount_30d=0,
        has_history=False,
        amount_to_avg_ratio=0,
    )
    results = evaluate_rules(features)
    triggered_codes = {r.code for r in results if r.triggered}
    assert "STRUCTURING_SUSPECTED" in triggered_codes


def test_fanout_ignores_transactions_from_the_same_batch():
    # 5 bénéficiaires distincts en 1h mais tous dans le même lot déclaré -> pas de fanout
    features = _features(distinct_receivers_last_1h=0, is_batch_operation=True)
    results = evaluate_rules(features)
    assert not any(r.code == "FANOUT_PATTERN" and r.triggered for r in results)


def test_fanout_triggers_outside_a_batch():
    features = _features(distinct_receivers_last_1h=5, is_batch_operation=False)
    results = evaluate_rules(features)
    assert any(r.code == "FANOUT_PATTERN" and r.triggered for r in results)


def test_cross_border_passthrough_rule_triggers():
    features = _features(is_cross_border_passthrough=True)
    results = evaluate_rules(features)
    assert any(r.code == "CROSS_BORDER_PASSTHROUGH" and r.triggered for r in results)


def test_amount_thresholds_are_currency_normalized():
    # 100 000 NGN équivalent XOF (~0.41 XOF/NGN) est sous le seuil "montant élevé" en XOF,
    # même si le nombre brut est le même que pour un seuil déclenché en XOF pur.
    features = _features(
        amount=100_000,
        currency="NGN",
        amount_xof_equivalent=100_000 * 0.41,
        is_known_receiver=False,
    )
    results = evaluate_rules(features)
    assert not any(r.code == "UNKNOWN_RECEIVER_HIGH_AMOUNT" and r.triggered for r in results)


def test_suspicious_batch_triggers_on_mostly_unknown_receivers():
    features = _features(is_batch_operation=True, batch_size_so_far=5, batch_unknown_receiver_ratio=0.9)
    results = evaluate_rules(features)
    assert any(r.code == "SUSPICIOUS_BATCH" and r.triggered for r in results)


def test_suspicious_batch_does_not_trigger_on_legitimate_payroll():
    # Un vrai virement de paie répète généralement les mêmes employés/fournisseurs.
    features = _features(is_batch_operation=True, batch_size_so_far=8, batch_unknown_receiver_ratio=0.1)
    results = evaluate_rules(features)
    assert not any(r.code == "SUSPICIOUS_BATCH" and r.triggered for r in results)


def test_sim_swap_signal_triggers_on_new_device_and_unknown_receiver():
    features = _features(is_new_device=True, has_history=True, is_known_receiver=False)
    results = evaluate_rules(features)
    assert any(r.code == "SIM_SWAP_SIGNAL" and r.triggered for r in results)


def test_sim_swap_signal_does_not_trigger_on_known_device():
    features = _features(is_new_device=False, has_history=True, is_known_receiver=False)
    results = evaluate_rules(features)
    assert not any(r.code == "SIM_SWAP_SIGNAL" and r.triggered for r in results)


def test_social_engineering_signal_triggers_on_isolated_large_transfer():
    features = _features(
        account_age_days=400,
        has_history=True,
        sender_avg_amount_30d=10_000,
        amount=120_000,
        amount_xof_equivalent=120_000,
        amount_to_avg_ratio=12,
        is_known_receiver=False,
        tx_count_last_1h=0,
        channel="mobile_app",
    )
    results = evaluate_rules(features)
    assert any(r.code == "SOCIAL_ENGINEERING_SIGNAL" and r.triggered for r in results)


def test_social_engineering_signal_does_not_trigger_during_a_burst():
    # Une rafale relève plutôt de HIGH_VELOCITY/STRUCTURING, pas de l'ingénierie sociale.
    features = _features(
        account_age_days=400,
        has_history=True,
        sender_avg_amount_30d=10_000,
        amount=120_000,
        amount_xof_equivalent=120_000,
        amount_to_avg_ratio=12,
        is_known_receiver=False,
        tx_count_last_1h=3,
        channel="mobile_app",
    )
    results = evaluate_rules(features)
    assert not any(r.code == "SOCIAL_ENGINEERING_SIGNAL" and r.triggered for r in results)


def test_agent_collusion_cashout_triggers_on_high_volume_diverse_senders():
    features = _features(
        transaction_type="withdrawal",
        agent_tx_count_last_1h=8,
        agent_distinct_senders_last_1h=7,
    )
    results = evaluate_rules(features)
    assert any(r.code == "AGENT_COLLUSION_CASHOUT" and r.triggered for r in results)


def test_account_drained_triggers_on_near_zero_balance():
    features = _features(is_balance_drained=True)
    results = evaluate_rules(features)
    assert any(r.code == "ACCOUNT_DRAINED" and r.triggered for r in results)


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
        "sender_phone": _unique_ci_phone(),
        "receiver_phone": _unique_ci_phone(),
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
        "sender_phone": _unique_ci_phone(),
        "receiver_phone": _unique_ci_phone(),
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


def test_batch_payment_does_not_trigger_fanout_via_api():
    # Un même batch_id envoyé à 5 bénéficiaires distincts en quelques minutes = paiement
    # de masse légitime (Clapay B2B) : ne doit jamais déclencher FANOUT_PATTERN.
    sender = _unique_ci_phone()
    batch_id = f"BATCH-TEST-{random.randint(100000, 999999)}"
    last_body = None
    for i in range(1, 6):
        payload = {
            "sender_phone": sender,
            "receiver_phone": _unique_ci_phone(),
            "amount": 80000,
            "transaction_type": "transfer",
            "channel": "api",
            "batch_id": batch_id,
            "timestamp": f"2026-05-10T09:0{i}:00",
        }
        response = client.post("/api/v1/transactions/analyze", json=payload)
        assert response.status_code == 200
        last_body = response.json()

    flag_codes = {f["code"] for f in last_body["rule_flags"]}
    assert "FANOUT_PATTERN" not in flag_codes
    assert last_body["batch_id"] == batch_id


def test_cross_border_passthrough_detected_via_api():
    victim = _unique_ci_phone()
    incoming_payload = {
        "sender_phone": "+221771234567",
        "receiver_phone": victim,
        "amount": 500000,
        "transaction_type": "transfer",
        "channel": "mobile_app",
        "timestamp": "2026-05-12T14:00:00",
    }
    response = client.post("/api/v1/transactions/analyze", json=incoming_payload)
    assert response.status_code == 200

    outgoing_payload = {
        "sender_phone": victim,
        "receiver_phone": "+2348012345678",
        "amount": 490000,
        "transaction_type": "transfer",
        "channel": "mobile_app",
        "timestamp": "2026-05-12T14:20:00",
    }
    response = client.post("/api/v1/transactions/analyze", json=outgoing_payload)
    assert response.status_code == 200
    body = response.json()

    assert body["is_cross_border"] is True
    flag_codes = {f["code"] for f in body["rule_flags"]}
    assert "CROSS_BORDER_PASSTHROUGH" in flag_codes
    assert body["decision"] == "TEMPORARY_BLOCK"


def test_get_transaction_after_analysis():
    payload = {
        "sender_phone": _unique_ci_phone(),
        "receiver_phone": _unique_ci_phone(),
        "amount": 5000,
        "transaction_type": "airtime_purchase",
        "channel": "ussd",
    }
    created = client.post("/api/v1/transactions/analyze", json=payload).json()
    fetched = client.get(f"/api/v1/transactions/{created['transaction_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["transaction_id"] == created["transaction_id"]
