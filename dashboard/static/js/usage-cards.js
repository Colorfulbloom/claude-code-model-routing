// Cards that the usage pages share, ported one to one from gen3.py. Each takes u, the object that
// fillUsage (usage-page.js) builds, and returns a node. They keep the old class names, so app.css applies
// unchanged. The numbers come from the server as they are: shares, agent order and ticks are not worked out
// again here.

import { h } from "./h.js";
import { t, renderText, fmtTokens, fmtCost, pct, shareText } from "./format.js";
import { card, kpi, delta } from "./components.js";
import {
  MODEL_CLASS, modelClass, ring, legendRows, stackedTokens, kindsLegend, hbars, miniRing, daybars,
} from "./charts.js";
import { ticksOf, ranWithLine } from "./usage-page.js";

// The cost tile's second est line, when the view has models with no list price.
function partlyPriced(view) {
  const unpriced = view.notes && Array.isArray(view.notes.unpriced) ? view.notes.unpriced : [];
  if (!unpriced.length) return null;
  const text = unpriced.length === 1 ? t("partly_priced") : t("partly_priced_many", { n: unpriced.length });
  return h("p", { class: "est" }, renderText(text));
}

export function usageKpis(u) {
  const { view, range } = u;
  const tot = view.totals;
  const p = view.previous || {};
  return h("div", { class: "kpis" },
    kpi({
      label: t("kpi_tokens"), value: fmtTokens(tot.tokens), icon: "bars",
      delta: delta(tot.tokens, p.tokens, range),
    }),
    kpi({
      label: t("kpi_cost"), value: fmtCost(tot.cost, tot.unpriced_requests), icon: "coins",
      sub: [u.est(), partlyPriced(view)],
      delta: delta(tot.cost, p.cost, range),
    }),
    kpi({
      label: t("kpi_hit"), value: pct(tot.hit_rate), icon: "cache",
      sub: h("span", { class: "kpi-def" }, t("hit_def")),
      delta: delta(tot.hit_rate ?? 0, tot.hit_rate === null ? null : p.hit_rate, range, true),
    }),
    kpi({
      label: t("kpi_runs"), value: tot.runs.toLocaleString("en-US"), icon: "agents",
      delta: delta(tot.runs, p.runs, range),
    }));
}

// One column per bucket: an hour on Today, a day on 7 and 30 days. The legend lists the models that appear.
export function perBucketCard(u) {
  const { view } = u;
  const hourly = view.bucket_unit === "hour";
  const buckets = view.buckets;
  const keys = buckets.map((b) => (hourly ? b.hour : b.date));
  const seen = (model) => buckets.some((b) => b.by_model[model] > 0);
  const listed = Object.keys(MODEL_CLASS).filter(seen);
  const other = buckets.some((b) => Object.keys(b.by_model).some((m) => modelClass(m) === "cat-other" && b.by_model[m] > 0));
  const legend = h("ul", { class: "klg" },
    listed.map((m) => h("li", null, h("span", { class: "swatch " + modelClass(m), "aria-hidden": "true" }), u.model(m))),
    other ? h("li", null, h("span", { class: "swatch cat-other", "aria-hidden": "true" }), t("other_models")) : null);
  const body = [
    daybars(buckets, keys, { unit: view.bucket_unit, ticks: ticksOf(view.axis.tokens_ticks), modelName: u.model }),
    hourly ? h("p", { class: "ring-sum" }, t("axis_hour")) : null,
    legend,
  ];
  return card({
    title: hourly ? t("c_per_hour") : t("c_per_day"), body, icon: "calendar", sub: t("q_time"),
  });
}

// Highest cost first, a model with no cost last. Array sort is stable, so equal costs keep the server's order.
function byCostDesc(a, b) {
  return (a.cost === null ? 1 : 0) - (b.cost === null ? 1 : 0) || (b.cost || 0) - (a.cost || 0);
}

export function costByModelCard(u) {
  const { view } = u;
  const tot = view.totals;
  const rows = view.by_model.slice().sort(byCostDesc);
  const segments = rows.map((r) => ({ label: u.model(r.model), value: r.cost || 0, cls: modelClass(r.model) }));
  const notPriced = (r) => r.cost === null || (r.cost === 0 && r.unpriced_requests > 0);
  const legend = legendRows(rows.map((r) => ({
    swatch: modelClass(r.model),
    label: u.model(r.model),
    cells: [
      fmtCost(r.cost, r.unpriced_requests),
      notPriced(r) ? "" : h("span", { class: "share" }, shareText(r.share_pct, r.share_lt1)),
    ],
  })), [t("kpi_cost"), t("lg_share")]);
  const body = [
    h("div", { class: "ring-row" }, ring(segments, fmtCost(tot.cost, tot.unpriced_requests), t("est_word"), "cost"), legend),
    u.est(),
  ];
  return card({ title: t("c_cost_model"), body, icon: "coins", sub: t("q_cost_model") });
}

// Agents arrive from the server by estimated cost, highest first, and keep that order.
export function tokensByAgentCard(u) {
  const { view } = u;
  const rows = view.by_agent.map((a) => ({ label: a.display, a, sub: ranWithLine(u, a) }));
  return card({
    title: t("c_tokens_agent"), body: [stackedTokens(rows), kindsLegend(view.totals)], icon: "agents", sub: t("q_where"),
  });
}

export function costByAgentCard(u) {
  const rows = u.view.by_agent.map((a) => ({
    label: a.display, value: a.cost || 0, text: fmtCost(a.cost, a.unpriced_requests),
  }));
  return card({ title: t("c_cost_agent"), body: [hbars(rows), u.est()], icon: "coins", sub: t("q_agents") });
}

export function cacheCard(u) {
  const minis = u.view.by_agent.map((a) =>
    miniRing(a.hit_rate, a.display, t("mini_cache_read", { n: fmtTokens(a.cache_read) })));
  const body = [h("div", { class: "minis" }, minis), h("p", { class: "ring-sum" }, t("hit_def"))];
  return card({ title: t("c_cache_agent"), body, icon: "cache", sub: t("q_cache") });
}

// low, medium, high and xhigh always, then max and Not recorded only when they have runs. The server decides.
export function effortCard(u) {
  const rows = u.view.by_effort.map((r) => ({
    label: r.effort === null || r.effort === undefined ? t("effort_not_recorded") : r.effort,
    value: r.tokens,
    text: fmtTokens(r.tokens),
  }));
  return card({ title: t("c_effort"), body: hbars(rows), icon: "sliders", sub: t("q_effort") });
}
