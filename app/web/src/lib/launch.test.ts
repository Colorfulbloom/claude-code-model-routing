import { describe, expect, it } from "vitest";
import { DEFAULT_COMMAND, readLaunch } from "@/lib/launch";

function docWith(html: string): Document {
  return new DOMParser().parseFromString(
    `<html><head>${html}</head><body></body></html>`,
    "text/html",
  );
}

describe("readLaunch", () => {
  it("reads the three meta tags", () => {
    const launch = readLaunch(
      docWith(
        '<meta name="csp-nonce" content="N1"><meta name="bartab-instance" content="inst-a"><meta name="bartab-command" content="/bartab-preview">',
      ),
    );
    expect(launch).toEqual({ nonce: "N1", instance: "inst-a", command: "/bartab-preview" });
  });

  it("falls back when a tag is missing", () => {
    expect(readLaunch(docWith(""))).toEqual({ nonce: "", instance: "", command: DEFAULT_COMMAND });
  });
});
