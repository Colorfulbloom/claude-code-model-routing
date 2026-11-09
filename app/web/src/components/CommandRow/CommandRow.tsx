import { useState } from "react";
import { Button } from "../Button/Button";
import { cx } from "../cx";
import "./CommandRow.css";

export const states = ["default", "copied"] as const;

export interface CommandRowProps {
  /** The command to show and copy. It comes from the bartab-command meta tag, never from the bundle. */
  command: string;
  copyLabel: string;
  /** Polite status shown after a copy, such as "Copied to clipboard". */
  copiedLabel: string;
  /** Copy is the primary action on the locked page. Elsewhere it stays secondary. */
  primary?: boolean;
  /** Forces the copied status, for the component sheet. */
  copied?: boolean;
  className?: string;
}

/** The command in a code well with a Copy button and a polite "Copied" status (components.md entry 31). */
export function CommandRow({
  command,
  copyLabel,
  copiedLabel,
  primary = false,
  copied = false,
  className,
}: CommandRowProps) {
  const [done, setDone] = useState(false);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(command);
      setDone(true);
    } catch {
      /* the clipboard can be blocked, and the command stays selectable */
    }
  }

  return (
    <div className={cx("command-row", className)}>
      <code className="command-row-code">{command}</code>
      <Button
        variant={primary ? "primary" : "secondary"}
        onPress={() => {
          void copy();
        }}
      >
        {copyLabel}
      </Button>
      <p className="command-row-status muted" role="status">
        {done || copied ? copiedLabel : ""}
      </p>
    </div>
  );
}
