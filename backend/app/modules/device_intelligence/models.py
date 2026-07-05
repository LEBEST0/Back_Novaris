from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.shared.database.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeviceStatus(str, enum.Enum):
    TRUSTED = "TRUSTED"
    SUSPICIOUS = "SUSPICIOUS"
    BLOCKED = "BLOCKED"


class UserDeviceFingerprint(Base):
    __tablename__ = "user_device_fingerprints"
    __table_args__ = (UniqueConstraint("user_id", "device_id", name="uq_user_device"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    device_hash: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    brand: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    os_name: Mapped[str] = mapped_column(String(32), nullable=False)
    os_version: Mapped[str] = mapped_column(String(32), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=DeviceStatus.TRUSTED.value)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class DeviceRequestNonce(Base):
    __tablename__ = "device_request_nonces"
    __table_args__ = (UniqueConstraint("nonce", name="uq_device_request_nonce"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    nonce: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    request_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
