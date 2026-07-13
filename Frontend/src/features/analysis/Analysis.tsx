import { useEffect, useRef, useState } from "react";
import { Play, ShieldAlert, X } from "lucide-react";
import { PresetSelector, type PresetKey } from "../../components/PresetSelector";
import { ScoreGauge } from "../../components/ScoreGauge";
import { EngineBreakdown } from "../../components/EngineBreakdown";
import { RiskBadge } from "../../components/RiskBadge";
import { CHANNELS, CHANNEL_LABELS, TRANSACTION_TYPES, TRANSACTION_TYPE_LABELS } from "../../constants";
import { analyzeTransaction, searchCustomers } from "../../services/api";
import type { Customer, TransactionAnalysis, TransactionRequest } from "../../types";
import { formatCurrency, formatDecision } from "../../utils/format";

interface AnalysisProps {
  current: TransactionAnalysis | null;
  submitting: boolean;
  error: string | null;
  onAnalyze: (payload: TransactionRequest) => void;
  onAnalysisComplete: (analysis: TransactionAnalysis) => void;
  onOpenInvestigation: () => void;
}

const CI_PREFIX_GROUPS = [["01", "02", "03"], ["05", "06"], ["07", "08", "09"]];
const DEMO_AGENT_ID = "AGT-CI-00187";

function randomCiPhone(): string {
  const group = CI_PREFIX_GROUPS[Math.floor(Math.random() * CI_PREFIX_GROUPS.length)];
  const prefix = group[Math.floor(Math.random() * group.length)];
  const suffix = Array.from({ length: 8 }, () => Math.floor(Math.random() * 10)).join("");
  return `+225${prefix}${suffix}`;
}

function randomDeviceId(): string {
  return `DEV-${Math.floor(Math.random() * 90000 + 10000)}`;
}

function buildPresetPayload(preset: PresetKey): TransactionRequest {
  const base: TransactionRequest = {
    sender_phone: randomCiPhone(),
    receiver_phone: randomCiPhone(),
    amount: 12000,
    currency: "XOF",
    transaction_type: "transfer",
    channel: "mobile_app",
    device_id: randomDeviceId(),
    sender_city: "Abidjan",
    timestamp: null,
    behaviour_time_to_complete_ms: 9000,
    behaviour_amount_field_edits: 1,
  };

  if (preset === "suspect") {
    // UNKNOWN_RECEIVER_HIGH_AMOUNT : montant élevé vers un inconnu, léger flottement de saisie.
    return { ...base, amount: 180000, behaviour_amount_field_edits: 4 };
  }
  if (preset === "critique") {
    // Le scénario critique (compte mule) se joue en plusieurs étapes — cf. runMuleChain.
    return base;
  }
  return base;
}

/** Rejoue 3 cycles dépôt (agence) -> retrait rapide, même agent, resserrés dans le temps :
 * déclenche MULE_PASSTHROUGH_PATTERN + HIGH_VELOCITY + STRUCTURING_SUSPECTED ensemble
 * (rule_score >= 80 -> plancher critique -> TEMPORARY_BLOCK garanti). Chaque étape est une
 * vraie analyse persistée (visible dans le dashboard/graphe), seule la dernière devient le
 * résultat affiché. */
async function runMuleChain(onProgress: (message: string) => void): Promise<TransactionAnalysis> {
  const phone = randomCiPhone();
  const baseTs = Date.now();
  let lastAnalysis: TransactionAnalysis | null = null;

  for (let cycle = 0; cycle < 3; cycle++) {
    const cycleStartMs = baseTs + cycle * 5 * 60 * 1000;
    onProgress(`Cycle ${cycle + 1}/3 — dépôt en agence...`);
    await analyzeTransaction({
      sender_phone: phone,
      receiver_phone: phone,
      amount: 180000,
      transaction_type: "deposit",
      channel: "agent",
      agent_id: DEMO_AGENT_ID,
      timestamp: new Date(cycleStartMs).toISOString(),
      behaviour_time_to_complete_ms: 1800,
      behaviour_amount_field_edits: 0,
    });

    onProgress(`Cycle ${cycle + 1}/3 — retrait rapide...`);
    lastAnalysis = await analyzeTransaction({
      sender_phone: phone,
      receiver_phone: phone,
      amount: 175000,
      transaction_type: "withdrawal",
      channel: "agent",
      agent_id: DEMO_AGENT_ID,
      timestamp: new Date(cycleStartMs + 2 * 60 * 1000).toISOString(),
      behaviour_time_to_complete_ms: 1500,
      behaviour_amount_field_edits: 0,
    });
  }

  return lastAnalysis!;
}

export function Analysis({ current, submitting, error, onAnalyze, onAnalysisComplete, onOpenInvestigation }: AnalysisProps) {
  const [preset, setPreset] = useState<PresetKey>("normal");
  const [form, setForm] = useState<TransactionRequest>(() => buildPresetPayload("normal"));
  const [chainRunning, setChainRunning] = useState(false);
  const [chainProgress, setChainProgress] = useState<string | null>(null);
  const [chainError, setChainError] = useState<string | null>(null);

  // Sélection d'un compte réel de la base, pour tester avec un historique/profil existant
  // plutôt que des numéros générés au hasard.
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Customer[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [deviceMode, setDeviceMode] = useState<"known" | "new">("new");
  const searchTimer = useRef<number | null>(null);

  useEffect(() => {
    if (searchTimer.current) window.clearTimeout(searchTimer.current);
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    searchTimer.current = window.setTimeout(() => {
      searchCustomers(query.trim()).then(setResults).catch(() => setResults([]));
    }, 300);
    return () => {
      if (searchTimer.current) window.clearTimeout(searchTimer.current);
    };
  }, [query]);

  const handlePreset = (nextPreset: PresetKey) => {
    setPreset(nextPreset);
    setChainError(null);
    setForm(buildPresetPayload(nextPreset));
  };

  const update = <K extends keyof TransactionRequest>(key: K, value: TransactionRequest[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleTransactionTypeChange = (type: string) => {
    setForm((prev) => {
      if (type === "transfer") return { ...prev, transaction_type: type, channel: "mobile_app", agent_id: null };
      if (type === "withdrawal") return { ...prev, transaction_type: type, channel: "agent", agent_id: prev.agent_id || DEMO_AGENT_ID };
      return { ...prev, transaction_type: type };
    });
  };

  const selectCustomer = (customer: Customer) => {
    setSelectedCustomer(customer);
    setQuery("");
    setResults([]);
    setDeviceMode(customer.last_device_id ? "known" : "new");
    update("sender_phone", customer.phone);
    update("sender_city", customer.home_city);
    update("device_id", customer.last_device_id ?? randomDeviceId());
  };

  const clearCustomer = () => {
    setSelectedCustomer(null);
    setDeviceMode("new");
  };

  const handleDeviceMode = (mode: "known" | "new") => {
    setDeviceMode(mode);
    if (mode === "known" && selectedCustomer?.last_device_id) {
      update("device_id", selectedCustomer.last_device_id);
    } else {
      update("device_id", randomDeviceId());
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setChainError(null);
    if (preset === "critique") {
      setChainRunning(true);
      try {
        const finalAnalysis = await runMuleChain(setChainProgress);
        onAnalysisComplete(finalAnalysis);
      } catch (err) {
        setChainError(err instanceof Error ? err.message : "Impossible de dérouler le scénario mule.");
      } finally {
        setChainRunning(false);
        setChainProgress(null);
      }
      return;
    }
    onAnalyze(form);
  };

  const showAgentField = form.channel === "agent";

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

          {preset === "critique" ? (
            <div className="detail-grid">
              <p className="summary" style={{ gridColumn: "1 / -1" }}>
                Scénario compte mule : 3 cycles dépôt (agence) → retrait rapide, même agent,
                resserrés dans le temps. Chaque étape est une vraie analyse persistée
                (visible dans le dashboard/graphe) ; le dernier retrait est celui affiché
                ci-contre, avec <code>MULE_PASSTHROUGH_PATTERN</code> déclenchée.
              </p>
              {chainProgress && <p className="chain-progress">{chainProgress}</p>}
              {chainError && <p className="form-error">{chainError}</p>}
              <button className="primary-action" type="button" onClick={handleSubmit} disabled={chainRunning}>
                <Play size={18} aria-hidden="true" />
                {chainRunning ? "Scénario en cours..." : "Lancer le scénario mule"}
              </button>
            </div>
          ) : (
            <form className="detail-grid" onSubmit={handleSubmit}>
              <div className="customer-search">
                <label>
                  Compte existant (optionnel)
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Rechercher par numéro ou nom..."
                  />
                </label>
                {results.length > 0 && (
                  <div className="customer-search-results">
                    {results.map((customer) => (
                      <button
                        key={customer.phone}
                        type="button"
                        className="customer-search-result"
                        onClick={() => selectCustomer(customer)}
                      >
                        <strong>{customer.full_name}</strong>
                        <small className="mono">
                          {customer.phone} · {customer.country} · KYC {customer.kyc_level}
                        </small>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {selectedCustomer && (
                <div className="selected-customer-chip">
                  <span>
                    <strong>{selectedCustomer.full_name}</strong>{" "}
                    <span className="mono">{selectedCustomer.phone}</span> · {selectedCustomer.customer_type}
                  </span>
                  <button type="button" onClick={clearCustomer}>
                    <X size={14} aria-hidden="true" /> Effacer
                  </button>
                </div>
              )}

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
                <select value={form.transaction_type} onChange={(e) => handleTransactionTypeChange(e.target.value)}>
                  {TRANSACTION_TYPES.map((type) => (
                    <option key={type} value={type}>{TRANSACTION_TYPE_LABELS[type]}</option>
                  ))}
                </select>
              </label>
              <label>
                Canal
                <select
                  value={form.channel ?? "mobile_app"}
                  onChange={(e) => update("channel", e.target.value)}
                  disabled={form.transaction_type !== "deposit"}
                >
                  {CHANNELS.map((channel) => (
                    <option key={channel} value={channel}>{CHANNEL_LABELS[channel]}</option>
                  ))}
                </select>
              </label>
              {showAgentField && (
                <label>
                  Agent ID
                  <input value={form.agent_id ?? ""} onChange={(e) => update("agent_id", e.target.value || null)} required />
                </label>
              )}
              <label>
                Ville émetteur
                <input value={form.sender_city ?? ""} onChange={(e) => update("sender_city", e.target.value || null)} />
              </label>

              <div className="behaviour-toggle">
                <button
                  type="button"
                  className={deviceMode === "known" ? "is-active" : ""}
                  onClick={() => handleDeviceMode("known")}
                  disabled={!selectedCustomer?.last_device_id}
                  title={!selectedCustomer?.last_device_id ? "Aucun appareil connu pour ce client" : undefined}
                >
                  Appareil connu
                </button>
                <button
                  type="button"
                  className={deviceMode === "new" ? "is-active" : ""}
                  onClick={() => handleDeviceMode("new")}
                >
                  Nouvel appareil
                </button>
              </div>
              <label>
                Device ID
                <input value={form.device_id ?? ""} onChange={(e) => update("device_id", e.target.value || null)} />
              </label>

              <details className="advanced-fields">
                <summary>Comportement sur Amani Wallet + champs avancés</summary>
                <div className="detail-grid">
                  <label>
                    Temps de saisie (ms)
                    <input
                      type="number"
                      min={0}
                      value={form.behaviour_time_to_complete_ms ?? ""}
                      onChange={(e) => update("behaviour_time_to_complete_ms", e.target.value ? Number(e.target.value) : null)}
                    />
                  </label>
                  <label>
                    Modifications du montant
                    <input
                      type="number"
                      min={0}
                      value={form.behaviour_amount_field_edits ?? ""}
                      onChange={(e) => update("behaviour_amount_field_edits", e.target.value ? Number(e.target.value) : null)}
                    />
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
                  <label>
                    Note
                    <input value={form.note ?? ""} onChange={(e) => update("note", e.target.value || null)} />
                  </label>
                </div>
              </details>

              {error && <p className="form-error">{error}</p>}

              <button className="primary-action" type="submit" disabled={submitting}>
                <Play size={18} aria-hidden="true" />
                {submitting ? "Analyse en cours..." : "Analyser"}
              </button>
            </form>
          )}
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
