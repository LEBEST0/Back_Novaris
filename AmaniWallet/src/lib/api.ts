import type {
  Agent,
  Beneficiary,
  CashOperationResult,
  DashboardData,
  DemoScenario,
  EvaluateAccessResult,
  HistoryEntry,
  LoginPayload,
  Profile,
  RegisterPayload,
  TransferConfirmResult,
  TransferPrepareResult,
} from "../types";

// En dev, le backend tourne en local sur le port 8010. En production (Vercel),
// VITE_NOVARIS_RISK_ENGINE_URL doit pointer vers l'origine réelle du backend — à défaut,
// on retombe sur le backend Render déployé plutôt que sur localhost.
const API_BASE_URL = import.meta.env.VITE_NOVARIS_RISK_ENGINE_URL ?? "https://back-novaris.onrender.com";

export class ApiUnavailableError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiUnavailableError(
      "Le service de vérification est momentanément indisponible. Veuillez réessayer.",
    );
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail ?? `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export function login(payload: LoginPayload): Promise<EvaluateAccessResult> {
  return request<EvaluateAccessResult>("/api/v1/wallet/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function register(payload: RegisterPayload): Promise<EvaluateAccessResult> {
  return request<EvaluateAccessResult>("/api/v1/wallet/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function evaluateAccess(
  sessionId: string,
  challengeResponse?: Record<string, unknown>,
): Promise<EvaluateAccessResult> {
  return request<EvaluateAccessResult>("/api/v1/access/risk/evaluate-access", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, challenge_response: challengeResponse ?? null }),
  });
}

export function logAccessEvent(eventType: string, extra?: Record<string, unknown>): Promise<void> {
  return request("/api/v1/access/events/access", {
    method: "POST",
    body: JSON.stringify({ event_type: eventType, ...extra }),
  }).then(() => undefined);
}

export function fetchDashboard(userId: string): Promise<DashboardData> {
  return request<DashboardData>(`/api/v1/wallet/dashboard?user_id=${encodeURIComponent(userId)}`);
}

export function fetchBeneficiaries(userId: string): Promise<Beneficiary[]> {
  return request<Beneficiary[]>(`/api/v1/wallet/beneficiaries?user_id=${encodeURIComponent(userId)}`);
}

export function addBeneficiary(
  userId: string,
  payload: { full_name: string; phone: string },
): Promise<Beneficiary> {
  return request<Beneficiary>(`/api/v1/wallet/beneficiaries?user_id=${encodeURIComponent(userId)}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function prepareTransfer(payload: {
  user_id: string;
  beneficiary_id: string;
  amount: number;
  reason?: string;
}): Promise<TransferPrepareResult> {
  return request<TransferPrepareResult>("/api/v1/wallet/transfer/prepare", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function confirmTransfer(payload: {
  user_id: string;
  beneficiary_id: string;
  amount: number;
  reason?: string;
  behaviour_time_to_complete_ms?: number;
  behaviour_amount_field_edits?: number;
}): Promise<TransferConfirmResult> {
  return request<TransferConfirmResult>("/api/v1/wallet/transfer/confirm", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchAgents(): Promise<Agent[]> {
  return request<Agent[]>("/api/v1/wallet/agents");
}

export function depositFunds(payload: {
  user_id: string;
  amount: number;
  source: "agent" | "external_momo";
  agent_id?: string | null;
  behaviour_time_to_complete_ms?: number;
  behaviour_amount_field_edits?: number;
}): Promise<CashOperationResult> {
  return request<CashOperationResult>("/api/v1/wallet/deposit", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function withdrawFunds(payload: {
  user_id: string;
  agent_id: string;
  amount: number;
  behaviour_time_to_complete_ms?: number;
  behaviour_amount_field_edits?: number;
}): Promise<CashOperationResult> {
  return request<CashOperationResult>("/api/v1/wallet/withdraw", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchHistory(userId: string): Promise<HistoryEntry[]> {
  return request<HistoryEntry[]>(`/api/v1/wallet/history?user_id=${encodeURIComponent(userId)}`);
}

export function fetchProfile(userId: string): Promise<Profile> {
  return request<Profile>(`/api/v1/wallet/profile?user_id=${encodeURIComponent(userId)}`);
}

export function fetchDemoScenarios(): Promise<DemoScenario[]> {
  return request<DemoScenario[]>("/api/v1/wallet/demo/scenarios");
}
