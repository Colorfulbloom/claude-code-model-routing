import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { postStatus } from "@/app/harness";
import { FakeChannel } from "@/app/test-channel";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { appInfo, fakeServer, historyInfo, pricesInfo } from "@/test/server";

afterEach(() => {
  cleanup();
  resetViewport();
});

beforeEach(() => {
  postStatus("");
});

/** [hash, the one sidebar link that is current] */
const sidebarCases: [string, string][] = [
  ["#/p/builder/live", "Live"],
  ["#/p/builder/review/summary", "Summary"],
  ["#/p/builder/review/sessions/s1", "Sessions"],
  ["#/p/builder/review/agents/new", "Agents"],
  ["#/p/builder/review/models", "Models"],
  ["#/p/builder/setup/settings/effort/edit", "Your setup"],
  ["#/p/builder/to-fix", "To fix, 4 items"],
  ["#/reference/decides", "How Claude Code decides"],
  ["#/reference/glossary", "Glossary"],
];

/** [hash, the one tab bar item that is current] */
const tabCases: [string, string][] = [
  ["#/p/builder/live", "Live"],
  ["#/p/builder/review/summary", "Review"],
  ["#/p/builder/review/sessions/s1", "Review"],
  ["#/p/builder/review/models", "Review"],
  ["#/p/builder/setup", "Setup"],
  ["#/p/builder/setup/settings/effort", "Setup"],
  ["#/p/builder/to-fix", "To fix, 4 items"],
  ["#/more", "More"],
  ["#/reference/decides", "More"],
  ["#/reference/glossary", "More"],
];

describe("sidebar at 1440", () => {
  it("has the plain wordmark, the groups, the version line and no tab bar", async () => {
    await mount("#/p/builder/live");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getByText("Bar Tab")).toBeInTheDocument();
    for (const heading of ["Review", "Setup", "Reference"]) {
      expect(within(nav).getByText(heading)).toBeInTheDocument();
    }
    expect(within(nav).getAllByRole("link")).toHaveLength(9);
    expect(await within(nav).findByText("Claude Code 2.1.310")).toBeInTheDocument();
    expect(screen.getAllByRole("navigation")).toHaveLength(1);
    expect(document.querySelector(".top-bar")).toBeNull();
  });

  it("carries the current range on the Review links, as the phone's pages do", async () => {
    await mount("#/p/builder/review/models?range=7d");
    await screen.findByRole("link", { name: "To fix, 4 items" });
    const links: [string, string][] = [
      ["Summary", "summary"],
      ["Sessions", "sessions"],
      ["Agents", "agents"],
      ["Models", "models"],
    ];
    for (const [name, page] of links) {
      expect(screen.getByRole("link", { name })).toHaveAttribute(
        "href",
        `#/p/builder/review/${page}?range=7d`,
      );
    }
  });

  it("leaves the Review links plain on a page that is not Review", async () => {
    await mount("#/p/builder/live?range=7d");
    await screen.findByRole("link", { name: "To fix, 4 items" });
    expect(screen.getByRole("link", { name: "Models" })).toHaveAttribute(
      "href",
      "#/p/builder/review/models",
    );
  });

  it.each(sidebarCases)("%s marks only %s as current", async (hash, name) => {
    await mount(hash);
    await screen.findByRole("link", { name: "To fix, 4 items" });
    const current = screen.getAllByRole("link", { current: "page" });
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAccessibleName(new RegExp(`^${name}`));
  });

  it("puts the count in the accessible name and hides it at zero", async () => {
    await mount("#/p/builder/live", {
      server: fakeServer({ app: appInfo({ to_fix_count: 0 }) }),
    });
    await screen.findByText("Claude Code 2.1.310");
    expect(screen.getByRole("link", { name: "To fix" })).toBeInTheDocument();
    expect(screen.queryByText("4")).toBeNull();
  });

  it("uses the singular for one item", async () => {
    await mount("#/p/builder/live", {
      server: fakeServer({ app: appInfo({ to_fix_count: 1 }) }),
    });
    expect(await screen.findByRole("link", { name: "To fix, 1 item" })).toBeInTheDocument();
  });

  it("asks /api/app for the project in the route", async () => {
    const { server } = await mount("#/p/driftwood/live");
    await screen.findByRole("link", { name: "To fix, 4 items" });
    expect(server.calls).toContain("/api/app?project=driftwood");
    expect(server.calls).toContain("/api/projects");
  });

  it("shows the Working mark for a running project, then drops it while calls fail", async () => {
    const { connection } = await mount("#/p/builder/live");
    const live = await screen.findByRole("link", { name: /^Live/ });
    await waitFor(() => {
      expect(within(live).getByText("Working")).toBeInTheDocument();
    });
    expect(screen.queryByText(/^Updated \d{1,2}:\d{2}:\d{2}/)).toBeNull();
    act(() => {
      connection.recordFailure();
    });
    expect(within(live).queryByText("Working")).toBeNull();
    expect(screen.getByText(/^Updated \d{1,2}:\d{2}:\d{2}/)).toBeInTheDocument();
  });

  it("shows no Working mark for a project with nothing running", async () => {
    await mount("#/p/driftwood/live");
    const live = await screen.findByRole("link", { name: /^Live/ });
    await screen.findByRole("link", { name: "To fix, 4 items" });
    expect(within(live).queryByText("Working")).toBeNull();
  });

  it("says no answer yet when calls fail before the first answer", async () => {
    const server = fakeServer();
    server.down = true;
    await mount("#/p/builder/live", { server });
    expect(await screen.findByText("No answer yet")).toBeInTheDocument();
  });

  it("opens the project list in a popover and swaps the project, keeping the page", async () => {
    const user = userEvent.setup();
    const { router } = await mount("#/p/builder/review/models");
    const select = await screen.findByRole("button", { name: /Project/ });
    await waitFor(() => {
      expect(select).toHaveTextContent("Builder");
    });
    await user.click(select);
    const list = await screen.findByRole("listbox");
    const options = within(list).getAllByRole("option");
    expect(options).toHaveLength(4);
    expect(within(list).getByText("Agent working")).toBeInTheDocument();
    expect(within(list).getByText("No .claude folder")).toBeInTheDocument();
    expect(within(list).getByText("Folder not found")).toBeInTheDocument();
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    await user.click(within(list).getByRole("option", { name: /Driftwood/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/p/driftwood/review/models");
    });
  });

  it("drops a detail page to its list when the project changes", async () => {
    const user = userEvent.setup();
    const { router } = await mount("#/p/builder/review/sessions/s1");
    const select = await screen.findByRole("button", { name: /Project/ });
    await waitFor(() => {
      expect(select).toHaveTextContent("Builder");
    });
    await user.click(select);
    await user.click(await screen.findByRole("option", { name: /Driftwood/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/p/driftwood/review/sessions");
    });
  });

  it("shows the empty state with a heading and a sentence, and no command row", async () => {
    const user = userEvent.setup();
    await mount("#/reference/glossary", { server: fakeServer({ projects: [] }) });
    await user.click(await screen.findByRole("button", { name: /Project/ }));
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(
      screen.getByText("A project appears here after you use Claude Code in it."),
    ).toBeInTheDocument();
    expect(screen.queryByText("/bartab-preview")).toBeNull();
    expect(screen.queryByRole("button", { name: "Copy command" })).toBeNull();
  });

  it("redirects #/more to the current project's Live", async () => {
    const { router } = await mount("#/more", { launchProject: "driftwood" });
    expect(await screen.findByRole("heading", { level: 1, name: "Live" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/p/driftwood/live");
  });

  it("limits the main column to 1280px through the shell content class", async () => {
    await mount("#/p/builder/live");
    const heading = await screen.findByRole("heading", { level: 1, name: "Live" });
    expect(heading.closest(".shell-content")).not.toBeNull();
    expect(heading.closest("main")).toHaveClass("shell-main");
  });

  it("shows the new-tab line above the h1 when another tab says it is back, until the person moves on", async () => {
    const { router } = await mount("#/p/builder/review/agents");
    const heading = await screen.findByRole("heading", { level: 1, name: "Agents" });
    expect(screen.queryByText(/Your other tab is open again/)).toBeNull();
    const other = new FakeChannel("bartab-access");
    act(() => {
      other.postMessage({ type: "back", route: "/p/builder/review/agents" });
    });
    const line = await screen.findByText("Your other tab is open again on Agents, builder.");
    expect(line.closest("[role=status]")).not.toBeNull();
    expect(line.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await act(() => router.navigate("/p/builder/review/models"));
    await waitFor(() => {
      expect(screen.queryByText(/Your other tab is open again/)).toBeNull();
    });
    other.close();
  });
});

describe("top bar and tab bar at 375", () => {
  it("has the top bar, the five-item tab bar last in the DOM and no sidebar", async () => {
    await mount("#/p/builder/live", { width: 375 });
    const bar = await screen.findByRole("navigation", { name: "Main" });
    expect(within(bar).getAllByRole("link")).toHaveLength(5);
    expect(document.querySelector(".top-bar")).toHaveTextContent("Live");
    expect(screen.getAllByRole("navigation")).toHaveLength(1);
    const main = screen.getByRole("main");
    expect(main.compareDocumentPosition(bar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(document.body.querySelector(".shell")?.lastElementChild).toBe(bar);
  });

  it.each(tabCases)("%s marks only %s as current", async (hash, name) => {
    await mount(hash, { width: 375 });
    await screen.findByRole("link", { name: "To fix, 4 items" });
    // The Review pages carry their own Segmented pages in the content, so look in the tab bar only.
    const bar = screen.getByRole("navigation", { name: "Main" });
    const current = within(bar).getAllByRole("link", { current: "page" });
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAccessibleName(name);
  });

  it("hides the tab bar on the agent form routes", async () => {
    await mount("#/p/builder/review/agents/new", { width: 375 });
    await screen.findByRole("heading", { level: 1, name: "New agent" });
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(document.querySelector(".top-bar")).not.toBeNull();
  });

  it("names the project button by its visible words, opens the tray, and returns focus on Escape and Close", async () => {
    const user = userEvent.setup();
    await mount("#/p/builder/live", { width: 375 });
    const trigger = await screen.findByRole("button", { name: "Builder" });
    expect(trigger).toHaveAttribute("aria-haspopup", "listbox");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);
    const tray = await screen.findByRole("dialog", { name: "Projects" });
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(within(tray).getAllByRole("option")).toHaveLength(4);
    expect(document.querySelector(".pk-scrim")).not.toBeNull();
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);
    await user.click(await screen.findByRole("button", { name: "Close" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(trigger).toHaveFocus();
  });

  it("swaps the project from the tray", async () => {
    const user = userEvent.setup();
    const { router } = await mount("#/p/builder/review/agents", { width: 375 });
    await user.click(await screen.findByRole("button", { name: "Builder" }));
    await user.click(await screen.findByRole("option", { name: /Driftwood/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/p/driftwood/review/agents");
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows the empty state in the tray, with no command row", async () => {
    const user = userEvent.setup();
    await mount("#/p/builder/live", { width: 375, server: fakeServer({ projects: [] }) });
    await user.click(await screen.findByRole("button", { name: "builder" }));
    const tray = await screen.findByRole("dialog", { name: "Projects" });
    expect(within(tray).getByText("No projects yet")).toBeInTheDocument();
    expect(within(tray).queryByRole("button", { name: "Copy command" })).toBeNull();
  });

  it("shows the Updated line while calls fail and drops it when they recover", async () => {
    const { connection } = await mount("#/p/builder/live", { width: 375 });
    await screen.findByRole("link", { name: "To fix, 4 items" });
    act(() => {
      connection.recordFailure();
    });
    expect(screen.getByText(/^Updated \d{1,2}:\d{2}:\d{2}/)).toBeInTheDocument();
    act(() => {
      connection.recordAnswer(Date.now());
    });
    expect(screen.queryByText(/^Updated \d{1,2}:\d{2}:\d{2}/)).toBeNull();
  });
});

describe("More page", () => {
  it("shows Reference links and both versions at phone width", async () => {
    await mount("#/more", { width: 375 });
    await screen.findByRole("heading", { level: 1, name: "More" });
    const card = screen.getByRole("region", { name: "Reference" });
    const links = within(card).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual([
      expect.stringContaining("How Claude Code decides"),
      expect.stringContaining("Glossary"),
    ]);
    const version = screen.getByRole("region", { name: "Version" });
    expect(await within(version).findByText("Claude Code 2.1.310")).toBeInTheDocument();
    expect(within(version).getByText("Bar Tab 0.0.0")).toBeInTheDocument();
  });
});

describe("sidebar footer", () => {
  const history = (over: Parameters<typeof historyInfo>[0]) => historyInfo(over);

  it("shows the five quiet lines at rest, none a link or a live region", async () => {
    await mount("#/p/builder/live");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    await within(nav).findByText("Prices as of October 28");
    const lines = [...nav.querySelectorAll(".sidebar-footer-line")].map((el) => el.textContent);
    expect(lines).toHaveLength(5);
    expect(lines[0]).toMatch(/^Updated /);
    expect(lines[1]).toBe("History since September 3");
    expect(lines[2]).toMatch(/^Last backup /);
    expect(lines[3]).toBe("Prices as of October 28");
    expect(lines[4]).toBe("Claude Code 2.1.310");
    const footer = nav.querySelector(".sidebar-footer");
    expect(footer?.querySelector("a")).toBeNull();
    expect(footer?.querySelector("[role], [aria-live]")).toBeNull();
  });

  it("adds the unreadable line and replaces the backup line on problems", async () => {
    const app = appInfo({
      history: history({
        unreadable_files: 3,
        backup_failed: { at: "2026-11-08T09:02:00Z", reason_code: "no_space" },
      }),
    });
    await mount("#/p/builder/live", { server: fakeServer({ app }) });
    const nav = await screen.findByRole("navigation", { name: "Main" });
    await within(nav).findByText("Couldn't read 3 files");
    const lines = [...nav.querySelectorAll(".sidebar-footer-line")].map((el) => el.textContent);
    expect(lines).toHaveLength(6);
    expect(lines[0]).toBe("Couldn't read 3 files");
    expect(lines.some((l) => l?.startsWith("Backup failed at "))).toBe(true);
    expect(lines.some((l) => l?.startsWith("Last backup"))).toBe(false);
  });

  it("names a prices source that is not LiteLLM", async () => {
    const server = fakeServer({ prices: pricesInfo({ source: "bundled" }) });
    await mount("#/p/builder/live", { server });
    expect(await screen.findByText("Bundled prices, October 28")).toBeInTheDocument();
  });

  it("keeps the last prices line when a later prices call fails", async () => {
    const server = fakeServer();
    await mount("#/p/builder/live", { server });
    await screen.findByText("Prices as of October 28");
    const original = server.fetch;
    server.fetch = (input, init) =>
      typeof input === "string" && input.startsWith("/api/prices")
        ? Promise.resolve(new Response("{}", { status: 503 }))
        : original(input, init);
    await act(async () => {
      window.dispatchEvent(new Event("visibilitychange"));
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(screen.getByText("Prices as of October 28")).toBeInTheDocument();
  });

  it("asks /api/app again at once when the tab becomes visible", async () => {
    const server = fakeServer();
    await mount("#/p/builder/live", { server });
    await screen.findByText("History since September 3");
    const before = server.calls.filter((c) => c.startsWith("/api/app")).length;
    await act(async () => {
      window.dispatchEvent(new Event("visibilitychange"));
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(server.calls.filter((c) => c.startsWith("/api/app")).length).toBeGreaterThan(before);
  });
});

describe("updates stopped notice", () => {
  const stopped = appInfo({
    history: historyInfo({
      pass_error: {
        code: "config_dir_unreadable",
        file: "/work/.claude/projects/a-very-long-folder-name/another-long-folder-name",
        since: "2026-11-08T15:12:00Z",
      },
    }),
  });

  it.each([1440, 375])("shows above the page on every page at %i px", async (width) => {
    for (const hash of ["#/p/builder/live", "#/p/builder/review/agents", "#/more"]) {
      await mount(hash, { width, server: fakeServer({ app: stopped }) });
      const notice = await screen.findByText(/^Updates stopped at /);
      const strip = notice.closest(".stopped-notice");
      expect(strip).not.toBeNull();
      expect(notice).toHaveTextContent(
        "because the dashboard couldn't read /work/.claude/projects/a-very-long-folder-name/another-long-folder-name, and it keeps trying again on its own.",
      );
      expect(within(notice).getByText(/another-long-folder-name$/).tagName).toBe("CODE");
      const main = document.querySelector(".shell-content");
      expect(main?.firstElementChild).toBe(strip);
      cleanup();
    }
  });

  it("says one sentence per code", async () => {
    const codes = [
      ["config_dir_missing", null, "couldn't find Claude Code's projects folder"],
      ["store_unwritable", "/work/data/db", "couldn't save to /work/data/db"],
      ["store_damaged", "/work/data/db", "database at /work/data/db failed its integrity check"],
      ["store_newer", null, "a newer Bar Tab upgraded your saved history"],
      ["unexpected", "/work/data/log", "wrote the details to /work/data/log"],
    ] as const;
    for (const [code, file, words] of codes) {
      const app = appInfo({
        history: historyInfo({ pass_error: { code, file, since: "2026-11-08T15:12:00Z" } }),
      });
      await mount("#/p/builder/live", { server: fakeServer({ app }) });
      expect(await screen.findByText(/^Updates stopped at /)).toHaveTextContent(words);
      cleanup();
    }
  });

  it("is absent with no pass error and clears on the next good pass", async () => {
    const server = fakeServer();
    await mount("#/p/builder/live", { server });
    await screen.findByRole("heading", { level: 1, name: "Live" });
    expect(screen.queryByText(/^Updates stopped at /)).toBeNull();
    server.app = stopped;
    const notice = await screen.findByText(/^Updates stopped at /, {}, { timeout: 15_000 });
    expect(notice.closest(".stopped-notice")).toHaveAttribute("role", "status");
    server.app = appInfo();
    await waitFor(
      () => {
        expect(screen.queryByText(/^Updates stopped at /)).toBeNull();
      },
      { timeout: 15_000 },
    );
  }, 40_000);

  it("is not announced when it is there from the first load", async () => {
    await mount("#/p/builder/live", { server: fakeServer({ app: stopped }) });
    const notice = await screen.findByText(/^Updates stopped at /);
    expect(notice.closest(".stopped-notice")).not.toHaveAttribute("role");
  });
});

describe("picker placeholder", () => {
  it("shows Pick a project in the sidebar Select and Bar Tab in the title on #/", async () => {
    await mount("#/");
    await screen.findByRole("dialog", { name: "Projects" });
    const button = await screen.findByRole("button", { name: /Pick a project/, hidden: true });
    expect(button).toHaveAccessibleName("Project Pick a project");
    expect(within(button).getByText("Pick a project")).toHaveAttribute("data-placeholder");
    expect(document.title).toBe("Projects, Bar Tab");
  });

  it("names Bar Tab in the top bar and Pick a project on the button at 375", async () => {
    await mount("#/", { width: 375 });
    await screen.findByRole("dialog", { name: "Projects" });
    const bar = document.querySelector(".top-bar");
    expect(bar?.querySelector(".top-bar-title")?.textContent).toBe("Bar Tab");
    const button = screen.getByRole("button", { name: "Pick a project", hidden: true });
    expect(button).toHaveAttribute("aria-expanded", "true");
  });

  it("drops the first-project fallback on the picker route only", async () => {
    await mount("#/reference/glossary");
    const sidebar = await screen.findByRole("navigation", { name: "Main" });
    expect(await within(sidebar).findByRole("button", { name: /Builder/ })).toBeInTheDocument();
  });
});

describe("More history card", () => {
  it("comes first with the rows at rest", async () => {
    await mount("#/more", { width: 375 });
    const card = await screen.findByRole("region", { name: "Your history" });
    await within(card).findByText("October 28");
    const labels = [...card.querySelectorAll("dt")].map((el) => el.textContent);
    expect(labels).toEqual(["Updated", "History since", "Last backup", "Prices as of"]);
    expect(card.querySelector("h3")).toBeNull();
    const regions = screen.getAllByRole("region").map((el) => el.getAttribute("aria-labelledby"));
    expect(regions[0]).toBe("history-card-title");
  });

  it("adds a finding with its reason for each problem", async () => {
    const app = appInfo({
      history: historyInfo({
        unreadable_files: 3,
        backup_failed: { at: "2026-11-08T09:02:00Z", reason_code: "no_space" },
      }),
    });
    await mount("#/more", { width: 375, server: fakeServer({ app }) });
    const card = await screen.findByRole("region", { name: "Your history" });
    const titles = (await within(card).findAllByRole("heading", { level: 3 })).map(
      (el) => el.textContent,
    );
    expect(titles).toEqual([expect.stringMatching(/^Backup failed at /), "Couldn't read 3 files"]);
    expect(card).toHaveTextContent("The disk was full, so the backup didn't finish.");
    expect(card).toHaveTextContent("The dashboard tries these files again on its next pass.");
    expect(card.querySelector("dd.is-warn")?.textContent).toMatch(/Backup failed at /);
  });
});
