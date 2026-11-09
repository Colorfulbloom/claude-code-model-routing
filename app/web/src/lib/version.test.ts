import { describe, expect, it } from "vitest";
import { APP_NAME, VERSION } from "@/lib/version";

describe("version", () => {
  it("names the app", () => {
    expect(APP_NAME).toBe("Bar Tab");
  });

  it("matches the server version", () => {
    expect(VERSION).toBe("0.0.0");
  });
});
