/*
 * The Live page, #/p/<project>/live?session=<id>. It owns what changes across sessions: the session
 * list (5 s) and the chosen session's timeline (1 s), Pause, the page clock, and the choice of
 * session. Without ?session= it opens the newest running session of the project and writes it into
 * the URL with replace, then stays on it. A newer session raises a notice with Switch. An ended
 * session stays on screen. Everything drawn for a session lives in LiveSession, keyed by its id.
 *
 * States. First load shows bones. A session on screen has working, idle, ended, paused and lost
 * forms. Without a session the page says nothing is running (with the last ended session and the
 * other projects' running ones), that the project has no sessions, or that the link's session is
 * gone.
 */
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { useApi, usePrices, useProjects } from "@/api/client";
import { usePageVisible, useSessionsFeed, useTimelineFeed } from "@/api/live";
import type { LiveSessions, TimelineSession } from "@/api/types";
import { postStatus } from "@/app/harness";
import { projectHref } from "@/app/nav";
import type { SelectOption } from "@/components/Select/Select";
import { RunStateGlyph } from "@/components/RunStateGlyph/RunStateGlyph";
import { clockShort } from "@/lib/clock";
import { usePageClock } from "@/lib/live-clock";
import { modelLabel } from "@/lib/models";
import { t } from "@/strings/t";
import { LiveHeader } from "./live/LiveHeader";
import { LiveSession } from "./live/LiveSession";
import {
  LostFinding,
  NoSessions,
  NothingRunning,
  OtherRunningCard,
  SessionGone,
} from "./live/LiveStates";
import type { OtherRunning } from "./live/LiveStates";
import { LiveTilesLoading } from "./live/LiveTiles";
import { ModelCheckLoading } from "./live/ModelCheckCard";
import { RequestsCard } from "./live/RequestsCard";
import { WhoLoading } from "./live/WhoCard";
import { SessionSelect } from "./live/SessionSelect";
import "./LivePage.css";

const liveHref = (project: string, session: string | null): string =>
  `${projectHref(project, "/live")}${session === null ? "" : `?session=${encodeURIComponent(session)}`}`;

/** The option a session reads as: "feature/quarter-close, 6:10 PM". */
function optionLabel(branch: string | null, started: string): string {
  return t("ss_opt", { branch: branch ?? t("lv_no_branch"), time: clockShort(started) });
}

function stateWord(state: "working" | "idle" | "ended"): string {
  return state === "working" ? t("rs_working") : state === "idle" ? t("rs_idle") : t("rs_ended");
}

interface Entry {
  optionId: string;
  project: string;
  session: string;
}

const optionId = (project: string, session: string): string => `${project}\u001f${session}`;

/** The Session Select's options and what each one opens. */
function sessionOptions(
  project: string,
  list: LiveSessions | undefined,
  current: TimelineSession | null,
): { items: SelectOption[]; entries: Entry[] } {
  const items: SelectOption[] = [];
  const entries: Entry[] = [];
  const seen = new Set<string>();
  function add(
    owner: string,
    session: string,
    branch: string | null,
    started: string,
    state: "working" | "idle" | "ended",
    group: string,
    extra: string | null,
  ): void {
    const id = optionId(owner, session);
    if (seen.has(id)) return;
    seen.add(id);
    entries.push({ optionId: id, project: owner, session });
    items.push({
      id,
      label: optionLabel(branch, started),
      group,
      description: (
        <span className="live-opt">
          <RunStateGlyph state={state}>{stateWord(state)}</RunStateGlyph>
          {extra !== null && <span className="live-opt-project">{extra}</span>}
        </span>
      ),
    });
  }
  if (current !== null) {
    add(project, current.id, current.branch, current.started, current.state, t("ss_this"), null);
  }
  for (const running of list?.sessions ?? []) {
    if (running.project === project) {
      add(project, running.id, running.branch, running.started, running.state, t("ss_this"), null);
    }
  }
  const ended = list?.latest_ended ?? null;
  if (ended !== null) {
    add(project, ended.id, ended.branch, ended.started, "ended", t("ss_this"), null);
  }
  for (const running of list?.sessions ?? []) {
    if (running.project !== project) {
      add(
        running.project,
        running.id,
        running.branch,
        running.started,
        running.state,
        t("ss_other"),
        running.project_name,
      );
    }
  }
  return { items, entries };
}

export function LivePage() {
  const { project } = useParams();
  if (project === undefined) return null;
  return <LiveProject key={project} project={project} />;
}

function LiveProject({ project }: { project: string }) {
  const { access } = useApi();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const sessionParam = search.get("session");
  const projects = useProjects();
  const prices = usePrices();
  const info = projects.data?.projects.find((candidate) => candidate.key === project);
  const projectName = info?.name ?? project;

  // Pause is per tab and not stored. The page time it was pressed at shows in the header.
  const [pausedAt, setPausedAt] = useState<number | null>(null);
  const visible = usePageVisible();
  const active = visible && pausedAt === null;

  const sessions = useSessionsFeed(project, active);
  const list = sessions.feed?.answer;
  const newest = list?.sessions.find((running) => running.project === project) ?? null;
  const chosen = sessionParam ?? newest?.id ?? null;
  const newestId = newest?.id ?? null;

  // The newest running session goes into the URL, and the page stays on it from then on.
  useEffect(() => {
    if (sessionParam === null && newestId !== null) {
      setSearch({ session: newestId }, { replace: true });
    }
  }, [sessionParam, newestId, setSearch]);

  const timeline = useTimelineFeed(project, chosen, active);
  const feed = timeline.feed;
  const clock = usePageClock(
    feed === undefined ? null : { serverMs: feed.serverMs, receivedAt: feed.receivedAt },
    pausedAt !== null,
  );
  const nowMs = clock ?? feed?.serverMs ?? 0;

  // Running sessions the page already knew about when this one opened never raise the notice.
  const [baseline, setBaseline] = useState<{ session: string | null; ids: string[] } | null>(null);
  if (list !== undefined && baseline?.session !== chosen) {
    setBaseline({
      session: chosen,
      ids: list.sessions
        .filter((running) => running.project === project)
        .map((running) => running.id),
    });
  }
  const current = feed?.answer.session ?? null;
  const newer =
    list !== undefined && baseline !== null && current !== null
      ? (list.sessions.find(
          (running) =>
            running.project === project &&
            running.id !== current.id &&
            !baseline.ids.includes(running.id) &&
            Date.parse(running.started) > Date.parse(current.started),
        ) ?? null)
      : null;

  const { items, entries } = sessionOptions(project, list, current);
  function open(entry: Entry | undefined): void {
    if (entry === undefined) return;
    if (entry.project !== project) access.setProject(entry.project);
    void navigate(liveHref(entry.project, entry.session).slice(1));
  }
  const gone = timeline.refusal !== null;
  const select = (
    <SessionSelect
      label={t("sel_label")}
      valueLabel={
        current !== null && !gone
          ? optionLabel(current.branch, current.started)
          : gone
            ? t("sel_pick")
            : t("sel_none")
      }
      placeholder={current === null || gone}
      heading={t("ss_h")}
      items={items}
      value={current !== null && !gone ? optionId(project, current.id) : null}
      onChange={(id) => {
        open(entries.find((entry) => entry.optionId === id));
      }}
      all={{ label: t("ss_all"), href: projectHref(project, "/review/sessions") }}
      closeLabel={t("pk_close")}
    />
  );

  function togglePause(): void {
    if (pausedAt === null) {
      setPausedAt(nowMs);
      postStatus(t("an_paused"));
    } else {
      setPausedAt(null);
      postStatus(t("an_resumed_poll"));
    }
  }

  const otherRunning: OtherRunning[] = (list?.sessions ?? [])
    .filter((running) => running.project !== project)
    .map((running) => ({
      id: running.id,
      project: running.project,
      title: running.branch ?? t("lv_no_branch"),
      meta: `${running.project_name}, ${clockShort(running.started)}`,
      state: running.state,
      stateWord: stateWord(running.state),
      href: projectHref(running.project, `/live?session=${encodeURIComponent(running.id)}`),
    }));
  const otherCard = (
    <OtherRunningCard
      items={otherRunning}
      onOpen={(item) => {
        access.setProject(item.project);
      }}
    />
  );

  const plainHeader = (
    <LiveHeader
      state={null}
      title={t("lv_h1")}
      sub={null}
      when={null}
      select={select}
      pause={null}
    />
  );

  // Session on screen.
  if (chosen !== null && feed !== undefined && !gone) {
    return (
      <LiveSession
        key={chosen}
        feed={feed}
        nowMs={nowMs}
        projectName={projectName}
        select={select}
        notice={
          newer === null
            ? null
            : {
                text: t("nt_switch", {
                  branch: newer.branch ?? t("lv_no_branch"),
                  time: clockShort(newer.started),
                }),
                onSwitch: () => {
                  open({ optionId: "", project, session: newer.id });
                },
              }
        }
        pausedAt={pausedAt}
        lost={timeline.lost ? { onRetry: timeline.retryNow } : null}
        onTogglePause={togglePause}
        priceDisagree={prices.data?.cross_check.models.map(modelLabel) ?? []}
        visible={visible}
      />
    );
  }

  // The link names a session this project does not have.
  if (gone) {
    return (
      <>
        {plainHeader}
        <SessionGone
          project={projectName}
          running={
            newest === null
              ? null
              : {
                  meta: optionLabel(newest.branch, newest.started),
                  onOpen: () => {
                    open({ optionId: "", project, session: newest.id });
                  },
                }
          }
          allHref={projectHref(project, "/review/sessions")}
        />
      </>
    );
  }

  // Nothing chosen and the list is in: nothing running, or no sessions at all.
  if (chosen === null && list !== undefined) {
    const ended = list.latest_ended;
    return (
      <>
        {plainHeader}
        {ended === null ? (
          <NoSessions project={projectName} path={info?.display_path ?? ""} />
        ) : (
          <NothingRunning
            project={projectName}
            last={{
              meta: t("nr_last_meta", {
                branch: ended.branch ?? t("lv_no_branch"),
                time: clockShort(ended.last_request),
              }),
              onOpen: () => {
                open({ optionId: "", project, session: ended.id });
              },
            }}
          />
        )}
        {otherCard}
      </>
    );
  }

  // First load, or the calls fail before any answer.
  const failing = timeline.lost || sessions.lost;
  return (
    <>
      {plainHeader}
      {failing && (
        <LostFinding time={null} onRetry={timeline.lost ? timeline.retryNow : sessions.retryNow} />
      )}
      <div aria-busy="true">
        <LiveTilesLoading />
        <WhoLoading />
        <div className="grid-two live-lower">
          <ModelCheckLoading />
          <RequestsCard rows={[]} prices={null} loading />
        </div>
      </div>
    </>
  );
}
