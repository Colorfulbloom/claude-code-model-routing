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
import { FirstRunPage, LockedPage, StoppedPage } from "@/pages/GatePages";
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
      bytes_done: 0,
      bytes_total: 0,
      error: null,
      retrying: false,
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

describe("FirstRunPage", () => {
  it("shows steps 1 and 2 as Done with no sizes and step 3 live with the file count", () => {
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
    expect(bar).toHaveAttribute("aria-valuetext", "312 of 1,240 files");
    expect(bar).toHaveAttribute("aria-valuenow", "25");
    expect(
      screen.getByText(
        "This step reads files on this computer, so it doesn't need an internet connection.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a failed step with the error finding, the file and the command", () => {
    renderFirstRun(
      running({
        state: "failed",
        files_done: 640,
        error: { code: "config_dir_unreadable", file: "/work/.claude/projects" },
      }),
    );
    const list = screen.getByRole("list", { name: "Getting the dashboard ready" });
    expect(within(list).getByText("Failed")).toBeInTheDocument();
    expect(within(list).getByText("640 of 1,240 files")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("The dashboard couldn't finish setting up")).toBeInTheDocument();
    expect(alert).toHaveTextContent(
      "The dashboard isn't allowed to read /work/.claude/projects. Check that folder's permissions.",
    );
    expect(within(alert).getByText("/work/.claude/projects").tagName).toBe("CODE");
    expect(within(alert).getByText("Run this command in Claude Code to try again.")).toBeVisible();
    expect(within(alert).getByText("/bartab")).toBeInTheDocument();
    expect(within(alert).getByRole("button", { name: "Copy command" })).toBeInTheDocument();
    expect(
      screen.queryByText(
        "This step reads files on this computer, so it doesn't need an internet connection.",
      ),
    ).toBeNull();
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

  it("shows retrying as In progress with an empty bar, a polite status and no finding", () => {
    renderFirstRun(running({ files_done: 0, retrying: true }));
    const list = screen.getByRole("list", { name: "Getting the dashboard ready" });
    expect(within(list).getByText("In progress")).toBeInTheDocument();
    expect(within(list).queryByText("Failed")).toBeNull();
    const since = clockShort("2026-11-08T15:42:00Z");
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "0");
    expect(bar).toHaveAttribute("aria-valuetext", `Trying again since ${since}`);
    const status = screen
      .getAllByRole("status")
      .find((el) => el.textContent === `Trying again since ${since}`);
    expect(status).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("goes back to the file count when the retry ends", () => {
    const { rerender } = renderFirstRun(running({ files_done: 0, retrying: true }));
    rerender(
      <>
        <StatusRegion />
        <FirstRunPage info={running({ files_done: 100 })} command="/bartab" />
      </>,
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "100 of 1,240 files");
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
