import type { Ref } from "react";
import { CODE_MARK, splitOnMark } from "@/lib/edit-words";
import { t } from "@/strings/t";
import { cx } from "../cx";
import "./EditsOffNote.css";

export const states = [
  "reason",
  "reason-demo",
  "reason-folder",
  "history",
  "route",
  "route-focus",
  "route-agent",
] as const;

interface BaseProps {
  /** An id the disabled Edit button names in aria-describedby, so the reason is read with it. */
  id?: string;
  className?: string;
}

export type EditsOffNoteProps = BaseProps &
  (
    | {
        /** The line under a disabled Edit (`reason`) or at the top of Changes (`history`). */
        kind: "reason" | "history";
        /** The launch command with --allow-edits, from the bartab-command meta tag. */
        command: string;
      }
    | {
        /** The box above an item page opened from an edit link. It takes focus from code. */
        kind: "route";
        command: string;
        /** The item the link was for, such as "Effort". */
        item: string;
        noteRef?: Ref<HTMLDivElement>;
      }
    | {
        /** Edits can't be turned on here. The line names no command. */
        kind: "demo";
      }
    | {
        /** The project's folder is missing, so nothing in it can be edited. */
        kind: "folder";
        /** The folder as the project list shows it, such as "~/work/tidewater-reporting". */
        path: string;
      }
    | {
        /**
         * An edit URL for an agent opened in M6a, which edits no agents. One line above the agent's
         * page, with focus on it, like the route note.
         */
        kind: "agent";
        name: string;
        noteRef?: Ref<HTMLDivElement>;
      }
  );

function LockMark() {
  return (
    <svg
      className="edits-off-lock"
      viewBox="0 0 12 14"
      width="11"
      height="13"
      aria-hidden="true"
      focusable="false"
    >
      <rect x="1.5" y="6" width="9" height="7" rx="1.5" fill="currentColor" />
      <path
        d="M3.5 6V4.2a2.5 2.5 0 0 1 5 0V6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      />
    </svg>
  );
}

function withCommand(text: string, command: string): React.ReactNode {
  const [before, after] = splitOnMark(text);
  return (
    <>
      {before}
      <code className="edits-off-cmd">{command}</code>
      {after}
    </>
  );
}

/**
 * Says why editing is off, and what turns it on (plan 5.2). It comes in three shapes. A quiet
 * line under the disabled Edit button, tied to it by aria-describedby. A note with a lock at the
 * top of Changes. A raised box above an item page opened from an edit link, which takes focus from
 * code. The launch command comes from the page (the bartab-command meta tag plus --allow-edits),
 * never from this file. With no tooltip, the reason is always on screen.
 */
export function EditsOffNote(props: EditsOffNoteProps) {
  const idProps = props.id === undefined ? {} : { id: props.id };
  switch (props.kind) {
    case "reason":
      return (
        <p className={cx("edits-off-reason", props.className)} {...idProps}>
          {withCommand(t("eo_reason", { cmd: CODE_MARK }), props.command)}
        </p>
      );
    case "demo":
      return (
        <p className={cx("edits-off-note", props.className)} {...idProps}>
          <LockMark />
          <span>{t("eo_reason_demo")}</span>
        </p>
      );
    case "folder":
      return (
        <p className={cx("edits-off-note", props.className)} {...idProps}>
          <LockMark />
          <span>{t("eo_reason_folder", { path: props.path })}</span>
        </p>
      );
    case "agent":
      return <AgentNote {...props} />;
    case "history":
      return (
        <p className={cx("edits-off-note", props.className)} {...idProps}>
          <LockMark />
          <span>{withCommand(t("eo_hist_note", { cmd: CODE_MARK }), props.command)}</span>
        </p>
      );
    case "route":
      return <RouteNote {...props} />;
  }
}

type AgentProps = Extract<EditsOffNoteProps, { kind: "agent" }>;

/** The one line above an agent opened from an edit link. It takes focus from code. */
function AgentNote({ id, className, name, noteRef }: AgentProps) {
  return (
    <div
      ref={noteRef}
      tabIndex={-1}
      className={cx("edits-off-route", "edits-off-agent", className)}
      {...(id === undefined ? {} : { id })}
    >
      <p>
        <LockMark />
        <span>{t("eo_route_agent", { name })}</span>
      </p>
    </div>
  );
}

type RouteProps = Extract<EditsOffNoteProps, { kind: "route" }>;

function RouteNote({ id, className, command, item, noteRef }: RouteProps) {
  return (
    <div
      ref={noteRef}
      tabIndex={-1}
      className={cx("edits-off-route", className)}
      {...(id === undefined ? {} : { id })}
    >
      <p>
        <LockMark />
        <span>{withCommand(t("eo_route", { item, cmd: CODE_MARK }), command)}</span>
      </p>
    </div>
  );
}
