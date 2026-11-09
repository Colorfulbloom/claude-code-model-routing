/*
 * What the polite live region says on Live. It is a pure diff of two answers. It speaks only when a
 * run starts, finishes or begins another round, and when the session ends or comes back. It never
 * speaks for working to idle, never twice for one row inside a minute (by the answer's own time),
 * and joins several finishes in one poll into one line. A line a row is not yet allowed to speak
 * is held, not dropped, and speaks on the first poll after the row's minute ends. A row keeps one
 * held line, and a later line for the row replaces the earlier one, because it covers it (a finish
 * covers a start or a round). A held line that is no longer true when its time comes is dropped,
 * and a held session ended and resumed cancel each other. A run that finishes the moment its starter
 * becomes known (a foreground run, fact V-7b16) speaks one line that says who started it.
 *
 * The first answer after a load, a session switch, a return from a hidden tab or a Resume after
 * Pause is a baseline, and the caller passes `prev` as null for it, so it says nothing.
 */
import type { Timeline, TimelineRun } from "@/api/types";
import { clockShort } from "@/lib/clock";
import { runLabel } from "@/lib/run-label";
import { t } from "@/strings/t";

/** One row speaks at most once per this long. */
export const ROW_LIMIT_MS = 60_000;
const SESSION_ROW = "@session";

/** When each row last spoke, in epoch milliseconds of the answers' own time. */
export type Spoken = Readonly<Record<string, number>>;

/** What a row has to say, held until its quiet minute ends. The text is built when it speaks. */
export interface HeldLine {
  kind: "start" | "round" | "finish" | "ended" | "resumed";
  /** For a finish: the run's starter became known in the same poll. */
  moved: boolean;
}

/** The held lines, by row. */
export type Held = Readonly<Record<string, HeldLine>>;

export interface Announcement {
  lines: string[];
  spoken: Spoken;
  held: Held;
}

function joinNames(names: readonly string[]): string {
  if (names.length < 2) return names.join("");
  return t("list_and", { list: names.slice(0, -1).join(", "), last: names.at(-1) ?? "" });
}

function parentName(run: TimelineRun, next: Timeline): string | null {
  if (!run.parent_known || run.parent === null) return null;
  if (run.parent === "main") return t("tl_main");
  const parent = next.runs.find((candidate) => candidate.run_id === run.parent);
  return parent === undefined ? null : runLabel(parent);
}

interface Finish {
  name: string;
  parent: string | null;
  moved: boolean;
}

/**
 * The lines for the change from `prev` to `next`. With no `prev` it is a baseline and says nothing.
 * `spoken` is the memory of the last lines and `held` the lines still waiting for their row's
 * minute to end. The result carries both, updated. `at` is the time of the poll, which differs from
 * `next.server_time` only when the poll answered unchanged, so held lines still come out then.
 */
export function diffAnnouncements(
  prev: Timeline | null,
  next: Timeline,
  spoken: Spoken,
  held: Held = {},
  at: number = Date.parse(next.server_time),
): Announcement {
  if (prev === null) return { lines: [], spoken, held: {} };
  const memory: Record<string, number> = { ...spoken };
  const pending: Record<string, HeldLine> = { ...held };
  const ready: [string, HeldLine][] = [];

  const quiet = (row: string): boolean => {
    const last = memory[row];
    return last !== undefined && at - last < ROW_LIMIT_MS;
  };

  /** A new line for a row. It speaks now, or waits in the row's one held slot. */
  function offer(row: string, line: HeldLine): void {
    if (row === SESSION_ROW && pending[row] !== undefined) {
      // Ended then resumed (or the reverse) before either spoke: the listener heard no change.
      delete pending[row];
    } else if (quiet(row)) {
      pending[row] = line;
    } else {
      delete pending[row];
      memory[row] = at;
      ready.push([row, line]);
    }
  }

  const before = new Map(prev.runs.map((run) => [run.run_id, run]));
  for (const run of next.runs) {
    const was = before.get(run.run_id);
    if (was === undefined) {
      offer(run.run_id, { kind: run.state === "finished" ? "finish" : "start", moved: false });
    } else if (run.rounds.length > was.rounds.length) {
      offer(run.run_id, { kind: "round", moved: false });
    } else if (run.state === "finished" && was.state !== "finished") {
      offer(run.run_id, { kind: "finish", moved: !was.parent_known && run.parent_known });
    }
  }
  const ended = next.session.state === "ended";
  if (ended !== (prev.session.state === "ended")) {
    offer(SESSION_ROW, { kind: ended ? "ended" : "resumed", moved: false });
  }

  // Held lines whose row is out of its minute speak now, if they are still true.
  const byId = new Map(next.runs.map((run) => [run.run_id, run]));
  for (const [row, line] of Object.entries(pending)) {
    if (quiet(row)) continue;
    const run = byId.get(row);
    const stands =
      row === SESSION_ROW
        ? (line.kind === "ended") === ended
        : run !== undefined && (line.kind !== "finish" || run.state === "finished");
    delete pending[row];
    if (stands) {
      memory[row] = at;
      ready.push([row, line]);
    }
  }

  const starts: string[] = [];
  const rounds: string[] = [];
  const finishes: Finish[] = [];
  const session: string[] = [];
  for (const [row, line] of ready) {
    if (row === SESSION_ROW) {
      session.push(
        line.kind === "ended"
          ? t("an_ended", { time: clockShort(next.session.ended_at ?? next.server_time) })
          : t("an_resumed"),
      );
      continue;
    }
    const run = byId.get(row);
    if (run === undefined) continue;
    const name = runLabel(run);
    if (line.kind === "start") {
      const parent = parentName(run, next);
      starts.push(parent === null ? t("an_start", { name }) : t("an_start_by", { name, parent }));
    } else if (line.kind === "round") {
      rounds.push(t("an_round", { name, n: run.rounds.length }));
    } else {
      finishes.push({ name, parent: parentName(run, next), moved: line.moved });
    }
  }

  const lines = [...starts, ...rounds];
  const [only] = finishes;
  if (finishes.length > 1) {
    lines.push(t("an_batch", { list: joinNames(finishes.map((finish) => finish.name)) }));
  } else if (only !== undefined) {
    lines.push(
      only.moved && only.parent !== null
        ? t("an_finish_moved", { name: only.name, parent: only.parent })
        : t("an_finish", { name: only.name }),
    );
  }
  lines.push(...session);
  return { lines, spoken: memory, held: pending };
}
