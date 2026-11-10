/*
 * The Agents table. Rows for every agent that ran in the range, then a group of agent files that
 * did not run. It is a plain table, like the sessions table, because the group header needs
 * `scope="colgroup"`. A name with a setup item is a link that opens the inspector beside the table
 * (`?agent=<item key>`), and the picked row takes the chosen look: a fill, a start bar and
 * `aria-current`. A click anywhere on a row with a link forwards to it (`useRowLink`). With an agent picked the table narrows to Agent, Check and Cost.
 * At 720px and below the Set to, Ran with and Runs columns clip-hide, as in the other tables.
 */
import { useId } from "react";
import { Link } from "react-aria-components";
import type { ReviewRange } from "@/api/types";
import { ModelSwatch } from "@/components/ModelSwatch/ModelSwatch";
import { ShareBar } from "@/components/ShareBar/ShareBar";
import { StatusChip } from "@/components/StatusChip/StatusChip";
import { Well } from "@/components/Well/Well";
import { cx } from "@/components/cx";
import { formatCost } from "@/lib/format";
import { STATUS_WORDS } from "@/lib/model-check";
import { reviewPath } from "@/lib/range";
import { useRowLink } from "@/lib/row-link";
import type { AgentRowView, AgentsView, NoRunsView, SetCell } from "@/lib/review-agents";
import { setWhyWords } from "@/lib/review-agents";
import { t } from "@/strings/t";
import "./AgentsPage.css";

/** What the table needs to build a name's link and mark the picked row. */
export interface AgentLinks {
  project: string;
  range: ReviewRange;
  /** The item key of the picked agent, or null with none picked. */
  picked: string | null;
}

/** A cell with nothing to say. The dash stands for "none" and reads as one dash to a screen reader. */
function Dash() {
  return <span className="muted">{"–"}</span>;
}

function SetTo({ cell }: { cell: SetCell }) {
  if (cell.text !== null) return <>{cell.text}</>;
  return (
    <span className="muted" data-set-why={cell.why ?? undefined}>
      {cell.why === null ? "" : setWhyWords(cell.why)}
    </span>
  );
}

function NameCell({ row, links }: { row: AgentRowView | NoRunsView; links: AgentLinks }) {
  const noteId = useId();
  const { source } = row;
  const picked = row.itemKey !== null && row.itemKey === links.picked;
  return (
    <th
      scope="row"
      className={cx("review-cell", picked && "chosen-cell-start")}
      {...(source.description !== null ? { "aria-describedby": noteId } : {})}
    >
      {row.itemKey === null ? (
        <span className="review-agents-name">{row.name}</span>
      ) : (
        <Link
          className="review-link review-agents-name review-agents-link"
          href={`#${reviewPath(links.project, "agents", links.range, { agent: row.itemKey })}`}
          data-agent-link={row.itemKey}
          {...(picked ? { "aria-current": "true" as const } : {})}
        >
          {row.name}
        </Link>
      )}
      <div className="review-agents-src muted">{source.text}</div>
      {source.description !== null && (
        <span id={noteId} className="sr-only">
          {source.description}
        </span>
      )}
    </th>
  );
}

function CheckCell({ row }: { row: AgentRowView }) {
  const noteId = useId();
  if (row.unchecked) {
    return (
      <>
        <span className="muted review-agents-unchecked" aria-describedby={noteId}>
          {t("ag_chk_unchecked")}
        </span>
        <span id={noteId} className="sr-only">
          {t("ag_chk_unchecked_aria")}
        </span>
      </>
    );
  }
  return row.check === null ? (
    <Dash />
  ) : (
    <StatusChip status={row.check}>{STATUS_WORDS[row.check]}</StatusChip>
  );
}

function RanRow({ row, links }: { row: AgentRowView; links: AgentLinks }) {
  const picked = row.itemKey !== null && row.itemKey === links.picked;
  const rowLink = useRowLink();
  return (
    <tr
      className={cx("review-row", picked && "review-agents-picked")}
      data-agent={row.key}
      {...(row.itemKey !== null ? rowLink : {})}
    >
      <NameCell row={row} links={links} />
      <td className="review-cell review-hp review-agents-wide">
        <SetTo cell={row.set} />
      </td>
      <td className="review-cell review-hp review-agents-wide">
        {row.ran.text === null ? (
          <Dash />
        ) : (
          <span className="review-agents-ran">
            {row.ran.model !== null && <ModelSwatch model={row.ran.model} />}
            {row.ran.text}
          </span>
        )}
        {row.ran.also.map((line) => (
          <div key={line} className="review-agents-also muted">
            {line}
          </div>
        ))}
      </td>
      <td className="review-cell">
        <CheckCell row={row} />
      </td>
      <td className="review-cell review-end review-hp review-agents-wide num">{row.runs}</td>
      <td className="review-cell review-end">
        <ShareBar variant="table" model={row.model} share={row.fill} value={row.cost} />
      </td>
    </tr>
  );
}

function NoRunsRow({ row, links }: { row: NoRunsView; links: AgentLinks }) {
  const picked = row.itemKey !== null && row.itemKey === links.picked;
  const rowLink = useRowLink();
  return (
    <tr
      className={cx("review-row review-agents-none", picked && "review-agents-picked")}
      data-agent={row.key}
      {...(row.itemKey !== null ? rowLink : {})}
    >
      <NameCell row={row} links={links} />
      <td className="review-cell review-hp review-agents-wide">
        <SetTo cell={row.set} />
      </td>
      <td className="review-cell review-hp review-agents-wide">
        <Dash />
      </td>
      <td className="review-cell">
        <Dash />
      </td>
      <td className="review-cell review-end review-hp review-agents-wide num muted">{0}</td>
      <td className="review-cell review-end num muted">{formatCost(0)}</td>
    </tr>
  );
}

export function AgentsTable({
  label,
  view,
  links,
}: {
  label: string;
  view: AgentsView;
  links: AgentLinks;
}) {
  return (
    <Well variant="list" className="review-table-well">
      <table
        className={cx(
          "review-table",
          "review-agents-table",
          links.picked !== null && "review-agents-narrow",
        )}
        aria-label={label}
      >
        <thead>
          <tr>
            <th scope="col" className="review-th">
              {t("ag_col_agent")}
            </th>
            <th scope="col" className="review-th review-hp review-agents-wide">
              {t("ag_col_set")}
            </th>
            <th scope="col" className="review-th review-hp review-agents-wide">
              {t("ag_col_ran")}
            </th>
            <th scope="col" className="review-th">
              {t("ag_col_check")}
            </th>
            <th scope="col" className="review-th review-end review-hp review-agents-wide">
              {t("ag_col_runs")}
            </th>
            <th scope="col" className="review-th review-end">
              {t("ag_col_cost")}
            </th>
          </tr>
        </thead>
        <tbody>
          {view.rows.map((row) => (
            <RanRow key={row.id} row={row} links={links} />
          ))}
          {view.neverRan.length > 0 && (
            <tr className="review-group">
              <th scope="colgroup" colSpan={6}>
                {t("ag_none_h")}
              </th>
            </tr>
          )}
          {view.neverRan.map((row) => (
            <NoRunsRow key={row.id} row={row} links={links} />
          ))}
        </tbody>
      </table>
    </Well>
  );
}
