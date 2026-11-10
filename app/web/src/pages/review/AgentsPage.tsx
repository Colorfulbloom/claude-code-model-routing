/*
 * The Agents page, #/p/<project>/review/agents?range=<r>. The usage half: every agent that ran in
 * the range with what is set for it, what it ran with, the model check and its cost, then the
 * agent files that did not run. The rows add up to Where the money went on Summary. A setup that
 * could not be read shows in each Set to cell and as one card error with Try again, while the
 * rows, runs and costs stay. A range with no runs shows the one page-level empty card.
 */
import { useParams } from "react-router";
import { useProjects } from "@/api/client";
import { useAgents } from "@/api/review";
import { Card } from "@/components/Card/Card";
import { useRangeParam } from "@/lib/range";
import { buildAgents } from "@/lib/review-agents";
import { t } from "@/strings/t";
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
    content = (
      <Card title={title} question={t("ag_q")}>
        {agents.failed && <StaleLine updatedAt={agents.updatedAt} />}
        {agents.setupError !== null && (
          <CardError card={t("ag_setup_card")} onRetry={agents.retry} />
        )}
        <AgentsTable label={title} view={buildAgents(answer)} />
        <CostFoot prices={answer.prices} />
      </Card>
    );
  }

  return (
    <ReviewShell
      project={project}
      page="agents"
      range={range}
      setRange={setRange}
      reviewWindow={answer?.window ?? null}
    >
      {content}
    </ReviewShell>
  );
}
