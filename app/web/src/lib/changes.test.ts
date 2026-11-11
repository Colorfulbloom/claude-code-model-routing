import { describe, expect, it } from "vitest";
import {
  changeText,
  groupByDay,
  hasUndo,
  RECHECK_GLYPH,
  recheckWord,
  rowFieldLabel,
  undoStateText,
} from "@/lib/changes";
import { historyRow } from "@/test/edit-server";

const NOW = "2026-11-11T15:00:00Z";

describe("groupByDay", () => {
  it("groups by local day, newest first as sent, and names today and yesterday", () => {
    const rows = [
      historyRow({ id: "a", time: "2026-11-11T14:55:00Z" }),
      historyRow({ id: "b", time: "2026-11-11T10:00:00Z" }),
      historyRow({ id: "c", time: "2026-11-10T15:00:00Z" }),
      historyRow({ id: "d", time: "2026-11-01T15:00:00Z" }),
    ];
    const groups = groupByDay(rows, NOW);
    expect(groups.map((g) => g.label)).toEqual(["Today", "Yesterday", "November 1"]);
    expect(groups.map((g) => g.rows.map((r) => r.id))).toEqual([["a", "b"], ["c"], ["d"]]);
    expect(new Set(groups.map((g) => g.key)).size).toBe(3);
  });

  it("returns no group for no rows", () => {
    expect(groupByDay([], NOW)).toEqual([]);
  });
});

describe("changeText", () => {
  it("names the field and both values", () => {
    expect(changeText(historyRow())).toBe("Effort, xhigh to low");
    expect(changeText(historyRow({ field: "maxEffortLevel", from: "high", to: "xhigh" }))).toBe(
      "Effort cap, high to xhigh",
    );
  });

  it("says a value was added when there was none, and names a missing one", () => {
    expect(changeText(historyRow({ from: null, to: "low" }))).toBe("Effort, set to low");
  });

  it("names an agent's field and a new agent", () => {
    const named = { kind: "agent", name: "builder" } as const;
    expect(
      changeText(historyRow({ field: "model", subject: named, from: "fable", to: "sonnet" })),
    ).toBe("Model for builder, fable to sonnet");
    expect(
      changeText(historyRow({ op: "create", subject: { kind: "agent", name: "planner" } })),
    ).toBe("New agent planner");
  });

  it("marks an undo and a restore", () => {
    expect(changeText(historyRow({ op: "undo" }))).toBe("Undid Effort, xhigh to low");
    expect(changeText(historyRow({ op: "restore" }))).toMatch(/^Restore of /);
  });

  it("says a save that made the file made it", () => {
    expect(changeText(historyRow({ op: "create", from: null, to: "high" }))).toBe(
      "Effort, set to high in a new file",
    );
  });

  it("keeps a field the page has no label for as the file spells it", () => {
    expect(rowFieldLabel("effortLevel")).toBe("Effort");
    expect(rowFieldLabel("someNewKey")).toBe("someNewKey");
  });
});

describe("undo state", () => {
  it("shows the button for the three states a person can act on", () => {
    expect(hasUndo("can_undo")).toBe(true);
    expect(hasUndo("changed_since")).toBe(true);
    expect(hasUndo("deletes_file")).toBe(true);
    expect(hasUndo("undone")).toBe(false);
    expect(hasUndo("not_undoable")).toBe(false);
  });

  it("words each state", () => {
    // A row that can simply be undone says nothing, because its button already says so.
    expect(undoStateText(historyRow({ undo_state: "can_undo" }))).toBeNull();
    expect(undoStateText(historyRow({ undo_state: "changed_since" }))).toBe(
      "File changed since. Undo shows what it removes first.",
    );
    expect(undoStateText(historyRow({ undo_state: "deletes_file" }))).toBe("Undo deletes the file");
    expect(
      undoStateText(historyRow({ undo_state: "undone", undone_at: "2026-11-11T14:58:00Z" })),
    ).toMatch(/^Undone at /);
  });

  it("gives each reason a save can't be undone its own sentence, and the rest the plain one", () => {
    const of = (
      not_undoable_reason:
        | "not_newest"
        | "undo_row"
        | "restore_row"
        | "backup_pruned"
        | "backup_damaged"
        | "file_refused"
        | null,
    ) => undoStateText(historyRow({ undo_state: "not_undoable", not_undoable_reason }));
    const distinct = new Set([
      of("not_newest"),
      of("undo_row"),
      of("backup_pruned"),
      of("backup_damaged"),
    ]);
    expect(distinct.size).toBe(4);
    expect(of("restore_row")).toBe(of("file_refused"));
    expect(of(null)).toBe(of("restore_row"));
    expect(distinct.has(of(null))).toBe(false);
  });
});

describe("recheck", () => {
  it("words each outcome and gives each a glyph", () => {
    expect(recheckWord("checking")).toBe("Checking the file");
    expect(recheckWord("confirmed")).toBe("Still in the file");
    expect(recheckWord("overwritten")).toBe("Changed by another program");
    expect(new Set(Object.values(RECHECK_GLYPH)).size).toBe(3);
  });
});
