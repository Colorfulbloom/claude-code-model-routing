/*
 * Session review, #/p/<project>/review/sessions/<id>: one session replayed minute by minute. The
 * page owns the timeline feed (5 s while the session runs, never after it ends), the replay line's
 * state (`?at=` through useReplay) and the choice of session. Every value on screen at the line
 * comes from the one timeline answer, so a drag or a key never asks the server.
 *
 * States. First load shows bones. A session on screen is running or ended, and a lost feed keeps
 * the last good numbers with a finding above them. An unknown session id shows the gone state.
 * A running session follows Now while the line sits at the end and stays where the owner put it
 * once moved. The page title and the route status come from the route harness.
 */
import { useNavigate, useParams } from "react-router";
import { Link } from "react-aria-components";
import { useAppInfo, useProjects } from "@/api/client";
import { usePageVisible, useReviewTimelineFeed } from "@/api/live";
import { useSessions } from "@/api/review";
import { projectHref } from "@/app/nav";
import { Button } from "@/components/Button/Button";
import { RaisedFinding } from "@/components/RaisedFinding/RaisedFinding";
import { RunStateGlyph } from "@/components/RunStateGlyph/RunStateGlyph";
import { clockMedium, clockShort, dayLong } from "@/lib/clock";
import { formatDuration } from "@/lib/duration";
import { reviewPath, useRangeParam } from "@/lib/range";
import { backLabel, selectHeading } from "@/lib/range-phrase";
import { useReplay } from "@/lib/replay";
import { buildReplayTiles } from "@/lib/replay-view";
import { choiceValue, limitChoices, sessionChoices } from "@/lib/session-choices";
import { t, tn } from "@/strings/t";
import { LiveHeader } from "../live/LiveHeader";
import { LostFinding } from "../live/LiveStates";
import { SessionSelect } from "../live/SessionSelect";
import { ReplayTiles, ReplayTilesLoading } from "./ReplayTiles";
import { ReplayWho, ReplayWhoLoading } from "./ReplayWho";
import "../LivePage.css";
import "./SessionReviewPage.css";

export function SessionReviewPage() {
  const { project, id } = useParams();
  if (project === undefined || id === undefined) return null;
  return <SessionReview key={`${project}/${id}`} project={project} id={id} />;
}

const stateWord = (state: "working" | "idle" | "ended"): string =>
  state === "working" ? t("rs_working") : state === "idle" ? t("rs_idle") : t("rs_ended");

function SessionReview({ project, id }: { project: string; id: string }) {
  const navigate = useNavigate();
  const { range } = useRangeParam();
  const projects = useProjects();
  const app = useAppInfo(project);
  const visible = usePageVisible();
  const feed = useReviewTimelineFeed(project, id, visible);
  const sessions = useSessions(project, range);
  const timeline = feed.feed?.answer;
  const replay = useReplay(timeline);

  const projectName =
    projects.data?.projects.find((entry) => entry.key === project)?.name ?? project;
  const oldest = sessions.head?.window.oldest ?? app.data?.history.oldest ?? null;
  const back = (
    <Link className="sreview-back" href={`#${reviewPath(project, "sessions", range)}`}>
      <span aria-hidden="true">{"←"}</span>
      {backLabel(range, oldest)}
    </Link>
  );

  // The link names a session this project does not have.
  if (feed.refusal !== null) {
    return (
      <>
        <LiveHeader
          back={back}
          state={null}
          title={t("gone_title")}
          sub={null}
          when={null}
          select={null}
          pause={null}
        />
        <RaisedFinding
          variant="error"
          title={t("gone_h", { project: projectName })}
          className="live-gone"
        >
          <p>{t("gone_b")}</p>
          <div className="live-acts">
            <Button variant="primary" href={`#${reviewPath(project, "sessions", range)}`}>
              {t("gone_all")}
            </Button>
          </div>
        </RaisedFinding>
      </>
    );
  }

  // First load, or the calls fail before any answer.
  if (timeline === undefined || replay === null || feed.feed === undefined) {
    return (
      <>
        <LiveHeader
          back={back}
          state={null}
          title={t("pg_session")}
          sub={null}
          when={null}
          select={null}
          pause={null}
        />
        {feed.lost && <LostFinding time={null} onRetry={feed.retryNow} />}
        <div aria-busy="true">
          <ReplayTilesLoading />
          <ReplayWhoLoading />
        </div>
      </>
    );
  }

  const { session } = timeline;
  const tz = sessions.head?.window.tz ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
  const choices = sessionChoices(
    sessions.days.flatMap((day) => day.sessions),
    session,
    tz,
    feed.feed.serverMs,
  );
  const here = choices.find((choice) => choice.id === session.id);
  const startedMs = Date.parse(session.started);
  const endedMs = Date.parse(session.ended_at ?? session.last_request);
  const sub = session.running
    ? t("sr_sub_running", { project: projectName, start: clockShort(startedMs) })
    : t("sr_sub_ended", {
        project: projectName,
        date: dayLong(startedMs),
        start: clockShort(startedMs),
        end: clockShort(endedMs),
        dur: formatDuration(endedMs - startedMs),
      });
  const count = sessions.head?.count ?? null;
  const select = (
    <>
      <SessionSelect
        label={t("rv_session_scope")}
        valueLabel={here === undefined ? "" : choiceValue(here)}
        heading={selectHeading(range, oldest)}
        items={limitChoices(choices, session.id).map((choice) => ({
          id: choice.id,
          label: choice.time,
          group: choice.group,
          description: (
            <span className="live-opt">
              {/* The board shows a state only for a session that is not over, so an ended one
                  reads as its branch alone. */}
              {choice.state !== "ended" && (
                <RunStateGlyph state={choice.state}>{stateWord(choice.state)}</RunStateGlyph>
              )}
              <span className="live-opt-project">{choice.branch ?? t("lv_no_branch")}</span>
            </span>
          ),
        }))}
        value={session.id}
        onChange={(next) => {
          void navigate(reviewPath(project, { session: next }, range));
        }}
        all={{
          label: count === null ? t("ss_all") : tn("sel_all", count),
          href: `#${reviewPath(project, "sessions", range)}`,
        }}
        closeLabel={t("pk_close")}
      />
      {session.running && (
        <Button href={projectHref(project, `/live?session=${encodeURIComponent(session.id)}`)}>
          {t("rv_open_live")}
        </Button>
      )}
    </>
  );

  return (
    <>
      <LiveHeader
        back={back}
        state={{ kind: session.state, word: stateWord(session.state) }}
        title={session.branch ?? t("lv_no_branch")}
        {...(session.branch === null ? { titleMuted: true } : {})}
        sub={sub}
        when={null}
        select={select}
        pause={null}
      />
      {feed.lost && <LostFinding time={clockMedium(feed.feed.serverMs)} onRetry={feed.retryNow} />}
      <ReplayTiles view={buildReplayTiles(timeline, replay)} />
      <ReplayWho timeline={timeline} replay={replay} serverMs={feed.feed.serverMs} />
    </>
  );
}
