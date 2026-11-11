import type { Ref } from "react";
import type { RestartState } from "@/api/edit";
import { CODE_MARK, splitOnMark } from "@/lib/edit-words";
import { t } from "@/strings/t";
import { Button } from "../Button/Button";
import { cx } from "../cx";
import { Mark, MessageFrame } from "../RefusedMessage/MessageFrame";
import "../EditsOffNote/EditsOffNote.css";
import "./RestartBox.css";

export const states = ["off", "on", "unknown", "phone"] as const;

export interface RestartBoxProps {
  /** The restart state from the edit layer. `mode` is the new server's mode, or null before it is known. */
  restart: Pick<RestartState, "mode">;
  /** The launch command with --allow-edits, from the bartab-command meta tag. Named when editing is off. */
  command: string;
  /** Reloads the page, so it reads the new server's mode and keys. */
  onReload: () => void;
  /** Where focus goes when the box appears. The box has tabindex -1 and no role="alert". */
  messageRef?: Ref<HTMLDivElement>;
  id?: string;
  className?: string;
}

/**
 * Tells the person the server restarted after the page loaded, so the page can't save (plan 3.2
 * and 5.1). When the new server has editing off, the body names the command that turns it on. In
 * every other case it says to reload. The Reload button is the primary action, and the box holds
 * Save in the rail until the page reloads. Like a refusal, it takes focus from code and has no
 * role="alert".
 */
export function RestartBox({
  restart,
  command,
  onReload,
  messageRef,
  id,
  className,
}: RestartBoxProps) {
  const off = restart.mode === "off";
  const [before, after] = splitOnMark(t("eo_restart_b", { cmd: CODE_MARK }));
  return (
    <MessageFrame
      tone="error"
      focusable
      {...(messageRef === undefined ? {} : { frameRef: messageRef })}
      {...(id === undefined ? {} : { id })}
      className={cx("restart-box", className)}
    >
      <p>
        <Mark tone="error" />
        <b className="restart-box-head">{off ? t("eo_restart_h") : t("eo_restart_on_h")}</b>
      </p>
      <p className="restart-box-body">
        {off ? (
          <>
            {before}
            <code className="edits-off-cmd">{command}</code>
            {after}
          </>
        ) : (
          t("eo_restart_on_b")
        )}
      </p>
      <div className="restart-box-actions">
        <Button variant="primary" onPress={onReload}>
          {t("eo_reload")}
        </Button>
      </div>
    </MessageFrame>
  );
}
