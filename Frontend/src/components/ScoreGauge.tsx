import { useMemo } from "react";

interface ScoreGaugeProps {
  /** Score de risque final (0-100), tel que renvoyé par core/decision_engine.py. */
  value: number;
  label?: string;
}

export function ScoreGauge({ value, label = "Score de risque" }: ScoreGaugeProps) {
  const normalized = Math.max(0, Math.min(100, value));
  const angle = useMemo(() => -120 + (normalized / 100) * 240, [normalized]);
  const color =
    normalized < 30 ? "#3DDC84" : normalized < 60 ? "#F5A623" : normalized < 80 ? "#FF7A45" : "#E23B3B";

  return (
    <div className="trust-gauge" style={{ "--gauge-angle": `${angle}deg`, "--gauge-color": color } as React.CSSProperties}>
      <div className="gauge-ring">
        <div className="gauge-needle" />
        <div className="gauge-center" />
      </div>
      <div className="gauge-readout">
        <span>{label}</span>
        <strong>{normalized.toFixed(1)}</strong>
        <small>/100</small>
      </div>
    </div>
  );
}
