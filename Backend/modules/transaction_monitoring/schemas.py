from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.config.constants import CHANNELS, TRANSACTION_TYPES


class TransactionIn(BaseModel):
    """Payload minimal envoyé par le canal d'entrée (app, API, agent, USSD) pour analyse."""

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
    batch_id: str | None = Field(
        default=None,
        description=(
            "Identifiant d'une opération de paiement de masse (Clapay B2B) : les "
            "transactions qui partagent le même batch_id sont traitées comme un seul "
            "envoi groupé déclaré, pas comme des transferts distincts indépendants."
        ),
    )
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
    batch_id: str | None
    amount: float
    currency: str
    transaction_type: str
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

    model_config = ConfigDict(from_attributes=True)


class CustomerIn(BaseModel):
    phone: str
    full_name: str
    kyc_level: str = "basic"
    customer_type: str = "individual"
    operator: str = "Autre / inconnu"
    country: str = "Côte d'Ivoire"
    home_city: str = "Abidjan"
    account_created_at: datetime | None = None
