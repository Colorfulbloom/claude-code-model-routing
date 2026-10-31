// Agent detail, at #/agents/<name or @main>. Ported from `agent_detail` in gen3.py (screen 03). The agent name
// is data, so it goes in as text and never as markup. The agent comes from the view's by_agent list, found by
// route_key, so an agent with no runs in this range gets the empty state.

import { h, clear } from "../h.js";
import { t, renderText, fmtTokens, fmtCost, pct, fmtTime } from "../format.js";
import { ALL_KEY, MAIN_KEY } from "../router.js";
import { pageHead, rangeControl, card, kpi, table3, emptyState, pinPill } from "../components.js";
import { fillUsage, ticksOf, noRangeText } from "../usage-page.js";
import { kindsTable } from "../usage-cards.js";
import { stackedTokens, daybars } from "../charts.js";
import { pinView } from "../pin-view.js";

const UNNAMED_KEY = "@unnamed";

function titleOf(key) {
  if (key === MAIN_KEY) return t("row_main");
  if (key === UNNAMED_KEY) return t("agent_unnamed");
  return key;
}

function tiles(u, a) {
  const main = a.route_key === MAIN_KEY;
  return h("div", { class: "kpis" },
    kpi(main
      ? { label: t("h_sessions"), value: a.sessions.toLocaleString("en-US"), icon: "agents" }
      : { label: t("kpi_runs"), value: a.runs.toLocaleString("en-US"), icon: "agents" }),
    kpi({ label: t("kpi_tokens"), value: fmtTokens(a.tokens), icon: "bars" }),
    kpi({ label: t("kpi_cost"), value: fmtCost(a.cost, a.unpriced_requests), icon: "coins", sub: u.est() }),
    kpi({ label: t("kpi_hit"), value: pct(a.hit_rate), icon: "cache", sub: h("span", { class: "kpi-def" }, t("hit_def")) }));
}

// "Pinned to {model} at {effort}. Ran with {model} at {effort}." then what decided it.
function pinCard(u, a) {
  const view = pinView(u, a);
  const first = Array.isArray(a.ran_with) && a.ran_with.length ? a.ran_with[0] : null;
  let ran = null;
  if (first) {
    ran = first.effort === null || first.effort === undefined
      ? t("ran_at_no_effort", { model: u.model(first.model) })
      : t("ran_at_fmt", { model: u.model(first.model), effort: first.effort });
  }
  const line = [view.detailPinned, ran].filter(Boolean).join(" ");
  const link = view.trailKey
    ? h("p", { class: "pin-link" },
      h("a", { href: u.hashFor("trail", { agent: a.route_key, setting: view.trailKey }) }, t("open_trail")))
    : null;
  const body = h("div", { class: "pin" },
    h("div", { class: "pin-top" }, view.pill ? pinPill(view.pill, view.pillLabel) : null, line ? h("p", null, line) : null),
    view.note ? h("p", { class: "en-rs" }, renderText(view.note)) : null,
    view.sentences.map((text) => h("p", { class: "en-rs" }, renderText(text))),
    link);
  return card({ title: t("c_pin_check"), body, icon: "pin" });
}

function runsOverTimeCard(u, a) {
  const { view } = u;
  const hourly = view.bucket_unit === "hour";
  const keys = view.buckets.map((b) => (hourly ? b.hour : b.date));
  const body = [
    daybars(a.runs_per_day, keys, { runs: true, unit: view.bucket_unit, height: 150, ticks: ticksOf(a.runs_ticks) }),
    h("p", { class: "ring-sum" }, hourly ? t("runs_axis_hour") : t("runs_axis")),
  ];
  return card({ title: t("c_runs_time"), body, icon: "calendar", sub: t("q_runs_time") });
}

function tokensCostCard(u, a) {
  const body = [
    stackedTokens([{ label: a.display, a }]),
    kindsTable(a),
    a.thinking ? h("p", { class: "ring-sum" }, t("thinking_note", { n: fmtTokens(a.thinking) })) : null,
    u.est(),
  ];
  return card({ title: t("c_tokens_cost"), body, icon: "bars", sub: t("q_tokens_kind") });
}

function recentRunsCard(u, a, all) {
  const cols = [t("h_started"), t("h_parent")];
  if (all) cols.push(t("h_project"));
  cols.push(t("f_model"), t("f_effort"), t("kpi_tokens"), t("kpi_cost"));
  const rows = (a.recent_runs || []).map((r) => {
    const row = [
      fmtTime(r.started),
      h("a", { class: "lnk", href: u.hashFor("session-detail", { id: r.session_id }) },
        t("session_from", { time: fmtTime(r.session_started) })),
    ];
    if (all) row.push(r.project);
    row.push(
      u.model(r.model),
      r.effort === null || r.effort === undefined ? t("effort_not_recorded") : r.effort,
      fmtTokens(r.tokens),
      fmtCost(r.cost, r.unpriced_requests));
    return row;
  });
  return card({ title: t("c_recent_runs"), body: [table3(cols, rows), u.est()], icon: "list" });
}

export function render(root, ctx) {
  clear(root);
  if (ctx.route.name !== "agent-detail") return; // the route carries the parameters this page needs
  const key = ctx.route.params.agent;
  root.appendChild(pageHead({
    title: titleOf(key),
    right: rangeControl(ctx.range, ctx.setRange),
    crumbs: [{ label: t("nav_agents"), href: ctx.hashFor("agents") }],
  }));
  fillUsage(root, ctx, (u) => {
    const a = u.view.by_agent.find((row) => row.route_key === key);
    if (!a) return [emptyState(t("s_no_range_h"), noRangeText(ctx))];
    const all = u.project.key === ALL_KEY;
    return [
      all ? tiles(u, a) : h("div", { class: "g21 g21-pin" }, tiles(u, a), pinCard(u, a)),
      h("div", { class: "g2" }, runsOverTimeCard(u, a), tokensCostCard(u, a)),
      recentRunsCard(u, a, all),
    ];
  });
}
