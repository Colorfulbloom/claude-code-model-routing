// Direction C, "Session map": sessions sit in the sidebar like a mail list. Live is the newest session's map. Any past session opens the same map with a replay strip.
function cNav(cur) {
  const it = (k, label, ic, o = {}) => ({ k, label, ic, cur: cur === k, ...o });
  const sess = [[`6:10 PM`, LIVE.branch, "working", cur === "live"], ...R.sessions.slice(0, 6).map((s) => [dayName(s).replace("October", "Oct") + ", " + sessionName(s), money(s.cost), null, false])];
  const list = `<div class="navh">${S.c_sessions_h}</div><ul class="c-sess">${sess.map((s, i) => `<li><a href="#"${i === 0 ? ' aria-current="page"' : ""}><span>${i === 0 ? st("working") : ""}<b>${s[0]}</b></span><small class="muted">${s[1]}</small></a></li>`).join("")}</ul><a class="nv" href="#"><span class="ic"></span>${S.rv_all_sessions}</a>`;
  return sidebar([it("summary", S.nav_summary, "&#x25A4;"), it("agents", S.nav_agents, "&#x263A;"), it("models", S.nav_models, "&#x25C8;"),
    it("setup", S.nav_setup, "&#x2699;"), it("tofix", S.nav_tofix, "&#x25B3;", { end: `<span class="end">${S.tofix_count}</span>` }), it("ref", S.nav_decides, "&#x2318;")], list);
}
function cPage(cur, title, body) {
  document.title = `${title}, ${S.project_name}, ${S.product}`;
  return `<div class="shell c">${cNav(cur)}<div>${topbar(title)}<main class="main c-main" id="main">${body}</main></div></div>
  ${tabbar([{ ic: "&#x25C9;", label: S.nav_live, cur: cur === "live" }, { ic: "&#x2630;", label: S.nav_sessions, cur: cur === "session" }, { ic: "&#x263A;", label: S.nav_agents }, { ic: "&#x25C8;", label: S.nav_models }, { ic: "&#x2261;", label: S.nav_more, cnt: S.tofix_count }])}`;
}

// Leaf-row layout for the map
function mapLayout() {
  let row = 0; const pos = {};
  const place = (r) => { const kids = RUNS.filter((k) => k.parent === r.run_id); pos[r.run_id] = { col: r.depth, row }; if (!kids.length) row++; else kids.forEach(place); };
  RUNS.filter((r) => !r.parent).forEach(place); return { pos, rows: row };
}
function cMap(at) {
  const cut = at ? T0 + at : null; const { pos, rows } = mapLayout();
  const cards = RUNS.map((r) => {
    let state = r.state;
    if (cut) { const s = minOf(r.started), e = r.state === "working" ? 1e9 : minOf(r.last_request); state = s > cut ? "idle" : e < cut ? "done" : "working"; }
    const sel = r.agent === "deep-reasoner";
    const p = pos[r.run_id];
    return `<button class="c-node ${state === "idle" ? "future" : ""}${sel ? " picked" : ""}" data-id="${r.run_id}" data-parent="${r.parent || ""}" style="grid-column:${p.col + 1};grid-row:${p.row + 1};--d:${r.depth}" aria-pressed="${sel}">
      <span class="c-n1"><b>${r.name}</b>${state === "idle" ? `<span class="st idle">${S.c_not_started}</span>` : st(state)}</span>
      <span class="c-n2">${sw(r.model_display)}${r.model_display} &middot; ${r.effort}</span>
      <span class="c-n3 num"><span>${tok(cut ? Math.round(r.tokens * frac(r, cut)) : r.tokens)}</span><b>${money(cut ? r.cost * frac(r, cut) : r.cost)}</b></span></button>`;
  }).join("");
  return `<div class="c-map" style="--rows:${rows}"><svg class="c-wires" aria-hidden="true"></svg>${cards}</div>`;
}
function cReplay(at) {
  const x = at ? at / SPAN * 100 : 100;
  return `<div class="c-replay"><div class="c-rp-lab"><b>${S.c_replay}</b><span class="muted">${at ? S.c_at : S.c_replay_hint}</span>${at ? `<a class="btn" href="#">${S.c_back_now}</a>` : ""}</div>
    <div class="c-rp-track">${at ? `<div class="tl-fade" style="left:${x}%"></div>` : ""}${stackBars(LIVE.minutes.map((m) => ({ by: m.by })), { h: 44, top: 80000, ticks: [], xl: [[0, "6:10"], [50, "6:25"], [100, S.tl_now]] })}
    <div class="c-handle" style="left:${x}%" role="slider" tabindex="0" aria-label="${S.c_replay}" aria-valuetext="${at ? "6:25 PM" : S.tl_now}"></div></div></div>`;
}
function cInspector(at) {
  const r = RUNS.find((x) => x.agent === "deep-reasoner"); const kids = RUNS.filter((k) => k.parent === r.run_id);
  return `<aside class="c-insp" aria-label="${r.name}">
    <header><h2>${r.name}</h2>${st("working")}</header>
    <p class="muted">${S.tl_started_by} Main session, ${clock(r.started)} PM</p>
    <dl class="c-kv"><div><dt>${S.rv_t_cost}</dt><dd class="num">${money(r.cost)}</dd></div><div><dt>${S.t_tokens}</dt><dd class="num">${tok(r.tokens)}</dd></div><div><dt>${S.c_requests}</dt><dd class="num">46</dd></div></dl>
    <h3>${S.mc_h}</h3><p class="c-chk">${st("in-effect", "In effect")}<span>${sw("Opus 5.5")}${S.c_as_set}</span></p>
    <h3>${S.c_kids.replace("{n}", kids.length)}</h3>
    <ul class="c-kids">${kids.map((k) => `<li><span>${k.name}</span>${st(k.state)}<span class="num">${money(k.cost)}</span></li>`).join("")}</ul>
    <a class="btn" href="#">${S.mc_open}</a>
  </aside>`;
}
function cBody(at) {
  const t = at ? { cost: RUNS.reduce((a, r) => a + r.cost * frac(r, T0 + at), 0), tokens: RUNS.reduce((a, r) => a + r.tokens * frac(r, T0 + at), 0), hit_rate: 0.77 } : LIVE.totals;
  return `<div class="ph"><div><div class="lv-state">${at ? `<span class="st idle">${S.c_at}</span>` : st("working")}<h1>${LIVE.branch}</h1></div><p class="sub">${S.live_session_where}</p></div>
    <div class="right"><span class="c-inline num"><b>${money(t.cost)}</b> <span class="muted">${S.t_cost.toLowerCase()}</span></span><span class="c-inline num"><b>${tok(t.tokens)}</b> <span class="muted">${S.t_tokens.toLowerCase()}</span></span><span class="c-inline num"><b>${pct(t.hit_rate)}</b> <span class="muted">${S.t_cache.toLowerCase()}</span></span>${at ? "" : `<button class="btn">${S.live_pause}</button>`}</div></div>
  <div class="c-stage"><section class="card c-mapcard"><header><h2>${S.c_map_h}</h2><span class="q">${S.c_map_q}</span></header>${cMap(at)}${cReplay(at)}</section>${cInspector(at)}</div>`;
}
function cLive() { return cPage("live", S.live_h1, cBody(null)); }
function cSession() { return cPage("session", S.nav_sessions, cBody(15)); }

window.after = function () {
  document.querySelectorAll(".c-map").forEach((map) => {
    const svg = map.querySelector(".c-wires"); const mb = map.getBoundingClientRect();
    if (getComputedStyle(svg).display === "none") return;
    svg.setAttribute("width", mb.width); svg.setAttribute("height", mb.height);
    let d = "";
    map.querySelectorAll(".c-node[data-parent]").forEach((n) => {
      const pid = n.dataset.parent; if (!pid) return; const p = map.querySelector(`.c-node[data-id="${pid}"]`); if (!p) return;
      const a = p.getBoundingClientRect(), b = n.getBoundingClientRect();
      const x1 = a.right - mb.left, y1 = a.top - mb.top + 22, x2 = b.left - mb.left, y2 = b.top - mb.top + 22, xm = x2 - 14;
      d += `M${x1} ${y1} H${xm} V${y2} H${x2} `;
    });
    svg.innerHTML = `<path d="${d}" fill="none" stroke="var(--border-strong)" stroke-width="1.5"/>`;
  });
};
