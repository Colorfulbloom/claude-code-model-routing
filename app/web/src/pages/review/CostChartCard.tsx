/*
 * Cost per hour, day, week or month, split by model. The pager moves this chart only, never the
 * tiles. The legend and the "Made of" line carry the same numbers as the bars, so the picture is
 * never the only way to read them. Bars split by model only. The kinds stay on Models.
 *
 * While a pager move loads, the pager stays (so focus stays) and the chart shows bones. A range
 * change remounts the card, because the page keys it by range.
 */
import { useRef, useState } from "react";
import { Link } from "react-aria-components";
import { usePrices } from "@/api/client";
import { localDate, useCostChart } from "@/api/review";
import type { CostChart } from "@/api/types";
import type { ReviewRange } from "@/api/types";
import { Button } from "@/components/Button/Button";
import { Card } from "@/components/Card/Card";
import { ModelSwatch } from "@/components/ModelSwatch/ModelSwatch";
import { Pager } from "@/components/Pager/Pager";
import { StackedBars } from "@/components/StackedBars/StackedBars";
import { Well } from "@/components/Well/Well";
import { dateWords } from "@/lib/clock";
import { reviewPath } from "@/lib/range";
import {
  buildCostChart,
  chartHeading,
  chartWindowLabel,
  earlierWindowLabel,
  laterWindowLabel,
  rangeUnit,
} from "@/lib/review-cards";
import { KINDS_SECTION } from "@/lib/review-models";
import { oldestLabel, rangeNoun } from "@/lib/review-view";
import { modelLabel } from "@/lib/models";
import { t } from "@/strings/t";
import { CardBones, CardError, StaleLine } from "./CardStates";

/** The pager's group, from the previous good answer while the next one loads. */
function ChartPager({
  shown,
  loading,
  chart,
  onNewest,
}: {
  shown: CostChart;
  loading: boolean;
  chart: ReturnType<typeof useCostChart>;
  onNewest: () => void;
}) {
  const { tz } = shown.window;
  const windowText = chartWindowLabel(shown.chart, tz);
  const newestEnd = localDate(shown.window.end, tz);
  const earlierDisabled = !loading && !chart.canEarlier;
  const laterDisabled = loading ? shown.chart.newest : !chart.canLater;
  return (
    <div className="review-pager">
      <Pager
        label={chartHeading(shown.chart.unit)}
        earlierLabel={t("pager_prev")}
        laterLabel={t("pager_next")}
        earlierAria={t("ch_prev_aria", { window: earlierWindowLabel(shown.chart, tz) })}
        laterAria={t("ch_next_aria", { window: laterWindowLabel(shown.chart, tz, newestEnd) })}
        windowLabel={windowText}
        onEarlier={chart.earlier}
        onLater={chart.later}
        earlierDisabled={earlierDisabled}
        earlierReason={t("ch_none_earlier", { date: oldestLabel(shown.window) ?? "" })}
        laterDisabled={laterDisabled}
        laterReason={t("ch_none_later")}
      />
      {!shown.chart.newest && (
        <Button variant="quiet" onPress={onNewest}>
          {t("pager_newest")}
        </Button>
      )}
    </div>
  );
}

export function CostChartCard({ project, range }: { project: string; range: ReviewRange }) {
  const chart = useCostChart(project, range);
  const prices = usePrices();
  const root = useRef<HTMLDivElement>(null);
  // The last good answer keeps the pager on screen while the next window loads.
  const [prev, setPrev] = useState<CostChart | undefined>(undefined);
  if (chart.answer !== undefined && chart.answer !== prev) setPrev(chart.answer);

  const answer = chart.answer;
  const shown = answer ?? prev;
  const unit = shown?.chart.unit ?? rangeUnit(range);
  const heading = chartHeading(unit);
  const view = answer === undefined ? null : buildCostChart(answer);
  const disagreed = prices.data?.cross_check.models.map(modelLabel) ?? [];

  function goNewest(): void {
    // The button leaves with the move, so focus goes to the pager's first button first.
    root.current?.querySelector<HTMLElement>(".pager-row .button")?.focus();
    chart.newest();
  }

  let body: React.ReactNode;
  if (chart.error !== null && answer === undefined) {
    body = <CardError card={heading} onRetry={chart.retry} />;
  } else if (view === null || answer === undefined) {
    body = <CardBones card={heading} rows={5} className="review-costbones" />;
  } else {
    const first = view.legend.length > 0;
    body = (
      <>
        {first && (
          <ul className="review-legend">
            {view.legend.map((entry) => (
              <li key={entry.model}>
                <ModelSwatch model={entry.model} />
                {entry.label} <b className="num">{entry.total}</b>
              </li>
            ))}
          </ul>
        )}
        {!answer.chart.newest && (
          <p className="review-scope-note">
            {t("ch_scope_note", { range: rangeNoun(range, answer.window) })}
          </p>
        )}
        <Well className="review-costwell">
          <StackedBars
            className="review-costbars"
            guttered
            bars={view.bars}
            models={view.models}
            yTicks={view.yTicks}
            xLabels={view.xLabels}
            {...(view.nowLabel !== undefined ? { nowLabel: view.nowLabel } : {})}
            legend={[]}
            axisLabel={view.heading}
            summary={view.summary}
          />
        </Well>
        {view.hasCost && (
          <p className="review-kinds">
            <span className="muted">{t("ch_kinds")}</span>
            {view.kinds.map((kind) => (
              <span key={kind.kind}>
                {kind.label} <b className="num">{kind.total}</b>
              </span>
            ))}
            <Link
              className="review-kinds-link"
              href={`#${reviewPath(project, "models", range, { section: KINDS_SECTION })}`}
            >
              {t("ch_kinds_link")}
            </Link>
          </p>
        )}
        <div className="review-foot">
          {view.unpricedLines.map((line) => (
            <p key={line} className="review-unpriced">
              {line}
            </p>
          ))}
          <p>{t("foot_est", { date: dateWords(answer.prices.as_of) })}</p>
          {answer.prices.cross_check_state === "disagree" && disagreed.length > 0 && (
            <p className="review-warn">
              <span aria-hidden="true">{"▲ "}</span>
              {t("foot_disagree", { model: disagreed.join(", ") })}
            </p>
          )}
        </div>
      </>
    );
  }

  return (
    <Card title={heading} question={t("ch_q")} className="review-cost">
      <div ref={root} className="review-cost-body">
        {chart.failed && <StaleLine updatedAt={chart.updatedAt} />}
        {shown !== undefined && range !== "all" && (
          <ChartPager
            shown={shown}
            loading={answer === undefined}
            chart={chart}
            onNewest={goNewest}
          />
        )}
        {body}
      </div>
    </Card>
  );
}
