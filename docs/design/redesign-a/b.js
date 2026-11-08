// Direction B, "Now feed": no sidebar. Three places in a top bar (Live, Review, Setup), Live reads as a sentence, then cards for who is working, then a feed of what happened.
function bTop(cur) {
  const t = (k, l, extra = "") => `<a href="#"${cur === k ? ' aria-current="page"' : ""}>${l}${extra}</a>`;
  return `<header class="b-top"><div class="b-top-in">
    <div class="brand"><span class="logo" aria-hidden="true">R</span><span class="hide-phone">${S.product}</span></div>
    <nav class="b-tabs" aria-label="Main">${t("live", S.nav_live, ' <span class="b-dot" aria-hidden="true">&#x25CF;</span>')}${t("review", S.nav_review)}${t("setup", S.nav_setup_h)}${t("tofix", S.nav_tofix, ` <span class="b-cnt">${S.tofix_count}</span>`)}</nav>
    <div class="b-tools"><button class="sel b-proj"><b>${S.project_name}</b></button><button class="btn hide-phone" aria-haspopup="menu">${S.nav_ref_h}</button></div>
  </div></header>`;
}
function bPage(cur, title, body) { document.title = `${title}, ${S.project_name}, ${S.product}`; return `<div class="b">${bTop(cur)}<main class="b-main" id="main">${body}</main></div>`; }

function bAgentCard(r, check) {
  const mins = Math.round(minOf("2026-10-30T18:40:00") - minOf(r.started));
  return `<article class="b-card ${mcls(r.model_display)}">
    <header><h3>${r.name}</h3>${st("working")}</header>
    <p class="b-mod">${sw(r.model_display)}${r.model_display} &middot; ${r.effort}</p>
    <p class="b-cost num">${money(r.cost)}</p>
    <dl class="b-facts"><div><dt>${S.t_tokens}</dt><dd class="num">${tok(r.tokens)}</dd></div><div><dt>${S.b_running_for}</dt><dd class="num">${mins} min</dd></div><div><dt>${S.tl_started_by}</dt><dd>${parentName(r) || "&#x2013;"}</dd></div></dl>
    ${check ? `<p class="b-flag">${st("lowered", "Lowered")}<span>${S.mc_judge_t}</span></p>` : ""}
  </article>`;
}

function bLive() {
  const t = LIVE.totals;
  const work = RUNS.filter((r) => r.state === "working"); const done = RUNS.filter((r) => r.state === "done");
  const f = (k, o) => S[k].replace(/\{(\w+)\}/g, (_, x) => o[x]);
  const ev = [
    ["6:39", "tech-writer", f("f_started_round", { by: "Main session", n: 2 }), "working"],
    ["6:30", "judge", f("f_started_by", { by: "deep-reasoner" }), "working"],
    ["6:28", "fast-worker 1", f("f_finished_cost", { cost: "$0.25" }), "done"],
    ["6:27", "fast-worker 2", f("f_finished_cost", { cost: "$0.23" }), "done"],
    ["6:24", "tech-writer", f("f_finished_round", { n: 1 }), "idle"],
    ["6:22", "fast-worker 1 and 2", f("f_started_together", { by: "deep-reasoner" }), "working"],
    ["6:20", "tech-writer", f("f_started_by", { by: "Main session" }), "working"],
    ["6:17", "scout 1 and 2", f("f_finished_under_each", { cost: "$0.01" }), "done"],
    ["6:14", "scout 1 and 2", f("f_started_together", { by: "deep-reasoner" }), "working"],
    ["6:12", "deep-reasoner", f("f_started_by", { by: "Main session" }), "working"],
  ];
  const mix = {}; RUNS.forEach((r) => mix[r.model_display] = (mix[r.model_display] || 0) + r.cost);
  return bPage("live", S.live_h1, `
  <section class="b-hero" aria-labelledby="hero">
    <div class="b-hero-l"><p class="b-state">${st("working")}<span class="muted">${S.live_updated}</span></p>
      <h1 id="hero">${S.b_hero}</h1><p class="sub">${S.b_hero_sub}</p>
      <div class="b-hero-ctl"><button class="sel"><span class="lab">${S.live_pick_label}</span><b>${S.live_pick_value}</b></button><button class="btn">${S.live_pause}</button></div></div>
    <div class="b-hero-r"><p class="b-big num">${money(t.cost)}</p><p class="muted">${S.b_spent}</p>
      <dl class="b-mini"><div><dt>${S.t_tokens}</dt><dd class="num">${tok(t.tokens)}</dd></div><div><dt>${S.t_cache}</dt><dd class="num">${pct(t.hit_rate)}</dd></div><div><dt>${S.b_last_min}</dt><dd class="num">$0.44</dd></div></dl></div>
  </section>
  <h2 class="b-h">${S.b_now_h} <span class="muted">${work.length}</span></h2>
  <div class="b-cards">${work.map((r) => bAgentCard(r, r.agent === "judge")).join("")}</div>
  <h2 class="b-h">${S.b_done_h} <span class="muted">${done.length}</span></h2>
  <ul class="b-done">${done.map((r) => `<li>${st("done")}<b>${r.name}</b><span class="muted">${sw(r.model_display)}${r.model_display}</span><span class="num">${money(r.cost)}</span></li>`).join("")}</ul>
  <div class="b-split">
    <section class="card"><header><h2>${S.b_feed_h}</h2><span class="q">${S.b_feed_q}</span></header>
      <ol class="b-feed">${ev.map((e) => `<li><time class="num">${e[0]}</time><span class="b-ev-mark ${e[3]}" aria-hidden="true"></span><span><b>${e[1]}</b> ${e[2]}</span></li>`).join("")}</ol></section>
    <div class="b-side">
      <section class="card"><header><h2>${S.b_rate_h}</h2></header>${stackBars(LIVE.minutes.map((m) => ({ by: m.by })), { h: 90, top: 80000, ticks: [[0, "0"], [80000, "80K"]], xl: [[0, "6:10"], [50, "6:25"], [100, S.tl_now]] })}</section>
      <section class="card"><header><h2>${S.b_mix_h}</h2></header><ul class="hb">${Object.entries(mix).map(([m, v]) => `<li><span class="hb-n">${sw(m)}${m}</span><span class="hb-bar"><i style="width:${v / 7.53 * 100}%"></i></span><span class="num hb-v">${money(v)}</span></li>`).join("")}</ul><p class="note">${S.cost_note}</p></section>
    </div>
  </div>`);
}

function bSummary() {
  const t = R.totals;
  return bPage("review", S.rv_h1, `
  <div class="b-rv-head"><h1>${S.rv_h1}</h1>
    <nav class="seg-tabs b-seg" aria-label="${S.nav_review}">${["summary", "sessions", "agents", "models"].map((k) => `<a href="#"${k === "summary" ? ' aria-current="page"' : ""}>${S["rv_tab_" + k]}</a>`).join("")}</nav>
    <button class="sel"><span class="lab">${S.rv_range_lab}</span><b>${S.rv_range}</b></button></div>
  <p class="b-lead">${S.b_review_lead}</p>
  <dl class="b-strip">
    <div><dt>${S.rv_t_cost}</dt><dd class="num">${money(t.cost)}</dd><dd class="muted">${S.rv_t_cost_d}</dd></div>
    <div><dt>${S.rv_t_sessions}</dt><dd class="num">${t.sessions}</dd><dd class="muted">${S.rv_t_sessions_d}</dd></div>
    <div><dt>${S.rv_t_tokens}</dt><dd class="num">${tok(t.tokens)}</dd><dd class="muted">${S.rv_t_tokens_d}</dd></div>
    <div><dt>${S.rv_t_cache}</dt><dd class="num">${pct(t.hit_rate)}</dd><dd class="muted">${S.rv_t_cache_d}</dd></div>
  </dl>
  <section class="card"><header><h2>${S.rv_day_h}</h2><span class="q">${S.rv_day_q}</span><span class="right">${modelLegend()}</span></header>${costPerDay(130)}</section>
  <div class="b-split" style="margin-top:var(--space-4)">
    <section class="card"><header><h2>${S.rv_top_h}</h2><span class="q">${S.rv_top_q}</span></header>${sessionTable(R.sessions.slice().sort((a, b) => b.cost - a.cost).slice(0, 5), false)}</section>
    <section class="card"><header><h2>${S.rv_who_h}</h2></header>${agentShare()}</section>
  </div>`);
}
