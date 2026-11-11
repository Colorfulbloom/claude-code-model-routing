import type { Ref } from "react";
import { cx } from "../cx";
import "./MessageFrame.css";

export type MessageTone = "error" | "warning" | "ok";

export interface MessageFrameProps {
  tone: MessageTone;
  children: React.ReactNode;
  /** Makes the box a focus target for code, such as a refusal the page moves focus to. */
  focusable?: boolean;
  frameRef?: Ref<HTMLDivElement>;
  /** `status` for a polite box. A box that takes focus has no role, so a screen reader reads it once. */
  role?: "status";
  id?: string;
  className?: string;
}

/**
 * The box the edit messages share: a raised surface with a 4px start edge in the tone's colour,
 * with the mark glyph and the words inside (see `Mark`). The edge repeats what the words say and
 * is never the only signal. Refusals, restarts, saved, changed-file warnings and the undo warning
 * all draw on it.
 */
export function MessageFrame({
  tone,
  children,
  focusable = false,
  frameRef,
  role,
  id,
  className,
}: MessageFrameProps) {
  return (
    <div
      ref={frameRef}
      id={id}
      role={role}
      tabIndex={focusable ? -1 : undefined}
      className={cx("message-frame", `message-frame-${tone}`, className)}
    >
      {children}
    </div>
  );
}

/** The glyph that opens a message line. Its alt text is empty, so the words carry the meaning. */
export function Mark({ tone }: { tone: MessageTone }) {
  return <span className={cx("message-mark", `message-mark-${tone}`)} aria-hidden="true" />;
}
