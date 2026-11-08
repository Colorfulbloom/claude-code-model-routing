// Direction A, "Timeline": Live is home. Review is a lens over a range or one session, with Summary, Sessions, Agents, Models.
function aNav(cur) {
  const it = (k, label, ic, o = {}) => ({ k, label, ic, cur: cur === k, ...o });
  return sidebar([
    it("live", S.nav_live, "&#x25C9;", { end: `<span class="live-dot"><span aria-hidden="true">&#x25CF;</span>${S.nav_working}</span>` }),
    { h: S.nav_review },
    it("summary", S.nav_summary, "&#x25A4;"), it("sessions", S.nav_sessions, "&#x2630;"), it("agents", S.nav_agents, "&#x263A;"), it("models", S.nav_models, "&#x25C8;"),
    { h: S.nav_setup_h },
    it("setup", S.nav_setup, "&#x2699;"), it("tofix", S.nav_tofix, "&#x25B3;", { end: `<span class="end">${S.tofix_count}</span>` }),
    { h: S.nav_ref_h },
    it("decides", S.nav_decides, "&#x2318;"), it("glossary", S.nav_glossary, "&#x2261;"),
  ]);
}
function aTabs(cur) {
  const rv = ["summary", "sessions", "agents", "models", "session"].includes(cur);
  return tabbar([{ ic: "&#x25C9;", label: S.nav_live, cur: cur === "live" }, { ic: "&#x25A4;", label: S.nav_review, cur: rv },
    { ic: "&#x2699;", label: S.nav_setup_h, cur: cur === "setup" }, { ic: "&#x25B3;", label: S.nav_tofix, cnt: S.tofix_count }, { ic: "&#x2261;", label: S.nav_more }]);
}
function aPage(cur, title, body) {
  document.title = `${title}, ${S.project_name}, ${S.product}`;
  return `<div class="shell a">${aNav(cur)}<div>${topbar(title)}<main class="main" id="main">${body}</main></div></div>${aTabs(cur)}`;
}

function aLive() {
  const t = LIVE.totals, lm = LIVE.last_minute;
  const costMin = LIVE.minutes.map((m) => m.tokens);
  return aPage("live", S.live_h1, `
  <div class="ph lv-head">
    <div><div class="lv-state">${st("working")}<h1>${LIVE.branch}</h1></div><p class="sub">${S.live_session_where}</p></div>
    <div class="right"><button class="sel" aria-label="${S.live_pick_label}"><span class="lab">${S.live_pick_label}</span><b>${S.live_pick_value}</b></button>
      <span class="muted upd" role="status">${S.live_updated}</span><button class="btn">${S.live_pause}</button></div>
  </div>
  <div class="tiles">
    ${tile(S.t_cost, money(t.cost), S.t_cost_d, spark(costMin))}
    ${tile(S.t_tokens, tok(t.tokens), S.t_tokens_d)}
    ${tile(S.t_cache, pct(t.hit_rate), S.t_cache_d, ring(t.hit_rate))}
    ${tile(S.t_agents, "4", S.t_agents_d, dots(4, 4))}
  </div>
  <section class="card"><header><h2>${S.tl_h}</h2><span class="q">${S.tl_q}</span></header>${timeline()}<p class="note">${S.tl_note}</p></section>
  <div class="grid two" style="margin-top:var(--space-4)">
    <section class="card"><header><h2>${S.mc_h}</h2><span class="q">${S.mc_q}</span></header>${modelCheckLive()}</section>
    <section class="card"><header><h2>${S.rq_h}</h2><span class="q">${S.rq_q}</span></header><div class="well">${requestsTable(5)}</div><p class="note">${S.cost_note}</p></section>
  </div>`);
}

function scopeBar(session, title) {
  return `<div class="ph rv-head"><div><h1>${title || S.rv_h1}</h1><p class="sub">${session ? S.rv_still : S.rv_range_sub}</p></div>
    <div class="right">${session
      ? `<a class="btn quiet" href="#">&#x2190; ${S.rv_back}</a><button class="sel"><span class="lab">${S.rv_session_scope}</span><b>${S.rv_session_value}</b></button><a class="btn" href="#">${S.rv_open_live}</a>`
      : `<button class="sel"><span class="lab">${S.rv_range_lab}</span><b>${S.rv_range}</b></button>`}</div></div>`;
}
function rvTabs(cur) {
  return `<nav class="seg-tabs only-phone" aria-label="${S.nav_review}">${["summary", "sessions", "agents", "models"].map((k) => `<a href="#"${cur === k ? ' aria-current="page"' : ""}>${S["rv_tab_" + k]}</a>`).join("")}</nav>`;
}

function aSummaryEarlier() { return aSummary("sep"); }
function aSummary(w = "oct") {
  const t = R.totals;
  const top = R.sessions.slice().sort((a, b) => b.cost - a.cost).slice(0, 4);
  const chk = R.agents.filter((a) => CHECK[a.name]);
  return aPage("summary", S.nav_summary, `${scopeBar(false, S.nav_summary)}${rvTabs("summary")}
  <div class="tiles">
    ${tile(S.rv_t_cost, money(t.cost), S.rv_t_cost_d)}
    ${tile(S.rv_t_sessions, t.sessions, S.rv_t_sessions_d)}
    ${tile(S.rv_t_tokens, tok(t.tokens), S.rv_t_tokens_d)}
    ${tile(S.rv_t_cache, pct(t.hit_rate), S.rv_t_cache_d)}
  </div>
  <section class="card"><header><h2>${S.rv_day_h}</h2><span class="q">${S.rv_day_q}</span></header><div class="chart-bar">${pager(w)}${modelLegend(w)}</div>${w === "oct" ? "" : `<p class="pg-note">${tpl("pg_scope_note", { range: S.rv_range.toLowerCase() })}</p>`}<div class="well">${costPerDay(140, w)}</div><p class="note">${S.cost_note}${w === "oct" ? "" : ` <span class="mock">Mock data, September is made up</span>`}</p></section>
  <div class="grid two" style="margin-top:var(--space-4)">
    <section class="card"><header><h2>${S.rv_who_h}</h2><span class="q">${S.rv_who_q}</span></header><div class="well">${agentShare()}</div></section>
    <section class="card"><header><h2>${S.rv_chk_h}</h2><span class="q">${S.rv_chk_sum}</span></header>
      <ul class="chk-list">${chk.map((a) => `<li>${st(CHECK[a.name].s, CHECK[a.name].w)}<span>${CHECK[a.name].t}</span></li>`).join("")}</ul></section>
  </div>
  <section class="card" style="margin-top:var(--space-4)"><header><h2>${S.rv_top_h}</h2><span class="q">${S.rv_top_q}</span><a class="right btn quiet" href="#">${S.rv_all_sessions} &#x2192;</a></header>
    <div class="well">${sessionTable(top, false)}</div></section>`);
}

function sessionTable(rows, group) {
  let last = "";
  const max = Math.max(...rows.map((s) => s.cost));
  return `<table class="t ss"><thead><tr><th>${S.ss_col_session}</th><th class="hp">${S.ss_col_agents}</th><th class="r hp">${S.ss_col_runs}</th><th class="r hp">${S.ss_col_tokens}</th><th class="r">${S.ss_col_cost}</th></tr></thead><tbody>
  ${rows.map((s) => { const dn = dayName(s); const gh = group && dn !== last ? `<tr class="grp"><th colspan="5" scope="colgroup">${dn}</th></tr>` : ""; last = dn;
    return `${gh}<tr><td><a href="#">${group ? sessionName(s) : dn + ", " + sessionName(s)}</a><div class="muted small">${s.branch}</div></td><td class="hp">${s.agents.map((a) => `<span class="badge">${a}</span>`).join(" ")}</td><td class="r num hp">${s.runs}</td><td class="r num hp">${tok(s.tokens)}</td>
      <td class="r"><div class="share"><span class="num">${money(s.cost)}</span><span class="bar hide-phone"><i style="width:${s.cost / max * 100}%"></i></span></div></td></tr>`; }).join("")}</tbody></table>`;
}

function aSessions() {
  const live = `<tr class="live-row"><td><a href="#">6:10 PM</a> ${st("working")}<div class="muted small">${LIVE.branch}</div></td><td class="hp">${["deep-reasoner", "judge", "tech-writer", "fast-worker", "scout"].map((a) => `<span class="badge">${a}</span>`).join(" ")}</td><td class="r num hp">8</td><td class="r num hp">${tok(LIVE.totals.tokens)}</td><td class="r"><div class="share"><span class="num">${money(LIVE.totals.cost)}</span><span class="bar hide-phone"><i style="width:${LIVE.totals.cost / 10.05 * 100}%"></i></span></div></td></tr>`;
  return aPage("sessions", S.nav_sessions, `${scopeBar(false, S.nav_sessions)}${rvTabs("sessions")}
  <section class="card"><header><h2>${S.ss_h}</h2><span class="q">53</span></header>
  <div class="well">${sessionTable(R.sessions.slice(0, 9), true).replace("<tbody>", `<tbody><tr class="grp"><th colspan="5" scope="colgroup">${S.ss_today}</th></tr>${live}`).replace(`<tr class="grp"><th colspan="5" scope="colgroup">October 30</th></tr>`, "")}</div>
  </section>`);
}

function aAgents() {
  const rows = R.agents.slice().sort((a, b) => b.cost - a.cost); const max = rows[0].cost;
  const src = { builder: S.ag_src_project, reviewer: S.ag_src_project, scribe: S.ag_src_user, "Main session": S.ag_main_src };
  const none = [["migrator", "Opus 5.5", "high", S.ag_src_project], ["release-notes", "Sonnet 5.5", "medium", S.ag_src_user], ["linter", "Haiku 5.5", "low", S.ag_src_plugin]];
  return aPage("agents", S.nav_agents, `${scopeBar(false, S.nav_agents)}${rvTabs("agents")}
  <section class="card"><header><h2>${S.ag_h}</h2><span class="q">${S.ag_q}</span></header>
  <div class="well"><table class="t ag"><thead><tr><th>${S.ag_col_agent}</th><th class="hp">${S.ag_col_set}</th><th class="hp">${S.ag_col_ran}</th><th>${S.ag_col_check}</th><th class="r hp">${S.ag_col_runs}</th><th class="r">${S.ag_col_cost}</th></tr></thead><tbody>
  ${rows.map((a) => `<tr><td><a href="#">${a.name}</a><div class="muted small">${src[a.name]}</div></td><td class="hp">${CHECK[a.name].set}</td><td class="hp">${sw(a.ran[0][0])}${a.ran[0][0]} &middot; ${a.ran[0][1]}</td><td>${st(CHECK[a.name].s, CHECK[a.name].w)}</td><td class="r num hp">${a.runs || a.sessions}</td>
    <td class="r"><div class="share"><span class="num">${money(a.cost)}</span><span class="bar hide-phone"><i style="width:${a.cost / max * 100}%"></i></span></div></td></tr>`).join("")}
  <tr class="grp"><th colspan="6" scope="colgroup">${S.ag_none_h}</th></tr>
  ${none.map((n) => `<tr class="none"><td><a href="#">${n[0]}</a><div class="muted small">${n[3]}</div></td><td class="hp">${n[1]} &middot; ${n[2]}</td><td class="hp muted">&#x2014;</td><td class="muted">&#x2014;</td><td class="r num hp muted">0</td><td class="r num muted">$0.00</td></tr>`).join("")}
  </tbody></table></div></section>`.replace(/&#x2014;/g, '<span aria-label="none">&#x2013;</span>'));
}

function aModels() {
  const ms = R.models.slice().sort((a, b) => b.cost - a.cost); const max = ms[0].cost;
  const kinds = [["cache_read", S.k_cache_read], ["input", S.k_input], ["cache_write", S.k_cache_write], ["output", S.k_output]];
  const tk = R.cost_by_kind;
  return aPage("models", S.nav_models, `${scopeBar(false, S.nav_models)}${rvTabs("models")}
  <section class="card"><header><h2>${S.md_h}</h2><span class="q">${S.md_q}</span></header>
  <div class="well"><table class="t md"><thead><tr><th>${S.md_col_model}</th><th class="r">${S.md_col_cost}</th><th class="hp">${S.md_col_share}</th><th class="r hp">${S.md_col_tokens}</th><th class="r hp">${S.md_col_cache}</th><th class="hp">${S.md_col_used}</th></tr></thead><tbody>
  ${ms.map((m) => `<tr><td><a href="#">${sw(m.display_name)}${m.display_name}</a></td><td class="r num">${money(m.cost)}</td><td class="hp"><div class="share" style="justify-content:flex-start"><span class="bar"><i class="mfill ${mcls(m.display_name)}" style="width:${m.cost / max * 100}%"></i></span><span class="num muted">${m.share_pct < 1 ? "<1" : m.share_pct}%</span></div></td><td class="r num hp">${tok(m.tokens)}</td><td class="r num hp">${pct(m.hit_rate)}</td><td class="hp">${m.agents.map((a) => `<span class="badge">${a}</span>`).join(" ")}</td></tr>`).join("")}
  </tbody></table></div><p class="note">${S.cost_note}</p></section>
  <section class="card" style="margin-top:var(--space-4)"><header><h2>${S.md_kind_h}</h2><span class="q">${S.md_kind_q}</span></header>
    <div class="legend kl">${kinds.map((k, i) => `<span><i class="kp kp${i + 1}" aria-hidden="true"></i>${k[1]} <b class="num">${money(tk[k[0]])}</b></span>`).join("")}</div><p class="note kl-note">${S.kind_legend_note}</p>
    <div class="well"><ul class="kind-rows">${ms.map((m) => { const s = Object.values(m.cost_by_kind).reduce((a, c) => a + c, 0); return `<li><span class="kn">${sw(m.display_name)}${m.display_name}</span><span class="kstack ${mcls(m.display_name)}" style="width:${Math.max(2, m.cost / max * 100)}%">${kinds.map((k, i) => `<i class="kp kp${i + 1}" style="width:${m.cost_by_kind[k[0]] / s * 100}%"></i>`).join("")}</span><span class="num kv">${money(m.cost)}</span><span class="kparts muted">${kinds.slice().sort((a, b) => m.cost_by_kind[b[0]] - m.cost_by_kind[a[0]]).map((k) => `${k[1]} ${money(m.cost_by_kind[k[0]])}`).join(", ")}</span></li>`; }).join("")}</ul></div>
  </section>`);
}

function aSession() {
  const t = LIVE.totals;
  return aPage("session", S.nav_sessions, `${scopeBar(true)}
  <div class="tiles">
    ${tile(S.rv_t_cost, money(t.cost), S.rv_whole)}${tile(S.t_tokens, tok(t.tokens), S.rv_whole)}${tile(S.t_cache, pct(t.hit_rate), S.rv_whole)}${tile(S.ss_col_runs, "8", S.rv_runs_d)}
  </div>
  <section class="card"><header><h2>${S.rv_tl_h}</h2><span class="q">${S.c_at}</span><a class="right btn" href="#">${S.c_back_now}</a></header>${timeline({ at: 15 })}<p class="note">${S.rv_replay_note}</p></section>`);
}
