import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { highlight, matchFields, matches } from "./match";

afterEach(cleanup);

describe("matchFields", () => {
  const rule = {
    sentence: "An effort cap lowers the effort",
    group: "Model and effort",
    quote: "The cap applies to every session. Café settings win.",
  };

  it("returns null when a word is found in no field", () => {
    expect(matchFields("effort zzz", rule)).toBeNull();
    expect(matchFields("zzz", rule)).toBeNull();
  });

  it("returns an empty set for an empty query", () => {
    expect(matchFields("", rule)).toEqual(new Set());
    expect(matchFields("   ", rule)).toEqual(new Set());
  });

  it("names every field in which any query word was found", () => {
    expect(matchFields("effort", rule)).toEqual(new Set(["sentence", "group"]));
  });

  it("reports a match only in the quote as the quote field alone", () => {
    expect(matchFields("session", rule)).toEqual(new Set(["quote"]));
  });

  it("needs every word, but each may sit in a different field", () => {
    expect(matchFields("model session", rule)).toEqual(new Set(["group", "quote"]));
    expect(matchFields("model zzz", rule)).toBeNull();
  });

  it("folds case and accents like matches does", () => {
    expect(matchFields("CAFE", rule)).toEqual(new Set(["quote"]));
  });

  it("agrees with matches over one joined field", () => {
    for (const query of ["", "cap", "cap session", "cap zzz", "CAFÉ", "effort model"]) {
      const joined = Object.values(rule).join(" ");
      expect(matchFields(query, rule) !== null).toBe(matches(query, joined));
    }
  });
});

describe("matches", () => {
  it("matches everything on an empty or blank query", () => {
    expect(matches("", "anything")).toBe(true);
    expect(matches("   ", "anything")).toBe(true);
    expect(matches("", "")).toBe(true);
  });

  it("ignores case", () => {
    expect(matches("CACHE", "Read from cache")).toBe(true);
    expect(matches("cache", "READ FROM CACHE")).toBe(true);
  });

  it("ignores accents on both sides", () => {
    expect(matches("cafe", "Café au lait")).toBe(true);
    expect(matches("café", "Cafe au lait")).toBe(true);
    expect(matches("naive", "naïve")).toBe(true);
  });

  it("folds compatibility forms", () => {
    expect(matches("fi", "ﬁle")).toBe(true);
    expect(matches("1", "①")).toBe(true);
  });

  it("needs every word, in any order, anywhere", () => {
    expect(matches("effort cap", "The cap lowers the effort")).toBe(true);
    expect(matches("effort model", "The cap lowers the effort")).toBe(false);
  });

  it("splits the query on any whitespace", () => {
    expect(matches("effort\tcap\n", "cap and effort")).toBe(true);
  });

  it("matches inside a word, as a filter does", () => {
    expect(matches("ache", "cache")).toBe(true);
  });

  it("does not match text that lacks the word", () => {
    expect(matches("zzz", "cache")).toBe(false);
  });
});

function html(nodes: ReturnType<typeof highlight>): string {
  const { container } = render(<p>{nodes}</p>);
  return container.innerHTML;
}

describe("highlight", () => {
  it("returns the text alone for an empty query or no match", () => {
    expect(highlight("Read from cache", "")).toEqual(["Read from cache"]);
    expect(highlight("Read from cache", "zzz")).toEqual(["Read from cache"]);
  });

  it("wraps each match in a mark and keeps the rest as strings", () => {
    expect(html(highlight("Read from cache", "cache"))).toBe(
      '<p>Read from <mark class="search-mark">cache</mark></p>',
    );
  });

  it("marks every word, case and accent blind, in the original spelling", () => {
    expect(html(highlight("Café au lait", "CAFE lait"))).toBe(
      '<p><mark class="search-mark">Café</mark> au <mark class="search-mark">lait</mark></p>',
    );
  });

  it("marks every occurrence", () => {
    expect(html(highlight("cache or cache", "cache"))).toBe(
      '<p><mark class="search-mark">cache</mark> or <mark class="search-mark">cache</mark></p>',
    );
  });

  it("merges overlapping and touching matches into one mark", () => {
    expect(html(highlight("cached", "cache ached"))).toBe(
      '<p><mark class="search-mark">cached</mark></p>',
    );
  });

  it("maps back correctly when folding changes a length", () => {
    expect(html(highlight("a ﬁle here", "fi"))).toBe(
      '<p>a <mark class="search-mark">ﬁ</mark>le here</p>',
    );
  });

  it("keeps a combining mark with its letter", () => {
    const decomposed = "Café time";
    expect(html(highlight(decomposed, "cafe"))).toBe(
      '<p><mark class="search-mark">Café</mark> time</p>',
    );
  });

  it("never turns text into markup", () => {
    const out = html(highlight("<b>cache</b> & more", "cache"));
    expect(out).toBe('<p>&lt;b&gt;<mark class="search-mark">cache</mark>&lt;/b&gt; &amp; more</p>');
  });
});
