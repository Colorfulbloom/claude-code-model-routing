import { Link } from "react-aria-components";
import { StatusChip, type SettingStatus } from "@/components/StatusChip/StatusChip";
import { en, type StringKey } from "@/strings/en";
import { GLOSSARY, hasTerm, type GlossaryTerm } from "@/strings/glossary";
import { helpEntry, type HelpEntry as HelpEntryData, type HelpId } from "@/strings/help";
import { LISTS, type ListId } from "@/strings/lists";
import { t } from "@/strings/t";
import { cx } from "../cx";
import { glossaryHref } from "./origin";
import "./HelpEntry.css";

export const states = ["full", "list-status", "list-scopes", "no-glossary"] as const;

export interface HelpEntryProps {
  help: HelpId;
  /** What the spot shows now, by the names its entry's lines use as `ref`. Each draws beside its line. */
  values?: Readonly<Record<string, string>>;
  /** The label of the line to mark "This column". A column header passes its own. */
  line?: string;
  /**
   * The id of the list item to mark "Shown here". A status pill passes its own. An entry with no
   * list marks the line whose label equals the word, such as the run state pills.
   */
  word?: string;
  /** Runs when a glossary link is pressed, so the panel can close. */
  onNavigate?: () => void;
  /** The component sheet and tests only. Draws this entry in place of the registry's. */
  source?: HelpEntryData;
  /** The component sheet and tests only. Replaces the glossary's own check for a term. */
  termExists?: (id: string) => boolean;
}

const LIST_LABEL = {
  status: "hp_list_status",
  scopes: "hp_list_scopes",
  confidence: "hp_list_confidence",
  project_state: "hp_list_project_state",
} as const satisfies Record<ListId, StringKey>;

/** A line's meaning starts lower case in the registry, so it reads as a sentence on screen. */
function sentence(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const TERMS: Readonly<Record<string, GlossaryTerm>> = GLOSSARY;

/**
 * The body of one help entry (components.md entry 57), in a fixed order. What the spot shows, then
 * its numbers or columns as a description list with the passed value beside its line, then the
 * shared list, then how to read it, then one link per glossary term that exists. A link to a term
 * the Glossary does not have does not render, so a link never goes nowhere. The title is not here,
 * because the panel owns the heading.
 */
export function HelpEntry({
  help,
  values,
  line,
  word,
  onNavigate,
  source,
  termExists = hasTerm,
}: HelpEntryProps) {
  const entry = source ?? helpEntry(help);
  const lines = entry.lines ?? [];
  const hasValues = lines.some(
    (item) => item.ref !== undefined && values?.[item.ref] !== undefined,
  );
  const items = entry.list === undefined ? [] : LISTS[entry.list];
  const links = (entry.glossary ?? []).filter((id) => termExists(id));
  return (
    <div className="hp-entry">
      {entry.shows !== undefined && <p className="hp-shows">{entry.shows}</p>}
      {lines.length > 0 && (
        <section className="hp-sec">
          <h3 className="hp-label">{t("hp_numbers")}</h3>
          <dl className={cx("hp-dl", hasValues && "hp-has-values")}>
            {lines.map((item) => {
              const value = item.ref === undefined ? undefined : values?.[item.ref];
              const markedColumn = line === item.label;
              const markedWord = entry.list === undefined && word === item.label;
              const marked = markedColumn || markedWord;
              return (
                <div key={item.label} className={cx("hp-row", marked && "hp-marked")}>
                  <dt className="hp-name">{item.label}</dt>
                  {value !== undefined && <dd className="hp-value num">{value}</dd>}
                  <dd className="hp-means">
                    {sentence(item.means)}
                    {markedColumn && (
                      <span className="hp-this chosen-mark">{t("hp_this_column")}</span>
                    )}
                    {!markedColumn && markedWord && (
                      <span className="hp-this chosen-mark">{t("hp_this_setting")}</span>
                    )}
                  </dd>
                </div>
              );
            })}
          </dl>
        </section>
      )}
      {entry.list !== undefined && (
        <section className="hp-sec">
          <h3 className="hp-label">{t(LIST_LABEL[entry.list])}</h3>
          <dl className="hp-dl hp-list">
            {items.map((item) => {
              const marked = word === item.id;
              const label = en[item.word];
              return (
                <div key={item.id} className={cx("hp-row", marked && "hp-marked")}>
                  <dt className="hp-name">
                    {entry.list === "status" ? (
                      <StatusChip status={item.id as SettingStatus}>{label}</StatusChip>
                    ) : (
                      label
                    )}
                  </dt>
                  <dd className="hp-means">
                    {item.means !== undefined && en[item.means]}
                    {marked && <span className="hp-this chosen-mark">{t("hp_this_setting")}</span>}
                  </dd>
                </div>
              );
            })}
          </dl>
        </section>
      )}
      {entry.reading !== undefined && (
        <section className="hp-sec">
          <h3 className="hp-label">{t("hp_reading")}</h3>
          <p className="hp-reading">{entry.reading}</p>
        </section>
      )}
      {links.length > 0 && (
        <div className="hp-foot">
          {links.map((id) => (
            <Link
              key={id}
              className="hp-link"
              href={glossaryHref(id, help)}
              {...(onNavigate === undefined ? {} : { onPress: onNavigate })}
            >
              {t("hp_glossary_link", { term: TERMS[id]?.term ?? id })}
              <span aria-hidden="true">{" →"}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
