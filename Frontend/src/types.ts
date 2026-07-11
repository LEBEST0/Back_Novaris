// Contrat aligné sur modules/transaction_monitoring/schemas.py (backend réel).
// Aucun champ ici n'est inventé côté frontend : tout vient de l'API FastAPI.

export type RiskLevel = "low" | "moderate" | "high" | "critical";
export type Decision = "ALLOW" | "MONITOR" | "REVIEW" | "TEMPORARY_BLOCK";
export type AnalystFeedback = "CONFIRMED" | "FALSE_POSITIVE";

export interface RuleFlag {
  code: string;
  description: string;
  weight: number;
}

export interface TransactionAnalysis {
  transaction_id: string;
  sender_phone: string;
  sender_operator: string;
  sender_country: string;
  receiver_phone: string;
  receiver_country: string | null;
  is_cross_border: boolean;
  batch_id: string | null;
  agent_id: string | null;
  device_id: string | null;
  sender_city: string | null;
  sender_kyc_level: string;
  sender_national_id: string | null;
  receiver_kyc_level: string | null;
  receiver_national_id: string | null;
  balance_before_sender: number | null;
  balance_after_sender: number | null;
  amount: number;
  currency: string;
  transaction_type: string;
  channel: string;
  rule_score: number;
  ml_score: number;
  final_score: number;
  risk_level: RiskLevel;
  decision: Decision;
  confidence: number;
  reasons: string[];
  rule_flags: RuleFlag[];
  top_ml_factors: string[];
  model_version: string;
  computed_at: string;
  analyst_feedback: AnalystFeedback | null;
  feedback_note: string | null;
  feedback_at: string | null;
}

// Payload d'analyse : mêmes champs que TransactionIn côté FastAPI.
export interface TransactionRequest {
  sender_phone: string;
  receiver_phone: string;
  amount: number;
  currency?: string | null;
  transaction_type: string;
  channel?: string;
  timestamp?: string | null;
  device_id?: string | null;
  sender_city?: string | null;
  note?: string | null;
  batch_id?: string | null;
  agent_id?: string | null;
  balance_before_sender?: number | null;
  balance_after_sender?: number | null;
}

export interface DashboardKpis {
  transactions_analyzed: number;
  active_alerts: number;
  blocking_rate: number;
  average_score: number;
  pending_analyst_review: number;
  fraud_amount_confirmed: number;
  false_positive_rate: number | null;
}

export interface DashboardTrendPoint {
  date: string;
  transactions_analyzed: number;
  alerts: number;
  average_score: number;
}
