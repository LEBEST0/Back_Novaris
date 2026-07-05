from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.database import Base


def _utcnow() -> datetime:
    # Naïf (sans tzinfo) volontairement : SQLite ne conserve pas le fuseau horaire des
    # datetimes stockés, il faut donc rester cohérent en UTC naïf partout (stockage,
    # feature engineering, comparaisons) pour éviter les erreurs offset-naive/aware.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Customer(Base):
    """Titulaire de portefeuille Mobile Money suivi par Novaris (l'émetteur des transactions)."""

    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    kyc_level: Mapped[str] = mapped_column(String(20), default="basic")
    customer_type: Mapped[str] = mapped_column(String(20), default="individual")
    operator: Mapped[str] = mapped_column(String(30), default="Autre / inconnu")
    home_city: Mapped[str] = mapped_column(String(60), default="Abidjan")
    account_created_at: Mapped[datetime] = mapped_column(DateTime())

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="sender")


class Transaction(Base):
    """Transaction Mobile Money brute reçue par le canal d'entrée (API, app, agent, USSD)."""

    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    sender_phone: Mapped[str] = mapped_column(
        String(20), ForeignKey("customers.phone"), index=True
    )
    receiver_phone: Mapped[str] = mapped_column(String(20), index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(6), default="XOF")
    transaction_type: Mapped[str] = mapped_column(String(30), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="mobile_app")
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sender_city: Mapped[str | None] = mapped_column(String(60), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), index=True, default=_utcnow)

    sender: Mapped["Customer"] = relationship(back_populates="transactions")
    analysis: Mapped["TransactionAnalysis"] = relationship(
        back_populates="transaction", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_sender_created_at", "sender_phone", "created_at"),)


class TransactionAnalysis(Base):
    """Résultat de l'analyse hybride (règles + ML) pour une transaction donnée."""

    __tablename__ = "transaction_analyses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("transactions.transaction_id"), unique=True, index=True
    )
    rule_score: Mapped[float] = mapped_column(Float)
    ml_score: Mapped[float] = mapped_column(Float)
    final_score: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(20))
    decision: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list] = mapped_column(JSON)
    rule_flags: Mapped[list] = mapped_column(JSON)
    top_ml_factors: Mapped[list] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(40))
    computed_at: Mapped[datetime] = mapped_column(DateTime(), default=_utcnow)

    transaction: Mapped["Transaction"] = relationship(back_populates="analysis")
