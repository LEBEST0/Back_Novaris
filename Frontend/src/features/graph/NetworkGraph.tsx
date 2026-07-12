import { useEffect, useMemo, useState } from "react";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation } from "d3-force";
import { UserCheck } from "lucide-react";
import { fetchNetworkGraph } from "../../services/api";
import { formatCurrency, formatDateTime, formatDecision } from "../../utils/format";
import type { NetworkEdge, NetworkGraph as NetworkGraphData, NetworkNode } from "../../types";

interface NetworkGraphProps {
  onSelectTransaction: (transactionId: string) => void;
}

const RISK_COLOR: Record<string, string> = {
  low: "#3DDC84",
  moderate: "#F5A623",
  high: "#FF7A45",
  critical: "#E23B3B",
};


interface LaidOutNode extends NetworkNode {
  x: number;
  y: number;
  radius: number;
}

function nodeRadius(transactionCount: number): number {
  return Math.min(26, Math.max(6, 4 + Math.sqrt(transactionCount) * 3.2));
}

const VIEW_SIZE = 1000;

function computeLayout(nodes: NetworkNode[], edges: NetworkEdge[]): LaidOutNode[] {
  const nodeIds = new Set(nodes.map((n) => n.id));
  const simNodes = nodes.map((n) => ({ ...n, radius: nodeRadius(n.transaction_count) })) as (LaidOutNode & { x?: number; y?: number })[];
  const simLinks = edges
    .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
    .map((e) => ({ source: e.source, target: e.target }));

  const simulation = forceSimulation(simNodes as never[])
    .force("link", forceLink(simLinks as never[]).id((d) => (d as { id: string }).id).distance(38).strength(0.35))
    .force("charge", forceManyBody().strength(-55))
    .force("center", forceCenter(0, 0))
    .force("collide", forceCollide((d) => (d as LaidOutNode).radius + 4))
    .stop();

  const ticks = nodes.length > 250 ? 100 : 160;
  for (let i = 0; i < ticks; i += 1) simulation.tick();

  const laid = simNodes.map((n) => ({ ...(n as LaidOutNode), x: n.x ?? 0, y: n.y ?? 0 }));

  // Normalise dans un viewBox fixe pour un rendu SVG statique (pas de pan/zoom custom
  // à maintenir) — un simple ajustement d'échelle suffit pour tout voir d'un coup d'œil.
  const xs = laid.map((n) => n.x);
  const ys = laid.map((n) => n.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = Math.max(1, maxX - minX);
  const spanY = Math.max(1, maxY - minY);
  const scale = (VIEW_SIZE - 80) / Math.max(spanX, spanY);

  return laid.map((n) => ({
    ...n,
    x: (n.x - minX - spanX / 2) * scale + VIEW_SIZE / 2,
    y: (n.y - minY - spanY / 2) * scale + VIEW_SIZE / 2,
  }));
}

interface HoverInfo {
  kind: "node" | "edge";
  title: string;
  rows: { label: string; value: string }[];
  x: number;
  y: number;
}

export function NetworkGraph({ onSelectTransaction }: NetworkGraphProps) {
  const [data, setData] = useState<NetworkGraphData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState<HoverInfo | null>(null);

  useEffect(() => {
    fetchNetworkGraph()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Impossible de charger le graphe réseau."));
  }, []);

  const laidOut = useMemo(() => (data ? computeLayout(data.nodes, data.edges) : []), [data]);
  const positionById = useMemo(() => new Map(laidOut.map((n) => [n.id, n])), [laidOut]);

  const drawableEdges = useMemo(() => {
    if (!data) return [];
    return data.edges.filter((e) => positionById.has(e.source) && positionById.has(e.target));
  }, [data, positionById]);

  if (error) return <p className="error-banner">{error}</p>;
  if (!data) return <div className="panel loading-panel">Chargement du graphe réseau...</div>;

  const showNodeTooltip = (e: React.MouseEvent<SVGGElement>, n: LaidOutNode) => {
    const svg = e.currentTarget.ownerSVGElement;
    const rect = (svg ?? e.currentTarget).getBoundingClientRect();
    setHover({
      kind: "node",
      title: n.label,
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
      rows: [
        { label: "Type", value: n.type === "customer" ? "Client" : n.type === "agent" ? "Agent" : "Appareil" },
        { label: "Transactions liées", value: String(n.transaction_count) },
        { label: "Pays", value: n.country ?? "Inconnu" },
        { label: "Risque max observé", value: n.max_risk_level },
        { label: "Identité", value: n.identity_verified ? "Vérifiée (KYC, national_id partagé)" : "Numéro de téléphone uniquement" },
      ],
    });
  };

  const showEdgeTooltip = (e: React.MouseEvent<SVGLineElement>, edge: NetworkEdge) => {
    const svg = e.currentTarget.ownerSVGElement;
    const rect = (svg ?? e.currentTarget).getBoundingClientRect();
    setHover({
      kind: "edge",
      title: edge.kind === "transaction" ? (edge.transaction_id ?? "Transaction") : edge.kind === "agent" ? "Lien agent" : "Lien appareil",
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
      rows:
        edge.kind === "transaction"
          ? [
              { label: "Type", value: edge.transaction_type ?? "—" },
              { label: "Montant", value: edge.amount ? formatCurrency(edge.amount, edge.currency ?? "XOF") : "—" },
              { label: "Décision", value: edge.decision ? formatDecision(edge.decision) : "—" },
              { label: "Date", value: edge.created_at ? formatDateTime(edge.created_at) : "—" },
            ]
          : [{ label: "Rôle", value: edge.kind === "agent" ? "Agent utilisé" : "Appareil utilisé" }],
    });
  };

  return (
    <>
      <div className="graph-network-summary">
        <span>{data.nodes.length} nœuds</span>
        <span>{data.edges.length} liens</span>
        <span>{data.nodes.filter((n) => n.identity_verified).length} identités KYC fusionnées</span>
        <span>{data.nodes.filter((n) => n.flagged).length} nœuds signalés</span>
        {data.truncated && <span className="graph-risk-pill high">Vue tronquée (limite atteinte)</span>}
      </div>
      <div className="graph-canvas-lite network-svg-wrap">
        <svg viewBox={`0 0 ${VIEW_SIZE} ${VIEW_SIZE}`} className="network-svg" onMouseLeave={() => setHover(null)}>
          <g opacity={0.55}>
            {drawableEdges.map((e) => {
              const s = positionById.get(e.source)!;
              const t = positionById.get(e.target)!;
              const color = e.risk_level ? RISK_COLOR[e.risk_level] : "#3A4658";
              const flagged = e.decision === "REVIEW" || e.decision === "TEMPORARY_BLOCK";
              return (
                <line
                  key={e.id}
                  x1={s.x}
                  y1={s.y}
                  x2={t.x}
                  y2={t.y}
                  stroke={color}
                  strokeWidth={flagged ? 1.6 : e.kind === "transaction" ? 0.9 : 0.6}
                  strokeDasharray={e.kind === "transaction" ? undefined : "3 3"}
                  className="network-edge"
                  onMouseEnter={(ev) => showEdgeTooltip(ev, e)}
                  onClick={() => e.transaction_id && onSelectTransaction(e.transaction_id)}
                />
              );
            })}
          </g>
          <g>
            {laidOut.map((n) => {
              const color = RISK_COLOR[n.max_risk_level] ?? RISK_COLOR.low;
              const shapeProps = {
                fill: "#141B26",
                stroke: color,
                strokeWidth: n.flagged ? 2.4 : 1.6,
              };
              return (
                <g
                  key={n.id}
                  transform={`translate(${n.x}, ${n.y})`}
                  className={`network-node-g ${n.flagged ? "is-flagged" : ""}`}
                  onMouseEnter={(ev) => showNodeTooltip(ev, n)}
                >
                  {n.type === "customer" && <circle r={n.radius} {...shapeProps} />}
                  {n.type === "agent" && (
                    <polygon
                      points={`0,${-n.radius} ${n.radius * 0.95},${n.radius * 0.75} ${-n.radius * 0.95},${n.radius * 0.75}`}
                      {...shapeProps}
                    />
                  )}
                  {n.type === "device" && (
                    <rect
                      x={-n.radius * 0.78}
                      y={-n.radius * 0.78}
                      width={n.radius * 1.56}
                      height={n.radius * 1.56}
                      rx={n.radius * 0.2}
                      {...shapeProps}
                    />
                  )}
                  {n.identity_verified && (
                    <circle cx={n.radius * 0.7} cy={n.radius * 0.7} r={4} fill="#3DDC84" stroke="#0B0E14" strokeWidth={1} />
                  )}
                </g>
              );
            })}
          </g>
        </svg>
        {hover && (
          <div className="network-tooltip" style={{ left: hover.x + 14, top: hover.y + 14 }}>
            <strong className="mono">{hover.title}</strong>
            <dl>
              {hover.rows.map((row) => (
                <div key={row.label}>
                  <dt>{row.label}</dt>
                  <dd>{row.value}</dd>
                </div>
              ))}
            </dl>
            {hover.kind === "edge" && <span className="network-tooltip-hint">Cliquer pour ouvrir le détail</span>}
          </div>
        )}
      </div>
      <div className="graph-narrative-legend">
        <span><UserCheck size={11} style={{ display: "inline", verticalAlign: "-2px" }} aria-hidden="true" /> Badge vert = identité KYC vérifiée (national_id partagé entre comptes)</span>
        <span><b className="legend-dot low" /> Risque faible</span>
        <span><b className="legend-dot medium" /> Modéré</span>
        <span><b className="legend-dot high" /> Élevé</span>
        <span><b className="legend-dot critical" /> Critique</span>
      </div>
    </>
  );
}
