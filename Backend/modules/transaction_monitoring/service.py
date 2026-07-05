from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.decision_engine import aggregate_final_score, compute_confidence, decide
from modules.transaction_monitoring import ml, rules
from modules.transaction_monitoring.feature_engineering import compute_context_features
from modules.transaction_monitoring.repository import TransactionRepository
from modules.transaction_monitoring.schemas import TransactionAnalysisOut, TransactionIn, RuleFlagOut


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

        features = compute_context_features(
            amount=payload.amount,
            receiver_phone=payload.receiver_phone,
            timestamp=timestamp,
            transaction_type=payload.transaction_type,
            channel=payload.channel,
            account_created_at=sender.account_created_at,
            kyc_level=sender.kyc_level,
            prior_history=prior_history,
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

        return TransactionAnalysisOut(
            transaction_id=transaction.transaction_id,
            sender_phone=transaction.sender_phone,
            sender_operator=sender.operator,
            receiver_phone=transaction.receiver_phone,
            amount=transaction.amount,
            currency=transaction.currency,
            transaction_type=transaction.transaction_type,
            rule_score=rule_score,
            ml_score=ml_score,
            final_score=final_score,
            risk_level=risk_level,
            decision=decision,
            confidence=confidence,
            reasons=reasons,
            rule_flags=[RuleFlagOut(code=r.code, description=r.description, weight=r.weight) for r in triggered_flags],
            top_ml_factors=top_ml_factors,
            model_version=transaction.analysis.model_version,
            computed_at=transaction.analysis.computed_at,
        )
