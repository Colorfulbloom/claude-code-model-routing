import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ModelSwatch, states } from "./ModelSwatch";

afterEach(cleanup);

describe("ModelSwatch", () => {
  it("has a shape class for every model and hides it from assistive tech", () => {
    for (const model of states) {
      const { container, unmount } = render(<ModelSwatch model={model} />);
      const swatch = container.firstElementChild;
      expect(swatch).toHaveClass(`model-swatch-${model}`);
      expect(swatch).toHaveAttribute("aria-hidden", "true");
      unmount();
    }
  });
});
