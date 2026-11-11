/* "Who is working": the tokens-per-minute chart over the lane rows, in one card (entries 20 and 22). */
import { Card } from "@/components/Card/Card";
import { HelpButton } from "@/components/HelpButton/HelpButton";
import { SkeletonBones } from "@/components/SkeletonBones/SkeletonBones";
import { StackedBars } from "@/components/StackedBars/StackedBars";
import { TimelineLane } from "@/components/TimelineLane/TimelineLane";
import type { TimelineLaneProps } from "@/components/TimelineLane/TimelineLane";
import type { ChartView } from "@/lib/live-chart";
import { t } from "@/strings/t";

export function WhoCard({
  chart,
  lane,
}: {
  chart: ChartView;
  lane: Pick<TimelineLaneProps, "axis" | "items" | "note" | "label">;
}) {
  return (
    <Card
      title={t("tl_h")}
      question={t("tl_q")}
      className="live-who"
      right={<HelpButton help="live.who" />}
    >
      <div className="live-who-body">
        <StackedBars
          bars={chart.bars}
          models={chart.models}
          yTicks={chart.yTicks}
          xLabels={chart.xLabels}
          legend={chart.legend}
          axisLabel={chart.axisLabel}
          summary={chart.summary}
        />
        <TimelineLane axis={lane.axis} items={lane.items} note={lane.note} label={lane.label} />
      </div>
    </Card>
  );
}

export function WhoLoading() {
  return (
    <Card title={t("tl_h")} question={t("tl_q")}>
      <SkeletonBones
        label=""
        className="live-who-bones"
        bones={[
          { width: "full" },
          { width: "full" },
          { width: "full" },
          { width: "full" },
          { width: "full" },
        ]}
      />
    </Card>
  );
}
