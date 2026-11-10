/*
 * The inspector of one item (components.md entry 26) filled from a SetupItem. The headline says what
 * runs, then where it is set (top wins), why and how sure Bar Tab is. A read-only item gets the
 * read-only box with its owner's reason, the command to copy or Copy path. An item the server did
 * not read gets a box under the headline with the Unknown pill. Copy path copies the full local path
 * while the screen shows the short one (owner answer, November 9).
 *
 * An agent adds three things. A callout under the headline when it doesn't run as its file sets it,
 * a run line with the cost over 30 days from /api/agents, and the footer link to the Agents page in
 * Review. Its where-set well lists its own files only (`whereRows`).
 */
import { useAgents } from "@/api/review";
import type { SetupItem } from "@/api/types";
import { postStatus } from "@/app/harness";
import { Button } from "@/components/Button/Button";
import { CopyPath } from "@/components/CopyPath/CopyPath";
import { Inspector } from "@/components/ListInspector/Inspector";
import type { InspectorProps } from "@/components/ListInspector/Inspector";
import { agentCheckView } from "@/lib/agent-check";
import { agentUsageLine, showReviewLink } from "@/lib/agent-usage";
import { reviewPath } from "@/lib/range";
import { itemName } from "@/lib/setup-list";
import { itemKey } from "@/lib/setup-routes";
import {
  appliesLine,
  copyPathOf,
  hasMaskedValue,
  notReadView,
  readOnlyView,
  runsLine,
  setLine,
  statusOf,
  usageLine,
  whereRows,
  whyView,
} from "@/lib/setup-inspector";
import { t } from "@/strings/t";
import { AgentCallout } from "./AgentCallout";
import { InspectorFacts } from "./InspectorFacts";

export interface ItemInspectorProps {
  item: SetupItem;
  project: string;
  /** The Switch's state, which the links inside the inspector keep. */
  scopes: boolean;
  /** `server_started_at`, which dates the shell scope. */
  startedAt: string | null;
  /** The ListInspector's heading ref and phone props, passed through. */
  inspector?: Pick<InspectorProps, "headingRef" | "focusOnMount" | "back">;
}

/** The inspector of one item. An agent's also reads its runs and cost over 30 days. */
export function ItemInspector(props: ItemInspectorProps) {
  return props.item.part === "agents" ? (
    <AgentItemInspector {...props} />
  ) : (
    <ItemInspectorView {...props} />
  );
}

function AgentItemInspector(props: ItemInspectorProps) {
  const agents = useAgents(props.project, "30d");
  return (
    <ItemInspectorView
      {...props}
      agentUsage={agentUsageLine(props.item, agents.answer, "30d")}
      reviewLink={showReviewLink(props.item, agents.answer)}
    />
  );
}

interface ItemInspectorViewProps extends ItemInspectorProps {
  /** An agent's run line with cost, or null while the Agents answer loads. */
  agentUsage?: string | null;
  /** False hides the Review link, for a plugin or managed agent with no runs. */
  reviewLink?: boolean;
}

function ItemInspectorView({
  item,
  project,
  scopes,
  startedAt,
  inspector,
  agentUsage = null,
  reviewLink = true,
}: ItemInspectorViewProps) {
  const runs = runsLine(item);
  const setTo = setLine(item);
  const readOnly = readOnlyView(item);
  const notRead = notReadView(item);
  const where = whereRows(item, startedAt);
  const why = whyView(item);
  // The agent's run line with cost replaces the server's runs-only line once /api/agents answers.
  const usage = agentUsage ?? usageLine(item);
  const applies = appliesLine(item);
  const path = copyPathOf(item);
  const masked = hasMaskedValue(item);
  const check = agentCheckView(item);
  const agentKey = item.part === "agents" ? itemKey("agents", item.id) : null;
  const copy =
    readOnly === null && path !== null ? (
      <CopyPath
        value={path}
        label={t("in_copy")}
        copiedLabel={t("an_copied")}
        onStatus={postStatus}
      />
    ) : null;
  const agentsLink =
    agentKey === null || !reviewLink ? null : (
      <Button
        variant="quiet"
        href={`#${reviewPath(project, "agents", "30d", { agent: agentKey })}`}
      >
        {t("nav_agents")} <span aria-hidden="true">→</span>
      </Button>
    );
  const parts: InspectorProps = {
    title: itemName(item),
    status: statusOf(item),
    ...(inspector ?? {}),
    ...(runs !== null
      ? {
          runs: (
            <>
              {runs.text}
              {runs.masked && <span className="setup-runs-mask muted"> {t("in_masked_word")}</span>}
            </>
          ),
        }
      : {}),
    ...(setTo !== null ? { setTo } : {}),
    ...(readOnly !== null
      ? {
          readOnly: {
            lockLabel: readOnly.lockLabel,
            reason: readOnly.reason,
            ...(readOnly.command !== undefined ? { command: readOnly.command } : {}),
            ...(readOnly.path !== undefined ? { path: readOnly.path } : {}),
          },
        }
      : {}),
    ...(notRead !== null ? { notRead: { status: statusOf(item), body: notRead.body } } : {}),
    ...(check !== null ? { check: <AgentCallout view={check} /> } : {}),
    details: <InspectorFacts item={item} project={project} scopes={scopes} />,
    ...(where.length > 0
      ? { where: { title: t("in_where_h"), rows: where, maskedLabel: t("in_masked_word") } }
      : {}),
    ...(why !== null
      ? { why: { title: t("in_why_h"), body: why.body, confidence: why.confidence } }
      : {}),
    ...(usage !== null ? { usage } : {}),
    ...(copy !== null || agentsLink !== null
      ? {
          actions: (
            <>
              {copy}
              {agentsLink}
            </>
          ),
        }
      : {}),
  };
  return (
    <Inspector {...parts}>
      {item.real_path !== null && (
        <p className="inspector-small muted setup-link">
          <span aria-hidden="true">{"↪"}</span> {t("in_link", { path: item.real_path })}
        </p>
      )}
      {item.may_change && <p className="inspector-small muted">{t("in_may_change")}</p>}
      {where.some((r) => r.id.startsWith("shell")) && (
        <p className="inspector-small muted">{t("in_shell_note")}</p>
      )}
      {applies !== null && <p className="inspector-small muted">{applies}</p>}
      {masked && <p className="inspector-small muted">{t("in_masked")}</p>}
    </Inspector>
  );
}
