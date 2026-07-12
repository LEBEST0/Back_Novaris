from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.decision_engine import aggregate_final_score, compute_confidence, decide
from modules.transaction_monitoring import ml, rules
from modules.transaction_monitoring.feature_engineering import compute_context_features
from modules.transaction_monitoring.models import Customer
from modules.transaction_monitoring.presenters import transaction_to_analysis_out
from modules.transaction_monitoring.repository import TransactionRepository
from modules.transaction_monitoring.schemas import (
    NetworkEdgeOut,
    NetworkGraphOut,
    NetworkNodeOut,
    TransactionAnalysisOut,
    TransactionIn,
)
from shared.utils.phone import country_from_phone, currency_for_country

RISK_ORDER = ["low", "moderate", "high", "critical"]
FLAGGED_DECISIONS = {"REVIEW", "TEMPORARY_BLOCK"}


class TransactionMonitoringService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TransactionRepository(db)

    def analyze(self, payload: TransactionIn) -> TransactionAnalysisOut:
        timestamp = payload.timestamp or datetime.now(timezone.utc)
        # Normalisé en UTC naïf : SQLite ne conserve pas le fuseau horaire des valeurs
        # stockées, donc l'historique relu de la base est toujours naïf. Comparer un
        # timestamp tz-aware à un naïf lève une TypeError (cf. feature_engineering).
        if timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)

        sender = self.repo.get_or_create_customer(payload.sender_phone, now=timestamp)
        prior_history = self.repo.get_sender_history(payload.sender_phone, before=timestamp)
        incoming_history = self.repo.get_receiver_history(payload.sender_phone, before=timestamp)

        receiver_country = country_from_phone(payload.receiver_phone)
        if payload.currency is None:
            payload.currency = currency_for_country(sender.country)

        agent_tx_count_last_1h = 0
        agent_distinct_senders_last_1h = 0
        if payload.agent_id:
            agent_tx_count_last_1h, agent_distinct_senders_last_1h = self.repo.get_agent_recent_activity(
                payload.agent_id, before=timestamp
            )

        features = compute_context_features(
            amount=payload.amount,
            receiver_phone=payload.receiver_phone,
            timestamp=timestamp,
            transaction_type=payload.transaction_type,
            channel=payload.channel,
            currency=payload.currency,
            account_created_at=sender.account_created_at,
            kyc_level=sender.kyc_level,
            prior_history=prior_history,
            sender_country=sender.country,
            receiver_country=receiver_country,
            batch_id=payload.batch_id,
            incoming_history=incoming_history,
            device_id=payload.device_id,
            balance_after_sender=payload.balance_after_sender,
            agent_tx_count_last_1h=agent_tx_count_last_1h,
            agent_distinct_senders_last_1h=agent_distinct_senders_last_1h,
            behaviour_time_to_complete_ms=payload.behaviour_time_to_complete_ms,
            behaviour_amount_field_edits=payload.behaviour_amount_field_edits,
        )

        rule_results = rules.evaluate_rules(features)
        rule_score = rules.aggregate_rule_score(rule_results)

        model_bundle = ml.get_model_bundle()
        ml_score, top_ml_factors = model_bundle.predict(features)

        final_score = aggregate_final_score(rule_score, ml_score)
        confidence = compute_confidence(rule_score, ml_score)
        decision, risk_level = decide(final_score)

        triggered_flags = [r for r in rule_results if r.triggered]
        reasons = [r.description for r in triggered_flags] + [
            f"Signal ML : {factor}" for factor in top_ml_factors
        ]
        if not reasons:
            reasons = ["Aucun facteur de risque significatif détecté."]

        transaction = self.repo.save_transaction_with_analysis(
            sender=sender,
            payload=payload,
            timestamp=timestamp,
            rule_score=rule_score,
            ml_score=ml_score,
            final_score=final_score,
            risk_level=risk_level,
            decision=decision,
            confidence=confidence,
            reasons=reasons,
            rule_flags=[
                {"code": r.code, "description": r.description, "weight": r.weight}
                for r in triggered_flags
            ],
            top_ml_factors=top_ml_factors,
            model_version=model_bundle.metadata.get("model_version", "unknown"),
        )

        return transaction_to_analysis_out(transaction, self.db)

    def build_network_graph(self, limit: int = 500) -> NetworkGraphOut:
        """Graphe réseau complet — toutes les transactions récentes, pas une seule. Un
        client avec KYC complet est identifié par son national_id (résolution d'identité
        inter-réseaux) : deux comptes qui le partagent fusionnent naturellement en un seul
        nœud, même sur des opérateurs/pays différents."""
        transactions = self.repo.list_transactions_for_network(limit=limit)
        truncated = len(transactions) >= limit

        receiver_phones = {t.receiver_phone for t in transactions}
        receiver_customers = self.repo.get_customers_by_phones(receiver_phones)

        def identity_key(phone: str, customer: Customer | None) -> tuple[str, str, bool]:
            if customer and customer.national_id:
                return customer.national_id, customer.national_id, True
            return phone, phone, False

        nodes: dict[str, NetworkNodeOut] = {}
        edges: list[NetworkEdgeOut] = []

        def upsert_node(
            key: str, label: str, type_: str, *, identity_verified: bool = False,
            country: str | None = None, risk_level: str = "low", flagged: bool = False,
        ) -> None:
            node = nodes.get(key)
            if node is None:
                nodes[key] = NetworkNodeOut(
                    id=key, label=label, type=type_, identity_verified=identity_verified,
                    country=country, transaction_count=1, max_risk_level=risk_level, flagged=flagged,
                )
                return
            node.transaction_count += 1
            if RISK_ORDER.index(risk_level) > RISK_ORDER.index(node.max_risk_level):
                node.max_risk_level = risk_level
            node.flagged = node.flagged or flagged

        for t in transactions:
            analysis = t.analysis
            if analysis is None:
                continue
            flagged = analysis.decision in FLAGGED_DECISIONS

            sender_key, sender_label, sender_verified = identity_key(t.sender_phone, t.sender)
            receiver_customer = receiver_customers.get(t.receiver_phone)
            receiver_key, receiver_label, receiver_verified = identity_key(t.receiver_phone, receiver_customer)

            upsert_node(
                sender_key, sender_label, "customer", identity_verified=sender_verified,
                country=t.sender.country, risk_level=analysis.risk_level, flagged=flagged,
            )
            upsert_node(
                receiver_key, receiver_label, "customer", identity_verified=receiver_verified,
                country=country_from_phone(t.receiver_phone), risk_level=analysis.risk_level, flagged=flagged,
            )
            edges.append(NetworkEdgeOut(
                id=f"edge-{t.transaction_id}",
                source=sender_key,
                target=receiver_key,
                kind="transaction",
                transaction_id=t.transaction_id,
                amount=t.amount,
                currency=t.currency,
                transaction_type=t.transaction_type,
                decision=analysis.decision,
                risk_level=analysis.risk_level,
                created_at=t.created_at.isoformat(),
            ))

            if t.agent_id:
                agent_key = f"agent:{t.agent_id}"
                upsert_node(agent_key, t.agent_id, "agent", risk_level=analysis.risk_level if flagged else "low", flagged=flagged)
                edges.append(NetworkEdgeOut(
                    id=f"edge-{t.transaction_id}-agent", source=sender_key, target=agent_key,
                    kind="agent", transaction_id=t.transaction_id,
                ))

            if t.device_id:
                device_key = f"device:{t.device_id[:16]}"
                upsert_node(device_key, f"{t.device_id[:10]}…", "device", risk_level=analysis.risk_level if flagged else "low", flagged=flagged)
                edges.append(NetworkEdgeOut(
                    id=f"edge-{t.transaction_id}-device", source=sender_key, target=device_key,
                    kind="device", transaction_id=t.transaction_id,
                ))

        return NetworkGraphOut(nodes=list(nodes.values()), edges=edges, truncated=truncated)
