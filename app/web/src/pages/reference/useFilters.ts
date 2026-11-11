import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import type { ConfidenceFilter, Filters } from "./rules-view";
import { readFilters } from "./reference-routes";

export interface FilterState {
  filters: Filters;
  /** The query string as the URL holds it, for links that keep the filters. */
  params: URLSearchParams;
  setQ: (value: string) => void;
  setConfidence: (value: ConfidenceFilter) => void;
  /** Drops the query and the Confidence word in one update. The due view stays. */
  clear: () => void;
  /** Leaves the due view and keeps the other filters. */
  showAll: () => void;
}

/**
 * The search, the Confidence filter and the due view, held in the URL's query with history replace.
 * The typed text is also held here, so the field answers at once and a router update never moves the
 * caret. A query that changes from outside (a link, Back) comes into the field.
 */
export function useFilters(): FilterState {
  const [params, setParams] = useSearchParams();
  const url = readFilters(params);
  const [q, setLocal] = useState(url.q);
  /** What the field holds now, so a URL that matches it needs no work. */
  const latest = useRef(url.q);
  /**
   * The values this hook has sent to the URL and not seen come back. The router applies each
   * replace after the next keystroke may already have landed, so "c" returns while the field says
   * "ca". That echo is ours and must not overwrite the field, or a fast typist loses characters.
   */
  const sent = useRef<string[]>([]);
  const expire = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => {
    const at = sent.current.indexOf(url.q);
    if (at >= 0) {
      sent.current = sent.current.slice(at + 1);
      return;
    }
    if (url.q !== latest.current) {
      latest.current = url.q;
      sent.current = [];
      setLocal(url.q);
    }
  }, [url.q]);
  useEffect(
    () => () => {
      clearTimeout(expire.current);
    },
    [],
  );

  /** Records a value the field now holds and is about to put in the URL. */
  const typed = (value: string): void => {
    latest.current = value;
    sent.current.push(value);
    setLocal(value);
    // An echo arrives within a frame or two. Dropping the record later stops a stale one from
    // swallowing a real change of the query from outside, such as a link to the same text.
    clearTimeout(expire.current);
    expire.current = setTimeout(() => {
      sent.current = [];
    }, 1000);
  };

  const update = (change: (next: URLSearchParams) => void): void => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        change(next);
        return next;
      },
      { replace: true },
    );
  };

  return {
    filters: { q, confidence: url.confidence, due: url.due },
    params,
    setQ: (value) => {
      typed(value);
      update((next) => {
        if (value === "") next.delete("q");
        else next.set("q", value);
      });
    },
    setConfidence: (value) => {
      update((next) => {
        if (value === "all") next.delete("confidence");
        else next.set("confidence", value);
      });
    },
    clear: () => {
      typed("");
      update((next) => {
        next.delete("q");
        next.delete("confidence");
      });
    },
    showAll: () => {
      update((next) => {
        next.delete("due");
      });
    },
  };
}
