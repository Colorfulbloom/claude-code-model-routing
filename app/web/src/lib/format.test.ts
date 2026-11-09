import { describe, expect, it } from "vitest";
import { formatCost, formatCostAtLeast, formatTokens } from "./format";

describe("formatCost", () => {
  it("shows cents below $1,000", () => {
    expect(formatCost(8.283)).toBe("$8.28");
    expect(formatCost(0.05)).toBe("$0.05");
    expect(formatCost(999.99)).toBe("$999.99");
    expect(formatCost(0)).toBe("$0.00");
  });

  it("drops cents from $1,000 up", () => {
    expect(formatCost(1000)).toBe("$1,000");
    expect(formatCost(1234.56)).toBe("$1,235");
  });

  it("rounds a value that reaches $1,000 to whole dollars", () => {
    expect(formatCost(999.996)).toBe("$1,000");
  });

  it("marks a tiny non-zero cost", () => {
    expect(formatCost(0.004)).toBe("<$0.01");
    expect(formatCost(0.005)).toBe("$0.01");
  });
});

describe("formatCostAtLeast", () => {
  it("wraps the cost", () => {
    expect(formatCostAtLeast(0.97)).toBe("at least $0.97");
    expect(formatCostAtLeast(2000)).toBe("at least $2,000");
  });
});

describe("formatTokens", () => {
  it("abbreviates", () => {
    expect(formatTokens(42)).toBe("42");
    expect(formatTokens(334_000)).toBe("334K");
    expect(formatTokens(5_300_000)).toBe("5.3M");
    expect(formatTokens(120_000_000)).toBe("120M");
    expect(formatTokens(1_200_000_000)).toBe("1.2B");
    expect(formatTokens(999_700)).toBe("1.0M");
  });
});
