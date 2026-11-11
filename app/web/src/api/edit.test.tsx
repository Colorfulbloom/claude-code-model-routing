import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  createEditClient,
  defaultRequestId,
  EditContext,
  editInvalidationKeys,
  PREVIEW_DEBOUNCE_MS,
  RECHECK_AT_MS,
  REQUEST_ID_PATTERN,
  useDrift,
  useHistory,
  useMarkSeen,
  useOpenWarning,
  usePreview,
  useRecheck,
  useSave,
  useUndo,
} from "@/api/edit";
import type {
  EditClient,
  EditHistory,
  EditPreview,
  EditScope,
  RecheckAnswer,
  SettingsChoice,
} from "@/api/edit";
import { createAccess, STORAGE_KEYS } from "@/app/access";
import type { Access } from "@/app/access";
import { createConnection } from "@/lib/connection";
import { appInfo, INSTANCE } from "@/test/server";

// Made-up keys for the fake server. They only need to be easy to search for in the output.
const READ_KEY = "fake-read-key-0001";
const BUILDER_KEY = "fake-edit-key-builder";
const OTHER_KEY = "fake-edit-key-other";
const SERVER_TIME = "2026-11-11T15:00:00Z";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(SERVER_TIME));
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

// ---------------------------------------------------------------------------------------------
// A fake server.
// ---------------------------------------------------------------------------------------------

interface Call {
  path: string;
  method: string;
  headers: Record<string, string>;
  body: Record<string, unknown> | null;
}

type Reply = Response | Promise<Response>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

function deferred(): { promise: Promise<Response>; resolve: (response: Response) => void } {
  let resolve: (response: Response) => void = () => undefined;
  const promise = new Promise<Response>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function fakeServer() {
  const calls: Call[] = [];
  let handler: (call: Call) => Reply = () => json({ code: "not_found" }, 404);
  let honourAbort = true;
  const fetchFn: typeof fetch = (input, init) => {
    const raw = init?.body;
    const call: Call = {
      path: typeof input === "string" ? input : input instanceof URL ? input.href : input.url,
      method: init?.method ?? "GET",
      headers: { ...(init?.headers as Record<string, string> | undefined) },
      body: typeof raw === "string" ? (JSON.parse(raw) as Record<string, unknown>) : null,
    };
    calls.push(call);
    return new Promise<Response>((resolve, reject) => {
      if (honourAbort) {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      }
      try {
        Promise.resolve(handler(call)).then(resolve, reject);
      } catch (error) {
        reject(error instanceof Error ? error : new Error("handler failed"));
      }
    });
  };
  return {
    calls,
    fetchFn,
    on(next: (call: Call) => Reply) {
      handler = next;
    },
    ignoreAbort() {
      honourAbort = false;
    },
    to(path: string) {
      return calls.filter((call) => call.path.startsWith(path));
    },
  };
}

type Server = ReturnType<typeof fakeServer>;

function preview(seq: number, over: Partial<EditPreview> = {}): EditPreview {
  return {
    server_time: SERVER_TIME,
    seq,
    choice_key: `ck-${String(seq)}`,
    target: {
      scope: "project",
      display_path: ".claude/settings.json",
      real_path: "/work/builder/.claude/settings.json",
      link: false,
      exists: true,
      git_tracked: false,
      new_file: false,
    },
    effect: {
      set: { from: "sonnet", to: "opus" },
      runs: {
        now: { value: "sonnet", status: "in_effect" },
        after: { value: "opus", status: "in_effect" },
      },
      applies: "new_session",
    },
    options: [],
    scopes: [],
    reaches: [],
    warnings: [],
    diff: { lines: [], new_file: false },
    summary: { verb: "changes", lines_changed: 1, display_path: ".claude/settings.json" },
    read_at: SERVER_TIME,
    version: `v-${String(seq)}`,
    refusal: null,
    ...over,
  };
}

const saved = (rowId = "row-1") => ({
  server_time: SERVER_TIME,
  row_id: rowId,
  saved_at: SERVER_TIME,
  recheck_after_ms: 2000,
});

const recheck = (state: RecheckAnswer["state"]): RecheckAnswer => ({
  server_time: SERVER_TIME,
  state,
  changed_keys: [],
  ours_survived: state === "checking" ? null : state === "confirmed",
  checked_at: state === "checking" ? null : SERVER_TIME,
  seen: false,
});

/** Answers every preview with its own seq, so the latest one always matches. */
function echoPreview(call: Call, over: Partial<EditPreview> = {}): Response {
  return json(preview(Number(call.body?.seq), over));
}

class FakeChannel extends EventTarget {
  postMessage(): void {
    /* the edit layer only listens */
  }
  close(): void {
    /* nothing to close */
  }
}

// ---------------------------------------------------------------------------------------------
// Harness.
// ---------------------------------------------------------------------------------------------

async function harness(server: Server) {
  sessionStorage.clear();
  sessionStorage.setItem(STORAGE_KEYS.readKey, READ_KEY);
  sessionStorage.setItem(STORAGE_KEYS.instance, INSTANCE);
  sessionStorage.setItem(
    STORAGE_KEYS.editKeys,
    JSON.stringify({ builder: BUILDER_KEY, other: OTHER_KEY }),
  );
  const access: Access = createAccess({
    launch: { nonce: "", instance: INSTANCE, command: "/bartab-preview" },
    makeChannel: () => {
      throw new Error("no access channel in this test");
    },
  });
  await access.start();
  const channel = new FakeChannel();
  let ids = 0;
  const edit: EditClient = createEditClient({
    access,
    connection: createConnection(),
    fetchFn: server.fetchFn,
    instance: INSTANCE,
    makeChannel: () => channel as unknown as BroadcastChannel,
    makeId: () => {
      ids += 1;
      return `req-${String(ids).padStart(6, "0")}`;
    },
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>
      <EditContext value={edit}>{children}</EditContext>
    </QueryClientProvider>
  );
  return { access, edit, client, invalidate, wrapper, channel };
}

async function tick(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

const MODEL = (value: string, scope: EditScope = "project"): SettingsChoice => ({
  op: "set",
  scope,
  field: "model",
  value,
});

function useEditor(choice: SettingsChoice | null, project = "builder") {
  const handle = usePreview(project, choice);
  const save = useSave(project, handle);
  return { handle, save };
}

function render(
  wrapper: Awaited<ReturnType<typeof harness>>["wrapper"],
  choice: SettingsChoice | null,
  project = "builder",
) {
  return renderHook(({ picked }) => useEditor(picked, project), {
    wrapper,
    initialProps: { picked: choice },
  });
}

/** Every key from the invalidateQueries spy, as JSON text. */
function invalidated(spy: { mock: { calls: readonly (readonly unknown[])[] } }): string[] {
  return spy.mock.calls.map((args) =>
    JSON.stringify((args[0] as { queryKey: unknown } | undefined)?.queryKey),
  );
}

// ---------------------------------------------------------------------------------------------
// Tests.
// ---------------------------------------------------------------------------------------------

describe("request ids", () => {
  it("match the server pattern", () => {
    for (let n = 0; n < 50; n += 1) expect(defaultRequestId()).toMatch(REQUEST_ID_PATTERN);
  });

  it("are reused only when the same body is sent again", async () => {
    const server = fakeServer();
    let failSave = true;
    server.on((call) => {
      if (call.path === "/api/edit/preview") return echoPreview(call);
      if (failSave) throw new TypeError("Failed to fetch");
      return json(saved());
    });
    const { wrapper } = await harness(server);
    const { result, rerender } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => result.current.save.save());
    await tick(0);
    expect(result.current.save.state).toEqual({ kind: "failed", reason: "network" });
    act(() => result.current.save.save());
    await tick(0);
    const [first, retry] = server.to("/api/edit/save");
    expect(first?.body?.request_id).toMatch(REQUEST_ID_PATTERN);
    expect(retry?.body?.request_id).toBe(first?.body?.request_id);

    failSave = false;
    rerender({ picked: MODEL("haiku") });
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => result.current.save.save());
    await tick(0);
    const third = server.to("/api/edit/save")[2];
    expect(third?.body?.value).toBe("haiku");
    expect(third?.body?.request_id).not.toBe(first?.body?.request_id);
    expect(result.current.save.state.kind).toBe("saved");
  });
});

describe("edit headers", () => {
  it("sends the read key and the project's edit key on every write, never in the URL", async () => {
    const server = fakeServer();
    server.on((call) => {
      if (call.path === "/api/edit/preview") return echoPreview(call);
      if (call.path === "/api/edit/save") return json(saved());
      return json({ server_time: SERVER_TIME, row_id: "row-1" });
    });
    const { wrapper } = await harness(server);
    const { result } = renderHook(
      () => ({ editor: useEditor(MODEL("opus")), undo: useUndo("builder") }),
      { wrapper },
    );
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => result.current.editor.save.save());
    await tick(0);
    act(() => result.current.undo.undo("row-1", "project"));
    await tick(0);
    const writes = server.calls.filter((call) => call.method === "POST");
    // The second preview is the refresh after the save, for a fresh token.
    expect(writes.map((call) => call.path)).toEqual([
      "/api/edit/preview",
      "/api/edit/save",
      "/api/edit/preview",
      "/api/edit/undo",
    ]);
    for (const call of writes) {
      expect(call.headers["X-Bartab-Key"]).toBe(READ_KEY);
      expect(call.headers["X-Bartab-Edit"]).toBe(BUILDER_KEY);
      expect(call.headers["Content-Type"]).toBe("application/json");
      expect(call.path).not.toContain(BUILDER_KEY);
      expect(call.path).not.toContain(READ_KEY);
      expect(JSON.stringify(call.body)).not.toContain(BUILDER_KEY);
    }
  });

  it("uses the current project's key for a user-scope edit", async () => {
    const server = fakeServer();
    server.on((call) => echoPreview(call));
    const { wrapper } = await harness(server);
    render(wrapper, MODEL("opus", "user"), "other");
    await tick(PREVIEW_DEBOUNCE_MS);
    const [call] = server.to("/api/edit/preview");
    expect(call?.body).toEqual({
      project: "other",
      op: "set",
      scope: "user",
      field: "model",
      value: "opus",
      seq: 1,
    });
    expect(call?.headers["X-Bartab-Edit"]).toBe(OTHER_KEY);
  });

  it("sends nothing for a project with no edit key and goes to the restart state", async () => {
    const server = fakeServer();
    server.on((call) => echoPreview(call));
    const { wrapper, edit } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"), "nokey");
    await tick(PREVIEW_DEBOUNCE_MS);
    expect(server.calls).toHaveLength(0);
    expect(edit.getRestart()).toEqual({ reason: "edit_key_unknown", mode: null });
    expect(result.current.handle.restart?.reason).toBe("edit_key_unknown");
    expect(result.current.save.canSave).toBe(false);
  });

  it("keeps every key out of hook states and thrown errors", async () => {
    const server = fakeServer();
    server.on((call) => {
      if (call.path === "/api/edit/preview") return echoPreview(call);
      if (call.path === "/api/edit/save") {
        return json({ server_time: SERVER_TIME, code: "link_outside", params: {} }, 422);
      }
      return json({ code: "unknown_project" }, 404);
    });
    const { wrapper } = await harness(server);
    const { result } = renderHook(
      () => ({ editor: useEditor(MODEL("opus")), history: useHistory("builder") }),
      { wrapper },
    );
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => result.current.editor.save.save());
    await tick(0);
    expect(result.current.editor.save.state).toEqual({
      kind: "refused",
      code: "link_outside",
      params: {},
    });
    const error = result.current.history.error;
    expect(error?.message).toBe("unknown_project");
    const seen = JSON.stringify([result.current.editor.save.state, error?.message, error?.stack]);
    for (const key of [READ_KEY, BUILDER_KEY, OTHER_KEY]) expect(seen).not.toContain(key);
  });
});

describe("preview", () => {
  it("waits 250 ms after the last change, then asks once with an increasing seq", async () => {
    const server = fakeServer();
    server.on((call) => echoPreview(call));
    const { wrapper } = await harness(server);
    const { result, rerender } = render(wrapper, MODEL("opus"));
    expect(result.current.handle.pending).toBe(true);
    await tick(PREVIEW_DEBOUNCE_MS - 1);
    expect(server.calls).toHaveLength(0);
    rerender({ picked: MODEL("haiku") });
    await tick(PREVIEW_DEBOUNCE_MS - 1);
    expect(server.calls).toHaveLength(0);
    await tick(1);
    expect(server.calls).toHaveLength(1);
    expect(server.calls[0]?.body?.value).toBe("haiku");
    const firstSeq = Number(server.calls[0]?.body?.seq);
    expect(result.current.handle.pending).toBe(false);
    expect(result.current.handle.preview?.seq).toBe(firstSeq);

    rerender({ picked: MODEL("sonnet") });
    await tick(PREVIEW_DEBOUNCE_MS);
    expect(Number(server.calls[1]?.body?.seq)).toBeGreaterThan(firstSeq);
  });

  it("keeps a new object with the same values as the same choice", async () => {
    const server = fakeServer();
    server.on((call) => echoPreview(call));
    const { wrapper } = await harness(server);
    const { result, rerender } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    rerender({ picked: MODEL("opus") });
    await tick(PREVIEW_DEBOUNCE_MS);
    expect(server.calls).toHaveLength(1);
    expect(result.current.handle.pending).toBe(false);
  });

  it("aborts the request before and drops an older answer that still arrives", async () => {
    const server = fakeServer();
    server.ignoreAbort();
    const waits = new Map<number, ReturnType<typeof deferred>>();
    server.on((call) => {
      const wait = deferred();
      waits.set(Number(call.body?.seq), wait);
      return wait.promise;
    });
    const { wrapper } = await harness(server);
    const { result, rerender } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    rerender({ picked: MODEL("haiku") });
    await tick(PREVIEW_DEBOUNCE_MS);
    const [older, newer] = [...waits.keys()];
    expect(older).toBeDefined();
    expect(newer).toBeGreaterThan(older ?? 0);

    // The newer answer first, then the older one: the older one is dropped.
    await act(async () => {
      waits.get(newer ?? 0)?.resolve(json(preview(newer ?? 0, { version: "v-newer" })));
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      waits.get(older ?? 0)?.resolve(json(preview(older ?? 0, { version: "v-older" })));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.handle.preview?.version).toBe("v-newer");
    expect(result.current.handle.pending).toBe(false);
  });

  it("drops an answer whose echoed seq is not the latest", async () => {
    const server = fakeServer();
    server.on(() => json(preview(99)));
    const { wrapper } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    expect(result.current.handle.preview).toBeNull();
    expect(result.current.handle.pending).toBe(true);
    expect(result.current.save.canSave).toBe(false);
  });

  it("aborts the in-flight request when the choice changes", async () => {
    const server = fakeServer();
    const signals: (AbortSignal | undefined)[] = [];
    const fetchFn = server.fetchFn;
    const spyFetch: typeof fetch = (input, init) => {
      signals.push(init?.signal ?? undefined);
      return fetchFn(input, init);
    };
    server.on(() => deferred().promise);
    const { wrapper } = await harness({ ...server, fetchFn: spyFetch });
    const { rerender } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    rerender({ picked: MODEL("haiku") });
    expect(signals[0]?.aborted).toBe(true);
  });
});

describe("save while pending", () => {
  it("holds a press while the preview is pending and sends it once the matching one is in", async () => {
    const server = fakeServer();
    const wait = deferred();
    server.on((call) => {
      // The first preview waits. The refresh after the save answers at once.
      if (call.path === "/api/edit/preview") {
        return Number(call.body?.seq) === 1 ? wait.promise : echoPreview(call);
      }
      return json(saved());
    });
    const { wrapper } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    act(() => result.current.save.save());
    expect(result.current.save.state).toEqual({ kind: "held" });
    expect(result.current.save.canSave).toBe(false);
    await tick(PREVIEW_DEBOUNCE_MS);
    expect(server.to("/api/edit/save")).toHaveLength(0);
    const seq = Number(server.to("/api/edit/preview")[0]?.body?.seq);
    await act(async () => {
      wait.resolve(json(preview(seq, { version: "v-match" })));
      await vi.advanceTimersByTimeAsync(0);
    });
    await tick(0);
    const [save] = server.to("/api/edit/save");
    expect(save?.body).toMatchObject({
      project: "builder",
      op: "set",
      scope: "project",
      field: "model",
      value: "opus",
      seq,
      version: "v-match",
    });
    expect(result.current.save.state.kind).toBe("saved");
  });

  it("never sends a held press against the stale preview of an older choice", async () => {
    const server = fakeServer();
    server.on((call) => {
      if (call.path === "/api/edit/preview") {
        const seq = Number(call.body?.seq);
        return json(preview(seq, { version: `v-${String(call.body?.value)}` }));
      }
      return json(saved());
    });
    const { wrapper } = await harness(server);
    const { result, rerender } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    expect(result.current.save.canSave).toBe(true);
    rerender({ picked: MODEL("haiku") });
    expect(result.current.handle.pending).toBe(true);
    act(() => result.current.save.save());
    expect(result.current.save.state.kind).toBe("held");
    expect(server.to("/api/edit/save")).toHaveLength(0);
    await tick(PREVIEW_DEBOUNCE_MS);
    await tick(0);
    const saves = server.to("/api/edit/save");
    expect(saves).toHaveLength(1);
    expect(saves[0]?.body).toMatchObject({ value: "haiku", version: "v-haiku" });
  });

  it("drops a held press when the choice changes again", async () => {
    const server = fakeServer();
    server.on((call) => {
      if (call.path === "/api/edit/preview") return echoPreview(call);
      return json(saved());
    });
    const { wrapper } = await harness(server);
    const { result, rerender } = render(wrapper, MODEL("opus"));
    act(() => result.current.save.save());
    expect(result.current.save.state.kind).toBe("held");
    rerender({ picked: MODEL("haiku") });
    await tick(0);
    expect(result.current.save.state.kind).toBe("idle");
    await tick(PREVIEW_DEBOUNCE_MS);
    await tick(0);
    expect(result.current.handle.pending).toBe(false);
    expect(server.to("/api/edit/save")).toHaveLength(0);
  });

  it("ignores a second press while saving", async () => {
    const server = fakeServer();
    const wait = deferred();
    server.on((call) => (call.path === "/api/edit/preview" ? echoPreview(call) : wait.promise));
    const { wrapper } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => result.current.save.save());
    act(() => result.current.save.save());
    expect(result.current.save.state.kind).toBe("saving");
    expect(server.to("/api/edit/save")).toHaveLength(1);
  });

  it("does not send a save the preview already refuses", async () => {
    const server = fakeServer();
    server.on((call) =>
      echoPreview(call, { refusal: { code: "link_outside", params: { path: "x" } } }),
    );
    const { wrapper } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    expect(result.current.save.canSave).toBe(false);
    act(() => result.current.save.save());
    expect(result.current.save.state).toEqual({
      kind: "refused",
      code: "link_outside",
      params: { path: "x" },
    });
    expect(server.to("/api/edit/save")).toHaveLength(0);
  });
});

describe("409 and refusals", () => {
  async function conflictRun(code: "changed" | "preview_mismatch") {
    const server = fakeServer();
    server.on((call) => {
      if (call.path === "/api/edit/preview") return echoPreview(call);
      const seq = Number(call.body?.seq);
      if (call.body?.version === "v-fresh") return json(saved());
      return json(
        {
          server_time: SERVER_TIME,
          code,
          preview: preview(seq, { version: "v-fresh" }),
          changed_keys: ["model", "env"],
          edited_key_changed: true,
        },
        409,
      );
    });
    const { wrapper } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => result.current.save.save());
    await tick(0);
    return { server, result };
  }

  it("puts the fresh preview from a changed answer in place and reports the changed keys", async () => {
    const { server, result } = await conflictRun("changed");
    expect(result.current.save.state).toEqual({
      kind: "conflict",
      code: "changed",
      changedKeys: ["model", "env"],
      editedKeyChanged: true,
    });
    expect(result.current.handle.preview?.version).toBe("v-fresh");
    expect(result.current.handle.pending).toBe(false);
    expect(server.to("/api/edit/preview")).toHaveLength(1);

    // Nothing was written, so the person presses Save again, now on the fresh token.
    const firstId = server.to("/api/edit/save")[0]?.body?.request_id;
    act(() => result.current.save.save());
    await tick(0);
    const retry = server.to("/api/edit/save")[1];
    expect(retry?.body?.version).toBe("v-fresh");
    expect(retry?.body?.request_id).not.toBe(firstId);
    expect(result.current.save.state.kind).toBe("saved");
  });

  it("does the same for preview_mismatch", async () => {
    const { result } = await conflictRun("preview_mismatch");
    expect(result.current.save.state).toMatchObject({ kind: "conflict", code: "preview_mismatch" });
    expect(result.current.handle.preview?.version).toBe("v-fresh");
  });

  it("asks for a fresh preview when a 409 carries none", async () => {
    const server = fakeServer();
    server.on((call) => {
      if (call.path === "/api/edit/preview") return echoPreview(call);
      return json(
        {
          server_time: SERVER_TIME,
          code: "changed",
          preview: null,
          changed_keys: [],
          edited_key_changed: false,
        },
        409,
      );
    });
    const { wrapper } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => result.current.save.save());
    await tick(0);
    expect(result.current.save.state).toMatchObject({ kind: "conflict", changedKeys: [] });
    await tick(0);
    const previews = server.to("/api/edit/preview");
    expect(previews).toHaveLength(2);
    expect(Number(previews[1]?.body?.seq)).toBe(2);
    expect(result.current.handle.preview?.seq).toBe(2);
    expect(result.current.handle.pending).toBe(false);
  });

  it("asks for a fresh token after bad_version and holds Save until it is in", async () => {
    const server = fakeServer();
    server.on((call) => {
      if (call.path === "/api/edit/preview") return echoPreview(call);
      if (call.body?.version === "v-1") {
        return json({ server_time: SERVER_TIME, code: "bad_version", params: {} }, 422);
      }
      return json(saved());
    });
    const { wrapper } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => result.current.save.save());
    await tick(0);
    expect(result.current.save.state).toEqual({ kind: "refused", code: "bad_version", params: {} });
    await tick(0);
    const previews = server.to("/api/edit/preview");
    expect(previews).toHaveLength(2);
    expect(Number(previews[1]?.body?.seq)).toBe(2);
    expect(result.current.handle.preview?.version).toBe("v-2");
    act(() => result.current.save.save());
    await tick(0);
    expect(server.to("/api/edit/save")[1]?.body?.version).toBe("v-2");
    expect(result.current.save.state.kind).toBe("saved");
  });

  it("locks the tab on a 401", async () => {
    const server = fakeServer();
    server.on((call) =>
      call.path === "/api/edit/preview" ? echoPreview(call) : json({ code: "bad_key" }, 401),
    );
    const { wrapper, access } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => result.current.save.save());
    await tick(0);
    expect(result.current.save.state).toEqual({ kind: "failed", reason: "locked" });
    expect(access.getState()).toMatchObject({ kind: "locked", reason: "server_restarted" });
  });

  it("maps an unknown refusal code to refused, never to server text", async () => {
    const server = fakeServer();
    server.on((call) =>
      call.path === "/api/edit/preview"
        ? echoPreview(call)
        : json({ code: "Something odd at /work/x", params: {} }, 403),
    );
    const { wrapper } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => result.current.save.save());
    await tick(0);
    expect(result.current.save.state).toEqual({ kind: "refused", code: "refused", params: {} });
  });
});

describe("invalidation", () => {
  it("lists the Setup, Agents, app and edit queries for one project", () => {
    expect(editInvalidationKeys("builder", "local")).toEqual([
      ["setup", "map", "builder"],
      ["setup", "part", "builder"],
      ["setup", "problems", "builder"],
      ["review", "agents", "builder"],
      ["app", "builder"],
      ["edit", "history", "builder"],
      ["edit", "open", "builder"],
    ]);
  });

  it("reaches every project for a user-scope edit or an undo of unknown scope", () => {
    const all = [
      ["setup", "map"],
      ["setup", "part"],
      ["setup", "problems"],
      ["review", "agents"],
      ["app"],
      ["edit", "history"],
      ["edit", "open"],
    ];
    expect(editInvalidationKeys("builder", "user")).toEqual(all);
    expect(editInvalidationKeys("builder", null)).toEqual(all);
  });

  it("invalidates the list after a save and after an undo", async () => {
    const server = fakeServer();
    server.on((call) => {
      if (call.path === "/api/edit/preview") return echoPreview(call);
      if (call.path === "/api/edit/save") return json(saved());
      return json({ server_time: SERVER_TIME, row_id: "row-1" });
    });
    const { wrapper, invalidate } = await harness(server);
    const { result } = renderHook(
      () => ({ editor: useEditor(MODEL("opus")), undo: useUndo("builder") }),
      { wrapper },
    );
    await tick(PREVIEW_DEBOUNCE_MS);
    invalidate.mockClear();
    act(() => result.current.editor.save.save());
    await tick(0);
    const expected = editInvalidationKeys("builder", "project").map((key) => JSON.stringify(key));
    expect(invalidated(invalidate)).toEqual(expected);

    invalidate.mockClear();
    act(() => result.current.undo.undo("row-1", "project"));
    await tick(0);
    expect(result.current.undo.state).toEqual({ kind: "done", rowId: "row-1" });
    expect(invalidated(invalidate)).toEqual(expected);
  });

  it("refetches the preview after a save, so the next save has a fresh token", async () => {
    const server = fakeServer();
    server.on((call) => (call.path === "/api/edit/preview" ? echoPreview(call) : json(saved())));
    const { wrapper } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => result.current.save.save());
    await tick(0);
    await tick(0);
    expect(server.to("/api/edit/preview")).toHaveLength(2);
    expect(result.current.handle.preview?.version).toBe("v-2");
  });
});

describe("restart state", () => {
  it("holds Save when an /api/app answer names another edits instance", async () => {
    const server = fakeServer();
    server.on((call) => (call.path === "/api/edit/preview" ? echoPreview(call) : json(saved())));
    const { wrapper, client, invalidate } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    expect(result.current.save.canSave).toBe(true);
    act(() => {
      client.setQueryData(
        ["app", "builder"],
        appInfo({ edits: { state: "on", instance: "inst-2" } }),
      );
    });
    expect(result.current.handle.restart).toEqual({ reason: "instance_changed", mode: "on" });
    expect(result.current.save.canSave).toBe(false);
    act(() => result.current.save.save());
    await tick(0);
    expect(result.current.save.state).toEqual({ kind: "restart" });
    expect(server.to("/api/edit/save")).toHaveLength(0);
    expect(invalidated(invalidate)).toContain(JSON.stringify(["app"]));
  });

  it("leaves Save alone for an /api/app answer from the same instance", async () => {
    const server = fakeServer();
    server.on((call) => echoPreview(call));
    const { wrapper, client } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => {
      client.setQueryData(
        ["app", "builder"],
        appInfo({ edits: { state: "on", instance: INSTANCE } }),
      );
    });
    expect(result.current.handle.restart).toBeNull();
    expect(result.current.save.canSave).toBe(true);
  });

  it("goes to the restart state on a key handoff for another instance", async () => {
    const server = fakeServer();
    server.on((call) => echoPreview(call));
    const { wrapper, channel } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => {
      channel.dispatchEvent(
        new MessageEvent("message", {
          data: { type: "offer", readKey: "fake-other", editKeys: {}, instance: INSTANCE },
        }),
      );
    });
    expect(result.current.handle.restart).toBeNull();
    act(() => {
      channel.dispatchEvent(
        new MessageEvent("message", {
          data: { type: "offer", readKey: "fake-other", editKeys: {}, instance: "inst-2" },
        }),
      );
    });
    expect(result.current.handle.restart).toEqual({ reason: "key_handoff", mode: null });
    expect(result.current.save.canSave).toBe(false);
  });

  it("goes to the restart state on edits_off, then takes the mode from /api/app", async () => {
    const server = fakeServer();
    server.on(() => json({ server_time: SERVER_TIME, code: "edits_off" }, 403));
    const { wrapper, client, invalidate } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    expect(result.current.handle.restart).toEqual({ reason: "edits_off", mode: "off" });
    expect(result.current.handle.reason).toBe("edits_off");
    expect(invalidated(invalidate)).toContain(JSON.stringify(["app"]));
    act(() => {
      client.setQueryData(
        ["app", "builder"],
        appInfo({ edits: { state: "on", instance: "inst-2" } }),
      );
    });
    expect(result.current.handle.restart).toEqual({ reason: "edits_off", mode: "on" });
  });

  it("goes to the restart state on edit_key_unknown from a save", async () => {
    const server = fakeServer();
    server.on((call) =>
      call.path === "/api/edit/preview"
        ? echoPreview(call)
        : json({ server_time: SERVER_TIME, code: "edit_key_unknown", params: {} }, 403),
    );
    const { wrapper } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => result.current.save.save());
    await tick(0);
    expect(result.current.save.state).toEqual({ kind: "restart" });
    expect(result.current.handle.restart).toEqual({ reason: "edit_key_unknown", mode: null });
    act(() => result.current.save.save());
    await tick(0);
    expect(server.to("/api/edit/save")).toHaveLength(1);
  });

  it("drops a held press when a restart begins", async () => {
    const server = fakeServer();
    const wait = deferred();
    server.on((call) => (call.path === "/api/edit/preview" ? wait.promise : json(saved())));
    const { wrapper, client } = await harness(server);
    const { result } = render(wrapper, MODEL("opus"));
    act(() => result.current.save.save());
    expect(result.current.save.state.kind).toBe("held");
    act(() => {
      client.setQueryData(
        ["app", "builder"],
        appInfo({ edits: { state: "off", instance: "inst-2" } }),
      );
    });
    await tick(0);
    expect(result.current.save.state).toEqual({ kind: "restart" });
    await tick(PREVIEW_DEBOUNCE_MS);
    await act(async () => {
      wait.resolve(json(preview(1)));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(server.to("/api/edit/save")).toHaveLength(0);
  });

  it("feeds the history answer's edits instance into the same check", async () => {
    const server = fakeServer();
    const history: EditHistory = {
      server_time: SERVER_TIME,
      rows: [],
      older: { count: 0, rows: [] },
      backup_folder: { display: "~/x", real: "/work/x" },
      edits: { state: "off", instance: "inst-2" },
    };
    server.on(() => json(history));
    const { wrapper, edit } = await harness(server);
    renderHook(() => useHistory("builder"), { wrapper });
    await tick(0);
    expect(edit.getRestart()).toEqual({ reason: "instance_changed", mode: "off" });
  });
});

describe("recheck", () => {
  it("reads the saved row at 2 s and 10 s after the save, then stops", async () => {
    expect(RECHECK_AT_MS).toEqual([2000, 10000]);
    const server = fakeServer();
    const states: RecheckAnswer["state"][] = ["checking", "confirmed"];
    server.on((call) => {
      if (call.path === "/api/edit/preview") return echoPreview(call);
      if (call.path === "/api/edit/save") return json(saved("row-7"));
      return json(recheck(states.shift() ?? "confirmed"));
    });
    const { wrapper, invalidate } = await harness(server);
    const { result } = renderHook(
      () => {
        const editor = useEditor(MODEL("opus"));
        const state = editor.save.state;
        const row =
          state.kind === "saved" ? { rowId: state.saved.row_id, scope: state.scope } : null;
        return { editor, recheck: useRecheck("builder", row) };
      },
      { wrapper },
    );
    await tick(PREVIEW_DEBOUNCE_MS);
    act(() => result.current.editor.save.save());
    await tick(0);
    invalidate.mockClear();
    const reads = () => server.to("/api/edit/rows/");
    await tick(1999 - 1);
    expect(reads()).toHaveLength(0);
    await tick(2);
    expect(reads()).toHaveLength(1);
    expect(reads()[0]?.path).toBe("/api/edit/rows/row-7?project=builder");
    expect(reads()[0]?.method).toBe("GET");
    expect(reads()[0]?.headers["X-Bartab-Edit"]).toBeUndefined();
    expect(result.current.recheck.answer?.state).toBe("checking");
    expect(invalidate).not.toHaveBeenCalled();

    await tick(8000);
    expect(reads()).toHaveLength(2);
    expect(result.current.recheck).toMatchObject({ reads: 2, done: true });
    expect(result.current.recheck.answer?.state).toBe("confirmed");
    expect(invalidated(invalidate)).toEqual(
      editInvalidationKeys("builder", "project").map((key) => JSON.stringify(key)),
    );

    await tick(60_000);
    expect(reads()).toHaveLength(2);
  });
});

describe("undo", () => {
  it("shows the undo preview on changed_since_save and confirms with its token", async () => {
    const server = fakeServer();
    server.on((call) => {
      if (call.body?.anyway === true) return json({ server_time: SERVER_TIME, row_id: "row-1" });
      return json(
        {
          server_time: SERVER_TIME,
          code: "changed_since_save",
          undo_preview: { diff: { lines: [], new_file: false }, version: "undo-v" },
        },
        409,
      );
    });
    const { wrapper, invalidate } = await harness(server);
    const { result } = renderHook(() => useUndo("builder"), { wrapper });
    act(() => result.current.undo("row-1"));
    await tick(0);
    expect(result.current.state).toMatchObject({
      kind: "conflict",
      rowId: "row-1",
      undoPreview: { version: "undo-v" },
    });
    expect(invalidate).not.toHaveBeenCalled();
    act(() => result.current.undoAnyway());
    await tick(0);
    const [first, confirm] = server.to("/api/edit/undo");
    expect(first?.body).toEqual({
      project: "builder",
      row_id: "row-1",
      request_id: first?.body?.request_id,
    });
    expect(confirm?.body).toMatchObject({
      project: "builder",
      row_id: "row-1",
      version: "undo-v",
      anyway: true,
    });
    expect(confirm?.body?.request_id).not.toBe(first?.body?.request_id);
    expect(confirm?.headers["X-Bartab-Edit"]).toBe(BUILDER_KEY);
    expect(result.current.state).toEqual({ kind: "done", rowId: "row-1" });
    // The scope was not given, so the undo reaches every project.
    expect(invalidated(invalidate)).toEqual(
      editInvalidationKeys("builder", null).map((key) => JSON.stringify(key)),
    );
  });
});

describe("always-mounted reads", () => {
  it("send the read key only, to the plan's paths", async () => {
    const server = fakeServer();
    server.on((call) => {
      if (call.path.startsWith("/api/edit/history")) {
        return json({
          server_time: SERVER_TIME,
          rows: [],
          older: { count: 0, rows: [] },
          backup_folder: { display: "~/x", real: "/work/x" },
          edits: { state: "on", instance: INSTANCE },
        });
      }
      if (call.path.includes("/drift")) {
        return json({ server_time: SERVER_TIME, lines: null, code: "cant_rebuild" });
      }
      if (call.path.startsWith("/api/edit/open")) {
        return json({ server_time: SERVER_TIME, row: null });
      }
      return json({ server_time: SERVER_TIME });
    });
    const { wrapper, invalidate, edit } = await harness(server);
    const { result } = renderHook(
      () => ({
        history: useHistory("builder"),
        drift: useDrift("builder", "row 1"),
        open: useOpenWarning("builder", "agent:a/b"),
        seen: useMarkSeen("builder"),
      }),
      { wrapper },
    );
    await tick(0);
    expect(result.current.drift.data?.code).toBe("cant_rebuild");
    expect(result.current.open.data?.row).toBeNull();
    await act(async () => {
      await result.current.seen.mutateAsync("row-1");
    });
    // The seen mark refetches the history and the open warning, so those two are asked twice.
    expect([...new Set(server.calls.map((call) => `${call.method} ${call.path}`))].sort()).toEqual([
      "GET /api/edit/history?project=builder",
      "GET /api/edit/open?project=builder&item=agent%3Aa%2Fb",
      "GET /api/edit/rows/row%201/drift?project=builder",
      "POST /api/edit/rows/row-1/seen",
    ]);
    for (const call of server.calls) {
      expect(call.headers["X-Bartab-Key"]).toBe(READ_KEY);
      expect(call.headers["X-Bartab-Edit"]).toBeUndefined();
    }
    expect(server.calls.find((call) => call.method === "POST")?.body).toEqual({
      project: "builder",
    });
    expect(invalidated(invalidate)).toEqual([
      JSON.stringify(["edit", "history", "builder"]),
      JSON.stringify(["edit", "open", "builder"]),
    ]);
    expect(edit.getRestart()).toBeNull();
  });

  it("read nothing for a null row or item", async () => {
    const server = fakeServer();
    const { wrapper } = await harness(server);
    renderHook(
      () => ({ drift: useDrift("builder", null), open: useOpenWarning("builder", null) }),
      { wrapper },
    );
    await tick(0);
    expect(server.calls).toHaveLength(0);
  });
});
