import { beforeEach, describe, expect, it, vi } from "vitest";
import { appPollInterval, createApiClient, FAILURES_TO_STOP } from "@/api/client";
import type { AppInfo } from "@/api/types";
import { createAccess, STORAGE_KEYS } from "@/app/access";
import { createConnection } from "@/lib/connection";

const INSTANCE = "inst-1";

function appInfo(state: AppInfo["ingest"]["state"] = "done"): AppInfo {
  return {
    server_time: "2026-11-08T10:00:00Z",
    instance: INSTANCE,
    claude_version: "2.1.310",
    ingest: {
      state,
      files_done: 0,
      files_total: 0,
      bytes_done: 0,
      bytes_total: 0,
      error: null,
      retrying: false,
    },
    running: [],
    to_fix_count: 2,
    editable_projects: [],
  };
}

function reply(status: number, body: unknown): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

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
  const connection = createConnection();
  const api = createApiClient({ access, connection, fetchFn, now: () => 1_000 });
  return { access, connection, api };
}

const offline = () => Promise.reject(new TypeError("offline"));

beforeEach(() => {
  sessionStorage.clear();
});

describe("api client", () => {
  it("adds the X-Bartab-Key header and the project query", async () => {
    const fetchFn = vi.fn(() => reply(200, appInfo()));
    const { api } = await setup(fetchFn);
    await api.getApp("my proj");
    expect(fetchFn).toHaveBeenCalledWith("/api/app?project=my%20proj", {
      headers: { "X-Bartab-Key": "key-1" },
    });
  });

  it("asks /api/app with no query when there is no project", async () => {
    const fetchFn = vi.fn(() => reply(200, appInfo()));
    const { api } = await setup(fetchFn);
    await api.getApp(null);
    expect(fetchFn).toHaveBeenCalledWith("/api/app", expect.anything());
  });

  it("reads the project list", async () => {
    const fetchFn = vi.fn(() => reply(200, { projects: [] }));
    const { api } = await setup(fetchFn);
    await expect(api.getProjects()).resolves.toEqual({ projects: [] });
    expect(fetchFn).toHaveBeenCalledWith("/api/projects", expect.anything());
  });

  it("maps a 401 no_key to locked(no_key)", async () => {
    const { api, access } = await setup(vi.fn(() => reply(401, { code: "no_key", path: null })));
    await expect(api.getApp("a")).rejects.toMatchObject({ status: 401, code: "no_key" });
    expect(access.getState()).toMatchObject({ kind: "locked", reason: "no_key" });
  });

  it("maps a 401 bad_key to locked(server_restarted)", async () => {
    const { api, access } = await setup(vi.fn(() => reply(401, { code: "bad_key", path: null })));
    await expect(api.getProjects()).rejects.toMatchObject({ status: 401 });
    expect(access.getState()).toMatchObject({ kind: "locked", reason: "server_restarted" });
  });

  it("counts a refusal as an answer", async () => {
    const { api, connection } = await setup(vi.fn(() => reply(401, { code: "bad_key" })));
    await api.getApp("a").catch(() => undefined);
    expect(connection.getState().lastAnswerAt).toBe(1_000);
    expect(connection.getState().failures).toBe(0);
  });

  it("moves to stopped after three network failures in a row", async () => {
    const { api, access, connection } = await setup(offline);
    for (let i = 1; i < FAILURES_TO_STOP; i++) {
      await expect(api.getApp("a")).rejects.toThrow();
      expect(access.getState()).toEqual({ kind: "unlocked" });
    }
    expect(connection.getState()).toMatchObject({ retrying: true, failures: 2 });
    await expect(api.getApp("a")).rejects.toThrow();
    expect(access.getState()).toEqual({ kind: "stopped" });
  });

  it("counts a 5xx as no answer", async () => {
    const { api, connection } = await setup(vi.fn(() => reply(503, { code: "down" })));
    await api.getApp("a").catch(() => undefined);
    expect(connection.getState().failures).toBe(1);
  });

  it("resets the count on a success and sets lastAnswerAt", async () => {
    const fetchFn = vi
      .fn<typeof fetch>()
      .mockImplementationOnce(offline)
      .mockImplementationOnce(offline)
      .mockImplementationOnce(() => reply(200, appInfo()))
      .mockImplementation(offline);
    const { api, access, connection } = await setup(fetchFn);
    await api.getApp("a").catch(() => undefined);
    await api.getApp("a").catch(() => undefined);
    await api.getApp("a");
    expect(connection.getState()).toEqual({ lastAnswerAt: 1_000, retrying: false, failures: 0 });
    await api.getApp("a").catch(() => undefined);
    await api.getApp("a").catch(() => undefined);
    expect(access.getState()).toEqual({ kind: "unlocked" });
  });

  it("resumes a stopped tab when the same instance answers", async () => {
    const fetchFn = vi.fn<typeof fetch>().mockImplementation(offline);
    const { api, access } = await setup(fetchFn);
    for (let i = 0; i < FAILURES_TO_STOP; i++) await api.getApp("a").catch(() => undefined);
    expect(access.getState()).toEqual({ kind: "stopped" });
    fetchFn.mockImplementation(() => reply(200, appInfo()));
    await api.getApp("a");
    expect(access.getState()).toEqual({ kind: "unlocked" });
  });

  it("locks with server_restarted when a new instance answers", async () => {
    const fetchFn = vi.fn<typeof fetch>().mockImplementation(offline);
    const { api, access } = await setup(fetchFn);
    for (let i = 0; i < FAILURES_TO_STOP; i++) await api.getApp("a").catch(() => undefined);
    fetchFn.mockImplementation(() => reply(200, { ...appInfo(), instance: "inst-2" }));
    await api.getApp("a");
    expect(access.getState()).toMatchObject({ kind: "locked", reason: "server_restarted" });
  });
});

describe("appPollInterval", () => {
  it("polls every second until the ingest is done, then every 10 seconds", () => {
    expect(appPollInterval(undefined)).toBe(10_000);
    expect(appPollInterval(appInfo("waiting"))).toBe(1_000);
    expect(appPollInterval(appInfo("running"))).toBe(1_000);
    expect(appPollInterval(appInfo("failed"))).toBe(1_000);
    expect(appPollInterval(appInfo("done"))).toBe(10_000);
  });
});
