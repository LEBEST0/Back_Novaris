import type {
  AnalystFeedback,
  DashboardKpis,
  DashboardTrendPoint,
  NetworkGraph,
  TransactionAnalysis,
  TransactionRequest,
} from "../types";

// En dev, le backend FastAPI tourne sur le port 8010 (cf. Backend/README.md). En
// production (Vercel), VITE_API_BASE_URL doit pointer vers l'origine réelle du backend —
// à défaut, on retombe sur le backend Render déployé plutôt que sur localhost.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "https://back-novaris.onrender.com";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText} — ${body}`);
  }
  return response.json() as Promise<T>;
}

export async function analyzeTransaction(payload: TransactionRequest): Promise<TransactionAnalysis> {
  return request<TransactionAnalysis>("/api/v1/transactions/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchTransaction(transactionId: string): Promise<TransactionAnalysis> {
  return request<TransactionAnalysis>(`/api/v1/transactions/${transactionId}`);
}

export async function fetchRecentTransactions(limit = 50): Promise<TransactionAnalysis[]> {
  return request<TransactionAnalysis[]>(`/api/v1/transactions?limit=${limit}`);
}

export async function submitFeedback(
  transactionId: string,
  feedback: AnalystFeedback,
  note?: string,
): Promise<TransactionAnalysis> {
  return request<TransactionAnalysis>(`/api/v1/transactions/${transactionId}/feedback`, {
    method: "PATCH",
    body: JSON.stringify({ feedback, note }),
  });
}

export async function fetchDashboardKpis(): Promise<DashboardKpis> {
  return request<DashboardKpis>("/api/v1/dashboard/kpis");
}

export async function fetchDashboardTrend(days = 7): Promise<DashboardTrendPoint[]> {
  return request<DashboardTrendPoint[]>(`/api/v1/dashboard/trend?days=${days}`);
}

export async function fetchNetworkGraph(limit = 500): Promise<NetworkGraph> {
  return request<NetworkGraph>(`/api/v1/transactions/network?limit=${limit}`);
}
