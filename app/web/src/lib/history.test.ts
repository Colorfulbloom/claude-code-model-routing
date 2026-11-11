import { describe, expect, it } from "vitest";
import { clockStamp, dateWords, dayLong } from "@/lib/clock";
import {
  backupReason,
  claudeVersionText,
  footerLines,
  pricesText,
  pricesValue,
} from "@/lib/history";
import { appInfo, historyInfo, pricesInfo } from "@/test/server";

const NOW = "2026-11-08T22:00:00Z";
const texts = (lines: { text: string }[]) => lines.map((l) => l.text);

describe("date and time words", () => {
  it("reads a calendar date without a zone shift", () => {
    expect(dateWords("2026-10-28")).toBe("October 28");
    expect(dateWords("2026-01-01")).toBe("January 1");
  });

  it("names the day for History since", () => {
    expect(dayLong(new Date(2026, 8, 3, 14, 20))).toBe("September 3");
  });

  it("shows time only today and the date on another day", () => {
    const today = new Date(2026, 10, 8, 9, 5);
    const earlier = new Date(2026, 10, 7, 23, 58);
    expect(clockStamp(today, new Date(2026, 10, 8, 20, 0))).toBe("9:05 AM");
    expect(clockStamp(earlier, new Date(2026, 10, 8, 20, 0))).toBe("November 7, 11:58 PM");
  });
});

describe("footerLines", () => {
  const rest = appInfo({
    as_of: new Date(2026, 10, 8, 18, 41).toISOString(),
    history: historyInfo({
      oldest: new Date(2026, 8, 3, 14, 20).toISOString(),
      last_backup: new Date(2026, 10, 8, 4, 2).toISOString(),
    }),
  });
  const now = new Date(2026, 10, 8, 20, 0);

  it("has five lines at rest, in order", () => {
    const lines = footerLines(rest, pricesInfo(), now);
    expect(texts(lines)).toEqual([
      "Updated 6:41 PM",
      "History since September 3",
      "Last backup 4:02 AM",
      "Prices as of October 28",
      "Claude Code 2.1.310",
    ]);
    expect(lines.some((l) => l.warn === true)).toBe(false);
  });

  it("puts a day on the backup when it was not today", () => {
    const app = appInfo({
      history: historyInfo({ last_backup: new Date(2026, 10, 7, 23, 58).toISOString() }),
    });
    expect(texts(footerLines(app, pricesInfo(), now))).toContain(
      "Last backup November 7, 11:58 PM",
    );
  });

  it("adds one unreadable line on top, in the singular and the plural", () => {
    const many = footerLines(
      appInfo({ history: historyInfo({ unreadable_files: 3 }) }),
      pricesInfo(),
      NOW,
    );
    expect(texts(many)[0]).toBe("Couldn't read 3 files");
    expect(many[0]?.warn).toBe(true);
    expect(many).toHaveLength(6);
    const one = footerLines(
      appInfo({ history: historyInfo({ unreadable_files: 1 }) }),
      pricesInfo(),
      NOW,
    );
    expect(texts(one)[0]).toBe("Couldn't read 1 file");
  });

  it("replaces the backup line when a backup failed", () => {
    const app = appInfo({
      history: historyInfo({
        backup_failed: { at: new Date(2026, 10, 8, 4, 2).toISOString(), reason_code: "no_space" },
      }),
    });
    const lines = footerLines(app, pricesInfo(), now);
    expect(lines).toHaveLength(5);
    const backup = lines.find((l) => l.id === "backup");
    expect(backup).toEqual({ id: "backup", text: "Backup failed at 4:02 AM", warn: true });
    expect(texts(lines).some((x) => x.startsWith("Last backup"))).toBe(false);
  });

  it("has six lines with both problems", () => {
    const app = appInfo({
      history: historyInfo({
        unreadable_files: 2,
        backup_failed: { at: NOW, reason_code: "copy_failed" },
      }),
    });
    expect(footerLines(app, pricesInfo(), NOW)).toHaveLength(6);
  });

  it("leaves out lines whose facts are missing", () => {
    const app = appInfo({
      as_of: null,
      history: historyInfo({ oldest: null, last_backup: null }),
    });
    expect(texts(footerLines(app, undefined, NOW))).toEqual(["Claude Code 2.1.310"]);
  });
});

describe("claudeVersionText", () => {
  it("names the version, or says unknown when there is none", () => {
    expect(claudeVersionText("2.1.310")).toBe("Claude Code 2.1.310");
    expect(claudeVersionText("")).toBe("Claude Code version unknown");
    expect(claudeVersionText("  ")).toBe("Claude Code version unknown");
    expect(claudeVersionText(null)).toBe("Claude Code version unknown");
  });
});

describe("price source words", () => {
  it.each([
    ["litellm", "Prices as of October 28", "October 28"],
    ["bundled", "Bundled prices, October 28", "Bundled prices, October 28"],
    ["last_good", "Saved prices, October 28", "Saved prices, October 28"],
    ["model_pricing", "Custom prices", "Custom prices"],
  ] as const)("%s", (source, line, value) => {
    const prices = pricesInfo({ source });
    expect(pricesText(prices)).toBe(line);
    expect(pricesValue(prices)).toBe(value);
  });
});

describe("backupReason", () => {
  it("adds the newest good copy when there is one", () => {
    const failure = { at: NOW, reason_code: "no_space" } as const;
    expect(backupReason(failure, new Date(2026, 10, 7, 4, 2).toISOString())).toMatch(
      /^The disk was full.*The newest good backup is from November 7\.$/,
    );
    expect(backupReason(failure, null)).not.toContain("newest");
  });

  it.each(["no_space", "unwritable", "check_failed", "copy_failed"] as const)("says %s", (code) => {
    expect(backupReason({ at: NOW, reason_code: code }, null)).toContain("backup");
  });
});
