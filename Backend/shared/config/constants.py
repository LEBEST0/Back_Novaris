"""Constantes métier partagées par les modules Novaris AI."""

TRANSACTION_TYPES = [
    "deposit",
    "withdrawal",
    "transfer",
    "merchant_payment",
    "airtime_purchase",
    "bill_payment",
]

CHANNELS = ["mobile_app", "ussd", "agent", "web", "api"]

KYC_LEVELS = ["basic", "standard", "premium"]

CURRENCY_DEFAULT = "XOF"

RISK_LEVELS = ["low", "moderate", "high", "critical"]

DECISIONS = ["ALLOW", "MONITOR", "REVIEW", "TEMPORARY_BLOCK"]
