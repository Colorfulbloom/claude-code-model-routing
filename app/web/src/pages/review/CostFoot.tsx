/*
 * The note under a Review page's first cost card: costs are API-rate estimates with the date of
 * the prices, and a line when two price sources disagree. It shows once per page. A page with a
 * Runs column passes `runsNote`, the one line that says what a run is, so touch and keyboard
 * readers see it and not only a pointer.
 */
import { usePrices } from "@/api/client";
import type { AgentList } from "@/api/types";
import { dateWords } from "@/lib/clock";
import { modelLabel } from "@/lib/models";
import { t } from "@/strings/t";

export function CostFoot({
  prices,
  runsNote = false,
}: {
  prices: AgentList["prices"];
  runsNote?: boolean;
}) {
  const known = usePrices();
  const disagreed = known.data?.cross_check.models.map(modelLabel) ?? [];
  return (
    <div className="review-foot">
      {runsNote && <p>{t("runs_def")}</p>}
      <p>{t("foot_est", { date: dateWords(prices.as_of) })}</p>
      {prices.cross_check_state === "disagree" && disagreed.length > 0 && (
        <p className="review-warn">
          <span aria-hidden="true">{"▲ "}</span>
          {t("foot_disagree", { model: disagreed.join(", ") })}
        </p>
      )}
    </div>
  );
}
