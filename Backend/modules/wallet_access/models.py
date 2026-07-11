"""Entités du module wallet_access : identité, appareils, sessions et sécurité côté
client (Amani Wallet) — distinct de modules.transaction_monitoring qui, lui, modélise
l'analyse d'une transaction déjà émise. Ici on modélise ce qui se passe AVANT une
transaction : est-ce vraiment le propriétaire du compte qui se connecte ?"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WalletUser(Base):
    __tablename__ = "wallet_users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Jamais le PIN en clair : seul le hash (passlib/bcrypt) est stocké.
    pin_hash: Mapped[str] = mapped_column(String(200))
    wallet_number: Mapped[str] = mapped_column(String(30), unique=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    kyc_status: Mapped[str] = mapped_column(String(20), default="pending")
    # Zone de connexion habituelle — sert au calcul réel de LOCATION_ANOMALY /
    # IMPOSSIBLE_TRAVEL (distance haversine), pas juste un indicateur simulé.
    home_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=_utcnow)

    devices: Mapped[list["Device"]] = relationship(back_populates="user")
    sessions: Mapped[list["WalletSession"]] = relationship(back_populates="user")
    beneficiaries: Mapped[list["Beneficiary"]] = relationship(back_populates="user")
    behaviour_profile: Mapped["BehaviourProfile"] = relationship(
        back_populates="user", uselist=False
    )


class Device(Base):
    """Appareil applicatif — l'empreinte n'est jamais présentée comme une preuve
    matérielle absolue (pas d'IMEI/Android ID réel), cf. shared/utils/device_fingerprint."""

    __tablename__ = "wallet_devices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("wallet_users.id"), index=True)
    local_device_uuid: Mapped[str] = mapped_column(String(64), index=True)
    device_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    platform: Mapped[str] = mapped_column(String(30))
    os_version: Mapped[str] = mapped_column(String(20))
    browser: Mapped[str] = mapped_column(String(60))
    screen_size: Mapped[str] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(10))
    timezone: Mapped[str] = mapped_column(String(60))
    # Android ID *simulé* (Google Identity API mock) — sert uniquement à démontrer la
    # détection de clonage d'identifiant (même android_id, empreinte applicative différente).
    android_id_mock: Mapped[str | None] = mapped_column(String(30), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(), default=_utcnow)
    trusted: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["WalletUser"] = relationship(back_populates="devices")


class WalletSession(Base):
    __tablename__ = "wallet_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("wallet_users.id"), index=True)
    device_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("wallet_devices.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    current_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    risk_level: Mapped[str] = mapped_column(String(20), default="LOW")
    final_decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    # État accumulé au fil des appels successifs à /risk/evaluate-access (device connu,
    # identité vérifiée, OTP validé...) — évite de rejouer tout le pipeline à chaque étape.
    pipeline_state: Mapped[dict] = mapped_column(JSON, default=dict)

    user: Mapped["WalletUser"] = relationship(back_populates="sessions")


class BehaviourProfile(Base):
    __tablename__ = "wallet_behaviour_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("wallet_users.id"), unique=True, index=True)
    average_login_duration: Mapped[float] = mapped_column(Float, default=0.0)
    average_pin_entry_duration: Mapped[float] = mapped_column(Float, default=0.0)
    average_navigation_time: Mapped[float] = mapped_column(Float, default=0.0)
    failed_attempt_average: Mapped[float] = mapped_column(Float, default=0.0)
    sample_count: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), default=_utcnow)

    user: Mapped["WalletUser"] = relationship(back_populates="behaviour_profile")


class Beneficiary(Base):
    __tablename__ = "wallet_beneficiaries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("wallet_users.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    wallet_number: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="nouveau")
    added_at: Mapped[datetime] = mapped_column(DateTime(), default=_utcnow)

    user: Mapped["WalletUser"] = relationship(back_populates="beneficiaries")


class WalletTransaction(Base):
    """Transaction fictive côté wallet (aucun vrai transfert d'argent). Sert uniquement à
    peupler l'écran Historique et à démontrer le lien conceptuel avec
    modules.transaction_monitoring, qui prend le relais pendant une vraie transaction."""

    __tablename__ = "wallet_transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("wallet_users.id"), index=True)
    beneficiary_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("wallet_beneficiaries.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=_utcnow)


class SecurityEvent(Base):
    """Journal brut de tout événement envoyé par Amani Wallet — piste d'audit, jamais
    utilisé directement pour décider (la décision vient du risk engine)."""

    __tablename__ = "wallet_security_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    sent_at: Mapped[datetime] = mapped_column(DateTime(), default=_utcnow)
    response_status: Mapped[str | None] = mapped_column(String(20), nullable=True)


class DemoScenario(Base):
    """Catalogue des scénarios du mode démonstration (section 10 du cahier des charges) —
    chaque scénario porte un jeu de signaux mock prêts à injecter dans APP_OPENED."""

    __tablename__ = "wallet_demo_scenarios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(300))
    mock_signals: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
