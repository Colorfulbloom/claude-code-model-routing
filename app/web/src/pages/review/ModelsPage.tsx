/*
 * The Models page, #/p/<project>/review/models?range=<r>. Two cards from the one models answer: what
 * each model cost, and what that cost is made of by kind. Summary's "Made of" link lands on the
 * second card (`?section=kinds`): the page scrolls to it and moves focus to its heading, once the
 * answer is in. Each card shows its own bones, error and stale line, and the kinds card stays on
 * the page in every state so the link always has somewhere to land. A range with no requests shows
 * the one page-level empty card.
 */
import { useEffect, useRef } from "react";
import { useParams, useSearchParams } from "react-router";
import { useProjects } from "@/api/client";
import { useModels } from "@/api/review";
import { Card } from "@/components/Card/Card";
import { HelpButton } from "@/components/HelpButton/HelpButton";
import { useRangeParam } from "@/lib/range";
import { KINDS_SECTION, buildModelRows } from "@/lib/review-models";
import { t } from "@/strings/t";
import { CardBones, CardError, StaleLine } from "./CardStates";
import { CostFoot } from "./CostFoot";
import { EmptyRange } from "./EmptyRange";
import { ModelsKinds } from "./ModelsKinds";
import { ModelsTable } from "./ModelsTable";
import { ReviewShell } from "./ReviewShell";

const KINDS_ID = "review-models-kinds";

export function ModelsPage() {
  const { project } = useParams();
  if (project === undefined) return null;
  return <ModelsProject key={project} project={project} />;
}

function ModelsProject({ project }: { project: string }) {
  const { range, setRange } = useRangeParam();
  const models = useModels(project, range);
  const projects = useProjects();
  const [params] = useSearchParams();
  const projectName = projects.data?.projects.find((p) => p.key === project)?.name ?? project;
  const answer = models.answer;
  const kinds = useRef<HTMLDivElement>(null);
  const landed = useRef(false);
  const wantsKinds = params.get("section") === KINDS_SECTION;
  const ready = answer !== undefined && answer.rows.length > 0;

  // The link lands once, when the section exists. A later refetch or range change never pulls the
  // page back to it.
  useEffect(() => {
    if (!wantsKinds || !ready || landed.current) return;
    landed.current = true;
    const heading = kinds.current?.querySelector("h2");
    if (heading === null || heading === undefined) return;
    heading.tabIndex = -1;
    heading.focus();
    kinds.current?.scrollIntoView({ block: "start" });
  }, [wantsKinds, ready]);

  const title = t("md_h");
  const kindsTitle = t("md_kind_h");

  let content: React.ReactNode;
  if (answer === undefined) {
    const loading = models.error === null;
    content = (
      <>
        <Card title={title} question={t("md_q")}>
          {loading ? (
            <CardBones card={title} rows={4} />
          ) : (
            <CardError card={title} onRetry={models.retry} />
          )}
        </Card>
        <div id={KINDS_ID} ref={kinds} className="review-models-kinds">
          <Card title={kindsTitle} question={t("md_kind_q")}>
            {loading ? (
              <CardBones card={kindsTitle} rows={4} />
            ) : (
              <CardError card={kindsTitle} onRetry={models.retry} />
            )}
          </Card>
        </div>
      </>
    );
  } else if (answer.rows.length === 0) {
    content = (
      <EmptyRange
        project={project}
        projectName={projectName}
        page="models"
        range={range}
        reviewWindow={answer.window}
      />
    );
  } else {
    content = (
      <>
        <Card title={title} question={t("md_q")}>
          {models.failed && <StaleLine updatedAt={models.updatedAt} />}
          <ModelsTable label={title} rows={buildModelRows(answer)} />
          <CostFoot prices={answer.prices} />
        </Card>
        <div id={KINDS_ID} ref={kinds} className="review-models-kinds">
          <Card
            title={kindsTitle}
            question={t("md_kind_q")}
            right={<HelpButton help="models.kinds" />}
          >
            {models.failed && <StaleLine updatedAt={models.updatedAt} />}
            <ModelsKinds answer={answer} range={range} />
          </Card>
        </div>
      </>
    );
  }

  return (
    <ReviewShell
      project={project}
      page="models"
      range={range}
      setRange={setRange}
      reviewWindow={answer?.window ?? null}
    >
      {content}
    </ReviewShell>
  );
}
