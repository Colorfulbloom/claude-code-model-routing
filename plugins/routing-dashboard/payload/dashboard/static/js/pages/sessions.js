// Sessions. Ported from `sessions_page` in gen3.py (screen 05). It shows the first 10 rows of the view's
// sessions, newest first as the server sends them, and a Show all button that expands to the full list the
// payload already holds, so it fetches nothing. All projects adds a Project column after Session.
// Branch, agent names and the project are data, so they go in as text and never as markup.

import { h, clear } from "../h.js";
import { t, fmtTokens, fmtCost, fmtTime } from "../format.js";
import { ALL_KEY } from "../router.js";
import { pageHead, rangeControl, card, table3, inline } from "../components.js";
import { fillUsage } from "../usage-page.js";

const SHORT_LIST = 10;

// The project and range whose list is expanded, as one string. It lives here, not in a render, so a redraw
// keeps the list open. A different project or range gives a different string, so that view starts short.
let expanded = "";

// The link in row 11, the first row Show all reveals. The button that held focus is gone after the redraw.
let firstRevealed = null;

function sessionRow(u, s, all) {
  const agents = Array.isArray(s.agents) ? s.agents : [];
  const row = [
    fmtTime(s.started),
    h("a", { class: "lnk", href: u.hashFor("session-detail", { id: s.session_id }) }, t("session_from", { time: fmtTime(s.started) })),
  ];
  if (all) row.push(s.project);
  row.push(
    s.branch ? h("span", { class: "mono" }, s.branch) : h("span", { class: "muted" }, t("no_branch")),
    agents.length ? inline(s.runs, agents.join(", ")) : h("span", { class: "muted" }, t("none_spawned")),
    fmtTokens(s.tokens),
    fmtCost(s.cost, s.unpriced_requests));
  return row;
}

export function render(root, ctx) {
  clear(root);
  firstRevealed = null;
  root.appendChild(pageHead({ title: t("nav_sessions"), intro: t("intro_sessions"), right: rangeControl(ctx.range, ctx.setRange) }));
  fillUsage(root, ctx, (u) => {
    const all = u.project.key === ALL_KEY;
    const sessions = u.view.sessions;
    const total = sessions.length;
    const mark = u.project.key + "|" + u.range;
    const open = expanded === mark;
    const shown = open ? sessions : sessions.slice(0, SHORT_LIST);
    const cols = [t("h_started"), t("h_session")];
    if (all) cols.push(t("h_project"));
    cols.push(t("h_branch"), t("h_agents_spawned"), t("kpi_tokens"), t("kpi_cost"));
    const rows = shown.map((s) => sessionRow(u, s, all));
    if (rows.length > SHORT_LIST) firstRevealed = rows[SHORT_LIST][1]; // the Session cell of row 11
    const table = table3(cols, rows);
    let more = null;
    if (!open && total > SHORT_LIST) {
      const hidden = total - SHORT_LIST;
      const text = hidden === 1 ? t("more_sessions_1") : t("more_sessions", { n: hidden.toLocaleString("en-US") });
      const button = h("button", {
        class: "btn",
        type: "button",
        on: {
          click: () => {
            expanded = mark;
            render(root, ctx);
            if (firstRevealed) firstRevealed.focus();
          },
        },
      }, t("sessions_show_all", { n: total.toLocaleString("en-US") }));
      more = h("p", { class: "at-more" }, text, " ", button);
    }
    return card({ title: t("c_sessions_table"), body: [table, more, u.est()], icon: "session" });
  });
}
