/*
 * The map's table: Part, What applies, Status. A plain table, because a row opens a page and holds
 * chips, so the grid keyboard model would hide the links. The part name is the row header and the
 * link. At 720px and below each row stacks, with the statuses beside the name and the chips under
 * the summary. With the Switch on, a row's scope chips sit under its summary (owner decision 1).
 */
import { Link } from "react-aria-components";
import { HelpTerm } from "@/components/HelpTerm/HelpTerm";
import { ScopeChip } from "@/components/ScopeChip/ScopeChip";
import { StatusChip } from "@/components/StatusChip/StatusChip";
import { Well } from "@/components/Well/Well";
import { useIsDesktop } from "@/lib/media";
import type { MapRowView } from "@/lib/setup-map";
import { setupPartPath } from "@/lib/setup-routes";
import { t } from "@/strings/t";

function Row({ project, row, scopes }: { project: string; row: MapRowView; scopes: boolean }) {
  return (
    <tr className="setup-map-row" data-part={row.part}>
      <th scope="row" className="setup-map-part">
        <Link className="setup-map-link" href={`#${setupPartPath(project, row.part, scopes)}`}>
          {row.name}
        </Link>
      </th>
      <td className="setup-map-what">
        <div className="setup-map-body">
          <span className="setup-map-summary">{row.summary}</span>
          {row.unread !== null && (
            <span className="setup-map-unread">
              <span aria-hidden="true" className="setup-map-x">
                {"✕"}
              </span>
              {row.unread}
            </span>
          )}
          {scopes && (
            <ul className="setup-map-chips">
              {row.chips.map((chip) => (
                <li key={chip.scope}>
                  <ScopeChip scope={chip.name} value={chip.value} />
                </li>
              ))}
              {row.noChips && <li className="setup-map-none muted">{t("sc_none")}</li>}
            </ul>
          )}
        </div>
      </td>
      <td className="setup-map-status">
        {row.statuses.length === 0 ? (
          <span className="muted">{"–"}</span>
        ) : (
          <span className="setup-map-chips-status">
            {row.statuses.map((s) => (
              <StatusChip key={s.status} status={s.status}>
                {s.label}
              </StatusChip>
            ))}
          </span>
        )}
      </td>
    </tr>
  );
}

export function SetupMapTable({
  project,
  rows,
  scopes,
}: {
  project: string;
  rows: MapRowView[];
  scopes: boolean;
}) {
  const desktop = useIsDesktop();
  return (
    <Well variant="list" className="setup-map-well">
      <table className="setup-map" aria-label={t("su_card_h")}>
        <thead>
          <tr>
            {/* At 720px and below the header row is clipped, so Runs and Status stay plain text and
                never hold a focus stop nobody can see. */}
            <th scope="col" className="setup-map-th">
              {t("su_col_what")}
            </th>
            <th scope="col" className="setup-map-th">
              {desktop ? (
                <HelpTerm help="setup.map" line={t("su_col_runs")}>
                  {t("su_col_runs")}
                </HelpTerm>
              ) : (
                t("su_col_runs")
              )}
            </th>
            <th scope="col" className="setup-map-th">
              {desktop ? (
                <HelpTerm help="setup.map" line={t("su_col_status")}>
                  {t("su_col_status")}
                </HelpTerm>
              ) : (
                t("su_col_status")
              )}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <Row key={row.part} project={project} row={row} scopes={scopes} />
          ))}
        </tbody>
      </table>
    </Well>
  );
}
