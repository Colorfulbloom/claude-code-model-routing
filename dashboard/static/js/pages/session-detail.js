// Session detail, at #/sessions/<id>. Ported from `session_detail` in gen3.py (screen 06). The title is the
// session id until the usage payload arrives. Then the page redraws with the real head, "Session from {time}".
// The id, branch, project and agent names are data, so they go in as text and never as markup.
// The session comes from the 30 day view whatever the range in the address, so the page has no range control.

import { h, clear } from "../h.js";
import { t, fmtTokens, fmtCost, pct, fmtTime } from "../format.js";
import { MAIN_KEY } from "../router.js";
import { pageHead, card, kpi, table3, emptyState } from "../components.js";
import { fillUsage, findSession } from "../usage-page.js";
import { stackedTokens, kindsLegend } from "../charts.js";

const UNNAMED_KEY = "@unnamed";

// A by_agent row has agent null for Main, "@unnamed" for an unnamed agent and the name for the rest.
function agentOf(row) {
  if (row.agent === null || row.agent === undefined) return { key: MAIN_KEY, display: t("row_main"), runs: 1 };
  if (row.agent === UNNAMED_KEY) return { key: row.agent, display: t("agent_unnamed"), runs: row.runs };
  return { key: row.agent, display: row.agent, runs: row.runs };
}

function tiles(u, s) {
  return h("div", { class: "kpis" },
    kpi({ label: t("kpi_tokens"), value: fmtTokens(s.tokens), icon: "bars" }),
    kpi({ label: t("kpi_cost"), value: fmtCost(s.cost, s.unpriced_requests), icon: "coins", sub: u.est() }),
    kpi({ label: t("kpi_hit"), value: pct(s.hit_rate), icon: "cache", sub: h("span", { class: "kpi-def" }, t("hit_def")) }),
    kpi({ label: t("kpi_runs"), value: s.runs.toLocaleString("en-US"), icon: "agents" }));
}

function agentsCard(u, s, agents) {
  const cols = [t("h_agent"), t("h_runs"), t("kpi_tokens"), t("kpi_cost"), t("kpi_hit")];
  const rows = s.by_agent.map((row, i) => [
    h("a", { class: "lnk", href: u.hashFor("agent-detail", { agent: agents[i].key }) }, agents[i].display),
    agents[i].runs.toLocaleString("en-US"),
    fmtTokens(row.tokens),
    fmtCost(row.cost, row.unpriced_requests),
    pct(row.hit_rate),
  ]);
  return card({
    title: t("c_agents_in_session"), body: [table3(cols, rows), u.est()], icon: "agents", sub: t("q_agents_session"),
  });
}

function tokensCard(s, agents) {
  const rows = s.by_agent.map((row, i) => ({ label: agents[i].display, a: row }));
  return card({
    title: t("c_tokens_by_agent_session"), body: [stackedTokens(rows), kindsLegend(s)], icon: "bars", sub: t("q_where"),
  });
}

export function render(root, ctx) {
  clear(root);
  if (ctx.route.name !== "session-detail") return; // the route carries the parameters this page needs
  const id = ctx.route.params.id;
  const crumbs = [{ label: t("nav_sessions"), href: ctx.hashFor("sessions") }];
  root.appendChild(pageHead({ title: id, crumbs }));
  fillUsage(root, ctx, (u) => {
    clear(root);
    const s = findSession(u.payload, id);
    if (!s) return [pageHead({ title: id, crumbs }), emptyState(t("s_no_range_h"), t("s_no_range_longest_t"))];
    const agents = s.by_agent.map(agentOf);
    const intro = s.branch
      ? t("intro_session", { branch: s.branch, project: s.project })
      : t("intro_session_no_branch", { project: s.project });
    return [
      pageHead({ title: t("session_from", { time: fmtTime(s.started) }), intro, crumbs }),
      tiles(u, s),
      h("div", { class: "g2" }, agentsCard(u, s, agents), tokensCard(s, agents)),
    ];
  });
}
