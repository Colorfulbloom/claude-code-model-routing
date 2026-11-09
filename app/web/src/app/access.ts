/*
 * The access client. It swaps the one-time code from the hash for a read key, keeps the keys in
 * sessionStorage, and shares them between tabs of the same server over a BroadcastChannel. The
 * gate state it exposes decides what App renders. Contract: docs/rebuild/planning/m0-build.md,
 * sections 4 and 10.
 *
 * States
 *   hold      no key yet, waiting up to 400 ms for another tab to offer one
 *   unlocked  a key for this server's instance is in hand
 *   locked    a reason code says why, the requested route is kept in bartab.route
 *   stopped   three calls in a row got no answer
 */
import type { SwapAnswer } from "@/api/types";
import { readLaunch } from "@/lib/launch";
import type { Launch } from "@/lib/launch";

export const LOCK_REASONS = [
  "no_key",
  "code_used",
  "code_expired",
  "code_unknown",
  "server_restarted",
  "wrong_project_key",
] as const;
export type LockReason = (typeof LOCK_REASONS)[number];

export const SWAP_REFUSALS = [
  "code_used",
  "code_expired",
  "code_unknown",
  "server_restarted",
] as const;
export type SwapRefusalCode = (typeof SWAP_REFUSALS)[number];

export type GateState =
  | { kind: "hold" }
  | { kind: "unlocked" }
  | { kind: "locked"; reason: LockReason; otherTabBack: boolean }
  | { kind: "stopped" };

export const HOLD_MS = 400;
export const CHANNEL_NAME = "bartab-access";
export const STORAGE_KEYS = {
  readKey: "bartab.readKey",
  editKeys: "bartab.editKeys",
  instance: "bartab.instance",
  route: "bartab.route",
  project: "bartab.project",
} as const;

export function isLockReason(value: unknown): value is LockReason {
  return typeof value === "string" && (LOCK_REASONS as readonly string[]).includes(value);
}

export function isSwapRefusal(value: unknown): value is SwapRefusalCode {
  return typeof value === "string" && (SWAP_REFUSALS as readonly string[]).includes(value);
}

export interface OtherTabBack {
  /** The route the other tab kept, such as /p/builder/review/agents. Null when it sent none. */
  route: string | null;
}

export interface AccessOptions {
  storage?: Storage;
  launch?: Launch;
  fetchFn?: typeof fetch;
  makeChannel?: () => BroadcastChannel;
  holdMs?: number;
}

export interface Access {
  getState: () => GateState;
  subscribe: (listener: () => void) => () => void;
  /** Reads the hash, swaps a code or restores the keys, and opens the channel. */
  start: () => Promise<void>;
  dispose: () => void;
  getReadKey: () => string | null;
  getEditKeys: () => Record<string, string>;
  /** The project the launcher passed with the code, or the last one this tab used. */
  getProject: () => string | null;
  /** Remembers the project the person picked, so a route with no project still has one. */
  setProject: (key: string) => void;
  getRoute: () => string | null;
  /**
   * Set on an unlocked tab when another tab unlocked in place and said so over the channel. The
   * route is the one that tab kept. The shell shows the new-tab line until the person moves on.
   */
  getOtherTabBack: () => OtherTabBack | null;
  acknowledgeOtherTabBack: () => void;
  saveRoute: (route: string) => void;
  /** Moves a tab to the locked page. Ignored when already locked. */
  lock: (reason: LockReason) => void;
  setStopped: () => void;
  /** Called with the instance of every /api/app answer. Resumes a stopped tab. */
  serverAnswered: (instance: string) => void;
}

interface Offer {
  readKey: string;
  editKeys: Record<string, string>;
  instance: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseOffer(data: unknown): Offer | null {
  if (!isRecord(data) || data.type !== "offer") return null;
  const { readKey, editKeys, instance } = data;
  if (typeof readKey !== "string" || typeof instance !== "string") return null;
  const keys: Record<string, string> = {};
  if (isRecord(editKeys)) {
    for (const [project, key] of Object.entries(editKeys)) {
      if (typeof key === "string") keys[project] = key;
    }
  }
  return { readKey, editKeys: keys, instance };
}

/** Splits "#/path?a=b" into the path and its query. */
function splitHash(hash: string): { path: string; params: URLSearchParams } {
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  const at = raw.indexOf("?");
  return {
    path: at < 0 ? raw : raw.slice(0, at),
    params: new URLSearchParams(at < 0 ? "" : raw.slice(at + 1)),
  };
}

export function createAccess(options: AccessOptions = {}): Access {
  const launch = options.launch ?? readLaunch();
  const holdMs = options.holdMs ?? HOLD_MS;
  const fetchFn = options.fetchFn ?? ((...args: Parameters<typeof fetch>) => fetch(...args));

  function storage(): Storage | null {
    try {
      return options.storage ?? window.sessionStorage;
    } catch {
      return null;
    }
  }
  function read(key: string): string | null {
    try {
      return storage()?.getItem(key) ?? null;
    } catch {
      return null;
    }
  }
  function write(key: string, value: string): void {
    try {
      storage()?.setItem(key, value);
    } catch {
      /* storage can be blocked, the tab still works until it reloads */
    }
  }

  // Keys kept in memory too, so a blocked storage still unlocks this tab.
  let readKey = read(STORAGE_KEYS.readKey);
  let editKeys = parseEditKeys(read(STORAGE_KEYS.editKeys));
  let instance = read(STORAGE_KEYS.instance);
  let project = read(STORAGE_KEYS.project);
  let route = read(STORAGE_KEYS.route);

  let state: GateState = { kind: "hold" };
  let otherTabBack: OtherTabBack | null = null;
  const listeners = new Set<() => void>();
  let channel: BroadcastChannel | null = null;
  let holdTimer: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;

  function parseEditKeys(raw: string | null): Record<string, string> {
    if (raw === null) return {};
    try {
      const parsed: unknown = JSON.parse(raw);
      const keys: Record<string, string> = {};
      if (isRecord(parsed)) {
        for (const [name, key] of Object.entries(parsed)) {
          if (typeof key === "string") keys[name] = key;
        }
      }
      return keys;
    } catch {
      return {};
    }
  }

  function setState(next: GateState): void {
    state = next;
    for (const listener of listeners) listener();
  }

  function clearHold(): void {
    if (holdTimer !== null) {
      clearTimeout(holdTimer);
      holdTimer = null;
    }
  }

  function lock(reason: LockReason): void {
    clearHold();
    if (state.kind === "locked" && state.reason === reason) return;
    setState({ kind: "locked", reason, otherTabBack: false });
  }

  function storeKeys(next: Offer): void {
    readKey = next.readKey;
    editKeys = next.editKeys;
    instance = next.instance;
    write(STORAGE_KEYS.readKey, next.readKey);
    write(STORAGE_KEYS.editKeys, JSON.stringify(next.editKeys));
    write(STORAGE_KEYS.instance, next.instance);
  }

  function post(message: unknown): void {
    try {
      channel?.postMessage(message);
    } catch {
      /* a closed channel only means no other tab hears us */
    }
  }

  function postOffer(): void {
    if (readKey === null || instance === null) return;
    post({ type: "offer", readKey, editKeys, instance });
  }

  function onMessage(event: MessageEvent): void {
    const data: unknown = event.data;
    if (!isRecord(data)) return;
    if (data.type === "ask") {
      if (state.kind === "unlocked") postOffer();
      return;
    }
    if (data.type === "offer") {
      if (state.kind !== "hold" && state.kind !== "locked") return;
      const offer = parseOffer(data);
      if (offer?.instance !== launch.instance) return;
      storeKeys(offer);
      clearHold();
      setState({ kind: "unlocked" });
      post({ type: "back", route });
      return;
    }
    if (data.type === "back") {
      if (state.kind === "locked" && !state.otherTabBack) {
        setState({ ...state, otherTabBack: true });
      } else if (state.kind === "unlocked") {
        otherTabBack = { route: typeof data.route === "string" ? data.route : null };
        for (const listener of listeners) listener();
      }
    }
  }

  function openChannel(): void {
    if (channel !== null) return;
    try {
      channel = options.makeChannel?.() ?? new BroadcastChannel(CHANNEL_NAME);
      channel.addEventListener("message", onMessage);
    } catch {
      channel = null;
    }
  }

  function takeCode(): { code: string | null } {
    const { path, params } = splitHash(window.location.hash);
    const code = params.get("code");
    if (code === null) {
      saveRoute((path === "" ? "/" : path) + queryOf(params));
      return { code: null };
    }
    params.delete("code");
    const rest = queryOf(params);
    const kept = path === "" ? "/" : path;
    saveRoute(kept + rest);
    history.replaceState(
      history.state as unknown,
      "",
      `${window.location.pathname}${window.location.search}#${kept}${rest}`,
    );
    return { code };
  }

  function queryOf(params: URLSearchParams): string {
    const text = params.toString();
    return text === "" ? "" : `?${text}`;
  }

  function saveRoute(next: string): void {
    route = next;
    write(STORAGE_KEYS.route, next);
  }

  async function swap(code: string): Promise<void> {
    const codeInstance = code.split(".")[0] ?? "";
    if (launch.instance !== "" && codeInstance !== launch.instance) {
      lock("server_restarted");
      return;
    }
    let response: Response;
    try {
      response = await fetchFn("/api/access/swap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
    } catch {
      setState({ kind: "stopped" });
      return;
    }
    if (disposed) return;
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    if (response.status === 403) {
      const refusal = isRecord(body) ? body.code : undefined;
      lock(isSwapRefusal(refusal) ? refusal : "code_unknown");
      return;
    }
    if (!response.ok || !isRecord(body) || typeof body.read_key !== "string") {
      setState({ kind: "stopped" });
      return;
    }
    const answer = body as unknown as SwapAnswer;
    if (launch.instance !== "" && answer.instance !== launch.instance) {
      lock("server_restarted");
      return;
    }
    storeKeys({
      readKey: answer.read_key,
      editKeys: answer.edit_keys,
      instance: answer.instance,
    });
    project = answer.project;
    if (answer.project !== null) write(STORAGE_KEYS.project, answer.project);
    setState({ kind: "unlocked" });
    postOffer();
  }

  async function start(): Promise<void> {
    openChannel();
    const { code } = takeCode();
    if (code !== null) {
      await swap(code);
      return;
    }
    if (readKey !== null) {
      if (launch.instance !== "" && instance !== launch.instance) {
        lock("server_restarted");
      } else {
        setState({ kind: "unlocked" });
      }
      return;
    }
    setState({ kind: "hold" });
    post({ type: "ask" });
    holdTimer = setTimeout(() => {
      holdTimer = null;
      if (state.kind === "hold") lock("no_key");
    }, holdMs);
  }

  return {
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    start,
    dispose() {
      disposed = true;
      clearHold();
      channel?.close();
      channel = null;
    },
    getReadKey: () => readKey,
    getEditKeys: () => editKeys,
    getProject: () => project,
    setProject(key) {
      project = key;
      write(STORAGE_KEYS.project, key);
    },
    getRoute: () => route,
    getOtherTabBack: () => otherTabBack,
    acknowledgeOtherTabBack() {
      if (otherTabBack === null) return;
      otherTabBack = null;
      for (const listener of listeners) listener();
    },
    saveRoute,
    lock(reason) {
      if (state.kind === "unlocked" || state.kind === "hold" || state.kind === "stopped") {
        lock(reason);
      }
    },
    setStopped() {
      if (state.kind === "unlocked") setState({ kind: "stopped" });
    },
    serverAnswered(answered) {
      if (state.kind === "locked") return;
      if (launch.instance !== "" && answered !== launch.instance) {
        lock("server_restarted");
        return;
      }
      if (state.kind === "stopped") setState({ kind: "unlocked" });
    },
  };
}
