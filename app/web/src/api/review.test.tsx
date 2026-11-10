import { focusManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiContext, createApiClient } from "@/api/client";
import { useReviewTimelineFeed } from "@/api/live";
import {
  REVIEW_POLL_MS,
  cardError,
  dayBefore,
  localDate,
  mergeSessionPages,
  useAgents,
  useCostChart,
  useModels,
  useSessions,
  useSummary,
} from "@/api/review";
import type { ReviewRange, ReviewSession, SessionList } from "@/api/types";
import { createAccess, STORAGE_KEYS } from "@/app/access";
import { createConnection } from "@/lib/connection";
import {
  AS_OF,
  agentList,
  costChart,
  modelList,
  sessionList,
  sessionRow,
  summary,
  unchanged,
} from "@/test/review";
import { INSTANCE } from "@/test/server";
import { sessionOf, timeline } from "@/test/timelines";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-09T15:00:00Z"));
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

type Reply = () => Response | Promise<Response>;

/** A fetch that answers from a queue, then from a fallback, and keeps every path it was asked for. */
function script() {
  const calls: string[] = [];
  const queue: Reply[] = [];
  let fallback: Reply = () => new Response("{}");
  const fetchFn: typeof fetch = (input) => {
    calls.push(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
    const next = queue.shift() ?? fallback;
    return Promise.resolve(next());
  };
  return {
    calls,
    fetchFn,
    always(reply: Reply) {
      fallback = reply;
    },
    once(reply: Reply) {
      queue.push(reply);
    },
    count: (part: string) => calls.filter((path) => path.includes(part)).length,
  };
}

const json =
  (body: unknown, status = 200): Reply =>
  () =>
    new Response(JSON.stringify(body), { status });
const down: Reply = () => {
  throw new TypeError("Failed to fetch");
};

async function setup(fetchFn: typeof fetch) {
  sessionStorage.clear();
  sessionStorage.setItem(STORAGE_KEYS.readKey, "key-1");
  sessionStorage.setItem(STORAGE_KEYS.instance, INSTANCE);
  const access = createAccess({
    launch: { nonce: "", instance: INSTANCE, command: "/bartab-preview" },
    makeChannel: () => {
      throw new Error("no channel in this test");
    },
  });
  await access.start();
  const api = createApiClient({ access, connection: createConnection(), fetchFn });
  const client = new QueryClient();
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>
      <ApiContext value={api}>{children}</ApiContext>
    </QueryClientProvider>
  );
  return { wrapper };
}

async function tick(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

/** One 60 second poll, then a short wait for the reply to be read. */
async function poll(): Promise<void> {
  await tick(REVIEW_POLL_MS);
  await tick(50);
}

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("expected a value");
  return value;
}

describe("the shared rules, on the summary", () => {
  it("asks with the project and range, then polls every 60 seconds with the last etag", async () => {
    const s = script();
    s.always(json(summary()));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSummary("builder", "30d"), { wrapper });
    expect(result.current.loading).toBe(true);
    expect(result.current.answer).toBeUndefined();
    await tick(0);
    expect(result.current.loading).toBe(false);
    expect(result.current.answer?.etag).toBe("etag-a");
    expect(s.calls[0]).toBe("/api/summary?project=builder&range=30d");
    await tick(REVIEW_POLL_MS - 1);
    expect(s.calls).toHaveLength(1);
    await tick(1);
    expect(s.calls[1]).toBe("/api/summary?project=builder&range=30d&etag=etag-a");
  });

  it("keeps the last full answer on unchanged and takes only the new server time", async () => {
    const s = script();
    s.once(json(summary()));
    s.always(json(unchanged("etag-a", "2026-11-09T15:01:00Z")));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSummary("builder", "30d"), { wrapper });
    await tick(0);
    const first = result.current;
    await poll();
    expect(result.current.answer).toBe(first.answer);
    expect(result.current.serverMs).toBe(Date.parse("2026-11-09T15:01:00Z"));
    expect(result.current.receivedAt).toBeGreaterThan(need(first.receivedAt));
    expect(result.current.failed).toBe(false);
  });

  it("takes a new answer when the etag changes", async () => {
    const s = script();
    s.once(json(summary()));
    s.always(json(summary({ etag: "etag-b", session_count: 54 })));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSummary("builder", "30d"), { wrapper });
    await poll();
    expect(result.current.answer?.etag).toBe("etag-b");
    expect(result.current.answer?.session_count).toBe(54);
  });

  it("asks again with no etag when a short reply comes with nothing stored", async () => {
    const s = script();
    s.once(json(unchanged("etag-z")));
    s.always(json(summary()));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSummary("builder", "30d"), { wrapper });
    await tick(0);
    expect(result.current.answer?.etag).toBe("etag-a");
    expect(s.calls).toHaveLength(2);
  });

  it("refetches when the window regains focus", async () => {
    const s = script();
    s.always(json(summary()));
    const { wrapper } = await setup(s.fetchFn);
    renderHook(() => useSummary("builder", "30d"), { wrapper });
    await tick(0);
    expect(s.calls).toHaveLength(1);
    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(s.calls).toHaveLength(2);
    expect(s.calls[1]).toContain("&etag=etag-a");
    focusManager.setFocused(undefined);
  });

  it("keeps the last good answer when a refetch fails, and exposes when it was good", async () => {
    const s = script();
    s.once(json(summary()));
    s.once(down);
    s.always(json(summary({ etag: "etag-b" })));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSummary("builder", "30d"), { wrapper });
    await tick(0);
    const good = result.current.answer;
    await poll();
    expect(result.current.failed).toBe(true);
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.answer).toBe(good);
    expect(result.current.loading).toBe(false);
    expect(result.current.asOf).toBe(Date.parse(AS_OF));
    expect(result.current.updatedAt).toBe(Date.parse(AS_OF));
    await poll();
    expect(result.current.failed).toBe(false);
    expect(result.current.answer?.etag).toBe("etag-b");
  });

  it("falls back to the server time for updatedAt when the answer has no as_of", async () => {
    const s = script();
    s.always(json(summary({ as_of: null })));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSummary("builder", "30d"), { wrapper });
    await tick(0);
    expect(result.current.asOf).toBeNull();
    expect(result.current.updatedAt).toBe(Date.parse("2026-11-09T15:00:00Z"));
  });

  it("is not loading and not failed on a first failure, and has no answer", async () => {
    const s = script();
    s.always(down);
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSummary("builder", "30d"), { wrapper });
    await tick(0);
    expect(result.current.loading).toBe(false);
    expect(result.current.failed).toBe(false);
    expect(result.current.answer).toBeUndefined();
    expect(result.current.error).toBeInstanceOf(Error);
  });
});

describe("a range change", () => {
  it("shows no answer while the new range loads, and drops a late answer for the old range", async () => {
    const s = script();
    let release: (response: Response) => void = () => undefined;
    s.once(() => new Promise<Response>((resolve) => (release = resolve)));
    s.always(json(summary({ range: "7d", etag: "etag-7" })));
    const { wrapper } = await setup(s.fetchFn);
    const { result, rerender } = renderHook(
      ({ range }: { range: ReviewRange }) => useSummary("builder", range),
      { wrapper, initialProps: { range: "30d" as ReviewRange } },
    );
    await tick(0);
    expect(result.current.loading).toBe(true);
    rerender({ range: "7d" });
    // The new range has no answer yet, so the card shows bones, not the old range's numbers.
    expect(result.current.answer).toBeUndefined();
    expect(result.current.loading).toBe(true);
    await tick(0);
    expect(result.current.answer?.range).toBe("7d");
    await act(async () => {
      release(new Response(JSON.stringify(summary({ range: "30d", etag: "etag-30" }))));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.answer?.range).toBe("7d");
    expect(result.current.answer?.etag).toBe("etag-7");
    expect(s.calls[1]).toBe("/api/summary?project=builder&range=7d");
  });

  it("never shows the old range's answer under the new range, even when both are loaded", async () => {
    const s = script();
    s.once(json(summary({ range: "30d" })));
    s.always(json(summary({ range: "90d", etag: "etag-90" })));
    const { wrapper } = await setup(s.fetchFn);
    const { result, rerender } = renderHook(
      ({ range }: { range: ReviewRange }) => useSummary("builder", range),
      { wrapper, initialProps: { range: "30d" as ReviewRange } },
    );
    await tick(0);
    expect(result.current.answer?.range).toBe("30d");
    rerender({ range: "90d" });
    expect(result.current.answer).toBeUndefined();
    await tick(0);
    expect(result.current.answer?.range).toBe("90d");
  });
});

describe("per-card errors", () => {
  it("exposes a null model_check and its error, and the rest of the summary stays", async () => {
    const s = script();
    s.always(
      json(
        summary({
          model_check: null,
          errors: [{ card: "model_check", code: "setup_unreadable" }],
        }),
      ),
    );
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSummary("builder", "30d"), { wrapper });
    await tick(0);
    expect(result.current.modelCheck).toBeNull();
    expect(result.current.modelCheckError).toEqual({
      card: "model_check",
      code: "setup_unreadable",
    });
    expect(result.current.errors).toHaveLength(1);
    expect(result.current.answer?.tiles.sessions.value).toBe(53);
  });

  it("has a model check and no error when the card worked", async () => {
    const s = script();
    s.always(json(summary()));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSummary("builder", "30d"), { wrapper });
    await tick(0);
    expect(result.current.modelCheck).toEqual({ rows: [], in_effect_count: 0 });
    expect(result.current.modelCheckError).toBeNull();
  });

  it("exposes the agent setup error on Agents", async () => {
    const s = script();
    s.always(json(agentList({ errors: [{ card: "agent_setup", code: "unexpected" }] })));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useAgents("builder", "30d"), { wrapper });
    await tick(0);
    expect(s.calls[0]).toBe("/api/agents?project=builder&range=30d");
    expect(result.current.setupError).toEqual({ card: "agent_setup", code: "unexpected" });
  });

  it("finds a card error by name", () => {
    const errors = [{ card: "agent_setup", code: "unexpected" }] as const;
    expect(cardError(errors, "agent_setup")?.code).toBe("unexpected");
    expect(cardError(errors, "model_check")).toBeNull();
  });
});

describe("models", () => {
  it("asks for the range and keeps its answer", async () => {
    const s = script();
    s.always(json(modelList({ range: "12m" })));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useModels("builder", "12m"), { wrapper });
    await tick(0);
    expect(s.calls[0]).toBe("/api/models?project=builder&range=12m");
    expect(result.current.answer?.range).toBe("12m");
  });
});

describe("date helpers", () => {
  it("reads the local date of an instant in a zone", () => {
    expect(localDate("2026-11-09T03:00:00Z", "America/New_York")).toBe("2026-11-08");
    expect(localDate("2026-11-09T05:00:00Z", "America/New_York")).toBe("2026-11-09");
    expect(localDate("2026-11-09T23:30:00Z", "Asia/Tokyo")).toBe("2026-11-10");
  });

  it("steps back one calendar day across a month and a year", () => {
    expect(dayBefore("2026-11-01")).toBe("2026-10-31");
    expect(dayBefore("2026-01-01")).toBe("2025-12-31");
    expect(dayBefore("2026-03-01")).toBe("2026-02-28");
  });
});

describe("useCostChart", () => {
  const newest = costChart();
  // The window before the newest: ends 2026-10-10 local, starts 30 days earlier.
  const older = costChart({
    etag: "etag-old",
    chart: {
      start: "2026-09-11T04:00:00Z",
      end: "2026-10-11T04:00:00Z",
      unit: "day",
      has_earlier: false,
      has_later: true,
      earlier_reason: "no_earlier_data",
      later_reason: null,
      newest: false,
    },
  });

  function chartServer() {
    const s = script();
    s.always(() => {
      const last = s.calls.at(-1) ?? "";
      return new Response(JSON.stringify(last.includes("&end=2026-10-10") ? older : newest));
    });
    return s;
  }

  it("asks for the newest window with no end", async () => {
    const s = chartServer();
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useCostChart("builder", "30d"), { wrapper });
    await tick(0);
    expect(s.calls[0]).toBe("/api/cost-chart?project=builder&range=30d");
    expect(result.current.end).toBeNull();
    expect(result.current.canEarlier).toBe(true);
    expect(result.current.canLater).toBe(false);
  });

  it("moves one window back to the day before this one starts, and forward again", async () => {
    const s = chartServer();
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useCostChart("builder", "30d"), { wrapper });
    await tick(0);
    act(() => {
      result.current.earlier();
    });
    // While the earlier window loads there is no answer, so the chart shows bones.
    expect(result.current.answer).toBeUndefined();
    await tick(0);
    expect(s.calls[1]).toBe("/api/cost-chart?project=builder&range=30d&end=2026-10-10");
    expect(result.current.end).toBe("2026-10-10");
    expect(result.current.answer?.chart.newest).toBe(false);
    expect(result.current.canEarlier).toBe(false);
    expect(result.current.canLater).toBe(true);
    act(() => {
      result.current.later();
    });
    await tick(0);
    expect(result.current.end).toBeNull();
    expect(result.current.answer?.chart.newest).toBe(true);
  });

  it("does nothing at an end of the pager", async () => {
    const s = chartServer();
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useCostChart("builder", "30d"), { wrapper });
    await tick(0);
    act(() => {
      result.current.later();
    });
    expect(result.current.end).toBeNull();
    act(() => {
      result.current.earlier();
    });
    await tick(0);
    act(() => {
      result.current.earlier();
    });
    expect(result.current.end).toBe("2026-10-10");
  });

  it("resets to the newest window when the range changes", async () => {
    const s = chartServer();
    const { wrapper } = await setup(s.fetchFn);
    const { result, rerender } = renderHook(
      ({ range }: { range: ReviewRange }) => useCostChart("builder", range),
      { wrapper, initialProps: { range: "30d" as ReviewRange } },
    );
    await tick(0);
    act(() => {
      result.current.earlier();
    });
    await tick(0);
    expect(result.current.end).toBe("2026-10-10");
    rerender({ range: "90d" });
    expect(result.current.end).toBeNull();
    await tick(0);
    expect(s.calls.at(-1)).toBe("/api/cost-chart?project=builder&range=90d");
  });

  it("goes back to the newest window on demand", async () => {
    const s = chartServer();
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useCostChart("builder", "30d"), { wrapper });
    await tick(0);
    act(() => {
      result.current.earlier();
    });
    await tick(0);
    act(() => {
      result.current.newest();
    });
    expect(result.current.end).toBeNull();
  });
});

/** A fake sessions server over an array of rows, newest first, with an anchored cursor. */
function sessionServer(initial: { id: string; day: string }[], pageSize: number) {
  let rows = initial;
  let version = 0;
  const s = script();
  const rowOf = (entry: { id: string; day: string }): ReviewSession =>
    sessionRow(entry.id, { started: `${entry.day}T12:00:00Z` });
  s.always(() => {
    const url = new URL(need(s.calls.at(-1)), "http://bartab.test");
    const cursor = url.searchParams.get("cursor");
    const etag = url.searchParams.get("etag");
    const from = cursor === null ? 0 : rows.findIndex((row) => row.id === cursor) + 1;
    const slice = rows.slice(from, from + pageSize);
    const next = from + pageSize < rows.length ? (slice.at(-1)?.id ?? null) : null;
    const days: SessionList["days"] = [];
    for (const row of slice) {
      const last = days.at(-1);
      if (last?.day === row.day) last.sessions.push(rowOf(row));
      else days.push({ day: row.day, sessions: [rowOf(row)] });
    }
    const tag = `${cursor ?? "top"}:${slice.map((row) => row.id).join(",")}:${String(rows.length)}`;
    if (etag === tag) return new Response(JSON.stringify(unchanged(tag)));
    return new Response(
      JSON.stringify(sessionList(days, { count: rows.length, next, etag: tag, as_of: AS_OF })),
    );
  });
  return {
    ...s,
    addOnTop(row: { id: string; day: string }) {
      rows = [row, ...rows];
      version += 1;
    },
    version: () => version,
  };
}

const idsOf = (days: { sessions: { id: string }[] }[]): string[] =>
  days.flatMap((day) => day.sessions.map((session) => session.id));

describe("mergeSessionPages", () => {
  it("never repeats a session and joins a day split across pages", () => {
    const one = sessionList(
      [
        { day: "2026-11-09", sessions: [sessionRow("a")] },
        { day: "2026-11-08", sessions: [sessionRow("b")] },
      ],
      { next: "b" },
    );
    const two = sessionList([
      { day: "2026-11-08", sessions: [sessionRow("b"), sessionRow("c"), sessionRow("d")] },
      { day: "2026-11-07", sessions: [sessionRow("e")] },
    ]);
    const merged = mergeSessionPages([one, two]);
    expect(merged.map((day) => day.day)).toEqual(["2026-11-09", "2026-11-08", "2026-11-07"]);
    expect(idsOf(merged)).toEqual(["a", "b", "c", "d", "e"]);
  });
});

describe("useSessions", () => {
  const rows = [
    { id: "a", day: "2026-11-09" },
    { id: "b", day: "2026-11-08" },
    { id: "c", day: "2026-11-08" },
    { id: "d", day: "2026-11-08" },
    { id: "e", day: "2026-11-07" },
  ];

  it("loads the first page and says how many there are", async () => {
    const server = sessionServer(rows, 2);
    const { wrapper } = await setup(server.fetchFn);
    const { result } = renderHook(() => useSessions("builder", "30d"), { wrapper });
    expect(result.current.loading).toBe(true);
    await tick(0);
    expect(server.calls[0]).toBe("/api/sessions?project=builder&range=30d");
    expect(result.current.loading).toBe(false);
    expect(result.current.count).toBe(5);
    expect(result.current.loaded).toBe(2);
    expect(result.current.remaining).toBe(3);
    expect(result.current.hasMore).toBe(true);
    expect(result.current.firstNewId).toBeNull();
    expect(idsOf(result.current.days)).toEqual(["a", "b"]);
    expect(result.current.head?.window.tz).toBe("America/New_York");
  });

  it("loads more with the cursor, joins the split day and reports the first new row", async () => {
    const server = sessionServer(rows, 2);
    const { wrapper } = await setup(server.fetchFn);
    const { result } = renderHook(() => useSessions("builder", "30d"), { wrapper });
    await tick(0);
    let firstNew: string | null = null;
    await act(async () => {
      firstNew = await result.current.loadMore();
    });
    expect(server.calls[1]).toBe("/api/sessions?project=builder&range=30d&cursor=b");
    expect(firstNew).toBe("c");
    expect(result.current.firstNewId).toBe("c");
    expect(result.current.loaded).toBe(4);
    expect(result.current.days.map((day) => day.day)).toEqual(["2026-11-09", "2026-11-08"]);
    expect(idsOf(result.current.days)).toEqual(["a", "b", "c", "d"]);
    expect(result.current.hasMore).toBe(true);
    await act(async () => {
      await result.current.loadMore();
    });
    expect(result.current.firstNewId).toBe("e");
    expect(result.current.hasMore).toBe(false);
    expect(result.current.loaded).toBe(5);
    expect(result.current.remaining).toBe(0);
  });

  it("clears the first new row when the range changes", async () => {
    const server = sessionServer(rows, 2);
    const { wrapper } = await setup(server.fetchFn);
    const { result, rerender } = renderHook(
      ({ range }: { range: ReviewRange }) => useSessions("builder", range),
      { wrapper, initialProps: { range: "30d" as ReviewRange } },
    );
    await tick(0);
    await act(async () => {
      await result.current.loadMore();
    });
    expect(result.current.firstNewId).toBe("c");
    rerender({ range: "7d" });
    expect(result.current.firstNewId).toBeNull();
    expect(result.current.days).toEqual([]);
    expect(result.current.loading).toBe(true);
  });

  it("keeps loaded rows in place and never repeats one when a new session arrives at the top", async () => {
    const server = sessionServer(rows, 2);
    const { wrapper } = await setup(server.fetchFn);
    const { result } = renderHook(() => useSessions("builder", "30d"), { wrapper });
    await tick(0);
    await act(async () => {
      await result.current.loadMore();
    });
    const before = idsOf(result.current.days);
    expect(before).toEqual(["a", "b", "c", "d"]);
    const firstNew = result.current.firstNewId;

    server.addOnTop({ id: "z", day: "2026-11-09" });
    await poll();

    const after = idsOf(result.current.days);
    expect(new Set(after).size).toBe(after.length);
    expect(after[0]).toBe("z");
    // Every row that stays keeps its order. The page window moved down by one, so the last
    // loaded row can slide into the next page, but no row is repeated or reordered.
    expect(after.slice(1)).toEqual(before.slice(0, after.length - 1));
    expect(result.current.count).toBe(6);
    expect(result.current.days[0]?.day).toBe("2026-11-09");
    expect(result.current.firstNewId).toBe(firstNew);
    expect(result.current.hasMore).toBe(true);
    // The refetch walked the loaded pages from the top, with the cursor each page gave.
    const refetch = server.calls.slice(-2);
    expect(refetch[0]).toContain("range=30d&etag=");
    expect(refetch[1]).toContain("&cursor=a");
  });

  it("sends each page's own etag and keeps the pages when nothing changed", async () => {
    const server = sessionServer(rows, 2);
    const { wrapper } = await setup(server.fetchFn);
    const { result } = renderHook(() => useSessions("builder", "30d"), { wrapper });
    await tick(0);
    await act(async () => {
      await result.current.loadMore();
    });
    const days = result.current.days;
    await poll();
    const refetch = server.calls.slice(-2);
    expect(refetch[0]).toContain("&etag=top");
    expect(refetch[1]).toContain("&cursor=b&etag=b");
    expect(idsOf(result.current.days)).toEqual(["a", "b", "c", "d"]);
    expect(result.current.days).toStrictEqual(days);
    expect(result.current.failed).toBe(false);
  });

  it("keeps the loaded rows when a refetch fails, and when Show more fails", async () => {
    const server = sessionServer(rows, 2);
    const { wrapper } = await setup(server.fetchFn);
    const { result } = renderHook(() => useSessions("builder", "30d"), { wrapper });
    await tick(0);
    server.once(down);
    await act(async () => {
      await result.current.loadMore();
    });
    await tick(0);
    expect(result.current.loadMoreError).toBeInstanceOf(Error);
    expect(result.current.error).toBeNull();
    expect(idsOf(result.current.days)).toEqual(["a", "b"]);
    expect(result.current.firstNewId).toBeNull();
    server.once(down);
    await poll();
    expect(result.current.failed).toBe(true);
    expect(idsOf(result.current.days)).toEqual(["a", "b"]);
    expect(result.current.updatedAt).toBe(Date.parse(AS_OF));
  });
});

describe("useReviewTimelineFeed", () => {
  const running = timeline();
  const ended = timeline({
    etag: "etag-end",
    session: sessionOf({ state: "ended", running: false, active: false }),
  });

  it("polls every 5 seconds with the etag while the session runs", async () => {
    const s = script();
    s.always(json(running));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useReviewTimelineFeed("builder", "s1", true), { wrapper });
    await tick(0);
    expect(s.calls[0]).toBe("/api/sessions/s1/timeline?project=builder");
    expect(result.current.feed?.answer.etag).toBe("etag-a");
    await tick(4_999);
    expect(s.calls).toHaveLength(1);
    await tick(1);
    expect(s.calls[1]).toBe("/api/sessions/s1/timeline?project=builder&etag=etag-a");
    await tick(10_000);
    expect(s.calls).toHaveLength(4);
  });

  it("stops for good once the session has ended", async () => {
    const s = script();
    s.once(json(running));
    s.always(json(ended));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useReviewTimelineFeed("builder", "s1", true), { wrapper });
    await tick(5_000);
    expect(result.current.feed?.answer.session.state).toBe("ended");
    expect(s.calls).toHaveLength(2);
    await tick(60_000);
    expect(s.calls).toHaveLength(2);
  });

  it("does not poll an ended session after its first answer", async () => {
    const s = script();
    s.always(json(ended));
    const { wrapper } = await setup(s.fetchFn);
    renderHook(() => useReviewTimelineFeed("builder", "s1", true), { wrapper });
    await tick(30_000);
    expect(s.calls).toHaveLength(1);
  });

  it("holds while the tab is hidden", async () => {
    const s = script();
    s.always(json(running));
    const { wrapper } = await setup(s.fetchFn);
    renderHook(() => useReviewTimelineFeed("builder", "s1", false), { wrapper });
    await tick(20_000);
    expect(s.calls).toHaveLength(1);
  });

  it("keeps its own cache apart from Live's feed", async () => {
    const s = script();
    s.always(json(running));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useReviewTimelineFeed("builder", "s1", true), { wrapper });
    await tick(0);
    expect(result.current.refusal).toBeNull();
    expect(result.current.lost).toBe(false);
  });
});
