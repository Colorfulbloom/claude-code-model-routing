/*
 * The callout under an agent's header on both inspectors (a-m4-p11-agents, a-m4-p12-agents): the
 * status pill and the sentence, then the reason in muted small text. Its words come from
 * `agentCheckView`, which reads the item's `check`.
 */
import { RaisedFinding } from "@/components/RaisedFinding/RaisedFinding";
import { StatusChip } from "@/components/StatusChip/StatusChip";
import type { AgentCheckView } from "@/lib/agent-check";
import "./AgentCallout.css";

export function AgentCallout({ view }: { view: AgentCheckView }) {
  return (
    <RaisedFinding className="agent-callout">
      <p className="agent-callout-line">
        <StatusChip status={view.status.status}>{view.status.label}</StatusChip> {view.line}
      </p>
      {view.why !== null && <p className="agent-callout-why muted">{view.why}</p>}
    </RaisedFinding>
  );
}
