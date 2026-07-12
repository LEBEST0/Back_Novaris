import { useState } from "react";
import { FraudGraph } from "./FraudGraph";
import { NetworkGraph } from "./NetworkGraph";
import type { TransactionAnalysis } from "../../types";

interface GraphScreenProps {
  current: TransactionAnalysis | null;
  onSelectTransaction: (transactionId: string) => void;
}

type Tab = "network" | "single";

export function GraphScreen({ current, onSelectTransaction }: GraphScreenProps) {
  const [tab, setTab] = useState<Tab>("network");

  const handleSelectTransaction = (transactionId: string) => {
    onSelectTransaction(transactionId);
    setTab("single");
  };

  if (tab === "single") {
    return (
      <section className="screen-stack">
        <div className="graph-tabs">
          <button type="button" className="" onClick={() => setTab("network")}>
            ← Retour au réseau complet
          </button>
        </div>
        {current ? <FraudGraph current={current} /> : <div className="panel loading-panel">Aucune transaction sélectionnée.</div>}
      </section>
    );
  }

  return (
    <section className="screen-stack">
      <div className="screen-heading">
        <div>
          <p className="eyebrow">Graphe transactionnel</p>
          <h1>Réseau complet</h1>
        </div>
        <div className="graph-tabs">
          <button type="button" className="is-active">Réseau complet</button>
          <button type="button" onClick={() => setTab("single")} disabled={!current}>
            Transaction sélectionnée
          </button>
        </div>
      </div>
      <p>Toutes les transactions de la base. Cliquez sur un lien pour ouvrir son détail ; survolez un nœud pour ses informations.</p>

      <article className="panel graph-panel">
        <NetworkGraph onSelectTransaction={handleSelectTransaction} />
      </article>
    </section>
  );
}
