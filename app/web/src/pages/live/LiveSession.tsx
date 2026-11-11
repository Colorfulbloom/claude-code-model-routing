/*
 * One session on screen: header, tiles, Who is working, Model check and Latest requests, all from
 * one timeline answer. It is keyed by session id, so a switch starts with a clean baseline for the
 * announcer, no moved rings and every fold closed.
 */
import { useEffect, useState } from "react";
import type { LiveFeed } from "@/api/live";
import type { Timeline } from "@/api/types";
import { postStatus } from "@/app/harness";
import { Button } from "@/components/Button/Button";
import { HelpButton } from "@/components/HelpButton/HelpButton";
import { clockMedium, clockShort } from "@/lib/clock";
import { formatDuration } from "@/lib/duration";
import { axisFor, buildChart } from "@/lib/live-chart";
import { buildLane } from "@/lib/live-lanes";
import { buildRequests, buildTiles } from "@/lib/live-tiles";
import { useIsDesktop } from "@/lib/media";
import { buildModelCheck } from "@/lib/model-check";
import { useAnnouncer } from "@/lib/use-announcer";
import { useMovedRuns } from "@/lib/use-moved";
import { t } from "@/strings/t";
import { LiveHeader } from "./LiveHeader";
import { LiveTiles } from "./LiveTiles";
import { LostFinding } from "./LiveStates";
import { ModelCheckCard } from "./ModelCheckCard";
import { RequestsCard } from "./RequestsCard";
import { WhoCard } from "./WhoCard";

export interface LiveSessionProps {
  feed: LiveFeed<Timeline>;
  /** Now on the page clock, in epoch milliseconds. */
  nowMs: number;
  projectName: string;
  select: React.ReactNode;
  /** The "a newer session started" notice, above the header. */
  notice: { text: string; onSwitch: () => void } | null;
  /** The page time Pause was pressed, or null while polling runs. */
  pausedAt: number | null;
  lost: { onRetry: () => void } | null;
  onTogglePause: () => void;
  /** Models the two price sources disagree on. */
  priceDisagree: string[];
  visible: boolean;
}

export function LiveSession({
  feed,
  nowMs,
  projectName,
  select,
  notice,
  pausedAt,
  lost,
  onTogglePause,
  priceDisagree,
  visible,
}: LiveSessionProps) {
  const answer = feed.answer;
  const { session } = answer;
  // A hidden tab and Pause both end polling, so the first answer after either is a baseline.
  useAnnouncer(feed, visible && pausedAt === null);
  // The newer-session notice stays on screen without a live region of its own. The page's one
  // polite region says it, once, when it appears or its text changes.
  const noticeText = notice?.text ?? null;
  useEffect(() => {
    if (noticeText !== null) postStatus(noticeText);
  }, [noticeText]);
  const desktop = useIsDesktop();
  const moved = useMovedRuns(answer, nowMs);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());

  const axis = axisFor(answer, nowMs);
  const chart = buildChart(answer, axis);
  const lane = buildLane(answer, {
    nowMs,
    axis,
    desktop,
    expanded,
    moved,
    onToggle: (runId) => {
      setExpanded((current) => {
        const next = new Set(current);
        if (!next.delete(runId)) next.add(runId);
        return next;
      });
    },
  });
  const ended = session.state === "ended";
  const startedMs = Date.parse(session.started);
  const endedMs = Date.parse(session.ended_at ?? session.last_request);
  const common = {
    project: projectName,
    start: clockShort(startedMs),
  };
  const sub = ended
    ? t("lv_sub_ended", { ...common, dur: formatDuration(endedMs - startedMs) })
    : t("lv_sub_live", { ...common, dur: formatDuration(nowMs - startedMs) });
  const when =
    pausedAt !== null
      ? t("lv_paused_at", { time: clockMedium(pausedAt) })
      : lost !== null
        ? t("lv_lost_at", { time: clockMedium(feed.serverMs) })
        : ended
          ? t("lv_ended_at", { time: clockShort(endedMs) })
          : null;
  const word =
    session.state === "working"
      ? t("rs_working")
      : session.state === "idle"
        ? t("rs_idle")
        : t("rs_ended");

  return (
    <>
      {notice !== null && (
        <p className="live-notice">
          <span className="live-notice-mark" aria-hidden="true">
            {"●"}
          </span>
          <span className="live-notice-text">{notice.text}</span>
          <Button onPress={notice.onSwitch}>{t("nt_switch_btn")}</Button>
        </p>
      )}
      <LiveHeader
        state={{ kind: session.state, word }}
        title={session.branch ?? t("lv_no_branch")}
        {...(session.branch === null ? { titleMuted: true } : {})}
        sub={sub}
        when={when}
        stateHelp={<HelpButton help="live.status" word={word} />}
        whenHelp={<HelpButton help="live.notices" />}
        select={select}
        pause={
          ended
            ? null
            : { label: pausedAt !== null ? t("lv_resume") : t("lv_pause"), onPress: onTogglePause }
        }
      />
      {lost !== null && <LostFinding time={clockMedium(feed.serverMs)} onRetry={lost.onRetry} />}
      <LiveTiles view={buildTiles(answer)} />
      <WhoCard chart={chart} lane={lane} />
      <div className="grid-two live-lower">
        <ModelCheckCard help="live.modelcheck" view={buildModelCheck(answer.model_check)} />
        <RequestsCard
          rows={buildRequests(answer)}
          prices={{
            asOf: answer.prices.as_of,
            disagree:
              answer.prices.cross_check_state === "disagree" && priceDisagree.length > 0
                ? priceDisagree.join(", ")
                : null,
          }}
        />
      </div>
    </>
  );
}
