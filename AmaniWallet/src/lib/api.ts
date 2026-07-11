import type {
  Beneficiary,
  DashboardData,
  DemoScenario,
  EvaluateAccessResult,
  HistoryEntry,
  LoginPayload,
  Profile,
  RegisterPayload,
  TransferPrepareResult,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_NOVARIS_RISK_ENGINE_URL ?? "http://127.0.0.1:8010";

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
  payload: { full_name: string; phone: string; wallet_number: string },
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

export function fetchHistory(userId: string): Promise<HistoryEntry[]> {
  return request<HistoryEntry[]>(`/api/v1/wallet/history?user_id=${encodeURIComponent(userId)}`);
}

export function fetchProfile(userId: string): Promise<Profile> {
  return request<Profile>(`/api/v1/wallet/profile?user_id=${encodeURIComponent(userId)}`);
}

export function fetchDemoScenarios(): Promise<DemoScenario[]> {
  return request<DemoScenario[]>("/api/v1/wallet/demo/scenarios");
}
