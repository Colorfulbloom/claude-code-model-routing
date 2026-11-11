/*
 * The Glossary, #/reference/glossary (direction A, picked on November 10). One column. The three
 * shared lists come first, status words, scopes and confidence words, then the terms from A to Z.
 * Jump to chips move to a section. The page has no API call, so it has no loading or error state.
 *
 * Routes. #/reference/glossary and #/reference/glossary/<id>, where the id is a glossary.ts term or
 * a list item such as status-in_effect, scope-managed or confidence-tested. A route with an id marks
 * that entry (the chosen fill and a 3 px start bar), scrolls it into view and focuses it. A stale id
 * says so and links to the whole Glossary. The id stays shown when ?q= would hide it.
 *
 * The return. A link from a help popover carries the route it came from and the help id in its
 * query. The header then says "Back to {page}", and following it goes back and focuses that "?"
 * (components/HelpEntry/origin.ts). Without a valid origin there is no Back link.
 */
import { useEffect, useRef } from "react";
import { Link } from "react-aria-components";
import { Navigate, useLocation } from "react-router";
import { parentPageName, parseRoute } from "@/app/routes";
import { Badge } from "@/components/Badge/Badge";
import { setReturnFocus } from "@/components/HelpEntry/origin";
import { EmptyState } from "@/components/EmptyState/EmptyState";
import { PageHeader } from "@/components/PageHeader/PageHeader";
import { highlight } from "@/components/SearchField/match";
import { SearchField } from "@/components/SearchField/SearchField";
import { StatusChip } from "@/components/StatusChip/StatusChip";
import { Well } from "@/components/Well/Well";
import { t, tn } from "@/strings/t";
import { GoneCard } from "./ReferenceStates";
import {
  entryMatches,
  glossarySections,
  resolveTarget,
  termName,
  type GlossaryEntry,
  type GlossarySection,
} from "./glossary-view";
import { DECIDES_PATH, glossaryLink, readOrigin } from "./reference-routes";
import type { Origin } from "./reference-routes";
import { useFilters } from "./useFilters";
import "@/components/Button/Button.css";
import "@/components/Card/Card.css";
import "./Reference.css";

export function GlossaryPage() {
  const { pathname } = useLocation();
  const parsed = parseRoute(pathname);
  if (parsed?.page !== "glossary") return <Navigate to="/" replace />;
  return <GlossaryView id={parsed.id} />;
}

/** The origin of a help link, when its route is a page a person can go back to. */
function validOrigin(
  origin: Origin | null,
): { href: string; page: string; help: string | null } | null {
  if (origin === null) return null;
  const parsed = parseRoute(origin.from);
  if (parsed === null) return null;
  if (parsed.page === "decides" || parsed.page === "glossary" || parsed.page === "picker")
    return null;
  return { href: `#${origin.from}`, page: parentPageName(parsed.page), help: origin.help };
}

function EntryName({ entry, query }: { entry: GlossaryEntry; query: string }) {
  const name = highlight(entry.name, query);
  if (entry.kind === "status" && entry.status !== undefined) {
    return <StatusChip status={entry.status}>{name}</StatusChip>;
  }
  if (entry.kind === "confidence") return <Badge>{name}</Badge>;
  return <>{name}</>;
}

interface RowProps {
  entry: GlossaryEntry;
  query: string;
  target: boolean;
  origin: Origin | null;
}

function Row({ entry, query, target, origin }: RowProps) {
  return (
    <div className={target ? "ref-term ref-term-on" : "ref-term"}>
      <dt
        data-term-id={entry.id}
        {...(target ? { tabIndex: -1, "aria-current": "true" as const } : {})}
      >
        <EntryName entry={entry} query={query} />
      </dt>
      <dd>
        {highlight(entry.means, query)}
        {entry.see.length > 0 && (
          <span className="ref-see">
            <span className="ref-see-label">{t("gl_see")}</span>
            {entry.see.map((other, index) => (
              <span key={other}>
                {index > 0 && ", "}
                <Link href={glossaryLink(other, { origin })}>{termName(other)}</Link>
              </span>
            ))}
          </span>
        )}
      </dd>
    </div>
  );
}

function countWords(shown: number, total: number, narrowed: boolean) {
  if (!narrowed) return { text: tn("gl_count", total), announce: tn("gl_count_ann", total) };
  return {
    text: t("gl_count_of", { n: shown, total }),
    announce: shown === 0 ? t("gl_count_ann_none") : t("gl_count_ann_of", { n: shown, total }),
  };
}

function GlossaryView({ id }: { id: string | undefined }) {
  const { filters, params, setQ } = useFilters();
  const root = useRef<HTMLDivElement>(null);
  const q = filters.q;
  const narrowed = q.trim() !== "";
  const sections = glossarySections();
  const target = id === undefined ? null : resolveTarget(id, sections);
  const origin = readOrigin(params);
  const back = validOrigin(origin);

  const total = sections.reduce((sum, section) => sum + section.entries.length, 0);
  const shown = sections.map((section) => ({
    section,
    // An entry the route names stays, even when the query would hide it.
    entries: section.entries.filter(
      (entry) => entryMatches(entry, q) || (target !== null && target.entry === entry.id),
    ),
  }));
  const count = shown.reduce((sum, item) => sum + item.entries.length, 0);
  // A target section stays when only its heading is named.
  const visible = shown.filter(
    (item) => item.entries.length > 0 || (target !== null && target.section === item.section.id),
  );

  // Focus follows the route's target. A plain load keeps the h1, which the route harness focuses.
  const targetSection = target?.section ?? null;
  const targetEntry = target?.entry ?? null;
  useEffect(() => {
    if (targetSection === null) return;
    queueMicrotask(() => {
      const el =
        targetEntry === null
          ? root.current?.querySelector<HTMLElement>(`[data-section-id="${targetSection}"]`)
          : Array.from(root.current?.querySelectorAll<HTMLElement>("[data-term-id]") ?? []).find(
              (node) => node.dataset.termId === targetEntry,
            );
      el?.focus();
    });
  }, [id, targetSection, targetEntry]);

  const jump = (section: GlossarySection): void => {
    const heading = root.current?.querySelector<HTMLElement>(`[data-section-id="${section.id}"]`);
    heading?.focus();
    heading?.closest("section")?.scrollIntoView({ block: "start" });
  };

  const backLink =
    back === null ? undefined : (
      <Link
        className="button button-quiet ref-back"
        href={back.href}
        onPressStart={() => {
          setReturnFocus(back.help, back.href);
        }}
      >
        <span aria-hidden="true">{"←"}</span> {t("sp_back", { part: back.page })}
      </Link>
    );

  let body: React.ReactNode;
  if (id !== undefined && target === null) {
    body = (
      <GoneCard
        title={t("gl_gone_h", { id })}
        link={{
          label: t("sp_back", { part: t("nav_glossary") }),
          href: glossaryLink(undefined, { origin }),
        }}
      />
    );
  } else if (count === 0) {
    body = (
      <EmptyState
        variant="page"
        mark="neutral"
        title={t("gl_none_h", { query: q.trim() })}
        action={{
          label: t("sf_clear"),
          onPress: () => {
            setQ("");
          },
        }}
        secondary={{
          label: t("gl_none_rules", { query: q.trim() }),
          href: `#${DECIDES_PATH}?q=${encodeURIComponent(q.trim())}`,
        }}
      >
        {t("gl_none_b")}
      </EmptyState>
    );
  } else {
    body = (
      <div className="ref-stack">
        {visible.map(({ section, entries }) => (
          <section
            key={section.id}
            className={
              target !== null && target.entry === null && target.section === section.id
                ? "card ref-section ref-section-on"
                : "card ref-section"
            }
            aria-labelledby={`gl-${section.id}`}
          >
            <header className="card-header">
              <h2
                className="card-title"
                id={`gl-${section.id}`}
                data-section-id={section.id}
                tabIndex={-1}
              >
                {section.title}
              </h2>
              <span className="card-count num">{entries.length}</span>
              <span className="card-question">{section.question}</span>
            </header>
            <div className="card-body">
              <Well variant="list">
                <dl className="ref-gl">
                  {entries.map((entry) => (
                    <Row
                      key={entry.id}
                      entry={entry}
                      query={q}
                      target={target !== null && target.entry === entry.id}
                      origin={origin}
                    />
                  ))}
                </dl>
              </Well>
            </div>
          </section>
        ))}
      </div>
    );
  }

  const words = countWords(count, total, narrowed);
  return (
    <div className="ref-page" ref={root}>
      <PageHeader
        title={t("nav_glossary")}
        sub={t("gl_sub")}
        {...(backLink === undefined ? {} : { controls: backLink })}
      />
      <div className="ref-tools">
        <SearchField
          className="ref-search"
          label={t("gl_search_label")}
          value={q}
          onChange={setQ}
          clearLabel={t("sf_clear")}
          placeholder={t("gl_search_ph")}
          count={words.text}
          announce={words.announce}
        />
      </div>
      {!narrowed && (
        <p className="ref-jump">
          <span className="muted">{t("sp_jump")}</span>
          {sections.map((section) => (
            <button
              key={section.id}
              type="button"
              className="ref-jump-chip"
              onClick={() => {
                jump(section);
              }}
            >
              {section.title} <span className="num">{section.entries.length}</span>
            </button>
          ))}
        </p>
      )}
      {body}
    </div>
  );
}
