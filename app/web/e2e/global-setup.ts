/// <reference types="node" />
/*
 * Builds the app and the component sheet into a temp folder outside the repo, then serves the
 * sheet from a small static server. The folder and the sheet URL reach the workers through the
 * environment. The returned function stops the server and removes the folder.
 *
 * The sheet server rewrites sheet.html per request with a fresh nonce, a csp-nonce meta tag and the
 * production CSP header, like the real server's index rewrite, so the sheet runs under that policy.
 */
import { randomBytes } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { extname, join, normalize, resolve, sep } from "node:path";
import { build } from "vite";
import { addNonce, expectedCsp } from "./policy";

const webDir = resolve(import.meta.dirname, "..");

const TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".json": "application/json",
  ".png": "image/png",
};

interface SheetServer {
  url: string;
  stop: () => Promise<void>;
}

async function startSheetServer(root: string): Promise<SheetServer> {
  const server = createServer((req, res) => {
    void (async () => {
      const path = new URL(req.url ?? "/", "http://127.0.0.1").pathname;
      if (path === "/favicon.ico") {
        res.writeHead(204).end();
        return;
      }
      const isPage = path === "/" || path === "/sheet.html";
      const file = normalize(join(root, isPage ? "sheet.html" : path));
      if (!file.startsWith(root + sep)) {
        res.writeHead(403).end();
        return;
      }
      try {
        const body = await readFile(file);
        const type = TYPES[extname(file)] ?? "application/octet-stream";
        if (isPage) {
          const nonce = randomBytes(16).toString("base64url");
          res.writeHead(200, {
            "Content-Type": type,
            "Content-Security-Policy": expectedCsp(nonce),
            "Cache-Control": "no-store",
          });
          res.end(addNonce(body.toString("utf8"), nonce));
        } else {
          res.writeHead(200, { "Content-Type": type }).end(body);
        }
      } catch {
        res.writeHead(404).end();
      }
    })();
  });
  await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
  const { port } = server.address() as AddressInfo;
  return {
    url: `http://127.0.0.1:${port}/`,
    stop: () =>
      new Promise<void>((done) => {
        server.closeAllConnections();
        server.close(() => {
          done();
        });
      }),
  };
}

async function buildInto(mode: string, outDir: string): Promise<void> {
  await build({
    root: webDir,
    mode,
    logLevel: "warn",
    build: { outDir, emptyOutDir: true },
  });
}

export default async function globalSetup(): Promise<() => Promise<void>> {
  const tmp = mkdtempSync(join(tmpdir(), "bartab-e2e-"));
  const dist = join(tmp, "dist");
  const distSheet = join(tmp, "dist-sheet");
  await buildInto("production", dist);
  await buildInto("sheet", distSheet);
  const sheet = await startSheetServer(distSheet);
  process.env.BARTAB_E2E_TMP = tmp;
  process.env.BARTAB_E2E_DIST = dist;
  process.env.BARTAB_E2E_SHEET_URL = sheet.url;
  return async () => {
    await sheet.stop();
    rmSync(tmp, { recursive: true, force: true });
  };
}
