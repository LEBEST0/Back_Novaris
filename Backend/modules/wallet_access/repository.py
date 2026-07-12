from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.wallet_access.models import (
    Beneficiary,
    BehaviourProfile,
    DemoScenario,
    Device,
    SecurityEvent,
    WalletSession,
    WalletTransaction,
    WalletUser,
)
from shared.utils.id_generator import (
    generate_beneficiary_id,
    generate_device_id,
    generate_event_id,
    generate_session_id,
    generate_user_id,
    generate_wallet_transaction_id,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WalletAccessRepository:
    def __init__(self, db: Session):
        self.db = db

    # --- Users -------------------------------------------------------
    def get_user_by_phone(self, phone: str) -> WalletUser | None:
        return self.db.scalar(select(WalletUser).where(WalletUser.phone == phone))

    def get_user(self, user_id: str) -> WalletUser | None:
        return self.db.get(WalletUser, user_id)

    def get_user_by_wallet_number(self, wallet_number: str) -> WalletUser | None:
        return self.db.scalar(select(WalletUser).where(WalletUser.wallet_number == wallet_number))

    def create_user(
        self,
        *,
        full_name: str,
        phone: str,
        pin_hash: str,
        wallet_number: str,
        home_latitude: float | None,
        home_longitude: float | None,
    ) -> WalletUser:
        user = WalletUser(
            id=generate_user_id(),
            full_name=full_name,
            phone=phone,
            pin_hash=pin_hash,
            wallet_number=wallet_number,
            balance=0.0,
            kyc_status="pending",
            home_latitude=home_latitude,
            home_longitude=home_longitude,
        )
        self.db.add(user)
        self.db.flush()
        return user

    # --- Devices -------------------------------------------------------
    def get_device_by_fingerprint(self, user_id: str, fingerprint: str) -> Device | None:
        return self.db.scalar(
            select(Device).where(Device.user_id == user_id).where(Device.device_fingerprint == fingerprint)
        )

    def get_device_by_id(self, device_id: str) -> Device | None:
        return self.db.get(Device, device_id)

    def get_primary_device(self, user_id: str) -> Device | None:
        return self.db.scalar(
            select(Device)
            .where(Device.user_id == user_id)
            .where(Device.trusted.is_(True))
            .order_by(Device.first_seen_at.asc())
            .limit(1)
        )

    def get_trusted_device_by_android_id(self, user_id: str, android_id_mock: str) -> Device | None:
        return self.db.scalar(
            select(Device)
            .where(Device.user_id == user_id)
            .where(Device.android_id_mock == android_id_mock)
            .where(Device.trusted.is_(True))
        )

    def register_device(self, *, user_id: str, payload, android_id_mock: str | None, trusted: bool) -> Device:
        device = Device(
            id=generate_device_id(),
            user_id=user_id,
            local_device_uuid=payload.local_device_uuid,
            device_fingerprint=payload.device_fingerprint,
            platform=payload.platform,
            os_version=payload.os_version,
            browser=payload.browser,
            screen_size=f"{payload.screen_width}x{payload.screen_height}" if payload.screen_width else "unknown",
            language=payload.language,
            timezone=payload.timezone,
            android_id_mock=android_id_mock,
            trusted=trusted,
        )
        self.db.add(device)
        self.db.flush()
        return device

    def touch_device(self, device: Device) -> None:
        device.last_seen_at = _utcnow()
        self.db.flush()

    def trust_device(self, device: Device) -> None:
        device.trusted = True
        self.db.flush()

    # --- Sessions -------------------------------------------------------
    def create_session(self, *, user_id: str, device_id: str | None) -> WalletSession:
        session = WalletSession(
            id=generate_session_id(),
            user_id=user_id,
            device_id=device_id,
            current_status="PENDING",
            risk_level="LOW",
            pipeline_state={},
        )
        self.db.add(session)
        self.db.flush()
        return session

    def get_session(self, session_id: str) -> WalletSession | None:
        return self.db.get(WalletSession, session_id)

    def get_last_session_with_location(self, user_id: str, *, before: str) -> WalletSession | None:
        return self.db.scalar(
            select(WalletSession)
            .where(WalletSession.user_id == user_id)
            .where(WalletSession.id != before)
            .where(WalletSession.latitude.is_not(None))
            .order_by(WalletSession.started_at.desc())
            .limit(1)
        )

    def get_latest_session(self, user_id: str) -> WalletSession | None:
        return self.db.scalar(
            select(WalletSession)
            .where(WalletSession.user_id == user_id)
            .order_by(WalletSession.started_at.desc())
            .limit(1)
        )

    def update_session(self, session: WalletSession, **fields) -> WalletSession:
        for key, value in fields.items():
            setattr(session, key, value)
        self.db.flush()
        return session

    # --- Behaviour -------------------------------------------------------
    def get_behaviour_profile(self, user_id: str) -> BehaviourProfile | None:
        return self.db.scalar(select(BehaviourProfile).where(BehaviourProfile.user_id == user_id))

    def upsert_behaviour_profile(self, user_id: str, *, login_duration_ms: int | None, pin_entry_duration_ms: int | None, failed_attempts: int) -> BehaviourProfile:
        profile = self.get_behaviour_profile(user_id)
        if profile is None:
            # Champs numériques initialisés explicitement : les defaults SQLAlchemy ne
            # sont appliqués qu'au flush/INSERT, pas à la construction de l'objet Python.
            profile = BehaviourProfile(
                user_id=user_id,
                average_login_duration=0.0,
                average_pin_entry_duration=0.0,
                average_navigation_time=0.0,
                failed_attempt_average=0.0,
                sample_count=0,
            )
            self.db.add(profile)

        n = profile.sample_count
        def _running_average(current: float, new_value: float | None) -> float:
            if new_value is None:
                return current
            return (current * n + new_value) / (n + 1)

        profile.average_login_duration = _running_average(profile.average_login_duration, login_duration_ms)
        profile.average_pin_entry_duration = _running_average(profile.average_pin_entry_duration, pin_entry_duration_ms)
        profile.failed_attempt_average = _running_average(profile.failed_attempt_average, failed_attempts)
        profile.sample_count = n + 1
        profile.updated_at = _utcnow()
        self.db.flush()
        return profile

    # --- Beneficiaries -------------------------------------------------------
    def list_beneficiaries(self, user_id: str) -> list[Beneficiary]:
        return list(
            self.db.scalars(
                select(Beneficiary).where(Beneficiary.user_id == user_id).order_by(Beneficiary.added_at.desc())
            )
        )

    def get_beneficiary(self, beneficiary_id: str) -> Beneficiary | None:
        return self.db.get(Beneficiary, beneficiary_id)

    def create_beneficiary(self, *, user_id: str, full_name: str, phone: str, wallet_number: str) -> Beneficiary:
        beneficiary = Beneficiary(
            id=generate_beneficiary_id(),
            user_id=user_id,
            full_name=full_name,
            phone=phone,
            wallet_number=wallet_number,
            status="nouveau",
        )
        self.db.add(beneficiary)
        self.db.flush()
        return beneficiary

    # --- Transactions (fictives côté wallet, notées à partir de la vraie analyse
    # transaction_monitoring — cf. WalletAccessService.confirm_transfer) -------------------
    def create_wallet_transaction(
        self, *, user_id: str, beneficiary_id: str | None, amount: float, type_: str, status: str
    ) -> WalletTransaction:
        transaction = WalletTransaction(
            id=generate_wallet_transaction_id(),
            user_id=user_id,
            beneficiary_id=beneficiary_id,
            amount=amount,
            type=type_,
            status=status,
        )
        self.db.add(transaction)
        self.db.flush()
        return transaction

    def list_transactions(self, user_id: str, limit: int = 50) -> list[WalletTransaction]:
        return list(
            self.db.scalars(
                select(WalletTransaction)
                .where(WalletTransaction.user_id == user_id)
                .order_by(WalletTransaction.created_at.desc())
                .limit(limit)
            )
        )

    # --- Security events -------------------------------------------------------
    def log_event(self, *, event_type: str, user_id: str | None, session_id: str | None, payload: dict, response_status: str | None) -> SecurityEvent:
        event = SecurityEvent(
            event_id=generate_event_id(),
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            payload=payload,
            response_status=response_status,
        )
        self.db.add(event)
        self.db.flush()
        return event

    # --- Demo scenarios -------------------------------------------------------
    def list_demo_scenarios(self) -> list[DemoScenario]:
        return list(self.db.scalars(select(DemoScenario).where(DemoScenario.active.is_(True))))

    def get_demo_scenario(self, name: str) -> DemoScenario | None:
        return self.db.scalar(select(DemoScenario).where(DemoScenario.name == name))
