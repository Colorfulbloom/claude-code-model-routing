/*
 * The edit data layer (M6a). Contract: docs/rebuild/planning/m6-build.md sections 3.2, 3.7, 4.2
 * and 5.1.
 *
 * Every edit write (preview, save, undo) goes through `postEdit`, which sends X-Bartab-Key and
 * the current project's X-Bartab-Edit. A user-scope edit uses the current project's key too. No
 * key ever goes in a URL, an error message or a hook state: failures come back as reason codes.
 *
 * Preview. `usePreview` waits 250 ms after the last change, aborts the request before it, and
 * keeps only the answer to its latest `seq`. It is `pending` while the latest choice has no
 * matching answer, and Save is held for as long as it is.
 *
 * Save. `useSave` never sends while the preview is pending. A press then is held, sent once the
 * matching preview has rendered, and dropped if the choice changes again. A 409 `changed` or
 * `preview_mismatch` puts the fresh preview in place and reports the changed keys. A
 * `bad_version` asks for a fresh preview. Each body gets one `request_id`, reused only when the
 * same body is sent again, so a retry after a lost answer gets the first result.
 *
 * Restart. `edits_off`, `edit_key_unknown`, an `edits.instance` other than the one the page loaded
 * under, and a key handoff for another instance on the access channel all put the layer in one
 * restart state. It holds Save until the page reloads, and the page then reads /api/app for the
 * new server's mode.
 *
 * After a save, an undo or a settled recheck, the hooks invalidate the Setup queries, the Agents
 * queries, /api/app and the edit reads (`editInvalidationKeys`).
 */
import { createContext, use, useEffect, useMemo, useSyncExternalStore } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  QueryClient,
  QueryKey,
  UseMutationResult,
  UseQueryResult,
} from "@tanstack/react-query";
import { ApiContext, FAILURES_TO_STOP, reasonFor401 } from "@/api/client";
import type { ApiClient } from "@/api/client";
import { CHANNEL_NAME } from "@/app/access";
import type { Access } from "@/app/access";
import type { components } from "@/api/schema";
import type { Connection } from "@/lib/connection";
import { readLaunch } from "@/lib/launch";

// ---------------------------------------------------------------------------------------------
// Contract types. All of them come from the generated schema (schema.d.ts, from openapi.json),
// which comes from the edit models in app/server/models.py. Only the refusal code list is a
// runtime value, so it stays here and a check below keeps it equal to the schema's union.
// ---------------------------------------------------------------------------------------------

type Schemas = components["schemas"];

export const EDIT_REFUSAL_CODES = [
  "changed",
  "preview_mismatch",
  "bad_version",
  "changed_since_save",
  "raced",
  "link_outside",
  "link_dangling",
  "not_regular",
  "hard_link",
  "not_owner",
  "too_large",
  "managed",
  "forbidden_path",
  "folder_not_found",
  "unknown_project",
  "not_editable",
  "bad_value",
  "no_change",
  "unparsed",
  "key_missing",
  "key_present",
  "parent_not_object",
  "repeated_key",
  "oracle_failed",
  "lock_busy",
  "write_failed",
  "ledger_damaged",
  "backup_damaged",
  "not_undoable",
  "unknown_edit",
  "forged_row",
  "request_reused",
  "cant_rebuild",
  "edits_off",
  "edit_key_unknown",
] as const;
export type EditRefusalCode = Schemas["EditError"]["code"];

// Fails to compile when EDIT_REFUSAL_CODES and the schema's union differ in either direction.
type MissingFromList = Exclude<EditRefusalCode, (typeof EDIT_REFUSAL_CODES)[number]>;
type MissingFromSchema = Exclude<(typeof EDIT_REFUSAL_CODES)[number], EditRefusalCode>;
export const CODES_MATCH_SCHEMA: [MissingFromList, MissingFromSchema] extends [never, never]
  ? true
  : never = true;

export type EditsMode = Schemas["EditsState"]["state"];
export type EditWarningCode = Schemas["EditWarning"]["code"];
export type EditReadOnlyCode = NonNullable<Schemas["EditScopeRow"]["read_only_reason"]>;
export type RecheckState = Schemas["RecheckAnswer"]["state"];
export type UndoState = Schemas["HistoryRow"]["undo_state"];
export type NotUndoableReason = NonNullable<Schemas["HistoryRow"]["not_undoable_reason"]>;
export type EditOp = Schemas["EditPreviewRequest"]["op"];
export type EditScope = Schemas["EditPreviewRequest"]["scope"];
export type SettingsEditField = Schemas["EditPreviewRequest"]["field"];
export type EditApplies = Schemas["EditEffect"]["applies"];
export type DiffKind = Schemas["DiffLine"]["kind"];
export type HistoryOp = Schemas["HistoryRow"]["op"];
export type ModelCheckStatus = Schemas["RunsAt"]["status"];

/** The server's request id pattern (REQUEST_ID_PATTERN in models.py). */
export const REQUEST_ID_PATTERN = /^[A-Za-z0-9_-]{8,64}$/;

export type EditsState = Schemas["EditsState"];
export type EditPreviewRequest = Schemas["EditPreviewRequest"];
export type EditSaveRequest = Schemas["EditSaveRequest"];
// The schema lists `anyway` as required because the export reads a defaulted field in
// serialization mode. The server's default is false, so the page may leave it out.
export type EditUndoRequest = Omit<Schemas["EditUndoRequest"], "anyway"> & {
  anyway?: boolean;
};
export type DiffLine = Schemas["DiffLine"];
export type EditDiff = Schemas["EditDiff"];
export type EditTarget = Schemas["EditTarget"];
export type RunsAt = Schemas["RunsAt"];
export type EditSetChange = Schemas["EditSetChange"];
export type EditRuns = Schemas["EditRuns"];
export type EditEffect = Schemas["EditEffect"];
export type OptionRunsAt = Schemas["OptionRunsAt"];
export type ScopeOutcome = Schemas["ScopeOutcome"];
export type EditScopeRow = Schemas["EditScopeRow"];
export type EditReach = Schemas["EditReach"];
export type EditWarning = Schemas["EditWarning"];
export type EditSummary = Schemas["EditSummary"];
export type EditRefusal = Schemas["EditRefusal"];
export type EditPreview = Schemas["EditPreview"];
export type EditSaved = Schemas["EditSaved"];
export type EditConflict = Schemas["EditConflict"];
export type EditError = Schemas["EditError"];
export type UndoDone = Schemas["UndoDone"];
export type UndoPreview = Schemas["UndoPreview"];
export type UndoConflict = Schemas["UndoConflict"];
export type RecheckAnswer = Schemas["RecheckAnswer"];
export type DriftAnswer = Schemas["DriftAnswer"];
export type HistorySubject = Schemas["HistorySubject"];
export type HistoryRecheck = Schemas["HistoryRecheck"];
export type HistoryRow = Schemas["HistoryRow"];
export type HistoryOlder = Schemas["HistoryOlder"];
export type BackupFolder = Schemas["BackupFolder"];
export type EditHistory = Schemas["EditHistory"];
export type OpenWarning = Schemas["OpenWarning"];

// ---------------------------------------------------------------------------------------------
// The edit client.
// ---------------------------------------------------------------------------------------------

/**
 * Why an edit call did not succeed. A server refusal code, or one of the page's own: `network`
 * (no answer), `server` (a 5xx), `locked` (a 401, the tab moved to the locked page) and `refused`
 * (a refusal with a code the page does not know).
 */
export type EditReason = EditRefusalCode | "network" | "server" | "locked" | "refused";

/** One answer. Refusals are values, never thrown, and carry no server text but the code. */
export type EditReply<T> =
  | { ok: true; status: number; body: T }
  | { ok: false; status: number; reason: EditReason; body: unknown };

export type RestartReason = "edits_off" | "edit_key_unknown" | "instance_changed" | "key_handoff";

/**
 * The one restart state (plan 3.2). `mode` is the new server's edit mode once an /api/app answer
 * (or an `edits_off` answer) has said it, and null until then.
 */
export interface RestartState {
  reason: RestartReason;
  mode: EditsMode | null;
}

export interface EditClient {
  /** POSTs an edit write with the read key and the project's edit key. */
  postEdit: <T>(
    path: string,
    project: string,
    body: unknown,
    signal?: AbortSignal,
  ) => Promise<EditReply<T>>;
  /** POSTs a call that needs only the read key, such as the seen mark. */
  postRead: <T>(path: string, body: unknown, signal?: AbortSignal) => Promise<EditReply<T>>;
  /** GETs one of the always-mounted edit reads, with the read key only. */
  getEdit: <T>(path: string, signal?: AbortSignal) => Promise<EditReply<T>>;
  getRestart: () => RestartState | null;
  /** Listens for restart changes. The first listener opens the access channel. */
  subscribe: (listener: () => void) => () => void;
  /** Called with the `edits` of every /api/app or history answer. */
  noteEdits: (edits: EditsState) => void;
  /** The instance the page loaded under, or null when neither the meta tag nor an answer said. */
  loadedInstance: () => string | null;
  /** A fresh id for one save or undo body, matching REQUEST_ID_PATTERN. */
  newRequestId: () => string;
}

export interface EditClientOptions {
  access: Access;
  connection: Connection;
  fetchFn?: typeof fetch;
  now?: () => number;
  /** The `bartab-instance` meta tag. Defaults to readLaunch(). */
  instance?: string;
  makeChannel?: () => BroadcastChannel;
  makeId?: () => string;
}

const RESTART_CODES: ReadonlySet<string> = new Set(["edits_off", "edit_key_unknown"]);

export function isEditRefusalCode(value: unknown): value is EditRefusalCode {
  return typeof value === "string" && (EDIT_REFUSAL_CODES as readonly string[]).includes(value);
}

/** 16 random bytes in base64url, 22 characters. */
export function defaultRequestId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let text = "";
  for (const byte of bytes) text += String.fromCharCode(byte);
  return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function createEditClient(options: EditClientOptions): EditClient {
  const { access, connection } = options;
  const fetchFn = options.fetchFn ?? ((...args: Parameters<typeof fetch>) => fetch(...args));
  const now = options.now ?? (() => Date.now());
  const makeId = options.makeId ?? defaultRequestId;
  const metaInstance = options.instance ?? readLaunch().instance;
  let loaded: string | null = metaInstance === "" ? null : metaInstance;
  let restart: RestartState | null = null;
  const listeners = new Set<() => void>();
  let channel: BroadcastChannel | null = null;

  function notify(): void {
    for (const listener of listeners) listener();
  }

  function enterRestart(reason: RestartReason, mode: EditsMode | null): void {
    if (restart !== null) {
      if (mode !== null && restart.mode !== mode) {
        restart = { ...restart, mode };
        notify();
      }
      return;
    }
    restart = { reason, mode };
    notify();
  }

  function onMessage(event: MessageEvent): void {
    const data: unknown = event.data;
    if (!isRecord(data) || data.type !== "offer" || typeof data.instance !== "string") return;
    if (loaded !== null && data.instance !== loaded) enterRestart("key_handoff", null);
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

  function closeChannel(): void {
    if (channel === null) return;
    channel.removeEventListener("message", onMessage);
    channel.close();
    channel = null;
  }

  function failed(): void {
    if (connection.recordFailure() >= FAILURES_TO_STOP) access.setStopped();
  }

  async function send<T>(
    path: string,
    method: "GET" | "POST",
    body: unknown,
    editProject: string | null,
    signal: AbortSignal | undefined,
  ): Promise<EditReply<T>> {
    const headers: Record<string, string> = {};
    const readKey = access.getReadKey();
    if (readKey !== null) headers["X-Bartab-Key"] = readKey;
    if (method === "POST") headers["Content-Type"] = "application/json";
    if (editProject !== null) {
      const editKey = access.getEditKeys()[editProject];
      if (editKey === undefined) {
        // No key for this project: the server would answer edit_key_unknown.
        enterRestart("edit_key_unknown", null);
        return { ok: false, status: 0, reason: "edit_key_unknown", body: null };
      }
      headers["X-Bartab-Edit"] = editKey;
    }
    const init: RequestInit = { method, headers };
    if (method === "POST") init.body = JSON.stringify(body);
    if (signal !== undefined) init.signal = signal;
    let response: Response;
    try {
      response = await fetchFn(path, init);
    } catch (error) {
      if (isAbort(error)) throw error;
      failed();
      return { ok: false, status: 0, reason: "network", body: null };
    }
    if (response.status >= 500) {
      failed();
      return { ok: false, status: response.status, reason: "server", body: null };
    }
    connection.recordAnswer(now());
    let parsed: unknown = null;
    try {
      parsed = await response.json();
    } catch (error) {
      if (isAbort(error)) throw error;
      parsed = null;
    }
    const code = isRecord(parsed) && typeof parsed.code === "string" ? parsed.code : null;
    if (response.status === 401) {
      access.lock(reasonFor401(code));
      return { ok: false, status: 401, reason: "locked", body: null };
    }
    if (code !== null && RESTART_CODES.has(code)) {
      enterRestart(code as RestartReason, code === "edits_off" ? "off" : null);
      return { ok: false, status: response.status, reason: code as EditRefusalCode, body: null };
    }
    if (!response.ok) {
      const reason: EditReason = isEditRefusalCode(code) ? code : "refused";
      return { ok: false, status: response.status, reason, body: parsed };
    }
    return { ok: true, status: response.status, body: parsed as T };
  }

  return {
    postEdit: (path, project, body, signal) => send(path, "POST", body, project, signal),
    postRead: (path, body, signal) => send(path, "POST", body, null, signal),
    getEdit: (path, signal) => send(path, "GET", null, null, signal),
    getRestart: () => restart,
    subscribe(listener) {
      listeners.add(listener);
      openChannel();
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0) closeChannel();
      };
    },
    noteEdits(edits) {
      loaded ??= edits.instance;
      if (restart !== null) {
        enterRestart(restart.reason, edits.state);
        return;
      }
      if (edits.instance !== loaded) enterRestart("instance_changed", edits.state);
    },
    loadedInstance: () => loaded,
    newRequestId: makeId,
  };
}

export const EditContext = createContext<EditClient | null>(null);

const fallbackClients = new WeakMap<ApiClient, EditClient>();

/** The edit client built on an ApiClient's access and connection, one per ApiClient. */
export function editClientFor(api: ApiClient): EditClient {
  let client = fallbackClients.get(api);
  if (client === undefined) {
    client = createEditClient({ access: api.access, connection: api.connection });
    fallbackClients.set(api, client);
  }
  return client;
}

/** The provided edit client, or one built on the ApiContext client. */
export function useEditClient(): EditClient {
  const provided = use(EditContext);
  const api = use(ApiContext);
  if (provided !== null) return provided;
  if (api === null) throw new Error("useEditClient needs an EditContext or ApiContext provider");
  return editClientFor(api);
}

/** A thrown read failure. The message is the reason code only. */
export class EditRequestError extends Error {
  readonly reason: EditReason;
  readonly status: number;

  constructor(reason: EditReason, status: number) {
    super(reason);
    this.name = "EditRequestError";
    this.reason = reason;
    this.status = status;
  }
}

function unwrap<T>(reply: EditReply<T>): T {
  if (reply.ok) return reply.body;
  throw new EditRequestError(reply.reason, reply.status);
}

// ---------------------------------------------------------------------------------------------
// Invalidation.
// ---------------------------------------------------------------------------------------------

/**
 * The queries a save, an undo or a settled recheck invalidates (plan 5.1, designer item 13): the
 * Setup map, parts and problems (the item lives in its part), the Agents queries, /api/app (the To
 * fix count) and the edit reads. A user-scope edit, or an undo whose scope is not known, reaches
 * every project, so its keys drop the project and match them all by prefix.
 */
export function editInvalidationKeys(project: string, scope: EditScope | null): QueryKey[] {
  const tail = scope === null || scope === "user" ? [] : [project];
  return [
    ["setup", "map", ...tail],
    ["setup", "part", ...tail],
    ["setup", "problems", ...tail],
    ["review", "agents", ...tail],
    ["app", ...tail],
    ["edit", "history", ...tail],
    ["edit", "open", ...tail],
  ];
}

export function invalidateAfterEdit(
  client: QueryClient,
  project: string,
  scope: EditScope | null,
): void {
  for (const queryKey of editInvalidationKeys(project, scope)) {
    void client.invalidateQueries({ queryKey });
  }
}

// ---------------------------------------------------------------------------------------------
// Preview.
// ---------------------------------------------------------------------------------------------

export const PREVIEW_DEBOUNCE_MS = 250;

/** A settings edit the person has picked. */
export interface SettingsChoice {
  op: EditOp;
  scope: EditScope;
  field: SettingsEditField;
  value: string | number;
}

/** A stable text for a choice, so a new object with the same values is not a new choice. */
export function choiceKeyOf(choice: SettingsChoice | null): string | null {
  if (choice === null) return null;
  return JSON.stringify([choice.op, choice.scope, choice.field, choice.value]);
}

function choiceFromKey(key: string): SettingsChoice {
  const [op, scope, field, value] = JSON.parse(key) as [
    EditOp,
    EditScope,
    SettingsEditField,
    string | number,
  ];
  return { op, scope, field, value };
}

export interface PreviewSnapshot {
  choiceKey: string | null;
  /** The latest matching answer, or the last one while a newer one is pending. */
  preview: EditPreview | null;
  /** True while the latest choice has no matching answer. Save is held. */
  pending: boolean;
  /** The latest request's seq. */
  seq: number;
  /** Bumped on every new choice, not on a refresh of the same choice. */
  gen: number;
  /** Why the latest preview failed, or null. */
  reason: EditReason | null;
}

export interface PreviewController {
  getSnapshot: () => PreviewSnapshot;
  subscribe: (listener: () => void) => () => void;
  getChoice: () => SettingsChoice | null;
  setChoice: (choice: SettingsChoice | null) => void;
  /** Asks again for the same choice, at once, with a new seq. */
  refresh: () => void;
  /** Takes a preview from a 409 answer. Dropped unless it answers the latest seq. */
  accept: (preview: EditPreview) => boolean;
  dispose: () => void;
}

export function createPreviewController(
  edit: EditClient,
  project: string,
  debounceMs = PREVIEW_DEBOUNCE_MS,
): PreviewController {
  let choice: SettingsChoice | null = null;
  let key: string | null = null;
  let seq = 0;
  let gen = 0;
  let preview: EditPreview | null = null;
  let reason: EditReason | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let inFlight: AbortController | null = null;
  const listeners = new Set<() => void>();
  let snapshot = build();

  function build(): PreviewSnapshot {
    return {
      choiceKey: key,
      preview,
      pending: choice !== null && preview?.seq !== seq,
      seq,
      gen,
      reason,
    };
  }

  function emit(): void {
    snapshot = build();
    for (const listener of listeners) listener();
  }

  function stop(): void {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    inFlight?.abort();
    inFlight = null;
  }

  async function fire(sent: number, picked: SettingsChoice): Promise<void> {
    timer = null;
    const controller = new AbortController();
    inFlight = controller;
    const body: EditPreviewRequest = { project, ...picked, seq: sent };
    let reply: EditReply<EditPreview>;
    try {
      reply = await edit.postEdit<EditPreview>(
        "/api/edit/preview",
        project,
        body,
        controller.signal,
      );
    } catch {
      return; // aborted by a newer request
    }
    if (inFlight === controller) inFlight = null;
    if (sent !== seq) return;
    if (reply.ok) {
      // A body that is not a preview, or one for another seq, is not this choice's answer.
      if ((reply.body as EditPreview | null)?.seq !== seq) return;
      preview = reply.body;
      reason = null;
    } else {
      reason = reply.reason;
    }
    emit();
  }

  function schedule(delay: number): void {
    stop();
    if (choice === null) return;
    seq += 1;
    const sent = seq;
    const picked = choice;
    timer = setTimeout(() => {
      void fire(sent, picked);
    }, delay);
  }

  return {
    getSnapshot: () => snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getChoice: () => choice,
    setChoice(next) {
      const nextKey = choiceKeyOf(next);
      if (nextKey === key) return;
      key = nextKey;
      choice = next;
      gen += 1;
      reason = null;
      if (next === null) {
        stop();
        seq += 1;
        preview = null;
      } else {
        schedule(debounceMs);
      }
      emit();
    },
    refresh() {
      if (choice === null) return;
      reason = null;
      schedule(0);
      emit();
    },
    accept(next) {
      if (choice === null || next.seq !== seq) return false;
      stop();
      preview = next;
      reason = null;
      emit();
      return true;
    },
    dispose() {
      stop();
      // A remount (StrictMode) sets the choice again and asks again.
      key = null;
      choice = null;
    },
  };
}

// ---------------------------------------------------------------------------------------------
// Save.
// ---------------------------------------------------------------------------------------------

export type SaveState =
  | { kind: "idle" }
  /** Pressed while the preview was pending. Sent once the matching preview has rendered. */
  | { kind: "held" }
  | { kind: "saving" }
  | { kind: "saved"; saved: EditSaved; scope: EditScope }
  /** A 409. The fresh preview is already in place. */
  | {
      kind: "conflict";
      code: "changed" | "preview_mismatch";
      changedKeys: string[];
      editedKeyChanged: boolean;
    }
  /** A refusal with no write, such as `bad_version` or `link_outside`. */
  | { kind: "refused"; code: EditReason; params: Record<string, string> }
  /** No answer, a 5xx or a locked tab. Pressing Save again resends with the same request id. */
  | { kind: "failed"; reason: EditReason }
  | { kind: "restart" };

export interface SaveController {
  getSnapshot: () => SaveState;
  subscribe: (listener: () => void) => () => void;
  /** Save. Sends now, holds while the preview is pending, and does nothing while saving. */
  save: () => void;
  /** Sends a held press if the matching preview is in, or drops it if the choice moved on. */
  release: () => void;
  reset: () => void;
}

export function createSaveController(
  edit: EditClient,
  preview: PreviewController,
  project: string,
  onSaved: (scope: EditScope) => void,
): SaveController {
  let state: SaveState = { kind: "idle" };
  let held: number | null = null;
  let last: { bodyKey: string; id: string } | null = null;
  const listeners = new Set<() => void>();

  function set(next: SaveState): void {
    state = next;
    for (const listener of listeners) listener();
  }

  async function send(current: EditPreview, picked: SettingsChoice): Promise<void> {
    if (current.refusal !== null) {
      set({ kind: "refused", code: current.refusal.code, params: current.refusal.params });
      return;
    }
    const base = { project, ...picked, seq: current.seq, version: current.version };
    const bodyKey = JSON.stringify(base);
    const id = last?.bodyKey === bodyKey ? last.id : edit.newRequestId();
    last = { bodyKey, id };
    const body: EditSaveRequest = { ...base, request_id: id };
    set({ kind: "saving" });
    const reply = await edit.postEdit<EditSaved>("/api/edit/save", project, body);
    if (reply.ok) {
      set({ kind: "saved", saved: reply.body, scope: picked.scope });
      onSaved(picked.scope);
      preview.refresh();
      return;
    }
    if (reply.reason === "edits_off" || reply.reason === "edit_key_unknown") {
      set({ kind: "restart" });
      return;
    }
    if (reply.reason === "changed" || reply.reason === "preview_mismatch") {
      const conflict = reply.body as EditConflict | null;
      if (conflict?.preview == null || !preview.accept(conflict.preview)) preview.refresh();
      set({
        kind: "conflict",
        code: reply.reason,
        changedKeys: conflict?.changed_keys ?? [],
        editedKeyChanged: conflict?.edited_key_changed ?? false,
      });
      return;
    }
    if (reply.reason === "bad_version") {
      // A token from another run or a forged one. Ask for a fresh token for the same choice.
      preview.refresh();
      set({ kind: "refused", code: "bad_version", params: {} });
      return;
    }
    if (reply.reason === "network" || reply.reason === "server" || reply.reason === "locked") {
      set({ kind: "failed", reason: reply.reason });
      return;
    }
    const error = reply.body as Partial<EditError> | null;
    set({ kind: "refused", code: reply.reason, params: error?.params ?? {} });
  }

  function trySend(): boolean {
    const snap = preview.getSnapshot();
    const picked = preview.getChoice();
    if (snap.pending || snap.preview === null || picked === null) return false;
    void send(snap.preview, picked);
    return true;
  }

  return {
    getSnapshot: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    save() {
      if (edit.getRestart() !== null) {
        held = null;
        set({ kind: "restart" });
        return;
      }
      if (state.kind === "saving") return;
      const snap = preview.getSnapshot();
      if (snap.choiceKey === null) return;
      if (trySend()) {
        held = null;
        return;
      }
      held = snap.gen;
      set({ kind: "held" });
    },
    release() {
      if (held === null) return;
      if (edit.getRestart() !== null) {
        held = null;
        set({ kind: "restart" });
        return;
      }
      if (preview.getSnapshot().gen !== held) {
        held = null;
        set({ kind: "idle" });
        return;
      }
      if (trySend()) held = null;
    },
    reset() {
      held = null;
      set({ kind: "idle" });
    },
  };
}

// ---------------------------------------------------------------------------------------------
// Undo.
// ---------------------------------------------------------------------------------------------

export type UndoStep =
  | { kind: "idle" }
  | { kind: "sending"; rowId: string }
  | { kind: "done"; rowId: string }
  /** The file changed since the save. "Undo anyway" sends this preview's token. */
  | { kind: "conflict"; rowId: string; undoPreview: UndoPreview; scope: EditScope | null }
  | { kind: "refused"; rowId: string; code: EditReason; params: Record<string, string> }
  | { kind: "failed"; rowId: string; reason: EditReason }
  | { kind: "restart" };

export interface UndoController {
  getSnapshot: () => UndoStep;
  subscribe: (listener: () => void) => () => void;
  /** Undoes one row. `scope` narrows the invalidation, null invalidates every project. */
  undo: (rowId: string, scope?: EditScope | null) => void;
  /** Confirms "Undo anyway" after a `changed_since_save` answer. */
  undoAnyway: () => void;
  reset: () => void;
}

export function createUndoController(
  edit: EditClient,
  project: string,
  onUndone: (scope: EditScope | null) => void,
): UndoController {
  let state: UndoStep = { kind: "idle" };
  let last: { bodyKey: string; id: string } | null = null;
  const listeners = new Set<() => void>();

  function set(next: UndoStep): void {
    state = next;
    for (const listener of listeners) listener();
  }

  async function send(
    rowId: string,
    scope: EditScope | null,
    confirm: { version: string } | null,
  ): Promise<void> {
    if (edit.getRestart() !== null) {
      set({ kind: "restart" });
      return;
    }
    if (state.kind === "sending") return;
    const base: Omit<EditUndoRequest, "request_id"> =
      confirm === null
        ? { project, row_id: rowId }
        : { project, row_id: rowId, version: confirm.version, anyway: true };
    const bodyKey = JSON.stringify(base);
    const id = last?.bodyKey === bodyKey ? last.id : edit.newRequestId();
    last = { bodyKey, id };
    set({ kind: "sending", rowId });
    const reply = await edit.postEdit<UndoDone>("/api/edit/undo", project, {
      ...base,
      request_id: id,
    });
    if (reply.ok) {
      set({ kind: "done", rowId });
      onUndone(scope);
      return;
    }
    if (reply.reason === "edits_off" || reply.reason === "edit_key_unknown") {
      set({ kind: "restart" });
      return;
    }
    if (reply.reason === "changed_since_save") {
      const conflict = reply.body as UndoConflict | null;
      if (conflict?.undo_preview != null) {
        set({ kind: "conflict", rowId, undoPreview: conflict.undo_preview, scope });
        return;
      }
    }
    if (reply.reason === "network" || reply.reason === "server" || reply.reason === "locked") {
      set({ kind: "failed", rowId, reason: reply.reason });
      return;
    }
    const error = reply.body as Partial<EditError> | null;
    set({ kind: "refused", rowId, code: reply.reason, params: error?.params ?? {} });
  }

  return {
    getSnapshot: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    undo(rowId, scope = null) {
      void send(rowId, scope, null);
    },
    undoAnyway() {
      if (state.kind !== "conflict") return;
      void send(state.rowId, state.scope, { version: state.undoPreview.version });
    },
    reset() {
      set({ kind: "idle" });
    },
  };
}

// ---------------------------------------------------------------------------------------------
// Recheck.
// ---------------------------------------------------------------------------------------------

/** When the page reads a saved row again, counted from the save. Then it stops (plan 5.1). */
export const RECHECK_AT_MS = [2_000, 10_000] as const;

export interface RecheckSnapshot {
  answer: RecheckAnswer | null;
  /** Reads made so far. */
  reads: number;
  /** True after the last read. */
  done: boolean;
  reason: EditReason | null;
}

export interface RecheckController {
  getSnapshot: () => RecheckSnapshot;
  subscribe: (listener: () => void) => () => void;
  start: () => void;
  stop: () => void;
}

export function createRecheckController(
  edit: EditClient,
  project: string,
  rowId: string,
  onSettled: () => void,
): RecheckController {
  let snapshot: RecheckSnapshot = { answer: null, reads: 0, done: false, reason: null };
  let timers: ReturnType<typeof setTimeout>[] = [];
  let aborter: AbortController | null = null;
  let settledAs: RecheckState | null = null;
  const listeners = new Set<() => void>();
  const path = `/api/edit/rows/${encodeURIComponent(rowId)}?project=${encodeURIComponent(project)}`;

  function set(next: RecheckSnapshot): void {
    snapshot = next;
    for (const listener of listeners) listener();
  }

  async function read(last: boolean): Promise<void> {
    const controller = new AbortController();
    aborter = controller;
    let reply: EditReply<RecheckAnswer>;
    try {
      reply = await edit.getEdit<RecheckAnswer>(path, controller.signal);
    } catch {
      return;
    }
    const reads = snapshot.reads + 1;
    if (!reply.ok) {
      set({ ...snapshot, reads, done: last, reason: reply.reason });
      return;
    }
    set({ answer: reply.body, reads, done: last, reason: null });
    if (reply.body.state !== "checking" && reply.body.state !== settledAs) {
      settledAs = reply.body.state;
      onSettled();
    }
  }

  return {
    getSnapshot: () => snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    start() {
      if (timers.length > 0 || snapshot.done) return;
      timers = RECHECK_AT_MS.map((at, index) =>
        setTimeout(() => {
          void read(index === RECHECK_AT_MS.length - 1);
        }, at),
      );
    },
    stop() {
      for (const timer of timers) clearTimeout(timer);
      timers = [];
      aborter?.abort();
      aborter = null;
    },
  };
}

// ---------------------------------------------------------------------------------------------
// Hooks.
// ---------------------------------------------------------------------------------------------

function isEditsState(value: unknown): value is EditsState {
  return isRecord(value) && typeof value.instance === "string" && typeof value.state === "string";
}

/**
 * The restart state. It feeds every /api/app answer in the cache to the edit client, and when a
 * restart begins it refetches /api/app so the box can say the new server's mode.
 */
export function useEditRestart(): RestartState | null {
  const edit = useEditClient();
  const client = useQueryClient();
  useEffect(() => {
    const cache = client.getQueryCache();
    const look = (data: unknown): void => {
      if (isRecord(data) && isEditsState(data.edits)) edit.noteEdits(data.edits);
    };
    for (const query of cache.findAll({ queryKey: ["app"] })) look(query.state.data);
    return cache.subscribe((event) => {
      const head: unknown = (event.query.queryKey as readonly unknown[])[0];
      // Only a new answer counts. A refetch start also fires an update, and its data is the old
      // answer, which would flip the restart box back to the mode it had before.
      if (event.type === "updated" && head === "app" && event.action.type === "success") {
        look(event.query.state.data);
      }
    });
  }, [client, edit]);
  const restart = useSyncExternalStore(edit.subscribe, edit.getRestart);
  const reason = restart?.reason ?? null;
  useEffect(() => {
    if (reason !== null) void client.invalidateQueries({ queryKey: ["app"] });
  }, [client, reason]);
  return restart;
}

export interface PreviewHandle {
  controller: PreviewController;
  preview: EditPreview | null;
  /** True while the latest choice has no matching answer. Save is held. */
  pending: boolean;
  gen: number;
  reason: EditReason | null;
  restart: RestartState | null;
  refresh: () => void;
}

/** The preview for one settings choice. Null asks for nothing. */
export function usePreview(project: string, choice: SettingsChoice | null): PreviewHandle {
  const edit = useEditClient();
  const restart = useEditRestart();
  const controller = useMemo(() => createPreviewController(edit, project), [edit, project]);
  useEffect(() => () => controller.dispose(), [controller]);
  const key = choiceKeyOf(choice);
  useEffect(() => {
    controller.setChoice(key === null ? null : choiceFromKey(key));
  }, [controller, key]);
  const snap = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  return {
    controller,
    preview: snap.preview,
    // Also pending in the render before the effect hands the new choice over.
    pending: snap.pending || snap.choiceKey !== key,
    gen: snap.gen,
    reason: snap.reason,
    restart,
    refresh: controller.refresh,
  };
}

export interface SaveHandle {
  state: SaveState;
  /** False while pending, saving, refused by the preview or in a restart. */
  canSave: boolean;
  save: () => void;
  reset: () => void;
}

export function useSave(project: string, handle: PreviewHandle): SaveHandle {
  const edit = useEditClient();
  const client = useQueryClient();
  const preview = handle.controller;
  const controller = useMemo(
    () =>
      createSaveController(edit, preview, project, (scope) => {
        invalidateAfterEdit(client, project, scope);
      }),
    [edit, preview, project, client],
  );
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  // A held press goes once the matching preview has rendered, or drops when the choice moves.
  useEffect(() => {
    controller.release();
  }, [controller, handle.preview, handle.pending, handle.gen, handle.restart]);
  const canSave =
    handle.restart === null &&
    !handle.pending &&
    handle.preview !== null &&
    handle.preview.refusal === null &&
    state.kind !== "saving";
  return { state, canSave, save: controller.save, reset: controller.reset };
}

export interface UndoHandle {
  state: UndoStep;
  restart: RestartState | null;
  undo: (rowId: string, scope?: EditScope | null) => void;
  undoAnyway: () => void;
  reset: () => void;
}

export function useUndo(project: string): UndoHandle {
  const edit = useEditClient();
  const client = useQueryClient();
  const restart = useEditRestart();
  const controller = useMemo(
    () =>
      createUndoController(edit, project, (scope) => {
        invalidateAfterEdit(client, project, scope);
      }),
    [edit, project, client],
  );
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  return {
    state,
    restart,
    undo: controller.undo,
    undoAnyway: controller.undoAnyway,
    reset: controller.reset,
  };
}

const IDLE_RECHECK: RecheckSnapshot = { answer: null, reads: 0, done: false, reason: null };
const noSubscribe = (): (() => void) => () => undefined;
const idleRecheck = (): RecheckSnapshot => IDLE_RECHECK;

/**
 * Reads a saved row at about 2 s and 10 s after the save, then stops. A read that settles on a
 * new state invalidates the same queries a save does. Null reads nothing.
 */
export function useRecheck(
  project: string,
  saved: { rowId: string; scope: EditScope | null } | null,
): RecheckSnapshot {
  const edit = useEditClient();
  const client = useQueryClient();
  const rowId = saved?.rowId ?? null;
  const scope = saved?.scope ?? null;
  const controller = useMemo(
    () =>
      rowId === null
        ? null
        : createRecheckController(edit, project, rowId, () => {
            invalidateAfterEdit(client, project, scope);
          }),
    [edit, project, rowId, scope, client],
  );
  useEffect(() => {
    if (controller === null) return;
    controller.start();
    return () => controller.stop();
  }, [controller]);
  return useSyncExternalStore(
    controller === null ? noSubscribe : controller.subscribe,
    controller === null ? idleRecheck : controller.getSnapshot,
  );
}

/** The Changes page rows. The answer's `edits` also feeds the restart check. */
export function useHistory(project: string): UseQueryResult<EditHistory> {
  const edit = useEditClient();
  return useQuery({
    queryKey: ["edit", "history", project],
    queryFn: async ({ signal }) => {
      const body = unwrap(
        await edit.getEdit<EditHistory>(
          `/api/edit/history?project=${encodeURIComponent(project)}`,
          signal,
        ),
      );
      edit.noteEdits(body.edits);
      return body;
    },
    refetchOnWindowFocus: "always",
    retry: false,
  });
}

/** The drift of an overwritten row. Null reads nothing. */
export function useDrift(project: string, rowId: string | null): UseQueryResult<DriftAnswer> {
  const edit = useEditClient();
  return useQuery({
    queryKey: ["edit", "drift", project, rowId],
    queryFn: async ({ signal }) =>
      unwrap(
        await edit.getEdit<DriftAnswer>(
          `/api/edit/rows/${encodeURIComponent(rowId ?? "")}/drift?project=${encodeURIComponent(project)}`,
          signal,
        ),
      ),
    enabled: rowId !== null,
    retry: false,
  });
}

/** The newest overwritten row not yet seen for one item. Null reads nothing. */
export function useOpenWarning(project: string, item: string | null): UseQueryResult<OpenWarning> {
  const edit = useEditClient();
  return useQuery({
    queryKey: ["edit", "open", project, item],
    queryFn: async ({ signal }) =>
      unwrap(
        await edit.getEdit<OpenWarning>(
          `/api/edit/open?project=${encodeURIComponent(project)}&item=${encodeURIComponent(item ?? "")}`,
          signal,
        ),
      ),
    enabled: item !== null,
    retry: false,
  });
}

/** Marks a row's warning seen. Read key only. Then the Changes rows and open warnings refetch. */
export function useMarkSeen(project: string): UseMutationResult<unknown, Error, string> {
  const edit = useEditClient();
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (rowId: string) =>
      unwrap(
        await edit.postRead<unknown>(`/api/edit/rows/${encodeURIComponent(rowId)}/seen`, {
          project,
        }),
      ),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["edit", "history", project] }),
        client.invalidateQueries({ queryKey: ["edit", "open", project] }),
      ]);
    },
  });
}
