from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.dependencies import get_db
from modules.wallet_access.access_rules import AccessContext, evaluate_single_rules
from modules.wallet_access.schemas import (
    AccessEventIn,
    AccessEventOut,
    BeneficiaryIn,
    BeneficiaryOut,
    BehaviourCheckIn,
    BehaviourCheckOut,
    DashboardOut,
    DemoScenarioOut,
    DeviceCheckIn,
    DeviceCheckOut,
    EvaluateAccessIn,
    EvaluateAccessOut,
    HistoryEntryOut,
    IdentityCheckIn,
    IdentityCheckOut,
    LoginIn,
    ProfileOut,
    RegisterIn,
    SimCheckIn,
    SimCheckOut,
    TransferConfirmIn,
    TransferConfirmOut,
    TransferPrepareIn,
    TransferPrepareOut,
)
from modules.wallet_access.service import (
    BeneficiaryNotFoundError,
    InvalidCredentialsError,
    PhoneAlreadyRegisteredError,
    SessionNotFoundError,
    UserNotFoundError,
    WalletAccessService,
)

access_router = APIRouter(prefix="/api/v1/access", tags=["wallet-access"])
wallet_router = APIRouter(prefix="/api/v1/wallet", tags=["wallet"])


# ----------------------------------------------------------------------
# Événements + moteur de risque d'accès
# ----------------------------------------------------------------------
@access_router.post("/events/access", response_model=AccessEventOut)
def log_access_event(payload: AccessEventIn, db: Session = Depends(get_db)):
    return WalletAccessService(db).log_access_event(payload)


@access_router.post("/risk/evaluate-access", response_model=EvaluateAccessOut)
def evaluate_access(payload: EvaluateAccessIn, db: Session = Depends(get_db)):
    try:
        return WalletAccessService(db).evaluate_access(payload)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session introuvable")


@access_router.post("/risk/device-check", response_model=DeviceCheckOut)
def device_check(payload: DeviceCheckIn):
    """Vérification isolée (documentation/tests) — le flux réel passe par /wallet/auth/login
    puis /risk/evaluate-access, qui orchestrent l'ensemble du pipeline avec persistance."""
    cloned = bool(
        payload.android_id_mock
        and payload.known_android_id_owner_fingerprint
        and payload.known_android_id_owner_fingerprint != payload.device.device_fingerprint
    )
    ctx = AccessContext(
        is_new_device=not payload.known_fingerprint,
        cloned_device_id=cloned,
        device_integrity_failed=False,
        emulator_detected=False,
        root_detected=False,
        location_anomaly=False,
        impossible_travel=False,
        recent_sim_change=False,
        biometric_result=None,
        liveness_result=None,
        behaviour_anomaly=False,
    )
    triggered = [r.code for r in evaluate_single_rules(ctx, {"NEW_DEVICE", "CLONED_DEVICE_ID"}) if r.triggered]
    return DeviceCheckOut(
        device_status="NEW" if ctx.is_new_device else "KNOWN", cloned_device_id=cloned, triggered_rules=triggered
    )


@access_router.post("/risk/identity-check", response_model=IdentityCheckOut)
def identity_check(payload: IdentityCheckIn):
    ctx = AccessContext(
        is_new_device=False,
        cloned_device_id=False,
        device_integrity_failed=False,
        emulator_detected=False,
        root_detected=False,
        location_anomaly=False,
        impossible_travel=False,
        recent_sim_change=False,
        biometric_result=payload.biometric_result,
        liveness_result=payload.liveness_result,
        behaviour_anomaly=False,
    )
    triggered = [r.code for r in evaluate_single_rules(ctx, {"BIOMETRIC_FAILED", "LIVENESS_FAILED"}) if r.triggered]
    if payload.liveness_result == "FAILED" or payload.biometric_result == "FAILED":
        status = "FAILED"
    elif payload.biometric_result == "PASSED" or payload.liveness_result == "PASSED":
        status = "PASSED"
    else:
        status = "PENDING"
    return IdentityCheckOut(identity_status=status, triggered_rules=triggered)


@access_router.post("/risk/behaviour-check", response_model=BehaviourCheckOut)
def behaviour_check(payload: BehaviourCheckIn):
    anomaly = False
    if (
        payload.pin_entry_duration_ms is not None
        and payload.average_pin_entry_duration_ms
        and payload.sample_count >= 3
    ):
        ratio = payload.pin_entry_duration_ms / payload.average_pin_entry_duration_ms
        anomaly = ratio > 2.5 or ratio < 0.35
    return BehaviourCheckOut(
        behaviour_status="ANOMALY" if anomaly else "NORMAL",
        triggered_rules=["BEHAVIOUR_ANOMALY"] if anomaly else [],
    )


@access_router.post("/risk/sim-check", response_model=SimCheckOut)
def sim_check(payload: SimCheckIn):
    changed = payload.sim_changed_recently_mock or bool(
        payload.esim_activated_recently_mock and payload.sim_age_hours_mock is not None and payload.sim_age_hours_mock < 24
    )
    ctx = AccessContext(
        is_new_device=False,
        cloned_device_id=False,
        device_integrity_failed=False,
        emulator_detected=False,
        root_detected=False,
        location_anomaly=False,
        impossible_travel=False,
        recent_sim_change=changed,
        biometric_result=None,
        liveness_result=None,
        behaviour_anomaly=False,
    )
    triggered = [r.code for r in evaluate_single_rules(ctx, {"RECENT_SIM_CHANGE"}) if r.triggered]
    return SimCheckOut(sim_status="CHANGED" if changed else "STABLE", triggered_rules=triggered)


# ----------------------------------------------------------------------
# Application cliente Amani Wallet
# ----------------------------------------------------------------------
@wallet_router.post("/auth/login", response_model=EvaluateAccessOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    try:
        return WalletAccessService(db).login(payload)
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="Numéro de téléphone ou mot de passe incorrect")


@wallet_router.post("/auth/register", response_model=EvaluateAccessOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    """Crée le compte puis exécute immédiatement le même pipeline de contrôle d'accès que
    la connexion (device/intégrité/identité...) : l'inscription connecte automatiquement,
    mais ne contourne jamais le moteur de risque."""
    try:
        return WalletAccessService(db).register(payload)
    except PhoneAlreadyRegisteredError:
        raise HTTPException(status_code=409, detail="Un compte existe déjà avec ce numéro de téléphone")


@wallet_router.get("/dashboard", response_model=DashboardOut)
def dashboard(user_id: str, db: Session = Depends(get_db)):
    try:
        return WalletAccessService(db).get_dashboard(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="Client introuvable")


@wallet_router.get("/beneficiaries", response_model=list[BeneficiaryOut])
def list_beneficiaries(user_id: str, db: Session = Depends(get_db)):
    return WalletAccessService(db).list_beneficiaries(user_id)


@wallet_router.post("/beneficiaries", response_model=BeneficiaryOut)
def add_beneficiary(user_id: str, payload: BeneficiaryIn, db: Session = Depends(get_db)):
    return WalletAccessService(db).add_beneficiary(user_id, payload)


@wallet_router.post("/transfer/prepare", response_model=TransferPrepareOut)
def prepare_transfer(payload: TransferPrepareIn, db: Session = Depends(get_db)):
    try:
        return WalletAccessService(db).prepare_transfer(payload)
    except BeneficiaryNotFoundError:
        raise HTTPException(status_code=404, detail="Bénéficiaire introuvable")


@wallet_router.post("/transfer/confirm", response_model=TransferConfirmOut)
def confirm_transfer(payload: TransferConfirmIn, db: Session = Depends(get_db)):
    """Fait réellement analyser l'opération par le module Transaction Monitoring —
    c'est cet appel, et non /transfer/prepare, qui rend la transaction visible dans le
    graphe/l'investigation de l'Admin."""
    try:
        return WalletAccessService(db).confirm_transfer(payload)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="Client introuvable")
    except BeneficiaryNotFoundError:
        raise HTTPException(status_code=404, detail="Bénéficiaire introuvable")


@wallet_router.get("/history", response_model=list[HistoryEntryOut])
def history(user_id: str, db: Session = Depends(get_db)):
    return WalletAccessService(db).get_history(user_id)


@wallet_router.get("/profile", response_model=ProfileOut)
def profile(user_id: str, db: Session = Depends(get_db)):
    try:
        return WalletAccessService(db).get_profile(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="Client introuvable")


@wallet_router.get("/demo/scenarios", response_model=list[DemoScenarioOut])
def demo_scenarios(db: Session = Depends(get_db)):
    return WalletAccessService(db).list_demo_scenarios()
