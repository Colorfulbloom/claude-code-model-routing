import { Button } from "../Button/Button";
import { CommandRow } from "../CommandRow/CommandRow";
import { CopyPath } from "../CopyPath/CopyPath";
import { cx } from "../cx";
import { RaisedFinding } from "../RaisedFinding/RaisedFinding";
import "./ToFixRow.css";

export const states = [
  "open-item",
  "copy-command",
  "copy-path",
  "cant-fix-here",
  "couldnt-read",
  "long",
] as const;

/** The one action a row offers. M4 has these four kinds, and no editor buttons until M6. */
export type ToFixAction =
  | { kind: "open_item"; label: string; href: string; ariaLabel?: string }
  | {
      kind: "copy_command";
      command: string;
      copyLabel: string;
      copiedLabel: string;
      ariaLabel?: string;
      /** A line under the command, such as "Bar Tab only copies this command and never runs it." */
      note?: string;
    }
  | { kind: "copy_path"; path: string; label: string; copiedLabel: string; ariaLabel?: string }
  | { kind: "cant_fix_here"; reason: string };

export interface ToFixRowProps {
  /** The h3, naming the thing and the problem, such as "MCP server docs-search won't start". */
  title: string;
  /** What is wrong, such as ".mcp.json points to ./tools/docs-search, which doesn't exist." */
  cause: string;
  /** File and line in code, such as `.mcp.json:8`. */
  location?: string;
  /** What it means for the person, in muted text. */
  consequence: string;
  action: ToFixAction;
  /**
   * A Couldn't read row. It leads with the ✕ glyph, as the raised error finding does, and never
   * uses the Invalid status chip, because Invalid means a wrong value.
   */
  unreadable?: boolean;
  /** Says the copied status through the page's one polite region. */
  onStatus?: (text: string) => void;
  className?: string;
}

/**
 * One counted problem and the one action that fixes it (components.md entry 32). A raised row with
 * an h3 title, the cause with file and line, the consequence in muted text and an action. The group
 * heading above carries the mark, so the row has no start edge. The action is a link that opens the
 * item, a command to copy, a path to copy, or a text reason when the dashboard can't fix it here.
 * Above 720px the action sits in a column at the end of the row, centred on the text. A command row
 * stays under the text, because it needs the width. At 720px and below the action sits under it.
 */
export function ToFixRow({
  title,
  cause,
  location,
  consequence,
  action,
  unreadable = false,
  onStatus,
  className,
}: ToFixRowProps) {
  let control: React.ReactNode;
  switch (action.kind) {
    case "open_item":
      control = (
        <Button
          href={action.href}
          {...(action.ariaLabel !== undefined ? { ariaLabel: action.ariaLabel } : {})}
        >
          {action.label}
        </Button>
      );
      break;
    case "copy_command":
      control = (
        <CommandRow
          command={action.command}
          copyLabel={action.copyLabel}
          copiedLabel={action.copiedLabel}
          {...(action.ariaLabel !== undefined ? { ariaLabel: action.ariaLabel } : {})}
          {...(onStatus !== undefined ? { onStatus } : {})}
        />
      );
      break;
    case "copy_path":
      control = (
        <CopyPath
          value={action.path}
          label={action.label}
          copiedLabel={action.copiedLabel}
          {...(action.ariaLabel !== undefined ? { ariaLabel: action.ariaLabel } : {})}
          {...(onStatus !== undefined ? { onStatus } : {})}
        />
      );
      break;
    case "cant_fix_here":
      control = <p className="tofix-row-cant">{action.reason}</p>;
      break;
  }

  return (
    <li className={cx("tofix-row", className)} data-action={action.kind}>
      <RaisedFinding
        title={title}
        className={cx("tofix-row-box", unreadable && "tofix-row-unreadable")}
      >
        <p className="tofix-row-cause">
          {cause}
          {location !== undefined && (
            <>
              {" "}
              <code className="tofix-row-location">{location}</code>
            </>
          )}
        </p>
        <p className="tofix-row-consequence muted">{consequence}</p>
        <div className="tofix-row-action">{control}</div>
        {action.kind === "copy_command" && action.note !== undefined && (
          <p className="tofix-row-note muted">{action.note}</p>
        )}
      </RaisedFinding>
    </li>
  );
}
