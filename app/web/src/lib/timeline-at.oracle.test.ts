/// <reference types="node" />
/*
 * The page-at-T oracle. For each live_flow scenario the new server's end-of-session answer
 * (app/fixtures/oracle/live/<scenario>/new-end.json, written by app/oracle/timelines.py) is read at
 * every T the old app was recorded at (at-*.json), and the values timeline-at.ts picks are compared
 * with the old answer's runs, parents, rounds, states, tokens and cost. The differences that
 * allowed-differences.json lists are handled where they apply. Old times carry a -04:00 offset, so
 * T comes from the `at` field, which is UTC. An old run's `tokens` is new tokens plus cache reads.
 *
 * Cumulative numbers are bucket-granular, so tokens and cost are compared at the T that fall on a
 * bucket boundary. States, parents and rounds are compared at every T.
 *
 * A bucket holds [start, end), so at a boundary T the picker leaves out a request stamped exactly T
 * (the old answer counts ts <= T, and the flow builds put a request on most minute marks). The
 * oracle takes the requests the old answer lists at exactly T out of its numbers before comparing.
 * A run's numbers are compared at a bucket-aligned T, except when its route key is shared by
 * several runs and a request at exactly T carries that key, because the old answer does not say
 * which of the runs the request belongs to. The four loosenings are listed in
 * allowed-differences.json (requests-at-t, bucket-aligned-t, shared-route-keys, half-open-bucket).
 */
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { Timeline } from "@/api/types";
import { valuesAt } from "@/lib/timeline-at";

const ORACLE = resolve(import.meta.dirname, "..", "..", "..", "fixtures", "oracle", "live");

function load(path: string): unknown {
  return JSON.parse(readFileSync(join(ORACLE, path), "utf8")) as unknown;
}

interface OldRun {
  run_id: string;
  route_key: string;
  parent: string | null;
  parent_known: boolean;
  state: "working" | "idle" | "done";
  tokens: number;
  cost: number | null;
  rounds: { n: number; started: string; last_request: string; by: string | null }[];
}

interface OldAnswer {
  at: string;
  session: { started: string; last_request: string; active: boolean } | null;
  runs: OldRun[];
  totals: { tokens: number; cost: number | null; unpriced_requests: number; requests: number };
  requests: { ts: string; route_key: string; tokens: number; cost: number | null }[];
}

interface Manifest {
  scenarios: Record<string, { sampled: string[] }>;
}

interface Allowed {
  differences: { id: string }[];
}

const manifest = load("manifest.json") as Manifest;
const allowed = load("allowed-differences.json") as Allowed;
const STATE_WORDS = { working: "working", idle: "idle", done: "finished" } as const;
const SCENARIOS = ["busy", "many", "unlinked", "empty"] as const;

const main = (id: string | null): string | null => (id === "@main" ? "main" : id);
const close = (a: number | null, b: number | null): boolean =>
  a === null || b === null
    ? a === b
    : Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));

describe("the allowed differences this oracle handles", () => {
  it("are the ones the file lists", () => {
    const ids = allowed.differences.map((d) => d.id);
    for (const id of [
      "runs-not-started",
      "state-words",
      "label-numbers",
      "last-minute-bucket",
      "requests-at-t",
      "bucket-aligned-t",
      "shared-route-keys",
      "half-open-bucket",
    ]) {
      expect(ids).toContain(id);
    }
  });
});

describe.each(SCENARIOS)("the %s scenario picked at every recorded T", (scenario) => {
  const end = load(`${scenario}/new-end.json`) as Timeline;
  const stamps = manifest.scenarios[scenario]?.sampled ?? [];
  const bucketMs = end.axis.bucket_seconds * 1000;
  const startMs = Date.parse(end.axis.start);

  it("has recorded times", () => {
    expect(stamps.length).toBeGreaterThan(0);
  });

  it("matches run states, parents, rounds, tokens and cost", () => {
    let compared = 0;
    let aligned = 0;
    let checked = 0;
    let wasChecked = 0;
    let total = 0;
    for (const stamp of stamps) {
      const old = load(`${scenario}/at-${stamp}.json`) as OldAnswer;
      if (old.session === null) continue;
      const t = Date.parse(old.at);
      const where = `${scenario} ${stamp}`;
      const at = valuesAt(end, t);
      // allowed difference 1: runs not started at T appear in the new answer
      const here = at.runs.filter((run) => run.state !== "not_started");
      expect(here.map((run) => run.runId).sort(), where).toEqual(
        old.runs.map((run) => main(run.run_id)).sort(),
      );
      expect(at.session === "working", `${where} session active`).toBe(old.session.active);
      const byId = new Map(here.map((run) => [run.runId, run]));
      const exact = (t - startMs) % bucketMs === 0;
      const boundary = old.requests.filter((request) => Date.parse(request.ts) === t);
      const adjust = (key: string): { tokens: number; cost: number } => ({
        tokens: boundary.filter((r) => r.route_key === key).reduce((sum, r) => sum + r.tokens, 0),
        cost: boundary
          .filter((r) => r.route_key === key)
          .reduce((sum, r) => sum + (r.cost ?? 0), 0),
      });
      for (const was of old.runs) {
        const id = main(was.run_id) ?? "";
        const mine = byId.get(id);
        const place = `${where} ${id}`;
        expect(mine, place).toBeDefined();
        if (mine === undefined) continue;
        // allowed difference 2: done reads as finished
        expect(mine.state, `${place} state`).toBe(STATE_WORDS[was.state]);
        expect(mine.parent, `${place} parent`).toBe(main(was.parent));
        expect(mine.parentKnown, `${place} parent known`).toBe(was.parent_known);
        expect(
          mine.rounds.map((r) => [r.n, r.at, main(r.by)]),
          `${place} rounds`,
        ).toEqual(was.rounds.map((r) => [r.n, Date.parse(r.started), main(r.by)]));
        for (const [index, round] of mine.rounds.entries()) {
          const oldRound = was.rounds[index];
          if (oldRound === undefined) continue;
          const oldLast = Date.parse(oldRound.last_request);
          const label = `${place} round ${String(round.n)} last request`;
          // A round that ended by T has its exact last request. One still going at T reports the
          // answer's last request held to T, which is never below what T had seen.
          if (end.runs.find((r) => r.run_id === id)?.rounds[index] !== undefined) {
            const final = Date.parse(
              end.runs.find((r) => r.run_id === id)?.rounds[index]?.last_request ?? "",
            );
            if (final <= t) expect(round.lastRequest, label).toBe(oldLast);
            else expect(round.lastRequest, label).toBeGreaterThanOrEqual(oldLast);
          }
          expect(round.lastRequest, label).toBeLessThanOrEqual(t);
        }
        total += 1;
        const alone = old.runs.filter((r) => r.route_key === was.route_key).length === 1;
        // Skipped only when a request at exactly T has this route key and the key is shared, so
        // the request cannot be told apart between the runs.
        const touched = !alone && boundary.some((r) => r.route_key === was.route_key);
        if (exact && alone) wasChecked += 1;
        if (exact && !touched) {
          const gone = adjust(was.route_key);
          expect(mine.cum.tokens + mine.cum.cache_read, `${place} tokens`).toBe(
            was.tokens - gone.tokens,
          );
          const cost = was.cost === null ? null : was.cost - gone.cost;
          expect(
            close(mine.cum.cost, cost),
            `${place} cost ${String(mine.cum.cost)} ${String(cost)}`,
          ).toBe(true);
          checked += 1;
        }
      }
      if (exact) {
        aligned += 1;
        const gone = boundary.reduce((sum, r) => sum + r.tokens, 0);
        const goneCost = boundary.reduce((sum, r) => sum + (r.cost ?? 0), 0);
        expect(at.totals.tokens + at.totals.cache_read, `${where} totals tokens`).toBe(
          old.totals.tokens - gone,
        );
        expect(
          close(at.totals.cost, (old.totals.cost ?? 0) - goneCost),
          `${where} totals cost`,
        ).toBe(true);
      }
      compared += 1;
    }
    expect(compared).toBeGreaterThan(0);
    if (scenario !== "empty") {
      expect(aligned).toBeGreaterThan(0);
      expect(checked).toBeGreaterThan(0);
      // Shared route keys no longer drop a run unless a request at exactly T touches the key.
      expect(checked).toBeGreaterThanOrEqual(wasChecked);
      expect(checked).toBeLessThanOrEqual(total);
    }
    if (scenario === "many") {
      expect(
        checked,
        "many checks more than its run rows with a route key to itself",
      ).toBeGreaterThan(wasChecked);
    }
  });
});
