// Miroir de shared/config/constants.py (backend) — à garder synchronisé.
export const TRANSACTION_TYPES = [
  "deposit",
  "withdrawal",
  "transfer",
] as const;

export const CHANNELS = ["mobile_app", "agent"] as const;

export const TRANSACTION_TYPE_LABELS: Record<string, string> = {
  deposit: "Dépôt (cash-in)",
  withdrawal: "Retrait (cash-out)",
  transfer: "Transfert P2P",
};

export const CHANNEL_LABELS: Record<string, string> = {
  mobile_app: "Application mobile",
  agent: "Agent",
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
