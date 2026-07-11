from datetime import datetime

from pydantic import BaseModel, Field


class DeviceInfoIn(BaseModel):
    local_device_uuid: str
    device_fingerprint: str
    platform: str = "unknown"
    os_version: str = "unknown"
    browser: str = "unknown"
    screen_width: int | None = None
    screen_height: int | None = None
    language: str = "fr-FR"
    timezone: str = "Africa/Abidjan"
    sensors_available: bool = True


class LocationIn(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    accuracy: float | None = None
    permission_granted: bool = False


class DemoSignalsIn(BaseModel):
    """Signaux simulés — jamais présentés comme des données matérielles réelles (cf.
    README, section « Données simulées »). `source` est toujours MOCK_* pour ces champs."""

    scenario: str = "NORMAL_USER"
    android_id_mock: str | None = None
    device_integrity_mock: str = "PASSED"
    emulator_detected_mock: bool = False
    root_detected_mock: bool = False
    sim_changed_recently_mock: bool = False
    esim_activated_recently_mock: bool = False
    sim_age_hours_mock: float | None = None
    biometric_result_mock: str | None = None
    liveness_result_mock: str | None = None


class BehaviourMetricsIn(BaseModel):
    login_duration_ms: int | None = None
    pin_entry_duration_ms: int | None = None
    correction_count: int = 0
    failed_attempts: int = 0
    time_on_page_ms: int | None = None


class ChallengeResponseIn(BaseModel):
    otp_code: str | None = None
    biometric_result: str | None = Field(default=None, description="'PASSED' ou 'FAILED', simulé côté client")
    liveness_result: str | None = Field(default=None, description="'PASSED' ou 'FAILED', simulé côté client")
    cni_provided: bool = False


class LoginIn(BaseModel):
    phone: str
    pin: str
    device: DeviceInfoIn
    location: LocationIn | None = None
    demo_signals: DemoSignalsIn | None = None
    behaviour: BehaviourMetricsIn | None = None


class RegisterIn(BaseModel):
    full_name: str
    phone: str
    pin: str = Field(pattern=r"^\d{4}$", description="Mot de passe à 4 chiffres (jamais stocké en clair)")
    device: DeviceInfoIn
    location: LocationIn | None = None
    demo_signals: DemoSignalsIn | None = None
    behaviour: BehaviourMetricsIn | None = None


class EvaluateAccessIn(BaseModel):
    session_id: str
    challenge_response: ChallengeResponseIn | None = None


class PipelineStepOut(BaseModel):
    step: str
    status: str
    triggered_rules: list[str]


class EvaluateAccessOut(BaseModel):
    session_id: str
    user_id: str | None = None
    access_status: str  # ALLOWED | PENDING | BLOCKED | TEMP_BLOCKED
    device_status: str  # KNOWN | NEW
    risk_level: str  # LOW | MEDIUM | HIGH | CRITICAL
    risk_score: float
    detected_signals: list[str]
    triggered_rules: list[str]
    pipeline: list[PipelineStepOut]
    next_action: str
    user_message: str


class AccessEventIn(BaseModel):
    event_id: str | None = None
    event_type: str
    user_id: str | None = None
    session_id: str | None = None
    timestamp: datetime | None = None
    device: DeviceInfoIn | None = None
    location: LocationIn | None = None
    demo_signals: DemoSignalsIn | None = None
    payload: dict = Field(default_factory=dict)


class AccessEventOut(BaseModel):
    event_id: str
    received: bool = True


class BeneficiaryIn(BaseModel):
    """Un client ajoute un bénéficiaire par nom + téléphone, comme dans un vrai Mobile
    Money — le numéro de wallet interne n'est pas quelque chose que l'utilisateur connaît
    ou doit saisir ; il est résolu/attribué côté serveur."""

    full_name: str
    phone: str


class BeneficiaryOut(BaseModel):
    id: str
    full_name: str
    phone_masked: str
    wallet_number_masked: str
    status: str
    added_at: datetime

    class Config:
        from_attributes = True


class TransferPrepareIn(BaseModel):
    user_id: str
    beneficiary_id: str
    amount: float = Field(gt=0)
    reason: str | None = None


class TransferPrepareOut(BaseModel):
    beneficiary_name: str
    beneficiary_wallet_masked: str
    amount: float
    reason: str | None
    fee_estimate: float
    total_debit: float
    note: str = "Aucun transfert réel n'est effectué à cette étape (démonstration Novaris AI)."


class TransferConfirmIn(BaseModel):
    user_id: str
    beneficiary_id: str
    amount: float = Field(gt=0)
    reason: str | None = None


class TransferConfirmOut(BaseModel):
    wallet_transaction_id: str
    status: str  # COMPLETED | PENDING | BLOCKED
    message: str


class DashboardOut(BaseModel):
    full_name: str
    balance: float
    wallet_number_masked: str
    last_operations: list[dict]


class HistoryEntryOut(BaseModel):
    id: str
    created_at: datetime
    beneficiary_name: str | None
    amount: float
    status: str
    type: str


class ProfileOut(BaseModel):
    full_name: str
    phone_masked: str
    created_at: datetime
    primary_device: str | None
    last_known_location: str | None
    kyc_status: str
    last_pin_change: str
    security_methods: list[str]


class DeviceCheckIn(BaseModel):
    device: DeviceInfoIn
    known_fingerprint: bool = Field(description="Vrai si ce fingerprint est déjà de confiance pour ce compte")
    android_id_mock: str | None = None
    known_android_id_owner_fingerprint: str | None = Field(
        default=None, description="Fingerprint de l'appareil de confiance qui possède déjà cet android_id_mock, si existant"
    )


class DeviceCheckOut(BaseModel):
    device_status: str
    cloned_device_id: bool
    triggered_rules: list[str]


class IdentityCheckIn(BaseModel):
    biometric_result: str | None = None
    liveness_result: str | None = None
    sensors_available: bool = True


class IdentityCheckOut(BaseModel):
    identity_status: str
    triggered_rules: list[str]


class BehaviourCheckIn(BaseModel):
    pin_entry_duration_ms: int | None = None
    average_pin_entry_duration_ms: float | None = None
    sample_count: int = 0


class BehaviourCheckOut(BaseModel):
    behaviour_status: str
    triggered_rules: list[str]


class SimCheckIn(BaseModel):
    sim_changed_recently_mock: bool = False
    esim_activated_recently_mock: bool = False
    sim_age_hours_mock: float | None = None


class SimCheckOut(BaseModel):
    sim_status: str
    triggered_rules: list[str]


class DemoScenarioOut(BaseModel):
    name: str
    description: str
    mock_signals: dict

    class Config:
        from_attributes = True
