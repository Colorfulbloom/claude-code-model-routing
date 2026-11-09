import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createAccess, HOLD_MS, STORAGE_KEYS } from "@/app/access";
import type { Access } from "@/app/access";
import { FakeChannel } from "@/app/test-channel";

const INSTANCE = "inst-1";
const launch = { nonce: "", instance: INSTANCE, command: "/bartab-preview" };

const swapOk = {
  read_key: "key-1",
  edit_keys: {},
  instance: INSTANCE,
  project: "builder",
};

function reply(status: number, body: unknown): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

const made: Access[] = [];
function make(fetchFn: typeof fetch = vi.fn(() => reply(200, swapOk))): Access {
  const access = createAccess({
    launch,
    fetchFn,
    makeChannel: () => new FakeChannel("bartab-access").asChannel(),
  });
  made.push(access);
  return access;
}

function setHash(hash: string): void {
  history.replaceState(null, "", hash);
}

beforeEach(() => {
  sessionStorage.clear();
  FakeChannel.reset();
  setHash("#/");
});

afterEach(() => {
  for (const access of made.splice(0)) access.dispose();
  vi.useRealTimers();
});

describe("swap", () => {
  it("swaps the code, stores the keys and unlocks", async () => {
    const fetchFn = vi.fn(() => reply(200, swapOk));
    setHash(`#/p/builder/live?code=${INSTANCE}.abc`);
    const access = make(fetchFn);
    await access.start();

    expect(access.getState()).toEqual({ kind: "unlocked" });
    expect(fetchFn).toHaveBeenCalledWith(
      "/api/access/swap",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ code: `${INSTANCE}.abc` }),
      }),
    );
    expect(sessionStorage.getItem(STORAGE_KEYS.readKey)).toBe("key-1");
    expect(sessionStorage.getItem(STORAGE_KEYS.instance)).toBe(INSTANCE);
    expect(access.getReadKey()).toBe("key-1");
    expect(access.getProject()).toBe("builder");
  });

  it("strips the code with replaceState and keeps the route", async () => {
    const replace = vi.spyOn(history, "replaceState");
    setHash(`#/p/builder/review/agents?range=30d&code=${INSTANCE}.abc`);
    replace.mockClear();
    const access = make();
    await access.start();

    expect(replace).toHaveBeenCalled();
    expect(window.location.hash).toBe("#/p/builder/review/agents?range=30d");
    expect(access.getRoute()).toBe("/p/builder/review/agents?range=30d");
    expect(sessionStorage.getItem(STORAGE_KEYS.route)).toBe("/p/builder/review/agents?range=30d");
    replace.mockRestore();
  });

  it.each(["code_used", "code_expired", "code_unknown", "server_restarted"] as const)(
    "locks with %s when the server refuses the code",
    async (code) => {
      setHash(`#/?code=${INSTANCE}.abc`);
      const access = make(vi.fn(() => reply(403, { code })));
      await access.start();
      expect(access.getState()).toEqual({ kind: "locked", reason: code, otherTabBack: false });
      expect(access.getReadKey()).toBeNull();
    },
  );

  it("locks with code_unknown for an unrecognised refusal", async () => {
    setHash(`#/?code=${INSTANCE}.abc`);
    const access = make(vi.fn(() => reply(403, { code: "odd" })));
    await access.start();
    expect(access.getState()).toMatchObject({ kind: "locked", reason: "code_unknown" });
  });

  it("locks with server_restarted without a call when the code names another instance", async () => {
    const fetchFn = vi.fn(() => reply(200, swapOk));
    setHash("#/?code=other-instance.abc");
    const access = make(fetchFn);
    await access.start();
    expect(fetchFn).not.toHaveBeenCalled();
    expect(access.getState()).toMatchObject({ kind: "locked", reason: "server_restarted" });
  });

  it("stops when the swap call gets no answer", async () => {
    setHash(`#/?code=${INSTANCE}.abc`);
    const access = make(vi.fn(() => Promise.reject(new TypeError("offline"))));
    await access.start();
    expect(access.getState()).toEqual({ kind: "stopped" });
  });

  it("posts one unsolicited offer after a swap", async () => {
    const other = new FakeChannel("bartab-access");
    const heard: unknown[] = [];
    other.addEventListener("message", (event) => heard.push(event.data));
    setHash(`#/?code=${INSTANCE}.abc`);
    await make().start();
    expect(heard).toEqual([{ type: "offer", readKey: "key-1", editKeys: {}, instance: INSTANCE }]);
  });
});

describe("restore and hold", () => {
  it("unlocks from stored keys with the same instance", async () => {
    sessionStorage.setItem(STORAGE_KEYS.readKey, "k");
    sessionStorage.setItem(STORAGE_KEYS.instance, INSTANCE);
    const access = make();
    await access.start();
    expect(access.getState()).toEqual({ kind: "unlocked" });
  });

  it("locks with server_restarted when the stored instance is another one", async () => {
    sessionStorage.setItem(STORAGE_KEYS.readKey, "k");
    sessionStorage.setItem(STORAGE_KEYS.instance, "old");
    const access = make();
    await access.start();
    expect(access.getState()).toMatchObject({ kind: "locked", reason: "server_restarted" });
  });

  it("holds, then resolves to locked(no_key) after 400 ms", async () => {
    vi.useFakeTimers();
    const access = make();
    await access.start();
    expect(access.getState()).toEqual({ kind: "hold" });
    vi.advanceTimersByTime(HOLD_MS - 1);
    expect(access.getState()).toEqual({ kind: "hold" });
    vi.advanceTimersByTime(1);
    expect(access.getState()).toEqual({ kind: "locked", reason: "no_key", otherTabBack: false });
  });

  it("asks other tabs while it holds", async () => {
    const other = new FakeChannel("bartab-access");
    const heard: unknown[] = [];
    other.addEventListener("message", (event) => heard.push(event.data));
    await make().start();
    expect(heard).toEqual([{ type: "ask" }]);
  });

  it("takes an offer with the matching instance and says it is back", async () => {
    const other = new FakeChannel("bartab-access");
    const heard: unknown[] = [];
    other.addEventListener("message", (event) => heard.push(event.data));
    setHash("#/p/builder/live");
    const access = make();
    await access.start();
    other.postMessage({
      type: "offer",
      readKey: "key-2",
      editKeys: { builder: "e1" },
      instance: INSTANCE,
    });
    expect(access.getState()).toEqual({ kind: "unlocked" });
    expect(access.getReadKey()).toBe("key-2");
    expect(access.getEditKeys()).toEqual({ builder: "e1" });
    expect(heard).toContainEqual({ type: "back", route: "/p/builder/live" });
  });

  it("ignores an offer with another instance", async () => {
    vi.useFakeTimers();
    const other = new FakeChannel("bartab-access");
    const access = make();
    await access.start();
    other.postMessage({ type: "offer", readKey: "stale", editKeys: {}, instance: "old" });
    expect(access.getState()).toEqual({ kind: "hold" });
    vi.advanceTimersByTime(HOLD_MS);
    expect(access.getState()).toMatchObject({ kind: "locked", reason: "no_key" });
    expect(access.getReadKey()).toBeNull();
  });

  it("a locked tab unlocks in place when a matching offer arrives later", async () => {
    vi.useFakeTimers();
    const other = new FakeChannel("bartab-access");
    const access = make();
    await access.start();
    vi.advanceTimersByTime(HOLD_MS);
    other.postMessage({ type: "offer", readKey: "key-3", editKeys: {}, instance: INSTANCE });
    expect(access.getState()).toEqual({ kind: "unlocked" });
  });

  it("a server_restarted tab never unlocks from an old-instance offer", async () => {
    setHash("#/?code=gone.abc");
    const other = new FakeChannel("bartab-access");
    const access = make();
    await access.start();
    other.postMessage({ type: "offer", readKey: "stale", editKeys: {}, instance: "gone" });
    expect(access.getState()).toMatchObject({ kind: "locked", reason: "server_restarted" });
  });

  it("marks a locked tab when another tab says it is back", async () => {
    vi.useFakeTimers();
    const other = new FakeChannel("bartab-access");
    const access = make();
    await access.start();
    vi.advanceTimersByTime(HOLD_MS);
    other.postMessage({ type: "back", route: "/p/builder/live" });
    expect(access.getState()).toMatchObject({ kind: "locked", otherTabBack: true });
  });

  it("tells an unlocked tab the other tab is back, with the route that tab kept", async () => {
    sessionStorage.setItem(STORAGE_KEYS.readKey, "k");
    sessionStorage.setItem(STORAGE_KEYS.instance, INSTANCE);
    const other = new FakeChannel("bartab-access");
    const access = make();
    await access.start();
    let heard = 0;
    access.subscribe(() => {
      heard += 1;
    });
    expect(access.getOtherTabBack()).toBeNull();
    other.postMessage({ type: "back", route: "/p/builder/review/agents" });
    expect(access.getOtherTabBack()).toEqual({ route: "/p/builder/review/agents" });
    expect(access.getState()).toEqual({ kind: "unlocked" });
    expect(heard).toBe(1);
    access.acknowledgeOtherTabBack();
    expect(access.getOtherTabBack()).toBeNull();
    expect(heard).toBe(2);
  });

  it("remembers the project the person picked", async () => {
    sessionStorage.setItem(STORAGE_KEYS.readKey, "k");
    sessionStorage.setItem(STORAGE_KEYS.instance, INSTANCE);
    const access = make();
    await access.start();
    access.setProject("driftwood");
    expect(access.getProject()).toBe("driftwood");
    expect(sessionStorage.getItem(STORAGE_KEYS.project)).toBe("driftwood");
  });

  it("answers an ask from another tab when it holds a key", async () => {
    const other = new FakeChannel("bartab-access");
    const heard: unknown[] = [];
    other.addEventListener("message", (event) => heard.push(event.data));
    sessionStorage.setItem(STORAGE_KEYS.readKey, "k");
    sessionStorage.setItem(STORAGE_KEYS.instance, INSTANCE);
    await make().start();
    other.postMessage({ type: "ask" });
    expect(heard).toContainEqual({ type: "offer", readKey: "k", editKeys: {}, instance: INSTANCE });
  });
});

describe("state changes", () => {
  it("locks and stops an unlocked tab, and resumes on the same instance", async () => {
    sessionStorage.setItem(STORAGE_KEYS.readKey, "k");
    sessionStorage.setItem(STORAGE_KEYS.instance, INSTANCE);
    const access = make();
    await access.start();
    access.setStopped();
    expect(access.getState()).toEqual({ kind: "stopped" });
    access.serverAnswered(INSTANCE);
    expect(access.getState()).toEqual({ kind: "unlocked" });
    access.setStopped();
    access.serverAnswered("new-instance");
    expect(access.getState()).toMatchObject({ kind: "locked", reason: "server_restarted" });
  });

  it("tells subscribers about each change", async () => {
    sessionStorage.setItem(STORAGE_KEYS.readKey, "k");
    sessionStorage.setItem(STORAGE_KEYS.instance, INSTANCE);
    const access = make();
    const listener = vi.fn();
    access.subscribe(listener);
    await access.start();
    expect(listener).toHaveBeenCalledTimes(1);
    access.lock("wrong_project_key");
    expect(listener).toHaveBeenCalledTimes(2);
    expect(access.getState()).toMatchObject({ kind: "locked", reason: "wrong_project_key" });
  });
});
