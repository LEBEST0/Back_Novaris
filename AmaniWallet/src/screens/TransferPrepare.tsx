import { useState } from "react";
import { ArrowLeft, CheckCircle2 } from "lucide-react";
import { prepareTransfer } from "../lib/api";
import type { Beneficiary, TransferPrepareResult } from "../types";

interface TransferPrepareProps {
  userId: string;
  beneficiary: Beneficiary | null;
  onBack: () => void;
  onChooseBeneficiary: () => void;
  onDone: () => void;
}

function formatXof(amount: number): string {
  return new Intl.NumberFormat("fr-FR").format(amount) + " F CFA";
}

export function TransferPrepare({ userId, beneficiary, onBack, onChooseBeneficiary, onDone }: TransferPrepareProps) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [recap, setRecap] = useState<TransferPrepareResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!beneficiary) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await prepareTransfer({
        user_id: userId,
        beneficiary_id: beneficiary.id,
        amount: Number(amount),
        reason: reason || undefined,
      });
      setRecap(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible de préparer ce transfert.");
    } finally {
      setSubmitting(false);
    }
  };

  if (recap) {
    return (
      <div className="screen no-nav">
        <div className="topbar">
          <button type="button" className="link-button" onClick={onDone}>
            <ArrowLeft size={16} style={{ verticalAlign: "-2px" }} /> Terminer
          </button>
        </div>
        <div className="verify-hero">
          <span className="icon-badge" style={{ background: "#e8f6ef", color: "#2f9e6f" }}>
            <CheckCircle2 size={30} />
          </span>
          <h1 style={{ fontSize: 18, margin: 0 }}>Récapitulatif du transfert</h1>
        </div>
        <div className="card detail-grid">
          <div className="row"><span>Bénéficiaire</span><span>{recap.beneficiary_name}</span></div>
          <div className="row"><span>Wallet</span><span className="mono">{recap.beneficiary_wallet_masked}</span></div>
          <div className="row"><span>Montant</span><span>{formatXof(recap.amount)}</span></div>
          {recap.reason && <div className="row"><span>Motif</span><span>{recap.reason}</span></div>}
          <div className="row"><span>Frais estimés</span><span>{formatXof(recap.fee_estimate)}</span></div>
          <div className="row"><span><strong>Total à débiter</strong></span><span><strong>{formatXof(recap.total_debit)}</strong></span></div>
        </div>
        <p className="summary">{recap.note}</p>
        <button type="button" className="btn btn-primary btn-block" onClick={onDone}>
          Retour au tableau de bord
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
      <h1 style={{ fontSize: 20 }}>Envoyer de l'argent</h1>

      <div className="card">
        <p className="eyebrow">Bénéficiaire</p>
        {beneficiary ? (
          <div className="list-row" style={{ borderBottom: "none", padding: "6px 0" }}>
            <div className="avatar">{beneficiary.full_name.slice(0, 2).toUpperCase()}</div>
            <div className="main">
              <strong>{beneficiary.full_name}</strong>
              <span className="mono">{beneficiary.phone_masked}</span>
            </div>
            <button type="button" className="link-button" onClick={onChooseBeneficiary}>
              Changer
            </button>
          </div>
        ) : (
          <button type="button" className="btn btn-secondary btn-block" onClick={onChooseBeneficiary}>
            Choisir un bénéficiaire
          </button>
        )}
      </div>

      <form className="screen" style={{ padding: 0, gap: 16 }} onSubmit={handleSubmit}>
        <div className="field">
          <label>Montant (F CFA)</label>
          <input type="number" min={1} value={amount} onChange={(e) => setAmount(e.target.value)} required />
        </div>
        <div className="field">
          <label>Motif (optionnel)</label>
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Ex : loyer, dépannage..." />
        </div>
        {error && <p className="error-banner">{error}</p>}
        <button className="btn btn-primary btn-block" type="submit" disabled={!beneficiary || submitting}>
          {submitting ? "Préparation..." : "Continuer"}
        </button>
      </form>
    </div>
  );
}
