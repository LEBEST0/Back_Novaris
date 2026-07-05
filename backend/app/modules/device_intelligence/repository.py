from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.modules.device_intelligence.models import DeviceRequestNonce, DeviceStatus, UserDeviceFingerprint
from backend.app.modules.device_intelligence.schemas import DeviceAnalyzeRequest, DeviceMetadataInput


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _upsert_device(
    db: Session,
    device: DeviceMetadataInput,
    device_hash: str,
    status: str,
) -> UserDeviceFingerprint:
    record = db.scalar(
        select(UserDeviceFingerprint).where(
            UserDeviceFingerprint.user_id == device.user_id,
            UserDeviceFingerprint.device_id == device.device_id,
        )
    )
    if record is None:
        record = UserDeviceFingerprint(
            user_id=device.user_id,
            device_id=device.device_id,
            device_hash=device_hash,
            brand=device.brand,
            model=device.model,
            os_name=device.os_name,
            os_version=device.os_version,
            ip_address=device.ip_address,
            country=device.country,
            city=device.city,
            status=status,
            first_seen_at=_utcnow(),
            last_used_at=_utcnow(),
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(record)
    else:
        record.device_hash = device_hash
        record.brand = device.brand
        record.model = device.model
        record.os_name = device.os_name
        record.os_version = device.os_version
        record.ip_address = device.ip_address
        record.country = device.country
        record.city = device.city
        record.status = status
        record.last_used_at = _utcnow()
        record.updated_at = _utcnow()
    db.commit()
    db.refresh(record)
    return record


def enroll_device(db: Session, device: DeviceMetadataInput, device_hash: str, status: str = DeviceStatus.TRUSTED.value) -> UserDeviceFingerprint:
    return _upsert_device(db, device, device_hash, status)


def get_user_devices(db: Session, user_id: str) -> list[UserDeviceFingerprint]:
    stmt = select(UserDeviceFingerprint).where(UserDeviceFingerprint.user_id == user_id).order_by(desc(UserDeviceFingerprint.last_used_at))
    return list(db.scalars(stmt).all())


def get_latest_trusted_device(db: Session, user_id: str) -> UserDeviceFingerprint | None:
    stmt = (
        select(UserDeviceFingerprint)
        .where(
            UserDeviceFingerprint.user_id == user_id,
            UserDeviceFingerprint.status == DeviceStatus.TRUSTED.value,
        )
        .order_by(desc(UserDeviceFingerprint.last_used_at))
    )
    return db.scalar(stmt)


def update_last_used(db: Session, user_id: str, device_id: str) -> UserDeviceFingerprint | None:
    record = db.scalar(
        select(UserDeviceFingerprint).where(
            UserDeviceFingerprint.user_id == user_id,
            UserDeviceFingerprint.device_id == device_id,
        )
    )
    if record is None:
        return None
    record.last_used_at = _utcnow()
    record.updated_at = _utcnow()
    db.commit()
    db.refresh(record)
    return record


def mark_device_suspicious(
    db: Session,
    device: DeviceMetadataInput,
    device_hash: str,
) -> UserDeviceFingerprint:
    return _upsert_device(db, device, device_hash, DeviceStatus.SUSPICIOUS.value)


def mark_device_blocked(
    db: Session,
    device: DeviceMetadataInput,
    device_hash: str,
) -> UserDeviceFingerprint:
    return _upsert_device(db, device, device_hash, DeviceStatus.BLOCKED.value)


def register_request_nonce(db: Session, payload: DeviceAnalyzeRequest) -> bool:
    record = DeviceRequestNonce(
        user_id=payload.user_id,
        request_id=payload.request_id,
        nonce=payload.nonce,
        request_timestamp=payload.timestamp,
        created_at=_utcnow(),
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True
