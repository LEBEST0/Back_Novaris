import { FileText } from "lucide-react";
import { EngineBreakdown } from "../../components/EngineBreakdown";
import { RiskBadge } from "../../components/RiskBadge";
import { ScoreGauge } from "../../components/ScoreGauge";
import type { AnalystFeedback, TransactionAnalysis } from "../../types";
import { formatCurrency, formatDateTime, formatDecision } from "../../utils/format";

interface InvestigationProps {
  current: TransactionAnalysis;
  onReport: () => void;
  onFeedback: (feedback: AnalystFeedback, note?: string) => void;
}

export function Investigation({ current, onReport, onFeedback }: InvestigationProps) {
  const isActionableAlert = current.decision === "REVIEW" || current.decision === "TEMPORARY_BLOCK";
  const feedbackLabel = current.analyst_feedback === "CONFIRMED" ? "Alerte confirmée par l'analyste" : "Faux positif écarté";

  return (
    <section className="screen-stack">
      <div className="screen-heading">
        <div>
          <p className="eyebrow">Dossier investigation</p>
          <h1 className="mono">{current.transaction_id}</h1>
        </div>
        <button type="button" className="primary-action compact" onClick={onReport}>
          <FileText size={18} aria-hidden="true" />
          Générer le rapport
        </button>
      </div>

      <div className="investigation-grid">
        <article className="panel">
          <div className="panel-heading">
            <h2>Transaction</h2>
            <RiskBadge level={current.risk_level} />
          </div>
          <div className="detail-grid">
            <label>Émetteur<span className="mono">{current.sender_phone}</span></label>
            <label>Opérateur<span>{current.sender_operator}</span></label>
            <label>Pays émetteur<span>{current.sender_country}</span></label>
            <label>
              Identité émetteur
              <span className="mono">
                {current.sender_national_id
                  ? `${current.sender_national_id} (KYC ${current.sender_kyc_level})`
                  : `Non vérifiée (KYC ${current.sender_kyc_level})`}
              </span>
            </label>
            <label>Destinataire<span className="mono">{current.receiver_phone}</span></label>
            <label>Pays destinataire<span>{current.receiver_country ?? "Inconnu"}</span></label>
            <label>
              Identité destinataire
              <span className="mono">
                {current.receiver_national_id
                  ? `${current.receiver_national_id} (KYC ${current.receiver_kyc_level})`
                  : current.receiver_kyc_level
                    ? `Non vérifiée (KYC ${current.receiver_kyc_level})`
                    : "Client hors Clapay (inconnu)"}
              </span>
            </label>
            <label>Transfrontalier<span>{current.is_cross_border ? "Oui" : "Non"}</span></label>
            <label>Montant<span>{formatCurrency(current.amount, current.currency)}</span></label>
            <label>Type<span>{current.transaction_type}</span></label>
            <label>Canal<span>{current.channel}</span></label>
            <label>Décision<span>{formatDecision(current.decision)}</span></label>
            <label>Ville émetteur<span>{current.sender_city ?? "—"}</span></label>
            <label>Device<span className="mono">{current.device_id ?? "—"}</span></label>
            <label>Agent<span className="mono">{current.agent_id ?? "—"}</span></label>
            <label>Batch<span className="mono">{current.batch_id ?? "—"}</span></label>
            <label>Solde avant<span>{current.balance_before_sender !== null ? formatCurrency(current.balance_before_sender, current.currency) : "—"}</span></label>
            <label>Solde après<span>{current.balance_after_sender !== null ? formatCurrency(current.balance_after_sender, current.currency) : "—"}</span></label>
            <label>Calculé le<span>{formatDateTime(current.computed_at)}</span></label>
            <label>Modèle<span className="mono">{current.model_version}</span></label>
          </div>
        </article>

        <article className="panel">
          <ScoreGauge value={current.final_score} />
        </article>

        {isActionableAlert && (
          <article className="panel wide analyst-feedback-panel">
            <div className="panel-heading">
              <h2>Validation analyste</h2>
              <span>Contrôle humain avant décision finale</span>
            </div>
            {current.analyst_feedback ? (
              <div className={`feedback-state ${current.analyst_feedback === "CONFIRMED" ? "is-confirmed" : "is-false-positive"}`}>
                <strong>{feedbackLabel}</strong>
                {current.feedback_at && <span>{formatDateTime(current.feedback_at)}</span>}
                {current.feedback_note && <p>{current.feedback_note}</p>}
              </div>
            ) : (
              <div className="feedback-actions">
                <button type="button" className="feedback-button confirm" onClick={() => onFeedback("CONFIRMED", "Alerte confirmée pendant la revue analyste.")}>
                  Confirmer l'alerte
                </button>
                <button type="button" className="feedback-button false-positive" onClick={() => onFeedback("FALSE_POSITIVE", "Signal écarté après contrôle manuel.")}>
                  Marquer comme faux positif
                </button>
              </div>
            )}
          </article>
        )}

        <article className="panel wide">
          <div className="panel-heading">
            <h2>Décomposition du score</h2>
            <span>Règles auditables + modèle ML</span>
          </div>
          <EngineBreakdown ruleScore={current.rule_score} mlScore={current.ml_score} confidence={current.confidence} />
        </article>

        <article className="panel wide">
          <div className="panel-heading">
            <h2>Règles déclenchées</h2>
            <span>{current.rule_flags.length} règle(s)</span>
          </div>
          {current.rule_flags.length ? (
            <ul className="rule-flag-list">
              {current.rule_flags.map((flag) => (
                <li key={flag.code}>
                  <span className="mono">{flag.code}</span>
                  <span>{flag.description}</span>
                  <strong>+{flag.weight}</strong>
                </li>
              ))}
            </ul>
          ) : (
            <p className="summary">Aucune règle auditable déclenchée.</p>
          )}
        </article>

        <article className="panel wide">
          <div className="panel-heading">
            <h2>Explication SHAP (modèle ML)</h2>
            <span>Facteurs les plus contributifs</span>
          </div>
          {current.top_ml_factors.length ? (
            <ul className="reason-list columns">
              {current.top_ml_factors.map((factor) => <li key={factor}>{factor}</li>)}
            </ul>
          ) : (
            <p className="summary">Pas de facteur ML dominant identifié.</p>
          )}
        </article>

        <article className="panel wide">
          <div className="panel-heading">
            <h2>Causes détectées (règles + ML fusionnées)</h2>
            <span>{current.reasons.length} signaux</span>
          </div>
          <ul className="reason-list columns">
            {current.reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        </article>
      </div>
    </section>
  );
}
