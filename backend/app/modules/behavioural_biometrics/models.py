from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.shared.database.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BehaviouralActionType(str, enum.Enum):
    LOGIN = "LOGIN"
    PIN_ENTRY = "PIN_ENTRY"
    TRANSACTION_CONFIRMATION = "TRANSACTION_CONFIRMATION"
    PASSWORD_CHANGE = "PASSWORD_CHANGE"
    BENEFICIARY_ADD = "BENEFICIARY_ADD"


class BehaviouralProfile(Base):
    __tablename__ = "behavioural_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_behavioural_profiles_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    samples_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    baseline_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    samples: Mapped[list["BehaviouralSample"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def baseline(self) -> dict[str, Any]:
        return self.baseline_data or {}

    @baseline.setter
    def baseline(self, value: dict[str, Any]) -> None:
        self.baseline_data = value or {}


class BehaviouralSample(Base):
    __tablename__ = "behavioural_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("behavioural_profiles.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    avg_key_interval_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_touch_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    typing_speed_cps: Mapped[float | None] = mapped_column(Float, nullable=True)
    tap_pressure_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    tap_pressure_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correction_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hesitation_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    swipe_speed_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    touch_precision_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    device_orientation_changes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    profile: Mapped[BehaviouralProfile] = relationship(back_populates="samples")


class BehaviouralRequestNonce(Base):
    __tablename__ = "behavioural_request_nonces"
    __table_args__ = (UniqueConstraint("nonce", name="uq_behavioural_request_nonce"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nonce: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
