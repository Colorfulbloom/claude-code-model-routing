import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToFixRow, states, type ToFixAction, type ToFixRowProps } from "./ToFixRow";

afterEach(cleanup);

function row(action: ToFixAction, extra: Partial<ToFixRowProps> = {}) {
  return (
    <ul>
      <ToFixRow
        title="MCP server docs-search won't start"
        cause=".mcp.json points to ./tools/docs-search, which doesn't exist."
        location=".mcp.json:8"
        consequence="Claude Code skips this server, so its tools aren't available."
        action={action}
        {...extra}
      />
    </ul>
  );
}

describe("ToFixRow", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual([
      "open-item",
      "copy-command",
      "copy-path",
      "cant-fix-here",
      "couldnt-read",
      "long",
    ]);
  });

  it("is a list item with an h3 title, the cause with file and line, and the consequence", () => {
    render(row({ kind: "open_item", label: "Open in MCP servers", href: "#/setup/mcp/docs" }));
    expect(screen.getByRole("listitem")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: "MCP server docs-search won't start" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/points to \.\/tools\/docs-search/)).toBeInTheDocument();
    expect(screen.getByText(".mcp.json:8").tagName).toBe("CODE");
    const consequence = screen.getByText(/Claude Code skips this server/);
    expect(consequence).toHaveClass("muted");
  });

  it("opens the item with a link for open_item", () => {
    render(row({ kind: "open_item", label: "Open in MCP servers", href: "#/setup/mcp/docs" }));
    expect(screen.getByRole("link", { name: "Open in MCP servers" })).toHaveAttribute(
      "href",
      "#/setup/mcp/docs",
    );
    expect(screen.getByRole("listitem")).toHaveAttribute("data-action", "open_item");
  });

  it("shows a command row for copy_command and copies the command", async () => {
    const user = userEvent.setup();
    render(
      row({
        kind: "copy_command",
        command: "claude mcp remove docs-search",
        copyLabel: "Copy command",
        copiedLabel: "Copied to clipboard",
      }),
    );
    expect(screen.getByText("claude mcp remove docs-search").tagName).toBe("CODE");
    await user.click(screen.getByRole("button", { name: "Copy command" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Copied to clipboard");
  });

  it("shows a copy button for copy_path with a polite Copied status", async () => {
    const user = userEvent.setup();
    render(
      row({
        kind: "copy_path",
        path: "/work/home/agents/notes.md",
        label: "Copy path",
        copiedLabel: "Copied to clipboard",
        ariaLabel: "Copy path, notes.md",
      }),
    );
    await user.click(screen.getByRole("button", { name: "Copy path, notes.md" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Copied to clipboard");
    expect(await navigator.clipboard.readText()).toBe("/work/home/agents/notes.md");
  });

  it("routes the copied status to the page's live region when onStatus is given", async () => {
    const user = userEvent.setup();
    const onStatus = vi.fn();
    render(
      row(
        { kind: "copy_path", path: "/work/a.md", label: "Copy path", copiedLabel: "Copied" },
        { onStatus },
      ),
    );
    await user.click(screen.getByRole("button", { name: "Copy path" }));
    expect(onStatus).toHaveBeenCalledWith("Copied");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows only a text reason for cant_fix_here, with no button or link", () => {
    render(
      row({
        kind: "cant_fix_here",
        reason: "Your organization manages this file, so the dashboard can't change it.",
      }),
    );
    expect(screen.getByText(/Your organization manages this file/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("marks a Couldn't read row with the ✕ glyph and never the Invalid chip", () => {
    const { container } = render(
      row(
        { kind: "copy_path", path: "/work/a.md", label: "Copy path", copiedLabel: "Copied" },
        { unreadable: true },
      ),
    );
    expect(container.querySelector(".tofix-row-unreadable")).not.toBeNull();
    expect(container.querySelector(".status-chip")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the note under a copy_command row and names the button when it has an aria label", () => {
    render(
      row({
        kind: "copy_command",
        command: "claude mcp remove archive -s user",
        copyLabel: "Copy command",
        copiedLabel: "Copied",
        ariaLabel: "Copy command for archive",
        note: "Bar Tab only copies this command and never runs it.",
      }),
    );
    expect(screen.getByText("Bar Tab only copies this command and never runs it.")).toHaveClass(
      "tofix-row-note",
    );
    expect(screen.getByRole("button", { name: "Copy command for archive" })).toBeInTheDocument();
  });

  it("has no start edge on a normal row", () => {
    const { container } = render(row({ kind: "cant_fix_here", reason: "Managed." }));
    expect(container.querySelector(".raised-finding-marked")).toBeNull();
  });
});
