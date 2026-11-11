/*
 * The Live header (components.md entry 3, revised). The run state and the branch share a line, then
 * the sub line, then on the right the Session Select, the time line for the states that have one,
 * and Pause. Nothing shows a time while the page is live. The time line carries no live region,
 * because the one polite region speaks Pause and Resume.
 *
 * The h1 is a new element whenever the page moves from bones to a session, or to another session,
 * so the route harness's focus on the old one is lost. A new header takes focus when nothing else
 * holds it.
 */
import { useEffect, useRef } from "react";
import { Button } from "@/components/Button/Button";
import { RunStateGlyph } from "@/components/RunStateGlyph/RunStateGlyph";

export interface LiveHeaderProps {
  /** The run state beside the title, or null for the pages with no session. */
  state: { kind: "working" | "idle" | "ended"; word: string } | null;
  title: string;
  /** The title is a prompt such as "No git branch", so it reads muted. */
  titleMuted?: boolean;
  sub: string | null;
  /** The right-hand time line, such as "Paused at 6:39:52 PM". */
  when: string | null;
  select: React.ReactNode;
  /** Absent once the session has ended. */
  pause: { label: string; onPress: () => void } | null;
  /** A link above the title, such as Session review's way back to Sessions. */
  back?: React.ReactNode;
  /** The "?" for the run state. Its page names the entry, because Live and Session review differ. */
  stateHelp?: React.ReactNode;
  /** The "?" for the time line, shown only while the time line is. */
  whenHelp?: React.ReactNode;
}

export function LiveHeader({
  state,
  title,
  titleMuted,
  sub,
  when,
  select,
  pause,
  back,
  stateHelp,
  whenHelp,
}: LiveHeaderProps) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const held = document.activeElement;
    if (held === null || held === document.body) heading.current?.focus();
  }, []);
  return (
    <header className="live-head">
      <div className="live-title">
        {back}
        <div className="live-state">
          {state !== null && <RunStateGlyph state={state.kind}>{state.word}</RunStateGlyph>}
          {state !== null && stateHelp}
          <h1
            ref={heading}
            tabIndex={-1}
            className={titleMuted === true ? "live-h1 muted" : "live-h1"}
          >
            {title}
          </h1>
        </div>
        {sub !== null && <p className="live-sub">{sub}</p>}
      </div>
      <div className="live-controls">
        {select}
        {when !== null && (
          <span className="live-when">
            {when}
            {whenHelp}
          </span>
        )}
        {pause !== null && <Button onPress={pause.onPress}>{pause.label}</Button>}
      </div>
    </header>
  );
}
