import { useState } from "react";
import { Button, Disclosure, DisclosurePanel } from "react-aria-components";
import type { RuleQuote } from "@/api/types";
import { highlight } from "@/components/SearchField/match";
import { tn, t } from "@/strings/t";

export interface DocsDisclosureProps {
  quotes: readonly RuleQuote[];
  /** The search text, so a match in a quote is marked. */
  query: string;
  /** Opens the line for a reason the page knows, such as a match found only in the docs. */
  autoOpen: boolean;
}

/** A docs address without its scheme, as it reads on screen. */
function shown(url: string): string {
  return url.replace(/^https?:\/\//, "");
}

/**
 * The docs lines a rule quotes, behind one Disclosure. The button says how many lines it holds, and
 * each line comes with its link, which opens in a new tab and says so to a screen reader. The line
 * is verbatim docs text, drawn as text and marked by splitting, never as HTML. The page opens it
 * when the match was only in the docs, or when the rule is the route's target. A person's own press
 * wins after that.
 */
export function DocsDisclosure({ quotes, query, autoOpen }: DocsDisclosureProps) {
  const [chosen, setChosen] = useState<boolean | null>(null);
  const open = chosen ?? autoOpen;
  return (
    <Disclosure
      className="ref-docs"
      isExpanded={open}
      onExpandedChange={(next) => {
        setChosen(next);
      }}
    >
      <Button slot="trigger" className="ref-docs-trigger">
        <span className="ref-docs-chevron" aria-hidden="true" />
        {tn("dc_docs", quotes.length)}
      </Button>
      <DisclosurePanel className="ref-docs-panel">
        <ul className="well ref-quotes">
          {quotes.map((quote, index) => (
            <li key={`${quote.doc_url}#${String(index)}`}>
              <blockquote className="ref-quote">{highlight(quote.quote, query)}</blockquote>
              <a
                className="ref-doclink"
                href={quote.doc_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                <span className="mono">{shown(quote.doc_url)}</span>{" "}
                <span aria-hidden="true">{"↗"}</span>
                <span className="sr-only"> ({t("dc_new_tab")})</span>
              </a>
            </li>
          ))}
        </ul>
      </DisclosurePanel>
    </Disclosure>
  );
}
