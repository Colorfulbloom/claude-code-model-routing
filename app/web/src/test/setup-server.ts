/*
 * A fake server for the setup page tests. It wraps the app fake (projects, prices, app info) and
 * answers /api/setup, /api/setup/{part} and /api/problems from handlers a test sets. A handler gets
 * the request URL and returns the answer, an HTTP status number to fail with, or a promise of either.
 * The paths it was asked for stay in `server.calls`.
 */
import type { ProblemList, SetupMap, SetupPart, SetupPartAnswer } from "@/api/types";
import { fakeServer } from "@/test/server";
import type { FakeServer } from "@/test/server";
import { partAnswer, problemList, setupMap } from "@/test/setup-fixtures";

type Reply<T> = T | number | Promise<T | number>;

export interface SetupHandlers {
  map: (url: URL) => Reply<SetupMap>;
  part: (part: SetupPart, url: URL) => Reply<SetupPartAnswer>;
  problems: (url: URL) => Reply<ProblemList>;
}

export function setupServer(over: Partial<SetupHandlers> = {}): FakeServer & {
  handlers: SetupHandlers;
} {
  const handlers: SetupHandlers = {
    map: () => setupMap([]),
    part: (part) => partAnswer(part, []),
    problems: () => problemList(),
    ...over,
  };
  const server = fakeServer();
  const base = server.fetch;
  async function answer<T>(reply: Reply<T>): Promise<Response> {
    const value = await reply;
    if (typeof value === "number") {
      return new Response(JSON.stringify({ code: "unexpected", path: null }), { status: value });
    }
    return new Response(JSON.stringify(value));
  }
  server.fetch = (input, init) => {
    const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(path, "http://x");
    if (url.pathname === "/api/setup") {
      server.calls.push(path);
      return answer(handlers.map(url));
    }
    if (url.pathname.startsWith("/api/setup/")) {
      server.calls.push(path);
      return answer(handlers.part(url.pathname.slice("/api/setup/".length) as SetupPart, url));
    }
    if (url.pathname === "/api/problems") {
      server.calls.push(path);
      return answer(handlers.problems(url));
    }
    return base(input, init);
  };
  return Object.assign(server, { handlers });
}
