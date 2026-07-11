// Miroir de shared/config/constants.py (backend) — à garder synchronisé.
export const TRANSACTION_TYPES = [
  "deposit",
  "withdrawal",
  "transfer",
  "merchant_payment",
  "airtime_purchase",
  "bill_payment",
] as const;

export const CHANNELS = ["mobile_app", "ussd", "agent", "web", "api"] as const;

export const TRANSACTION_TYPE_LABELS: Record<string, string> = {
  deposit: "Dépôt (cash-in)",
  withdrawal: "Retrait (cash-out)",
  transfer: "Transfert P2P",
  merchant_payment: "Paiement marchand",
  airtime_purchase: "Achat de crédit",
  bill_payment: "Paiement de facture",
};

export const CHANNEL_LABELS: Record<string, string> = {
  mobile_app: "Application mobile",
  ussd: "USSD",
  agent: "Agent",
  web: "Web",
  api: "API",
};

export const RISK_LABELS: Record<string, string> = {
  low: "Faible",
  moderate: "Modéré",
  high: "Élevé",
  critical: "Critique",
};

export const DECISION_LABELS: Record<string, string> = {
  ALLOW: "Autorisé",
  MONITOR: "Sous surveillance",
  REVIEW: "Revue analyste",
  TEMPORARY_BLOCK: "Blocage temporaire",
};
