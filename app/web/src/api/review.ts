/*
 * The Review reads: summary, cost chart, sessions, agents and models. Each is a TanStack query
 * keyed by project and range (the chart also by its end date, the sessions by their cursor), so an
 * answer that arrives late for an older range lands on its own key and never on the new one. No
 * query keeps the previous range's data as a placeholder. After a range change a card has no
 * answer until its own arrives, so the page shows bones, never old numbers under a new label.
 *
 * Every read refetches every 60 seconds and when the window regains focus, and sends the last
 * answer's etag. A reply of `unchanged` keeps the last full answer and takes only the new
 * server_time. A refetch that fails keeps the last good answer and says so (`failed`), with the
 * time of that answer (`updatedAt`) for the card's "Updated {time}".
 *
 * The page owns every word and every state. Per-card errors from `errors[]` come back as helpers
 * (`cardError`), and `summary.model_check` is null when its card failed.
 */
import { useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import type { InfiniteData, QueryKey } from "@tanstack/react-query";
import { useApi } from "@/api/client";
import type {
  AgentList,
  CardError,
  CostChart,
  ModelCheck,
  ModelList,
  ReviewRange,
  SessionDay,
  SessionList,
  Summary,
  Unchanged,
} from "@/api/types";

export const REVIEW_POLL_MS = 60_000;

/** The fields every full Review answer carries, which the hooks read. */
interface ReviewAnswer {
  unchanged: false;
  server_time: string;
  etag: string;
  as_of: string | null;
  errors: CardError[];
}

/** One stored answer: the last full body, and when the latest reply (full or short) said it was. */
interface Stored<T> {
  answer: T;
  /** `server_time` of the latest reply, epoch milliseconds. */
  serverMs: number;
  /** The local time the latest reply arrived, epoch milliseconds. */
  receivedAt: number;
}

/** What a card reads from a Review query. */
export interface ReviewCard<T> {
  /** The last good full answer. Undefined until the first one, and after a range change. */
  answer: T | undefined;
  /** No answer yet and no error, so the card shows bones. */
  loading: boolean;
  /** The latest fetch failed. `answer` may still hold the last good one. */
  error: Error | null;
  /** The latest refetch failed but an older good answer is still shown. */
  failed: boolean;
  /** `as_of` of the last good answer (the last finished ingest pass), epoch ms, or null. */
  asOf: number | null;
  /** `server_time` of the last good reply, epoch ms, or null before the first. */
  serverMs: number | null;
  /** When the last good reply arrived on this device, epoch ms, or null before the first. */
  receivedAt: number | null;
  /** The time for "Updated {time}": the answer's own `as_of`, else the last good server time. */
  updatedAt: number | null;
  /** The card errors the last good answer carries. */
  errors: CardError[];
  /** Fetches again at once, for a Try again button. */
  retry: () => void;
}

const NO_ERRORS: CardError[] = [];

function toCard<T extends ReviewAnswer>(
  stored: Stored<T> | undefined,
  error: Error | null,
  retry: () => void,
): ReviewCard<T> {
  const answer = stored?.answer;
  const asOf = answer?.as_of != null ? Date.parse(answer.as_of) : null;
  const serverMs = stored?.serverMs ?? null;
  return {
    answer,
    loading: stored === undefined && error === null,
    error,
    failed: error !== null && stored !== undefined,
    asOf,
    serverMs,
    receivedAt: stored?.receivedAt ?? null,
    updatedAt: asOf ?? serverMs,
    errors: answer?.errors ?? NO_ERRORS,
    retry,
  };
}

/** The error a card raised for one of its parts, or null. */
export function cardError(errors: readonly CardError[], card: CardError["card"]): CardError | null {
  return errors.find((entry) => entry.card === card) ?? null;
}

/**
 * Turns a reply into the stored answer. A short reply keeps the last full answer. A short reply
 * with nothing stored is a server that answered an etag we never sent, so `again` asks once more
 * with no etag.
 */
async function resolveReply<T extends ReviewAnswer>(
  prev: Stored<T> | undefined,
  ask: (etag: string | null) => Promise<T | Unchanged>,
): Promise<Stored<T>> {
  let reply = await ask(prev?.answer.etag ?? null);
  if (reply.unchanged && prev === undefined) reply = await ask(null);
  const receivedAt = Date.now();
  const serverMs = Date.parse(reply.server_time);
  if (reply.unchanged && prev !== undefined) return { answer: prev.answer, serverMs, receivedAt };
  return { answer: reply as T, serverMs, receivedAt };
}

const POLL = {
  refetchInterval: REVIEW_POLL_MS,
  refetchIntervalInBackground: false,
  refetchOnWindowFocus: "always",
  refetchOnReconnect: false,
  retry: false,
  gcTime: 0,
} as const;

function useReviewQuery<T extends ReviewAnswer>(
  key: QueryKey,
  ask: (etag: string | null, signal: AbortSignal) => Promise<T | Unchanged>,
): ReviewCard<T> {
  const client = useQueryClient();
  const query = useQuery({
    ...POLL,
    queryKey: key,
    queryFn: ({ signal }) =>
      resolveReply(client.getQueryData<Stored<T>>(key), (etag) => ask(etag, signal)),
  });
  return toCard(query.data, query.error, () => {
    void query.refetch();
  });
}

/** The Summary page: tiles, money, model check and the four most expensive sessions. */
export interface SummaryCard extends ReviewCard<Summary> {
  /** The model check, or null while loading and when its card failed. */
  modelCheck: ModelCheck | null;
  /** Why the model check is null, when its card failed. */
  modelCheckError: CardError | null;
}

export function useSummary(project: string, range: ReviewRange): SummaryCard {
  const api = useApi();
  const card = useReviewQuery<Summary>(["review", "summary", project, range], (etag, signal) =>
    api.getSummary(project, range, etag, signal),
  );
  return {
    ...card,
    modelCheck: card.answer?.model_check ?? null,
    modelCheckError: cardError(card.errors, "model_check"),
  };
}

/** The Agents page. A `set` is null on a row when the setup read failed, with an agent_setup error. */
export interface AgentsCard extends ReviewCard<AgentList> {
  setupError: CardError | null;
}

export function useAgents(project: string, range: ReviewRange): AgentsCard {
  const api = useApi();
  const card = useReviewQuery<AgentList>(["review", "agents", project, range], (etag, signal) =>
    api.getAgents(project, range, etag, signal),
  );
  return { ...card, setupError: cardError(card.errors, "agent_setup") };
}

export function useModels(project: string, range: ReviewRange): ReviewCard<ModelList> {
  const api = useApi();
  return useReviewQuery<ModelList>(["review", "models", project, range], (etag, signal) =>
    api.getModels(project, range, etag, signal),
  );
}

const DAY_MS = 86_400_000;

/** The local date of an instant in a zone, as YYYY-MM-DD. */
export function localDate(instant: number | string, tz: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(instant));
  const pick = (type: string): string => parts.find((part) => part.type === type)?.value ?? "";
  return `${pick("year")}-${pick("month")}-${pick("day")}`;
}

/** The day before a local date, as YYYY-MM-DD. Calendar arithmetic only, so no zone is involved. */
export function dayBefore(date: string): string {
  return new Date(Date.parse(`${date}T00:00:00Z`) - DAY_MS).toISOString().slice(0, 10);
}

export interface CostChartCard extends ReviewCard<CostChart> {
  /** Moves one window back. Does nothing at the oldest end, or before the first answer. */
  earlier: () => void;
  /** Moves one window forward, to the window it came from. Does nothing on the newest page. */
  later: () => void;
  /** Back to the newest window. */
  newest: () => void;
  /** The chart's end date as asked, or null on the newest window. Not in the URL. */
  end: string | null;
  /** The pager moves are open: false at an end or before the first answer. */
  canEarlier: boolean;
  canLater: boolean;
}

/**
 * The cost chart and its pager. The pager's position is state, not URL, and it resets to the
 * newest window when the project or range changes. Earlier and Later never touch the tiles
 * (those come from the Summary query). While a page loads the card has no answer, so the chart
 * shows bones.
 */
export function useCostChart(project: string, range: ReviewRange): CostChartCard {
  const api = useApi();
  const scope = `${project}\u0000${range}`;
  // Ends already visited, newest first to last. Later pops one. The scope tag resets it.
  const [trail, setTrail] = useState<{ scope: string; ends: string[] }>({ scope, ends: [] });
  const ends = trail.scope === scope ? trail.ends : [];
  const end = ends.at(-1) ?? null;
  const card = useReviewQuery<CostChart>(
    ["review", "cost-chart", project, range, end],
    (etag, signal) => api.getCostChart(project, range, end, etag, signal),
  );
  const chart = card.answer?.chart;
  const tz = card.answer?.window.tz;
  const canEarlier = chart?.has_earlier === true && tz !== undefined;
  const canLater = chart?.has_later === true && ends.length > 0;
  return {
    ...card,
    end,
    canEarlier,
    canLater,
    earlier() {
      if (chart === undefined || tz === undefined || !chart.has_earlier) return;
      // The window before this one ends on the day before this one starts.
      const previous = dayBefore(localDate(chart.start, tz));
      setTrail({ scope, ends: [...ends, previous] });
    },
    later() {
      if (ends.length === 0) return;
      setTrail({ scope, ends: ends.slice(0, -1) });
    },
    newest() {
      setTrail({ scope, ends: [] });
    },
  };
}

/** One loaded page of the sessions list, with the cursor that asked for it. */
interface SessionsPage extends Stored<SessionList> {
  cursor: string | null;
}

export interface SessionsCard {
  /** The first page's answer: window, prices, errors, as_of. Undefined until it arrives. */
  head: SessionList | undefined;
  /** Loaded sessions grouped by local day, newest first. A row is never repeated. */
  days: SessionDay[];
  /** Sessions in the range, from the first page. */
  count: number;
  /** Sessions loaded so far. */
  loaded: number;
  /** Sessions still to load, never below zero. */
  remaining: number;
  hasMore: boolean;
  /** Loads the next page. Resolves to the id of its first new row, or null when it had none. */
  loadMore: () => Promise<string | null>;
  loadingMore: boolean;
  /** The next page failed to load. The loaded rows stay. */
  loadMoreError: Error | null;
  /** The first row that the latest load added, for the page to focus. Null until a load. */
  firstNewId: string | null;
  loading: boolean;
  error: Error | null;
  failed: boolean;
  asOf: number | null;
  serverMs: number | null;
  receivedAt: number | null;
  updatedAt: number | null;
  retry: () => void;
}

/**
 * Merges pages into days. Rows are keyed by session id, so one never repeats, and a day that
 * runs across a page break sits under one header.
 */
export function mergeSessionPages(pages: readonly SessionList[]): SessionDay[] {
  const seen = new Set<string>();
  const merged: SessionDay[] = [];
  const byDay = new Map<string, SessionDay>();
  for (const page of pages) {
    for (const day of page.days) {
      for (const session of day.sessions) {
        if (seen.has(session.id)) continue;
        seen.add(session.id);
        let target = byDay.get(day.day);
        if (target === undefined) {
          target = { day: day.day, sessions: [] };
          byDay.set(day.day, target);
          merged.push(target);
        }
        target.sessions.push(session);
      }
    }
  }
  return merged;
}

function idsOf(days: readonly SessionDay[]): Set<string> {
  return new Set(days.flatMap((day) => day.sessions.map((session) => session.id)));
}

/**
 * The sessions list, 50 a page with the server's cursor. The 60 second refetch walks the loaded
 * pages again from the top, and the server anchors each cursor on a row's sort key, so loaded
 * rows never move or repeat. New sessions arrive only at the top.
 */
export function useSessions(project: string, range: ReviewRange): SessionsCard {
  const api = useApi();
  const client = useQueryClient();
  const key: QueryKey = ["review", "sessions", project, range];
  const scope = `${project}\u0000${range}`;
  const [added, setAdded] = useState<{ scope: string; id: string | null }>({ scope, id: null });

  const query = useInfiniteQuery({
    ...POLL,
    queryKey: key,
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam, signal }): Promise<SessionsPage> => {
      const before = client.getQueryData<InfiniteData<SessionsPage, string | null>>(key);
      const prev = before?.pages.find((page) => page.cursor === pageParam);
      const stored = await resolveReply<SessionList>(prev, (etag) =>
        api.getReviewSessions(project, range, pageParam, etag, signal),
      );
      return { ...stored, cursor: pageParam };
    },
    getNextPageParam: (last) => last.answer.next,
  });

  const pages = query.data?.pages;
  const days = mergeSessionPages(pages?.map((page) => page.answer) ?? []);
  const first = pages?.[0];
  const last = pages?.at(-1);
  const loaded = days.reduce((sum, day) => sum + day.sessions.length, 0);
  const count = first?.answer.count ?? 0;
  const asOf = first?.answer.as_of != null ? Date.parse(first.answer.as_of) : null;
  const serverMs = first?.serverMs ?? null;
  const { fetchNextPage } = query;
  // A failed "Show more" is its own error. It leaves the loaded list as it was.
  const listError = query.isFetchNextPageError ? null : query.error;

  return {
    head: first?.answer,
    days,
    count,
    loaded,
    remaining: Math.max(0, count - loaded),
    hasMore: last?.answer.next != null,
    async loadMore() {
      const known = idsOf(days);
      const result = await fetchNextPage();
      const appended = result.data?.pages.at(-1)?.answer.days ?? [];
      const firstNew =
        appended.flatMap((day) => day.sessions).find((session) => !known.has(session.id))?.id ??
        null;
      if (result.isError) return null;
      setAdded({ scope, id: firstNew });
      return firstNew;
    },
    loadingMore: query.isFetchingNextPage,
    loadMoreError: query.isFetchNextPageError ? query.error : null,
    firstNewId: added.scope === scope ? added.id : null,
    loading: pages === undefined && query.error === null,
    error: listError,
    failed: listError !== null && pages !== undefined,
    asOf,
    serverMs,
    receivedAt: first?.receivedAt ?? null,
    updatedAt: asOf ?? serverMs,
    retry: () => {
      void query.refetch();
    },
  };
}
