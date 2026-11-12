/// <reference types="node" />
/*
 * The screenshot fixture of M6a (m6-build.md section 8.4, task a13). It builds a made-up home and
 * project under a temp folder, outside every git work tree, and starts the real server on them with
 * `--claude-dir`, so the pages read real files and a save writes a real file.
 *
 *   <root>                       the made-up HOME
 *   <root>/.claude               the Claude folder (settings.json is a link into dotfiles)
 *   <root>/dotfiles/claude       the real user settings.json and agent builder.md
 *   <root>/work/tidewater-reporting   the project, a git repo with one commit
 *   <root>/data                  the server's data folder
 *
 * The dotfiles folder sits under the HOME, because a link may only reach a real file under the real
 * home or the project (m6-build.md section 3.4). `outsideFile` is the one file that does not, in a
 * second temp folder beside the root, for the link_outside state.
 *
 * The ledger is seeded only by driving real saves through the running server's API (`seedHistory`),
 * never by writing ledger files. A fixture with `local: false` starts with no settings.local.json,
 * so one seeded save creates it and its row can say "Undo deletes the file".
 *
 * Every git call runs with no global or system config and a fixed author. No path leaves the temp
 * folder, and nothing here reads the owner's own Claude files.
 */
import { execFileSync } from "node:child_process";
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { startServer } from "../server";
import type { Server } from "../server";

export const PROJECT_NAME = "Tidewater reporting";
export const PROJECT_KEY = "tidewater-reporting";
const MARKET = "bartab-demo";
const PLUGIN = "linter-kit";
const PLUGIN_VERSION = "0.1.0";

export interface M6Fixture {
  root: string;
  home: string;
  claudeDir: string;
  dataDir: string;
  project: string;
  /** The link the server reads as the user's settings.json, and the real file behind it. */
  userLink: string;
  userReal: string;
  projectFile: string;
  localFile: string;
  /** The builder wrote settings.local.json. */
  hasLocal: boolean;
  /** A settings file outside the home and the project, for a link that must be refused. */
  outsideFile: string;
  cleanup: () => void;
}

function writeJson(path: string, value: unknown): void {
  mkdirSync(join(path, ".."), { recursive: true });
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

function writeText(path: string, text: string): void {
  mkdirSync(join(path, ".."), { recursive: true });
  writeFileSync(path, text);
}

function git(cwd: string, args: string[]): void {
  execFileSync("git", ["-c", "commit.gpgsign=false", "-c", "core.fsmonitor=false", ...args], {
    cwd,
    stdio: "ignore",
    env: {
      PATH: process.env.PATH ?? "",
      HOME: cwd,
      GIT_CONFIG_GLOBAL: "/dev/null",
      GIT_CONFIG_NOSYSTEM: "1",
      GIT_AUTHOR_NAME: "Tidewater Tester",
      GIT_AUTHOR_EMAIL: "tester@example.test",
      GIT_COMMITTER_NAME: "Tidewater Tester",
      GIT_COMMITTER_EMAIL: "tester@example.test",
      GIT_AUTHOR_DATE: "2026-11-01T12:00:00+0000",
      GIT_COMMITTER_DATE: "2026-11-01T12:00:00+0000",
    },
  });
}

export interface BuildOptions {
  /** Start with .claude/settings.local.json (the env var), or without it. Default true. */
  local?: boolean;
  /** More keys for the user's settings.json, such as one of the Settings items that wait for M7. */
  userExtra?: Record<string, unknown>;
}

/** Builds the home, the dotfiles, the project and the plugin cache, all under a new temp folder. */
export function buildM6Fixture(options: BuildOptions = {}): M6Fixture {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "bartab-m6-")));
  const home = root;
  const claudeDir = join(home, ".claude");
  const dotfiles = join(home, "dotfiles", "claude");
  const project = join(home, "work", "tidewater-reporting");
  const userReal = join(dotfiles, "settings.json");
  const userLink = join(claudeDir, "settings.json");
  // A second temp folder, because everything under the root is under the made-up home.
  const outsideRoot = realpathSync(mkdtempSync(join(tmpdir(), "bartab-m6-outside-")));
  const outsideFile = join(outsideRoot, "settings.json");
  const install = join(claudeDir, "plugins", "cache", MARKET, PLUGIN, PLUGIN_VERSION);

  // The user layer: settings.json is a link into the dotfiles, and so is the agent builder.md.
  writeJson(userReal, {
    model: "opus",
    effortLevel: "xhigh",
    maxEffortLevel: "high",
    enabledPlugins: { [`${PLUGIN}@${MARKET}`]: true },
    ...options.userExtra,
  });
  mkdirSync(claudeDir, { recursive: true });
  symlinkSync(userReal, userLink);
  writeText(
    join(dotfiles, "agents", "builder.md"),
    "---\nname: builder\ndescription: Builds well-specified changes.\nmodel: sonnet\n---\nBuild it.\n",
  );
  mkdirSync(join(claudeDir, "agents"), { recursive: true });
  symlinkSync(join(dotfiles, "agents", "builder.md"), join(claudeDir, "agents", "builder.md"));
  writeJson(outsideFile, { effortLevel: "low" });

  // The plugin cache, with one agent named linter.
  writeJson(join(claudeDir, "plugins", "installed_plugins.json"), {
    version: 2,
    plugins: {
      [`${PLUGIN}@${MARKET}`]: [{ scope: "user", installPath: install, version: PLUGIN_VERSION }],
    },
  });
  writeJson(join(claudeDir, "plugins", "known_marketplaces.json"), {
    [MARKET]: {
      source: { source: "github", repo: `example/${MARKET}` },
      installLocation: join(claudeDir, "plugins", "marketplaces", MARKET),
      lastUpdated: "2026-11-01T00:00:00.000Z",
      autoUpdate: true,
    },
  });
  writeJson(join(install, ".claude-plugin", "plugin.json"), {
    name: PLUGIN,
    version: PLUGIN_VERSION,
    description: "Lints a change before review.",
  });
  writeText(
    join(install, "agents", "linter.md"),
    "---\nname: linter\ndescription: Checks a change against the house style.\ntools: Read, Grep\nmodel: haiku\n---\nLint it.\n",
  );

  // The project layer, as a git repo with one commit, so .claude/settings.json is tracked.
  const projectFile = join(project, ".claude", "settings.json");
  const localFile = join(project, ".claude", "settings.local.json");
  writeJson(projectFile, { effortLevel: "medium" });
  writeText(
    join(project, ".claude", "agents", "reviewer.md"),
    "---\nname: reviewer\ndescription: Reviews a change for the owner.\nmodel: sonnet\n---\nReview it.\n",
  );
  writeText(join(project, ".gitignore"), ".claude/settings.local.json\n");
  writeText(join(project, "README.md"), "# Tidewater reporting\n");
  git(project, ["init", "-q", "-b", "main"]);
  git(project, ["add", ".gitignore", "README.md", ".claude/settings.json", ".claude/agents"]);
  git(project, ["commit", "-q", "-m", "Start Tidewater reporting"]);
  if (options.local !== false) {
    writeJson(localFile, { env: { CLAUDE_CODE_EFFORT_LEVEL: "xhigh" } });
  }

  // No sessions were ever recorded, but the first ingest reads the folder where they would be and
  // fails with config_dir_missing without it. The server only reads there, so the fixture makes it.
  mkdirSync(join(claudeDir, "projects"));

  // The project list the server reads from the Claude folder.
  writeJson(join(claudeDir, "routing-dashboard.json"), {
    projects: [{ name: PROJECT_NAME, path: project }],
    plan: "subscription",
  });

  return {
    root,
    home,
    claudeDir,
    dataDir: join(root, "data"),
    project,
    userLink,
    userReal,
    projectFile,
    localFile,
    hasLocal: options.local !== false,
    outsideFile,
    cleanup: () => {
      rmSync(root, { recursive: true, force: true });
      rmSync(outsideRoot, { recursive: true, force: true });
    },
  };
}

export interface StartM6 {
  /** Pass --allow-edits. Default true. */
  edits?: boolean;
  /** Bind this port, for a restart on the same address. */
  port?: number;
}

/** Starts the real server on the fixture. The same data folder and HOME serve a restart. */
export function startM6Server(fx: M6Fixture, options: StartM6 = {}): Promise<Server> {
  return startServer({
    fixture: null,
    dataDir: fx.dataDir,
    homeDir: fx.home,
    ...(options.port !== undefined ? { port: options.port } : {}),
    args: [
      "--claude-dir",
      fx.claudeDir,
      "--project-dir",
      fx.project,
      "--no-price-fetch",
      ...(options.edits === false ? [] : ["--allow-edits"]),
    ],
  });
}

/** Starts the server and waits for its first ingest, so the first page load is not first run. */
export async function startReady(fx: M6Fixture, options: StartM6 = {}): Promise<Server> {
  const server = await startM6Server(fx, options);
  try {
    await waitForIngest(await openSession(server));
  } catch (error) {
    await server.stop();
    throw error;
  }
  return server;
}

// ---------------------------------------------------------------------------------------------
// Seeding. Real saves through the API, as the page makes them.
// ---------------------------------------------------------------------------------------------

type Scope = "user" | "project" | "local";

export interface Session {
  server: Server;
  readKey: string;
  /** Null on a server with editing off, which hands out no edit keys. */
  editKey: string | null;
}

/** Swaps a fresh code for keys, as the page does on load. */
export async function openSession(server: Server): Promise<Session> {
  const code = await server.mint(PROJECT_KEY);
  const res = await fetch(`${server.baseURL}/api/access/swap`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: server.baseURL },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) throw new Error(`swap answered ${String(res.status)}`);
  const body = (await res.json()) as { read_key: string; edit_keys: Record<string, string> };
  return { server, readKey: body.read_key, editKey: body.edit_keys[PROJECT_KEY] ?? null };
}

async function call(
  session: Session,
  method: "GET" | "POST",
  path: string,
  body?: unknown,
): Promise<{ status: number; body: Record<string, unknown> }> {
  const headers: Record<string, string> = {
    "X-Bartab-Key": session.readKey,
    Origin: session.server.baseURL,
  };
  if (method === "POST") {
    headers["Content-Type"] = "application/json";
    if (session.editKey === null) throw new Error("this server handed out no edit key");
    headers["X-Bartab-Edit"] = session.editKey;
  }
  const res = await fetch(`${session.server.baseURL}${path}`, {
    method,
    headers,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return { status: res.status, body: (await res.json()) as Record<string, unknown> };
}

/** Waits until the first ingest of the made-up Claude folder is done, so no page shows first run. */
export async function waitForIngest(session: Session): Promise<void> {
  let last = "";
  for (let tries = 0; tries < 60; tries++) {
    const app = await call(session, "GET", `/api/app?project=${PROJECT_KEY}`);
    const ingest = app.body.ingest as { state?: string } | undefined;
    if (ingest?.state === "done") return;
    last = JSON.stringify(app.body.ingest);
    await new Promise((done) => {
      setTimeout(done, 500);
    });
  }
  throw new Error("the first ingest did not finish in 30 s " + last);
}

let counter = 0;

function requestId(): string {
  counter += 1;
  return `m6-shots-${String(Date.now())}-${String(counter)}`;
}

/** One preview then one save of a settings field. Returns the new row's id. */
export async function saveField(
  session: Session,
  scope: Scope,
  field: "model" | "effortLevel" | "maxEffortLevel" | "autoCompactWindow",
  value: string | number,
): Promise<string> {
  const pick = { project: PROJECT_KEY, op: "set", scope, field, value };
  const preview = await call(session, "POST", "/api/edit/preview", { ...pick, seq: 1 });
  if (preview.status !== 200) {
    throw new Error(`preview of ${scope} ${field} answered ${String(preview.status)}`);
  }
  const version = String(preview.body.version);
  const saved = await call(session, "POST", "/api/edit/save", {
    ...pick,
    seq: 1,
    version,
    request_id: requestId(),
  });
  if (saved.status !== 200) {
    throw new Error(
      `save of ${scope} ${field} answered ${String(saved.status)} ${JSON.stringify(saved.body).slice(0, 300)}`,
    );
  }
  return String(saved.body.row_id);
}

/** Undoes a row. The row must be the newest of its file and unchanged since. */
export async function undoRow(session: Session, rowId: string): Promise<void> {
  const done = await call(session, "POST", "/api/edit/undo", {
    project: PROJECT_KEY,
    row_id: rowId,
    request_id: requestId(),
    anyway: false,
  });
  if (done.status !== 200) throw new Error(`undo answered ${String(done.status)}`);
}

function sleep(ms: number): Promise<void> {
  return new Promise((done) => {
    setTimeout(done, ms);
  });
}

/**
 * The server rechecks a save at 2 s and 10 s, and each recheck judges the file as it is then. So a
 * row keeps its outcome only when nothing else changes its file until after the second one.
 */
export async function waitForRechecks(): Promise<void> {
  await sleep(11_000);
}

function readJson(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
}

/** Another program's change to a settings file, right now. */
export function rewriteJson(path: string, change: (now: Record<string, unknown>) => void): void {
  const now = readJson(path);
  change(now);
  writeJson(path, now);
}

/**
 * Fills Changes with rows in every undo state and recheck outcome that real saves can make. The
 * fixture must be built with `local: false`. Rows, oldest first:
 *
 *   project  A  Effort medium to low, confirmed, then not the newest (not_newest)
 *   project  E  Effort low to high, then another program kept it and added a key (overwritten, kept)
 *   project  F  Effort high to low, then another program removed it and added includeCoAuthoredBy
 *                (overwritten, lost), changed_since, so Undo anyway removes that added line
 *   user     U1 Effort xhigh to high through the link, confirmed, undone (and its undo row)
 *   user     U2 Effort xhigh to medium through the link, confirmed, can_undo
 *   local    C  Effort set in a file that did not exist, confirmed, deletes_file
 *
 * The checking outcome lasts 2 s on a real save, so the page spec marks one row as checking in the
 * history answer it draws from (see `markChecking` in the spec).
 */
export async function seedHistory(server: Server, fx: M6Fixture): Promise<void> {
  const session = await openSession(server);
  await waitForIngest(session);

  // The three files are independent, so their chains run side by side. They start 1.5 s apart,
  // because two saves that make their backup folders in the same moment can fail.
  await Promise.all([
    (async () => {
      await saveField(session, "project", "effortLevel", "low");
      await waitForRechecks();
      await saveField(session, "project", "effortLevel", "high");
      rewriteJson(fx.projectFile, (now) => {
        now.permissions = { allow: ["Read"] };
      });
      await waitForRechecks();
      await saveField(session, "project", "effortLevel", "low");
      rewriteJson(fx.projectFile, (now) => {
        delete now.effortLevel;
        now.includeCoAuthoredBy = false;
      });
      await waitForRechecks();
    })(),
    (async () => {
      await sleep(3000);
      const first = await saveField(session, "user", "effortLevel", "high");
      await waitForRechecks();
      await undoRow(session, first);
      await waitForRechecks();
      await saveField(session, "user", "effortLevel", "medium");
      await waitForRechecks();
    })(),
    (async () => {
      await sleep(1500);
      await saveField(session, "local", "effortLevel", "high");
      await waitForRechecks();
    })(),
  ]);
}

/**
 * Waits until the server is done with every setup read it began for a page that has gone.
 *
 * A save makes the page ask for the setup again at once, so a spec that puts the files back right
 * after a save can land in the middle of that read, and a slow runner makes that likely. The server
 * keeps such a read out of its cache (SetupService.bundle in app/server/setup_answers.py), but the
 * page that asked still gets the old values. A read holds the project's lock from start to end, so
 * one more read that gets its answer means no earlier read is left running. Leave the page first,
 * so no new request arrives after this one.
 */
export async function waitForSetupRead(server: Server): Promise<void> {
  const session = await openSession(server);
  const answer = await call(session, "GET", `/api/setup/settings?project=${PROJECT_KEY}`);
  if (answer.status !== 200) throw new Error(`setup answered ${String(answer.status)}`);
}

/**
 * Puts the three settings files back as the builder wrote them, and the user link back on its
 * file, so a test can run the same flow once per width and theme. The ledger keeps its rows. Call
 * `waitForSetupRead` first when a page was open on the server a moment ago.
 */
export function restoreFiles(fx: M6Fixture): void {
  writeJson(fx.projectFile, { effortLevel: "medium" });
  if (fx.hasLocal) writeJson(fx.localFile, { env: { CLAUDE_CODE_EFFORT_LEVEL: "xhigh" } });
  rmSync(fx.userLink, { force: true });
  symlinkSync(fx.userReal, fx.userLink);
}

/** Points the user's settings.json at a file outside the home and the project (link_outside). */
export function linkUserOutside(fx: M6Fixture): void {
  rmSync(fx.userLink, { force: true });
  symlinkSync(fx.outsideFile, fx.userLink);
}
