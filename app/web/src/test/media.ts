/*
 * A matchMedia stand-in for tests. jsdom has none, so the shell shows its desktop layout. Call
 * setViewport(width) before rendering to pick a layout, or while mounted to change it.
 */
type Listener = (event: { matches: boolean }) => void;

const listeners = new Set<Listener>();
let width = 1440;

function matches(query: string): boolean {
  const min = /\(min-width:\s*(\d+)px\)/.exec(query);
  if (min?.[1] !== undefined) return width >= Number(min[1]);
  const max = /\(max-width:\s*(\d+)px\)/.exec(query);
  if (max?.[1] !== undefined) return width <= Number(max[1]);
  return false;
}

export function setViewport(next: number): void {
  width = next;
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      get matches() {
        return matches(query);
      },
      media: query,
      addEventListener: (_type: string, listener: Listener) => listeners.add(listener),
      removeEventListener: (_type: string, listener: Listener) => listeners.delete(listener),
    }),
  });
  for (const listener of listeners) listener({ matches: next >= 721 });
}

export function resetViewport(): void {
  listeners.clear();
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: undefined,
  });
  width = 1440;
}
