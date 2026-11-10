/*
 * A range with no sessions shows one page-level card in place of every card, never an empty state
 * per card. The body says when the last session ran, read from the project's whole history, so
 * this card asks for the All list. An empty All range has nothing to say about "last", so it uses
 * the first-run words.
 */
import { localDate, useSessions } from "@/api/review";
import type { ReviewPageId } from "./ReviewShell";
import type { ReviewRange, ReviewWindow } from "@/api/types";
import { projectHref } from "@/app/nav";
import { EmptyState } from "@/components/EmptyState/EmptyState";
import { reviewPath } from "@/lib/range";
import { addDays, dateLabel, rangePhrase, timeIn } from "@/lib/review-view";
import { t } from "@/strings/t";

function whenWords(lastRequest: string, w: ReviewWindow): string {
  const day = localDate(lastRequest, w.tz);
  const today = localDate(w.end, w.tz);
  const time = timeIn(lastRequest, w.tz);
  if (day === today) return t("em_when_today", { time });
  if (day === addDays(today, -1)) return t("em_when_yday", { time });
  return t("em_when_date", { date: dateLabel(day, day.slice(0, 4) !== today.slice(0, 4)), time });
}

function EmptyWithLast({
  project,
  projectName,
  page,
  range,
  reviewWindow,
}: {
  project: string;
  projectName: string;
  page: ReviewPageId;
  range: ReviewRange;
  reviewWindow: ReviewWindow;
}) {
  const all = useSessions(project, "all");
  const last = all.days[0]?.sessions[0] ?? null;
  const body =
    last !== null
      ? t("em_b", { when: whenWords(last.last_request, reviewWindow) })
      : all.loading
        ? ""
        : t("ns_b");
  return (
    <EmptyState
      variant="page"
      title={t("em_h", { project: projectName, range: rangePhrase(range, reviewWindow) })}
      {...(range === "7d"
        ? {}
        : {
            action: {
              label: t("em_a"),
              href: `#${reviewPath(project, page, "7d")}`,
              primary: true,
            },
          })}
      secondary={{ label: t("em_live"), href: projectHref(project, "/live") }}
    >
      {body}
    </EmptyState>
  );
}

/** The card for a range with no sessions. `reviewWindow` is the answer's, for its time zone. */
export function EmptyRange({
  project,
  projectName,
  page,
  range,
  reviewWindow,
}: {
  project: string;
  projectName: string;
  page: ReviewPageId;
  range: ReviewRange;
  reviewWindow: ReviewWindow;
}) {
  if (range === "all") {
    return (
      <EmptyState
        variant="page"
        title={t("ns_h", { project: projectName })}
        secondary={{ label: t("em_live"), href: projectHref(project, "/live") }}
      >
        {t("ns_b")}
      </EmptyState>
    );
  }
  return (
    <EmptyWithLast
      project={project}
      projectName={projectName}
      page={page}
      range={range}
      reviewWindow={reviewWindow}
    />
  );
}
