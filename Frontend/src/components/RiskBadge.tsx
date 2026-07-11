import type { RiskLevel } from "../types";
import { formatRiskLevel, riskClass } from "../utils/format";

interface RiskBadgeProps {
  level: RiskLevel;
}

export function RiskBadge({ level }: RiskBadgeProps) {
  return <span className={`risk-badge ${riskClass(level)}`}>{formatRiskLevel(level)}</span>;
}
