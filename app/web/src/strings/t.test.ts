import { describe, expect, it } from "vitest";
import { t, tn } from "@/strings/t";

describe("t", () => {
  it("returns a plain value", () => {
    expect(t("nav_live")).toBe("Live");
    expect(t("product")).toBe("Bar Tab");
  });

  it("fills params", () => {
    expect(t("lk_route2", { page: "Agents", project: "builder" })).toBe(
      "This tab reopens on Agents, builder once another tab opens the dashboard.",
    );
    expect(t("updated_at", { time: "6:39 PM" })).toBe("Updated 6:39 PM");
  });

  it("rejects a missing key or param at compile time", () => {
    // @ts-expect-error no such key
    expect(() => t("not_a_key")).toThrow();
    // @ts-expect-error params are required for this key
    expect(t("lk_route2")).toContain("{page}");
    // @ts-expect-error project is missing
    expect(t("lk_route2", { page: "Agents" })).toContain("{project}");
  });
});

describe("tn", () => {
  it("picks one for 1 and other for the rest", () => {
    expect(tn("tofix_aria", 1)).toBe("To fix, 1 item");
    expect(tn("tofix_aria", 4)).toBe("To fix, 4 items");
    expect(tn("tofix_aria", 0)).toBe("To fix, 0 items");
  });

  it("rejects a key with no plural pair at compile time", () => {
    // @ts-expect-error nav_live has no _one and _other
    expect(() => tn("nav_live", 2)).toThrow();
  });
});
