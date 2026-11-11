import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { Spark } from "../Spark/Spark";
import { Tile, states } from "./Tile";

afterEach(cleanup);

describe("Tile", () => {
  it("lists its states", () => {
    expect(states).toEqual([
      "default",
      "proof",
      "unpriced",
      "loading",
      "link",
      "help",
      "link-help",
    ]);
  });

  it("shows label, qualifier, value, delta and note", () => {
    render(
      <Tile
        label="Spent so far"
        qualifier="API-rate estimate"
        value="$7.05"
        delta="$0.44 in the last minute"
        note="12 requests have no price"
      />,
    );
    expect(screen.getByText("Spent so far")).toBeInTheDocument();
    expect(screen.getByText("API-rate estimate")).toBeInTheDocument();
    expect(screen.getByText("$7.05")).toBeInTheDocument();
    expect(screen.getByText(/\$0\.44 in the last minute/)).toBeInTheDocument();
    expect(screen.getByText("12 requests have no price")).toBeInTheDocument();
  });

  it("keeps the proof out of the accessibility tree", () => {
    const { container } = render(
      <Tile label="Tokens" value="5.3M" delta="334K" proof={<Spark values={[1, 2]} />} />,
    );
    expect(container.querySelector('[aria-hidden="true"]')).not.toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("swaps the value and delta for bones and the loading line while loading", () => {
    const { container } = render(
      <Tile label="Tokens" value="5.3M" delta="334K" loading={{ label: "Loading sessions" }} />,
    );
    expect(screen.queryByText("5.3M")).toBeNull();
    expect(screen.queryByText("334K")).toBeNull();
    expect(screen.getByText("Loading sessions")).toBeInTheDocument();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it("is a link when it opens a page", () => {
    render(<Tile label="Tokens" value="5.3M" delta="334K" href="#summary" />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "#summary");
    expect(screen.getByRole("link")).toHaveTextContent("Tokens");
  });

  it("is plain text without an href", () => {
    render(<Tile label="Tokens" value="5.3M" delta="334K" />);
    expect(screen.queryByRole("link")).toBeNull();
  });

  describe("as a link", () => {
    it("names the link by the label alone, with the numbers outside it", () => {
      render(
        <Tile
          label="Tokens"
          qualifier="API-rate estimate"
          value="5.3M"
          delta="334K in the last minute"
          note="12 requests have no price"
          href="#summary"
        />,
      );
      const link = screen.getByRole("link", { name: "Tokens" });
      expect(link.textContent).toBe("Tokens");
      for (const text of ["5.3M", "334K in the last minute", "12 requests have no price"]) {
        expect(screen.getByText(text, { exact: false }).closest("a")).toBeNull();
      }
    });

    it("keeps value, delta and note after the link in the DOM, as plain text", () => {
      const { container } = render(
        <Tile label="Tokens" value="5.3M" delta="334K" href="#summary" />,
      );
      const link = container.querySelector("a");
      const value = screen.getByText("5.3M");
      expect(link?.compareDocumentPosition(value)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    });
  });

  describe("with help", () => {
    it("draws a help button named About and the entry title, as the end of the label row", () => {
      const { container } = render(
        <Tile label="Read from cache" value="78%" delta="81%" help={{ id: "live.cache" }} />,
      );
      const button = screen.getByRole("button", { name: "About Read from cache" });
      expect(button).toHaveAttribute("aria-haspopup", "dialog");
      expect(button.closest(".tile-label")).not.toBeNull();
      expect(container.querySelector(".tile-label")?.lastElementChild).toBe(button);
    });

    it("opens the entry with the tile's own values beside their lines", async () => {
      const user = userEvent.setup();
      render(
        <Tile
          label="Read from cache"
          value="78%"
          delta="81% in the last minute"
          help={{ id: "live.cache", values: { value: "78%", delta: "81%" } }}
        />,
      );
      await user.click(screen.getByRole("button", { name: "About Read from cache" }));
      const dialog = screen.getByRole("dialog", { name: "Read from cache" });
      expect(within(dialog).getByText("78%")).toBeInTheDocument();
      expect(within(dialog).getByText("81%")).toBeInTheDocument();
    });

    it("stays open on the tile's new values when Live polls and the tile re-renders", async () => {
      const user = userEvent.setup();
      const tile = (value: string) => (
        <Tile
          label="Read from cache"
          value={value}
          delta="81% in the last minute"
          href="#cache"
          help={{ id: "live.cache", values: { value, delta: "81%" } }}
        />
      );
      const { rerender } = render(tile("78%"));
      const button = screen.getByRole("button", { name: "About Read from cache" });
      await user.click(button);
      const dialog = screen.getByRole("dialog");
      rerender(tile("79%"));
      rerender(tile("80%"));
      expect(screen.getByRole("dialog")).toBe(dialog);
      expect(dialog).toHaveFocus();
      expect(screen.getByRole("button", { name: "About Read from cache", hidden: true })).toBe(
        button,
      );
      expect(within(dialog).getByText("80%")).toBeInTheDocument();
    });

    it("has no help button without a help prop", () => {
      render(<Tile label="Tokens" value="5.3M" delta="334K" />);
      expect(screen.queryByRole("button")).toBeNull();
    });
  });

  describe("as a link with help", () => {
    function renderBoth() {
      window.location.hash = "";
      return render(
        <Tile
          label="Read from cache"
          value="78%"
          delta="81%"
          href="#cache"
          help={{ id: "live.cache" }}
        />,
      );
    }

    it("does not put the help button inside the link", () => {
      renderBoth();
      const link = screen.getByRole("link", { name: "Read from cache" });
      const button = screen.getByRole("button", { name: "About Read from cache" });
      expect(link.contains(button)).toBe(false);
      expect(button.closest("a")).toBeNull();
    });

    it("tabs to the link first and then to the help button", async () => {
      const user = userEvent.setup();
      renderBoth();
      await user.tab();
      expect(screen.getByRole("link", { name: "Read from cache" })).toHaveFocus();
      await user.tab();
      expect(screen.getByRole("button", { name: "About Read from cache" })).toHaveFocus();
    });

    it("opens help from the button and does not navigate", async () => {
      const user = userEvent.setup();
      renderBoth();
      await user.click(screen.getByRole("button", { name: "About Read from cache" }));
      expect(screen.getByRole("dialog", { name: "Read from cache" })).toBeVisible();
      expect(window.location.hash).toBe("");
    });
  });
});

/*
 * jsdom has no layout, so it cannot hit-test the ::after layer that stretches the link over the
 * tile. The click on the value and the click on the "?" in a real browser are in e2e/help.spec.ts.
 */
