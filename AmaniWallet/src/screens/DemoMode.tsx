import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { fetchDemoScenarios } from "../lib/api";
import type { DemoScenario } from "../types";

interface DemoModeProps {
  active: DemoScenario | null;
  onSelect: (scenario: DemoScenario | null) => void;
  onClose: () => void;
}

export function DemoMode({ active, onSelect, onClose }: DemoModeProps) {
  const [scenarios, setScenarios] = useState<DemoScenario[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDemoScenarios()
      .then(setScenarios)
      .catch((err) => setError(err instanceof Error ? err.message : "Impossible de charger les scénarios."));
  }, []);

  return (
    <div className="screen no-nav">
      <div className="topbar">
        <button type="button" className="link-button" onClick={onClose}>
          <ArrowLeft size={16} style={{ verticalAlign: "-2px" }} /> Fermer
        </button>
      </div>
      <div>
        <p className="eyebrow">Accès réservé — présentation Novaris AI</p>
        <h1 style={{ fontSize: 20 }}>Mode démonstration</h1>
      </div>
      <p className="summary">
        Choisissez un scénario pour la prochaine tentative de connexion. Le comportement redevient normal
        (appareil de confiance) si vous n'en sélectionnez aucun.
      </p>

      {error && <p className="error-banner">{error}</p>}

      <div className="demo-scenario-list">
        <button
          type="button"
          className={`demo-scenario-item ${active === null ? "is-active" : ""}`}
          onClick={() => onSelect(null)}
        >
          <strong>NORMAL_USER (par défaut)</strong>
          <span>Appareil habituel, localisation cohérente — accès attendu : ALLOW.</span>
        </button>
        {scenarios.map((scenario) => (
          <button
            key={scenario.name}
            type="button"
            className={`demo-scenario-item ${active?.name === scenario.name ? "is-active" : ""}`}
            onClick={() => onSelect(scenario)}
          >
            <strong>{scenario.name}</strong>
            <span>{scenario.description}</span>
          </button>
        ))}
      </div>

      <button type="button" className="btn btn-primary btn-block" onClick={onClose}>
        Retour à la connexion
      </button>
    </div>
  );
}
