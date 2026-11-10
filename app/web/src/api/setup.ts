/*
 * The Setup reads: the map, one part and the problems feed. Each is a TanStack query keyed by
 * project (the part also by its name), so an answer that arrives late for an older project lands
 * on its own key and never on the new one.
 *
 * Every read refetches every 10 seconds while the tab is visible and not at all while it is
 * hidden, and a tab coming back refetches at once. Each sends the last answer's etag. A reply of
 * `unchanged` keeps the last full answer and takes only the new server_time. A refetch that fails
 * keeps the last good answer and says so (`failed`). An error is never an empty answer: `error`
 * and `empty` are separate, and `empty` is true only for a good answer that holds nothing.
 *
 * The To fix count in the shell comes from /api/app (`to_fix`), read by `toFixNav`. When the
 * problems etag moves, `useProblems` refetches the app answer, so the nav and the To fix page
 * agree (need 23).
 *
 * The page owns every word and every state.
 */
import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { QueryKey } from "@tanstack/react-query";
import { useApi } from "@/api/client";
import type {
  AppInfo,
  ProblemList,
  ProblemRow,
  SetupItem,
  SetupMap,
  SetupPart,
  SetupPartAnswer,
  Unchanged,
} from "@/api/types";

export const SETUP_POLL_MS = 10_000;

/** The fields every full Setup answer carries, which the hooks read. */
interface SetupAnswer {
  unchanged: false;
  server_time: string;
  etag: string;
  as_of: string | null;
}

/** One stored answer: the last full body, and when the latest reply (full or short) said it was. */
interface Stored<T> {
  answer: T;
  /** `server_time` of the latest reply, epoch milliseconds. */
  serverMs: number;
  /** The local time the latest reply arrived, epoch milliseconds. */
  receivedAt: number;
}

/** What a Setup page reads from one query. */
export interface SetupCard<T> {
  /** The last good full answer. Undefined until the first one. */
  answer: T | undefined;
  /** No answer yet and no error, so the page shows bones. */
  loading: boolean;
  /** The latest fetch failed. `answer` may still hold the last good one. */
  error: Error | null;
  /** The latest refetch failed but an older good answer is still shown. */
  failed: boolean;
  /** A good answer arrived and it holds nothing. Never true while `error` is set with no answer. */
  empty: boolean;
  /** `as_of` of the last good answer, epoch ms, or null. */
  asOf: number | null;
  /** `server_time` of the last good reply, epoch ms, or null before the first. */
  serverMs: number | null;
  /** When the last good reply arrived on this device, epoch ms, or null before the first. */
  receivedAt: number | null;
  /** Fetches again at once, for a Try again button. */
  retry: () => void;
}

function toCard<T extends SetupAnswer>(
  stored: Stored<T> | undefined,
  error: Error | null,
  retry: () => void,
  isEmpty: (answer: T) => boolean,
): SetupCard<T> {
  const answer = stored?.answer;
  return {
    answer,
    loading: stored === undefined && error === null,
    error,
    failed: error !== null && stored !== undefined,
    empty: answer !== undefined && isEmpty(answer),
    asOf: answer?.as_of != null ? Date.parse(answer.as_of) : null,
    serverMs: stored?.serverMs ?? null,
    receivedAt: stored?.receivedAt ?? null,
    retry,
  };
}

/**
 * Turns a reply into the stored answer. A short reply keeps the last full answer. A short reply
 * with nothing stored is a server that answered an etag we never sent, so it asks once more with
 * no etag.
 */
async function resolveReply<T extends SetupAnswer>(
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
  refetchInterval: SETUP_POLL_MS,
  refetchIntervalInBackground: false,
  refetchOnWindowFocus: "always",
  refetchOnReconnect: false,
  retry: false,
  gcTime: 0,
} as const;

function useSetupQuery<T extends SetupAnswer>(
  key: QueryKey,
  ask: (etag: string | null, signal: AbortSignal) => Promise<T | Unchanged>,
  isEmpty: (answer: T) => boolean,
): SetupCard<T> {
  const client = useQueryClient();
  const query = useQuery({
    ...POLL,
    queryKey: key,
    queryFn: ({ signal }) =>
      resolveReply(client.getQueryData<Stored<T>>(key), (etag) => ask(etag, signal)),
  });
  return toCard(
    query.data,
    query.error,
    () => {
      void query.refetch();
    },
    isEmpty,
  );
}

/** The map: ten part rows, each with its statuses, summary and per-scope cells. */
export function useSetupMap(project: string): SetupCard<SetupMap> {
  const api = useApi();
  return useSetupQuery<SetupMap>(
    ["setup", "map", project],
    (etag, signal) => api.getSetup(project, etag, signal),
    (answer) => answer.parts.length === 0,
  );
}

/** One part's items. Empty is a good answer with no items, whatever `empty_reason` says. */
export function useSetupPart(project: string, part: SetupPart): SetupCard<SetupPartAnswer> {
  const api = useApi();
  return useSetupQuery<SetupPartAnswer>(
    ["setup", "part", project, part],
    (etag, signal) => api.getSetupPart(project, part, etag, signal),
    (answer) => answer.items.length === 0,
  );
}

/**
 * The problems feed, which the To fix page and the inspectors read. When its etag moves while
 * the app answer still carries another one, the app answer refetches at once, so the nav count
 * follows the page (need 23).
 */
export function useProblems(project: string): SetupCard<ProblemList> {
  const api = useApi();
  const client = useQueryClient();
  const card = useSetupQuery<ProblemList>(
    ["setup", "problems", project],
    (etag, signal) => api.getProblems(project, etag, signal),
    (answer) => answer.rows.length === 0,
  );
  const etag = card.answer?.etag;
  useEffect(() => {
    if (etag === undefined) return;
    const app = client.getQueryData<AppInfo>(["app", project]);
    if (app === undefined) return;
    if (app.to_fix?.etag !== etag) void client.invalidateQueries({ queryKey: ["app", project] });
  }, [client, project, etag]);
  return card;
}

/** The shell's To fix count. `count` is set only when the state is `ok`. */
export interface ToFixNav {
  /** `ok` has a count. `unchecked` is before the first problems pass. `failed` could not run. */
  state: "ok" | "unchecked" | "failed";
  count: number | null;
  /** The problems etag the count was built from, or null. */
  etag: string | null;
}

/**
 * Reads the To fix count from an /api/app answer. Without `to_fix` (an older server) it falls back
 * to `to_fix_count`, and a null there means the count is not known yet. Before the first app
 * answer it is `unchecked`, so the nav shows no number.
 */
export function toFixNav(app: AppInfo | undefined): ToFixNav {
  if (app === undefined) return { state: "unchecked", count: null, etag: null };
  const toFix = app.to_fix;
  if (toFix === undefined) {
    return app.to_fix_count === null
      ? { state: "unchecked", count: null, etag: null }
      : { state: "ok", count: app.to_fix_count, etag: null };
  }
  if (toFix.state === "ok") {
    return { state: "ok", count: toFix.count ?? 0, etag: toFix.etag };
  }
  return { state: toFix.state, count: null, etag: toFix.etag };
}

/** Problem rows that name one item, for an inspector's own list. */
export function problemsFor(
  rows: readonly ProblemRow[],
  item: Pick<SetupItem, "id">,
): ProblemRow[] {
  return rows.filter((row) => row.item_id === item.id);
}
