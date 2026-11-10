import { focusManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiContext, createApiClient } from "@/api/client";
import {
  SETUP_POLL_MS,
  problemsFor,
  toFixNav,
  useProblems,
  useSetupMap,
  useSetupPart,
} from "@/api/setup";
import type { ProblemList, ProblemRow, SetupMap, SetupPartAnswer } from "@/api/types";
import { createAccess, STORAGE_KEYS } from "@/app/access";
import { createConnection } from "@/lib/connection";
import { appInfo, INSTANCE } from "@/test/server";

const SERVER_TIME = "2026-11-10T15:00:00Z";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-10T15:00:00Z"));
});
afterEach(() => {
  cleanup();
  focusManager.setFocused(undefined);
  vi.useRealTimers();
});

function setupMap(over: Partial<SetupMap> = {}): SetupMap {
  return {
    project: "builder",
    server_time: SERVER_TIME,
    server_started_at: "2026-11-10T09:00:00Z",
    as_of: SERVER_TIME,
    etag: "map-a",
    unchanged: false,
    listed: true,
    notices: [],
    parts: [],
    ...over,
  };
}

function partAnswer(over: Partial<SetupPartAnswer> = {}): SetupPartAnswer {
  return {
    project: "builder",
    part: "agents",
    server_time: SERVER_TIME,
    as_of: SERVER_TIME,
    etag: "part-a",
    unchanged: false,
    items: [],
    groups: [],
    unreadable: [],
    empty: null,
    ...over,
  };
}

function problemList(over: Partial<ProblemList> = {}): ProblemList {
  return {
    project: "builder",
    server_time: SERVER_TIME,
    as_of: SERVER_TIME,
    etag: "prob-a",
    unchanged: false,
    counted: 0,
    rows: [],
    ...over,
  };
}

const short = (etag: string, serverTime = SERVER_TIME) => ({
  project: "builder",
  server_time: serverTime,
  etag,
  unchanged: true as const,
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
  return { wrapper, client };
}

async function tick(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

/** One 10 second poll, then a short wait for the reply to be read. */
async function poll(): Promise<void> {
  await tick(SETUP_POLL_MS);
  await tick(50);
}

describe("the map query", () => {
  it("asks with the project, then polls every 10 seconds with the last etag", async () => {
    const s = script();
    s.always(json(setupMap()));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSetupMap("builder"), { wrapper });
    expect(result.current.loading).toBe(true);
    await tick(0);
    expect(result.current.loading).toBe(false);
    expect(result.current.answer?.etag).toBe("map-a");
    expect(s.calls[0]).toBe("/api/setup?project=builder");
    await tick(SETUP_POLL_MS - 1);
    expect(s.calls).toHaveLength(1);
    await tick(1);
    expect(s.calls[1]).toBe("/api/setup?project=builder&etag=map-a");
  });

  it("keeps the cached answer on an unchanged reply and takes only the new server time", async () => {
    const s = script();
    s.once(json(setupMap()));
    s.always(json(short("map-a", "2026-11-10T15:01:00Z")));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSetupMap("builder"), { wrapper });
    await tick(0);
    const first = result.current;
    await poll();
    expect(result.current.answer).toBe(first.answer);
    expect(result.current.serverMs).toBe(Date.parse("2026-11-10T15:01:00Z"));
    expect(result.current.receivedAt).toBeGreaterThan(first.receivedAt ?? 0);
    expect(result.current.failed).toBe(false);
  });

  it("takes a new answer when the etag moves", async () => {
    const s = script();
    s.once(json(setupMap()));
    s.always(json(setupMap({ etag: "map-b", listed: false })));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSetupMap("builder"), { wrapper });
    await poll();
    expect(result.current.answer?.etag).toBe("map-b");
    expect(result.current.answer?.listed).toBe(false);
  });

  it("asks again with no etag when a short reply comes with nothing stored", async () => {
    const s = script();
    s.once(json(short("map-z")));
    s.always(json(setupMap()));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSetupMap("builder"), { wrapper });
    await tick(0);
    expect(result.current.answer?.etag).toBe("map-a");
    expect(s.calls).toHaveLength(2);
    expect(s.calls[1]).toBe("/api/setup?project=builder");
  });

  it("keeps each project under its own key", async () => {
    const s = script();
    s.always(json(setupMap()));
    const { wrapper } = await setup(s.fetchFn);
    const { result, rerender } = renderHook(({ project }) => useSetupMap(project), {
      wrapper,
      initialProps: { project: "builder" },
    });
    await tick(0);
    expect(result.current.answer).toBeDefined();
    rerender({ project: "driftwood" });
    expect(result.current.answer).toBeUndefined();
    expect(result.current.loading).toBe(true);
    await tick(0);
    expect(s.calls[1]).toBe("/api/setup?project=driftwood");
  });
});

describe("visible and hidden tabs", () => {
  it("does not refetch while the tab is hidden", async () => {
    const s = script();
    s.always(json(setupMap()));
    const { wrapper } = await setup(s.fetchFn);
    renderHook(() => useSetupMap("builder"), { wrapper });
    await tick(0);
    expect(s.calls).toHaveLength(1);
    await act(async () => {
      focusManager.setFocused(false);
      await vi.advanceTimersByTimeAsync(SETUP_POLL_MS * 3);
    });
    expect(s.calls).toHaveLength(1);
  });

  it("refetches at once with the last etag when the tab comes back, then keeps polling", async () => {
    const s = script();
    s.always(json(setupMap()));
    const { wrapper } = await setup(s.fetchFn);
    renderHook(() => useSetupMap("builder"), { wrapper });
    await tick(0);
    await act(async () => {
      focusManager.setFocused(false);
      await vi.advanceTimersByTimeAsync(SETUP_POLL_MS * 2);
    });
    expect(s.calls).toHaveLength(1);
    await act(async () => {
      focusManager.setFocused(true);
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(s.calls).toHaveLength(2);
    expect(s.calls[1]).toContain("&etag=map-a");
    await tick(SETUP_POLL_MS);
    expect(s.calls).toHaveLength(3);
  });
});

describe("errors and empty stay apart", () => {
  it("is an error, not empty, when the first fetch fails", async () => {
    const s = script();
    s.always(down);
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSetupPart("builder", "agents"), { wrapper });
    await tick(0);
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.empty).toBe(false);
    expect(result.current.loading).toBe(false);
    expect(result.current.failed).toBe(false);
    expect(result.current.answer).toBeUndefined();
  });

  it("is empty, not an error, for a good answer with no items", async () => {
    const s = script();
    s.always(json(partAnswer({ empty: { reason: "none_found", action: null, target: null } })));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSetupPart("builder", "agents"), { wrapper });
    await tick(0);
    expect(result.current.empty).toBe(true);
    expect(result.current.error).toBeNull();
    expect(s.calls[0]).toBe("/api/setup/agents?project=builder");
  });

  it("keeps the last good answer when a refetch fails and then recovers", async () => {
    const s = script();
    s.once(json(partAnswer()));
    s.once(down);
    s.always(json(short("part-a")));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useSetupPart("builder", "agents"), { wrapper });
    await tick(0);
    const good = result.current.answer;
    await poll();
    expect(result.current.failed).toBe(true);
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.answer).toBe(good);
    expect(result.current.loading).toBe(false);
    await poll();
    expect(result.current.failed).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.answer).toBe(good);
  });

  it("keys a part by its name", async () => {
    const s = script();
    s.always(json(partAnswer()));
    const { wrapper } = await setup(s.fetchFn);
    const { rerender } = renderHook(({ part }) => useSetupPart("builder", part), {
      wrapper,
      initialProps: { part: "agents" as "agents" | "skills" },
    });
    await tick(0);
    rerender({ part: "skills" });
    await tick(0);
    expect(s.calls).toEqual([
      "/api/setup/agents?project=builder",
      "/api/setup/skills?project=builder",
    ]);
  });
});

describe("the problems feed and the app answer", () => {
  it("refetches the app answer when the problems etag moves", async () => {
    const s = script();
    s.once(json(problemList({ etag: "prob-a" })));
    s.always(json(problemList({ etag: "prob-b" })));
    const { wrapper, client } = await setup(s.fetchFn);
    client.setQueryData(
      ["app", "builder"],
      appInfo({ to_fix: { state: "ok", count: 0, etag: "prob-a" } }),
    );
    const invalidate = vi.spyOn(client, "invalidateQueries");
    renderHook(() => useProblems("builder"), { wrapper });
    await tick(0);
    expect(invalidate).not.toHaveBeenCalled();
    await poll();
    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["app", "builder"] });
    expect(s.calls[0]).toBe("/api/problems?project=builder");
  });

  it("leaves the app answer alone when it already carries the same etag", async () => {
    const s = script();
    s.always(json(problemList({ etag: "prob-a" })));
    const { wrapper, client } = await setup(s.fetchFn);
    client.setQueryData(
      ["app", "builder"],
      appInfo({ to_fix: { state: "ok", count: 2, etag: "prob-a" } }),
    );
    const invalidate = vi.spyOn(client, "invalidateQueries");
    renderHook(() => useProblems("builder"), { wrapper });
    await tick(0);
    await poll();
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("filters the rows that name one item", () => {
    const rows = [
      { id: "r1", item_id: "agents:a" },
      { id: "r2", item_id: null },
      { id: "r3", item_id: "agents:b" },
    ] as ProblemRow[];
    expect(problemsFor(rows, { id: "agents:a" }).map((row) => row.id)).toEqual(["r1"]);
  });
});

describe("toFixNav", () => {
  it("reads a count from an ok state", () => {
    const app = appInfo({ to_fix: { state: "ok", count: 3, etag: "prob-a" } });
    expect(toFixNav(app)).toEqual({ state: "ok", count: 3, etag: "prob-a" });
  });

  it("reads a zero count from an ok state with no count", () => {
    const app = appInfo({ to_fix: { state: "ok", count: null, etag: "prob-a" } });
    expect(toFixNav(app)).toEqual({ state: "ok", count: 0, etag: "prob-a" });
  });

  it("keeps unchecked apart, with no count", () => {
    const app = appInfo({ to_fix: { state: "unchecked", count: null, etag: null } });
    expect(toFixNav(app)).toEqual({ state: "unchecked", count: null, etag: null });
  });

  it("keeps failed apart from unchecked, with no count", () => {
    const app = appInfo({ to_fix: { state: "failed", count: null, etag: "prob-a" } });
    expect(toFixNav(app)).toEqual({ state: "failed", count: null, etag: "prob-a" });
  });

  it("is unchecked before the first app answer", () => {
    expect(toFixNav(undefined)).toEqual({ state: "unchecked", count: null, etag: null });
  });

  it("falls back to to_fix_count when the server sends no to_fix", () => {
    expect(toFixNav(appInfo({ to_fix_count: 4 }))).toEqual({ state: "ok", count: 4, etag: null });
    expect(toFixNav(appInfo({ to_fix_count: null }))).toEqual({
      state: "unchecked",
      count: null,
      etag: null,
    });
  });
});
