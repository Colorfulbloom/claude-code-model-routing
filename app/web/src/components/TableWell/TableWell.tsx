import { Cell, Column, Row, Table, TableBody, TableHeader } from "react-aria-components";
import { cx } from "../cx";
import { EmptyState, type EmptyStateProps } from "../EmptyState/EmptyState";
import { RaisedFinding } from "../RaisedFinding/RaisedFinding";
import { SkeletonBones } from "../SkeletonBones/SkeletonBones";
import { Well } from "../Well/Well";
import "./TableWell.css";

export const states = ["default", "hover", "empty", "error", "loading"] as const;

export interface TableColumn {
  id: string;
  /** The header word. It stays in the DOM at every width. */
  name: string;
  /** Numbers and costs. Right-aligned with tabular figures. */
  align?: "end";
  /** Hidden at 720 px and below (the `hp` columns). The header is clip-hidden, never display:none. */
  hp?: boolean;
  /** The row's name cell. One column should set it, so each row has a name for assistive tech. */
  rowHeader?: boolean;
}

export interface TableRowData {
  id: string;
  /** Cell content by column id. The first cell is a link when the row opens something. */
  cells: Readonly<Record<string, React.ReactNode>>;
  /** Forces the hover look, for the component sheet. */
  className?: string;
}

export interface TableWellProps {
  /** Accessible name of the table. */
  label: string;
  columns: readonly TableColumn[];
  rows: readonly TableRowData[];
  /** Skeleton bones in place of the rows. `label` is the one line a screen reader hears. */
  loading?: { label: string };
  /** Shown when there are no rows. Says what will appear, plus the action that fills it. */
  empty?: { text: string; action?: EmptyStateProps["action"] };
  /** A raised error row above the rows that did load. */
  error?: { text: string };
  className?: string;
}

/**
 * Rows to compare across the same columns, inside a well (components.md entry 24). It is a React
 * Aria Table, so it follows the APG grid keyboard model. Header text is muted and numbers are
 * right-aligned with tabular figures. Columns marked `hp` clip-hide at 720 px and below.
 */
export function TableWell({
  label,
  columns,
  rows,
  loading,
  empty,
  error,
  className,
}: TableWellProps) {
  const shown = loading === undefined ? rows : [];
  return (
    <div className={cx("table-well", className)}>
      {error !== undefined && (
        <RaisedFinding variant="error" className="table-well-error">
          {error.text}
        </RaisedFinding>
      )}
      <Well variant="list" aria-busy={loading !== undefined ? "true" : undefined}>
        <Table aria-label={label} className="table-well-table">
          <TableHeader columns={columns}>
            {(column) => (
              <Column
                isRowHeader={column.rowHeader === true}
                className={cx(
                  "table-well-th",
                  column.align === "end" && "table-well-end",
                  column.hp === true && "table-well-hp",
                )}
              >
                {column.name}
              </Column>
            )}
          </TableHeader>
          <TableBody
            items={shown}
            renderEmptyState={() =>
              loading !== undefined ? (
                <SkeletonBones
                  label={loading.label}
                  bones={[{ width: "full" }, { width: "full" }, { width: "full" }]}
                />
              ) : empty !== undefined ? (
                <EmptyState {...(empty.action !== undefined ? { action: empty.action } : {})}>
                  {empty.text}
                </EmptyState>
              ) : null
            }
          >
            {(row) => (
              <Row columns={columns} className={cx("table-well-row", row.className)}>
                {(column) => (
                  <Cell
                    className={cx(
                      "table-well-td",
                      column.align === "end" && "table-well-end num",
                      column.hp === true && "table-well-hp",
                    )}
                  >
                    {row.cells[column.id]}
                  </Cell>
                )}
              </Row>
            )}
          </TableBody>
        </Table>
      </Well>
    </div>
  );
}
