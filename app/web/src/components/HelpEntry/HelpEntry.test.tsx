import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { en } from "@/strings/en";
import { GLOSSARY } from "@/strings/glossary";
import { type HelpEntry as HelpEntryData } from "@/strings/help";
import { LISTS } from "@/strings/lists";
import { t } from "@/strings/t";
import { HelpEntry, states } from "./HelpEntry";
import { setReturnFocus, takeReturnFocus } from "./origin";

afterEach(cleanup);

/*
 * The tests draw their own entries through `source`, so they hold when the copy deck changes a
 * registry entry. The registry's own shape is guarded in strings/help.test.ts.
 */
const FIXTURE: HelpEntryData = {
  title: "Fixture",
  kind: "tile",
  shows: "Shows sentence for the fixture.",
  lines: [
    { label: "Percent", means: "the first thing.", ref: "value" },
    { label: "In the minute", means: "the second thing.", ref: "delta" },
  ],
  reading: "Reading sentence for the fixture.",
  glossary: ["read-from-cache", "cache-write"],
};

const BARE: HelpEntryData = { title: "Bare", kind: "other" };

describe("HelpEntry", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["full", "list-status", "list-scopes", "no-glossary"]);
  });

  it("draws shows, then the numbers, then how to read it, then the links, in that order", () => {
    const { container } = render(
      <HelpEntry help="live.cache" source={FIXTURE} values={{ value: "78%" }} />,
    );
    const text = container.textContent ?? "";
    const order = [
      "Shows sentence",
      en.hp_numbers,
      "The first thing",
      en.hp_reading,
      "Reading sentence",
      "in the glossary",
    ].map((needle) => text.indexOf(needle));
    expect(order.every((at) => at >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
  });

  it("puts a passed value beside its line, and leaves a line without a value bare", () => {
    render(<HelpEntry help="live.cache" source={FIXTURE} values={{ value: "78%" }} />);
    const first = screen.getByText("Percent").closest("div");
    expect(within(first as HTMLElement).getByText("78%")).toBeInTheDocument();
    const second = screen.getByText("In the minute").closest("div");
    expect(within(second as HTMLElement).queryByText("78%")).toBeNull();
  });

  it("labels the lines with the numbers heading when a value is passed", () => {
    render(<HelpEntry help="live.cache" source={FIXTURE} values={{ value: "78%" }} />);
    expect(screen.getByRole("heading", { level: 3, name: en.hp_numbers })).toBeVisible();
  });

  it("labels the lines with the same heading when no value is passed", () => {
    // The shows paragraph already says what the spot shows, so the lines never take that label.
    render(<HelpEntry help="live.cache" source={FIXTURE} />);
    expect(screen.getByRole("heading", { level: 3, name: en.hp_numbers })).toBeVisible();
  });

  it("starts each line's meaning with a capital", () => {
    render(<HelpEntry help="live.cache" source={FIXTURE} />);
    expect(screen.getByText("The first thing.")).toBeInTheDocument();
  });

  it("marks the line it is given as This column, once", () => {
    render(<HelpEntry help="live.cache" source={FIXTURE} line="Percent" />);
    expect(screen.getAllByText(en.hp_this_column)).toHaveLength(1);
    expect(screen.getByText(en.hp_this_column).closest("div")).toHaveTextContent("Percent");
  });

  it("marks the line whose label is the word, as Shown here, when the entry has no list", () => {
    render(<HelpEntry help="live.status" word="Idle" />);
    expect(screen.getAllByText(en.hp_this_setting)).toHaveLength(1);
    expect(screen.queryByText(en.hp_this_column)).toBeNull();
    expect(screen.getByText(en.hp_this_setting).closest(".hp-row")).toHaveTextContent("Idle");
  });

  it("leaves a lines entry unmarked when the word matches no label", () => {
    render(<HelpEntry help="live.status" word="Nothing like it" />);
    expect(screen.queryByText(en.hp_this_setting)).toBeNull();
  });

  it("marks nothing when the line does not match", () => {
    render(<HelpEntry help="live.cache" source={FIXTURE} line="Nothing like it" />);
    expect(screen.queryByText(en.hp_this_column)).toBeNull();
  });

  it("draws the status list with a chip and the shared meaning for every word, and marks one", () => {
    const { container } = render(
      <HelpEntry help="agents.check" source={{ ...BARE, list: "status" }} word="overridden" />,
    );
    expect(screen.getByRole("heading", { level: 3, name: en.hp_list_status })).toBeVisible();
    expect(container.querySelectorAll(".status-chip")).toHaveLength(LISTS.status.length);
    for (const item of LISTS.status) {
      expect(screen.getByText(en[item.word])).toBeInTheDocument();
      if (item.means !== undefined) expect(screen.getByText(en[item.means])).toBeInTheDocument();
    }
    expect(screen.getAllByText(en.hp_this_setting)).toHaveLength(1);
    expect(screen.getByText(en.hp_this_setting).closest("div")).toHaveTextContent(
      en.status_overridden,
    );
  });

  it("draws a non-status list as words, with no chips", () => {
    const { container } = render(
      <HelpEntry help="setup.scopes" source={{ ...BARE, list: "scopes" }} word="user" />,
    );
    expect(screen.getByRole("heading", { level: 3, name: en.hp_list_scopes })).toBeVisible();
    expect(container.querySelector(".status-chip")).toBeNull();
    for (const item of LISTS.scopes) expect(screen.getByText(en[item.word])).toBeInTheDocument();
    expect(screen.getByText(en.hp_this_setting).closest("div")).toHaveTextContent(en.sc_user);
  });

  it("labels each shared list with its own heading", () => {
    for (const [list, label] of [
      ["confidence", en.hp_list_confidence],
      ["project_state", en.hp_list_project_state],
    ] as const) {
      const { unmount } = render(<HelpEntry help="live.cache" source={{ ...BARE, list }} />);
      expect(screen.getByRole("heading", { level: 3, name: label })).toBeVisible();
      unmount();
    }
  });

  it("draws one glossary link per term that exists, named for the term", () => {
    render(<HelpEntry help="live.cache" source={FIXTURE} />);
    for (const id of ["read-from-cache", "cache-write"] as const) {
      const link = screen.getByRole("link", {
        name: t("hp_glossary_link", { term: GLOSSARY[id].term }),
      });
      expect(link).toHaveAttribute("href", `#/reference/glossary/${id}`);
    }
  });

  describe("origin", () => {
    it("hands the help id to the page Back names, and to no other page", () => {
      setReturnFocus("live.cache", "#/p/builder/live?session=s1");
      expect(takeReturnFocus("/p/builder/live")).toBe("live.cache");
      expect(takeReturnFocus("/p/builder/live")).toBeNull();
      setReturnFocus("live.cache", "#/p/builder/live");
      expect(takeReturnFocus("/p/builder/summary")).toBeNull();
      expect(takeReturnFocus("/p/builder/live")).toBeNull();
      setReturnFocus(null, "#/p/builder/live");
      expect(takeReturnFocus("/p/builder/live")).toBeNull();
    });

    afterEach(() => {
      history.replaceState(null, "", "/");
    });

    it("adds the route it is on and the help id to each glossary link", () => {
      history.replaceState(null, "", "/#/p/builder/live?session=s1");
      render(<HelpEntry help="live.cache" source={FIXTURE} />);
      const link = screen.getByRole("link", {
        name: t("hp_glossary_link", { term: GLOSSARY["cache-write"].term }),
      });
      const href = link.getAttribute("href") ?? "";
      expect(href.startsWith("#/reference/glossary/cache-write?")).toBe(true);
      const query = new URLSearchParams(href.slice(href.indexOf("?")));
      expect(query.get("from")).toBe("/p/builder/live?session=s1");
      expect(query.get("help")).toBe("live.cache");
    });

    it("adds nothing on a Reference page or with no route", () => {
      history.replaceState(null, "", "/#/reference/decides");
      const { unmount } = render(<HelpEntry help="live.cache" source={FIXTURE} />);
      expect(screen.getAllByRole("link")[0]).toHaveAttribute(
        "href",
        "#/reference/glossary/read-from-cache",
      );
      unmount();
      history.replaceState(null, "", "/");
      render(<HelpEntry help="live.cache" source={FIXTURE} />);
      expect(screen.getAllByRole("link")[0]).toHaveAttribute(
        "href",
        "#/reference/glossary/read-from-cache",
      );
    });
  });

  it("does not render a link to a term the glossary lacks", () => {
    render(<HelpEntry help="live.cache" source={FIXTURE} termExists={() => false} />);
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("skips a missing term and keeps the others", () => {
    render(
      <HelpEntry help="live.cache" source={FIXTURE} termExists={(id) => id === "cache-write"} />,
    );
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("draws no section for a part the entry does not have", () => {
    render(<HelpEntry help="live.cache" source={BARE} />);
    expect(screen.queryByRole("heading")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("reads the registry when no source is given", () => {
    render(<HelpEntry help="agents.check" word="invalid" />);
    expect(screen.getByRole("heading", { level: 3, name: en.hp_list_status })).toBeVisible();
    expect(screen.getAllByText(en.hp_this_setting)).toHaveLength(1);
  });
});
