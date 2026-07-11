import { DECISION_LABELS, RISK_LABELS } from "../constants";
import type { Decision, RiskLevel } from "../types";

export const formatCurrency = (amount: number, currency = "XOF") =>
  new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);

export const formatDecision = (decision: Decision) => DECISION_LABELS[decision] ?? decision;

export const formatRiskLevel = (riskLevel: RiskLevel) => RISK_LABELS[riskLevel] ?? riskLevel;

const RISK_CLASSES: Record<RiskLevel, string> = {
  low: "risk-low",
  moderate: "risk-medium",
  high: "risk-high",
  critical: "risk-critical",
};

export const riskClass = (riskLevel: RiskLevel) => RISK_CLASSES[riskLevel] ?? "risk-low";

export const formatDateTime = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });

export const formatPercent = (value: number, digits = 0) => `${value.toFixed(digits)}%`;
