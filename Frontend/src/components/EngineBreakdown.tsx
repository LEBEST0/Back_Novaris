interface EngineBreakdownProps {
  ruleScore: number;
  mlScore: number;
  confidence: number;
}

export function EngineBreakdown({ ruleScore, mlScore, confidence }: EngineBreakdownProps) {
  const rows = [
    { key: "rules", label: "Moteur de règles (auditable)", score: ruleScore },
    { key: "ml", label: "Modèle ML (XGBoost)", score: mlScore },
  ];

  return (
    <div className="module-list">
      {rows.map((row) => (
        <div className="module-score" key={row.key}>
          <div>
            <span>{row.label}</span>
            <strong>{row.score.toFixed(1)}/100</strong>
          </div>
          <div className="score-track" aria-hidden="true">
            <span style={{ width: `${Math.min(100, row.score)}%` }} />
          </div>
        </div>
      ))}
      <div className="module-score">
        <div>
          <span>Accord règles / ML (confiance)</span>
          <strong>{(confidence * 100).toFixed(0)}%</strong>
        </div>
        <div className="score-track" aria-hidden="true">
          <span style={{ width: `${confidence * 100}%` }} />
        </div>
      </div>
    </div>
  );
}
