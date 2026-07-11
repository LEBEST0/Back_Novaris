import { useEffect, useState } from "react";
import { ArrowDownToLine, ArrowUpRight, CreditCard, ShieldCheck, Wallet } from "lucide-react";
import { fetchDashboard } from "../lib/api";
import { BottomNav, type NavScreen } from "../components/BottomNav";
import type { DashboardData } from "../types";

interface DashboardProps {
  userId: string;
  onNavigate: (screen: NavScreen) => void;
  onSend: () => void;
}

function formatXof(amount: number): string {
  return new Intl.NumberFormat("fr-FR").format(amount) + " F CFA";
}

function statusLabel(status: string): { text: string; className: string } {
  switch (status) {
    case "COMPLETED":
      return { text: "Terminée", className: "badge-success" };
    case "PENDING":
      return { text: "En cours", className: "badge-warning" };
    case "FAILED":
      return { text: "Échouée", className: "badge-danger" };
    case "BLOCKED":
      return { text: "Bloquée", className: "badge-danger" };
    default:
      return { text: status, className: "badge-neutral" };
  }
}

export function Dashboard({ userId, onNavigate, onSend }: DashboardProps) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDashboard(userId)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Impossible de charger le tableau de bord."));
  }, [userId]);

  if (error) {
    return (
      <div className="screen">
        <p className="error-banner">{error}</p>
        <BottomNav active="dashboard" onNavigate={onNavigate} />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="loading-screen">
        <span className="spinner" style={{ borderTopColor: "#1B3FA0", borderColor: "#e2e6f2" }} />
        Chargement de votre wallet…
      </div>
    );
  }

  return (
    <div className="screen">
      <div className="topbar">
        <div>
          <p className="eyebrow">Bonjour</p>
          <h1>{data.full_name}</h1>
        </div>
      </div>

      <div className="balance-card">
        <span className="label">Solde disponible</span>
        <span className="amount">{formatXof(data.balance)}</span>
        <span className="wallet-number">{data.wallet_number_masked}</span>
      </div>

      <div className={`security-status ${data.session_secured ? "" : "warning"}`}>
        <ShieldCheck size={18} aria-hidden="true" />
        <div>
          <strong>{data.session_secured ? "Session sécurisée" : "Session sous surveillance"}</strong>
          <div>
            {data.device_recognized ? "Appareil reconnu" : "Nouvel appareil"} · Dernière vérification :{" "}
            {data.last_verification_at ? new Date(data.last_verification_at).toLocaleString("fr-FR") : "—"}
          </div>
        </div>
      </div>

      <div className="quick-actions">
        <button type="button" className="quick-action" onClick={onSend}>
          <span className="icon-circle">
            <ArrowUpRight size={18} />
          </span>
          Envoyer
        </button>
        <button type="button" className="quick-action" onClick={() => onNavigate("history")}>
          <span className="icon-circle">
            <ArrowDownToLine size={18} />
          </span>
          Recharger
        </button>
        <button type="button" className="quick-action" onClick={() => onNavigate("history")}>
          <span className="icon-circle">
            <CreditCard size={18} />
          </span>
          Payer
        </button>
        <button type="button" className="quick-action" onClick={() => onNavigate("history")}>
          <span className="icon-circle">
            <Wallet size={18} />
          </span>
          Retirer
        </button>
      </div>

      <div className="card">
        <p className="eyebrow">Dernières opérations</p>
        {data.last_operations.length === 0 && <p className="summary">Aucune opération pour l'instant.</p>}
        {data.last_operations.map((op) => {
          const badge = statusLabel(op.status);
          return (
            <div className="list-row" key={op.id}>
              <div className="avatar">{op.type.slice(0, 2).toUpperCase()}</div>
              <div className="main">
                <strong>{formatXof(op.amount)}</strong>
                <span>{new Date(op.date).toLocaleDateString("fr-FR")}</span>
              </div>
              <span className={`badge ${badge.className}`}>{badge.text}</span>
            </div>
          );
        })}
      </div>

      <BottomNav active="dashboard" onNavigate={onNavigate} />
    </div>
  );
}
