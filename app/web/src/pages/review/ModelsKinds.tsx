/*
 * What the cost is made of: the four kinds as a legend with their totals, the note that says
 * patterns mean kinds and colours mean models, and one stacked row per model. The stack's pieces
 * are told apart by pattern, never by colour alone, and each row says its kind amounts as text
 * under the stack, so the picture is never the only way to read them. The picture is one image
 * with the chart's label. The legend and the rows' text sit outside it.
 */
import type { ModelList, ReviewRange } from "@/api/types";
import { HelpButton } from "@/components/HelpButton/HelpButton";
import { Well } from "@/components/Well/Well";
import { ModelSwatch } from "@/components/ModelSwatch/ModelSwatch";
import { buildKindLegend, buildKindRows, kindsImageLabel } from "@/lib/review-models";
import { t } from "@/strings/t";
import "./ModelsPage.css";

export function ModelsKinds({ answer, range }: { answer: ModelList; range: ReviewRange }) {
  const legend = buildKindLegend(answer);
  const rows = buildKindRows(answer);
  return (
    <>
      <div className="review-models-legendrow">
        <ul className="review-models-legend">
          {legend.map((entry) => (
            <li key={entry.kind} data-kind={entry.kind}>
              <i
                className={`review-models-kp review-models-kp${String(entry.pattern)}`}
                aria-hidden="true"
              />
              {entry.label} <b className="num">{entry.total}</b>
            </li>
          ))}
        </ul>
        <HelpButton help="models.chart" />
      </div>
      <p className="review-models-note">{t("kind_legend_note")}</p>
      <Well className="review-models-well">
        <div role="img" aria-label={kindsImageLabel(answer, range)}>
          <ul className="review-models-rows">
            {rows.map((row) => (
              <li key={row.id} data-model={row.id}>
                <span className="review-models-kname">
                  {row.family !== null && <ModelSwatch model={row.family} />}
                  {row.name}
                </span>
                <span
                  className={`review-models-stack review-models-ink-${row.family ?? "neutral"}`}
                  style={{
                    width: row.stack.length === 0 ? 0 : `${String(Math.max(2, row.width * 100))}%`,
                  }}
                >
                  {row.stack.map((part) => (
                    <i
                      key={part.kind}
                      className={`review-models-kp review-models-kp${String(part.pattern)}`}
                      style={{ flexGrow: part.amount }}
                    />
                  ))}
                </span>
                <span className="review-models-kvalue num">{row.total}</span>
                <span className="review-models-kparts muted">
                  {row.parts.map((part) => `${part.label} ${part.text}`).join(", ")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </Well>
    </>
  );
}
