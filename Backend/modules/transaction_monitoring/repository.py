from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.transaction_monitoring.feature_engineering import HistoryEntry
from modules.transaction_monitoring.models import Customer, Transaction, TransactionAnalysis
from shared.utils.id_generator import generate_customer_id, generate_transaction_id
from shared.utils.phone import operator_from_phone

# On ne remonte jamais plus de 30 jours d'historique : c'est la fenêtre la plus large
# utilisée par les règles/features (moyenne 30j), inutile de charger plus.
HISTORY_WINDOW_DAYS = 30


class TransactionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_customer_by_phone(self, phone: str) -> Customer | None:
        return self.db.scalar(select(Customer).where(Customer.phone == phone))

    def get_or_create_customer(self, phone: str, *, now: datetime) -> Customer:
        customer = self.get_customer_by_phone(phone)
        if customer:
            return customer
        customer = Customer(
            customer_id=generate_customer_id(),
            phone=phone,
            full_name="Client inconnu",
            kyc_level="basic",
            customer_type="individual",
            operator=operator_from_phone(phone),
            home_city="Abidjan",
            account_created_at=now,
        )
        self.db.add(customer)
        self.db.flush()
        return customer

    def get_sender_history(self, sender_phone: str, *, before: datetime) -> list[HistoryEntry]:
        window_start = before - timedelta(days=HISTORY_WINDOW_DAYS)
        rows = self.db.scalars(
            select(Transaction)
            .where(Transaction.sender_phone == sender_phone)
            .where(Transaction.created_at >= window_start)
            .where(Transaction.created_at < before)
        ).all()
        return [
            HistoryEntry(receiver_phone=r.receiver_phone, amount=r.amount, created_at=r.created_at)
            for r in rows
        ]

    def save_transaction_with_analysis(
        self,
        *,
        sender: Customer,
        payload,
        timestamp: datetime,
        rule_score: float,
        ml_score: float,
        final_score: float,
        risk_level: str,
        decision: str,
        confidence: float,
        reasons: list[str],
        rule_flags: list[dict],
        top_ml_factors: list[str],
        model_version: str,
    ) -> Transaction:
        transaction = Transaction(
            transaction_id=generate_transaction_id(),
            sender_phone=sender.phone,
            receiver_phone=payload.receiver_phone,
            amount=payload.amount,
            currency=payload.currency,
            transaction_type=payload.transaction_type,
            channel=payload.channel,
            device_id=payload.device_id,
            sender_city=payload.sender_city,
            note=payload.note,
            created_at=timestamp,
        )
        self.db.add(transaction)
        self.db.flush()

        analysis = TransactionAnalysis(
            transaction_id=transaction.transaction_id,
            rule_score=rule_score,
            ml_score=ml_score,
            final_score=final_score,
            risk_level=risk_level,
            decision=decision,
            confidence=confidence,
            reasons=reasons,
            rule_flags=rule_flags,
            top_ml_factors=top_ml_factors,
            model_version=model_version,
            computed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(transaction)
        return transaction

    def get_transaction(self, transaction_id: str) -> Transaction | None:
        return self.db.scalar(
            select(Transaction).where(Transaction.transaction_id == transaction_id)
        )

    def list_transactions(self, limit: int = 50, offset: int = 0) -> list[Transaction]:
        return list(
            self.db.scalars(
                select(Transaction)
                .order_by(Transaction.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
