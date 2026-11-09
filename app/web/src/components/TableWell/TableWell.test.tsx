import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { TableWell, states, type TableColumn, type TableRowData } from "./TableWell";

afterEach(cleanup);

const columns: TableColumn[] = [
  { id: "time", name: "Time", rowHeader: true },
  { id: "agent", name: "Agent" },
  { id: "model", name: "Model", hp: true },
  { id: "tokens", name: "Tokens", align: "end" },
];

const rows: TableRowData[] = [
  {
    id: "a",
    cells: { time: <a href="#a">6:39:50</a>, agent: "Main session", model: "Opus", tokens: "48K" },
  },
  { id: "b", cells: { time: "6:39:48", agent: "tech-writer", model: "Fable", tokens: "36K" } },
];

describe("TableWell", () => {
  it("lists its states", () => {
    expect(states).toEqual(["default", "hover", "empty", "error", "loading"]);
  });

  it("renders a named table with a header row and one row per item", () => {
    render(<TableWell label="Latest requests" columns={columns} rows={rows} />);
    expect(screen.getByRole("grid", { name: "Latest requests" })).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader")).toHaveLength(4);
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(screen.getByRole("link", { name: "6:39:50" })).toHaveAttribute("href", "#a");
  });

  it("keeps hidden-at-phone columns in the DOM, headers included", () => {
    render(<TableWell label="Latest requests" columns={columns} rows={rows} />);
    const header = screen.getByRole("columnheader", { name: "Model" });
    expect(header).toHaveClass("table-well-hp");
    expect(screen.getByRole("gridcell", { name: "Opus" })).toHaveClass("table-well-hp");
  });

  it("right-aligns number columns", () => {
    render(<TableWell label="Latest requests" columns={columns} rows={rows} />);
    expect(screen.getByRole("gridcell", { name: "48K" })).toHaveClass("table-well-end", "num");
    expect(screen.getByRole("columnheader", { name: "Tokens" })).toHaveClass("table-well-end");
  });

  it("says what will appear when empty and offers the action", () => {
    render(
      <TableWell
        label="Sessions"
        columns={columns}
        rows={[]}
        empty={{ text: "No sessions yet.", action: { label: "Show all time", href: "#all" } }}
      />,
    );
    expect(screen.getByText("No sessions yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Show all time" })).toHaveAttribute("href", "#all");
  });

  it("shows an error row above the rows that loaded", () => {
    render(
      <TableWell
        label="Sessions"
        columns={columns}
        rows={rows}
        error={{ text: "Couldn't load." }}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load.");
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("is busy with one spoken line while loading", () => {
    const { container } = render(
      <TableWell
        label="Sessions"
        columns={columns}
        rows={rows}
        loading={{ label: "Loading sessions" }}
      />,
    );
    expect(container.querySelector('.well[aria-busy="true"]')).not.toBeNull();
    expect(screen.getByText("Loading sessions")).toBeInTheDocument();
    expect(screen.queryByText("Main session")).toBeNull();
  });
});
