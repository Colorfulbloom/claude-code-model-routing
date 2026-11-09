import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelCheckRow, Timeline } from "@/api/types";
import { postStatus } from "@/app/harness";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { appInfo, fakeServer, liveSessions, pricesInfo } from "@/test/server";
import type { FakeServer } from "@/test/server";
import { bucket, liveSession, NOW, run, sessionOf, START, state, timeline } from "@/test/timelines";

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("missing");
  return value;
}

afterEach(() => {
  cleanup();
  resetViewport();
  vi.useRealTimers();
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
});

beforeEach(() => {
  postStatus("");
});

const at = (seconds: number): string => new Date(Date.parse(NOW) + seconds * 1000).toISOString();

/** A server with one running session s1 in builder and its timeline. */
function serverWith(over: Partial<Timeline> = {}, init: Partial<FakeServer> = {}): FakeServer {
  const answer = timeline(over);
  const server = fakeServer({
    live: liveSessions({ sessions: [liveSession("s1")] }),
    timelines: { s1: answer },
  });
  Object.assign(server, init);
  return server;
}

const requested = (server: FakeServer, part: string): number =>
  server.calls.filter((path) => path.includes(part)).length;

describe("first load", () => {
  it("shows bones with one spoken line, the Live heading and no session yet", async () => {
    const server = fakeServer({ live: liveSessions({ sessions: [liveSession("s1")] }) });
    const base = server.fetch;
    // the session list answers, the timeline never does
    server.fetch = (input, init) =>
      (typeof input === "string" ? input : "").includes("/timeline")
        ? new Promise<Response>(() => undefined)
        : base(input, init);
    await mount("#/p/builder/live", { server });
    expect(await screen.findByRole("heading", { level: 1, name: "Live" })).toBeInTheDocument();
    expect(screen.getByText("Loading this session")).toBeInTheDocument();
    expect(document.querySelector("[aria-busy='true']")).not.toBeNull();
  });
});

describe("session choice", () => {
  it("opens the newest running session of the project and writes it into the URL with replace", async () => {
    const server = serverWith();
    const { router } = await mount("#/p/builder/live", { server });
    expect(
      await screen.findByRole("heading", { level: 1, name: "feature/quarter-close" }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(router.state.location.search).toBe("?session=s1");
    });
    expect(router.state.historyAction).toBe("REPLACE");
  });

  it("moves focus to the h1 and keeps the route status at Live", async () => {
    const server = serverWith();
    await mount("#/p/builder/live?session=s1", { server });
    const heading = await screen.findByRole("heading", { level: 1, name: "feature/quarter-close" });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
    expect(document.querySelector("div.sr-only[role='status']")).toHaveTextContent("Live");
  });

  it("stays on the opened session when a newer one starts, and offers Switch", async () => {
    const server = serverWith();
    const user = userEvent.setup();
    const { router } = await mount("#/p/builder/live?session=s1", { server });
    await screen.findByRole("heading", { level: 1, name: "feature/quarter-close" });
    expect(screen.queryByText(/A new session started/)).toBeNull();
    server.live = liveSessions({
      etag: "sessions-2",
      sessions: [
        liveSession("s2", {
          branch: "feature/invoice-export",
          started: at(120),
          last_request: at(130),
        }),
        liveSession("s1"),
      ],
    });
    server.timelines.s2 = timeline({
      session: sessionOf({ id: "s2", branch: "feature/invoice-export", started: at(120) }),
    });
    expect(
      await screen.findByText(/A new session started on feature\/invoice-export at/, undefined, {
        timeout: 7000,
      }),
    ).toBeInTheDocument();
    // The notice is not a second live region. The one polite region says it.
    const notice = document.querySelector(".live-notice");
    expect(notice).not.toBeNull();
    expect(notice).not.toHaveAttribute("role");
    expect(document.querySelectorAll("[role='status']")).toHaveLength(1);
    expect(document.querySelector("div.sr-only[role='status']")).toHaveTextContent(
      /A new session started on feature\/invoice-export at/,
    );
    expect(router.state.location.search).toBe("?session=s1");
    await user.click(screen.getByRole("button", { name: "Switch to it" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "feature/invoice-export" }),
    ).toBeInTheDocument();
    expect(router.state.location.search).toBe("?session=s2");
    // the notice is for sessions that start after the page opened, so it is gone on s2
    expect(screen.queryByText(/A new session started/)).toBeNull();
  }, 15_000);

  it("uses the no-branch words for a session with no branch", async () => {
    const server = serverWith({ session: sessionOf({ branch: null }) });
    await mount("#/p/builder/live?session=s1", { server });
    expect(
      await screen.findByRole("heading", { level: 1, name: "No git branch" }),
    ).toBeInTheDocument();
  });
});

describe("a working session", () => {
  it("draws the header, tiles, lanes, model check and latest requests", async () => {
    const server = serverWith({
      model_check: {
        in_effect_count: 2,
        rows: [
          {
            agent: "judge",
            mismatched_runs: 0,
            params: {
              setting: "effort",
              value: "high",
              expected: "medium",
              cap_file: "Project local",
              cap_line: "3",
            },
            ran: { effort: "medium", mixed: false, model: "claude-opus-5-5" },
            reason_code: "lowered_by_cap",
            runs: 1,
            set: {
              effort: { file: ".claude/agents/judge.md", line: 5, scope: "agent", value: "high" },
              model: null,
            },
            status: "lowered",
          } satisfies ModelCheckRow,
          ...["a", "b"].map((agent): ModelCheckRow => ({
            agent,
            mismatched_runs: 0,
            params: {},
            ran: { effort: "high", mixed: false, model: "claude-opus-5-5" },
            reason_code: "in_effect",
            runs: 1,
            set: { effort: null, model: null },
            status: "in_effect",
          })),
        ],
      },
    });
    await mount("#/p/builder/live?session=s1", { server });
    const heading = await screen.findByRole("heading", { level: 1, name: "feature/quarter-close" });
    const header = heading.closest("header");
    expect(header).not.toBeNull();
    expect(within(need(header)).getByText("Working")).toBeInTheDocument();
    expect(screen.getByText(/Builder, started .*, 30 minutes so far/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
    // no time while live
    expect(screen.queryByText(/Paused at|Ended at|Last reached/)).toBeNull();
    // tiles
    expect(screen.getByText("Spent so far")).toBeInTheDocument();
    expect(screen.getByText("$8.28")).toBeInTheDocument();
    expect(screen.getByText("$0.44 in the last minute")).toBeInTheDocument();
    expect(screen.getByText("151K")).toBeInTheDocument();
    expect(screen.getByText("78%")).toBeInTheDocument();
    expect(screen.getByText("0 finished, 2 runs in all")).toBeInTheDocument();
    // Who is working
    const lanes = screen.getByRole("list", { name: "Who is working" });
    expect(within(lanes).getByText("Main session")).toBeInTheDocument();
    expect(within(lanes).getByText("deep-reasoner")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "New tokens per minute" })).toBeInTheDocument();
    // Model check
    const check = screen.getByRole("region", { name: "Model check" });
    expect(within(check).getByText("Lowered")).toBeInTheDocument();
    expect(within(check).getByText("judge ran at medium")).toBeInTheDocument();
    expect(
      within(check).getByText("The other 2 agents ran as their files set."),
    ).toBeInTheDocument();
    expect(within(check).queryByRole("link")).toBeNull();
    // Latest requests
    const requests = screen.getByRole("region", { name: "Latest requests" });
    expect(within(requests).getAllByRole("row")).toHaveLength(6);
    expect(within(requests).getByText(/Prices as of November 8\./)).toBeInTheDocument();
    expect(within(requests).getByText(/On a subscription you pay a flat fee/)).toBeInTheDocument();
    expect(within(requests).queryByText(/disagree/)).toBeNull();
  });

  it("adds the price disagreement line under Prices as of", async () => {
    const server = serverWith(
      { prices: { as_of: "2026-11-08", source: "litellm", cross_check_state: "disagree" } },
      { prices: pricesInfo({ cross_check: { state: "disagree", models: ["claude-opus-5-5"] } }) },
    );
    await mount("#/p/builder/live?session=s1", { server });
    expect(
      await screen.findByText("Two price sources disagree on Opus 5.5, so its costs may be off."),
    ).toBeInTheDocument();
  });

  it("shows an idle session with the Idle word", async () => {
    const server = serverWith({ session: sessionOf({ state: "idle", active: false }) });
    await mount("#/p/builder/live?session=s1", { server });
    const heading = await screen.findByRole("heading", { level: 1, name: "feature/quarter-close" });
    expect(within(need(heading.closest("header"))).getByText("Idle")).toBeInTheDocument();
  });

  it("reads the unpriced forms in the tile and the lanes", async () => {
    const base = timeline();
    const server = serverWith({
      totals: { ...base.totals, unpriced: { requests: 12, models: ["Fable 5.1"] } },
      runs: [
        run("main", { cost: 3.1 }),
        run("deep-reasoner", {
          dispatch_order: 1,
          cost: 0.97,
          unpriced: { requests: 3, models: ["Fable 5.1"] },
        }),
        run("tw", {
          agent: "tech-writer",
          dispatch_order: 2,
          cost: null,
          unpriced: { requests: 4, models: ["Fable 5.1"] },
        }),
      ],
    });
    await mount("#/p/builder/live?session=s1", { server });
    expect(await screen.findByText("12 requests have no price")).toBeInTheDocument();
    expect(screen.getByText("at least")).toBeInTheDocument();
    expect(screen.getByText("No price for Fable 5.1")).toBeInTheDocument();
  });
});

describe("an ended session", () => {
  const ended = (): Partial<Timeline> => ({
    session: sessionOf({
      state: "ended",
      running: false,
      active: false,
      ended_at: at(-600),
      last_request: at(-600),
    }),
    last_minute: null,
  });

  it("stays on screen with Ended at, no Pause and the whole-session tiles", async () => {
    const server = serverWith(ended(), {
      live: liveSessions({ sessions: [], latest_ended: null }),
    });
    await mount("#/p/builder/live?session=s1", { server });
    const heading = await screen.findByRole("heading", { level: 1, name: "feature/quarter-close" });
    const header = need(heading.closest("header"));
    expect(within(header).getByText("Ended")).toBeInTheDocument();
    expect(within(header).getByText(/^Ended at /)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
    expect(screen.getAllByText(/in all$/).length).toBeGreaterThan(0);
    expect(screen.getByText("Spent in all")).toBeInTheDocument();
    expect(screen.getAllByText("Whole session")).toHaveLength(3);
  });

  it("shows every run as Finished with its run time, main included", async () => {
    const server = serverWith({
      ...ended(),
      runs: [
        run("main", { state: "idle", last_request: at(-600) }),
        run("lead", { agent: "deep-reasoner", dispatch_order: 1, state: "idle" }),
      ],
    });
    await mount("#/p/builder/live?session=s1", { server });
    const list = await screen.findByRole("list", { name: "Who is working" });
    expect(within(list).getAllByText("Finished")).toHaveLength(2);
    expect(within(list).queryByText("Idle")).toBeNull();
    expect(within(list).queryByText(/Last request/)).toBeNull();
  });

  it("lists the current session even when it is not in the running list", async () => {
    const server = serverWith(ended(), { live: liveSessions({ sessions: [] }) });
    const user = userEvent.setup();
    await mount("#/p/builder/live?session=s1", { server });
    const button = await screen.findByRole("button", { name: /Session\s*feature\/quarter-close/ });
    await user.click(button);
    const dialog = await screen.findByRole("dialog", { name: "Sessions" });
    expect(within(dialog).getByText("This project")).toBeInTheDocument();
    expect(within(dialog).getByRole("option", { name: /feature\/quarter-close/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});

describe("the fold on a busy lead", () => {
  const minutesAgo = (n: number): string => new Date(Date.parse(NOW) - n * 60_000).toISOString();
  const worker = (id: string, order: number, ago: number) =>
    run(id, {
      agent: "fast-worker",
      label_n: order,
      parent: "lead",
      dispatch_order: order,
      state: "finished",
      first_request: minutesAgo(ago + 3),
      last_request: minutesAgo(ago),
      states: [state(0, "working"), { at: minutesAgo(ago), state: "finished" }],
      segments: [{ start: minutesAgo(ago + 3), end: minutesAgo(ago) }],
    });
  const busy = (): Partial<Timeline> => ({
    runs: [
      run("main"),
      run("lead", { agent: "deep-reasoner", dispatch_order: 1 }),
      worker("w1", 2, 20),
      worker("w2", 3, 18),
      worker("w3", 4, 15),
      worker("w4", 5, 12),
      run("w5", { agent: "fast-worker", label_n: 5, parent: "lead", dispatch_order: 6 }),
    ],
  });

  it("Show opens the folded rows, the button reads Hide, and Hide closes them again", async () => {
    const server = serverWith(busy());
    const user = userEvent.setup();
    await mount("#/p/builder/live?session=s1", { server });
    const show = await screen.findByRole("button", { name: "Show" });
    expect(show).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("fast-worker 1")).toBeNull();
    await user.click(show);
    const hide = await screen.findByRole("button", { name: "Hide" });
    expect(hide).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("fast-worker 2")).toBeInTheDocument();
    expect(screen.getByText("fast-worker 4")).toBeInTheDocument();
    await user.click(hide);
    expect(await screen.findByRole("button", { name: "Show" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByText("fast-worker 2")).toBeNull();
  });

  it("keeps the fold open across the page's next answers", async () => {
    const server = serverWith(busy());
    const user = userEvent.setup();
    await mount("#/p/builder/live?session=s1", { server });
    await user.click(await screen.findByRole("button", { name: "Show" }));
    await screen.findByRole("button", { name: "Hide" });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 6000));
    });
    expect(screen.getByRole("button", { name: "Hide" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("fast-worker 2")).toBeInTheDocument();
  }, 15_000);
});

describe("the Session Select", () => {
  it("groups this project and other projects, links to all sessions and goes to another project's Live", async () => {
    const server = serverWith(
      {},
      {
        live: liveSessions({
          sessions: [
            liveSession("s1"),
            liveSession("s9", {
              project: "driftwood",
              project_name: "Driftwood",
              branch: "main",
              state: "idle",
            }),
          ],
        }),
      },
    );
    const user = userEvent.setup();
    const { router } = await mount("#/p/builder/live?session=s1", { server });
    await user.click(
      await screen.findByRole("button", { name: /^Session\s*feature\/quarter-close/ }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Sessions" });
    expect(within(dialog).getByText("This project")).toBeInTheDocument();
    expect(within(dialog).getByText("Other projects")).toBeInTheDocument();
    const all = within(dialog).getByRole("link", { name: /See all sessions/ });
    expect(all).toHaveAttribute("href", "#/p/builder/review/sessions");
    await user.click(within(dialog).getByRole("option", { name: /main/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/p/driftwood/live");
    });
    expect(router.state.location.search).toBe("?session=s9");
  });

  it("names the button by its visible words", async () => {
    const server = serverWith();
    await mount("#/p/builder/live?session=s1", { server });
    const button = await screen.findByRole("button", { name: /^Session\s*feature\/quarter-close/ });
    expect(button).not.toHaveAttribute("aria-label");
    expect(button).toHaveTextContent(/^Session\s*feature\/quarter-close, /);
  });
});

describe("Pause", () => {
  it("stops polling, shows Paused at and Resume, says so politely, and resumes with a poll at once", async () => {
    const server = serverWith();
    const user = userEvent.setup();
    await mount("#/p/builder/live?session=s1", { server });
    await screen.findByRole("heading", { level: 1, name: "feature/quarter-close" });
    await user.click(screen.getByRole("button", { name: "Pause" }));
    expect(screen.getByRole("button", { name: "Resume" })).toBeInTheDocument();
    expect(screen.getByText(/^Paused at /)).toBeInTheDocument();
    expect(document.querySelector("div.sr-only[role='status']")).toHaveTextContent(
      "Updates paused",
    );
    const timelineCalls = requested(server, "/timeline");
    const listCalls = requested(server, "/live/sessions");
    await new Promise((done) => setTimeout(done, 2500));
    expect(requested(server, "/timeline")).toBe(timelineCalls);
    expect(requested(server, "/live/sessions")).toBe(listCalls);
    await user.click(screen.getByRole("button", { name: "Resume" }));
    expect(document.querySelector("div.sr-only[role='status']")).toHaveTextContent(
      "Updates resumed",
    );
    await waitFor(() => {
      expect(requested(server, "/timeline")).toBe(timelineCalls + 1);
    });
    expect(screen.queryByText(/^Paused at /)).toBeNull();
  }, 15_000);
});

describe("a hidden tab", () => {
  it("makes no request while hidden and polls at once when shown", async () => {
    const server = serverWith();
    await mount("#/p/builder/live?session=s1", { server });
    await screen.findByRole("heading", { level: 1, name: "feature/quarter-close" });
    const set = (value: "hidden" | "visible") => {
      Object.defineProperty(document, "visibilityState", { configurable: true, value });
      document.dispatchEvent(new Event("visibilitychange"));
    };
    act(() => {
      set("hidden");
    });
    const timelineCalls = requested(server, "/timeline");
    const listCalls = requested(server, "/live/sessions");
    await new Promise((done) => setTimeout(done, 2500));
    expect(requested(server, "/timeline")).toBe(timelineCalls);
    expect(requested(server, "/live/sessions")).toBe(listCalls);
    act(() => {
      set("visible");
    });
    await waitFor(() => {
      expect(requested(server, "/timeline")).toBe(timelineCalls + 1);
    });
    expect(requested(server, "/live/sessions")).toBe(listCalls + 1);
  }, 15_000);
});

describe("lost", () => {
  it("shows the finding with Try now and keeps the last numbers after three failed polls", async () => {
    const server = serverWith();
    const user = userEvent.setup();
    await mount("#/p/builder/live?session=s1", { server });
    await screen.findByRole("heading", { level: 1, name: "feature/quarter-close" });
    server.down = true;
    expect(
      await screen.findByText("Can't reach the Bar Tab server", undefined, { timeout: 8000 }),
    ).toBeInTheDocument();
    expect(screen.getByText(/^Last reached the server at /)).toBeInTheDocument();
    expect(
      screen.getByText(/These numbers are from .* Bar Tab tries again every 10 seconds\./),
    ).toBeInTheDocument();
    // the last good numbers stay
    expect(screen.getByText("$8.28")).toBeInTheDocument();
    server.down = false;
    await user.click(screen.getByRole("button", { name: "Try now" }));
    await waitFor(() => {
      expect(screen.queryByText("Can't reach the Bar Tab server")).toBeNull();
    });
  }, 20_000);
});

describe("session gone", () => {
  it("says the session isn't in the project and offers the running one", async () => {
    const server = fakeServer({ live: liveSessions({ sessions: [liveSession("s1")] }) });
    const user = userEvent.setup();
    const { router } = await mount("#/p/builder/live?session=nope", { server });
    expect(await screen.findByText("This session isn't in Builder")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Live" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The link names a session Bar Tab can't find in this project.",
    );
    expect(screen.getByRole("button", { name: /^Session\s*Pick a session/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See all sessions" })).toHaveAttribute(
      "href",
      "#/p/builder/review/sessions",
    );
    server.timelines.s1 = timeline();
    await user.click(screen.getByRole("button", { name: "Open the running session" }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("?session=s1");
    });
    expect(
      await screen.findByRole("heading", { level: 1, name: "feature/quarter-close" }),
    ).toBeInTheDocument();
  });

  it("offers no running session when none runs", async () => {
    await mount("#/p/builder/live?session=nope", { server: fakeServer() });
    await screen.findByText("This session isn't in Builder");
    expect(screen.queryByRole("button", { name: "Open the running session" })).toBeNull();
  });
});

describe("nothing running", () => {
  it("offers the last session and lists other projects' running sessions", async () => {
    const server = fakeServer({
      live: liveSessions({
        sessions: [
          liveSession("s7", {
            project: "driftwood",
            project_name: "Driftwood",
            branch: "fix/login",
            state: "working",
          }),
        ],
        latest_ended: {
          id: "s0",
          branch: "feature/old",
          started: START,
          last_request: NOW,
          requests: 12,
        },
      }),
      timelines: {
        s0: timeline({
          session: sessionOf({ id: "s0", branch: "feature/old", state: "ended", running: false }),
        }),
      },
    });
    const user = userEvent.setup();
    const { router } = await mount("#/p/builder/live", { server });
    expect(await screen.findByText("Nothing is running in Builder")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Live" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Session\s*None running/ })).toBeInTheDocument();
    expect(screen.getByText(/^feature\/old, ended /)).toBeInTheDocument();
    const other = screen.getByRole("region", { name: "Running in other projects" });
    const link = within(other).getByRole("link", { name: /fix\/login/ });
    expect(link).toHaveAttribute("href", "#/p/driftwood/live?session=s7");
    expect(router.state.location.search).toBe("");
    await user.click(screen.getByRole("button", { name: "Open the last session" }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("?session=s0");
    });
    expect(
      await screen.findByRole("heading", { level: 1, name: "feature/old" }),
    ).toBeInTheDocument();
  });

  it("leaves out the other-projects card when none runs", async () => {
    const server = fakeServer({
      live: liveSessions({
        latest_ended: { id: "s0", branch: null, started: START, last_request: NOW, requests: 1 },
      }),
    });
    await mount("#/p/builder/live", { server });
    await screen.findByText("Nothing is running in Builder");
    expect(screen.queryByText("Running in other projects")).toBeNull();
    expect(screen.getByText(/^No git branch, ended /)).toBeInTheDocument();
  });
});

describe("no sessions", () => {
  it("shows the first-use state with the command for the project folder", async () => {
    await mount("#/p/builder/live", { server: fakeServer() });
    expect(await screen.findByText("No sessions in Builder yet")).toBeInTheDocument();
    expect(screen.getByText("cd /work/builder && claude")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy command" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Session\s*None running/ })).toBeInTheDocument();
  });
});

describe("the demo mark", () => {
  it("shows in the sidebar and in the top bar unless the data is real", async () => {
    await mount("#/p/builder/live", { server: fakeServer({ app: appInfo({ mode: "flow" }) }) });
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(await within(nav).findByText("Demo data")).toBeInTheDocument();
    cleanup();
    await mount("#/p/builder/live", {
      width: 375,
      server: fakeServer({ app: appInfo({ mode: "demo" }) }),
    });
    expect(await screen.findByText("Demo data")).toBeInTheDocument();
    expect(document.querySelector(".top-bar")).toHaveTextContent("Demo data");
  });

  it("is left out on real data", async () => {
    await mount("#/p/builder/live", { server: fakeServer({ app: appInfo({ mode: "real" }) }) });
    await screen.findByRole("navigation", { name: "Main" });
    await screen.findByText("No sessions in Builder yet");
    expect(screen.queryByText("Demo data")).toBeNull();
  });
});

describe("announcements through the one polite region", () => {
  it("keeps one live region on the empty Live page", async () => {
    await mount("#/p/builder/live", { server: fakeServer({ app: appInfo({ mode: "real" }) }) });
    await screen.findByText("No sessions in Builder yet");
    expect(document.querySelectorAll("[role='status']")).toHaveLength(1);
  });

  it("says nothing for the first answer, then speaks a started and a finished run", async () => {
    const server = serverWith({ runs: [run("main")] });
    await mount("#/p/builder/live?session=s1", { server });
    await screen.findByRole("heading", { level: 1, name: "feature/quarter-close" });
    const region = document.querySelector("div.sr-only[role='status']");
    expect(region).toHaveTextContent("Live");
    const base = need(server.timelines.s1);
    server.timelines.s1 = {
      ...base,
      etag: "etag-b",
      server_time: at(2),
      runs: [run("main"), run("w1", { agent: "scout", dispatch_order: 1, parent: "main" })],
    };
    await waitFor(
      () => {
        expect(region).toHaveTextContent("scout started by Main session");
      },
      { timeout: 4000 },
    );
    server.timelines.s1 = {
      ...base,
      etag: "etag-c",
      server_time: at(70),
      runs: [
        run("main"),
        run("w1", {
          agent: "scout",
          dispatch_order: 1,
          parent: "main",
          state: "finished",
          states: [state(0, "finished")],
        }),
      ],
    };
    await waitFor(
      () => {
        expect(region).toHaveTextContent("scout finished");
      },
      { timeout: 4000 },
    );
  }, 15_000);
});

describe("narrow screens", () => {
  it("draws the same page at 375 with the project in the top bar", async () => {
    const server = serverWith({ buckets: [bucket(0), bucket(1)] });
    await mount("#/p/builder/live?session=s1", { width: 375, server });
    expect(
      await screen.findByRole("heading", { level: 1, name: "feature/quarter-close" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Who is working" })).toBeInTheDocument();
  });
});
