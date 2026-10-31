// All projects: the overview when the project is All. Ported from `all_projects` in gen3.py (screen 11).
// It reads the all view of the /api/usage payload, so switching range fetches nothing. The two cards at the
// bottom list every transcript folder in by_project, the listed ones and the rest, in one token order.
// A listed folder links to that project's overview. An unlisted folder is plain text with the Not on the list
// note, because it has no project to open.

import { h, clear } from "../h.js";
import { t, rangeWord, fmtTokens, fmtCost, pct } from "../format.js";
import { pageHead, rangeControl, card, table3 } from "../components.js";
import { stackedTokens, kindsLegend } from "../charts.js";
import { fillUsage } from "../usage-page.js";
import { usageKpis, perBucketCard, costByModelCard } from "../usage-cards.js";

// The folders with the most tokens first. Array sort is stable, so equal tokens keep the server's order.
// Both cards use it, so one order holds on the page.
function projectsByTokens(view) {
  const rows = Array.isArray(view.by_project) ? view.by_project : [];
  return rows.slice().sort((a, b) => b.tokens - a.tokens);
}

function tokensByProjectCard(view, rows) {
  const bars = rows.map((row) => ({ label: row.name, a: row, sub: null }));
  return card({
    title: t("c_tokens_project"), body: [stackedTokens(bars), kindsLegend(view.totals)], icon: "bars", sub: t("q_where"),
  });
}

function projectCell(u, row) {
  if (!row.key) return [row.name, h("span", { class: "cell-note" }, t("not_listed"))];
  return h("a", { class: "lnk", href: u.hashFor("overview", {}, { project: row.key }) }, row.name);
}

// The cost, with a star when the row has requests the dashboard could not price.
function costCell(row) {
  const text = fmtCost(row.cost, row.unpriced_requests);
  if (!row.unpriced_requests) return text;
  return h("span", { class: "cw" }, text, h("sup", { class: "fn", "aria-hidden": "true" }, "*"));
}

function partlyPricedNote(row) {
  const text = row.unpriced_requests === 1
    ? t("partly_priced_row_1", { project: row.name })
    : t("partly_priced_row", { project: row.name, n: row.unpriced_requests });
  return h("p", { class: "est" }, h("span", { "aria-hidden": "true" }, "*"), " ", text);
}

function projectsCard(u, rows) {
  const cols = [t("h_project"), t("h_sessions"), t("kpi_runs"), t("kpi_tokens"), t("kpi_cost"), t("kpi_hit")];
  const cells = rows.map((row) => [
    projectCell(u, row),
    row.sessions.toLocaleString("en-US"),
    row.runs.toLocaleString("en-US"),
    fmtTokens(row.tokens),
    costCell(row),
    pct(row.hit_rate),
  ]);
  const body = [
    table3(cols, cells),
    rows.filter((row) => row.unpriced_requests).map(partlyPricedNote),
    u.est(),
  ];
  return card({ title: t("c_projects_table"), body, icon: "overview" });
}

export function render(root, ctx) {
  clear(root);
  const intro = ctx.range === "today"
    ? t("intro_all_today")
    : t("intro_all", { range: rangeWord(ctx.range).toLowerCase() });
  root.appendChild(pageHead({ title: t("all_projects"), intro, right: rangeControl(ctx.range, ctx.setRange) }));
  fillUsage(root, ctx, (u) => {
    const rows = projectsByTokens(u.view);
    return [
      usageKpis(u),
      h("div", { class: "g21" }, perBucketCard(u), costByModelCard(u)),
      h("div", { class: "g2" }, tokensByProjectCard(u.view, rows), projectsCard(u, rows)),
    ];
  });
}
