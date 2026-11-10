/*
 * The session rows both Review pages draw: the Sessions page under its day headers, and Summary's
 * four most expensive sessions with no headers. It is a plain table, not the grid table, because a
 * day header row needs `scope="colgroup"`. The first cell is the link to Session review, with the
 * range kept, and a click anywhere on the row forwards to it (`useRowLink`). At 720px and below the Agents, Runs and Tokens columns clip-hide, as in the other tables.
 */
import { useId } from "react";
import { Link } from "react-aria-components";
import type { ReviewRange } from "@/api/types";
import { Badge } from "@/components/Badge/Badge";
import { RunStateGlyph } from "@/components/RunStateGlyph/RunStateGlyph";
import { ShareBar } from "@/components/ShareBar/ShareBar";
import { Well } from "@/components/Well/Well";
import { reviewPath } from "@/lib/range";
import { useRowLink } from "@/lib/row-link";
import type { SessionGroup, SessionRowView } from "@/lib/review-cards";
import { t } from "@/strings/t";

function stateWord(state: SessionRowView["state"]): string | null {
  return state === "working" ? t("rs_working") : state === "idle" ? t("rs_idle") : null;
}

function Row({
  row,
  project,
  range,
}: {
  row: SessionRowView;
  project: string;
  range: ReviewRange;
}) {
  const noteId = useId();
  const word = stateWord(row.state);
  const rowLink = useRowLink();
  return (
    <tr className="review-row" {...rowLink}>
      <th scope="row" className="review-cell review-session">
        <Link
          className="review-link"
          href={`#${reviewPath(project, { session: row.id }, range)}`}
          data-session={row.id}
          {...(row.startedEarlier ? { "aria-describedby": noteId } : {})}
        >
          {row.when}
        </Link>
        {word !== null && (
          <RunStateGlyph
            state={row.state === "working" ? "working" : "idle"}
            className="review-state"
          >
            {word}
          </RunStateGlyph>
        )}
        {row.startedEarlier && (
          <>
            <Badge className="review-before">{t("ss_before")}</Badge>
            <span id={noteId} className="sr-only">
              {t("ss_before_aria")}
            </span>
          </>
        )}
        <div className="review-branch muted">{row.branch}</div>
      </th>
      <td className="review-cell review-hp">
        {row.agents.map((agent) => (
          <Badge key={agent} className="review-agent">
            {agent}
          </Badge>
        ))}
      </td>
      <td className="review-cell review-end review-hp num">{row.runs}</td>
      <td className="review-cell review-end review-hp num">{row.tokens}</td>
      <td className="review-cell review-end">
        <ShareBar variant="table" model={null} share={row.fill} value={row.cost} />
      </td>
    </tr>
  );
}

export function SessionsTable({
  label,
  groups,
  project,
  range,
}: {
  label: string;
  groups: SessionGroup[];
  project: string;
  range: ReviewRange;
}) {
  return (
    <Well variant="list" className="review-table-well">
      <table className="review-table" aria-label={label}>
        <thead>
          <tr>
            <th scope="col" className="review-th">
              {t("ss_col_session")}
            </th>
            <th scope="col" className="review-th review-hp">
              {t("ss_col_agents")}
            </th>
            <th scope="col" className="review-th review-end review-hp">
              {t("ss_col_runs")}
            </th>
            <th scope="col" className="review-th review-end review-hp">
              {t("ss_col_tokens")}
            </th>
            <th scope="col" className="review-th review-end">
              {t("ss_col_cost")}
            </th>
          </tr>
        </thead>
        <tbody>
          {groups.flatMap((group) => [
            ...(group.label === ""
              ? []
              : [
                  <tr key={`h-${group.key}`} className="review-group">
                    <th scope="colgroup" colSpan={5}>
                      {group.label}
                    </th>
                  </tr>,
                ]),
            ...group.rows.map((row) => (
              <Row key={row.id} row={row} project={project} range={range} />
            )),
          ])}
        </tbody>
      </table>
    </Well>
  );
}
