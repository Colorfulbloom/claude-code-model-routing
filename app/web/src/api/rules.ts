/*
 * The rules reference read: one TanStack query keyed ["rules"], because the answer is the same for
 * every project. It sends the last answer's etag. A reply of `unchanged` keeps the last full
 * answer and takes only the new server_time. A refetch that fails keeps the last good answer and
 * says so (`failed`). An error is never an empty answer: `error` and `empty` are separate, and
 * `empty` is true only for a good answer that holds no rules.
 *
 * It refetches every 60 seconds while the tab is visible and not at all while it is hidden, and a
 * tab coming back refetches at once. The rules change only when the server's rules file or the
 * installed Claude Code version does (the `due` marks), so a slow poll is enough. The answer stays
 * cached for the default five minutes after the page unmounts, so coming back to the page shows it
 * at once and asks again with its etag.
 *
 * The page owns every word and every state.
 */
import { useQuery } from "@tanstack/react-query";
import { useApi } from "@/api/client";
import type { RulesAnswer, RulesUnchanged } from "@/api/types";

export const RULES_POLL_MS = 60_000;

/** The query key, for a test or an invalidate. */
export const RULES_KEY = ["rules"] as const;

/** One stored answer: the last full body, and when the latest reply (full or short) said it was. */
interface Stored {
  answer: RulesAnswer;
  /** `server_time` of the latest reply, epoch milliseconds. */
  serverMs: number;
  /** The local time the latest reply arrived, epoch milliseconds. */
  receivedAt: number;
}

/** What the rules page reads from the query. */
export interface RulesCard {
  /** The last good full answer. Undefined until the first one. */
  answer: RulesAnswer | undefined;
  /** No answer yet and no error, so the page shows bones. */
  loading: boolean;
  /** The latest fetch failed. `answer` may still hold the last good one. */
  error: Error | null;
  /** The latest refetch failed but an older good answer is still shown. */
  failed: boolean;
  /** A good answer arrived and it holds no rules. Never true while `error` is set with no answer. */
  empty: boolean;
  /** `server_time` of the last good reply, epoch ms, or null before the first. */
  serverMs: number | null;
  /** When the last good reply arrived on this device, epoch ms, or null before the first. */
  receivedAt: number | null;
  /** Fetches again at once, for a Try again button. */
  retry: () => void;
}

/**
 * Turns a reply into the stored answer. A short reply keeps the last full answer. A short reply
 * with nothing stored is a server that answered an etag we never sent, so it asks once more with
 * no etag. A second short reply with still nothing to keep is an error, not an empty answer.
 */
async function resolveReply(
  prev: Stored | undefined,
  ask: (etag: string | null) => Promise<RulesAnswer | RulesUnchanged>,
): Promise<Stored> {
  let reply = await ask(prev?.answer.etag ?? null);
  if (reply.unchanged && prev === undefined) reply = await ask(null);
  const receivedAt = Date.now();
  const serverMs = Date.parse(reply.server_time);
  if (!reply.unchanged) return { answer: reply, serverMs, receivedAt };
  if (prev === undefined) throw new Error("The server sent a short answer with nothing to keep");
  return { answer: prev.answer, serverMs, receivedAt };
}

/** The rules reference, with its etag, its poll and its error state. */
export function useRules(): RulesCard {
  const api = useApi();
  const query = useQuery({
    queryKey: RULES_KEY,
    queryFn: ({ signal, client }) =>
      resolveReply(client.getQueryData<Stored>(RULES_KEY), (etag) => api.getRules(etag, signal)),
    refetchInterval: RULES_POLL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: "always",
    refetchOnReconnect: false,
    retry: false,
  });
  const stored = query.data;
  const error = query.error;
  return {
    answer: stored?.answer,
    loading: stored === undefined && error === null,
    error,
    failed: error !== null && stored !== undefined,
    empty: stored?.answer.rules.length === 0,
    serverMs: stored?.serverMs ?? null,
    receivedAt: stored?.receivedAt ?? null,
    retry: () => {
      void query.refetch();
    },
  };
}
