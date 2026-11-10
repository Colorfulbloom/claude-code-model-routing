import { act, cleanup, renderHook } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_RANGE,
  RANGES,
  RANGE_STORAGE_KEY,
  isRange,
  parseRange,
  readLastRange,
  reviewPath,
  useRangeParam,
  writeLastRange,
} from "@/lib/range";

beforeEach(() => {
  sessionStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("RANGES", () => {
  it("lists the six presets in the Select's order", () => {
    expect(RANGES).toEqual(["today", "7d", "30d", "90d", "12m", "all"]);
    expect(DEFAULT_RANGE).toBe("30d");
  });

  it("knows a preset from anything else", () => {
    expect(RANGES.every((range) => isRange(range))).toBe(true);
    expect(isRange("1y")).toBe(false);
    expect(isRange("30D")).toBe(false);
    expect(isRange(null)).toBe(false);
  });
});

describe("parseRange", () => {
  it("passes every preset and leaves the URL alone", () => {
    for (const range of RANGES) expect(parseRange(range)).toEqual({ range, replace: false });
  });

  it("uses the fallback when the link has no range, without replacing the URL", () => {
    expect(parseRange(null, "90d")).toEqual({ range: "90d", replace: false });
    expect(parseRange(null)).toEqual({ range: "30d", replace: false });
  });

  it("falls back to 30 days for an unknown value and asks to replace the URL", () => {
    expect(parseRange("1y", "90d")).toEqual({ range: "30d", replace: true });
    expect(parseRange("", "90d")).toEqual({ range: "30d", replace: true });
    expect(parseRange("30d ", "90d")).toEqual({ range: "30d", replace: true });
  });
});

describe("last pick in sessionStorage", () => {
  it("round trips a range", () => {
    expect(readLastRange()).toBeNull();
    writeLastRange("12m");
    expect(readLastRange()).toBe("12m");
  });

  it("ignores a stored value that is not a preset", () => {
    sessionStorage.setItem(RANGE_STORAGE_KEY, "forever");
    expect(readLastRange()).toBeNull();
  });

  it("survives storage that throws on read and on write", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(readLastRange()).toBeNull();
    expect(() => {
      writeLastRange("7d");
    }).not.toThrow();
  });
});

describe("reviewPath", () => {
  it("keeps the range on a page link", () => {
    expect(reviewPath("builder", "summary", "90d")).toBe("/p/builder/review/summary?range=90d");
    expect(reviewPath("builder", "models", "today")).toBe("/p/builder/review/models?range=today");
  });

  it("links a session with its range and extra params, and encodes the parts", () => {
    expect(reviewPath("my proj", { session: "a/b" }, "7d", { at: 12 })).toBe(
      "/p/my%20proj/review/sessions/a%2Fb?range=7d&at=12",
    );
  });

  it("leaves out an extra that is null or undefined", () => {
    expect(reviewPath("builder", "sessions", "all", { at: null, x: undefined })).toBe(
      "/p/builder/review/sessions?range=all",
    );
  });
});

function mountRange(url: string) {
  return renderHook(
    () => {
      const param = useRangeParam();
      const location = useLocation();
      return { ...param, search: location.search };
    },
    {
      wrapper: ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={[url]}>{children}</MemoryRouter>
      ),
    },
  );
}

describe("useRangeParam", () => {
  it("reads a good range and remembers it for the tab", () => {
    const { result } = mountRange("/x?range=90d");
    expect(result.current.range).toBe("90d");
    expect(result.current.search).toBe("?range=90d");
    expect(readLastRange()).toBe("90d");
  });

  it("uses the tab's last pick when the link has no range", () => {
    writeLastRange("7d");
    const { result } = mountRange("/x");
    expect(result.current.range).toBe("7d");
    expect(result.current.search).toBe("");
  });

  it("uses 30 days when there is no range and no last pick", () => {
    const { result } = mountRange("/x");
    expect(result.current.range).toBe("30d");
  });

  it("answers 30 days at once for a bad range and replaces the URL", () => {
    writeLastRange("7d");
    const { result } = mountRange("/x?range=1y&keep=1");
    expect(result.current.range).toBe("30d");
    expect(result.current.search).toBe("?range=30d&keep=1");
  });

  it("sets a range, keeps the other params and remembers it", () => {
    const { result } = mountRange("/x?range=7d&at=4");
    act(() => {
      result.current.setRange("12m");
    });
    expect(result.current.range).toBe("12m");
    expect(result.current.search).toBe("?range=12m&at=4");
    expect(readLastRange()).toBe("12m");
  });

  it("works when storage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    const { result } = mountRange("/x?range=90d");
    expect(result.current.range).toBe("90d");
    act(() => {
      result.current.setRange("all");
    });
    expect(result.current.range).toBe("all");
  });
});
