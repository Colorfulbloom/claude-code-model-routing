/*
 * A fake server for the app tests. fakeServer() returns a fetch that answers /api/app and
 * /api/projects from the object it holds, so a test changes the answers by changing the object.
 */
import type { AppInfo, Project } from "@/api/types";

export const INSTANCE = "inst-1";

export const PROJECTS: Project[] = [
  { key: "builder", name: "Builder", display_path: "/work/builder", state: "ok", running: true },
  {
    key: "driftwood",
    name: "Driftwood",
    display_path: "/work/driftwood",
    state: "ok",
    running: false,
  },
  {
    key: "saltmarsh",
    name: "Saltmarsh",
    display_path: "/work/saltmarsh",
    state: "no_claude_folder",
    running: false,
  },
  {
    key: "harbor",
    name: "Harbor notes",
    display_path: "/work/old/harbor-notes",
    state: "folder_not_found",
    running: false,
  },
];

export function appInfo(over: Partial<AppInfo> = {}): AppInfo {
  return {
    server_time: "2026-11-08T15:42:00Z",
    instance: INSTANCE,
    claude_version: "2.1.310",
    ingest: {
      state: "done",
      files_done: 0,
      files_total: 0,
      bytes_done: 0,
      bytes_total: 0,
      error: null,
      retrying: false,
    },
    running: [{ project: "builder", session: "s1" }],
    to_fix_count: 4,
    editable_projects: [],
    ...over,
  };
}

export interface FakeServer {
  app: AppInfo;
  projects: Project[];
  /** True makes every call fail like a stopped server. */
  down: boolean;
  /** Paths requested, in order, for assertions. */
  calls: string[];
  fetch: typeof fetch;
}

export function fakeServer(init: Partial<Pick<FakeServer, "app" | "projects">> = {}): FakeServer {
  const server: FakeServer = {
    app: init.app ?? appInfo(),
    projects: init.projects ?? PROJECTS,
    down: false,
    calls: [],
    fetch: (input) => {
      const path =
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      server.calls.push(path);
      if (server.down) return Promise.reject(new TypeError("Failed to fetch"));
      const body = path.startsWith("/api/projects") ? { projects: server.projects } : server.app;
      return Promise.resolve(new Response(JSON.stringify(body)));
    },
  };
  return server;
}
