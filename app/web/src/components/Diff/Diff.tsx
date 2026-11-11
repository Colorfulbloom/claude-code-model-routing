import type { DiffLine } from "@/api/edit";
import { t, tn } from "@/strings/t";
import { cx } from "../cx";
import "./Diff.css";

export const states = ["default", "link", "new-file", "no-path", "wrap"] as const;

export interface DiffProps {
  lines: DiffLine[];
  /** Names the list for a screen reader, such as "This save". */
  label: string;
  /** The path the diff changes, on a line above the lines. Leave it out where the card already shows it. */
  path?: string;
  /** The real file, when the path is a link. */
  linksTo?: string;
  className?: string;
}

function gutterWord(kind: DiffLine["kind"]): string {
  switch (kind) {
    case "add":
      return t("ed_diff_added");
    case "del":
      return t("ed_diff_removed");
    case "ctx":
      return t("ed_diff_same");
  }
}

const GLYPH: Record<DiffLine["kind"], string> = { add: "+", del: "-", ctx: "" };

/** A row of the list: one line of the diff, or a run of unchanged lines the server left out. */
export type DiffRow = { kind: "line"; line: DiffLine } | { kind: "fold"; count: number };

/**
 * The lines with a fold row wherever the line numbers jump. The server sends the changed lines
 * with a few lines of context, so a jump in the numbers is a run of unchanged lines. The old side
 * and the new side each count on their own, because a removed line has no new number and an added
 * line has no old one, and a gap is the same size on both.
 */
export function withFolds(lines: readonly DiffLine[]): DiffRow[] {
  const rows: DiffRow[] = [];
  let oldAt = 0;
  let newAt = 0;
  for (const line of lines) {
    const gap =
      line.old_n !== null ? line.old_n - oldAt - 1 : (line.new_n ?? newAt + 1) - newAt - 1;
    if (gap > 0) rows.push({ kind: "fold", count: gap });
    rows.push({ kind: "line", line });
    if (line.old_n !== null) oldAt = line.old_n;
    if (line.new_n !== null) newAt = line.new_n;
  }
  return rows;
}

/**
 * The exact change to a file, shown before every save (components.md entry 29). A well with the
 * real path line, then numbered lines. An added line carries a plus and a removed line a minus in
 * the gutter, beside its tint, and a screen reader hears "added" or "removed" before the text. Long
 * lines wrap at any character and never scroll sideways. Line numbers are the file's own: a removed
 * line shows its old number and the rest show the new one. A run of unchanged lines the server
 * left out shows as one "N unchanged lines" row, so the diff never cuts a stretch without saying so.
 */
export function Diff({ lines, label, path, linksTo, className }: DiffProps) {
  const rows = withFolds(lines);
  return (
    <div className={cx("diff", className)}>
      {path !== undefined && (
        <p className="diff-path">
          <span className="diff-path-text">{path}</span>
          {linksTo !== undefined && (
            <span className="diff-path-link">
              <span aria-hidden="true">{"↪"}</span> {t("ed_links_to")}{" "}
              <span className="diff-path-text">{linksTo}</span>
            </span>
          )}
        </p>
      )}
      <ol className="diff-lines" aria-label={label}>
        {rows.map((row, i) =>
          row.kind === "fold" ? (
            <li key={`fold-${String(i)}`} className="diff-line diff-fold">
              <span className="diff-ln" aria-hidden="true">
                {"⋮"}
              </span>
              <span className="diff-gm" aria-hidden="true" />
              <span className="diff-fold-text">{tn("ed_diff_fold", row.count)}</span>
            </li>
          ) : (
            <li
              key={`${String(i)}-${String(row.line.old_n)}-${String(row.line.new_n)}`}
              className={cx("diff-line", row.line.kind !== "ctx" && `diff-${row.line.kind}`)}
            >
              <span className="diff-ln">
                {row.line.kind === "del" ? row.line.old_n : row.line.new_n}
              </span>
              <span className="diff-gm" aria-hidden="true">
                {GLYPH[row.line.kind]}
              </span>
              <span className="sr-only">{gutterWord(row.line.kind)} </span>
              <code className="diff-code">{row.line.text}</code>
            </li>
          ),
        )}
      </ol>
    </div>
  );
}
