/*
 * The route harness. On a route or gate change it sets the document title, moves focus to the
 * page h1 and posts the page name to one polite live region. Routes and gate states share it.
 */
import { useEffect, useSyncExternalStore } from "react";
import type { RefObject } from "react";

let statusText = "";
const statusListeners = new Set<() => void>();

/** Posts text to the polite live region. */
export function postStatus(text: string): void {
  statusText = text;
  for (const listener of statusListeners) listener();
}

function subscribeStatus(listener: () => void): () => void {
  statusListeners.add(listener);
  return () => {
    statusListeners.delete(listener);
  };
}

function getStatus(): string {
  return statusText;
}

/** One per app, always mounted, so the region exists before it first speaks. */
export function StatusRegion() {
  const text = useSyncExternalStore(subscribeStatus, getStatus);
  return (
    <div role="status" aria-live="polite" className="sr-only">
      {text}
    </div>
  );
}

interface HarnessInput {
  /** Changes when the route or gate state changes. A change moves focus and posts the status. */
  id: string;
  title: string;
  status: string;
}

export function useHarness(rootRef: RefObject<HTMLElement | null>, input: HarnessInput): void {
  const { id, title, status } = input;

  useEffect(() => {
    document.title = title;
  }, [title]);

  useEffect(() => {
    const heading = rootRef.current?.querySelector("h1");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus();
    }
    postStatus(status);
    // id is the trigger, status is derived from it
  }, [id, status, rootRef]);
}
