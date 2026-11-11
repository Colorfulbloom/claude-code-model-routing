/*
 * A fake server for the app tests. fakeServer() returns a fetch that answers /api/app and
 * /api/projects from the object it holds, so a test changes the answers by changing the object.
 */
import type { AppInfo, LiveSessions, PricesAnswer, Project, Timeline } from "@/api/types";
import { agentList, costChart, modelList, sessionList, summary } from "@/test/review";

export const INSTANCE = "inst-1";

export const PROJECTS: Project[] = [
  {
    key: "builder",
    name: "Builder",
    display_path: "/work/builder",
    state: "ok",
    running: true,
    listed: true,
  },
  {
    key: "driftwood",
    name: "Driftwood",
    display_path: "/work/driftwood",
    state: "ok",
    running: false,
    listed: true,
  },
  {
    key: "saltmarsh",
    name: "Saltmarsh",
    display_path: "/work/saltmarsh",
    state: "no_claude_folder",
    running: false,
    listed: true,
  },
  {
    key: "harbor",
    name: "Harbor notes",
    display_path: "/work/old/harbor-notes",
    state: "folder_not_found",
    running: false,
    listed: true,
  },
];

export function historyInfo(over: Partial<AppInfo["history"]> = {}): AppInfo["history"] {
  return {
    oldest: "2026-09-03T14:20:00Z",
    first_ingest: "2026-09-03T14:31:00Z",
    last_backup: "2026-11-08T09:02:00Z",
    backup_failed: null,
    pass_error: null,
    unreadable_files: 0,
    kept_files: 0,
    no_usage_rows: 0,
    ...over,
  };
}

export function pricesInfo(over: Partial<PricesAnswer> = {}): PricesAnswer {
  return {
    source: "litellm",
    as_of: "2026-10-28",
    etag: "prices-1",
    cross_check: { state: "agree", models: [] },
    models: [],
    ...over,
  };
}

export function appInfo(over: Partial<AppInfo> = {}): AppInfo {
  return {
    server_time: "2026-11-08T15:42:00Z",
    instance: INSTANCE,
    claude_version: "2.1.310",
    as_of: "2026-11-08T15:41:00Z",
    pass_running_since: null,
    etag: "etag-1",
    ingest: {
      state: "done",
      files_done: 0,
      files_total: 0,
      bytes_done: 0,
      bytes_total: 0,
      error: null,
      retrying: false,
      retry_at: null,
    },
    history: historyInfo(),
    running: [{ project: "builder", session: "s1" }],
    to_fix_count: 4,
    editable_projects: [],
    edits: { state: "off", instance: INSTANCE },
    mode: "fixture",
    clock: { kind: "real", rate_n: null },
    ...over,
  };
}

export function liveSessions(over: Partial<LiveSessions> = {}): LiveSessions {
  return {
    server_time: "2026-11-08T15:42:00Z",
    as_of: "2026-11-08T15:41:00Z",
    etag: "sessions-1",
    unchanged: false,
    sessions: [],
    latest_ended: null,
    ...over,
  };
}

export interface FakeServer {
  app: AppInfo;
  /** The Live session list. It answers `unchanged` when the asked etag matches. */
  live: LiveSessions;
  /** Timelines by session id. A session with none answers 404 unknown_session. */
  timelines: Record<string, Timeline>;
  projects: Project[];
  prices: PricesAnswer;
  /** True makes every call fail like a stopped server. */
  down: boolean;
  /** Paths requested, in order, for assertions. */
  calls: string[];
  fetch: typeof fetch;
}

export function fakeServer(
  init: Partial<Pick<FakeServer, "app" | "projects" | "prices" | "live" | "timelines">> = {},
): FakeServer {
  const server: FakeServer = {
    app: init.app ?? appInfo(),
    projects: init.projects ?? PROJECTS,
    prices: init.prices ?? pricesInfo(),
    live: init.live ?? liveSessions(),
    timelines: init.timelines ?? {},
    down: false,
    calls: [],
    fetch: (input) => {
      const path =
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      server.calls.push(path);
      if (server.down) return Promise.reject(new TypeError("Failed to fetch"));
      if (path.startsWith("/api/live/sessions")) {
        const etag = new URL(path, "http://x").searchParams.get("etag");
        const body =
          etag === server.live.etag
            ? { etag, server_time: server.live.server_time, unchanged: true }
            : server.live;
        return Promise.resolve(new Response(JSON.stringify(body)));
      }
      const timeline = /^\/api\/sessions\/([^/?]+)\/timeline/.exec(path);
      if (timeline?.[1] !== undefined) {
        const found = server.timelines[decodeURIComponent(timeline[1])];
        if (found === undefined) {
          return Promise.resolve(
            new Response(JSON.stringify({ code: "unknown_session", path: null }), { status: 404 }),
          );
        }
        const etag = new URL(path, "http://x").searchParams.get("etag");
        const body =
          etag === found.etag
            ? { etag, project: found.project, server_time: found.server_time, unchanged: true }
            : found;
        return Promise.resolve(new Response(JSON.stringify(body)));
      }
      // Summary and its chart, so a page test that is not about Review still mounts a working
      // page. The Review page tests use review-server.ts for answers of their own.
      if (path.startsWith("/api/summary?") || path.startsWith("/api/cost-chart?")) {
        const range = new URL(path, "http://x").searchParams.get("range") as "30d";
        const answer = path.startsWith("/api/summary?") ? summary({ range }) : costChart({ range });
        return Promise.resolve(new Response(JSON.stringify(answer)));
      }
      // Agents and Models, empty, so their routes mount as the empty range card.
      if (path.startsWith("/api/agents?") || path.startsWith("/api/models?")) {
        const range = new URL(path, "http://x").searchParams.get("range") as "30d";
        const answer = path.startsWith("/api/agents?")
          ? agentList({ range })
          : modelList({ range });
        return Promise.resolve(new Response(JSON.stringify(answer)));
      }
      if (path.startsWith("/api/sessions?")) {
        // The Session review Select list, empty, so a page that asks for it does not read app JSON.
        return Promise.resolve(new Response(JSON.stringify(sessionList([]))));
      }
      // The To fix feed, empty, so the To fix route mounts as its empty card. The To fix page tests
      // use tofix.ts for rows of their own.
      if (path.startsWith("/api/problems?")) {
        const body = {
          project: new URL(path, "http://x").searchParams.get("project") ?? "",
          server_time: "2026-11-10T15:00:00Z",
          as_of: "2026-11-10T15:00:00Z",
          etag: "problems-empty",
          unchanged: false,
          rows: [],
          counted: 0,
        };
        return Promise.resolve(new Response(JSON.stringify(body)));
      }
      // The rules reference, empty, so the Reference route mounts as a page with no rules. The
      // Reference page tests use rules-server.ts for the real rules.
      if (path.startsWith("/api/rules")) {
        const body = {
          server_time: "2026-11-10T15:00:00Z",
          etag: "rules-empty",
          unchanged: false,
          installed: null,
          checked_on: "",
          rules: [],
        };
        return Promise.resolve(new Response(JSON.stringify(body)));
      }
      const body = path.startsWith("/api/projects")
        ? { projects: server.projects }
        : path.startsWith("/api/prices")
          ? server.prices
          : server.app;
      return Promise.resolve(new Response(JSON.stringify(body)));
    },
  };
  return server;
}
