import { describe, expect, it } from "vitest";
import {
  decidesHref,
  filtersQuery,
  glossaryLink,
  isNarrowed,
  readFilters,
  readOrigin,
} from "./reference-routes";

describe("the Decides query", () => {
  it("reads q, confidence and due, and treats anything else as the default", () => {
    expect(readFilters(new URLSearchParams(""))).toEqual({ q: "", confidence: "all", due: false });
    expect(readFilters(new URLSearchParams("q=cache&confidence=tested&due=1"))).toEqual({
      q: "cache",
      confidence: "tested",
      due: true,
    });
    expect(readFilters(new URLSearchParams("confidence=nope&due=yes"))).toEqual({
      q: "",
      confidence: "all",
      due: false,
    });
  });

  it("writes only the filters that apply, in a fixed order", () => {
    expect(filtersQuery({ q: "", confidence: "all", due: false })).toBe("");
    expect(filtersQuery({ q: "a b", confidence: "assumed", due: true })).toBe(
      "?q=a+b&confidence=assumed&due=1",
    );
  });

  it("knows when a filter narrows the rules", () => {
    expect(isNarrowed({ q: "  ", confidence: "all", due: false })).toBe(false);
    expect(isNarrowed({ q: "x", confidence: "all", due: false })).toBe(true);
    expect(isNarrowed({ q: "", confidence: "tested", due: false })).toBe(true);
    expect(isNarrowed({ q: "", confidence: "all", due: true })).toBe(true);
  });

  it("builds a setting and a rule link, with the key's dot escaped only when needed", () => {
    expect(decidesHref({})).toBe("#/reference/decides");
    expect(decidesHref({ setting: "effortLevel" })).toBe("#/reference/decides/effortLevel");
    expect(decidesHref({ setting: "effortLevel", rule: "effort-level-layer-order" })).toBe(
      "#/reference/decides/effortLevel/effort-level-layer-order",
    );
    expect(
      decidesHref(
        { setting: "modelSettings.maxEffortLevel" },
        { q: "", confidence: "all", due: true },
      ),
    ).toBe("#/reference/decides/modelSettings.maxEffortLevel?due=1");
  });
});

describe("the Glossary link", () => {
  it("builds a root, a term, a query and an origin", () => {
    expect(glossaryLink()).toBe("#/reference/glossary");
    expect(glossaryLink("cache-write")).toBe("#/reference/glossary/cache-write");
    expect(glossaryLink(undefined, { q: "cache" })).toBe("#/reference/glossary?q=cache");
    expect(
      glossaryLink("run", { origin: { from: "/p/a/live?session=s1", help: "live.who" } }),
    ).toBe("#/reference/glossary/run?from=%2Fp%2Fa%2Flive%3Fsession%3Ds1&help=live.who");
  });

  it("reads the origin back, and none without a from", () => {
    const link = glossaryLink("run", {
      origin: { from: "/p/a/live?session=s1", help: "live.who" },
    });
    const query = new URLSearchParams(link.slice(link.indexOf("?")));
    expect(readOrigin(query)).toEqual({ from: "/p/a/live?session=s1", help: "live.who" });
    expect(readOrigin(new URLSearchParams("help=x"))).toBeNull();
    expect(readOrigin(new URLSearchParams("from=%2Fp%2Fa%2Flive"))).toEqual({
      from: "/p/a/live",
      help: null,
    });
  });
});
