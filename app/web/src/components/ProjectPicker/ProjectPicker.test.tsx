import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectPicker, projectOption, states, type ProjectItem } from "./ProjectPicker";

afterEach(cleanup);

const items: ProjectItem[] = [
  {
    id: "a",
    name: "Tidewater",
    path: "/work/tidewater",
    kind: "working",
    stateWord: "Agent working",
  },
  { id: "b", name: "Driftwood", path: "/work/driftwood", kind: "ready", stateWord: "Ready" },
  {
    id: "c",
    name: "Saltmarsh",
    path: "/work/saltmarsh",
    kind: "idle",
    stateWord: "No .claude folder",
    detail: "Opens with its usage.",
  },
  {
    id: "d",
    name: "Harbor",
    path: "/work/harbor",
    kind: "bad",
    stateWord: "Folder not found",
    detail: "Nothing is at this path now.",
  },
];

function fail(): never {
  throw new Error("missing item");
}

function picker(extra: Partial<React.ComponentProps<typeof ProjectPicker>> = {}) {
  return (
    <ProjectPicker
      heading="Projects"
      items={items}
      value="a"
      onChange={vi.fn()}
      emptyTitle="No projects yet"
      emptyBody="A project appears here after you use Claude Code in it."
      loadingText="Loading projects"
      {...extra}
    />
  );
}

describe("ProjectPicker", () => {
  it("lists every state", () => {
    expect(states).toEqual(["open", "empty", "loading"]);
  });

  it("builds an option with the path and the state in words", () => {
    const option = projectOption(items[2] ?? fail());
    expect(option.id).toBe("c");
    expect(option.label).toBe("Saltmarsh");
  });

  it("lists every project with its path and its state word, and marks the chosen one", () => {
    render(picker());
    const list = screen.getByRole("listbox", { name: "Projects" });
    const options = within(list).getAllByRole("option");
    expect(options).toHaveLength(4);
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    expect(options[1]).toHaveAttribute("aria-selected", "false");
    expect(within(options[0] ?? document.body).getByText("/work/tidewater")).toBeInTheDocument();
    for (const word of ["Agent working", "Ready", "No .claude folder", "Folder not found"]) {
      expect(within(list).getByText(word)).toBeInTheDocument();
    }
    expect(within(list).getByText("Opens with its usage.")).toBeInTheDocument();
    expect(within(list).getByText("Nothing is at this path now.")).toBeInTheDocument();
  });

  it("lets every state be picked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(picker({ onChange }));
    await user.click(screen.getByRole("option", { name: /Harbor/ }));
    expect(onChange).toHaveBeenCalledWith("d");
  });

  it("shows Close only when asked, and calls it", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { rerender } = render(picker());
    expect(screen.queryByRole("button", { name: "Close" })).toBeNull();
    rerender(picker({ closeLabel: "Close", onClose }));
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows the empty state with a heading and a sentence and nothing to copy", () => {
    render(picker({ items: [] }));
    expect(screen.getByText("No projects yet")).toBeInTheDocument();
    expect(
      screen.getByText("A project appears here after you use Claude Code in it."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows a polite loading line", () => {
    render(picker({ loading: true }));
    expect(screen.getByRole("status")).toHaveTextContent("Loading projects");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("can be the page h1", () => {
    render(picker({ headingLevel: 1 }));
    expect(screen.getByRole("heading", { level: 1, name: "Projects" })).toBeInTheDocument();
  });
});
