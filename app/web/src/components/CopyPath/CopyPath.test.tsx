import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CopyPath, states } from "./CopyPath";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CopyPath", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["default", "copied"]);
  });

  it("shows one button and an empty polite status", () => {
    render(<CopyPath value="/work/a.json" label="Copy path" copiedLabel="Copied to clipboard" />);
    expect(screen.getByRole("button", { name: "Copy path" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("copies the value and says so without changing the label", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    render(<CopyPath value="/work/a.json" label="Copy path" copiedLabel="Copied to clipboard" />);
    await user.click(screen.getByRole("button", { name: "Copy path" }));
    expect(writeText).toHaveBeenCalledWith("/work/a.json");
    expect(await screen.findByText("Copied to clipboard")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Copied to clipboard");
    expect(screen.getByRole("button", { name: "Copy path" })).toBeInTheDocument();
  });

  it("hands the status to the page's live region when onStatus is given", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const onStatus = vi.fn();
    render(
      <CopyPath
        value="/work/a.json"
        label="Copy path"
        copiedLabel="Copied to clipboard"
        onStatus={onStatus}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Copy path" }));
    expect(onStatus).toHaveBeenCalledWith("Copied to clipboard");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("stays quiet when the clipboard is blocked", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("blocked"));
    render(<CopyPath value="/work/a.json" label="Copy path" copiedLabel="Copied to clipboard" />);
    await user.click(screen.getByRole("button", { name: "Copy path" }));
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("takes a longer accessible name", () => {
    render(
      <CopyPath
        value="/work/a.json"
        label="Copy path"
        copiedLabel="Copied"
        ariaLabel="Copy path, a.json"
      />,
    );
    expect(screen.getByRole("button", { name: "Copy path, a.json" })).toBeInTheDocument();
  });

  it("forces the copied status for the sheet", () => {
    render(<CopyPath value="/work/a.json" label="Copy path" copiedLabel="Copied" copied />);
    expect(screen.getByRole("status")).toHaveTextContent("Copied");
  });
});
