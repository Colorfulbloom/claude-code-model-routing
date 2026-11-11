/*
 * A fake edit server for the page tests (M6a task a11). It wraps a setup fake and answers the
 * /api/edit paths the settings editor and the Changes page read: preview, save, undo, history, one
 * row, its drift, the open warning and the seen mark. The state is plain, so a test can read what
 * was saved and set what the next call answers. Every path it was asked for, with the body, stays
 * in `edit.calls`.
 */
import type {
  EditHistory,
  EditPreview,
  EditScope,
  HistoryRow,
  RecheckAnswer,
  SettingsEditField,
} from "@/api/edit";
import { appInfo, INSTANCE } from "@/test/server";
import type { FakeServer } from "@/test/server";
import { setupServer } from "@/test/setup-server";
import type { SetupHandlers } from "@/test/setup-server";

export const EDIT_KEY = "fake-edit-key-builder";
export const SERVER_TIME = "2026-11-11T15:00:00Z";

export interface EditCall {
  path: string;
  method: string;
  body: Record<string, unknown> | null;
}

export interface EditState {
  /** What each scope's file holds for the edited field now. */
  current: Record<EditScope, string | null>;
  rows: HistoryRow[];
  older: HistoryRow[];
  recheck: RecheckAnswer["state"];
  /** Replaces the next save's answer. A number is an HTTP status with this code. */
  saveReply: { status: number; code: string; params?: Record<string, string> } | null;
  /** Replaces the next undo's answer the same way. */
  undoReply: { status: number; body: unknown } | null;
  /** The open warning's row, or null. */
  warning: HistoryRow | null;
  /** The edit mode /api/app reports. */
  mode: "on" | "off" | "unavailable";
  nextRow: number;
}

export type EditFake = FakeServer & {
  handlers: SetupHandlers;
  edit: EditState & { calls: EditCall[]; of(path: string): EditCall[] };
};

const PATHS: Record<EditScope, { display: string; real: string }> = {
  user: { display: "~/config/settings.json", real: "/home/me/.claude/settings.json" },
  project: { display: ".claude/settings.json", real: "/work/builder/.claude/settings.json" },
  local: {
    display: ".claude/settings.local.json",
    real: "/work/builder/.claude/settings.local.json",
  },
};

const LEVELS = ["low", "medium", "high", "xhigh"];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

export function historyRow(over: Partial<HistoryRow> = {}): HistoryRow {
  return {
    id: "row-1",
    time: "2026-11-11T14:30:00Z",
    scope: "local",
    op: "set",
    field: "effortLevel",
    subject: { kind: "main", name: null },
    from: "xhigh",
    to: "low",
    display_path: PATHS.local.display,
    real_path: PATHS.local.display,
    undo_state: "can_undo",
    not_undoable_reason: null,
    undone_at: null,
    recheck: { state: "confirmed", changed_keys: [], ours_survived: true, seen: false },
    ...over,
  };
}

function buildPreview(state: EditState, body: Record<string, unknown>): EditPreview {
  const scope = (body.scope as EditScope | undefined) ?? "local";
  const field = (body.field as SettingsEditField | undefined) ?? "effortLevel";
  const value =
    typeof body.value === "string" || typeof body.value === "number" ? String(body.value) : "";
  const held = state.current[scope];
  const same = held === value;
  const target = PATHS[scope];
  return {
    server_time: SERVER_TIME,
    seq: Number(body.seq),
    choice_key: `ck-${String(body.seq)}`,
    target: {
      scope,
      display_path: target.display,
      real_path: target.real,
      link: false,
      exists: held !== null,
      git_tracked: false,
      new_file: held === null,
    },
    effect: {
      set: { from: held, to: value },
      runs: {
        now: { value: held, status: "in_effect" },
        after: { value, status: "in_effect" },
      },
      applies: "new_session",
    },
    options:
      field === "effortLevel" || field === "maxEffortLevel"
        ? LEVELS.map((level) => ({
            value: level,
            runs_at: { value: level, status: "in_effect" as const },
          }))
        : [],
    scopes: (["user", "project", "local"] as const).map((s) => ({
      scope: s,
      display_path: PATHS[s].display,
      real_path: PATHS[s].real,
      link: false,
      git_tracked: false,
      current_value: state.current[s],
      outcome: { status: "in_effect" as const, beaten_by: null },
      read_only_reason: null,
      writable: true,
    })),
    reaches: [],
    warnings: [],
    diff: { lines: [], new_file: held === null },
    summary: {
      verb: held === null ? "creates" : "changes",
      lines_changed: 1,
      display_path: target.display,
    },
    read_at: SERVER_TIME,
    version: `v-${String(body.seq)}`,
    refusal: same ? { code: "no_change", params: {} } : null,
  } as unknown as EditPreview;
}

/** A setup fake with the edit paths. Edits are `on` unless the test says otherwise. */
export function editServer(
  over: Partial<SetupHandlers> = {},
  state: Partial<EditState> = {},
): EditFake {
  const server = setupServer(over);
  const edit: EditState & { calls: EditCall[]; of(path: string): EditCall[] } = {
    current: { user: "xhigh", project: "medium", local: "xhigh" },
    rows: [],
    older: [],
    recheck: "confirmed",
    saveReply: null,
    undoReply: null,
    warning: null,
    mode: "on",
    nextRow: 1,
    calls: [],
    of(path) {
      return this.calls.filter((call) => call.path.startsWith(path));
    },
    ...state,
  };
  // The rows are the server's own, so an undo in one test doesn't change a row another test shares.
  edit.rows = structuredClone(edit.rows);
  edit.older = structuredClone(edit.older);
  edit.warning = structuredClone(edit.warning);
  server.app = appInfo({ edits: { state: edit.mode, instance: INSTANCE } });
  const base = server.fetch;
  server.fetch = async (input, init) => {
    const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(path, "http://x");
    if (!url.pathname.startsWith("/api/edit/")) {
      // The app answer follows the mode, so a test can switch it between calls.
      if (url.pathname === "/api/app")
        server.app = appInfo({ edits: { state: edit.mode, instance: INSTANCE } });
      return base(input, init);
    }
    const raw = init?.body;
    const body = typeof raw === "string" ? (JSON.parse(raw) as Record<string, unknown>) : null;
    edit.calls.push({ path, method: init?.method ?? "GET", body });
    server.calls.push(path);
    const route = url.pathname;
    if (route === "/api/edit/preview" && body !== null) return json(buildPreview(edit, body));
    if (route === "/api/edit/save" && body !== null) {
      const reply = edit.saveReply;
      if (reply !== null) {
        edit.saveReply = null;
        return json({ code: reply.code, params: reply.params ?? {} }, reply.status);
      }
      const scope = body.scope as EditScope;
      const row = historyRow({
        id: `row-${String(edit.nextRow)}`,
        scope,
        field: String(body.field),
        from: edit.current[scope],
        to: body.value as string | number,
        display_path: PATHS[scope].display,
        real_path: PATHS[scope].display,
        recheck: { state: "checking", changed_keys: [], ours_survived: null, seen: false },
      });
      edit.nextRow += 1;
      edit.current[scope] = String(body.value);
      edit.rows.unshift(row);
      return json({
        server_time: SERVER_TIME,
        row_id: row.id,
        saved_at: SERVER_TIME,
        recheck_after_ms: 2000,
      });
    }
    if (route === "/api/edit/undo" && body !== null) {
      const reply = edit.undoReply;
      if (reply !== null) {
        edit.undoReply = null;
        return json(reply.body, reply.status);
      }
      const found = [...edit.rows, ...edit.older].find((row) => row.id === body.row_id);
      if (found !== undefined) {
        found.undo_state = "undone";
        found.undone_at = SERVER_TIME;
      }
      return json({ server_time: SERVER_TIME, row_id: String(body.row_id) });
    }
    if (route === "/api/edit/history") {
      const history: EditHistory = {
        server_time: SERVER_TIME,
        edits: { state: edit.mode, instance: INSTANCE },
        rows: edit.rows,
        older: { count: edit.older.length, rows: edit.older },
        backup_folder: { display: "~/backups", real: "/home/me/.config/backups" },
      };
      return json(history);
    }
    if (route === "/api/edit/open") return json({ server_time: SERVER_TIME, row: edit.warning });
    if (route.endsWith("/drift")) {
      return json({
        server_time: SERVER_TIME,
        code: null,
        lines: [{ kind: "add", old_n: null, new_n: 2, text: '  "effortLevel": "low"' }],
      });
    }
    if (route.endsWith("/seen")) return json({ server_time: SERVER_TIME });
    const one = /^\/api\/edit\/rows\/([^/]+)$/.exec(route);
    if (one?.[1] !== undefined) {
      const answer: RecheckAnswer = {
        server_time: SERVER_TIME,
        state: edit.recheck,
        changed_keys: edit.recheck === "overwritten" ? ["effortLevel"] : [],
        ours_survived: edit.recheck === "checking" ? null : edit.recheck === "confirmed",
        checked_at: edit.recheck === "checking" ? null : SERVER_TIME,
        seen: false,
      };
      return json(answer);
    }
    return json({ code: "not_found", params: {} }, 404);
  };
  return Object.assign(server, { edit });
}
