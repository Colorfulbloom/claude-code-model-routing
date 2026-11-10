import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReplayLine, SETTLE_MS, states, type ReplayLineProps } from "./ReplayLine";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const line = (over: Partial<ReplayLineProps> = {}) => {
  const onChange = vi.fn();
  const props: ReplayLineProps = {
    label: "Replay time",
    max: 60,
    value: 25,
    valueText: "2:25 PM",
    pageStep: 5,
    onChange,
    ...over,
  };
  const view = render(<ReplayLine {...props} />);
  return { onChange, view, input: screen.getByRole("slider") };
};

describe("ReplayLine", () => {
  it("lists its states", () => {
    expect(states).toContain("dragging");
  });

  it("is a native range input with step 1 from 0 to max", () => {
    const { input } = line();
    expect(input.tagName).toBe("INPUT");
    expect(input).toHaveAttribute("type", "range");
    expect(input).toHaveAttribute("min", "0");
    expect(input).toHaveAttribute("max", "60");
    expect(input).toHaveAttribute("step", "1");
    expect(input).toHaveValue("25");
  });

  it("takes its name and value text from props", () => {
    const { input } = line();
    expect(screen.getByRole("slider", { name: "Replay time" })).toBe(input);
    expect(input).toHaveAttribute("aria-valuetext", "2:25 PM");
  });

  it("calls onChange on every input event", () => {
    const { onChange, input } = line();
    fireEvent.change(input, { target: { value: "26" } });
    fireEvent.change(input, { target: { value: "27" } });
    expect(onChange).toHaveBeenNthCalledWith(1, 26);
    expect(onChange).toHaveBeenNthCalledWith(2, 27);
  });

  it("moves Page Up and Page Down by pageStep and stops the native step", () => {
    const { onChange, input } = line({ pageStep: 5 });
    const up = fireEvent.keyDown(input, { key: "PageUp" });
    expect(up).toBe(false);
    expect(onChange).toHaveBeenLastCalledWith(30);
    // The page has not re-rendered yet, so the next key starts from the 30 the first one asked for.
    const down = fireEvent.keyDown(input, { key: "PageDown" });
    expect(down).toBe(false);
    expect(onChange).toHaveBeenLastCalledWith(25);
  });

  it("keeps counting from the last step when keys repeat before the page answers", () => {
    const { onChange, input } = line({ pageStep: 5, value: 25 });
    fireEvent.keyDown(input, { key: "PageUp" });
    fireEvent.keyDown(input, { key: "PageUp" });
    fireEvent.keyDown(input, { key: "PageUp" });
    expect(onChange).toHaveBeenNthCalledWith(1, 30);
    expect(onChange).toHaveBeenNthCalledWith(2, 35);
    expect(onChange).toHaveBeenNthCalledWith(3, 40);
  });

  it("uses a larger page step when the page passes one", () => {
    const { onChange, input } = line({ pageStep: 10, value: 20 });
    fireEvent.keyDown(input, { key: "PageUp" });
    expect(onChange).toHaveBeenLastCalledWith(30);
  });

  it("clamps the page keys to the range", () => {
    const { onChange, input } = line({ value: 58 });
    fireEvent.keyDown(input, { key: "PageUp" });
    expect(onChange).toHaveBeenLastCalledWith(60);
    cleanup();
    const low = line({ value: 2 });
    fireEvent.keyDown(low.input, { key: "PageDown" });
    expect(low.onChange).toHaveBeenLastCalledWith(0);
  });

  it("does not call onChange at the end, but still stops the native step", () => {
    const { onChange, input } = line({ value: 60 });
    const notPrevented = fireEvent.keyDown(input, { key: "PageUp" });
    expect(notPrevented).toBe(false);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("leaves arrow keys, Home and End to the browser", () => {
    const { onChange, input } = line();
    for (const key of ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"]) {
      expect(fireEvent.keyDown(input, { key })).toBe(true);
    }
    expect(onChange).not.toHaveBeenCalled();
  });

  it("leaves a page key with a modifier alone", () => {
    const { onChange, input } = line();
    expect(fireEvent.keyDown(input, { key: "PageUp", ctrlKey: true })).toBe(true);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("fires onSettle 500 ms after the last change", () => {
    const onSettle = vi.fn();
    const { input } = line({ onSettle });
    fireEvent.change(input, { target: { value: "26" } });
    act(() => {
      vi.advanceTimersByTime(SETTLE_MS - 1);
    });
    fireEvent.change(input, { target: { value: "27" } });
    act(() => {
      vi.advanceTimersByTime(SETTLE_MS - 1);
    });
    expect(onSettle).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(onSettle).toHaveBeenCalledTimes(1);
    expect(onSettle).toHaveBeenCalledWith(27);
  });

  it("settles after a page key too", () => {
    const onSettle = vi.fn();
    const { input } = line({ onSettle });
    fireEvent.keyDown(input, { key: "PageUp" });
    act(() => {
      vi.advanceTimersByTime(SETTLE_MS);
    });
    expect(onSettle).toHaveBeenCalledWith(30);
  });

  it("does not settle after it unmounts", () => {
    const onSettle = vi.fn();
    const { input, view } = line({ onSettle });
    fireEvent.change(input, { target: { value: "26" } });
    view.unmount();
    act(() => {
      vi.advanceTimersByTime(SETTLE_MS * 2);
    });
    expect(onSettle).not.toHaveBeenCalled();
  });

  it("puts the handle where the value is", () => {
    const { view } = line({ value: 15, max: 60 });
    const root = view.container.querySelector<HTMLElement>(".replay");
    expect(root?.style.getPropertyValue("--replay-x")).toBe("25%");
  });

  it("holds the handle at the start when max is 0", () => {
    const { view } = line({ value: 0, max: 0 });
    const root = view.container.querySelector<HTMLElement>(".replay");
    expect(root?.style.getPropertyValue("--replay-x")).toBe("0%");
  });

  it("shows the time, the precision line and the key hint", () => {
    line({
      showing: "Showing 2:25 PM",
      precision: "As of the last 10-minute mark",
      hint: "Arrow keys",
    });
    expect(screen.getByText("Showing 2:25 PM")).toBeInTheDocument();
    expect(screen.getByText("As of the last 10-minute mark")).toBeInTheDocument();
    expect(screen.getByText("Arrow keys")).toBeInTheDocument();
  });

  it("hides the decoration from assistive tech", () => {
    const { view } = line();
    for (const cls of [".replay-rail", ".replay-cut", ".replay-handle"]) {
      expect(view.container.querySelector(cls)).toHaveAttribute("aria-hidden", "true");
    }
  });
});
