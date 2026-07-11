import { Activity, AlertTriangle, Ban, Gauge, ScanSearch, ShieldCheck, WalletCards } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useEffect, useState } from "react";
import { KpiCard } from "../../components/KpiCard";
import { RiskBadge } from "../../components/RiskBadge";
import type { DashboardKpis, DashboardTrendPoint, RiskLevel, TransactionAnalysis } from "../../types";
import { fetchDashboardKpis, fetchDashboardTrend } from "../../services/api";
import { formatCurrency, formatDecision, formatPercent, riskClass } from "../../utils/format";

interface DashboardProps {
  transactions: TransactionAnalysis[];
  liveActive: boolean;
  onToggleLive: () => void;
  onOpen: (analysis: TransactionAnalysis) => void;
}

const riskColors: Record<RiskLevel, string> = {
  low: "#3DDC84",
  moderate: "#F5A623",
  high: "#FF7A45",
  critical: "#E23B3B",
};

const riskOrder: RiskLevel[] = ["low", "moderate", "high", "critical"];
const riskLabels: Record<RiskLevel, string> = {
  low: "Faible",
  moderate: "Modéré",
  high: "Élevé",
  critical: "Critique",
};

export function Dashboard({ transactions, liveActive, onToggleLive, onOpen }: DashboardProps) {
  const [kpis, setKpis] = useState<DashboardKpis | null>(null);
  const [trend, setTrend] = useState<DashboardTrendPoint[]>([]);

  useEffect(() => {
    fetchDashboardKpis().then(setKpis);
    fetchDashboardTrend().then(setTrend);
  }, []);

  useEffect(() => {
    if (!liveActive) return;
    const interval = window.setInterval(() => {
      fetchDashboardKpis().then(setKpis);
      fetchDashboardTrend().then(setTrend);
    }, 15000);
    return () => window.clearInterval(interval);
  }, [liveActive]);

  const distribution = riskOrder.map((level) => {
    const items = transactions.filter((item) => item.risk_level === level);
    const average = items.length ? Math.round(items.reduce((sum, item) => sum + item.final_score, 0) / items.length) : 0;
    return {
      level,
      name: riskLabels[level],
      count: items.length,
      score: average,
    };
  });

  const topAlerts = [...transactions].sort((a, b) => b.final_score - a.final_score).slice(0, 7);
  const trendData = trend.map((item) => ({
    ...item,
    day: new Date(item.date).toLocaleDateString("fr-FR", { weekday: "short" }),
  }));

  return (
    <section className="screen-stack">
      <div className="screen-heading">
        <div>
          <p className="eyebrow">Supervision anti-fraude</p>
          <h1>Dashboard</h1>
        </div>
        <div className="live-feed-control">
          <span className={liveActive ? "live-status is-active" : "live-status"}>
            <i /> {liveActive ? "Rafraîchissement automatique" : "Rafraîchissement en pause"}
          </span>
          <button type="button" onClick={onToggleLive}>
            <Activity size={15} aria-hidden="true" />
            {liveActive ? "Pause" : "Reprendre"}
          </button>
        </div>
      </div>

      <div className="business-kpi-grid">
        <article className="panel business-kpi-card">
          <div className="kpi-icon" aria-hidden="true">
            <WalletCards size={20} />
          </div>
          <div>
            <p className="eyebrow">Fraude confirmée</p>
            <strong>{formatCurrency(kpis?.fraud_amount_confirmed ?? 0)}</strong>
            <span>montant confirmé par les analystes (TEMPORARY_BLOCK)</span>
          </div>
        </article>
        <article className="panel precision-card">
          <div className="kpi-icon" aria-hidden="true">
            <ShieldCheck size={18} />
          </div>
          <div>
            <p className="eyebrow">Qualité analyste</p>
            <strong>{kpis?.false_positive_rate !== null && kpis?.false_positive_rate !== undefined ? formatPercent(100 - kpis.false_positive_rate) : "—"}</strong>
            <span>de précision après feedback</span>
          </div>
        </article>
      </div>

      <div className="kpi-grid">
        <KpiCard icon={ScanSearch} label="Transactions analysées" value={`${kpis?.transactions_analyzed ?? "—"}`} hint="Total en base" />
        <KpiCard icon={AlertTriangle} label="Alertes actives" value={`${kpis?.active_alerts ?? "—"}`} hint="Revue ou blocage" />
        <KpiCard icon={Ban} label="Taux de blocage" value={kpis ? formatPercent(kpis.blocking_rate) : "—"} hint="TEMPORARY_BLOCK" />
        <KpiCard icon={Gauge} label="En attente de revue" value={`${kpis?.pending_analyst_review ?? "—"}`} hint="Sans feedback analyste" />
      </div>

      <div className="dashboard-grid">
        <article className="panel chart-panel wide">
          <div className="panel-heading">
            <h2>Activité de surveillance</h2>
            <span>7 derniers jours</span>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={trendData}>
              <CartesianGrid stroke="#232B3A" vertical={false} />
              <XAxis dataKey="day" stroke="#8792A2" />
              <YAxis stroke="#8792A2" />
              <Tooltip contentStyle={{ background: "#141B26", border: "1px solid #232B3A", color: "#E8ECF1" }} />
              <Line type="monotone" dataKey="transactions_analyzed" name="Transactions" stroke="#2FD1C9" strokeWidth={2.4} dot={false} />
              <Line type="monotone" dataKey="alerts" name="Alertes" stroke="#E23B3B" strokeWidth={2.4} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </article>

        <article className="panel chart-panel wide">
          <div className="panel-heading">
            <h2>Répartition des risques</h2>
            <span>{transactions.length} transactions récentes chargées</span>
          </div>
          <div className="risk-overview-grid">
            {distribution.map((item) => (
              <div key={item.level} className={`risk-overview-card ${riskClass(item.level)}`}>
                <span>{item.name}</span>
                <strong>{item.count}</strong>
                <small>Score moyen {item.score || "—"}</small>
              </div>
            ))}
          </div>
          <ResponsiveContainer width="100%" height={210}>
            <BarChart data={distribution}>
              <CartesianGrid stroke="#232B3A" vertical={false} />
              <XAxis dataKey="name" stroke="#8792A2" />
              <YAxis stroke="#8792A2" />
              <Tooltip contentStyle={{ background: "#141B26", border: "1px solid #232B3A", color: "#E8ECF1" }} />
              <Bar dataKey="count" name="Transactions" radius={[8, 8, 0, 0]}>
                {distribution.map((entry) => (
                  <Cell key={entry.level} fill={riskColors[entry.level as RiskLevel]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </article>

        <article className="panel alerts-panel wide">
          <div className="panel-heading">
            <h2>Alertes récentes</h2>
            <span>Triées par score final</span>
          </div>
          <div className="alert-list">
            {topAlerts.map((analysis) => (
              <button
                key={analysis.transaction_id}
                type="button"
                className={`alert-row ${riskClass(analysis.risk_level)}`}
                onClick={() => onOpen(analysis)}
              >
                <span className="alert-main">
                  <strong className="mono">{analysis.transaction_id}</strong>
                  <small className="mono">{analysis.sender_phone}</small>
                </span>
                <span className="alert-money">
                  <strong>{formatCurrency(analysis.amount, analysis.currency)}</strong>
                  <small>{formatDecision(analysis.decision)}</small>
                </span>
                <span className="alert-risk">
                  <RiskBadge level={analysis.risk_level} />
                  <small>{analysis.final_score.toFixed(0)}/100</small>
                </span>
              </button>
            ))}
            {!topAlerts.length && <p className="summary">Aucune transaction récente. Lancez une analyse pour commencer.</p>}
          </div>
        </article>
      </div>
    </section>
  );
}
