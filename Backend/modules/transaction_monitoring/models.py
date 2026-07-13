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
    # Identifiant de pièce d'identité (KYC), renseigné uniquement pour kyc_level != "basic"
    # (KYC basique = numéro vérifié par SMS seulement, pas de pièce d'identité collectée).
    # Deux comptes (numéros de téléphone/opérateurs différents, potentiellement dans des
    # pays différents de l'écosystème Clapay) qui partagent ce même national_id désignent
    # la même personne physique — c'est la clé de résolution d'identité inter-réseaux :
    # le numéro de téléphone seul ne suffit pas (cf. discussion produit sur le graphe).
    national_id: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    customer_type: Mapped[str] = mapped_column(String(20), default="individual")
    operator: Mapped[str] = mapped_column(String(30), default="Autre / inconnu")
    country: Mapped[str] = mapped_column(String(40), default="Côte d'Ivoire")
    home_city: Mapped[str] = mapped_column(String(60), default="Abidjan")
    account_created_at: Mapped[datetime] = mapped_column(DateTime())

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="sender")


class Transaction(Base):
    """Transaction Mobile Money brute reçue par le canal d'entrée (app ou agence)."""

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
    agent_id: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    # Solde du portefeuille de l'émetteur avant/après la transaction, si le système
    # appelant (Clapay) les transmet — signal fortement prédictif documenté par les
    # travaux de référence sur la simulation Mobile Money (PaySim, MoMTSim) : une
    # transaction qui vide le compte à zéro est un indice fort de fraude/compte compromis.
    # Optionnel : Novaris ne gère pas les soldes, il ne fait que les recevoir s'ils existent.
    balance_before_sender: Mapped[float | None] = mapped_column(Float, nullable=True)
    balance_after_sender: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), index=True, default=_utcnow)

    sender: Mapped["Customer"] = relationship(back_populates="transactions")
    analysis: Mapped["TransactionAnalysis"] = relationship(
        back_populates="transaction", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_sender_created_at", "sender_phone", "created_at"),
        Index("ix_agent_created_at", "agent_id", "created_at"),
    )


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

    # Retour analyste (dashboard admin) : boucle de contrôle humain, pas encore réinjectée
    # dans l'entraînement mais déjà utile pour mesurer la precision perçue en production.
    analyst_feedback: Mapped[str | None] = mapped_column(String(20), nullable=True)
    feedback_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    transaction: Mapped["Transaction"] = relationship(back_populates="analysis")
