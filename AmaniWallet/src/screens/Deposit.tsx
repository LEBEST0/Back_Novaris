import { useEffect, useRef, useState } from "react";
import { ArrowLeft, CheckCircle2, AlertTriangle, Clock } from "lucide-react";
import { depositFunds, fetchAgents } from "../lib/api";
import type { Agent, CashOperationResult } from "../types";

interface DepositProps {
  userId: string;
  onBack: () => void;
  onDone: () => void;
}

function formatXof(amount: number): string {
  return new Intl.NumberFormat("fr-FR").format(amount) + " F CFA";
}

const STATUS_STYLE: Record<CashOperationResult["status"], { bg: string; color: string; icon: typeof CheckCircle2; title: string }> = {
  COMPLETED: { bg: "#e8f6ef", color: "#2f9e6f", icon: CheckCircle2, title: "Dépôt effectué" },
  PENDING: { bg: "#fdf1de", color: "#c97a12", icon: Clock, title: "Vérification en cours" },
  BLOCKED: { bg: "#fbe9e9", color: "#c23b3b", icon: AlertTriangle, title: "Dépôt non abouti" },
};

export function Deposit({ userId, onBack, onDone }: DepositProps) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [source, setSource] = useState<"agent" | "external_momo">("agent");
  const [agentId, setAgentId] = useState("");
  const [amount, setAmount] = useState("");
  const [recap, setRecap] = useState(false);
  const [result, setResult] = useState<CashOperationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  // Comportement observé côté client pour CETTE opération, envoyé à Novaris avec la
  // transaction (cf. TRANSACTION_BEHAVIOUR_ANOMALY et MULE_PASSTHROUGH_PATTERN côté backend).
  const formOpenedAt = useRef(Date.now());
  const amountEditCount = useRef(0);

  useEffect(() => {
    fetchAgents()
      .then((list) => {
        setAgents(list);
        if (list.length) setAgentId(list[0].agent_id);
      })
      .catch(() => setAgents([]));
  }, []);

  const handleAmountChange = (value: string) => {
    amountEditCount.current += 1;
    setAmount(value);
  };

  const handleContinue = (event: React.FormEvent) => {
    event.preventDefault();
    if (source === "agent" && !agentId) return;
    setRecap(true);
  };

  const handleConfirm = async () => {
    setConfirming(true);
    setError(null);
    try {
      const response = await depositFunds({
        user_id: userId,
        amount: Number(amount),
        source,
        agent_id: source === "agent" ? agentId : null,
        behaviour_time_to_complete_ms: Date.now() - formOpenedAt.current,
        behaviour_amount_field_edits: amountEditCount.current,
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible de confirmer ce dépôt.");
    } finally {
      setConfirming(false);
    }
  };

  if (result) {
    const style = STATUS_STYLE[result.status];
    const Icon = style.icon;
    return (
      <div className="screen no-nav">
        <div className="verify-hero">
          <span className="icon-badge" style={{ background: style.bg, color: style.color }}>
            <Icon size={30} />
          </span>
          <h1 style={{ fontSize: 18, margin: 0 }}>{style.title}</h1>
          <p className="summary">{result.message}</p>
        </div>
        <button type="button" className="btn btn-primary btn-block" onClick={onDone}>
          Retour au tableau de bord
        </button>
      </div>
    );
  }

  if (recap) {
    const selectedAgent = agents.find((a) => a.agent_id === agentId);
    return (
      <div className="screen no-nav">
        <div className="topbar">
          <button type="button" className="link-button" onClick={() => setRecap(false)}>
            <ArrowLeft size={16} style={{ verticalAlign: "-2px" }} /> Modifier
          </button>
        </div>
        <div className="verify-hero">
          <span className="icon-badge" style={{ background: "#e8f6ef", color: "#2f9e6f" }}>
            <CheckCircle2 size={30} />
          </span>
          <h1 style={{ fontSize: 18, margin: 0 }}>Récapitulatif du dépôt</h1>
        </div>
        <div className="card detail-grid">
          <div className="row">
            <span>Source</span>
            <span>{source === "agent" ? "Dépôt en agence" : "Compte Mobile money externe"}</span>
          </div>
          {source === "agent" && (
            <div className="row"><span>Agence</span><span>{selectedAgent?.name ?? agentId}</span></div>
          )}
          <div className="row"><span>Montant</span><span>{formatXof(Number(amount))}</span></div>
        </div>
        {error && <p className="error-banner">{error}</p>}
        <button type="button" className="btn btn-primary btn-block" onClick={handleConfirm} disabled={confirming}>
          {confirming ? "Envoi en cours..." : "Confirmer le dépôt"}
        </button>
        <button type="button" className="btn btn-secondary btn-block" onClick={onDone}>
          Annuler
        </button>
      </div>
    );
  }

  return (
    <div className="screen no-nav">
      <div className="topbar">
        <button type="button" className="link-button" onClick={onBack}>
          <ArrowLeft size={16} style={{ verticalAlign: "-2px" }} /> Retour
        </button>
      </div>
      <h1 style={{ fontSize: 20 }}>Recharger mon wallet</h1>

      <form className="screen" style={{ padding: 0, gap: 16 }} onSubmit={handleContinue}>
        <div className="field">
          <label>Provenance du dépôt</label>
          <select value={source} onChange={(e) => setSource(e.target.value as "agent" | "external_momo")}>
            <option value="agent">En agence (cash)</option>
            <option value="external_momo">Depuis un compte Mobile money externe</option>
          </select>
        </div>
        {source === "agent" && (
          <div className="field">
            <label>Agence</label>
            <select value={agentId} onChange={(e) => setAgentId(e.target.value)} required>
              {agents.map((a) => (
                <option key={a.agent_id} value={a.agent_id}>{a.name}</option>
              ))}
            </select>
          </div>
        )}
        <div className="field">
          <label>Montant (F CFA)</label>
          <input type="number" min={1} value={amount} onChange={(e) => handleAmountChange(e.target.value)} required />
        </div>
        <button className="btn btn-primary btn-block" type="submit" disabled={source === "agent" && !agentId}>
          Continuer
        </button>
      </form>
    </div>
  );
}
