import { useState } from "react";
import { Button } from "../Button/Button";
import { cx } from "../cx";
import "./CopyPath.css";

export const states = ["default", "copied"] as const;

export interface CopyPathProps {
  /** The text the button puts on the clipboard, such as a file path. */
  value: string;
  /** The visible button label, such as "Copy path". */
  label: string;
  /** Polite status shown after a copy, such as "Copied to clipboard". */
  copiedLabel: string;
  /** Names the button when several rows carry the same label, such as "Copy path, notes.md". */
  ariaLabel?: string;
  /** Forces the copied status, for the component sheet. */
  copied?: boolean;
  /**
   * Says the copied status through the page's one polite region, as CommandRow does. The visible
   * status stays, but it is not a second live region.
   */
  onStatus?: (text: string) => void;
  className?: string;
}

/**
 * A secondary button that copies a path and says "Copied" in a polite status beside it
 * (components.md entry 31 pattern, for Copy path in the inspector and in To fix rows). The label
 * never changes, so the button keeps its size. The status takes no room while it is empty.
 */
export function CopyPath({
  value,
  label,
  copiedLabel,
  ariaLabel,
  copied = false,
  onStatus,
  className,
}: CopyPathProps) {
  const [done, setDone] = useState(false);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(value);
      setDone(true);
      onStatus?.(copiedLabel);
    } catch {
      /* the clipboard can be blocked, and the path stays selectable where it is shown */
    }
  }

  return (
    <span className={cx("copy-path", className)}>
      <Button
        {...(ariaLabel !== undefined ? { ariaLabel } : {})}
        onPress={() => {
          void copy();
        }}
      >
        {label}
      </Button>
      <span
        className="copy-path-status muted"
        {...(onStatus === undefined ? { role: "status" } : {})}
      >
        {done || copied ? copiedLabel : ""}
      </span>
    </span>
  );
}
