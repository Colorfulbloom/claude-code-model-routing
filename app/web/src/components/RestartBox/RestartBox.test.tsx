import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RestartBox, states } from "./RestartBox";

afterEach(cleanup);

const CMD = "/bartab-preview --allow-edits";

describe("RestartBox", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["off", "on", "unknown", "phone"]);
  });

  it("names the command when the new server has editing off", () => {
    const { container } = render(
      <RestartBox restart={{ mode: "off" }} command={CMD} onReload={() => undefined} />,
    );
    expect(
      screen.getByText(
        "Bar Tab restarted with editing off after this page loaded, so this page can't save.",
      ),
    ).toBeInTheDocument();
    expect(container).toHaveTextContent(
      `Reload to see the page as it is now. To edit again, start Bar Tab with ${CMD} first.`,
    );
    expect(container.querySelector("code")).toHaveTextContent(CMD);
  });

  it("says to reload when editing is on, and when the mode isn't known yet", () => {
    for (const mode of ["on", "unavailable", null] as const) {
      const { container, unmount } = render(
        <RestartBox restart={{ mode }} command={CMD} onReload={() => undefined} />,
      );
      expect(
        screen.getByText("Bar Tab restarted after this page loaded, so this page can't save."),
      ).toBeInTheDocument();
      expect(screen.getByText("Reload the page to edit again.")).toBeInTheDocument();
      expect(container.querySelector("code")).toBeNull();
      unmount();
    }
  });

  it("reloads from the primary Reload button", async () => {
    const user = userEvent.setup();
    const onReload = vi.fn();
    render(<RestartBox restart={{ mode: "on" }} command={CMD} onReload={onReload} />);
    const button = screen.getByRole("button", { name: "Reload" });
    expect(button).toHaveClass("button-primary");
    await user.click(button);
    expect(onReload).toHaveBeenCalledTimes(1);
  });

  it("takes focus from code, with no alert role, and a hidden glyph", () => {
    const ref = createRef<HTMLDivElement>();
    const { container } = render(
      <RestartBox
        restart={{ mode: "on" }}
        command={CMD}
        onReload={() => undefined}
        messageRef={ref}
      />,
    );
    expect(ref.current).toHaveAttribute("tabindex", "-1");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(container.querySelector(".message-mark")).toHaveAttribute("aria-hidden", "true");
  });
});
