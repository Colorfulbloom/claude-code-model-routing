/*
 * The Agents table. Rows for every agent that ran in the range, then a group of agent files that
 * did not run. It is a plain table, like the sessions table, because the group header needs
 * `scope="colgroup"`. The name is plain text, because agent pages come with the setup half.
 * At 720px and below the Set to, Ran with and Runs columns clip-hide, as in the other tables.
 */
import { useId } from "react";
import { ModelSwatch } from "@/components/ModelSwatch/ModelSwatch";
import { ShareBar } from "@/components/ShareBar/ShareBar";
import { StatusChip } from "@/components/StatusChip/StatusChip";
import { Well } from "@/components/Well/Well";
import { formatCost } from "@/lib/format";
import { STATUS_WORDS } from "@/lib/model-check";
import type { AgentRowView, AgentsView, NoRunsView, SetCell } from "@/lib/review-agents";
import { setWhyWords } from "@/lib/review-agents";
import { t } from "@/strings/t";
import "./AgentsPage.css";

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

function NameCell({ name, source }: { name: string; source: AgentRowView["source"] }) {
  const noteId = useId();
  return (
    <th
      scope="row"
      className="review-cell"
      {...(source.description !== null ? { "aria-describedby": noteId } : {})}
    >
      <span className="review-agents-name">{name}</span>
      <div className="review-agents-src muted">{source.text}</div>
      {source.description !== null && (
        <span id={noteId} className="sr-only">
          {source.description}
        </span>
      )}
    </th>
  );
}

function RanRow({ row }: { row: AgentRowView }) {
  return (
    <tr className="review-row" data-agent={row.key}>
      <NameCell name={row.name} source={row.source} />
      <td className="review-cell review-hp">
        <SetTo cell={row.set} />
      </td>
      <td className="review-cell review-hp">
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
        {row.check === null ? (
          <Dash />
        ) : (
          <StatusChip status={row.check}>{STATUS_WORDS[row.check]}</StatusChip>
        )}
      </td>
      <td className="review-cell review-end review-hp num">{row.runs}</td>
      <td className="review-cell review-end">
        <ShareBar variant="table" model={row.model} share={row.fill} value={row.cost} />
      </td>
    </tr>
  );
}

function NoRunsRow({ row }: { row: NoRunsView }) {
  return (
    <tr className="review-row review-agents-none" data-agent={row.key}>
      <NameCell name={row.name} source={row.source} />
      <td className="review-cell review-hp">
        <SetTo cell={row.set} />
      </td>
      <td className="review-cell review-hp">
        <Dash />
      </td>
      <td className="review-cell">
        <Dash />
      </td>
      <td className="review-cell review-end review-hp num muted">{0}</td>
      <td className="review-cell review-end num muted">{formatCost(0)}</td>
    </tr>
  );
}

export function AgentsTable({ label, view }: { label: string; view: AgentsView }) {
  return (
    <Well variant="list" className="review-table-well">
      <table className="review-table review-agents-table" aria-label={label}>
        <thead>
          <tr>
            <th scope="col" className="review-th">
              {t("ag_col_agent")}
            </th>
            <th scope="col" className="review-th review-hp">
              {t("ag_col_set")}
            </th>
            <th scope="col" className="review-th review-hp">
              {t("ag_col_ran")}
            </th>
            <th scope="col" className="review-th">
              {t("ag_col_check")}
            </th>
            <th scope="col" className="review-th review-end review-hp">
              {t("ag_col_runs")}
            </th>
            <th scope="col" className="review-th review-end">
              {t("ag_col_cost")}
            </th>
          </tr>
        </thead>
        <tbody>
          {view.rows.map((row) => (
            <RanRow key={row.key} row={row} />
          ))}
          {view.neverRan.length > 0 && (
            <tr className="review-group">
              <th scope="colgroup" colSpan={6}>
                {t("ag_none_h")}
              </th>
            </tr>
          )}
          {view.neverRan.map((row) => (
            <NoRunsRow key={row.key} row={row} />
          ))}
        </tbody>
      </table>
    </Well>
  );
}
