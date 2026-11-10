/*
 * The Summary page, #/p/<project>/review/summary?range=<r>. Four tiles, the cost chart with its
 * pager, Where the money went, the model check over the range and the most expensive sessions.
 * The tiles, money, check and top sessions share one summary query. The chart has its own, so
 * its pager never moves the tiles. Each card shows its own bones, error and stale line. A range
 * with no sessions shows one page-level card in place of them all.
 */
import { useParams } from "react-router";
import { useProjects } from "@/api/client";
import { useSummary } from "@/api/review";
import { useRangeParam } from "@/lib/range";
import { CostChartCard } from "./CostChartCard";
import { EmptyRange } from "./EmptyRange";
import { ReviewShell } from "./ReviewShell";
import { MoneyCard, SummaryCheckCard, TopSessionsCard } from "./SummaryCards";
import { SummaryTiles, SummaryTilesError, SummaryTilesLoading } from "./SummaryTiles";
import { StaleLine } from "./CardStates";

export function SummaryPage() {
  const { project } = useParams();
  if (project === undefined) return null;
  return <SummaryProject key={project} project={project} />;
}

function SummaryProject({ project }: { project: string }) {
  const { range, setRange } = useRangeParam();
  const summary = useSummary(project, range);
  const projects = useProjects();
  const projectName = projects.data?.projects.find((p) => p.key === project)?.name ?? project;
  const answer = summary.answer;

  let tiles: React.ReactNode;
  if (answer !== undefined) tiles = <SummaryTiles summary={answer} />;
  else if (summary.error !== null) tiles = <SummaryTilesError onRetry={summary.retry} />;
  else tiles = <SummaryTilesLoading />;

  return (
    <ReviewShell
      project={project}
      page="summary"
      range={range}
      setRange={setRange}
      reviewWindow={answer?.window ?? null}
    >
      {answer?.session_count === 0 ? (
        <EmptyRange
          project={project}
          projectName={projectName}
          page="summary"
          range={range}
          reviewWindow={answer.window}
        />
      ) : (
        <>
          {summary.failed && <StaleLine updatedAt={summary.updatedAt} />}
          {tiles}
          <CostChartCard key={range} project={project} range={range} />
          <div className="grid-two review-lower">
            <MoneyCard card={summary} />
            <SummaryCheckCard card={summary} />
          </div>
          <TopSessionsCard card={summary} project={project} range={range} />
        </>
      )}
    </ReviewShell>
  );
}
