/*
 * A fake server for the Review page tests. It wraps the app fake (projects, prices, app info) and
 * answers the Review routes from handlers a test sets. A handler gets the request URL and returns
 * the answer, an HTTP status number to fail with, or a promise of either. The paths it was asked
 * for stay in `server.calls`, like the rest.
 */
import type { AgentList, CostChart, ModelList, SessionList, Summary } from "@/api/types";
import { agentList, costChart, modelList, sessionList, summary } from "@/test/review";
import { fakeServer } from "@/test/server";
import type { FakeServer } from "@/test/server";

type Reply<T> = T | number | Promise<T | number>;

export interface ReviewHandlers {
  summary: (url: URL) => Reply<Summary>;
  chart: (url: URL) => Reply<CostChart>;
  sessions: (url: URL) => Reply<SessionList>;
  agents: (url: URL) => Reply<AgentList>;
  models: (url: URL) => Reply<ModelList>;
}

const ranged = (url: URL) => url.searchParams.get("range") as Summary["range"];

export function reviewServer(over: Partial<ReviewHandlers> = {}): FakeServer & {
  handlers: ReviewHandlers;
} {
  const handlers: ReviewHandlers = {
    summary: (url) => summary({ range: ranged(url) }),
    chart: (url) => costChart({ range: ranged(url) }),
    sessions: (url) => sessionList([], { range: ranged(url) }),
    agents: (url) => agentList({ range: ranged(url) }),
    models: (url) => modelList({ range: ranged(url) }),
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
    if (url.pathname === "/api/summary") {
      server.calls.push(path);
      return answer(handlers.summary(url));
    }
    if (url.pathname === "/api/cost-chart") {
      server.calls.push(path);
      return answer(handlers.chart(url));
    }
    if (url.pathname === "/api/sessions") {
      server.calls.push(path);
      return answer(handlers.sessions(url));
    }
    if (url.pathname === "/api/agents") {
      server.calls.push(path);
      return answer(handlers.agents(url));
    }
    if (url.pathname === "/api/models") {
      server.calls.push(path);
      return answer(handlers.models(url));
    }
    return base(input, init);
  };
  return Object.assign(server, { handlers });
}

/** A promise that never settles, for the loading state. */
export const never = <T>(): Promise<T> => new Promise<T>(() => undefined);
