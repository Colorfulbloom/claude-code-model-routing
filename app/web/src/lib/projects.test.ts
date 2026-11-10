import { describe, expect, it } from "vitest";
import { projectItem } from "@/lib/projects";

const base = {
  key: "k",
  name: "Name",
  display_path: "/work/k",
  running: false,
  listed: true,
} as const;

describe("projectItem", () => {
  it("reads a ready project", () => {
    expect(projectItem({ ...base, state: "ok" })).toMatchObject({
      kind: "ready",
      stateWord: "Ready",
      path: "/work/k",
    });
  });

  it("reads a running project as Agent working", () => {
    expect(projectItem({ ...base, state: "ok", running: true })).toMatchObject({
      kind: "working",
      stateWord: "Agent working",
    });
  });

  it("gives the two odd states a word and a line, and keeps them pickable", () => {
    expect(projectItem({ ...base, state: "no_claude_folder" })).toMatchObject({
      kind: "idle",
      stateWord: "No .claude folder",
      detail: expect.stringContaining("without project settings") as string,
    });
    expect(projectItem({ ...base, state: "folder_not_found" })).toMatchObject({
      kind: "bad",
      stateWord: "Folder not found",
      detail: expect.stringContaining("no project setup") as string,
    });
  });
});
