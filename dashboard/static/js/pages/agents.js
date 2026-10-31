// Agents. Ported from `agents_page` in gen3.py (screen 02). It reads one view of the /api/usage payload, so
// switching range fetches nothing. The rows keep the server's order (estimated cost, highest first).
// All projects drops Pinned to, Pin check and the note under the table, because a pin belongs to one project.

import { h, clear } from "../h.js";
import { t, renderText, fmtTokens, fmtCost, pct } from "../format.js";
import { ALL_KEY, MAIN_KEY } from "../router.js";
import { pageHead, rangeControl, card, table3, inline, pinPill } from "../components.js";
import { fillUsage } from "../usage-page.js";
import { costByAgentCard, cacheCard } from "../usage-cards.js";
import { pinView } from "../pin-view.js";

// "12 sessions" as a count and its word, split at the first space as components.delta splits its text.
function sessionsCell(n) {
  const text = n === 1 ? t("n_sessions_1") : t("n_sessions", { n: n.toLocaleString("en-US") });
  const cut = text.indexOf(" ");
  return inline(text.slice(0, cut), text.slice(cut + 1));
}

function ranWithCell(u, a) {
  const rows = Array.isArray(a.ran_with) ? a.ran_with : [];
  if (!rows.length) return "";
  const first = rows[0];
  const effort = first.effort === null || first.effort === undefined ? t("effort_not_recorded_inline") : first.effort;
  return [
    u.model(first.model) + ", " + effort,
    rows.length > 1 ? h("span", { class: "cell-note" }, t("ran_with_more", { n: rows.length - 1 })) : null,
  ];
}

function agentRow(u, a, withPin) {
  const view = withPin ? pinView(u, a) : null;
  const runs = a.route_key === MAIN_KEY ? sessionsCell(a.sessions) : a.runs.toLocaleString("en-US");
  const row = [
    h("a", { class: "lnk", href: u.hashFor("agent-detail", { agent: a.route_key }) }, a.display),
    runs,
    fmtTokens(a.tokens),
    fmtCost(a.cost, a.unpriced_requests),
    pct(a.hit_rate),
    ranWithCell(u, a),
  ];
  if (withPin) {
    row.push([view.pinnedText, view.pinnedNote ? h("span", { class: "cell-note" }, view.pinnedNote) : null]);
    row.push(view.pill ? [pinPill(view.pill, view.pillLabel), view.note ? h("span", { class: "cell-note" }, view.note) : null] : "");
  }
  return row;
}

export function render(root, ctx) {
  clear(root);
  const single = ctx.project.key !== ALL_KEY;
  // All projects hides the pin check, so its intro does not mention a pin.
  const intro = single ? t("intro_agents") : t("intro_agents_all");
  root.appendChild(pageHead({ title: t("nav_agents"), intro, right: rangeControl(ctx.range, ctx.setRange) }));
  fillUsage(root, ctx, (u) => {
    const cols = [t("h_agent"), t("h_runs"), t("kpi_tokens"), t("kpi_cost"), t("kpi_hit"), t("h_ran_at")];
    if (single) cols.push(t("h_pinned"), t("h_pin_check"));
    const rows = u.view.by_agent.map((a) => agentRow(u, a, single));
    const body = [table3(cols, rows), u.est(), single ? h("p", { class: "est" }, renderText(t("pin_note"))) : null];
    return [
      h("div", { class: "g2" }, costByAgentCard(u), cacheCard(u)),
      card({ title: t("c_agents_table"), body, icon: "agents" }),
    ];
  });
}
