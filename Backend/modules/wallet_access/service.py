"""Orchestration du contrôle d'accès pré-transaction : device → intégrité → identité →
liveness → SIM → décision finale. L'application ne décide jamais elle-même (cf. Amani
Wallet, section 14) — c'est ce service qui produit `next_action`, et seulement lui."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from modules.transaction_monitoring.schemas import TransactionIn
from modules.transaction_monitoring.service import TransactionMonitoringService
from modules.wallet_access.access_rules import AccessContext, aggregate_score, evaluate_rules
from modules.wallet_access.repository import WalletAccessRepository
from modules.wallet_access.schemas import (
    AccessEventIn,
    AccessEventOut,
    BeneficiaryIn,
    BeneficiaryOut,
    DashboardOut,
    DemoScenarioOut,
    EvaluateAccessIn,
    EvaluateAccessOut,
    HistoryEntryOut,
    LoginIn,
    PipelineStepOut,
    ProfileOut,
    RegisterIn,
    TransferConfirmIn,
    TransferConfirmOut,
    TransferPrepareIn,
    TransferPrepareOut,
)
from shared.utils.geo import haversine_km
from shared.utils.id_generator import generate_wallet_number
from shared.utils.masking import mask_phone, mask_wallet_number
from shared.utils.security import hash_pin, verify_pin

MAX_PLAUSIBLE_TRAVEL_SPEED_KMH = 900.0  # vitesse d'un vol commercial, seuil de "voyage impossible"
LOCATION_ANOMALY_RADIUS_KM = 150.0
# Code de démonstration uniquement — un vrai OTP serait généré et envoyé par SMS/notification.
DEMO_OTP_CODE = "123456"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class InvalidCredentialsError(Exception):
    pass


class PhoneAlreadyRegisteredError(Exception):
    pass


class SessionNotFoundError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class BeneficiaryNotFoundError(Exception):
    pass


class WalletAccessService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = WalletAccessRepository(db)

    # ------------------------------------------------------------------
    # Connexion + pipeline de risque
    # ------------------------------------------------------------------
    def login(self, payload: LoginIn) -> EvaluateAccessOut:
        user = self.repo.get_user_by_phone(payload.phone)
        if user is None or not verify_pin(payload.pin, user.pin_hash):
            raise InvalidCredentialsError()
        return self._run_access_pipeline(user, payload, event_type="LOGIN_ATTEMPT")

    def register(self, payload: RegisterIn) -> EvaluateAccessOut:
        if self.repo.get_user_by_phone(payload.phone) is not None:
            raise PhoneAlreadyRegisteredError()

        user = self.repo.create_user(
            full_name=payload.full_name,
            phone=payload.phone,
            pin_hash=hash_pin(payload.pin),
            wallet_number=self._generate_unique_wallet_number(),
            home_latitude=payload.location.latitude if payload.location else None,
            home_longitude=payload.location.longitude if payload.location else None,
        )
        self.db.commit()
        # Un compte tout juste créé n'a par définition aucun appareil de confiance : la
        # toute première connexion suit exactement le même pipeline qu'un « nouvel
        # appareil » sur un compte existant (vérification d'identité incluse).
        return self._run_access_pipeline(user, payload, event_type="REGISTER_ATTEMPT")

    def _generate_unique_wallet_number(self) -> str:
        for _ in range(20):
            candidate = generate_wallet_number()
            if self.repo.get_user_by_wallet_number(candidate) is None:
                return candidate
        raise RuntimeError("Impossible de générer un numéro de wallet unique")

    def _run_access_pipeline(self, user, payload: LoginIn | RegisterIn, *, event_type: str) -> EvaluateAccessOut:
        demo = payload.demo_signals
        android_id_mock = demo.android_id_mock if demo else None

        device = self.repo.get_device_by_fingerprint(user.id, payload.device.device_fingerprint)
        is_new_device = device is None or not device.trusted
        cloned_device_id = False
        if device is None and android_id_mock:
            spoofed_owner = self.repo.get_trusted_device_by_android_id(user.id, android_id_mock)
            if spoofed_owner is not None:
                cloned_device_id = True

        if device is None:
            device = self.repo.register_device(
                user_id=user.id, payload=payload.device, android_id_mock=android_id_mock, trusted=False
            )
        else:
            self.repo.touch_device(device)

        session = self.repo.create_session(user_id=user.id, device_id=device.id)
        if payload.location and payload.location.latitude is not None:
            self.repo.update_session(session, latitude=payload.location.latitude, longitude=payload.location.longitude)

        location_anomaly, impossible_travel = self._evaluate_location(user, session, payload.location)
        recent_sim_change = self._evaluate_sim(demo)
        behaviour_anomaly = self._evaluate_behaviour(user.id, payload.behaviour)

        ctx = AccessContext(
            is_new_device=is_new_device,
            cloned_device_id=cloned_device_id,
            device_integrity_failed=(demo.device_integrity_mock == "FAILED") if demo else False,
            emulator_detected=demo.emulator_detected_mock if demo else False,
            root_detected=demo.root_detected_mock if demo else False,
            location_anomaly=location_anomaly,
            impossible_travel=impossible_travel,
            recent_sim_change=recent_sim_change,
            biometric_result=None,
            liveness_result=None,
            behaviour_anomaly=behaviour_anomaly,
        )

        result = self._finalize(
            ctx, session=session, user=user, device=device, sensors_available=payload.device.sensors_available, otp_verified=False
        )

        self.repo.update_session(
            session,
            pipeline_state={
                "is_new_device": is_new_device,
                "cloned_device_id": cloned_device_id,
                "device_integrity_failed": ctx.device_integrity_failed,
                "emulator_detected": ctx.emulator_detected,
                "root_detected": ctx.root_detected,
                "location_anomaly": location_anomaly,
                "impossible_travel": impossible_travel,
                "recent_sim_change": recent_sim_change,
                "behaviour_anomaly": behaviour_anomaly,
                "sensors_available": payload.device.sensors_available,
                "device_id": device.id,
            },
        )

        if payload.behaviour is not None:
            self.repo.upsert_behaviour_profile(
                user.id,
                login_duration_ms=payload.behaviour.login_duration_ms,
                pin_entry_duration_ms=payload.behaviour.pin_entry_duration_ms,
                failed_attempts=payload.behaviour.failed_attempts,
            )

        self.repo.log_event(
            event_type=event_type,
            user_id=user.id,
            session_id=session.id,
            payload=payload.model_dump(mode="json"),
            response_status=result.next_action,
        )
        self.db.commit()
        return result

    def evaluate_access(self, payload: EvaluateAccessIn) -> EvaluateAccessOut:
        session = self.repo.get_session(payload.session_id)
        if session is None:
            raise SessionNotFoundError()
        user = self.repo.get_user(session.user_id)
        state = dict(session.pipeline_state or {})

        challenge = payload.challenge_response
        biometric_result = challenge.biometric_result if challenge else None
        liveness_result = challenge.liveness_result if challenge else None

        otp_verified = state.get("otp_verified", False)
        if challenge and challenge.otp_code:
            otp_verified = challenge.otp_code == DEMO_OTP_CODE

        ctx = AccessContext(
            is_new_device=state.get("is_new_device", False),
            cloned_device_id=state.get("cloned_device_id", False),
            device_integrity_failed=state.get("device_integrity_failed", False),
            emulator_detected=state.get("emulator_detected", False),
            root_detected=state.get("root_detected", False),
            location_anomaly=state.get("location_anomaly", False),
            impossible_travel=state.get("impossible_travel", False),
            recent_sim_change=state.get("recent_sim_change", False),
            biometric_result=biometric_result,
            liveness_result=liveness_result,
            behaviour_anomaly=state.get("behaviour_anomaly", False),
        )
        sensors_available = state.get("sensors_available", True)
        device = self.repo.get_device_by_id(state.get("device_id", "")) if state.get("device_id") else None

        result = self._finalize(
            ctx, session=session, user=user, device=device, sensors_available=sensors_available, otp_verified=otp_verified
        )

        state["otp_verified"] = otp_verified
        self.repo.update_session(session, pipeline_state=state)

        self.repo.log_event(
            event_type="ACCESS_CHALLENGE_RESPONSE",
            user_id=user.id if user else None,
            session_id=session.id,
            payload=payload.model_dump(mode="json"),
            response_status=result.next_action,
        )
        self.db.commit()
        return result

    def _finalize(
        self, ctx: AccessContext, *, session, user, device, sensors_available: bool, otp_verified: bool
    ) -> EvaluateAccessOut:
        results = evaluate_rules(ctx)
        score = aggregate_score(results)
        triggered_codes = [r.code for r in results if r.triggered]

        needs_identity = ctx.is_new_device or ctx.device_integrity_failed or ctx.emulator_detected or ctx.root_detected
        identity_still_pending = needs_identity and ctx.biometric_result is None and ctx.liveness_result is None

        # Une fois l'identité confirmée (biométrie/liveness PASSED), le risque "nouvel
        # appareil" est considéré traité : il ne doit plus, à lui seul, imposer une étape
        # supplémentaire (OTP) — sinon la vérification d'identité ne servirait à rien.
        identity_just_confirmed = ctx.biometric_result == "PASSED" or ctx.liveness_result == "PASSED"
        decision_score = score
        if identity_just_confirmed and "NEW_DEVICE" in triggered_codes:
            new_device_weight = next(r.weight for r in results if r.code == "NEW_DEVICE")
            decision_score = max(0.0, decision_score - new_device_weight)

        next_action, user_message = self._decide(ctx, decision_score, identity_still_pending, sensors_available, otp_verified)
        risk_level = self._risk_level(score)
        access_status = {"ALLOW": "ALLOWED", "BLOCK": "BLOCKED", "TEMPORARY_BLOCK": "TEMP_BLOCKED"}.get(
            next_action, "PENDING"
        )
        device_status = "NEW" if ctx.is_new_device else "KNOWN"

        if next_action == "ALLOW" and device is not None:
            self.repo.trust_device(device)

        self.repo.update_session(
            session,
            current_status=access_status,
            risk_level=risk_level,
            final_decision=next_action if next_action in ("ALLOW", "BLOCK", "TEMPORARY_BLOCK") else None,
            ended_at=_utcnow() if next_action in ("ALLOW", "BLOCK", "TEMPORARY_BLOCK") else None,
        )

        pipeline = self._build_pipeline(ctx, triggered_codes, needs_identity, sensors_available, next_action)

        return EvaluateAccessOut(
            session_id=session.id,
            user_id=user.id if user else None,
            access_status=access_status,
            device_status=device_status,
            risk_level=risk_level,
            risk_score=round(score, 1),
            detected_signals=triggered_codes,
            triggered_rules=triggered_codes,
            pipeline=pipeline,
            next_action=next_action,
            user_message=user_message,
        )

    @staticmethod
    def _decide(
        ctx: AccessContext, score: float, identity_still_pending: bool, sensors_available: bool, otp_verified: bool
    ) -> tuple[str, str]:
        agency_message = (
            "Nous n'avons pas pu confirmer votre identité. Pour des raisons de sécurité, "
            "votre compte est temporairement bloqué : rendez-vous en agence avec une pièce "
            "d'identité pour le débloquer."
        )
        if ctx.liveness_result == "FAILED":
            return "BLOCK", agency_message
        if ctx.biometric_result == "FAILED":
            return "REQUIRE_LIVENESS", (
                "La vérification biométrique n'a pas abouti. Une vérification de vivacité "
                "ou votre pièce d'identité est nécessaire."
            )
        if ctx.cloned_device_id:
            return "TEMPORARY_BLOCK", (
                "Nous avons détecté une incohérence sur l'identifiant de votre appareil. "
                "Accès temporairement bloqué par mesure de précaution."
            )
        if score >= 70:
            return "TEMPORARY_BLOCK", (
                "Plusieurs signaux de sécurité inhabituels ont été détectés. Accès "
                "temporairement bloqué par mesure de précaution."
            )
        if identity_still_pending:
            action = "REQUIRE_BIOMETRIC" if sensors_available else "REQUIRE_LIVENESS"
            return action, "Une vérification supplémentaire est nécessaire pour sécuriser votre compte."
        if otp_verified:
            return "ALLOW", "Connexion sécurisée. Bienvenue."
        if score >= 45:
            return "REQUIRE_STEP_UP", "Une vérification supplémentaire est nécessaire pour sécuriser votre compte."
        if score >= 20:
            return "REQUIRE_OTP", "Un code de vérification vous a été envoyé pour confirmer votre identité."
        return "ALLOW", "Connexion sécurisée. Bienvenue."

    @staticmethod
    def _risk_level(score: float) -> str:
        if score >= 70:
            return "CRITICAL"
        if score >= 45:
            return "HIGH"
        if score >= 20:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _build_pipeline(
        ctx: AccessContext, triggered_codes: list[str], needs_identity: bool, sensors_available: bool, next_action: str
    ) -> list[PipelineStepOut]:
        def has(*codes: str) -> list[str]:
            return [c for c in codes if c in triggered_codes]

        integrity_failed_any = ctx.device_integrity_failed or ctx.emulator_detected or ctx.root_detected

        if not needs_identity:
            identity_status = "SKIPPED"
        elif ctx.biometric_result == "PASSED":
            identity_status = "PASSED"
        elif ctx.biometric_result == "FAILED":
            identity_status = "FAILED"
        else:
            identity_status = "PENDING" if sensors_available else "SKIPPED"

        if not needs_identity:
            liveness_status = "SKIPPED"
        elif ctx.liveness_result == "PASSED":
            liveness_status = "PASSED"
        elif ctx.liveness_result == "FAILED":
            liveness_status = "FAILED"
        elif not sensors_available or ctx.biometric_result == "FAILED":
            liveness_status = "PENDING"
        else:
            liveness_status = "SKIPPED"

        return [
            PipelineStepOut(step="DEVICE_CHECK", status="NEW" if ctx.is_new_device else "KNOWN", triggered_rules=has("NEW_DEVICE", "CLONED_DEVICE_ID")),
            PipelineStepOut(step="INTEGRITY_CHECK", status="FAILED" if integrity_failed_any else "PASSED", triggered_rules=has("DEVICE_INTEGRITY_FAILED", "EMULATOR_DETECTED", "ROOT_DETECTED")),
            PipelineStepOut(step="IDENTITY_CHALLENGE", status=identity_status, triggered_rules=has("BIOMETRIC_FAILED")),
            PipelineStepOut(step="LIVENESS_CHECK", status=liveness_status, triggered_rules=has("LIVENESS_FAILED")),
            PipelineStepOut(step="SIM_CHECK", status="CHANGED" if ctx.recent_sim_change else "STABLE", triggered_rules=has("RECENT_SIM_CHANGE")),
            PipelineStepOut(step="FINAL_ACCESS_DECISION", status=next_action, triggered_rules=[]),
        ]

    def _evaluate_location(self, user, session, location) -> tuple[bool, bool]:
        if location is None or location.latitude is None or location.longitude is None:
            return False, False

        location_anomaly = False
        if user.home_latitude is not None and user.home_longitude is not None:
            distance_from_home = haversine_km(location.latitude, location.longitude, user.home_latitude, user.home_longitude)
            location_anomaly = distance_from_home > LOCATION_ANOMALY_RADIUS_KM

        impossible_travel = False
        last_session = self.repo.get_last_session_with_location(user.id, before=session.id)
        if last_session is not None and last_session.latitude is not None:
            elapsed_hours = max((session.started_at - last_session.started_at).total_seconds() / 3600, 0.01)
            distance_km = haversine_km(location.latitude, location.longitude, last_session.latitude, last_session.longitude)
            impossible_travel = (distance_km / elapsed_hours) > MAX_PLAUSIBLE_TRAVEL_SPEED_KMH

        return location_anomaly, impossible_travel

    @staticmethod
    def _evaluate_sim(demo) -> bool:
        if demo is None:
            return False
        if demo.sim_changed_recently_mock:
            return True
        return bool(
            demo.esim_activated_recently_mock
            and demo.sim_age_hours_mock is not None
            and demo.sim_age_hours_mock < 24
        )

    def _evaluate_behaviour(self, user_id: str, behaviour) -> bool:
        if behaviour is None or behaviour.pin_entry_duration_ms is None:
            return False
        profile = self.repo.get_behaviour_profile(user_id)
        if profile is None or profile.sample_count < 3 or profile.average_pin_entry_duration <= 0:
            return False
        ratio = behaviour.pin_entry_duration_ms / profile.average_pin_entry_duration
        return ratio > 2.5 or ratio < 0.35

    # ------------------------------------------------------------------
    # Événements génériques (ouverture app, ajout bénéficiaire, préparation transfert...)
    # ------------------------------------------------------------------
    def log_access_event(self, payload: AccessEventIn) -> AccessEventOut:
        event = self.repo.log_event(
            event_type=payload.event_type,
            user_id=payload.user_id,
            session_id=payload.session_id,
            payload=payload.model_dump(mode="json"),
            response_status=None,
        )
        self.db.commit()
        return AccessEventOut(event_id=event.event_id, received=True)

    # ------------------------------------------------------------------
    # Écrans client (dashboard, bénéficiaires, transfert, historique, profil)
    # ------------------------------------------------------------------
    def get_dashboard(self, user_id: str) -> DashboardOut:
        user = self.repo.get_user(user_id)
        if user is None:
            raise UserNotFoundError()
        transactions = self.repo.list_transactions(user_id, limit=5)
        last_ops = [
            {"id": t.id, "date": t.created_at.isoformat(), "amount": t.amount, "type": t.type, "status": t.status}
            for t in transactions
        ]
        return DashboardOut(
            full_name=user.full_name,
            balance=user.balance,
            wallet_number_masked=mask_wallet_number(user.wallet_number),
            last_operations=last_ops,
        )

    def list_beneficiaries(self, user_id: str) -> list[BeneficiaryOut]:
        return [
            BeneficiaryOut(
                id=b.id,
                full_name=b.full_name,
                phone_masked=mask_phone(b.phone),
                wallet_number_masked=mask_wallet_number(b.wallet_number),
                status=b.status,
                added_at=b.added_at,
            )
            for b in self.repo.list_beneficiaries(user_id)
        ]

    def add_beneficiary(self, user_id: str, payload: BeneficiaryIn) -> BeneficiaryOut:
        # Si ce numéro correspond à un client Amani Wallet existant, on réutilise son vrai
        # numéro de wallet (résolution automatique, comme un vrai Mobile Money) ; sinon on
        # attribue une référence interne — jamais demandée à l'utilisateur qui ajoute.
        existing_user = self.repo.get_user_by_phone(payload.phone)
        wallet_number = existing_user.wallet_number if existing_user else self._generate_unique_wallet_number()
        beneficiary = self.repo.create_beneficiary(
            user_id=user_id, full_name=payload.full_name, phone=payload.phone, wallet_number=wallet_number
        )
        self.repo.log_event(
            event_type="BENEFICIARY_ADDED",
            user_id=user_id,
            session_id=None,
            payload={"beneficiary_id": beneficiary.id},
            response_status=None,
        )
        self.db.commit()
        return BeneficiaryOut(
            id=beneficiary.id,
            full_name=beneficiary.full_name,
            phone_masked=mask_phone(beneficiary.phone),
            wallet_number_masked=mask_wallet_number(beneficiary.wallet_number),
            status=beneficiary.status,
            added_at=beneficiary.added_at,
        )

    def prepare_transfer(self, payload: TransferPrepareIn) -> TransferPrepareOut:
        beneficiary = self.repo.get_beneficiary(payload.beneficiary_id)
        if beneficiary is None or beneficiary.user_id != payload.user_id:
            raise BeneficiaryNotFoundError()

        fee_estimate = round(payload.amount * 0.01, 2)
        self.repo.log_event(
            event_type="TRANSFER_PREPARED",
            user_id=payload.user_id,
            session_id=None,
            payload=payload.model_dump(mode="json"),
            response_status=None,
        )
        self.db.commit()
        return TransferPrepareOut(
            beneficiary_name=beneficiary.full_name,
            beneficiary_wallet_masked=mask_wallet_number(beneficiary.wallet_number),
            amount=payload.amount,
            reason=payload.reason,
            fee_estimate=fee_estimate,
            total_debit=round(payload.amount + fee_estimate, 2),
        )

    def confirm_transfer(self, payload: TransferConfirmIn) -> TransferConfirmOut:
        """Ici (et seulement ici) le module Transaction Monitoring est sollicité, comme
        prévu : la préparation (recap) n'engage rien, la confirmation fait réellement
        analyser l'opération par le même moteur règles + ML que le reste de la plateforme
        — c'est ce qui la rend visible dans le graphe/l'investigation de l'Admin. Aucun
        vrai virement bancaire n'a lieu ; seul le solde fictif du wallet est ajusté."""
        user = self.repo.get_user(payload.user_id)
        if user is None:
            raise UserNotFoundError()
        beneficiary = self.repo.get_beneficiary(payload.beneficiary_id)
        if beneficiary is None or beneficiary.user_id != payload.user_id:
            raise BeneficiaryNotFoundError()

        primary_device = self.repo.get_primary_device(payload.user_id)

        txn_payload = TransactionIn(
            sender_phone=user.phone,
            receiver_phone=beneficiary.phone,
            amount=payload.amount,
            transaction_type="transfer",
            channel="mobile_app",
            device_id=primary_device.device_fingerprint if primary_device else None,
            note=payload.reason,
            behaviour_time_to_complete_ms=payload.behaviour_time_to_complete_ms,
            behaviour_amount_field_edits=payload.behaviour_amount_field_edits,
        )
        analysis = TransactionMonitoringService(self.db).analyze(txn_payload)

        status_by_decision = {
            "ALLOW": "COMPLETED",
            "MONITOR": "COMPLETED",
            "REVIEW": "PENDING",
            "TEMPORARY_BLOCK": "BLOCKED",
        }
        status = status_by_decision.get(analysis.decision, "PENDING")
        message_by_status = {
            "COMPLETED": "Transfert envoyé avec succès.",
            "PENDING": "Votre transfert est en cours de vérification. Vous serez notifié dès qu'il sera traité.",
            "BLOCKED": "Ce transfert n'a pas pu être effectué. Contactez le support Amani Wallet pour plus d'informations.",
        }

        if status == "COMPLETED":
            user.balance -= payload.amount

        wallet_transaction = self.repo.create_wallet_transaction(
            user_id=payload.user_id,
            beneficiary_id=beneficiary.id,
            amount=payload.amount,
            type_="transfer",
            status=status,
        )

        self.repo.log_event(
            event_type="TRANSFER_CONFIRMED",
            user_id=payload.user_id,
            session_id=None,
            payload={**payload.model_dump(mode="json"), "transaction_monitoring_id": analysis.transaction_id},
            response_status=analysis.decision,
        )
        self.db.commit()

        return TransferConfirmOut(
            wallet_transaction_id=wallet_transaction.id,
            status=status,
            message=message_by_status[status],
        )

    def get_history(self, user_id: str) -> list[HistoryEntryOut]:
        out = []
        for t in self.repo.list_transactions(user_id, limit=50):
            beneficiary = self.repo.get_beneficiary(t.beneficiary_id) if t.beneficiary_id else None
            out.append(
                HistoryEntryOut(
                    id=t.id,
                    created_at=t.created_at,
                    beneficiary_name=beneficiary.full_name if beneficiary else None,
                    amount=t.amount,
                    status=t.status,
                    type=t.type,
                )
            )
        return out

    def get_profile(self, user_id: str) -> ProfileOut:
        user = self.repo.get_user(user_id)
        if user is None:
            raise UserNotFoundError()
        primary_device = self.repo.get_primary_device(user_id)
        last_session = self.repo.get_latest_session(user_id)
        return ProfileOut(
            full_name=user.full_name,
            phone_masked=mask_phone(user.phone),
            created_at=user.created_at,
            primary_device=f"{primary_device.platform} • {primary_device.browser}" if primary_device else None,
            last_known_location=(
                f"{last_session.latitude:.3f}, {last_session.longitude:.3f}"
                if last_session and last_session.latitude is not None
                else None
            ),
            kyc_status=user.kyc_status,
            last_pin_change="Non modifié depuis la création du compte",
            security_methods=["Code PIN", "Biométrie (si disponible)", "Vérification de vivacité (liveness)"],
        )

    def list_demo_scenarios(self) -> list[DemoScenarioOut]:
        return [
            DemoScenarioOut(name=s.name, description=s.description, mock_signals=s.mock_signals)
            for s in self.repo.list_demo_scenarios()
        ]
