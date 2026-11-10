/*
 * The top of every Review page: the scope bar with the Range Select, the title with the window
 * line under it, and at 720px and below the segmented pages. A range change goes into the URL
 * through useRangeParam and is spoken once through the page's polite status. The links between
 * the Review pages keep the range (reviewPath). Summary, Sessions, Agents and Models use it.
 */
import { postStatus } from "@/app/harness";
import { pageName } from "@/app/routes";
import { ScopeBar } from "@/components/ScopeBar/ScopeBar";
import { Segmented } from "@/components/Segmented/Segmented";
import type { SegmentedItem } from "@/components/Segmented/Segmented";
import type { SelectOption } from "@/components/Select/Select";
import type { ReviewRange, ReviewWindow } from "@/api/types";
import { RANGES, isRange, reviewPath } from "@/lib/range";
import { useIsDesktop } from "@/lib/media";
import { rangeLabel, rangeNoun, rangeWindow, subLine } from "@/lib/review-view";
import { t } from "@/strings/t";
import "./ReviewPage.css";

export type ReviewPageId = "summary" | "sessions" | "agents" | "models";

const PAGES: readonly ReviewPageId[] = ["summary", "sessions", "agents", "models"];

function pagesLabel(id: ReviewPageId): string {
  return pageName(id);
}

export interface ReviewShellProps {
  project: string;
  page: ReviewPageId;
  range: ReviewRange;
  setRange: (next: ReviewRange) => void;
  /** The window of any answer for this range, or null before the first one arrives. */
  reviewWindow: ReviewWindow | null;
  children: React.ReactNode;
}

export function ReviewShell({
  project,
  page,
  range,
  setRange,
  reviewWindow,
  children,
}: ReviewShellProps) {
  const desktop = useIsDesktop();
  const options: SelectOption[] = RANGES.map((id) => ({
    id,
    label: rangeLabel(id),
    ...(reviewWindow === null ? {} : { description: rangeWindow(id, reviewWindow) }),
  }));
  const items: SegmentedItem[] = PAGES.map((id) => ({
    id,
    href: `#${reviewPath(project, id, range)}`,
    label: pagesLabel(id),
    ...(id === page ? { current: true } : {}),
  }));
  return (
    <div className="review">
      <ScopeBar
        form="range"
        title={pageName(page)}
        {...(reviewWindow === null ? {} : { sub: subLine(range, reviewWindow) })}
        range={{
          label: t("rg_h"),
          options,
          value: range,
          onChange: (id) => {
            if (!isRange(id) || id === range) return;
            setRange(id);
            postStatus(t("rt_range", { range: rangeNoun(id, reviewWindow) }));
          },
        }}
        {...(desktop ? {} : { pages: <Segmented label={t("nav_review")} items={items} /> })}
      />
      {children}
    </div>
  );
}
