import { useEffect, useState } from "react";
import { fetchHistory } from "../lib/api";
import { BottomNav, type NavScreen } from "../components/BottomNav";
import type { HistoryEntry } from "../types";

interface HistoryProps {
  userId: string;
  onNavigate: (screen: NavScreen) => void;
}

function formatXof(amount: number): string {
  return new Intl.NumberFormat("fr-FR").format(amount) + " F CFA";
}

const STATUS_BADGE: Record<string, string> = {
  COMPLETED: "badge-success",
  PENDING: "badge-warning",
  FAILED: "badge-danger",
  BLOCKED: "badge-danger",
};

const STATUS_LABEL: Record<string, string> = {
  COMPLETED: "Terminée",
  PENDING: "En cours",
  FAILED: "Échouée",
  BLOCKED: "Bloquée",
};

const TYPE_LABEL: Record<string, string> = {
  transfer: "Transfert",
  recharge: "Recharge",
  payment: "Paiement",
  withdrawal: "Retrait",
};

export function History({ userId, onNavigate }: HistoryProps) {
  const [items, setItems] = useState<HistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHistory(userId)
      .then(setItems)
      .catch((err) => setError(err instanceof Error ? err.message : "Impossible de charger l'historique."));
  }, [userId]);

  return (
    <div className="screen">
      <div className="topbar">
        <div>
          <p className="eyebrow">Amani Wallet</p>
          <h1>Historique</h1>
        </div>
      </div>

      {error && <p className="error-banner">{error}</p>}

      <div className="card">
        {!items && !error && <p className="summary">Chargement…</p>}
        {items && items.length === 0 && <p className="summary">Aucune opération enregistrée.</p>}
        {items?.map((entry) => (
          <div className="list-row" key={entry.id}>
            <div className="avatar">{(TYPE_LABEL[entry.type] ?? entry.type).slice(0, 2).toUpperCase()}</div>
            <div className="main">
              <strong>{entry.beneficiary_name ?? TYPE_LABEL[entry.type] ?? entry.type}</strong>
              <span>{new Date(entry.created_at).toLocaleString("fr-FR")} · {formatXof(entry.amount)}</span>
            </div>
            <span className={`badge ${STATUS_BADGE[entry.status] ?? "badge-neutral"}`}>
              {STATUS_LABEL[entry.status] ?? entry.status}
            </span>
          </div>
        ))}
      </div>

      <BottomNav active="history" onNavigate={onNavigate} />
    </div>
  );
}
