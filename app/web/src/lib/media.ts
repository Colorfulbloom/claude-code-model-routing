/*
 * The two layouts. The sidebar shell shows at 721px and up, the top bar and tab bar at 720px and
 * below. The shell renders one of them, never both, so the page has one nav landmark. Without
 * matchMedia (jsdom, old engines) the desktop layout wins.
 */
import { useSyncExternalStore } from "react";

export const DESKTOP_QUERY = "(min-width: 721px)";

/** matchMedia is missing in jsdom, and the property can exist with no function behind it. */
function hasMatchMedia(): boolean {
  return typeof (window as { matchMedia?: unknown }).matchMedia === "function";
}

function subscribe(listener: () => void): () => void {
  if (!hasMatchMedia()) return () => undefined;
  const list = window.matchMedia(DESKTOP_QUERY);
  list.addEventListener("change", listener);
  return () => {
    list.removeEventListener("change", listener);
  };
}

function snapshot(): boolean {
  return hasMatchMedia() ? window.matchMedia(DESKTOP_QUERY).matches : true;
}

export function useIsDesktop(): boolean {
  return useSyncExternalStore(subscribe, snapshot, () => true);
}
