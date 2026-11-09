/* Whether the person asked for less motion. Without matchMedia (jsdom, old engines) motion is allowed. */
import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function hasMatchMedia(): boolean {
  return typeof (window as { matchMedia?: unknown }).matchMedia === "function";
}

function subscribe(listener: () => void): () => void {
  if (!hasMatchMedia()) return () => undefined;
  const list = window.matchMedia(QUERY);
  list.addEventListener("change", listener);
  return () => {
    list.removeEventListener("change", listener);
  };
}

function snapshot(): boolean {
  return hasMatchMedia() ? window.matchMedia(QUERY).matches : false;
}

export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, snapshot, () => false);
}
