import { cleanup, render, screen, waitFor, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiContext, createApiClient } from "@/api/client";
import type { AppInfo } from "@/api/types";
import { createAccess } from "@/app/access";
import type { LockReason } from "@/app/access";
import { postStatus, StatusRegion } from "@/app/harness";
import { clockShort } from "@/lib/clock";
import { createConnection } from "@/lib/connection";
import { clampIngest, FirstRunPage, LockedPage, sizeText, StoppedPage } from "@/pages/GatePages";
import { appInfo, fakeServer, INSTANCE } from "@/test/server";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

beforeEach(() => {
  postStatus("");
  document.title = "";
});

function at(list: HTMLElement[], index: number): HTMLElement {
  const item = list[index];
  if (item === undefined) throw new Error(`No item at ${index}`);
  return item;
}

const reasons: [LockReason, RegExp][] = [
  ["no_key", /opened without a code/],
  ["code_used", /already used\. Each link works once/],
  ["code_expired", /expired before the tab used it/],
  ["code_unknown", /didn't recognize this link's code/],
  ["server_restarted", /dashboard restarted/],
  ["wrong_project_key", /can't open this project/],
];

describe("LockedPage", () => {
  it.each(reasons)("%s shows its sentence, focuses the h1 and sets the title", (reason, body) => {
    render(
      <>
        <StatusRegion />
        <LockedPage
          gate={{ kind: "locked", reason, otherTabBack: false }}
          command="/bartab"
          route="/p/builder/review/agents"
        />
      </>,
    );
    const heading = screen.getByRole("heading", {
      level: 1,
      name: "This tab can't reach the dashboard",
    });
    expect(heading).toHaveFocus();
    expect(screen.getByText(body)).toBeInTheDocument();
    expect(document.title).toBe("Can't reach the dashboard, Bar Tab");
    expect(screen.getAllByRole("status").map((el) => el.textContent)).toContain(
      "This tab can't reach the dashboard",
    );
    expect(screen.getByText("/bartab")).toBeInTheDocument();
    expect(
      screen.getByText("This tab reopens on Agents, builder once another tab opens the dashboard."),
    ).toBeInTheDocument();
  });

  it("makes Copy the primary action and says Copied politely", async () => {
    const user = userEvent.setup();
    render(
      <LockedPage
        gate={{ kind: "locked", reason: "code_used", otherTabBack: false }}
        command="/bartab"
        route={null}
      />,
    );
    const copy = screen.getByRole("button", { name: "Copy command" });
    expect(copy).toHaveClass("button-primary");
    expect(screen.queryByText("Copied to clipboard")).toBeNull();
    await user.click(copy);
    const status = await screen.findByText("Copied to clipboard");
    expect(status).toHaveAttribute("role", "status");
    expect(await navigator.clipboard.readText()).toBe("/bartab");
  });

  it("leaves out the route line when no route was kept", () => {
    render(
      <LockedPage
        gate={{ kind: "locked", reason: "no_key", otherTabBack: false }}
        command="/bartab"
        route={null}
      />,
    );
    expect(screen.queryByText(/This tab reopens on/)).toBeNull();
  });

  it("shows the new-tab line above the h1 when the other tab is back", () => {
    render(
      <LockedPage
        gate={{ kind: "locked", reason: "code_used", otherTabBack: true }}
        command="/bartab"
        route="/p/builder/review/agents"
      />,
    );
    const line = screen.getByText("Your other tab is open again on Agents, builder.");
    expect(line.closest("[role=status]")).not.toBeNull();
    const heading = screen.getByRole("heading", { level: 1 });
    expect(line.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

function renderStopped(server = fakeServer()) {
  const access = createAccess({
    launch: { nonce: "", instance: INSTANCE, command: "/bartab" },
    storage: window.sessionStorage,
  });
  const connection = createConnection();
  const api = createApiClient({ access, connection, fetchFn: server.fetch });
  render(
    <ApiContext value={api}>
      <StatusRegion />
      <StoppedPage command="/bartab" route="/p/builder/live" />
    </ApiContext>,
  );
  return { connection, server };
}

describe("StoppedPage", () => {
  it("shows the card, the command, the route line and the retry row", () => {
    renderStopped();
    expect(
      screen.getByRole("heading", { level: 1, name: "The dashboard stopped answering" }),
    ).toHaveFocus();
    expect(document.title).toBe("Dashboard stopped answering, Bar Tab");
    expect(screen.getByText("Run this command in Claude Code to start it again.")).toBeVisible();
    expect(screen.getByText("/bartab")).toBeInTheDocument();
    expect(
      screen.getByText("When it answers, this tab goes back to Live, builder on its own."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Checking again every 10 seconds/)).toBeInTheDocument();
    expect(screen.getByText("No answer yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy command" })).not.toHaveClass("button-primary");
  });

  it("shows the last answer as a clock time", () => {
    const { connection } = renderStopped();
    const at = new Date(2026, 10, 8, 15, 42).getTime();
    act(() => {
      connection.recordAnswer(at);
    });
    expect(screen.getByText(`Last answer at ${clockShort(at)}`)).toBeInTheDocument();
  });

  it("swaps Try now to Checking with aria-busy while a request runs", async () => {
    const user = userEvent.setup();
    const server = fakeServer();
    let release: (response: Response) => void = () => undefined;
    server.fetch = () =>
      new Promise<Response>((resolve) => {
        release = resolve;
      });
    renderStopped(server);
    const button = screen.getByRole("button", { name: "Try now" });
    expect(button).not.toHaveAttribute("aria-busy");
    await user.click(button);
    const busy = await screen.findByRole("button", { name: "Checking" });
    expect(busy).toHaveAttribute("aria-busy", "true");
    release(new Response(JSON.stringify(appInfo())));
    expect(await screen.findByRole("button", { name: "Try now" })).not.toHaveAttribute("aria-busy");
  });

  it("checks again every 10 seconds while the tab is visible", () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const { server } = renderStopped();
    expect(server.calls).toHaveLength(0);
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(server.calls).toEqual(["/api/app?project=builder"]);
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(server.calls).toHaveLength(2);
  });

  it("does not check while the tab is hidden", () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const { server } = renderStopped();
    const spy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(server.calls).toHaveLength(0);
    spy.mockRestore();
  });
});

function running(over: Partial<AppInfo["ingest"]> = {}): AppInfo {
  return appInfo({
    ingest: {
      state: "running",
      files_done: 312,
      files_total: 1240,
      bytes_done: 1_200_000_000,
      bytes_total: 2_000_000_000,
      error: null,
      retrying: false,
      retry_at: null,
      ...over,
    },
  });
}

function renderFirstRun(info: AppInfo) {
  return render(
    <>
      <StatusRegion />
      <FirstRunPage info={info} command="/bartab" />
    </>,
  );
}

function firstRunPage(info: AppInfo) {
  return (
    <>
      <StatusRegion />
      <FirstRunPage info={info} command="/bartab" />
    </>
  );
}

describe("size label", () => {
  it.each([
    [1_200_000_000, 2_000_000_000, "1.2 of 2.0 GB"],
    [0, 2_000_000_000, "0.0 of 2.0 GB"],
    [41_000_000, 82_000_000, "41.0 of 82.0 MB"],
    [950_000_000, 999_000_000, "950.0 of 999.0 MB"],
    [1_500, 4_000, "1.5 of 4.0 KB"],
    [120, 640, "120 of 640 B"],
    [3_000_000_000, 2_000_000_000, "2.0 of 2.0 GB"],
  ])("%i of %i reads %s", (done, total, text) => {
    expect(sizeText({ bytes_done: done, bytes_total: total })).toBe(text);
  });

  it("has no label while the total is unknown or zero", () => {
    expect(sizeText({ bytes_done: 0, bytes_total: null })).toBeNull();
    expect(sizeText({ bytes_done: 0, bytes_total: 0 })).toBeNull();
  });
});

describe("clampIngest", () => {
  const base = running().ingest;

  it("holds the largest bytes_done seen for the same total", () => {
    const first = clampIngest({ ...base, bytes_done: 1_000 }, null);
    const back = clampIngest({ ...base, bytes_done: 400 }, first.seen);
    expect(back.ingest.bytes_done).toBe(1_000);
    const on = clampIngest({ ...base, bytes_done: 1_500 }, back.seen);
    expect(on.ingest.bytes_done).toBe(1_500);
  });

  it("starts over for a new total or when a retry starts", () => {
    const first = clampIngest({ ...base, bytes_done: 1_000 }, null);
    expect(
      clampIngest({ ...base, bytes_total: 3_000_000_000, bytes_done: 5 }, first.seen).ingest
        .bytes_done,
    ).toBe(5);
    expect(
      clampIngest({ ...base, retrying: true, bytes_done: 5 }, first.seen).ingest.bytes_done,
    ).toBe(5);
  });
});

describe("FirstRunPage", () => {
  it("shows steps 1 and 2 as Done and step 3 live with the size, by bytes only", () => {
    renderFirstRun(running());
    expect(
      screen.getByRole("heading", { level: 1, name: "Getting the dashboard ready" }),
    ).toHaveFocus();
    expect(document.title).toBe("Getting the dashboard ready, Bar Tab");
    const list = screen.getByRole("list", { name: "Getting the dashboard ready" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(at(rows, 0)).getByText("Done")).toBeInTheDocument();
    expect(within(at(rows, 1)).getByText("Done")).toBeInTheDocument();
    expect(within(at(rows, 2)).getByText("In progress")).toBeInTheDocument();
    expect(within(at(rows, 0)).queryByRole("progressbar")).toBeNull();
    const bar = screen.getByRole("progressbar", { name: "Read your usage history" });
    expect(bar).toHaveAttribute("aria-valuetext", "1.2 of 2.0 GB");
    expect(bar).toHaveAttribute("aria-valuenow", "60");
    expect(within(list).getByText("1.2 of 2.0 GB")).toBeInTheDocument();
    expect(list).not.toHaveTextContent(/files/);
    expect(
      screen.getByText(
        "This step reads files on this computer, so it doesn't need an internet connection.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says Counting files with no bar while the totals are null", () => {
    renderFirstRun(running({ files_total: null, bytes_total: null, bytes_done: 0, files_done: 0 }));
    const list = screen.getByRole("list", { name: "Getting the dashboard ready" });
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(within(list).getByText("In progress")).toBeInTheDocument();
    const note = within(list).getByText("Counting files");
    expect(note).toHaveAttribute("role", "status");
    expect(note).toHaveAttribute("aria-busy", "true");
    expect(list).not.toHaveTextContent("0 of 0");
  });

  it("never moves the bar back within a pass", () => {
    const { rerender } = renderFirstRun(running({ bytes_done: 1_200_000_000 }));
    rerender(firstRunPage(running({ bytes_done: 600_000_000 })));
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "60");
    expect(bar).toHaveAttribute("aria-valuetext", "1.2 of 2.0 GB");
    rerender(firstRunPage(running({ bytes_done: 1_600_000_000 })));
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "80");
  });

  it("shows a failed step with the error finding, the file, the next try and the command", () => {
    renderFirstRun(
      running({
        state: "failed",
        bytes_done: 800_000_000,
        error: { code: "config_dir_unreadable", file: "/work/.claude/projects" },
        retry_at: "2026-11-08T15:44:00Z",
      }),
    );
    const list = screen.getByRole("list", { name: "Getting the dashboard ready" });
    expect(within(list).getByText("Failed")).toBeInTheDocument();
    expect(within(list).getByText("0.8 of 2.0 GB")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("The dashboard couldn't finish setting up")).toBeInTheDocument();
    expect(alert).toHaveTextContent(
      "The dashboard isn't allowed to read /work/.claude/projects. Check that folder's permissions.",
    );
    expect(within(alert).getByText("/work/.claude/projects").tagName).toBe("CODE");
    expect(
      within(alert).getByText(`Next try at ${clockShort("2026-11-08T15:44:00Z")}`),
    ).toBeVisible();
    expect(
      within(alert).getByText(
        "The dashboard tries again on its own. To try now, run this command in Claude Code.",
      ),
    ).toBeVisible();
    expect(within(alert).getByText("/bartab")).toBeInTheDocument();
    expect(within(alert).getByRole("button", { name: "Copy command" })).toBeInTheDocument();
    expect(
      screen.queryByText(
        "This step reads files on this computer, so it doesn't need an internet connection.",
      ),
    ).toBeNull();
  });

  it("keeps the old try-again line when no retry time is set", () => {
    renderFirstRun(
      running({ state: "failed", error: { code: "store_damaged", file: "/work/data/db" } }),
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Run this command in Claude Code to try again.");
    expect(alert).not.toHaveTextContent("Next try at");
  });

  it.each([
    ["config_dir_missing", null, "can't find Claude Code's projects folder"],
    ["store_unwritable", "/work/data", "can't save to /work/data"],
    ["store_damaged", "/work/data/db", "database at /work/data/db failed its integrity check"],
    ["unexpected", "/work/data/log", "details are in /work/data/log"],
  ] as const)("says the %s reason", (code, file, text) => {
    renderFirstRun(running({ state: "failed", error: { code, file } }));
    expect(screen.getByRole("alert")).toHaveTextContent(text);
  });

  it("keeps the finding while a retry runs and goes back to Counting files", () => {
    renderFirstRun(
      running({
        retrying: true,
        files_total: null,
        bytes_total: null,
        bytes_done: 0,
        error: { code: "store_unwritable", file: "/work/data/db" },
      }),
    );
    const list = screen.getByRole("list", { name: "Getting the dashboard ready" });
    expect(within(list).getByText("In progress")).toBeInTheDocument();
    expect(within(list).getByText("Counting files")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("can't save to /work/data/db");
  });

  it("announces a retry time once, not on every poll", async () => {
    const failed = (retryAt: string) =>
      firstRunPage(
        running({
          state: "failed",
          error: { code: "store_unwritable", file: "/work/data/db" },
          retry_at: retryAt,
        }),
      );
    const { rerender } = render(failed("2026-11-08T15:44:00Z"));
    const status = screen.getByText(`Next try at ${clockShort("2026-11-08T15:44:00Z")}`);
    expect(status).toHaveAttribute("role", "status");
    let mutations = 0;
    const observer = new MutationObserver((list) => {
      mutations += list.length;
    });
    observer.observe(status, { childList: true, subtree: true, characterData: true });
    rerender(failed("2026-11-08T15:44:00Z"));
    rerender(failed("2026-11-08T15:44:00Z"));
    await Promise.resolve();
    expect(observer.takeRecords()).toHaveLength(0);
    expect(mutations).toBe(0);
    rerender(failed("2026-11-08T15:51:00Z"));
    await waitFor(() => {
      expect(status).toHaveTextContent(`Next try at ${clockShort("2026-11-08T15:51:00Z")}`);
    });
    observer.disconnect();
  });

  it("shows the store_newer gate with its sentence, next step and command", () => {
    renderFirstRun(
      running({
        state: "failed",
        files_total: null,
        bytes_total: null,
        bytes_done: 0,
        error: { code: "store_newer", file: null },
      }),
    );
    const heading = screen.getByRole("heading", {
      level: 1,
      name: "This history needs a newer Bar Tab",
    });
    expect(heading).toHaveFocus();
    expect(document.title).toBe("This history needs a newer Bar Tab, Bar Tab");
    expect(screen.getByText(/can't open it\./)).toHaveTextContent(
      "A newer Bar Tab upgraded your saved history, so Bar Tab 0.0.0, the version running now, can't open it.",
    );
    expect(screen.getByText("Update Bar Tab, then run this command in Claude Code.")).toBeVisible();
    expect(screen.getByText("/bartab")).toBeInTheDocument();
    expect(screen.queryByRole("list")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("gate transitions", () => {
  it("moves focus and the title when the reason changes", async () => {
    const { rerender } = render(
      <LockedPage
        gate={{ kind: "locked", reason: "code_used", otherTabBack: false }}
        command="/bartab"
        route={null}
      />,
    );
    const heading = screen.getByRole("heading", { level: 1 });
    heading.blur();
    rerender(
      <LockedPage
        gate={{ kind: "locked", reason: "server_restarted", otherTabBack: false }}
        command="/bartab"
        route={null}
      />,
    );
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1 })).toHaveFocus();
    });
  });
});
