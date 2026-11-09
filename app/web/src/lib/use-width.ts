/*
 * The pixel width of an element, kept current by a ResizeObserver. The stacked bars draw in pixels
 * (a 2 px gap and a 5 px floor for the open bar cannot be written as percentages), so they need
 * the plot's real width. Before the first measure, and where there is no ResizeObserver (jsdom),
 * the hook returns the fallback.
 */
import { useRef, useSyncExternalStore } from "react";

export function useElementWidth<T extends HTMLElement>(
  fallback: number,
): { ref: React.RefObject<T | null>; width: number } {
  const ref = useRef<T>(null);
  const subscribe = (notify: () => void): (() => void) => {
    const el = ref.current;
    if (el === null || typeof ResizeObserver === "undefined") return () => undefined;
    const observer = new ResizeObserver(notify);
    observer.observe(el);
    return () => {
      observer.disconnect();
    };
  };
  const width = useSyncExternalStore(
    subscribe,
    () => {
      const measured = ref.current?.clientWidth ?? 0;
      return measured > 0 ? measured : fallback;
    },
    () => fallback,
  );
  return { ref, width };
}
