/*
 * The Agents page, #/p/<project>/review/agents?range=<r>. The usage half: every agent that ran in
 * the range with what is set for it, what it ran with, the model check and its cost, then the
 * agent files that did not run. The rows add up to Where the money went on Summary. A setup that
 * could not be read shows in each Set to cell and as one card error with Try again, while the
 * rows, runs and costs stay. A range with no runs shows the one page-level empty card.
 *
 * The setup half. A name with a setup item is a link to `?agent=<item key>`, and the table narrows
 * to Agent, Check and Cost beside the inspector (AgentInspector). At phone width the list is the
 * page and a picked agent is its own page with a back link.
 */
import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router";
import { useProjects } from "@/api/client";
import { useAgents } from "@/api/review";
import { Card } from "@/components/Card/Card";
import { useIsDesktop } from "@/lib/media";
import { reviewPath, useRangeParam } from "@/lib/range";
import { buildAgents } from "@/lib/review-agents";
import { t } from "@/strings/t";
import { AgentInspector } from "./AgentInspector";
import { AgentsTable } from "./AgentsTable";
import { CardBones, CardError, StaleLine } from "./CardStates";
import { CostFoot } from "./CostFoot";
import { EmptyRange } from "./EmptyRange";
import { ReviewShell } from "./ReviewShell";

export function AgentsPage() {
  const { project } = useParams();
  if (project === undefined) return null;
  return <AgentsProject key={project} project={project} />;
}

function AgentsProject({ project }: { project: string }) {
  const { range, setRange } = useRangeParam();
  const agents = useAgents(project, range);
  const desktop = useIsDesktop();
  const [search] = useSearchParams();
  // The item key in `?agent=`, `judge` or `lint-kit:linter`. An empty value is none.
  const picked = search.get("agent") === "" ? null : search.get("agent");
  // Set once the pick changes after the page opened, whether from a link, the back link or the
  // browser's history, so the inspector takes focus. A page that opens on a URL with an agent in it
  // leaves focus on the h1, as every route does. A press handler would not do, because a keyboard
  // press on the link navigates on keydown and the table remounts before the key comes up.
  const [moved, setMoved] = useState(false);
  const before = useRef<string | null>(picked);
  useEffect(() => {
    const left = before.current;
    if (left === picked) return;
    before.current = picked;
    setMoved(true);
    // Back from an agent, focus returns to the row that was open.
    if (picked === null && left !== null) {
      document.querySelector<HTMLElement>(`[data-agent-link="${CSS.escape(left)}"]`)?.focus();
    }
  }, [picked]);
  const projects = useProjects();
  const projectName = projects.data?.projects.find((p) => p.key === project)?.name ?? project;
  const answer = agents.answer;
  const title = t("ag_h");

  let content: React.ReactNode;
  if (answer === undefined) {
    content = (
      <Card title={title} question={t("ag_q")}>
        {agents.error === null ? (
          <CardBones card={title} rows={6} />
        ) : (
          <CardError card={title} onRetry={agents.retry} />
        )}
      </Card>
    );
  } else if (answer.ran.length === 0) {
    content = (
      <EmptyRange
        project={project}
        projectName={projectName}
        page="agents"
        range={range}
        reviewWindow={answer.window}
      />
    );
  } else {
    const table = (
      <Card title={title} question={picked === null ? t("ag_q") : t("ag_q_picked")}>
        {agents.failed && <StaleLine updatedAt={agents.updatedAt} />}
        {agents.setupError !== null && (
          <CardError card={t("ag_setup_card")} onRetry={agents.retry} />
        )}
        <AgentsTable label={title} view={buildAgents(answer)} links={{ project, range, picked }} />
        <CostFoot prices={answer.prices} runsNote />
      </Card>
    );
    const inspector =
      picked === null ? null : (
        <AgentInspector
          project={project}
          range={range}
          itemKey={picked}
          agents={answer}
          focus={moved}
          {...(desktop ? {} : { back: { href: `#${reviewPath(project, "agents", range)}` } })}
        />
      );
    // At phone width the list is the page, and a picked agent is its own page with a back link.
    content =
      inspector === null ? (
        table
      ) : desktop ? (
        <div className="review-agents-wrap">
          {table}
          {inspector}
        </div>
      ) : (
        inspector
      );
  }

  return (
    <ReviewShell
      project={project}
      page="agents"
      range={range}
      setRange={setRange}
      reviewWindow={answer?.window ?? null}
      hidePages={!desktop && picked !== null && answer !== undefined && answer.ran.length > 0}
    >
      {content}
    </ReviewShell>
  );
}
