/*
 * The Models table: what each model cost over the range, its share, its tokens, how much of its
 * input came from cache and which agents used it. A model with no price keeps its row and shows
 * "No price" in place of a cost and a share. At 720px and below the Share, Tokens, From cache and
 * Used by columns clip-hide, and a line under the name says the same in one sentence of figures.
 */
import { Badge } from "@/components/Badge/Badge";
import { HelpTerm } from "@/components/HelpTerm/HelpTerm";
import { ModelSwatch } from "@/components/ModelSwatch/ModelSwatch";
import { ShareBar } from "@/components/ShareBar/ShareBar";
import { Well } from "@/components/Well/Well";
import { useIsDesktop } from "@/lib/media";
import type { ModelRowView } from "@/lib/review-models";
import { phoneLine } from "@/lib/review-models";
import { t } from "@/strings/t";
import "./ModelsPage.css";

function Dash() {
  return <span className="muted">{"–"}</span>;
}

function Row({ row }: { row: ModelRowView }) {
  return (
    <tr className="review-row" data-model={row.id}>
      <th scope="row" className="review-cell">
        <span className="review-models-name">
          {row.family !== null && <ModelSwatch model={row.family} />}
          {row.name}
        </span>
        <div className="review-models-phone muted" aria-hidden="true">
          {phoneLine(row)}
        </div>
      </th>
      <td className="review-cell review-end num">{row.cost}</td>
      <td className="review-cell review-hp review-models-share">
        {row.fill === null || row.percent === null ? (
          <Dash />
        ) : (
          <ShareBar variant="table" model={row.family} share={row.fill} value={row.percent} />
        )}
      </td>
      <td className="review-cell review-end review-hp num">{row.tokens}</td>
      <td className="review-cell review-end review-hp num">{row.cache ?? <Dash />}</td>
      <td className="review-cell review-hp">
        {row.usedBy.map((agent) => (
          <Badge key={agent} className="review-agent">
            {agent}
          </Badge>
        ))}
      </td>
    </tr>
  );
}

export function ModelsTable({ label, rows }: { label: string; rows: ModelRowView[] }) {
  const desktop = useIsDesktop();
  return (
    <Well variant="list" className="review-table-well">
      <table className="review-table review-models-table" aria-label={label}>
        <thead>
          <tr>
            <th scope="col" className="review-th">
              {t("md_col_model")}
            </th>
            <th scope="col" className="review-th review-end">
              {t("md_col_cost")}
            </th>
            {/* At 720px and below Share and From cache are clipped, so they stay plain text and never
                hold a focus stop nobody can see. */}
            <th scope="col" className="review-th review-hp">
              {desktop ? (
                <HelpTerm help="models.cols" line={t("md_col_share")}>
                  {t("md_col_share")}
                </HelpTerm>
              ) : (
                t("md_col_share")
              )}
            </th>
            <th scope="col" className="review-th review-end review-hp">
              {t("md_col_tokens")}
            </th>
            <th scope="col" className="review-th review-end review-hp">
              {desktop ? (
                <HelpTerm help="models.cols" line={t("md_col_cache")}>
                  {t("md_col_cache")}
                </HelpTerm>
              ) : (
                t("md_col_cache")
              )}
            </th>
            <th scope="col" className="review-th review-hp">
              {t("md_col_used")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <Row key={row.id} row={row} />
          ))}
        </tbody>
      </table>
    </Well>
  );
}
