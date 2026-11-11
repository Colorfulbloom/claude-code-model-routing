import { describe, expect, it } from "vitest";
import {
  asScope,
  CODE_MARK,
  fullPathOf,
  outcomeView,
  scopeMeaning,
  scopeName,
  splitOnMark,
  splitPath,
  statusWord,
} from "./edit-words";

describe("edit words", () => {
  it("names each scope and says what it means", () => {
    expect(scopeName("local")).toBe("Project local");
    expect(scopeName("project")).toBe("Shared project");
    expect(scopeName("user")).toBe("User");
    expect(scopeMeaning("local")).toBe("Just you, this project");
    expect(scopeMeaning("project")).toBe("Everyone in this project");
    expect(scopeMeaning("user")).toBe("You, every project");
  });

  it("reads a scope code from a params value, and nothing else", () => {
    expect(asScope("user")).toBe("user");
    expect(asScope("Managed")).toBeNull();
    expect(asScope(undefined)).toBeNull();
  });

  it("words an outcome with the status's glyph key and its word", () => {
    expect(outcomeView({ status: "in_effect", beaten_by: null })).toEqual({
      status: "in_effect",
      word: "Takes effect",
    });
    expect(outcomeView({ status: "overridden", beaten_by: "local" })).toEqual({
      status: "overridden",
      word: "Overridden by Project local",
    });
  });

  it("keeps the plain status word when nothing names who wins", () => {
    expect(outcomeView({ status: "overridden", beaten_by: null }).word).toBe("Overridden");
    expect(outcomeView({ status: "lowered", beaten_by: null }).word).toBe("Lowered");
    expect(statusWord("ignored")).toBe("Ignored");
  });

  it("splits a sentence where the code span goes", () => {
    expect(splitOnMark(`Start with ${CODE_MARK} now.`)).toEqual(["Start with ", " now."]);
    expect(splitOnMark("No mark here.")).toEqual(["No mark here.", ""]);
  });

  it("puts the project's path before a relative file path, and leaves a full one alone", () => {
    expect(fullPathOf(".claude/settings.json", "~/work/tide")).toBe(
      "~/work/tide/.claude/settings.json",
    );
    expect(fullPathOf(".claude/settings.json", "/work/tide/")).toBe(
      "/work/tide/.claude/settings.json",
    );
    expect(fullPathOf("~/.claude/settings.json", "~/work/tide")).toBe("~/.claude/settings.json");
    expect(fullPathOf("/work/x/settings.json", "~/work/tide")).toBe("/work/x/settings.json");
    // A project that shows as a bare name gives nothing to put in front.
    expect(fullPathOf(".claude/settings.json", "tide")).toBe(".claude/settings.json");
    expect(fullPathOf(".claude/settings.json", undefined)).toBe(".claude/settings.json");
  });

  it("splits a path into its folder and file name", () => {
    expect(splitPath("~/a/b/c.json")).toEqual({ dir: "~/a/b/", name: "c.json" });
    expect(splitPath("c.json")).toEqual({ dir: "", name: "c.json" });
  });
});
