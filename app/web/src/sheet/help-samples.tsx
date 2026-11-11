/*
 * Sample cells for the help components and the search field (M5). The open states draw the panel
 * in place (the `sheetOpen` and `inline` props), because a real popover or tray would cover the
 * other cells, as the Select's open state does.
 */
import { useState } from "react";
import { HelpButton } from "@/components/HelpButton/HelpButton";
import { HelpEntry } from "@/components/HelpEntry/HelpEntry";
import { HelpPanel } from "@/components/HelpPanel/HelpPanel";
import { HelpTerm } from "@/components/HelpTerm/HelpTerm";
import { highlight, matches } from "@/components/SearchField/match";
import { SearchField } from "@/components/SearchField/SearchField";
import { StatusChip } from "@/components/StatusChip/StatusChip";
import { t } from "@/strings/t";
import { W } from "./words";

const CACHE_VALUES = { value: "78%", delta: "81%" } as const;

/** Stands in for a Glossary that holds none of the entry's terms, so no link may render. */
const termsMissing = () => false;

export type HelpButtonState =
  "closed" | "open-popover" | "open-with-values" | "line-marked" | "word-marked";

export function HelpButtonDemo({ state }: { state: HelpButtonState }) {
  switch (state) {
    case "closed":
      return (
        <span className="sheet-help-row">
          <span className="muted">{W.t_cache}</span>
          <HelpButton help="live.cache" values={CACHE_VALUES} />
        </span>
      );
    case "open-popover":
      return <HelpButton help="live.cache" sheetOpen={{}} />;
    case "open-with-values":
      return <HelpButton help="live.cache" values={CACHE_VALUES} sheetOpen={{}} />;
    case "line-marked":
      return (
        <HelpButton
          help="live.cache"
          values={CACHE_VALUES}
          line="In the last minute"
          sheetOpen={{}}
        />
      );
    case "word-marked":
      return <HelpButton help="agents.check" word="lowered" sheetOpen={{}} />;
  }
}

export type HelpTermState = "closed" | "open" | "in-header";

export function HelpTermDemo({ state }: { state: HelpTermState }) {
  switch (state) {
    case "closed":
      return <HelpTerm help="agents.check">{W.sheet_hp_th_check}</HelpTerm>;
    case "open":
      return (
        <HelpTerm help="setup.where" sheetOpen={{}}>
          {W.sheet_hp_where}
        </HelpTerm>
      );
    case "in-header":
      return (
        <table className="sheet-hp-table">
          <thead>
            <tr>
              <th scope="col">{W.sheet_hp_th_agent}</th>
              <th scope="col">
                <HelpTerm help="agents.check">{W.sheet_hp_th_check}</HelpTerm>
              </th>
              <th scope="col" className="sheet-hp-num">
                {W.sheet_hp_th_cost}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{W.sheet_hp_td_agent}</td>
              <td>
                <StatusChip status="overridden">{t("status_overridden")}</StatusChip>
              </td>
              <td className="sheet-hp-num num">{W.sheet_hp_td_cost}</td>
            </tr>
            <tr>
              <td>{W.sheet_hp_td_agent_2}</td>
              <td>
                <StatusChip status="in_effect">{t("status_in_effect")}</StatusChip>
              </td>
              <td className="sheet-hp-num num">{W.sheet_hp_td_cost_2}</td>
            </tr>
          </tbody>
        </table>
      );
  }
}

export type HelpPanelState = "popover" | "tray";

export function HelpPanelDemo({ state }: { state: HelpPanelState }) {
  return state === "popover" ? (
    <HelpPanel help="setup.where" line="Row" inline />
  ) : (
    <div className="sheet-phone sheet-tray-frame">
      <HelpPanel help="agents.check" word="lowered" tray inline />
    </div>
  );
}

export type HelpEntryState = "full" | "list-status" | "list-scopes" | "no-glossary";

export function HelpEntryDemo({ state }: { state: HelpEntryState }) {
  const body = (() => {
    switch (state) {
      case "full":
        return <HelpEntry help="live.cache" values={CACHE_VALUES} line="Percent" />;
      case "list-status":
        return <HelpEntry help="agents.check" word="invalid" />;
      case "list-scopes":
        return <HelpEntry help="setup.scopes" word="user" />;
      case "no-glossary":
        return <HelpEntry help="live.cache" values={CACHE_VALUES} termExists={termsMissing} />;
    }
  })();
  return <div className="sheet-hp-card">{body}</div>;
}

export type SearchFieldState = "empty" | "typed" | "no-results";

const RULES = [W.sheet_search_rule_1, W.sheet_search_rule_2, W.sheet_search_rule_3] as const;

/** A search field with its own value and a short list it filters, for the sheet. */
export function SearchFieldDemo({ state }: { state: SearchFieldState }) {
  const [value, setValue] = useState(
    state === "typed" ? "cache" : state === "no-results" ? "zzz" : "",
  );
  const shown = RULES.filter((rule) => matches(value, rule));
  const count =
    shown.length === RULES.length
      ? undefined
      : shown.length === 0
        ? W.sheet_search_count_none
        : W.sheet_search_count_some;
  return (
    <div className="sheet-search">
      <SearchField
        label={W.sheet_search_label}
        clearLabel={W.sheet_search_clear}
        value={value}
        onChange={setValue}
        {...(count === undefined ? {} : { count, announce: count })}
      />
      {shown.length === 0 ? (
        <p className="muted">{W.sheet_search_none}</p>
      ) : (
        <ul className="sheet-list">
          {shown.map((rule) => (
            <li key={rule}>{highlight(rule, value)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
