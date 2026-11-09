import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiContext, createApiClient } from "@/api/client";
import { FAILURES_TO_LOST, useSessionsFeed, useTimelineFeed, usePageVisible } from "@/api/live";
import { createAccess, STORAGE_KEYS } from "@/app/access";
import { createConnection } from "@/lib/connection";
import { liveSessions, INSTANCE } from "@/test/server";
import { liveSession, sessionOf, timeline } from "@/test/timelines";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-09T10:00:00Z"));
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  setVisibility("visible");
});

function setVisibility(state: "visible" | "hidden"): void {
  Object.defineProperty(document, "visibilityState", { configurable: true, value: state });
  document.dispatchEvent(new Event("visibilitychange"));
}

type Reply = () => Response | Promise<Response>;

/** A fetch that answers from a queue and keeps every path it was asked for. */
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
  return { wrapper, access };
}

async function tick(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("useTimelineFeed", () => {
  it("loads, then polls every second with the last etag", async () => {
    const s = script();
    s.always(json(timeline()));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useTimelineFeed("builder", "s1", true), { wrapper });
    expect(result.current.loading).toBe(true);
    await tick(0);
    expect(result.current.feed?.answer.etag).toBe("etag-a");
    expect(s.calls[0]).toBe("/api/sessions/s1/timeline?project=builder");
    await tick(1000);
    expect(s.calls[1]).toBe("/api/sessions/s1/timeline?project=builder&etag=etag-a");
    await tick(2000);
    expect(s.count("/timeline")).toBe(4);
  });

  it("keeps the last full answer when the reply is unchanged, and moves the server time", async () => {
    const s = script();
    const full = timeline();
    s.once(json(full));
    s.always(
      json({
        etag: "etag-a",
        project: "builder",
        server_time: "2026-10-30T22:40:07Z",
        unchanged: true,
      }),
    );
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useTimelineFeed("builder", "s1", true), { wrapper });
    await tick(0);
    const first = result.current.feed;
    await tick(1000);
    expect(result.current.feed?.answer).toBe(first?.answer);
    expect(result.current.feed?.serverMs).toBe(Date.parse("2026-10-30T22:40:07Z"));
    expect(result.current.feed?.receivedAt).toBeGreaterThan(first?.receivedAt ?? Infinity);
  });

  it("replaces the answer when the etag changes", async () => {
    const s = script();
    s.once(json(timeline()));
    s.always(json(timeline({ etag: "etag-b" })));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useTimelineFeed("builder", "s1", true), { wrapper });
    await tick(1000);
    expect(result.current.feed?.answer.etag).toBe("etag-b");
  });

  it("makes no request while inactive, and one at once when it turns active", async () => {
    const s = script();
    s.always(json(timeline()));
    const { wrapper } = await setup(s.fetchFn);
    const { result, rerender } = renderHook(
      ({ active }: { active: boolean }) => useTimelineFeed("builder", "s1", active),
      { wrapper, initialProps: { active: true } },
    );
    await tick(0);
    expect(result.current.feed).toBeDefined();
    rerender({ active: false });
    const before = s.count("/timeline");
    await tick(5000);
    expect(s.count("/timeline")).toBe(before);
    rerender({ active: true });
    await tick(0);
    expect(s.count("/timeline")).toBe(before + 1);
  });

  it("holds the feed with no session", async () => {
    const s = script();
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useTimelineFeed("builder", null, true), { wrapper });
    await tick(5000);
    expect(s.calls).toEqual([]);
    expect(result.current.loading).toBe(false);
  });

  it("polls an ended session every 10 seconds", async () => {
    const s = script();
    s.always(
      json(
        timeline({
          session: sessionOf({ state: "ended", running: false, ended_at: "2026-10-30T22:30:00Z" }),
        }),
      ),
    );
    const { wrapper } = await setup(s.fetchFn);
    renderHook(() => useTimelineFeed("builder", "s1", true), { wrapper });
    await tick(0);
    expect(s.count("/timeline")).toBe(1);
    await tick(9000);
    expect(s.count("/timeline")).toBe(1);
    await tick(1000);
    expect(s.count("/timeline")).toBe(2);
  });

  it("moves to lost after three failed polls in a row and retries every 10 seconds", async () => {
    const s = script();
    s.once(json(timeline()));
    s.always(down);
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useTimelineFeed("builder", "s1", true), { wrapper });
    await tick(0);
    expect(result.current.lost).toBe(false);
    await tick(1000);
    await tick(1000);
    expect(result.current.failures).toBe(FAILURES_TO_LOST - 1);
    expect(result.current.lost).toBe(false);
    await tick(1000);
    expect(result.current.lost).toBe(true);
    // the last good answer stays
    expect(result.current.feed?.answer.etag).toBe("etag-a");
    const after = s.count("/timeline");
    await tick(9000);
    expect(s.count("/timeline")).toBe(after);
    await tick(1000);
    expect(s.count("/timeline")).toBe(after + 1);
  });

  it("clears lost on the first good answer and goes back to one second", async () => {
    const s = script();
    s.always(down);
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useTimelineFeed("builder", "s1", true), { wrapper });
    await tick(2000);
    expect(result.current.lost).toBe(true);
    s.always(json(timeline()));
    await tick(10_000);
    expect(result.current.lost).toBe(false);
    expect(result.current.failures).toBe(0);
    const before = s.count("/timeline");
    await tick(2000);
    expect(s.count("/timeline")).toBe(before + 2);
  });

  it("polls at once on Try now", async () => {
    const s = script();
    s.always(down);
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useTimelineFeed("builder", "s1", true), { wrapper });
    await tick(2000);
    const before = s.count("/timeline");
    s.always(json(timeline()));
    act(() => {
      result.current.retryNow();
    });
    await tick(0);
    expect(s.count("/timeline")).toBe(before + 1);
    expect(result.current.lost).toBe(false);
    expect(result.current.feed).toBeDefined();
  });

  it("does not count a failure, and stops polling, when the session is gone", async () => {
    const s = script();
    s.always(json({ code: "unknown_session", path: null }, 404));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useTimelineFeed("builder", "s1", true), { wrapper });
    await tick(0);
    expect(result.current.refusal?.code).toBe("unknown_session");
    expect(result.current.feed).toBeUndefined();
    expect(result.current.loading).toBe(false);
    expect(result.current.failures).toBe(0);
    await tick(5000);
    expect(s.count("/timeline")).toBe(1);
  });

  it("does not stop the tab on failed Live polls", async () => {
    const s = script();
    s.always(down);
    const { wrapper, access } = await setup(s.fetchFn);
    renderHook(() => useTimelineFeed("builder", "s1", true), { wrapper });
    await tick(5000);
    expect(access.getState().kind).not.toBe("stopped");
  });
});

describe("usePageVisible", () => {
  it("follows the tab", () => {
    const { result } = renderHook(() => usePageVisible());
    expect(result.current).toBe(true);
    act(() => {
      setVisibility("hidden");
    });
    expect(result.current).toBe(false);
    act(() => {
      setVisibility("visible");
    });
    expect(result.current).toBe(true);
  });
});

describe("useSessionsFeed", () => {
  it("polls every 5 seconds and keeps the list on unchanged", async () => {
    const s = script();
    const list = liveSessions({ sessions: [liveSession("s1")] });
    s.once(json(list));
    s.always(json({ etag: list.etag, server_time: "2026-11-08T15:42:09Z", unchanged: true }));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSessionsFeed("builder", true), { wrapper });
    await tick(0);
    const first = result.current.feed?.answer;
    expect(first?.sessions).toHaveLength(1);
    expect(s.calls[0]).toBe("/api/live/sessions?project=builder");
    await tick(4000);
    expect(s.count("/live/sessions")).toBe(1);
    await tick(1000);
    expect(s.count("/live/sessions")).toBe(2);
    expect(s.calls[1]).toBe(`/api/live/sessions?project=builder&etag=${list.etag}`);
    expect(result.current.feed?.answer).toBe(first);
  });

  it("holds while inactive", async () => {
    const s = script();
    s.always(json(liveSessions()));
    const { wrapper } = await setup(s.fetchFn);
    const { rerender } = renderHook(
      ({ active }: { active: boolean }) => useSessionsFeed("builder", active),
      {
        wrapper,
        initialProps: { active: false },
      },
    );
    await tick(0);
    const before = s.count("/live/sessions");
    await tick(20_000);
    expect(s.count("/live/sessions")).toBe(before);
    rerender({ active: true });
    await tick(0);
    expect(s.count("/live/sessions")).toBe(before + 1);
  });
});
