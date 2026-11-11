import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { t } from "@/strings/t";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionList } from "@/api/types";
import { postStatus } from "@/app/harness";
import { clockShort } from "@/lib/clock";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { minuteAt, replaySession, runningSession } from "@/test/replay-session";
import { sessionList, sessionRow } from "@/test/review";
import { fakeServer } from "@/test/server";
import type { FakeServer } from "@/test/server";
import type { Timeline } from "@/api/types";

afterEach(() => {
  cleanup();
  resetViewport();
  vi.useRealTimers();
});

beforeEach(() => {
  postStatus("");
});

const ms = (text: string): number => Date.parse(text);
const time = (minute: number): string => clockShort(ms(minuteAt(minute)));
const base = "#/p/builder/review/sessions/s1";

/** A server with one session and a Sessions list that names it. */
function serverWith(answer: Timeline, list: SessionList | null = null): FakeServer {
  const server = fakeServer({ timelines: { s1: answer } });
  const rows =
    list ??
    sessionList([
      {
        day: "2026-10-30",
        sessions: [sessionRow("s1", { started: answer.session.started, branch: "feature/ledger" })],
      },
    ]);
  const inner = server.fetch;
  server.fetch = (input, init) => {
    const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (path.startsWith("/api/sessions?")) {
      server.calls.push(path);
      return Promise.resolve(new Response(JSON.stringify(rows)));
    }
    return inner(input, init);
  };
  return server;
}

const slider = (): HTMLInputElement =>
  screen.getByRole<HTMLInputElement>("slider", { name: "Replay time" });
const status = (): string =>
  document.querySelector("div.sr-only[role='status']")?.textContent ?? "";

async function ready(): Promise<HTMLInputElement> {
  await screen.findByRole("slider", { name: "Replay time" });
  return slider();
}

describe("the header", () => {
  it("names the session, its state, who ran it and when, with a way back that keeps the range", async () => {
    const server = serverWith(replaySession());
    await mount(`${base}?range=7d`, { server });
    const heading = await screen.findByRole("heading", { level: 1, name: "feature/quarter-close" });
    const header = heading.closest("header");
    if (header === null) throw new Error("no header");
    expect(within(header).getByText("Ended")).toBeInTheDocument();
    expect(within(header).getByText(/^Builder, .*, 1 hour$/)).toBeInTheDocument();
    const back = within(header).getByRole("link", { name: /Sessions in the last 7 days/ });
    expect(back).toHaveAttribute("href", "#/p/builder/review/sessions?range=7d");
    expect(within(header).queryByRole("link", { name: "Open in Live" })).toBeNull();
  });

  it("offers Open in Live only while the session runs", async () => {
    const server = serverWith(runningSession(30));
    await mount(`${base}?range=30d`, { server });
    const link = await screen.findByRole("link", { name: "Open in Live" });
    expect(link).toHaveAttribute("href", "#/p/builder/live?session=s1");
    expect(screen.getByText(/still running$/)).toBeInTheDocument();
  });
});

describe("help", () => {
  it("puts a button on the state, the totals and the timeline, and keeps the line's keys", async () => {
    await mount(`${base}?range=30d`, { server: serverWith(replaySession()) });
    await ready();
    expect(screen.getByRole("button", { name: "About Session states" })).toBeInTheDocument();
    // One entry for the Ring and the dots, with one "?" on the first tile that draws one.
    expect(screen.getAllByRole("button", { name: "About Session totals" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "About Who worked when" })).toBeInTheDocument();
    // The slider is still the only slider, and the "?" buttons are not it.
    expect(screen.getAllByRole("slider")).toHaveLength(1);
  });

  it("marks the session's state line in the states popover as Shown here", async () => {
    const user = userEvent.setup();
    await mount(`${base}?range=30d`, { server: serverWith(replaySession()) });
    await ready();
    await user.click(screen.getByRole("button", { name: "About Session states" }));
    const dialog = await screen.findByRole("dialog", { name: "Session states" });
    const marked = within(dialog).getByText(t("hp_this_setting")).closest(".hp-row");
    expect(marked).not.toBeNull();
    const word = ["Working", "Idle", "Ended"].find((w) => marked?.textContent?.startsWith(w));
    expect(word).toBeDefined();
    expect(document.querySelector(".live-state")).toHaveTextContent(word ?? "");
  });
});

describe("the tiles and the line", () => {
  it("read the time from ?at= and show the value at the line with the whole session under it", async () => {
    await mount(`${base}?range=30d&at=25`, { server: serverWith(replaySession()) });
    const line = await ready();
    expect(line).toHaveValue("25");
    expect(line).toHaveAttribute("aria-valuetext", time(25));
    expect(screen.getByText(`Spent by ${time(25)}`)).toBeInTheDocument();
    expect(screen.getByText(`Runs by ${time(25)}`)).toBeInTheDocument();
    expect(screen.getByText("3 working, 4 not started yet")).toBeInTheDocument();
    expect(screen.getAllByText(/in the whole session$/).length).toBeGreaterThan(0);
  });

  it("clamps a value past the axis to the end with no message and drops it from the URL", async () => {
    const { router } = await mount(`${base}?range=30d&at=999`, {
      server: serverWith(replaySession()),
    });
    const line = await ready();
    expect(line).toHaveValue("60");
    await waitFor(() => {
      expect(router.state.location.search).not.toContain("at=");
    });
    expect(router.state.location.search).toContain("range=30d");
    expect(screen.getAllByText("Whole session")).toHaveLength(3);
    expect(screen.getByText("10 finished")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Go to end" })).toBeNull();
  });

  it("moves with the keys, writes ?at= with replace and keeps the range", async () => {
    const user = userEvent.setup();
    const { router } = await mount(`${base}?range=30d&at=25`, {
      server: serverWith(replaySession()),
    });
    const line = await ready();
    fireEvent.change(line, { target: { value: "26" } });
    await waitFor(() => {
      expect(router.state.location.search).toContain("at=26");
    });
    expect(router.state.historyAction).toBe("REPLACE");
    expect(slider()).toHaveAttribute("aria-valuetext", time(26));
    slider().focus();
    await user.keyboard("{PageUp}");
    await waitFor(() => {
      expect(slider()).toHaveValue("31");
    });
    expect(slider()).toHaveAttribute("aria-valuetext", time(31));
    await user.keyboard("{PageDown}{PageDown}");
    await waitFor(() => {
      expect(slider()).toHaveValue("21");
    });
    expect(router.state.location.search).toContain("range=30d");
  });

  it("shows the hint with the page step", async () => {
    await mount(`${base}?range=30d&at=25`, { server: serverWith(replaySession()) });
    await ready();
    expect(
      screen.getByText("Arrow keys move 1 minute, Page Up and Page Down move 5"),
    ).toBeInTheDocument();
  });
});

describe("a long session", () => {
  it("says numbers update every bucket and moves Page Up by one bucket", async () => {
    const answer = replaySession();
    const long: Timeline = {
      ...answer,
      axis: { ...answer.axis, bucket_seconds: 600 },
      buckets: answer.buckets.filter((_, i) => i % 10 === 0),
      runs: answer.runs.map((r) => ({ ...r, cum: r.cum.filter((_, i) => i % 10 === 9) })),
    };
    const user = userEvent.setup();
    await mount(`${base}?range=30d&at=25`, { server: serverWith(long) });
    await ready();
    expect(
      screen.getByText(
        "On long sessions they update every 10 minutes, but runs update every minute.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Arrow keys move 1 minute, Page Up and Page Down move 10"),
    ).toBeInTheDocument();
    // Cost and tokens are as of the last bucket end, runs as of the line.
    expect(screen.getByText(`Spent by ${time(20)}`)).toBeInTheDocument();
    expect(screen.getByText(`Runs by ${time(25)}`)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /averaged over 10 minutes/ })).toBeInTheDocument();
    slider().focus();
    await user.keyboard("{PageUp}");
    await waitFor(() => {
      expect(slider()).toHaveValue("35");
    });
  });

  it("shows no precision label on a one minute session", async () => {
    await mount(`${base}?range=30d&at=25`, { server: serverWith(replaySession()) });
    await ready();
    expect(screen.queryByText(/On long sessions/)).toBeNull();
  });
});

describe("the chart's text alternative", () => {
  it("follows the line", async () => {
    await mount(`${base}?range=30d&at=10`, { server: serverWith(replaySession()) });
    await ready();
    expect(
      screen.getByRole("img", {
        name: `Chart of new tokens per minute from ${time(0)} to ${time(10)}, 10K in all, most of them on Opus 5.5`,
      }),
    ).toBeInTheDocument();
    fireEvent.change(slider(), { target: { value: "40" } });
    expect(
      await screen.findByRole("img", {
        name: `Chart of new tokens per minute from ${time(0)} to ${time(40)}, 40K in all, most of them on Opus 5.5`,
      }),
    ).toBeInTheDocument();
  });
});

describe("the lane folds", () => {
  it("folds the runs that start later and shows them when asked", async () => {
    const user = userEvent.setup();
    await mount(`${base}?range=30d&at=25`, { server: serverWith(replaySession()) });
    await ready();
    const lanes = screen.getByRole("list", { name: "Who worked when" });
    expect(within(lanes).getByText("3 start later")).toBeInTheDocument();
    expect(within(lanes).queryByText("c5")).toBeNull();
    const show = within(lanes).getByRole("button", {
      name: "Show 3 runs that start later under deep-reasoner",
    });
    expect(show).toHaveAttribute("aria-expanded", "false");
    await user.click(show);
    expect(within(lanes).getByText("c5")).toBeInTheDocument();
    expect(
      within(lanes).getByRole("button", {
        name: "Hide 3 runs that start later under deep-reasoner",
      }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(within(lanes).getAllByText("Not started yet").length).toBeGreaterThan(3);
  });

  it("does not fold the rows before the line when few children remain", async () => {
    await mount(`${base}?range=30d&at=58`, { server: serverWith(replaySession()) });
    await ready();
    const lanes = screen.getByRole("list", { name: "Who worked when" });
    // Everything under the lead has started or finished, so there is no starts later row.
    expect(within(lanes).queryByText(/start later/)).toBeNull();
  });
});

describe("the settle line", () => {
  it("is said once, 500 ms after the line stops, and not on every step", async () => {
    await mount(`${base}?range=30d&at=25`, { server: serverWith(replaySession()) });
    await ready();
    // Only the timers set from here on are faked, so the page's own polling and waits stay real.
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    postStatus("");
    fireEvent.change(slider(), { target: { value: "26" } });
    fireEvent.change(slider(), { target: { value: "27" } });
    fireEvent.change(slider(), { target: { value: "28" } });
    expect(status()).toBe("");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(499);
    });
    expect(status()).toBe("");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(status()).toBe(
      `At ${time(28)}, 3 working, 3 finished and 4 not started yet. $0.72 spent so far.`,
    );
  });
});

describe("a running session", () => {
  it("follows Now while the line sits at the end", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const server = serverWith(runningSession(30));
    await mount(base, { server });
    expect(await ready()).toHaveValue("30");
    expect(slider()).toHaveAttribute("aria-valuetext", `Now, ${time(30)}`);
    expect(screen.getAllByText("Whole session so far")).toHaveLength(3);
    server.timelines.s1 = runningSession(33);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    await waitFor(() => {
      expect(slider()).toHaveValue("33");
    });
    expect(slider()).toHaveAttribute("aria-valuetext", `Now, ${time(33)}`);
  });

  it("stays where the owner put the line, and Back to now goes to the end", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const server = serverWith(runningSession(30));
    const { router } = await mount(`${base}?at=12`, { server });
    expect(await ready()).toHaveValue("12");
    expect(screen.getByText(`Spent by ${time(12)}`)).toBeInTheDocument();
    server.timelines.s1 = runningSession(33);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    await waitFor(() => {
      expect(slider()).toHaveAttribute("max", "33");
    });
    expect(slider()).toHaveValue("12");
    const button = screen.getByRole("button", { name: "Back to now" });
    fireEvent.click(button);
    await waitFor(() => {
      expect(slider()).toHaveValue("33");
    });
    expect(router.state.location.search).not.toContain("at=");
    expect(slider()).toHaveFocus();
    expect(screen.queryByRole("button", { name: "Back to now" })).toBeNull();
  });

  it("stops polling once the session has ended", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const server = serverWith(runningSession(30));
    await mount(base, { server });
    await ready();
    server.timelines.s1 = replaySession();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    await waitFor(() => {
      expect(screen.getByText("Ended")).toBeInTheDocument();
    });
    expect(screen.queryByRole("link", { name: "Open in Live" })).toBeNull();
    const asked = server.calls.filter((path) => path.includes("/timeline")).length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(server.calls.filter((path) => path.includes("/timeline")).length).toBe(asked);
  });

  it("names the button Go to end on an ended session", async () => {
    await mount(`${base}?at=12`, { server: serverWith(replaySession()) });
    await ready();
    expect(screen.getByRole("button", { name: "Go to end" })).toBeInTheDocument();
  });
});

describe("a session that is not there", () => {
  it("shows the gone state with its own title and a way to Sessions", async () => {
    const server = serverWith(replaySession());
    await mount("#/p/builder/review/sessions/nope?range=90d", { server });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Session not found" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("This session isn't in Builder");
    expect(
      screen.getByText("The link names a session Bar Tab can't find in this project."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See all sessions" })).toHaveAttribute(
      "href",
      "#/p/builder/review/sessions?range=90d",
    );
    expect(screen.getByRole("link", { name: /Sessions in the last 90 days/ })).toBeInTheDocument();
    expect(screen.queryByRole("slider")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Session/ })).toBeNull();
  });
});

describe("the first load", () => {
  it("shows bones with one spoken line and the Session heading", async () => {
    const server = fakeServer({ timelines: { s1: replaySession() } });
    const inner = server.fetch;
    server.fetch = (input, init) =>
      (typeof input === "string" ? input : "").includes("/timeline")
        ? new Promise<Response>(() => undefined)
        : inner(input, init);
    await mount(base, { server });
    expect(await screen.findByRole("heading", { level: 1, name: "Session" })).toBeInTheDocument();
    expect(screen.getByText("Loading this session")).toBeInTheDocument();
    expect(document.querySelector("[aria-busy='true']")).not.toBeNull();
  });
});

describe("the Session Select", () => {
  it("shows the session on screen even when the list's first 50 leave it out", async () => {
    const user = userEvent.setup();
    const answer = replaySession();
    const rows = Array.from({ length: 50 }, (_, i) =>
      sessionRow(`other-${String(i)}`, {
        started: new Date(ms(answer.session.started) + (i + 1) * 3_600_000).toISOString(),
        branch: `feature/n${String(i)}`,
      }),
    );
    const list = sessionList([{ day: "2026-10-31", sessions: rows }], { count: 53, next: "c2" });
    await mount(`${base}?range=30d`, { server: serverWith(answer, list) });
    await ready();
    const select = await screen.findByRole("button", { name: /^Session/ });
    // "October 30, 5:10 PM" in New York. The day and time come from the session's start.
    expect(select).toHaveTextContent(clockShort(ms(answer.session.started)));
    await user.click(select);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Sessions in the last 30 days")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: /See all 53 sessions/ })).toHaveAttribute(
      "href",
      "#/p/builder/review/sessions?range=30d",
    );
    const options = within(dialog).getAllByRole("option");
    // The list stops at 5, and the open session, the oldest of the 51, keeps the last place.
    expect(options).toHaveLength(5);
    const selected = options.filter((option) => option.getAttribute("aria-selected") === "true");
    expect(selected).toHaveLength(1);
    expect(options.at(-1)).toBe(selected[0]);
    // An ended session reads as its branch alone, with no state word before it.
    expect(within(dialog).queryByText("Ended")).toBeNull();
  });

  it("opens another session and keeps the range but not the line", async () => {
    const user = userEvent.setup();
    const answer = replaySession();
    const server = serverWith(
      answer,
      sessionList([
        {
          day: "2026-10-30",
          sessions: [
            sessionRow("s1", { started: answer.session.started, branch: "feature/ledger" }),
            sessionRow("s2", {
              started: new Date(ms(answer.session.started) - 3_600_000).toISOString(),
              branch: "fix/rounding",
            }),
          ],
        },
      ]),
    );
    server.timelines.s2 = {
      ...replaySession(),
      session: { ...answer.session, id: "s2", branch: "fix/rounding" },
    };
    const { router } = await mount(`${base}?range=30d&at=25`, { server });
    await ready();
    await user.click(await screen.findByRole("button", { name: /^Session/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByText("fix/rounding"));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/p/builder/review/sessions/s2");
    });
    expect(router.state.location.search).toBe("?range=30d");
  });
});

describe("a lost feed", () => {
  it("keeps the last numbers on screen under a finding", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const server = serverWith(runningSession(30));
    await mount(base, { server });
    await ready();
    server.down = true;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000);
    });
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /reach|lost|Lost/i })).toBeInTheDocument();
    });
    expect(slider()).toHaveValue("30");
  });
});
