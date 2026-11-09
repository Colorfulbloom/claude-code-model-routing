import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { postStatus } from "@/app/harness";
import { FakeChannel } from "@/app/test-channel";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { appInfo, fakeServer } from "@/test/server";

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
    expect(screen.queryByText(/^Updated /)).toBeNull();
    act(() => {
      connection.recordFailure();
    });
    expect(within(live).queryByText("Working")).toBeNull();
    expect(screen.getByText(/^Updated /)).toBeInTheDocument();
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
    const current = screen.getAllByRole("link", { current: "page" });
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAccessibleName(name);
  });

  it("hides the tab bar on the agent form routes", async () => {
    await mount("#/p/builder/review/agents/new", { width: 375 });
    await screen.findByRole("heading", { level: 1, name: "New agent" });
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(document.querySelector(".top-bar")).not.toBeNull();
  });

  it("names the project button, opens the tray, and returns focus on Escape and Close", async () => {
    const user = userEvent.setup();
    await mount("#/p/builder/live", { width: 375 });
    const trigger = await screen.findByRole("button", { name: "Project, Builder" });
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
    await user.click(await screen.findByRole("button", { name: "Project, Builder" }));
    await user.click(await screen.findByRole("option", { name: /Driftwood/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/p/driftwood/review/agents");
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows the empty state in the tray, with no command row", async () => {
    const user = userEvent.setup();
    await mount("#/p/builder/live", { width: 375, server: fakeServer({ projects: [] }) });
    await user.click(await screen.findByRole("button", { name: "Project, builder" }));
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
    expect(screen.getByText(/^Updated /)).toBeInTheDocument();
    act(() => {
      connection.recordAnswer(Date.now());
    });
    expect(screen.queryByText(/^Updated /)).toBeNull();
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
