import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ListInspector, states, type ListInspectorProps } from "./ListInspector";
import type { InspectorItem } from "./types";

afterEach(cleanup);

const items: InspectorItem[] = [
  {
    id: "settings:model",
    name: "Model",
    href: "#/setup/settings/model",
    value: { text: "Opus 5.5" },
    status: { status: "in_effect", label: "In effect" },
  },
  {
    id: "settings:effortLevel",
    name: "Effort",
    href: "#/setup/settings/effortLevel",
    value: { text: "high" },
    status: { status: "lowered", label: "Lowered" },
  },
  {
    id: "settings:availableModels",
    name: "Allowed models",
    href: "#/setup/settings/availableModels",
    value: { text: "Opus 5.5, Sonnet 5.5" },
    status: { status: "in_effect", label: "In effect" },
    locked: true,
  },
];

function props(extra: Partial<ListInspectorProps> = {}): ListInspectorProps {
  return {
    list: {
      title: "Settings",
      count: "3",
      items,
      selectedId: "settings:effortLevel",
      lockLabel: "Read only",
      maskedLabel: "Masked",
      notReadLabel: "Not read here",
    },
    inspector: {
      title: "Effort",
      status: { status: "lowered", label: "Lowered" },
      runs: "Runs at high",
      setTo: "Set to xhigh in Project local, settings.local.json line 3.",
      where: {
        title: "Where it's set, top wins",
        maskedLabel: "Masked",
        rows: [
          {
            id: "local",
            scope: { name: "Project local", meaning: "Just you, this project" },
            key: "effortLevel",
            value: { text: "xhigh" },
            status: { status: "lowered", label: "Lowered" },
            location: "settings.local.json:3",
          },
          {
            id: "project",
            scope: { name: "Shared project", meaning: "Everyone in this project" },
            key: "effortLevel",
            value: { text: "medium" },
            status: { status: "overridden", label: "Overridden" },
            location: "settings.json:7",
          },
          {
            id: "shell",
            scope: { name: "Your shell", meaning: "When Bar Tab started" },
            note: "Not visible here",
          },
        ],
      },
      why: {
        title: "Why",
        body: "When an effort cap is set, any higher effort runs at the cap.",
        confidence: "Based on Claude Code's docs and tested on 2.1.302.",
      },
      usage: "In the last 30 days, all 53 main sessions ran at high.",
      actions: <button type="button">Copy path</button>,
    },
    ...extra,
  };
}

describe("ListInspector", () => {
  it("lists every sheet state once", () => {
    expect(new Set(states).size).toBe(states.length);
    expect(states).toContain("phone-inspector");
  });

  describe("the list", () => {
    it("is a nav named by its h2, with one link and one URL per item", () => {
      render(<ListInspector {...props()} />);
      const nav = screen.getByRole("navigation", { name: "Settings" });
      expect(within(nav).getByRole("heading", { level: 2, name: "Settings" })).toBeInTheDocument();
      const links = within(nav).getAllByRole("link");
      expect(links.map((link) => link.getAttribute("href"))).toEqual([
        "#/setup/settings/model",
        "#/setup/settings/effortLevel",
        "#/setup/settings/availableModels",
      ]);
    });

    it("shows name, value and status word on each row", () => {
      render(<ListInspector {...props()} />);
      const row = screen.getByRole("link", { name: /^Model/ });
      expect(row).toHaveTextContent("Opus 5.5");
      expect(row).toHaveTextContent("In effect");
    });

    it("marks only the picked item with the chosen state and aria-current", () => {
      render(<ListInspector {...props()} />);
      const picked = screen.getByRole("link", { name: /^Effort/ });
      expect(picked).toHaveAttribute("aria-current", "page");
      expect(picked).toHaveClass("chosen-row");
      for (const name of [/^Model/, /^Allowed models/]) {
        const other = screen.getByRole("link", { name });
        expect(other).not.toHaveAttribute("aria-current");
        expect(other).not.toHaveClass("chosen-row");
      }
    });

    it("puts the lock word in the accessible name of a read-only item", () => {
      render(<ListInspector {...props()} />);
      expect(screen.getByRole("link", { name: /Allowed models.*Read only/ })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /^Model/ })).not.toHaveTextContent("Read only");
    });

    it("keeps a stable DOM node per item id when values change", () => {
      const { rerender } = render(<ListInspector {...props()} />);
      const before = screen.getByRole("link", { name: /^Effort/ });
      rerender(
        <ListInspector
          {...props({
            list: {
              ...props().list,
              items: items.map((item) =>
                item.id === "settings:effortLevel" ? { ...item, value: { text: "medium" } } : item,
              ),
            },
          })}
        />,
      );
      const after = screen.getByRole("link", { name: /^Effort/ });
      expect(after).toBe(before);
      expect(after).toHaveTextContent("medium");
    });

    it("shows a masked value with a visible masked word in the accessible name", () => {
      const list = {
        ...props().list,
        items: [
          {
            id: "mcp:docs",
            name: "docs-search",
            href: "#/setup/mcp/docs",
            value: { text: "API_KEY=abc…", masked: true },
          },
        ],
      };
      render(<ListInspector {...props({ list, inspector: null })} />);
      const link = screen.getByRole("link", { name: /docs-search/ });
      expect(link).toHaveAccessibleName(/API_KEY=abc….*Masked/);
    });

    it("shows a not-read item with its own words, not the Unknown chip or a failure", () => {
      const list = {
        ...props().list,
        items: [
          {
            id: "instructions:other",
            name: "docs/OTHER.md",
            href: "#/setup/instructions/other",
            notRead: true,
            status: { status: "unknown" as const, label: "Unknown" },
          },
        ],
      };
      const { container } = render(<ListInspector {...props({ list, inspector: null })} />);
      const link = screen.getByRole("link", { name: /docs\/OTHER.md/ });
      expect(link).toHaveTextContent("Not read here");
      expect(link).not.toHaveTextContent("Unknown");
      expect(container.querySelector(".status-chip")).toBeNull();
      expect(container.querySelector(".item-not-read-mark")).toHaveAttribute("aria-hidden", "true");
    });

    it("shows one sentence and one action when empty", () => {
      const list = {
        ...props().list,
        items: [],
        count: "0",
        empty: {
          text: "No hooks yet. Hooks you add show up here.",
          actionLabel: "Open the docs",
          href: "#/docs/hooks",
        },
      };
      render(<ListInspector {...props({ list, inspector: null })} />);
      expect(screen.getByText("No hooks yet. Hooks you add show up here.")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Open the docs" })).toHaveAttribute(
        "href",
        "#/docs/hooks",
      );
      expect(screen.queryByRole("list")).toBeNull();
    });

    it("draws group headings with counts, in order", () => {
      const grouped = items.map((item, i) => ({ ...item, group: i < 2 ? "allow" : "deny" }));
      const list = {
        ...props().list,
        items: grouped,
        groups: [
          { key: "allow", label: "Allow", count: "2" },
          { key: "deny", label: "Deny", count: "1" },
        ],
      };
      render(<ListInspector {...props({ list, inspector: null })} />);
      const headings = screen.getAllByRole("heading", { level: 3 });
      expect(headings.map((h) => h.textContent)).toEqual(["Allow 2", "Deny 1"]);
      const lists = screen.getAllByRole("list");
      expect(lists.map((list) => within(list).getAllByRole("link").length)).toEqual([2, 1]);
    });

    it("leaves out a group with no items", () => {
      const list = {
        ...props().list,
        items: items.map((item) => ({ ...item, group: "allow" })),
        groups: [
          { key: "allow", label: "Allow", count: "3" },
          { key: "deny", label: "Deny", count: "0" },
        ],
      };
      render(<ListInspector {...props({ list })} />);
      expect(screen.queryByRole("heading", { level: 3, name: /Deny/ })).toBeNull();
    });
  });

  describe("the inspector", () => {
    it("is a region named by its h2, with the status beside it", () => {
      render(<ListInspector {...props()} />);
      const region = screen.getByRole("region", { name: "Effort" });
      const heading = within(region).getByRole("heading", { level: 2, name: "Effort" });
      expect(heading).toHaveAttribute("tabindex", "-1");
      expect(region).toHaveTextContent("Lowered");
    });

    it("fills the runs, set-to, where-set, Why, usage and actions slots", () => {
      render(<ListInspector {...props()} />);
      const region = screen.getByRole("region", { name: "Effort" });
      expect(within(region).getByText("Runs at high")).toBeInTheDocument();
      expect(within(region).getByText(/^Set to xhigh/)).toBeInTheDocument();
      expect(
        within(region).getByRole("heading", { level: 3, name: "Where it's set, top wins" }),
      ).toBeInTheDocument();
      expect(within(region).getByRole("heading", { level: 3, name: "Why" })).toBeInTheDocument();
      expect(within(region).getByText(/tested on 2.1.302/)).toBeInTheDocument();
      expect(within(region).getByText(/all 53 main sessions/)).toBeInTheDocument();
      expect(within(region).getByRole("button", { name: "Copy path" })).toBeInTheDocument();
    });

    it("lists the where-set rows in the order given, with scope label, key, value and place", () => {
      render(<ListInspector {...props()} />);
      const rows = screen
        .getAllByRole("listitem")
        .filter((li) => li.classList.contains("where-row"));
      expect(rows).toHaveLength(3);
      expect(rows[0]).toHaveTextContent("Project local");
      expect(rows[0]).toHaveTextContent("Just you, this project");
      expect(rows[0]).toHaveTextContent("effortLevel");
      expect(rows[0]).toHaveTextContent("xhigh");
      expect(rows[0]).toHaveTextContent("settings.local.json:3");
      expect(rows[1]).toHaveTextContent("Shared project");
      expect(rows[2]).toHaveTextContent("Not visible here");
    });

    it("shows a read-only box with the lock word, the reason, a command and Copy path", () => {
      const base = props();
      const inspector = {
        ...(base.inspector ?? { title: "Servers" }),
        readOnly: {
          lockLabel: "Read only",
          reason: "This server is set at user scope, so the dashboard can't change it.",
          command: {
            command: "claude mcp remove docs-search --scope user",
            copyLabel: "Copy command",
            copiedLabel: "Copied to clipboard",
          },
          path: { value: "/work/home/.mcp.json", label: "Copy path", copiedLabel: "Copied" },
        },
      };
      render(<ListInspector {...props({ inspector })} />);
      expect(screen.getByText(/This server is set at user scope/)).toBeInTheDocument();
      expect(screen.getByText(/^Read only\./)).toHaveClass("sr-only");
      expect(screen.getByText("claude mcp remove docs-search --scope user")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Copy command" })).toBeInTheDocument();
      expect(screen.getAllByRole("button", { name: "Copy path" })).toHaveLength(2);
    });

    it("shows an item the server did not read as a raised box with the Unknown pill", () => {
      const inspector = {
        title: "team-tools",
        runs: "Bar Tab can't tell what this plugin adds",
        notRead: {
          status: { status: "unknown" as const, label: "Unknown" },
          body: "It's installed outside your Claude plugins folder, so Bar Tab doesn't read it.",
        },
        check: <p>Check callout</p>,
      };
      const { container } = render(<ListInspector {...props({ inspector })} />);
      const box = container.querySelector(".inspector-not-read");
      expect(box).not.toBeNull();
      expect(box?.querySelector(".status-chip-unknown")).toHaveTextContent("Unknown");
      expect(box).toHaveTextContent(/installed outside your Claude plugins folder/);
      expect(container.querySelector(".item-not-read-mark")).toBeNull();
      expect(screen.queryByRole("heading", { level: 3 })).toBeNull();
      expect(screen.queryByRole("alert")).toBeNull();
      // The box and the check callout sit below the headline, in that order.
      const body = container.querySelector(".inspector-body")?.textContent ?? "";
      const order = ["can't tell what this plugin adds", "Unknown", "Check callout"].map((text) =>
        body.indexOf(text),
      );
      expect(order).toEqual([...order].sort((a, b) => a - b));
      expect(order.every((at) => at >= 0)).toBe(true);
    });

    it("leaves out slots it has no words for", () => {
      render(<ListInspector {...props({ inspector: { title: "Effort" } })} />);
      expect(screen.queryByRole("heading", { level: 3 })).toBeNull();
    });
  });

  describe("focus and phone mode", () => {
    it("moves focus to the inspector h2 when an item opens with Enter", async () => {
      const user = userEvent.setup();
      const onOpen = vi.fn();
      render(<ListInspector {...props({ onOpen })} />);
      screen.getByRole("link", { name: /^Model/ }).focus();
      await user.keyboard("{Enter}");
      expect(onOpen).toHaveBeenCalledWith("settings:model");
      await Promise.resolve();
      expect(screen.getByRole("heading", { level: 2, name: "Effort" })).toHaveFocus();
    });

    it("tabs through the items in order", async () => {
      const user = userEvent.setup();
      render(<ListInspector {...props()} />);
      await user.tab();
      expect(screen.getByRole("link", { name: /^Model/ })).toHaveFocus();
      await user.tab();
      expect(screen.getByRole("link", { name: /^Effort/ })).toHaveFocus();
    });

    it("shows only the list in list mode", () => {
      render(<ListInspector {...props({ mode: "list" })} />);
      expect(screen.getByRole("navigation", { name: "Settings" })).toBeInTheDocument();
      expect(screen.queryByRole("region", { name: "Effort" })).toBeNull();
    });

    it("shows only the inspector in inspector mode, with a back link and focus on the h2", () => {
      render(
        <ListInspector
          {...props({ mode: "inspector", back: { label: "Settings", href: "#/setup/settings" } })}
        />,
      );
      expect(screen.queryByRole("navigation", { name: "Settings" })).toBeNull();
      expect(screen.getByRole("link", { name: /Settings/ })).toHaveAttribute(
        "href",
        "#/setup/settings",
      );
      expect(screen.getByRole("heading", { level: 2, name: "Effort" })).toHaveFocus();
    });

    it("draws nothing for the inspector while nothing is picked", () => {
      render(<ListInspector {...props({ inspector: null })} />);
      expect(screen.queryByRole("region")).toBeNull();
    });
  });
});

describe("ListInspector additions for the setup pages", () => {
  const listOf = (extra: Partial<ListInspectorProps["list"]> = {}): ListInspectorProps["list"] => ({
    ...props().list,
    ...extra,
  });

  it("draws a finding above the rows, inside the nav", () => {
    render(<ListInspector {...props({ list: listOf({ pre: <p>Couldn't read 1 file</p> }) })} />);
    const nav = screen.getByRole("navigation", { name: "Settings" });
    const note = within(nav).getByText("Couldn't read 1 file");
    const first = within(nav).getAllByRole("link")[0];
    if (first === undefined) throw new Error("no rows");
    expect(note.compareDocumentPosition(first)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("gives a group a Show n more button that calls its handler", async () => {
    const onPress = vi.fn();
    const grouped = items.map((item) => ({ ...item, group: "all" }));
    render(
      <ListInspector
        {...props({
          list: listOf({
            items: grouped,
            groups: [
              { key: "all", label: "All", count: "9", more: { label: "Show 6 more", onPress } },
            ],
          }),
        })}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Show 6 more" }));
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it("makes each group a section with a focusable heading, for Jump to chips", () => {
    const grouped = items.map((item, n) => ({ ...item, group: n === 0 ? "a" : "b" }));
    render(
      <ListInspector
        {...props({
          list: listOf({
            items: grouped,
            groups: [
              { key: "a", label: "Allow", count: "1" },
              { key: "b", label: "Deny", count: "2" },
            ],
          }),
        })}
      />,
    );
    const heading = screen.getByRole("heading", { level: 3, name: /^Deny/ });
    expect(heading).toHaveAttribute("tabindex", "-1");
    expect(heading.closest("section")).toHaveAttribute("data-group", "b");
  });

  it("shows Jump to chips that call their handlers", async () => {
    const onPress = vi.fn();
    render(
      <ListInspector
        {...props({
          list: listOf({
            jump: {
              label: "Jump to",
              chips: [{ key: "deny", label: "Deny", count: "4", onPress }],
            },
          }),
        })}
      />,
    );
    expect(screen.getByText("Jump to")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Deny 4" }));
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it("shows an empty list with no action when it has no action label", () => {
    render(
      <ListInspector
        {...props({ list: listOf({ items: [], empty: { text: "Nothing here." } }) })}
      />,
    );
    expect(screen.getByText("Nothing here.")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Settings" });
    expect(within(nav).queryByRole("button")).toBeNull();
    expect(within(nav).queryByRole("link")).toBeNull();
  });

  it("draws the details slot in the inspector, between the read-only box and the where well", () => {
    const { inspector } = props();
    if (inspector === null || inspector === undefined) throw new Error("no inspector");
    render(
      <ListInspector
        {...props({
          inspector: {
            ...inspector,
            readOnly: { lockLabel: "Read only", reason: "Managed by your organization." },
            details: <p>Facts about the item</p>,
          },
        })}
      />,
    );
    const region = screen.getByRole("region", { name: "Effort" });
    const readOnly = within(region).getByText("Managed by your organization.");
    const details = within(region).getByText("Facts about the item");
    const where = within(region).getByText("Where it's set, top wins");
    expect(
      readOnly.compareDocumentPosition(details) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(details.compareDocumentPosition(where) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("help in the inspector", () => {
  it("marks the status word on the pill's button, and gives Where and Why a term", async () => {
    const user = userEvent.setup();
    render(<ListInspector {...props()} />);
    const region = screen.getByRole("region", { name: "Effort" });
    expect(
      within(region).getByRole("button", { name: "Where it's set, top wins" }),
    ).toHaveAttribute("data-help-id", "setup.where");
    expect(within(region).getByRole("heading", { level: 3, name: "Why" })).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: "Why" })).toHaveAttribute(
      "data-help-id",
      "setup.why",
    );
    await user.click(within(region).getByRole("button", { name: "About Status" }));
    const dialog = await screen.findByRole("dialog", { name: "Status" });
    expect(within(dialog).getByText("Shown here").closest(".hp-row")).toHaveTextContent("Lowered");
  });
});
