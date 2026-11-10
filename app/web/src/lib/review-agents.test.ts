import { describe, expect, it } from "vitest";
import { IDS } from "@/test/review-fixtures";
import { SONNET, agentRow, agentsAnswer, noRuns, setPair } from "@/test/review-tables";
import {
  buildAgents,
  checkStatus,
  ranCell,
  runsOf,
  setCell,
  setWhyWords,
  sourceLine,
} from "@/lib/review-agents";

describe("the Set to cell", () => {
  it("reads a set pair as the model name and the effort", () => {
    expect(setCell(setPair(IDS.fable, "xhigh"), null)).toEqual({
      text: "Fable 5.1 · xhigh",
      why: null,
    });
    expect(setCell(setPair(IDS.opus, null), null).text).toBe("Opus 5.5");
    expect(setCell(setPair(null, "low"), null).text).toBe("low");
  });

  it("says Nothing set when a file sets nothing", () => {
    const cell = setCell(null, "sets_nothing");
    expect(cell).toEqual({ text: null, why: "sets_nothing" });
    expect(setWhyWords("sets_nothing")).toBe("Nothing set");
  });

  it("says No agent file when there is no file", () => {
    expect(setCell(null, "no_file").why).toBe("no_file");
    expect(setWhyWords("no_file")).toBe("No agent file");
  });

  it("says it could not read the setup when the read failed", () => {
    expect(setCell(null, "read_failed").why).toBe("read_failed");
    expect(setWhyWords("read_failed")).toBe("Couldn't read its setup");
  });

  it("treats a null pair with no reason as nothing set, and an empty pair the same", () => {
    expect(setCell(null, null).why).toBe("sets_nothing");
    expect(setCell(setPair(null, null), null).why).toBe("sets_nothing");
  });

  it("never produces the text None", () => {
    const view = buildAgents(agentsAnswer());
    const words = [
      ...view.rows.map((row) => row.set.text ?? setWhyWords(row.set.why ?? "sets_nothing")),
      ...view.neverRan.map((row) => row.set.text ?? ""),
    ];
    expect(words.filter((word) => /^none$/i.test(word))).toEqual([]);
  });
});

describe("the source line", () => {
  it("names each source", () => {
    expect(sourceLine("user")).toEqual({ text: "User", description: null });
    expect(sourceLine("project")).toEqual({ text: "Shared project", description: null });
    expect(sourceLine("main")).toEqual({ text: "Settings", description: null });
    expect(sourceLine("unnamed")).toEqual({ text: "Runs with no agent type", description: null });
  });

  it("says the source is unknown for no file, and explains it", () => {
    expect(sourceLine("no_file")).toEqual({
      text: "Source unknown",
      description: "Bar Tab found no user or project file for this agent type.",
    });
  });
});

describe("the Ran with cell", () => {
  it("shows the most common pair with the model's colour", () => {
    const cell = ranCell(agentRow());
    expect(cell).toEqual({ model: "fable", text: "Fable 5.1 · medium", also: [] });
  });

  it("adds an Also line for each other pair, with its runs", () => {
    const row = agentsAnswer().ran[2];
    if (row === undefined) throw new Error("missing");
    expect(ranCell(row).also).toEqual(["Also Sonnet 5.5 · high on 4 runs"]);
  });

  it("uses the singular for one run", () => {
    const cell = ranCell(
      agentRow({
        ran: { model: SONNET, effort: "xhigh", mixed: true },
        ran_pairs: [
          { model: SONNET, effort: "xhigh", runs: 9 },
          { model: SONNET, effort: "low", runs: 1 },
        ],
      }),
    );
    expect(cell.also).toEqual(["Also Sonnet 5.5 · low on 1 run"]);
  });

  it("has no text when the runs name neither a model nor an effort", () => {
    const cell = ranCell(
      agentRow({ ran: { model: null, effort: null, mixed: false }, ran_pairs: [] }),
    );
    expect(cell.text).toBeNull();
    expect(cell.model).toBeNull();
  });
});

describe("the Check cell", () => {
  it("keeps a status the server sent", () => {
    expect(checkStatus(agentRow({ status: "lowered" }))).toBe("lowered");
  });

  it("shows Default when nothing is set", () => {
    expect(checkStatus(agentRow({ status: null, set: null, set_reason: "sets_nothing" }))).toBe(
      "default",
    );
    expect(checkStatus(agentRow({ status: null, set: null, set_reason: "no_file" }))).toBe(
      "default",
    );
  });

  it("has no verdict when the setup could not be read", () => {
    expect(
      checkStatus(agentRow({ status: null, set: null, set_reason: "read_failed" })),
    ).toBeNull();
  });
});

describe("the rows", () => {
  it("name Main session and Unnamed agent, and keep an agent type as sent", () => {
    const names = buildAgents(agentsAnswer()).rows.map((row) => row.name);
    expect(names).toEqual([
      "builder",
      "Main session",
      "reviewer",
      "Unnamed agent",
      "Explore",
      "scribe",
    ]);
  });

  it("show a cost with unpriced requests as at least, and a model with no price as No price", () => {
    const view = buildAgents(
      agentsAnswer({
        ran: [
          agentRow({ cost: 8.28, unpriced: { requests: 2, models: [IDS.fable] } }),
          agentRow({ agent: "x", cost: null, share: null }),
        ],
      }),
    );
    expect(view.rows.map((row) => row.cost)).toEqual(["at least $8.28", "No price"]);
    expect(view.rows[1]?.fill).toBeNull();
  });

  it("scale the cost bar to the biggest cost", () => {
    const view = buildAgents(agentsAnswer());
    expect(view.rows[0]?.fill).toBe(1);
    expect(view.rows[1]?.fill).toBeCloseTo(8 / 40);
  });

  it("add up to the cost and the runs of the answer", () => {
    const answer = agentsAnswer();
    const view = buildAgents(answer);
    const cost = answer.ran.reduce((sum, row) => sum + (row.cost ?? 0), 0);
    expect(cost).toBeCloseTo(50.28);
    expect(view.rows.reduce((sum, row) => sum + row.runs, 0)).toBe(
      answer.ran.reduce((sum, row) => sum + runsOf(row), 0),
    );
  });

  it("counts the Main session once for each session, and a subagent by its runs", () => {
    const view = buildAgents(agentsAnswer());
    expect(view.rows.find((row) => row.key === "@main")?.runs).toBe(53);
    expect(view.rows.find((row) => row.key === "builder")?.runs).toBe(5);
  });

  it("list the agent files that did not run with their source and setup", () => {
    const view = buildAgents(
      agentsAnswer({ never_ran: [noRuns({ set: null, set_reason: "read_failed" })] }),
    );
    expect(view.neverRan).toEqual([
      {
        key: "migrator",
        name: "migrator",
        source: { text: "Shared project", description: null },
        set: { text: null, why: "read_failed" },
      },
    ]);
  });
});
