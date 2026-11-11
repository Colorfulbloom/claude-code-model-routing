/*
 * "Who worked when": the tokens-per-minute chart, the replay line and the lane rows in one card
 * (components.md entries 20, 22 and 23). The chart, the lanes and the line share one x scale. The
 * page owns T. The chart fades after the line through its CSS, and its text alternative follows
 * the line. A drag or a key never asks the server, because every value comes from the one answer.
 */
import { useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { Timeline } from "@/api/types";
import { postStatus } from "@/app/harness";
import { Button } from "@/components/Button/Button";
import { Card } from "@/components/Card/Card";
import { HelpButton } from "@/components/HelpButton/HelpButton";
import { ReplayLine } from "@/components/ReplayLine/ReplayLine";
import { SkeletonBones } from "@/components/SkeletonBones/SkeletonBones";
import { StackedBars } from "@/components/StackedBars/StackedBars";
import { TimelineLane } from "@/components/TimelineLane/TimelineLane";
import { axisFor } from "@/lib/live-chart";
import { useIsDesktop } from "@/lib/media";
import type { Replay } from "@/lib/replay";
import { buildReplayLane } from "@/lib/replay-lanes";
import {
  buildReplayChart,
  keysHint,
  lineLabel,
  precisionLabel,
  settleLine,
  toEndLabel,
} from "@/lib/replay-view";
import { t } from "@/strings/t";

export interface ReplayWhoProps {
  timeline: Timeline;
  replay: Replay;
  /** The latest server time, epoch ms. It sets where a running session's axis ends. */
  serverMs: number;
}

export function ReplayWho({ timeline, replay, serverMs }: ReplayWhoProps) {
  const desktop = useIsDesktop();
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const stage = useRef<HTMLDivElement>(null);
  const axis = axisFor(timeline, serverMs);
  const chart = buildReplayChart(timeline, replay, axis);
  const lane = buildReplayLane(timeline, replay, {
    axis,
    desktop,
    expanded,
    onToggle: (id) => {
      setExpanded((current) => {
        const next = new Set(current);
        if (!next.delete(id)) next.add(id);
        return next;
      });
    },
  });
  const label = lineLabel(timeline, replay);
  const precision = precisionLabel(replay);

  const toEnd = (
    <Button
      onPress={() => {
        replay.toEnd();
        // The button goes away at the end, so focus moves to the line it moved.
        stage.current?.querySelector<HTMLInputElement>(".replay-input")?.focus();
      }}
    >
      {toEndLabel(timeline)}
    </Button>
  );

  return (
    <Card
      title={t("sr_tl_h")}
      className="live-who sreview-who"
      right={
        <span className="sreview-card-end">
          {!replay.atEnd && toEnd}
          <HelpButton help="review.timeline" />
        </span>
      }
    >
      <div className="live-who-body sreview-stage" ref={stage}>
        <div
          className="sreview-chart"
          data-faded={chart.fade < 1 ? "true" : undefined}
          style={{ "--cut": chart.cut, "--fade": chart.fade } as CSSProperties}
        >
          <StackedBars
            bars={chart.bars}
            models={chart.models}
            yTicks={chart.yTicks}
            xLabels={chart.xLabels}
            legend={chart.legend}
            axisLabel={chart.axisLabel}
            summary={chart.summary}
          />
        </div>
        <ReplayLine
          label={t("sr_label")}
          max={replay.max}
          value={replay.minute}
          valueText={label}
          pageStep={replay.step}
          onChange={replay.setMinute}
          onSettle={() => {
            postStatus(settleLine(timeline, replay));
          }}
          showing={
            <>
              <span className="replay-word">{t("sr_showing")}</span> <b className="num">{label}</b>
            </>
          }
          {...(precision !== null ? { precision } : {})}
          hint={keysHint(replay)}
          className="sreview-replay"
        />
        <TimelineLane
          axis={lane.axis}
          items={lane.items}
          cut={lane.cut}
          note={lane.note}
          label={lane.label}
        />
      </div>
    </Card>
  );
}

/** The card while the first answer is on its way. */
export function ReplayWhoLoading() {
  return (
    <Card title={t("sr_tl_h")} className="live-who">
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
