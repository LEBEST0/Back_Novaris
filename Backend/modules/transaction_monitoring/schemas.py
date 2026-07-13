from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.config.constants import CHANNELS, TRANSACTION_TYPES


class TransactionIn(BaseModel):
    """Payload minimal envoyé par le canal d'entrée (app ou agence) pour analyse."""

    sender_phone: str = Field(examples=["+2250700000001"])
    receiver_phone: str = Field(examples=["+2250700000099"])
    amount: float = Field(gt=0)
    currency: str | None = Field(
        default=None,
        description="Devise ISO du montant. Si absente, déduite du pays de l'émetteur.",
    )
    transaction_type: str
    channel: str = "mobile_app"
    timestamp: datetime | None = None
    device_id: str | None = None
    sender_city: str | None = None
    note: str | None = None
    agent_id: str | None = Field(
        default=None,
        description="Agent Mobile Money ayant traité un dépôt/retrait en espèces (cash-in/cash-out).",
    )
    balance_before_sender: float | None = Field(
        default=None,
        description="Solde du portefeuille de l'émetteur avant la transaction, si connu du système appelant.",
    )
    balance_after_sender: float | None = Field(
        default=None,
        description="Solde du portefeuille de l'émetteur après la transaction, si connu du système appelant.",
    )
    behaviour_time_to_complete_ms: int | None = Field(
        default=None,
        description=(
            "Temps entre l'ouverture du formulaire de transaction et sa confirmation par "
            "le client, si mesuré par le canal appelant (ex. Amani Wallet)."
        ),
    )
    behaviour_amount_field_edits: int | None = Field(
        default=None,
        description="Nombre de modifications du champ montant avant confirmation, si mesuré par le canal appelant.",
    )

    @field_validator("transaction_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in TRANSACTION_TYPES:
            raise ValueError(f"transaction_type doit être l'un de {TRANSACTION_TYPES}")
        return v

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        if v not in CHANNELS:
            raise ValueError(f"channel doit être l'un de {CHANNELS}")
        return v


class RuleFlagOut(BaseModel):
    code: str
    description: str
    weight: float


class TransactionAnalysisOut(BaseModel):
    transaction_id: str
    sender_phone: str
    sender_operator: str
    sender_country: str
    receiver_phone: str
    receiver_country: str | None
    is_cross_border: bool
    agent_id: str | None = None
    device_id: str | None = None
    sender_city: str | None = None
    sender_kyc_level: str
    sender_national_id: str | None = None
    receiver_kyc_level: str | None = None
    receiver_national_id: str | None = None
    balance_before_sender: float | None = None
    balance_after_sender: float | None = None
    amount: float
    currency: str
    transaction_type: str
    channel: str = "mobile_app"
    rule_score: float
    ml_score: float
    final_score: float
    risk_level: str
    decision: str
    confidence: float
    reasons: list[str]
    rule_flags: list[RuleFlagOut]
    top_ml_factors: list[str]
    model_version: str
    computed_at: datetime
    analyst_feedback: str | None = None
    feedback_note: str | None = None
    feedback_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class FeedbackIn(BaseModel):
    feedback: str = Field(description="CONFIRMED (alerte confirmée) ou FALSE_POSITIVE (signal écarté)")
    note: str | None = None

    @field_validator("feedback")
    @classmethod
    def validate_feedback(cls, v: str) -> str:
        allowed = {"CONFIRMED", "FALSE_POSITIVE"}
        if v not in allowed:
            raise ValueError(f"feedback doit être l'un de {sorted(allowed)}")
        return v


class DashboardKpisOut(BaseModel):
    transactions_analyzed: int
    active_alerts: int
    blocking_rate: float
    average_score: float
    pending_analyst_review: int
    fraud_amount_confirmed: float
    false_positive_rate: float | None = None


class DashboardTrendPointOut(BaseModel):
    date: str
    transactions_analyzed: int
    alerts: int
    average_score: float


class RiskDistributionPointOut(BaseModel):
    risk_level: str
    count: int
    average_score: float


class NetworkNodeOut(BaseModel):
    id: str
    label: str
    type: str  # "customer" | "agent" | "device"
    identity_verified: bool = False
    country: str | None = None
    transaction_count: int = 0
    max_risk_level: str = "low"
    flagged: bool = False  # au moins une transaction REVIEW/TEMPORARY_BLOCK impliquant ce nœud


class NetworkEdgeOut(BaseModel):
    id: str
    source: str
    target: str
    kind: str  # "transaction" | "agent" | "device"
    transaction_id: str | None = None
    amount: float | None = None
    currency: str | None = None
    transaction_type: str | None = None
    decision: str | None = None
    risk_level: str | None = None
    created_at: str | None = None


class NetworkGraphOut(BaseModel):
    nodes: list[NetworkNodeOut]
    edges: list[NetworkEdgeOut]
    truncated: bool = False


class CustomerIn(BaseModel):
    phone: str
    full_name: str
    kyc_level: str = "basic"
    national_id: str | None = None
    customer_type: str = "individual"
    operator: str = "Autre / inconnu"
    country: str = "Côte d'Ivoire"
    home_city: str = "Abidjan"
    account_created_at: datetime | None = None


class CustomerOut(BaseModel):
    phone: str
    full_name: str
    kyc_level: str
    national_id: str | None = None
    customer_type: str
    operator: str
    country: str
    home_city: str
    account_created_at: datetime
    # Dernier device_id observé pour ce client (transaction la plus récente), pour que
    # l'écran d'analyse manuelle puisse simuler un appareil "connu" ou "nouveau" à volonté.
    last_device_id: str | None = None

    model_config = ConfigDict(from_attributes=True)
