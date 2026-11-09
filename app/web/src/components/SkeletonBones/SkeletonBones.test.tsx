import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SkeletonBones, states } from "./SkeletonBones";

afterEach(cleanup);

describe("SkeletonBones", () => {
  it("lists every state", () => {
    expect(states).toEqual(["text", "value", "rows"]);
  });

  it("is aria-busy, speaks one line, and hides the bones", () => {
    const { container } = render(
      <SkeletonBones
        label="Loading sessions"
        bones={[{ width: "m" }, { width: "s", height: "value" }]}
      />,
    );
    expect(container.firstElementChild).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Loading sessions")).toBeInTheDocument();
    const bones = container.querySelectorAll(".bone");
    expect(bones).toHaveLength(2);
    for (const bone of bones) expect(bone).toHaveAttribute("aria-hidden", "true");
  });
});
