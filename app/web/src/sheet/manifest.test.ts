import { describe, expect, it } from "vitest";
import { manifest } from "./manifest";

interface ComponentModule {
  states?: readonly string[];
}

const modules = import.meta.glob<ComponentModule>(
  ["../components/*/*.tsx", "!../components/*/*.test.tsx"],
  {
    eager: true,
  },
);

/** Component folder name to the `states` its main file exports. */
const folders = new Map<string, readonly string[] | undefined>();
for (const [path, mod] of Object.entries(modules)) {
  const match = /\.\.\/components\/([^/]+)\/([^/]+)\.tsx$/.exec(path);
  if (match?.[1] !== undefined && match[1] === match[2]) folders.set(match[1], mod.states);
}

describe("component sheet manifest", () => {
  it("finds the component folders", () => {
    expect(folders.size).toBeGreaterThan(0);
  });

  it("has an entry for every component folder", () => {
    const listed = new Set(manifest.map((entry) => entry.component));
    const missing = [...folders.keys()].filter((name) => !listed.has(name));
    expect(missing).toEqual([]);
  });

  it("has a states export on every component", () => {
    const without = [...folders].filter(
      ([, states]) => states === undefined || states.length === 0,
    );
    expect(without.map(([name]) => name)).toEqual([]);
  });

  it("has an entry for every state a component lists", () => {
    const missing: string[] = [];
    for (const [name, states] of folders) {
      for (const state of states ?? []) {
        if (!manifest.some((entry) => entry.component === name && entry.state === state)) {
          missing.push(`${name}:${state}`);
        }
      }
    }
    expect(missing).toEqual([]);
  });

  it("names no state that a component does not list", () => {
    const unknown = manifest
      .filter((entry) => folders.has(entry.component))
      .filter((entry) => !(folders.get(entry.component) ?? []).includes(entry.state))
      .map((entry) => `${entry.component}:${entry.state}`);
    expect(unknown).toEqual([]);
  });

  it("renders every entry", () => {
    for (const entry of manifest) expect(entry.render()).toBeDefined();
  });
});
