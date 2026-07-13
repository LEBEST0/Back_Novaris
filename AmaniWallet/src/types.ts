// Contrat aligné sur Backend/modules/wallet_access/schemas.py — rien n'est inventé côté
// frontend, tout vient de l'API.

export interface DeviceInfo {
  local_device_uuid: string;
  device_fingerprint: string;
  platform: string;
  os_version: string;
  browser: string;
  screen_width: number;
  screen_height: number;
  language: string;
  timezone: string;
  sensors_available: boolean;
}

export interface LocationInfo {
  latitude: number | null;
  longitude: number | null;
  accuracy: number | null;
  permission_granted: boolean;
}

export interface DemoSignals {
  scenario: string;
  android_id_mock?: string | null;
  device_integrity_mock?: string;
  emulator_detected_mock?: boolean;
  root_detected_mock?: boolean;
  sim_changed_recently_mock?: boolean;
  esim_activated_recently_mock?: boolean;
  sim_age_hours_mock?: number | null;
  biometric_result_mock?: string | null;
  liveness_result_mock?: string | null;
}

export interface BehaviourMetrics {
  login_duration_ms: number | null;
  pin_entry_duration_ms: number | null;
  correction_count: number;
  failed_attempts: number;
  time_on_page_ms: number | null;
}

export interface ChallengeResponse {
  otp_code?: string | null;
  biometric_result?: string | null;
  liveness_result?: string | null;
  cni_provided?: boolean;
}

export interface LoginPayload {
  phone: string;
  pin: string;
  device: DeviceInfo;
  location?: LocationInfo | null;
  demo_signals?: DemoSignals | null;
  behaviour?: BehaviourMetrics | null;
}

export interface RegisterPayload extends LoginPayload {
  full_name: string;
}

export interface PipelineStep {
  step: string;
  status: string;
  triggered_rules: string[];
}

export interface EvaluateAccessResult {
  session_id: string;
  user_id: string | null;
  access_status: string;
  device_status: string;
  risk_level: string;
  risk_score: number;
  detected_signals: string[];
  triggered_rules: string[];
  pipeline: PipelineStep[];
  next_action: NextAction;
  user_message: string;
}

export type NextAction =
  | "ALLOW"
  | "REQUIRE_OTP"
  | "REQUIRE_STEP_UP"
  | "REQUIRE_BIOMETRIC"
  | "REQUIRE_LIVENESS"
  | "TEMPORARY_BLOCK"
  | "BLOCK";

export interface DashboardData {
  full_name: string;
  balance: number;
  wallet_number_masked: string;
  last_operations: Array<{ id: string; date: string; amount: number; type: string; status: string }>;
}

export interface Beneficiary {
  id: string;
  full_name: string;
  phone_masked: string;
  wallet_number_masked: string;
  status: string;
  added_at: string;
}

export interface TransferPrepareResult {
  beneficiary_name: string;
  beneficiary_wallet_masked: string;
  amount: number;
  reason: string | null;
  fee_estimate: number;
  total_debit: number;
  note: string;
}

export interface TransferConfirmResult {
  wallet_transaction_id: string;
  status: "COMPLETED" | "PENDING" | "BLOCKED";
  message: string;
}

export interface Agent {
  agent_id: string;
  name: string;
  city: string;
}

export interface CashOperationResult {
  wallet_transaction_id: string;
  status: "COMPLETED" | "PENDING" | "BLOCKED";
  message: string;
  new_balance: number;
}

export interface HistoryEntry {
  id: string;
  created_at: string;
  beneficiary_name: string | null;
  amount: number;
  status: string;
  type: string;
}

export interface Profile {
  full_name: string;
  phone_masked: string;
  created_at: string;
  primary_device: string | null;
  last_known_location: string | null;
  kyc_status: string;
  last_pin_change: string;
  security_methods: string[];
}

export interface DemoScenario {
  name: string;
  description: string;
  mock_signals: Record<string, unknown>;
}
