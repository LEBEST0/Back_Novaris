import { Download, Printer } from "lucide-react";
import { EngineBreakdown } from "../../components/EngineBreakdown";
import { RiskBadge } from "../../components/RiskBadge";
import type { TransactionAnalysis } from "../../types";
import { formatCurrency, formatDateTime, formatDecision } from "../../utils/format";

interface ReportProps {
  current: TransactionAnalysis;
}

export function Report({ current }: ReportProps) {
  return (
    <section className="screen-stack report-screen">
      <div className="screen-heading no-print">
        <div>
          <p className="eyebrow">Rapport exportable</p>
          <h1>Dossier imprimable</h1>
        </div>
        <button type="button" className="primary-action compact" onClick={() => window.print()}>
          <Printer size={18} aria-hidden="true" />
          Imprimer
        </button>
      </div>

      <article className="report-page">
        <header className="report-header">
          <div>
            <p>Novaris AI</p>
            <h2>Rapport d'investigation</h2>
          </div>
          <RiskBadge level={current.risk_level} />
        </header>

        <div className="report-summary">
          <div>
            <span>Transaction</span>
            <strong className="mono">{current.transaction_id}</strong>
          </div>
          <div>
            <span>Décision</span>
            <strong>{formatDecision(current.decision)}</strong>
          </div>
          <div>
            <span>Score final</span>
            <strong>{current.final_score.toFixed(1)}/100</strong>
          </div>
          <div>
            <span>Confiance</span>
            <strong>{(current.confidence * 100).toFixed(0)}%</strong>
          </div>
        </div>

        <section className="report-section">
          <h3>Informations clés</h3>
          <div className="detail-grid">
            <label>Émetteur<span className="mono">{current.sender_phone}</span></label>
            <label>Opérateur<span>{current.sender_operator}</span></label>
            <label>Destinataire<span className="mono">{current.receiver_phone}</span></label>
            <label>Montant<span>{formatCurrency(current.amount, current.currency)}</span></label>
            <label>Type<span>{current.transaction_type}</span></label>
            <label>Canal<span>{current.channel}</span></label>
            <label>Agent<span className="mono">{current.agent_id ?? "—"}</span></label>
            <label>Device<span className="mono">{current.device_id ?? "—"}</span></label>
            <label>Transfrontalier<span>{current.is_cross_border ? "Oui" : "Non"}</span></label>
            <label>Calculé le<span>{formatDateTime(current.computed_at)}</span></label>
          </div>
        </section>

        <section className="report-section">
          <h3>Règles déclenchées</h3>
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
            <p>Aucune règle auditable déclenchée.</p>
          )}
        </section>

        <section className="report-section">
          <h3>Explication SHAP</h3>
          <ul className="reason-list">
            {current.top_ml_factors.length
              ? current.top_ml_factors.map((factor) => <li key={factor}>{factor}</li>)
              : <li>Pas de facteur ML dominant identifié.</li>}
          </ul>
        </section>

        <section className="report-section">
          <h3>Causes détectées</h3>
          <ul className="reason-list">
            {current.reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        </section>

        <section className="report-section">
          <h3>Décomposition du score</h3>
          <EngineBreakdown ruleScore={current.rule_score} mlScore={current.ml_score} confidence={current.confidence} />
        </section>

        {current.analyst_feedback && (
          <section className="report-section">
            <h3>Feedback analyste</h3>
            <p>
              {current.analyst_feedback === "CONFIRMED" ? "Alerte confirmée" : "Faux positif"}
              {current.feedback_at ? ` — ${formatDateTime(current.feedback_at)}` : ""}
            </p>
            {current.feedback_note && <p>{current.feedback_note}</p>}
          </section>
        )}

        <footer className="report-footer">
          <Download size={16} aria-hidden="true" />
          Dossier généré depuis les données réelles du moteur Novaris AI.
        </footer>
      </article>
    </section>
  );
}
