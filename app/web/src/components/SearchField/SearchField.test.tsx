import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SearchField, states } from "./SearchField";

afterEach(cleanup);

/*
 * The announce wait runs on real timers with a short delay. React Testing Library's async helpers
 * wait on setTimeout, so fake timers would stall every user event.
 */
const sleep = (ms: number) =>
  act(async () => {
    await new Promise((done) => setTimeout(done, ms));
  });

interface HarnessProps {
  initial?: string;
  announceFor?: (value: string) => string | undefined;
  delay?: number;
}

function Harness({ initial = "", announceFor, delay }: HarnessProps) {
  const [value, setValue] = useState(initial);
  const text = announceFor?.(value);
  return (
    <SearchField
      label="Search rules"
      clearLabel="Clear search"
      value={value}
      onChange={setValue}
      {...(text === undefined ? {} : { count: text, announce: text })}
      {...(delay === undefined ? {} : { delay })}
    />
  );
}

const byLength = (value: string) =>
  value === "" ? "84 rules" : `${String(value.length)} of 84 rules`;

describe("SearchField", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["empty", "typed", "no-results"]);
  });

  it("has a visible label that names the field", () => {
    render(<Harness />);
    expect(screen.getByText("Search rules")).toBeVisible();
    expect(screen.getByRole("searchbox", { name: "Search rules" })).toBeInTheDocument();
  });

  it("marks the field empty until there is text, which is when the clear button hides", async () => {
    const user = userEvent.setup();
    const { container } = render(<Harness />);
    const field = container.querySelector(".search-field");
    expect(field).toHaveAttribute("data-empty", "true");
    await user.type(screen.getByRole("searchbox"), "a");
    expect(field).not.toHaveAttribute("data-empty");
    expect(screen.getByRole("button", { name: "Clear search" })).toBeInTheDocument();
  });

  it("calls back with the typed text", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SearchField label="Search" clearLabel="Clear" value="" onChange={onChange} />);
    await user.type(screen.getByRole("searchbox"), "c");
    expect(onChange).toHaveBeenCalledWith("c");
  });

  it("clears with Escape and keeps focus in the field", async () => {
    const user = userEvent.setup();
    render(<Harness initial="cache" />);
    const input = screen.getByRole("searchbox");
    input.focus();
    await user.keyboard("{Escape}");
    expect(input).toHaveValue("");
    expect(input).toHaveFocus();
  });

  it("does nothing on Enter", async () => {
    const user = userEvent.setup();
    render(<Harness initial="cache" />);
    const input = screen.getByRole("searchbox");
    input.focus();
    await user.keyboard("{Enter}");
    expect(input).toHaveValue("cache");
    expect(input).toHaveFocus();
  });

  it("clears with the clear button", async () => {
    const user = userEvent.setup();
    render(<Harness initial="cache" />);
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(screen.getByRole("searchbox")).toHaveValue("");
  });

  it("shows the count as plain text outside any live region", () => {
    render(<Harness initial="cache" announceFor={byLength} />);
    const count = screen.getByText("5 of 84 rules", { selector: "p" });
    expect(count).toBeVisible();
    expect(count.closest("[aria-live]")).toBeNull();
    expect(count.closest("[role='status']")).toBeNull();
  });

  describe("the status region", () => {
    it("is one polite status region, empty on first render", () => {
      render(<Harness initial="cache" announceFor={byLength} />);
      expect(screen.getAllByRole("status")).toHaveLength(1);
      expect(screen.getByRole("status")).toBeEmptyDOMElement();
      expect(screen.getByRole("status")).toHaveClass("sr-only");
    });

    it("says nothing on first render even after the delay passes", async () => {
      render(<Harness initial="cache" announceFor={byLength} delay={30} />);
      await sleep(120);
      expect(screen.getByRole("status")).toBeEmptyDOMElement();
    });

    it("treats the first text after a loading wait as the baseline, and says nothing for it", async () => {
      // A page gives the field no text while its data loads, then the first count.
      const field = (props: { value: string; text?: string }) => (
        <SearchField
          label="Search rules"
          clearLabel="Clear search"
          value={props.value}
          onChange={() => undefined}
          delay={30}
          {...(props.text === undefined ? {} : { count: props.text, announce: props.text })}
        />
      );
      const { rerender } = render(field({ value: "" }));
      rerender(field({ value: "", text: "84 rules shown" }));
      await sleep(120);
      expect(screen.getByRole("status")).toBeEmptyDOMElement();
      rerender(field({ value: "a", text: "5 of 84 rules shown" }));
      await waitFor(() => {
        expect(screen.getByRole("status")).toHaveTextContent("5 of 84 rules shown");
      });
    });

    it("announces only after the delay since the last change", async () => {
      const user = userEvent.setup();
      render(<Harness announceFor={byLength} delay={300} />);
      await user.type(screen.getByRole("searchbox"), "ca");
      expect(screen.getByRole("status")).toBeEmptyDOMElement();
      await sleep(150);
      expect(screen.getByRole("status")).toBeEmptyDOMElement();
      await waitFor(
        () => {
          expect(screen.getByRole("status")).toHaveTextContent("2 of 84 rules");
        },
        { timeout: 1500 },
      );
    });

    it("restarts the wait on each change, so it says the final text once", async () => {
      const user = userEvent.setup();
      render(<Harness announceFor={byLength} delay={300} />);
      const input = screen.getByRole("searchbox");
      await user.type(input, "c");
      await sleep(200);
      await user.type(input, "ac");
      await sleep(200);
      // 400 ms since the first key, but only 200 since the last.
      expect(screen.getByRole("status")).toBeEmptyDOMElement();
      await waitFor(
        () => {
          expect(screen.getByRole("status")).toHaveTextContent("3 of 84 rules");
        },
        { timeout: 1500 },
      );
    });

    it("says nothing new when the announce text is the same as the last announcement", async () => {
      const user = userEvent.setup();
      const same = (value: string) => (value === "" ? "84 rules" : "12 of 84 rules");
      render(<Harness announceFor={same} delay={60} />);
      const input = screen.getByRole("searchbox");
      await user.type(input, "a");
      await waitFor(() => {
        expect(screen.getByRole("status")).toHaveTextContent("12 of 84 rules");
      });
      const region = screen.getByRole("status");
      // The region's text node must not be replaced: a replaced node would be announced again.
      const node = region.firstChild;
      await user.type(input, "b");
      await sleep(200);
      expect(region.firstChild).toBe(node);
      expect(region).toHaveTextContent("12 of 84 rules");
    });

    it("does not announce when the text returns to what was last announced", async () => {
      const user = userEvent.setup();
      render(
        <Harness announceFor={(v) => (v === "" ? "84 rules" : "No rules match")} delay={60} />,
      );
      const input = screen.getByRole("searchbox");
      // Back to the empty text before the wait ends, so nothing changed since the last announcement.
      await user.type(input, "z");
      await user.clear(input);
      await sleep(250);
      expect(screen.getByRole("status")).toBeEmptyDOMElement();
    });

    it("keeps the visible count and the spoken text separate", async () => {
      const user = userEvent.setup();
      render(<Harness announceFor={byLength} delay={30} />);
      await user.type(screen.getByRole("searchbox"), "a");
      expect(screen.getByText("1 of 84 rules", { selector: "p" })).toBeVisible();
      await waitFor(() => {
        expect(screen.getByRole("status")).toHaveTextContent("1 of 84 rules");
      });
    });
  });
});
