/*
 * Feeds the page's one polite live region from the timeline polls. Each poll that brings a new full
 * answer is diffed against the one before (announcer.ts). The first answer after the page loads,
 * after a session switch (the page remounts this hook per session), after the tab was hidden and
 * after Resume following Pause is a baseline and says nothing. A poll that answers `unchanged`
 * brings no new answer, but it still lets a held line out once its row's minute has ended.
 */
import { useEffect, useRef } from "react";
import type { LiveFeed } from "@/api/live";
import type { Timeline } from "@/api/types";
import { postStatus } from "@/app/harness";
import { diffAnnouncements } from "@/lib/announcer";
import type { Held, Spoken } from "@/lib/announcer";

/** Joins the lines of one poll into one message. */
export const LINE_JOINER = ". ";

/** `active` is false while the tab is hidden or Pause is on. The first answer after it is a baseline. */
export function useAnnouncer(feed: LiveFeed<Timeline> | undefined, active: boolean): void {
  const previous = useRef<Timeline | null>(null);
  const spoken = useRef<Spoken>({});
  const held = useRef<Held>({});
  const baseline = useRef(true);

  useEffect(() => {
    if (!active) baseline.current = true;
  }, [active]);

  const receivedAt = feed?.receivedAt;
  useEffect(() => {
    if (feed === undefined) return;
    const answer = feed.answer;
    if (baseline.current || previous.current === null) {
      baseline.current = false;
      previous.current = answer;
      held.current = {};
      return;
    }
    // An unchanged poll diffs the answer with itself, so only held lines can come out of it.
    const result = diffAnnouncements(
      previous.current,
      answer,
      spoken.current,
      held.current,
      feed.serverMs,
    );
    previous.current = answer;
    spoken.current = result.spoken;
    held.current = result.held;
    if (result.lines.length > 0) postStatus(result.lines.join(LINE_JOINER));
    // One effect per poll: feed changes every poll, and receivedAt names that.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [receivedAt]);
}
