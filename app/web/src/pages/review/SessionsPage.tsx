/*
 * The Sessions page, #/p/<project>/review/sessions?range=<r>. The range's sessions under their
 * local day, newest first, 50 to a page. "Show more" loads the next page and moves focus to its
 * first new row. A failed load keeps the rows and says so by the button. A session that began
 * before the range shows its in-range cost with the "Started earlier" flag. A range with no
 * sessions shows the one page-level empty card.
 */
import { useEffect } from "react";
import { useParams } from "react-router";
import { usePrices, useProjects } from "@/api/client";
import { useSessions } from "@/api/review";
import { Button } from "@/components/Button/Button";
import { Card } from "@/components/Card/Card";
import { HelpButton } from "@/components/HelpButton/HelpButton";
import { dateWords } from "@/lib/clock";
import { modelLabel } from "@/lib/models";
import { useRangeParam } from "@/lib/range";
import { buildSessionGroups } from "@/lib/review-cards";
import { t, tn } from "@/strings/t";
import { CardBones, CardError, StaleLine } from "./CardStates";
import { EmptyRange } from "./EmptyRange";
import { ReviewShell } from "./ReviewShell";
import { SessionsTable } from "./SessionsTable";

/** The server's page size. "Show n more" never offers more than one page. */
const PAGE = 50;

export function SessionsPage() {
  const { project } = useParams();
  if (project === undefined) return null;
  return <SessionsProject key={project} project={project} />;
}

function SessionsProject({ project }: { project: string }) {
  const { range, setRange } = useRangeParam();
  const sessions = useSessions(project, range);
  const prices = usePrices();
  const projects = useProjects();
  const projectName = projects.data?.projects.find((p) => p.key === project)?.name ?? project;
  const head = sessions.head;
  const { firstNewId } = sessions;

  // The first row a "Show more" added takes focus, so a keyboard reader lands where the new rows start.
  useEffect(() => {
    if (firstNewId === null) return;
    document.querySelector<HTMLElement>(`[data-session="${CSS.escape(firstNewId)}"]`)?.focus();
  }, [firstNewId]);

  const title = t("ss_h");
  const disagreed = prices.data?.cross_check.models.map(modelLabel) ?? [];

  let content: React.ReactNode;
  if (head === undefined) {
    content = (
      <Card title={title}>
        {sessions.error === null ? (
          <CardBones card={title} rows={8} />
        ) : (
          <CardError card={title} onRetry={sessions.retry} />
        )}
      </Card>
    );
  } else if (sessions.count === 0) {
    content = (
      <EmptyRange
        project={project}
        projectName={projectName}
        page="sessions"
        range={range}
        reviewWindow={head.window}
      />
    );
  } else {
    const groups = buildSessionGroups(sessions.days, head.window.tz, head.window.end);
    content = (
      <Card
        title={title}
        count={String(sessions.count)}
        right={<HelpButton help="sessions.share" />}
      >
        {sessions.failed && <StaleLine updatedAt={sessions.updatedAt} />}
        <SessionsTable label={title} groups={groups} project={project} range={range} />
        <div className="review-pgfoot">
          {sessions.hasMore ? (
            <>
              <span className="muted">
                {t("ss_page", { a: sessions.loaded, n: sessions.count })}
              </span>
              <Button
                busy={sessions.loadingMore}
                busyLabel={t("ld_line", { card: title.toLowerCase() })}
                onPress={() => {
                  void sessions.loadMore();
                }}
              >
                {sessions.loadMoreError === null
                  ? tn("ss_more", Math.min(PAGE, sessions.remaining))
                  : t("er_try")}
              </Button>
            </>
          ) : (
            <span className="muted">{tn("ss_end", sessions.count)}</span>
          )}
        </div>
        {sessions.loadMoreError !== null && (
          <p className="review-more-error" role="alert">
            {t("er_h", { card: title.toLowerCase() })}
          </p>
        )}
        <div className="review-foot">
          <p>{t("runs_def")}</p>
          <p>{t("foot_est", { date: dateWords(head.prices.as_of) })}</p>
          {head.prices.cross_check_state === "disagree" && disagreed.length > 0 && (
            <p className="review-warn">
              <span aria-hidden="true">{"▲ "}</span>
              {t("foot_disagree", { model: disagreed.join(", ") })}
            </p>
          )}
        </div>
      </Card>
    );
  }

  return (
    <ReviewShell
      project={project}
      page="sessions"
      range={range}
      setRange={setRange}
      reviewWindow={head?.window ?? null}
    >
      {content}
    </ReviewShell>
  );
}
