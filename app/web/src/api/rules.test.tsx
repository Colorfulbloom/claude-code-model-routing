import { focusManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiContext, createApiClient } from "@/api/client";
import { RULES_POLL_MS, useRules } from "@/api/rules";
import type { RuleRow, RulesAnswer } from "@/api/types";
import { createAccess, STORAGE_KEYS } from "@/app/access";
import { createConnection } from "@/lib/connection";
import { INSTANCE } from "@/test/server";

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

function rule(over: Partial<RuleRow> = {}): RuleRow {
  return {
    combine: "highest_layer",
    confidence: "tested",
    due: false,
    experiment: null,
    key: "effortLevel",
    layer_order: ["env", "user", "default"],
    outcomes: ["in_effect"],
    quotes: [{ doc_url: "https://code.claude.com/docs/en/model-config", quote: "A quote." }],
    rule_id: "effort-level-main",
    scope: "main",
    verified_on: { claude_version: "2.1.302", date: "2026-10-29" },
    ...over,
  };
}

function rulesAnswer(over: Partial<RulesAnswer> = {}): RulesAnswer {
  return {
    checked_on: "2.1.302",
    etag: "rules-a",
    installed: "2.1.302",
    rules: [rule()],
    server_time: SERVER_TIME,
    unchanged: false,
    ...over,
  };
}

const short = (etag: string, serverTime = SERVER_TIME) => ({
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

/** One poll, then a short wait for the reply to be read. */
async function poll(): Promise<void> {
  await tick(RULES_POLL_MS);
  await tick(50);
}

describe("the rules query", () => {
  it("loads once with no etag, then polls every minute with the last etag", async () => {
    const s = script();
    s.always(json(rulesAnswer()));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useRules(), { wrapper });
    expect(result.current.loading).toBe(true);
    expect(result.current.answer).toBeUndefined();
    await tick(0);
    expect(result.current.loading).toBe(false);
    expect(result.current.answer?.etag).toBe("rules-a");
    expect(result.current.answer?.rules).toHaveLength(1);
    expect(result.current.empty).toBe(false);
    expect(result.current.serverMs).toBe(Date.parse(SERVER_TIME));
    expect(s.calls).toEqual(["/api/rules"]);
    await tick(RULES_POLL_MS - 1);
    expect(s.calls).toHaveLength(1);
    await tick(1);
    expect(s.calls[1]).toBe("/api/rules?etag=rules-a");
  });

  it("keeps the cached answer on an unchanged reply and takes only the new server time", async () => {
    const s = script();
    s.once(json(rulesAnswer()));
    s.always(json(short("rules-a", "2026-11-10T15:01:00Z")));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useRules(), { wrapper });
    await tick(0);
    const first = result.current;
    await poll();
    expect(result.current.answer).toBe(first.answer);
    expect(result.current.serverMs).toBe(Date.parse("2026-11-10T15:01:00Z"));
    expect(result.current.receivedAt).toBeGreaterThan(first.receivedAt ?? 0);
    expect(result.current.failed).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("takes a new answer when the etag moves", async () => {
    const s = script();
    s.once(json(rulesAnswer()));
    s.always(json(rulesAnswer({ etag: "rules-b", rules: [rule({ due: true })] })));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useRules(), { wrapper });
    await poll();
    expect(result.current.answer?.etag).toBe("rules-b");
    expect(result.current.answer?.rules[0]?.due).toBe(true);
  });

  it("asks again with no etag when a short reply comes with nothing stored", async () => {
    const s = script();
    s.once(json(short("rules-z")));
    s.always(json(rulesAnswer()));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useRules(), { wrapper });
    await tick(0);
    expect(result.current.answer?.etag).toBe("rules-a");
    expect(s.calls).toEqual(["/api/rules", "/api/rules"]);
  });

  it("is an error, not an answer, when the server only ever sends short replies", async () => {
    const s = script();
    s.always(json(short("rules-z")));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useRules(), { wrapper });
    await tick(0);
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.answer).toBeUndefined();
    expect(result.current.empty).toBe(false);
  });

  it("is empty, not an error, for a good answer with no rules", async () => {
    const s = script();
    s.always(json(rulesAnswer({ rules: [] })));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useRules(), { wrapper });
    await tick(0);
    expect(result.current.empty).toBe(true);
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it("does not refetch while the tab is hidden, and refetches at once when it comes back", async () => {
    const s = script();
    s.always(json(rulesAnswer()));
    const { wrapper } = await setup(s.fetchFn);
    renderHook(() => useRules(), { wrapper });
    await tick(0);
    await act(async () => {
      focusManager.setFocused(false);
      await vi.advanceTimersByTimeAsync(RULES_POLL_MS * 3);
    });
    expect(s.calls).toHaveLength(1);
    await act(async () => {
      focusManager.setFocused(true);
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(s.calls).toHaveLength(2);
    expect(s.calls[1]).toBe("/api/rules?etag=rules-a");
  });
});

describe("errors stay apart from empty", () => {
  it("is an error, not empty, when the first fetch fails", async () => {
    const s = script();
    s.always(down);
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useRules(), { wrapper });
    await tick(0);
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.empty).toBe(false);
    expect(result.current.loading).toBe(false);
    expect(result.current.failed).toBe(false);
    expect(result.current.answer).toBeUndefined();
  });

  it("is an error when the server refuses with a bad request", async () => {
    const s = script();
    s.always(json({ code: "bad_request" }, 400));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useRules(), { wrapper });
    await tick(0);
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.answer).toBeUndefined();
  });

  it("keeps the last good answer when a refetch fails, then recovers", async () => {
    const s = script();
    s.once(json(rulesAnswer()));
    s.once(down);
    s.always(json(short("rules-a")));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useRules(), { wrapper });
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

  it("fetches again at once when retry is called", async () => {
    const s = script();
    s.once(down);
    s.always(json(rulesAnswer()));
    const { wrapper } = await setup(s.fetchFn);
    const { result } = renderHook(() => useRules(), { wrapper });
    await tick(0);
    expect(result.current.error).toBeInstanceOf(Error);
    await act(async () => {
      result.current.retry();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.answer?.etag).toBe("rules-a");
    expect(result.current.error).toBeNull();
  });
});
