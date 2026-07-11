import { useState } from "react";
import { Play, ShieldAlert } from "lucide-react";
import { PresetSelector, type PresetKey } from "../../components/PresetSelector";
import { ScoreGauge } from "../../components/ScoreGauge";
import { EngineBreakdown } from "../../components/EngineBreakdown";
import { RiskBadge } from "../../components/RiskBadge";
import { CHANNELS, CHANNEL_LABELS, TRANSACTION_TYPES, TRANSACTION_TYPE_LABELS } from "../../constants";
import type { TransactionAnalysis, TransactionRequest } from "../../types";
import { formatCurrency, formatDecision } from "../../utils/format";

interface AnalysisProps {
  current: TransactionAnalysis | null;
  submitting: boolean;
  error: string | null;
  onAnalyze: (payload: TransactionRequest) => void;
  onOpenInvestigation: () => void;
}

const CI_PREFIX_GROUPS = [["01", "02", "03"], ["05", "06"], ["07", "08", "09"]];

function randomCiPhone(): string {
  const group = CI_PREFIX_GROUPS[Math.floor(Math.random() * CI_PREFIX_GROUPS.length)];
  const prefix = group[Math.floor(Math.random() * group.length)];
  const suffix = Array.from({ length: 8 }, () => Math.floor(Math.random() * 10)).join("");
  return `+225${prefix}${suffix}`;
}

function buildPresetPayload(preset: PresetKey): TransactionRequest {
  const base: TransactionRequest = {
    sender_phone: randomCiPhone(),
    receiver_phone: randomCiPhone(),
    amount: 12000,
    currency: "XOF",
    transaction_type: "transfer",
    channel: "mobile_app",
    device_id: `DEV-${Math.floor(Math.random() * 90000 + 10000)}`,
    sender_city: "Abidjan",
    timestamp: null,
  };

  if (preset === "suspect") {
    return { ...base, amount: 150000, channel: "web" };
  }
  if (preset === "critique") {
    const night = new Date();
    night.setHours(2, 15, 0, 0);
    return { ...base, amount: 950000, channel: "web", timestamp: night.toISOString() };
  }
  return base;
}

export function Analysis({ current, submitting, error, onAnalyze, onOpenInvestigation }: AnalysisProps) {
  const [preset, setPreset] = useState<PresetKey>("normal");
  const [form, setForm] = useState<TransactionRequest>(() => buildPresetPayload("normal"));

  const handlePreset = (nextPreset: PresetKey) => {
    setPreset(nextPreset);
    setForm(buildPresetPayload(nextPreset));
  };

  const update = <K extends keyof TransactionRequest>(key: K, value: TransactionRequest[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    onAnalyze(form);
  };

  return (
    <section className="screen-stack">
      <div className="screen-heading">
        <div>
          <p className="eyebrow">Analyse transaction</p>
          <h1>Déclencher une analyse</h1>
        </div>
        <PresetSelector value={preset} onChange={handlePreset} />
      </div>

      <div className="analysis-grid">
        <article className="panel form-panel">
          <div className="panel-heading">
            <h2>Transaction à analyser</h2>
            <span className="mono">POST /api/v1/transactions/analyze</span>
          </div>
          <form className="detail-grid" onSubmit={handleSubmit}>
            <label>
              Numéro émetteur
              <input value={form.sender_phone} onChange={(e) => update("sender_phone", e.target.value)} required />
            </label>
            <label>
              Numéro destinataire
              <input value={form.receiver_phone} onChange={(e) => update("receiver_phone", e.target.value)} required />
            </label>
            <label>
              Montant
              <input
                type="number"
                min={1}
                value={form.amount}
                onChange={(e) => update("amount", Number(e.target.value))}
                required
              />
            </label>
            <label>
              Type de transaction
              <select value={form.transaction_type} onChange={(e) => update("transaction_type", e.target.value)}>
                {TRANSACTION_TYPES.map((type) => (
                  <option key={type} value={type}>{TRANSACTION_TYPE_LABELS[type]}</option>
                ))}
              </select>
            </label>
            <label>
              Canal
              <select value={form.channel ?? "mobile_app"} onChange={(e) => update("channel", e.target.value)}>
                {CHANNELS.map((channel) => (
                  <option key={channel} value={channel}>{CHANNEL_LABELS[channel]}</option>
                ))}
              </select>
            </label>
            <label>
              Ville émetteur
              <input value={form.sender_city ?? ""} onChange={(e) => update("sender_city", e.target.value || null)} />
            </label>
            <label>
              Device
              <input value={form.device_id ?? ""} onChange={(e) => update("device_id", e.target.value || null)} />
            </label>

            <details className="advanced-fields">
              <summary>Champs avancés (batch, agent, soldes)</summary>
              <div className="detail-grid">
                <label>
                  Batch ID
                  <input value={form.batch_id ?? ""} onChange={(e) => update("batch_id", e.target.value || null)} />
                </label>
                <label>
                  Agent ID
                  <input value={form.agent_id ?? ""} onChange={(e) => update("agent_id", e.target.value || null)} />
                </label>
                <label>
                  Solde avant (émetteur)
                  <input
                    type="number"
                    value={form.balance_before_sender ?? ""}
                    onChange={(e) => update("balance_before_sender", e.target.value ? Number(e.target.value) : null)}
                  />
                </label>
                <label>
                  Solde après (émetteur)
                  <input
                    type="number"
                    value={form.balance_after_sender ?? ""}
                    onChange={(e) => update("balance_after_sender", e.target.value ? Number(e.target.value) : null)}
                  />
                </label>
              </div>
            </details>

            {error && <p className="form-error">{error}</p>}

            <button className="primary-action" type="submit" disabled={submitting}>
              <Play size={18} aria-hidden="true" />
              {submitting ? "Analyse en cours..." : "Analyser"}
            </button>
          </form>
        </article>

        <article className="panel result-panel">
          {current ? (
            <>
              <div className="result-header">
                <ShieldAlert aria-hidden="true" />
                <div>
                  <p className="eyebrow">Résultat</p>
                  <h2>{formatDecision(current.decision)}</h2>
                </div>
                <RiskBadge level={current.risk_level} />
              </div>
              <div className="score-pair">
                <ScoreGauge value={current.final_score} />
              </div>
              <EngineBreakdown ruleScore={current.rule_score} mlScore={current.ml_score} confidence={current.confidence} />
              <ul className="reason-list">
                {current.reasons.slice(0, 5).map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
              <p className="summary mono">
                {current.transaction_id} · {formatCurrency(current.amount, current.currency)}
              </p>
              <button type="button" className="primary-action compact" onClick={onOpenInvestigation}>
                Voir le dossier complet
              </button>
            </>
          ) : (
            <p className="summary">Aucune analyse pour l'instant. Choisissez un profil ou remplissez le formulaire, puis cliquez sur Analyser.</p>
          )}
        </article>
      </div>
    </section>
  );
}
