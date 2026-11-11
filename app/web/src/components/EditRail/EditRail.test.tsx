import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { samplePreview, scopeRows } from "@/sheet/edit-samples";
import { resetViewport, setViewport } from "@/test/media";
import { RefusedMessage } from "../RefusedMessage/RefusedMessage";
import { SaveToList } from "../SaveToList/SaveToList";
import { ThisSave } from "../ThisSave/ThisSave";
import { EditRail, states, type EditRailProps } from "./EditRail";

afterEach(() => {
  cleanup();
  resetViewport();
});

function rail(props: Partial<EditRailProps> = {}): EditRailProps {
  return {
    field: "effort",
    scopeName: "Project local",
    control: <p>Control</p>,
    saveTo: <SaveToList scopes={scopeRows()} picked="local" onPick={() => undefined} />,
    thisSave: <ThisSave preview={samplePreview()} />,
    summary: "settings.local.json, xhigh to medium",
    onSave: () => undefined,
    onCancel: () => undefined,
    layout: "rail",
    ...props,
  };
}

describe("EditRail", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual([
      "default",
      "message",
      "updating",
      "saving",
      "refusal",
      "sheet",
      "sheet-saving",
    ]);
  });

  it("is a region named Edit effort, with the parts in order and the backup note beside Save", () => {
    const { container } = render(<EditRail {...rail()} />);
    const region = screen.getByRole("region", { name: "Edit effort" });
    const order = [
      ...region.querySelectorAll(".edit-rail-control, .save-to, .this-save, .edit-rail-foot"),
    ].map((el) => el.className.split(" ")[0]);
    expect(order).toEqual(["edit-rail-control", "save-to", "this-save", "edit-rail-foot"]);
    expect(
      within(region).getByText("Bar Tab keeps a copy of the old file, so Undo can put it back."),
    ).toBeInTheDocument();
    expect(container.querySelector(".phone-action-bar")).toBeNull();
  });

  it("names the scope on Save and calls onSave and onCancel", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const onCancel = vi.fn();
    render(<EditRail {...rail({ onSave, onCancel })} />);
    await user.click(screen.getByRole("button", { name: "Save to Project local" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("swaps the label to Saving, keeps both labels in place for a stable width, and ignores a press", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const { container } = render(<EditRail {...rail({ saving: true, onSave })} />);
    const save = screen.getByRole("button", { name: "Saving" });
    expect(save).toHaveAttribute("aria-busy", "true");
    expect(container.querySelectorAll(".edit-save-label > span")).toHaveLength(2);
    expect(container.querySelector(".edit-save-idle")).toHaveAttribute("aria-hidden", "true");
    await user.click(save);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("holds Save and shows the reason beside it when the picked row refuses", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <EditRail {...rail({ refusal: { code: "link_outside", file: "settings.json" }, onSave })} />,
    );
    const save = screen.getByRole("button", { name: "Save to Project local" });
    const reason = screen.getByText(/settings.json links to a file outside your home folder/);
    expect(save).toHaveAttribute("aria-disabled", "true");
    expect(save).toHaveAttribute("aria-describedby", reason.id);
    await user.click(save);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("shows a message above the control, and the heading takes focus from code", () => {
    const ref = createRef<HTMLHeadingElement>();
    const { container } = render(
      <EditRail
        {...rail({
          message: <RefusedMessage code="changed" file="settings.local.json" />,
          headingRef: ref,
        })}
      />,
    );
    const body = container.querySelector(".edit-rail-body");
    expect(body?.firstElementChild).toHaveClass("refused");
    expect(ref.current).toHaveAttribute("tabindex", "-1");
    ref.current?.focus();
    expect(document.activeElement).toBe(ref.current);
  });

  it("is a labelled dialog with Close and the phone action bar when it draws the sheet in place", () => {
    const { container } = render(<EditRail {...rail({ layout: "sheet", inline: true })} />);
    const dialog = screen.getByRole("dialog", { name: "Edit effort" });
    expect(within(dialog).getByRole("button", { name: "Close" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Cancel" })).toBeNull();
    const bar = container.querySelector(".phone-action-bar");
    expect(bar).toHaveTextContent("settings.local.json, xhigh to medium");
    expect(
      within(bar as HTMLElement).getByRole("button", { name: "Save to Project local" }),
    ).toBeInTheDocument();
    expect(container.querySelector(".edit-rail-foot")).toBeNull();
  });

  it("opens the sheet as a modal dialog at 720px and under, and Escape cancels it", async () => {
    setViewport(375);
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(<EditRail {...rail({ layout: "auto", onCancel })} />);
    const dialog = screen.getByRole("dialog", { name: "Edit effort" });
    expect(dialog).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("keeps the modal open on Escape while a save is in flight", async () => {
    setViewport(375);
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(<EditRail {...rail({ layout: "auto", saving: true, onCancel })} />);
    await user.keyboard("{Escape}");
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("is a region at 721px and up when the layout is auto", () => {
    setViewport(1440);
    render(<EditRail {...rail({ layout: "auto" })} />);
    expect(screen.getByRole("region", { name: "Edit effort" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
