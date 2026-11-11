import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HelpButton } from "@/components/HelpButton/HelpButton";
import { resetViewport, setViewport } from "@/test/media";
import { TRAY_GAP, revealAboveTray } from "./useHelpOpen";

const scrollIntoView = vi.fn();
let triggerBottom = 700;
let triggerTop = 676;

beforeEach(() => {
  scrollIntoView.mockClear();
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    get() {
      return (this as HTMLElement).classList.contains("hp-tray") ? 400 : 0;
    },
  });
  Element.prototype.scrollIntoView = scrollIntoView;
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
    this: HTMLElement,
  ) {
    const isTrigger = this.classList.contains("help-button");
    return {
      top: isTrigger ? triggerTop : 0,
      bottom: isTrigger ? triggerBottom : 0,
    } as DOMRect;
  });
});

afterEach(() => {
  cleanup();
  resetViewport();
  vi.restoreAllMocks();
});

describe("revealAboveTray", () => {
  function pair(): { trigger: HTMLElement; tray: HTMLElement } {
    const trigger = document.createElement("button");
    trigger.classList.add("help-button");
    const tray = document.createElement("div");
    tray.classList.add("hp-tray");
    return { trigger, tray };
  }

  it("leaves the page alone when the trigger already sits above the tray", () => {
    triggerTop = 100;
    triggerBottom = 124;
    const { trigger, tray } = pair();
    expect(revealAboveTray(trigger, tray)).toBe(false);
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("scrolls when the trigger sits under the tray, keeping a gap above it", () => {
    triggerTop = 676;
    triggerBottom = 700;
    const { trigger, tray } = pair();
    expect(revealAboveTray(trigger, tray)).toBe(true);
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest", behavior: "smooth" });
    expect(trigger.style.scrollMarginBottom).toBe("");
    expect(TRAY_GAP).toBe(16);
  });

  it("scrolls with no animation under prefers-reduced-motion", () => {
    triggerTop = 676;
    triggerBottom = 700;
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: (query: string) => ({
        matches: query.includes("prefers-reduced-motion"),
        media: query,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
      }),
    });
    const { trigger, tray } = pair();
    revealAboveTray(trigger, tray);
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest", behavior: "auto" });
  });
});

describe("the tray and its trigger", () => {
  it("scrolls the trigger into view when the tray opens, and keeps focus rules", async () => {
    triggerTop = 676;
    triggerBottom = 700;
    setViewport(375);
    const user = userEvent.setup();
    render(<HelpButton help="live.cache" />);
    const button = screen.getByRole("button", { name: "About Read from cache" });
    await user.click(button);
    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalled();
    });
    expect(scrollIntoView.mock.contexts[0]).toBe(button);
    expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement);
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(button).toHaveFocus();
    });
  });

  it("does not scroll when the trigger is already above the tray", async () => {
    triggerTop = 100;
    triggerBottom = 124;
    setViewport(375);
    const user = userEvent.setup();
    render(<HelpButton help="live.cache" />);
    await user.click(screen.getByRole("button", { name: "About Read from cache" }));
    await screen.findByRole("dialog");
    await new Promise((resolve) => window.setTimeout(resolve, 50));
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("does not scroll for the popover at desktop width", async () => {
    triggerTop = 676;
    triggerBottom = 700;
    setViewport(1440);
    const user = userEvent.setup();
    render(<HelpButton help="live.cache" />);
    await user.click(screen.getByRole("button", { name: "About Read from cache" }));
    await screen.findByRole("dialog");
    await new Promise((resolve) => window.setTimeout(resolve, 50));
    expect(scrollIntoView).not.toHaveBeenCalled();
  });
});
