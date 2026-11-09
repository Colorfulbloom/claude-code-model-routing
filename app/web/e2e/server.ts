/// <reference types="node" />
/*
 * Starts the real server (app/server/serve.py) on a port from 47000 to 47999 against the built app and a fresh data
 * folder, reads the launch line from fd 3, and stops it with SIGTERM. The `server` fixture gives
 * each test its own server, so codes and keys never leak between tests.
 */
import { spawn } from "node:child_process";
import type { ChildProcess } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { test as base } from "@playwright/test";

const appDir = resolve(import.meta.dirname, "..", "..");
const PYTHON = join(appDir, ".venv", "bin", "python");
const SERVE = join(appDir, "server", "serve.py");

/** The ports e2e servers may bind. */
const PORT_FIRST = 47000;
const PORT_COUNT = 1000;
let nextPort = Math.floor(Math.random() * PORT_COUNT);

function listens(port: number): Promise<boolean> {
  return new Promise((done) => {
    const probe = createServer();
    probe.once("error", () => {
      done(false);
    });
    probe.listen(port, "127.0.0.1", () => {
      probe.close(() => {
        done(true);
      });
    });
  });
}

/** A free port from 47000 to 47999. Workers start at different offsets, so they rarely meet. */
export async function freePort(): Promise<number> {
  for (let tries = 0; tries < PORT_COUNT; tries++) {
    const port = PORT_FIRST + ((nextPort + tries + process.pid) % PORT_COUNT);
    if (await listens(port)) {
      nextPort = (port - PORT_FIRST + 1) % PORT_COUNT;
      return port;
    }
  }
  throw new Error("no free port in 47000 to 47999");
}

export interface StartOptions {
  /** Reuse a data folder, for the restart check. A new one is made when omitted. */
  dataDir?: string;
  /** Bind this port, for the restart check. 0 or none picks a free one from 47000 to 47999. */
  port?: number;
  /** The fixture scenario. null leaves --fixture off, for a server that reads the store. */
  fixture?: string | null;
  /** More serve.py arguments, such as --demo. */
  args?: string[];
}

export interface Server {
  baseURL: string;
  port: number;
  /** The first link's code, from the launch line. */
  code: string;
  instance: string;
  pid: number;
  dataDir: string;
  mintSecret: string;
  /** Asks the running server for a fresh single-use code. */
  mint: (project?: string | null) => Promise<string>;
  /** SIGTERM, then waits for the process to exit. */
  stop: () => Promise<void>;
}

interface LaunchLine {
  port: number;
  pid: number;
  instance: string;
  code: string;
  project: string | null;
}

function readLaunchLine(child: ChildProcess, stderr: () => string): Promise<LaunchLine> {
  return new Promise((done, fail) => {
    const fd3 = child.stdio[3];
    if (fd3 === null || fd3 === undefined || !("on" in fd3)) {
      fail(new Error("no launch pipe"));
      return;
    }
    let text = "";
    const timer = setTimeout(() => {
      fail(new Error(`no launch line in 30 s\n${stderr()}`));
    }, 30_000);
    fd3.on("data", (chunk: Buffer) => {
      text += chunk.toString("utf8");
      const end = text.indexOf("\n");
      if (end >= 0) {
        clearTimeout(timer);
        done(JSON.parse(text.slice(0, end)) as LaunchLine);
      }
    });
    child.once("exit", (code) => {
      clearTimeout(timer);
      fail(new Error(`server exited with ${String(code)} before it was ready\n${stderr()}`));
    });
  });
}

export async function startServer(options: StartOptions = {}): Promise<Server> {
  const dist = process.env.BARTAB_E2E_DIST;
  if (dist === undefined)
    throw new Error("BARTAB_E2E_DIST is not set, the global setup did not run");
  const dataDir = options.dataDir ?? mkdtempSync(join(tmpdir(), "bartab-e2e-data-"));
  const args = [
    SERVE,
    "--port",
    String(options.port === undefined || options.port === 0 ? await freePort() : options.port),
    "--dist",
    dist,
    "--data",
    dataDir,
    ...(options.fixture === null ? [] : ["--fixture", options.fixture ?? "demo"]),
    "--launch-fd",
    "3",
    "--idle-exit-minutes",
    "0",
    ...(options.args ?? []),
  ];
  const child = spawn(PYTHON, args, {
    cwd: join(appDir, "server"),
    stdio: ["ignore", "ignore", "pipe", "pipe"],
  });
  let log = "";
  child.stderr?.on("data", (chunk: Buffer) => {
    log += chunk.toString("utf8");
  });
  const exited = new Promise<void>((done) => {
    child.once("exit", () => {
      done();
    });
  });
  let launch: LaunchLine;
  try {
    launch = await readLaunchLine(child, () => log);
  } catch (err) {
    child.kill("SIGKILL");
    throw err;
  }
  const info = JSON.parse(readFileSync(join(dataDir, "server.json"), "utf8")) as {
    mint_secret: string;
  };
  const baseURL = `http://127.0.0.1:${String(launch.port)}`;
  const mint = async (project: string | null = null): Promise<string> => {
    const res = await fetch(`${baseURL}/api/access/mint`, {
      method: "POST",
      headers: {
        Host: `127.0.0.1:${String(launch.port)}`,
        "Content-Type": "application/json",
        "X-Bartab-Mint": info.mint_secret,
      },
      body: JSON.stringify({ project }),
    });
    if (!res.ok) throw new Error(`mint answered ${String(res.status)}`);
    return ((await res.json()) as { code: string }).code;
  };
  return {
    baseURL,
    port: launch.port,
    code: launch.code,
    instance: launch.instance,
    pid: launch.pid,
    dataDir,
    mintSecret: info.mint_secret,
    mint,
    stop: async () => {
      if (child.exitCode === null && child.signalCode === null) child.kill("SIGTERM");
      await exited;
    },
  };
}

/** The flow scenarios `serve.py --flow` builds (tests/fixtures/live_flow). */
export type FlowScenario = "busy" | "many" | "unlinked" | "empty";

export const test = base.extend<{ server: Server; fixture: string; flow: FlowScenario | null }>({
  fixture: ["demo", { option: true }],
  // A scenario name starts the server in flow mode with the test clock, in place of a fixture.
  flow: [null, { option: true }],
  server: async ({ fixture, flow }, run) => {
    const server = await startServer(
      flow === null
        ? { fixture }
        : { fixture: null, args: ["--flow", flow, "--test-clock", "--no-price-fetch"] },
    );
    try {
      await run(server);
    } finally {
      await server.stop();
      rmSync(server.dataDir, { recursive: true, force: true });
    }
  },
});

/**
 * One server per worker, for specs that only read. Each test mints its own code, so tabs never
 * share keys, but the server's state (the demo fixture) is shared.
 */
export const readOnlyTest = base.extend<object, { shared: Server }>({
  shared: [
    // eslint-disable-next-line no-empty-pattern
    async ({}, run) => {
      const server = await startServer();
      try {
        await run(server);
      } finally {
        await server.stop();
        rmSync(server.dataDir, { recursive: true, force: true });
      }
    },
    { scope: "worker" },
  ],
});

export { expect } from "@playwright/test";
