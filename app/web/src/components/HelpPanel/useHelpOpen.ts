/*
 * Open state for one help spot. The panel is a popover above 720 px and a tray at 720 px and
 * under (lib/media.ts, the same line the shell uses). The layout is read when the panel opens. If
 * the window crosses that line while the panel is open, the panel closes, because a popover and a
 * tray are different dialogs and one cannot turn into the other without losing focus. Without
 * matchMedia (jsdom) the popover wins.
 *
 * The tray is up to 82 vh high and can sit over the trigger that opened it. When the tray opens,
 * the page scrolls just enough to bring the trigger into view above the tray, so its open ring
 * shows. Reduced motion scrolls with no animation.
 */
import { useEffect, useRef, useState, type RefObject } from "react";
import { DESKTOP_QUERY, useIsDesktop } from "@/lib/media";

export interface HelpOpen {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  /** True when the panel draws as the bottom tray. */
  tray: boolean;
}

/** The gap kept between the trigger and the top of the tray. */
export const TRAY_GAP = 16;

/**
 * Scrolls the page so `trigger` sits fully above the top of `tray`, only when it would sit under
 * the tray (or above the top of the window). Returns true when it asked the page to scroll.
 */
export function revealAboveTray(trigger: HTMLElement, tray: HTMLElement): boolean {
  const viewport = window.visualViewport?.height ?? window.innerHeight;
  const trayTop = viewport - tray.offsetHeight;
  const rect = trigger.getBoundingClientRect();
  if (rect.top >= 0 && rect.bottom + TRAY_GAP <= trayTop) return false;
  const reduced =
    typeof (window as { matchMedia?: unknown }).matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  trigger.style.scrollMarginBottom = `${String(tray.offsetHeight + TRAY_GAP)}px`;
  trigger.scrollIntoView({ block: "nearest", behavior: reduced ? "auto" : "smooth" });
  trigger.style.removeProperty("scroll-margin-bottom");
  return true;
}

/** The open state, and the ref that goes on the trigger button so the open tray can keep it in view. */
export function useHelpOpen(): [HelpOpen, RefObject<HTMLButtonElement | null>] {
  const desktop = useIsDesktop();
  const [isOpen, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (!isOpen || typeof (window as { matchMedia?: unknown }).matchMedia !== "function") {
      return undefined;
    }
    const list = window.matchMedia(DESKTOP_QUERY);
    const close = () => {
      setOpen(false);
    };
    list.addEventListener("change", close);
    return () => {
      list.removeEventListener("change", close);
    };
  }, [isOpen]);
  const tray = !desktop;
  useEffect(() => {
    if (!isOpen || !tray) return undefined;
    const frame = window.requestAnimationFrame(() => {
      const trigger = triggerRef.current;
      const panel = document.querySelector<HTMLElement>(".hp-tray:not(.hp-inline)");
      if (trigger === null || panel === null || typeof trigger.scrollIntoView !== "function") {
        return;
      }
      revealAboveTray(trigger, panel);
    });
    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [isOpen, tray]);
  return [{ isOpen, onOpenChange: setOpen, tray }, triggerRef];
}
