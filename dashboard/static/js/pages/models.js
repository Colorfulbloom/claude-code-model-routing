// Models. Ported from `models_page` in gen3.py (screen 04). It reads one view of the /api/usage payload, so
// switching range fetches nothing. Every list follows modelsByCost, so the cost card, the tokens card and the
// table share one order. Used by comes from the agents the model's row carries, in the order the server sends.

import { h, clear } from "../h.js";
import { t, fmtTokens, fmtCost, pct } from "../format.js";
import { pageHead, rangeControl, card, table3 } from "../components.js";
import { modelClass, stackedTokens, kindsLegend } from "../charts.js";
import { fillUsage } from "../usage-page.js";
import { costByModelCard, modelsByCost } from "../usage-cards.js";

function tokensByModelCard(view, rows) {
  const bars = rows.map((r) => ({ label: r.display_name, a: r, sub: null }));
  return card({
    title: t("c_tokens_model"), body: [stackedTokens(bars), kindsLegend(view.totals)], icon: "bars", sub: t("q_where"),
  });
}

function modelCell(r) {
  return [
    h("span", { class: "cw" }, h("span", { class: "swatch " + modelClass(r.model), "aria-hidden": "true" }), r.display_name),
    " ",
    h("span", { class: "muted mono" }, r.model),
  ];
}

export function render(root, ctx) {
  clear(root);
  root.appendChild(pageHead({ title: t("nav_models"), intro: t("intro_models"), right: rangeControl(ctx.range, ctx.setRange) }));
  fillUsage(root, ctx, (u) => {
    const { view } = u;
    const rows = modelsByCost(view);
    const cols = [t("f_model"), t("h_requests"), t("kpi_tokens"), t("kpi_cost"), t("kpi_hit"), t("h_used_by")];
    const cells = rows.map((r) => [
      modelCell(r),
      r.requests.toLocaleString("en-US"),
      fmtTokens(r.tokens),
      fmtCost(r.cost, r.unpriced_requests),
      pct(r.hit_rate),
      Array.isArray(r.agents) ? r.agents.join(", ") : "",
    ]);
    const unpriced = view.notes && Array.isArray(view.notes.unpriced) ? view.notes.unpriced : [];
    const body = [
      table3(cols, cells),
      u.est(),
      unpriced.map((n) => h("p", { class: "est" }, t("not_priced_note", { model: u.model(n.model) }))),
    ];
    return [
      h("div", { class: "g2" }, costByModelCard(u), tokensByModelCard(view, rows)),
      card({ title: t("c_models_table"), body, icon: "cpu" }),
    ];
  });
}
