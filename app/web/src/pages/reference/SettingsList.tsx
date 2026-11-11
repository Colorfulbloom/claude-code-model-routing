import { useId, type ReactNode } from "react";
import { Link } from "react-aria-components";
import { cx } from "@/components/cx";
import { highlight } from "@/components/SearchField/match";
import { Well } from "@/components/Well/Well";
import { t } from "@/strings/t";
import { decidesHref } from "./reference-routes";
import { settingName, type Filters } from "./rules-view";
import "@/components/Card/Card.css";
import "@/components/ListInspector/ListInspector.css";

export interface SettingsListRow {
  key: string;
  /** Rules that pass the filters. */
  shown: number;
  /** Every rule of the setting. */
  total: number;
}

export interface SettingsListProps {
  rows: readonly SettingsListRow[];
  /** How many settings there are in all, for the count beside the title. */
  settings: number;
  /** The setting the route names, or the one the page shows. It gets the chosen state. */
  current: string | null;
  filters: Filters;
  /** Called when a person opens a setting, so the page can move focus to its heading. */
  onOpen: (key: string) => void;
}

/**
 * Lets a setting key break after a dot, such as modelSettings. before autoCompactWindow, so a long
 * key wraps at a sensible point. A wbr adds no text, so the key reads the same.
 */
function breakAfterDots(nodes: ReactNode[]): ReactNode[] {
  return nodes.flatMap<ReactNode>((node, at) => {
    if (typeof node !== "string") return [node];
    return node.split(/(?<=\.)/).flatMap<ReactNode>((part, index) => {
      const key = `${String(at)}-${String(index)}`;
      return index === 0 ? [part] : [<wbr key={key} />, part];
    });
  });
}

/**
 * The settings list of How Claude Code decides: a nav of links, one URL per setting, with the number
 * of its rules at the end of the row. Searching narrows it to the settings with a match and says
 * "n of total" on each row and in the title. The current setting has the chosen fill, a 3 px start
 * bar and aria-current, as every list in the app does.
 */
export function SettingsList({ rows, settings, current, filters, onOpen }: SettingsListProps) {
  const headingId = useId();
  const narrowed = rows.length !== settings;
  return (
    <nav className="card item-list ref-list" aria-labelledby={headingId}>
      <header className="card-header">
        <h2 className="card-title" id={headingId}>
          {t("sf_settings")}
        </h2>
        <span className="card-count num">
          {narrowed ? t("dc_list_of", { n: rows.length, total: settings }) : String(settings)}
        </span>
      </header>
      <div className="card-body">
        <Well variant="list">
          <ul className="item-ul">
            {rows.map((row) => {
              const selected = row.key === current;
              return (
                <li key={row.key} className="item-row" data-setting-key={row.key}>
                  <Link
                    href={decidesHref({ setting: row.key }, filters)}
                    className={cx("item-link", selected && "chosen-row")}
                    {...(selected ? { "aria-current": "page" as const } : {})}
                    onPress={() => {
                      onOpen(row.key);
                    }}
                  >
                    <span className="item-name">{highlight(settingName(row.key), filters.q)}</span>
                    <span className="item-state num ref-list-count">
                      {narrowed || row.shown !== row.total
                        ? t("dc_list_of", { n: row.shown, total: row.total })
                        : String(row.total)}
                    </span>
                    <code className="item-value mono">
                      {breakAfterDots(highlight(row.key, filters.q))}
                    </code>
                  </Link>
                </li>
              );
            })}
          </ul>
        </Well>
      </div>
    </nav>
  );
}
