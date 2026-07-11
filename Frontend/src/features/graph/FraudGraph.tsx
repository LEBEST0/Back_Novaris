import { useMemo } from "react";
import {
  BaseEdge,
  Background,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  getBezierPath,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Compass, Landmark, Layers, Smartphone, User, UserCheck } from "lucide-react";
import type { TransactionAnalysis } from "../../types";
import { formatCurrency, formatDateTime, formatDecision } from "../../utils/format";

interface FraudGraphProps {
  current: TransactionAnalysis;
}

type NodeRole = "sender" | "receiver" | "agent" | "device" | "batch";
type HandleSpec = { id: string; position: Position; type: "source" | "target" };

interface TooltipRow {
  label: string;
  value: string;
}

interface CircleNodeData extends Record<string, unknown> {
  role: NodeRole;
  shortLabel: string;
  caption: string;
  attention?: boolean;
  identityVerified?: boolean;
  tooltipTitle: string;
  tooltipRows: TooltipRow[];
  handles: HandleSpec[];
}

interface PropertyEdgeData extends Record<string, unknown> {
  chipLabel: string;
  attention?: boolean;
  tooltipTitle: string;
  tooltipRows: TooltipRow[];
}

const ROLE_ICON: Record<NodeRole, typeof User> = {
  sender: User,
  receiver: User,
  agent: Landmark,
  device: Smartphone,
  batch: Layers,
};

function CircleNode({ data }: NodeProps<Node<CircleNodeData>>) {
  const Icon = ROLE_ICON[data.role];
  return (
    <div className={`graph-circle-node role-${data.role} ${data.attention ? "needs-attention" : ""}`}>
      {data.handles.map((handle) => (
        <Handle key={handle.id} id={handle.id} type={handle.type} position={handle.position} className="graph-circle-handle" />
      ))}
      <div className="graph-circle">
        <Icon size={20} aria-hidden="true" />
        {data.identityVerified && (
          <span className="graph-identity-badge" title="Identité vérifiée (KYC)">
            <UserCheck size={11} aria-hidden="true" />
          </span>
        )}
      </div>
      <span className="graph-node-caption">{data.caption}</span>
      <span className="graph-node-shortlabel mono">{data.shortLabel}</span>
      <div className="graph-hover-tooltip">
        <strong>{data.tooltipTitle}</strong>
        <dl>
          {data.tooltipRows.map((row) => (
            <div key={row.label}>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}

function PropertyEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, markerEnd, data, style }: EdgeProps<Edge<PropertyEdgeData>>) {
  const [edgePath, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  if (!data) return <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={style} />;

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={style} />
      <EdgeLabelRenderer>
        <div
          className={`graph-edge-chip ${data.attention ? "needs-attention" : ""}`}
          style={{ transform: `translate(-50%, 0%) translate(${labelX}px, ${labelY}px)` }}
        >
          <span>{data.chipLabel}</span>
          <div className="graph-hover-tooltip below">
            <strong>{data.tooltipTitle}</strong>
            <dl>
              {data.tooltipRows.map((row) => (
                <div key={row.label}>
                  <dt>{row.label}</dt>
                  <dd>{row.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

const nodeTypes = { circleNode: CircleNode };
const edgeTypes = { propertyEdge: PropertyEdge };

const AGENT_RULE_CODES = new Set(["AGENT_COLLUSION_CASHOUT"]);
const DEVICE_RULE_CODES = new Set(["SIM_SWAP_SIGNAL", "SOCIAL_ENGINEERING_SIGNAL"]);

function shortPhone(phone: string) {
  return phone.length > 4 ? `···${phone.slice(-4)}` : phone;
}

function identityRow(nationalId: string | null, kycLevel: string | null): TooltipRow {
  if (nationalId) return { label: "Identité", value: `Vérifiée — KYC ${kycLevel} (${nationalId})` };
  if (kycLevel) return { label: "Identité", value: `Non vérifiée — KYC ${kycLevel} (numéro seul)` };
  return { label: "Identité", value: "Client hors Clapay — inconnu de ce système" };
}

export function FraudGraph({ current }: FraudGraphProps) {
  const agentFlagged = current.rule_flags.some((flag) => AGENT_RULE_CODES.has(flag.code));
  const deviceFlagged = current.rule_flags.some((flag) => DEVICE_RULE_CODES.has(flag.code));
  const agentRuleDescription = current.rule_flags.find((flag) => AGENT_RULE_CODES.has(flag.code))?.description;
  const deviceRuleDescription = current.rule_flags.find((flag) => DEVICE_RULE_CODES.has(flag.code))?.description;

  const optionalRoles = useMemo(() => {
    const roles: NodeRole[] = [];
    if (current.agent_id) roles.push("agent");
    if (current.device_id) roles.push("device");
    if (current.batch_id) roles.push("batch");
    return roles;
  }, [current.agent_id, current.batch_id, current.device_id]);

  const nodes: Node<CircleNodeData>[] = useMemo(() => {
    const centerY = 140;
    const list: Node<CircleNodeData>[] = [
      {
        id: "sender",
        type: "circleNode",
        position: { x: 20, y: centerY },
        data: {
          role: "sender",
          shortLabel: current.sender_national_id ? `KYC···${current.sender_national_id.slice(-4)}` : shortPhone(current.sender_phone),
          caption: "Émetteur",
          identityVerified: Boolean(current.sender_national_id),
          handles: [
            { id: "right", position: Position.Right, type: "source" },
            { id: "bottom", position: Position.Bottom, type: "source" },
          ],
          tooltipTitle: current.sender_national_id ?? current.sender_phone,
          tooltipRows: [
            { label: "Téléphone", value: current.sender_phone },
            { label: "Opérateur", value: current.sender_operator },
            { label: "Pays", value: current.sender_country },
            { label: "Ville", value: current.sender_city ?? "—" },
            identityRow(current.sender_national_id, current.sender_kyc_level),
          ],
        },
      },
      {
        id: "receiver",
        type: "circleNode",
        position: { x: 640, y: centerY },
        data: {
          role: "receiver",
          shortLabel: current.receiver_national_id ? `KYC···${current.receiver_national_id.slice(-4)}` : shortPhone(current.receiver_phone),
          caption: "Destinataire",
          identityVerified: Boolean(current.receiver_national_id),
          handles: [{ id: "left", position: Position.Left, type: "target" }],
          tooltipTitle: current.receiver_national_id ?? current.receiver_phone,
          tooltipRows: [
            { label: "Téléphone", value: current.receiver_phone },
            { label: "Pays", value: current.receiver_country ?? "Inconnu" },
            { label: "Transfrontalier", value: current.is_cross_border ? "Oui" : "Non" },
            identityRow(current.receiver_national_id, current.receiver_kyc_level),
          ],
        },
      },
    ];

    optionalRoles.forEach((role, index) => {
      const y = centerY + 200 + index * 150;
      if (role === "agent") {
        list.push({
          id: "agent",
          type: "circleNode",
          position: { x: 330, y },
          data: {
            role: "agent",
            shortLabel: current.agent_id ?? "",
            caption: agentFlagged ? "Agent — à examiner" : "Agent",
            attention: agentFlagged,
            handles: [{ id: "top", position: Position.Top, type: "target" }],
            tooltipTitle: `Agent ${current.agent_id}`,
            tooltipRows: [
              { label: "Statut", value: agentFlagged ? "Règle déclenchée" : "Aucune règle déclenchée" },
              ...(agentRuleDescription ? [{ label: "Détail", value: agentRuleDescription }] : []),
            ],
          },
        });
      }
      if (role === "device") {
        list.push({
          id: "device",
          type: "circleNode",
          position: { x: 330, y },
          data: {
            role: "device",
            shortLabel: current.device_id ?? "",
            caption: deviceFlagged ? "Device — à examiner" : "Device",
            attention: deviceFlagged,
            handles: [{ id: "top", position: Position.Top, type: "target" }],
            tooltipTitle: `Appareil ${current.device_id}`,
            tooltipRows: [
              { label: "Statut", value: deviceFlagged ? "Règle déclenchée" : "Aucune règle déclenchée" },
              ...(deviceRuleDescription ? [{ label: "Détail", value: deviceRuleDescription }] : []),
            ],
          },
        });
      }
      if (role === "batch") {
        list.push({
          id: "batch",
          type: "circleNode",
          position: { x: 330, y },
          data: {
            role: "batch",
            shortLabel: current.batch_id ?? "",
            caption: "Batch",
            handles: [{ id: "top", position: Position.Top, type: "target" }],
            tooltipTitle: `Batch ${current.batch_id}`,
            tooltipRows: [{ label: "Type", value: "Paiement de masse" }],
          },
        });
      }
    });

    return list;
  }, [agentFlagged, agentRuleDescription, current, deviceFlagged, deviceRuleDescription, optionalRoles]);

  const edges: Edge<PropertyEdgeData>[] = useMemo(() => {
    const list: Edge<PropertyEdgeData>[] = [
      {
        id: "sender-receiver",
        source: "sender",
        sourceHandle: "right",
        target: "receiver",
        targetHandle: "left",
        type: "propertyEdge",
        markerEnd: { type: MarkerType.ArrowClosed },
        data: {
          chipLabel: formatCurrency(current.amount, current.currency),
          tooltipTitle: "Transaction",
          tooltipRows: [
            { label: "Type", value: current.transaction_type },
            { label: "Canal", value: current.channel },
            { label: "Montant", value: formatCurrency(current.amount, current.currency) },
            { label: "Date", value: formatDateTime(current.computed_at) },
            { label: "Décision", value: formatDecision(current.decision) },
            { label: "Score final", value: `${current.final_score.toFixed(1)}/100` },
          ],
        },
      },
    ];

    if (current.agent_id) {
      list.push({
        id: "sender-agent",
        source: "sender",
        sourceHandle: "bottom",
        target: "agent",
        targetHandle: "top",
        type: "propertyEdge",
        markerEnd: { type: MarkerType.ArrowClosed },
        className: agentFlagged ? "edge-attention" : "",
        data: {
          chipLabel: "Agent",
          attention: agentFlagged,
          tooltipTitle: "Relation émetteur → agent",
          tooltipRows: [
            { label: "Rôle", value: "Point de service utilisé" },
            { label: "Statut", value: agentFlagged ? "Signal de risque" : "Normal" },
          ],
        },
      });
    }

    if (current.device_id) {
      list.push({
        id: "sender-device",
        source: "sender",
        sourceHandle: "bottom",
        target: "device",
        targetHandle: "top",
        type: "propertyEdge",
        markerEnd: { type: MarkerType.ArrowClosed },
        className: deviceFlagged ? "edge-attention edge-device" : "",
        data: {
          chipLabel: "Device",
          attention: deviceFlagged,
          tooltipTitle: "Relation émetteur → device",
          tooltipRows: [
            { label: "Rôle", value: "Appareil utilisé pour l'opération" },
            { label: "Statut", value: deviceFlagged ? "Signal de risque" : "Normal" },
          ],
        },
      });
    }

    if (current.batch_id) {
      list.push({
        id: "sender-batch",
        source: "sender",
        sourceHandle: "bottom",
        target: "batch",
        targetHandle: "top",
        type: "propertyEdge",
        markerEnd: { type: MarkerType.ArrowClosed },
        data: {
          chipLabel: "Batch",
          tooltipTitle: "Relation émetteur → batch",
          tooltipRows: [{ label: "Rôle", value: "Fait partie de ce paiement de masse" }],
        },
      });
    }

    return list;
  }, [agentFlagged, current, deviceFlagged]);

  return (
    <section className="screen-stack">
      <div className="screen-heading">
        <div>
          <p className="eyebrow">Graphe transactionnel</p>
          <h1>Liens de la transaction</h1>
        </div>
        <p>Survolez un nœud (compte, agent, device, batch) ou une arête (transaction) pour voir ses propriétés.</p>
      </div>

      <article className="panel roadmap-banner">
        <Compass size={18} aria-hidden="true" />
        <div>
          <strong>Aperçu limité à une transaction</strong>
          <span>
            Un client avec un KYC complet est identifié par son identifiant KYC (badge <UserCheck size={11} style={{ display: "inline", verticalAlign: "-2px" }} aria-hidden="true" />) plutôt que par son numéro — deux comptes qui partagent cet
            identifiant désignent la même personne, même sur des opérateurs/pays différents. Sans KYC complet, le numéro de
            téléphone reste le seul identifiant disponible. Ce qui manque encore : relier entre eux les nœuds de
            transactions différentes (vue réseau multi-comptes, théorie des graphes, puis GNN prédictif) — prévu pour une
            phase ultérieure.
          </span>
        </div>
      </article>

      <article className="panel graph-panel">
        <div className="graph-canvas-lite">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            fitView
            nodesDraggable={false}
            nodesConnectable={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#232B3A" gap={18} />
            <Controls />
          </ReactFlow>
        </div>
      </article>
    </section>
  );
}
