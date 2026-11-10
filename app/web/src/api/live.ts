/*
 * The Live reads: one session's timeline every second and the session list every five. Each call
 * sends the last answer's etag and keeps the last full answer when the reply is `unchanged`, so a
 * quiet poll costs a few bytes and changes nothing on screen.
 *
 * Polling is gated by `active`, which the page sets false while Pause is on or the tab is hidden.
 * Nothing refetches in the background then, and the first poll after `active` turns true goes out
 * at once. TanStack's own focus and reconnect refetches are off, because they would break Pause.
 * Three failed polls in a row (no answer, or an error that is not a refusal) move the feed to the
 * lost state and slow it to one try every 10 seconds, and any good answer clears that. An ended
 * session polls every 10 seconds too. An answered refusal such as `unknown_session` is not a
 * failure. It stops the poll, and the page shows its own state.
 */
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { QueryKey } from "@tanstack/react-query";
import { ApiError, useApi } from "@/api/client";
import type { LiveSessions, LiveSessionsUnchanged, Timeline, Unchanged } from "@/api/types";

export const TIMELINE_POLL_MS = 1_000;
export const SESSIONS_POLL_MS = 5_000;
export const REVIEW_TIMELINE_POLL_MS = 5_000;
export const SLOW_POLL_MS = 10_000;
export const FAILURES_TO_LOST = 3;

/** The last full answer, with when the latest reply (full or short) said it was and arrived. */
export interface LiveFeed<T> {
  answer: T;
  /** `server_time` of the latest reply, epoch milliseconds. */
  serverMs: number;
  /** The local time the latest reply arrived, epoch milliseconds. */
  receivedAt: number;
}

export interface FeedState<T> {
  feed: LiveFeed<T> | undefined;
  /** True until the first answer or refusal. */
  loading: boolean;
  /** An answered refusal, such as unknown_session. Null otherwise. */
  refusal: ApiError | null;
  failures: number;
  /** Three failed polls in a row. */
  lost: boolean;
  /** Polls at once, for Try now. */
  retryNow: () => void;
}

function subscribeVisibility(listener: () => void): () => void {
  document.addEventListener("visibilitychange", listener);
  return () => {
    document.removeEventListener("visibilitychange", listener);
  };
}

/** False while the tab is hidden. */
export function usePageVisible(): boolean {
  return useSyncExternalStore(
    subscribeVisibility,
    () => document.visibilityState !== "hidden",
    () => true,
  );
}

/** A failure counts unless the server answered "not there" (a 404) or the call was cancelled. */
function countsAsFailure(error: unknown): boolean {
  if (error instanceof DOMException && error.name === "AbortError") return false;
  if (error instanceof ApiError) return error.status !== 404;
  return error instanceof Error;
}

interface FeedOptions<R extends { unchanged: boolean; server_time: string; etag: string }> {
  key: QueryKey;
  /** False holds every poll. The first poll after it turns true goes out at once. */
  active: boolean;
  enabled: boolean;
  intervalMs: number;
  /** Polls this slowly once the answer says the session is over. */
  slowWhen?: (answer: Extract<R, { unchanged: false }>) => boolean;
  /** Stops polling once the answer says nothing more will change. */
  stopWhen?: (answer: Extract<R, { unchanged: false }>) => boolean;
  fetchReply: (etag: string | null, signal: AbortSignal) => Promise<R>;
}

function useFeed<R extends { unchanged: boolean; server_time: string; etag: string }>(
  options: FeedOptions<R>,
): FeedState<Extract<R, { unchanged: false }>> {
  type Full = Extract<R, { unchanged: false }>;
  const { key, active, enabled, intervalMs, slowWhen, stopWhen, fetchReply } = options;
  const client = useQueryClient();
  const keyText = JSON.stringify(key);
  const [counted, setCounted] = useState<{ key: string; failures: number }>({
    key: keyText,
    failures: 0,
  });
  const failures = counted.key === keyText ? counted.failures : 0;
  const lost = failures >= FAILURES_TO_LOST;

  function note(ok: boolean): void {
    setCounted((current) => {
      const base = current.key === keyText ? current.failures : 0;
      return { key: keyText, failures: ok ? 0 : base + 1 };
    });
  }

  const query = useQuery({
    queryKey: key,
    enabled,
    queryFn: async ({ signal }): Promise<LiveFeed<Full>> => {
      const prev = client.getQueryData<LiveFeed<Full>>(key);
      try {
        let reply = await fetchReply(prev?.answer.etag ?? null, signal);
        if (reply.unchanged && prev === undefined) reply = await fetchReply(null, signal);
        const receivedAt = Date.now();
        note(true);
        const serverMs = Date.parse(reply.server_time);
        if (reply.unchanged && prev !== undefined)
          return { answer: prev.answer, serverMs, receivedAt };
        return { answer: reply as Full, serverMs, receivedAt };
      } catch (error) {
        if (countsAsFailure(error)) note(false);
        throw error;
      }
    },
    refetchInterval: (current) => {
      if (!active) return false;
      if (current.state.error instanceof ApiError && current.state.error.status === 404) {
        return false;
      }
      const data = current.state.data;
      if (data !== undefined && stopWhen?.(data.answer) === true) return false;
      if (lost) return SLOW_POLL_MS;
      return data !== undefined && slowWhen?.(data.answer) === true ? SLOW_POLL_MS : intervalMs;
    },
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
    gcTime: 0,
  });

  // Showing the tab again, or resuming, polls at once. The first render is not a return.
  const wasActive = useRef(active);
  const { refetch } = query;
  useEffect(() => {
    if (active && !wasActive.current && enabled) void refetch();
    wasActive.current = active;
  }, [active, enabled, refetch]);

  const refusal =
    query.error instanceof ApiError && query.error.status === 404 ? query.error : null;
  return {
    feed: refusal === null ? query.data : undefined,
    loading: enabled && query.data === undefined && query.error === null,
    refusal,
    failures,
    lost,
    retryNow: () => {
      void refetch();
    },
  };
}

/** One session's timeline. `session` null holds the feed (no session chosen yet). */
export function useTimelineFeed(
  project: string,
  session: string | null,
  active: boolean,
): FeedState<Timeline> {
  const api = useApi();
  return useFeed<Timeline | Unchanged>({
    key: ["timeline", project, session],
    active,
    enabled: session !== null,
    intervalMs: TIMELINE_POLL_MS,
    slowWhen: (answer) => answer.session.state === "ended",
    fetchReply: (etag, signal) => api.getTimeline(project, session ?? "", etag, signal),
  });
}

/**
 * The timeline of a session open in Session review. Same answer and same etag rule as Live, on
 * its own query key, so Live's feed and this one never share a cache entry. It polls every 5
 * seconds while the session runs and stops for good once the answer says it ended.
 */
export function useReviewTimelineFeed(
  project: string,
  session: string | null,
  active: boolean,
): FeedState<Timeline> {
  const api = useApi();
  return useFeed<Timeline | Unchanged>({
    key: ["review-timeline", project, session],
    active,
    enabled: session !== null,
    intervalMs: REVIEW_TIMELINE_POLL_MS,
    stopWhen: (answer) => answer.session.state === "ended",
    fetchReply: (etag, signal) => api.getTimeline(project, session ?? "", etag, signal),
  });
}

/** The running sessions of every project, and this project's newest ended one. */
export function useSessionsFeed(project: string, active: boolean): FeedState<LiveSessions> {
  const api = useApi();
  return useFeed<LiveSessions | LiveSessionsUnchanged>({
    key: ["live-sessions", project],
    active,
    enabled: true,
    intervalMs: SESSIONS_POLL_MS,
    fetchReply: (etag, signal) => api.getLiveSessions(project, etag, signal),
  });
}
