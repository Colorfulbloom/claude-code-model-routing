/*
 * The cost cell for a run, a fold or a request. A cost sums the priced requests only. When some
 * requests have no price it reads "at least {cost}", and when none has one it names the model.
 */
import type { LaneCost } from "@/components/TimelineLane/TimelineLane";
import type { Unpriced } from "@/api/types";
import { formatCost, formatCostAtLeast } from "@/lib/format";
import { t } from "@/strings/t";

/** `cost` is null when no request in the group has a price. */
export function laneCost(cost: number | null, unpriced: Unpriced): LaneCost {
  if (cost === null) {
    const model = unpriced.models.join(", ");
    // The cell shows the short words, so a narrow cost column never wraps. The model goes in `full`.
    return model === ""
      ? { kind: "none", text: t("c_none_short") }
      : { kind: "none", text: t("c_none_short"), full: t("c_none", { model }) };
  }
  if (unpriced.requests > 0) return { kind: "least", text: formatCostAtLeast(cost) };
  return { kind: "cost", text: formatCost(cost) };
}

/** Adds groups together: the cost of the priced ones, and the unpriced requests and models of all. */
export function sumCosts(groups: readonly { cost: number | null; unpriced: Unpriced }[]): {
  cost: number | null;
  unpriced: Unpriced;
} {
  let cost: number | null = null;
  let requests = 0;
  const models: string[] = [];
  for (const group of groups) {
    if (group.cost !== null) cost = (cost ?? 0) + group.cost;
    requests += group.unpriced.requests;
    for (const model of group.unpriced.models) if (!models.includes(model)) models.push(model);
  }
  return { cost, unpriced: { requests, models } };
}
