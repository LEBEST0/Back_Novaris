"""Constantes métier partagées par les modules Novaris AI."""

TRANSACTION_TYPES = [
    "deposit",
    "withdrawal",
    "transfer",
]

CHANNELS = ["mobile_app", "agent"]

KYC_LEVELS = ["basic", "standard", "premium"]

CUSTOMER_TYPES = ["individual", "merchant", "agent"]

CURRENCY_DEFAULT = "XOF"

RISK_LEVELS = ["low", "moderate", "high", "critical"]

DECISIONS = ["ALLOW", "MONITOR", "REVIEW", "TEMPORARY_BLOCK"]
