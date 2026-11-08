// Shared helpers and components for the three directions.
const Q = new URLSearchParams(location.search);
const D = Q.get("d") || "a", SCR = Q.get("s") || "live";
if (Q.get("theme")) document.documentElement.dataset.theme = Q.get("theme");

const money = (v) => v < 0.005 ? "<$0.01" : "$" + v.toFixed(2);
const tok = (v) => v >= 1e6 ? (v / 1e6).toFixed(v >= 1e8 ? 0 : 1) + "M" : v >= 1e3 ? Math.round(v / 1e3) + "K" : String(v);
const pct = (v) => Math.round(v * 100) + "%";
const mcls = (m) => (m || "").split(" ")[0].toLowerCase();
const sw = (m) => `<span class="sw ${mcls(m)}" aria-hidden="true"></span>`;
const st = (k, w) => `<span class="st ${k}">${w || S["st_" + k] || k}</span>`;
const esc = (s) => String(s);

// Time on the Live axis: 6:10 PM to 6:40 PM.
const T0 = 18 * 60 + 10, SPAN = 30;
const minOf = (iso) => { const [h, m, s] = iso.slice(11, 19).split(":").map(Number); return h * 60 + m + s / 60; };
const xp = (iso) => Math.max(0, Math.min(100, (minOf(iso) - T0) / SPAN * 100));
const clock = (iso) => { const [h, m] = iso.slice(11, 16).split(":").map(Number); return `${h > 12 ? h - 12 : h}:${String(m).padStart(2, "0")}`; };

function frac(r, cut) { const s = minOf(r.started), e = r.state === "working" ? T0 + SPAN : minOf(r.last_request); return Math.max(0, Math.min(1, (cut - s) / Math.max(0.1, e - s))); }
function runName(r) { return r.agent ? r.agent + (r.label_n ? " " + r.label_n : "") : "Main session"; }
function treeOrder(runs) {
  const out = []; const kids = (p) => runs.filter((r) => r.parent === p).sort((a, b) => a.dispatch_order - b.dispatch_order);
  const walk = (r, d) => { out.push({ ...r, depth: d, name: runName(r) }); kids(r.run_id).forEach((k) => walk(k, d + 1)); };
  kids(null).forEach((r) => walk(r, 0)); return out;
}
const RUNS = treeOrder(LIVE.runs);
const parentName = (r) => { const p = LIVE.runs.find((x) => x.run_id === r.parent); return p ? runName(p) : null; };

// Shell with a sidebar (A and C). items: [{h}|{k,label,ic,end,sub,cur}]
function sidebar(items, extra = "") {
  const nav = items.map((i) => i.h ? `<div class="navh">${i.h}</div>` :
    `<a class="nv${i.sub ? " sub" : ""}" href="#"${i.cur ? ' aria-current="page"' : ""}><span class="ic" aria-hidden="true">${i.ic || ""}</span>${i.label}${i.end || ""}</a>`).join("");
  return `<nav class="side" aria-label="Main">
    <div class="brand"><span class="logo" aria-hidden="true">R</span>${S.product}</div>
    <button class="proj" aria-label="${S.project_label}, ${S.project_name}"><small>${S.project_label}</small><b>${S.project_name}<span aria-hidden="true">&#x25BE;</span></b></button>
    ${nav}${extra}
    <div class="foot">${S.version}</div></nav>`;
}
function topbar(title) { return `<header class="topbar"><span class="pname">${title}</span><span class="proj-s">${S.project_name}</span></header>`; }
function tabbar(items) {
  return `<nav class="tabbar" aria-label="Main">${items.map((i) => `<a href="#"${i.cur ? ' aria-current="page"' : ""}><span class="ic" aria-hidden="true">${i.ic}</span>${i.label}${i.cnt ? `<span class="cnt">${i.cnt}<span class="sr"> to fix</span></span>` : ""}</a>`).join("")}</nav>`;
}

// Tiles
function tile(k, v, d, proof = "") { return `<div class="tile"><div class="k">${k}</div><div class="v num">${v}</div>${proof ? `<div class="proof" aria-hidden="true">${proof}</div>` : ""}<div class="d">${d}</div></div>`; }
function spark(vals) { const mx = Math.max(...vals); return `<div class="spark">${vals.map((v, i) => `<i${i === vals.length - 1 ? ' class="last"' : ""} style="height:${Math.max(4, v / mx * 100)}%"></i>`).join("")}</div>`; }
function kbar(t) { const s = t.cache_read + t.input + t.cache_write + t.output; return `<div class="kbar">${[t.cache_read, t.input, t.cache_write, t.output].map((v) => `<i style="width:${v / s * 100}%"></i>`).join("")}</div>`; }
function dots(on, ok) { return `<div class="dots">${Array.from({ length: on }, () => '<i class="on"></i>').join("")}${Array.from({ length: ok }, () => '<i class="ok"></i>').join("")}</div>`; }
function ring(p) { return `<div class="ring" style="--p:${p}"></div>`; }

const MODELS = ["Opus 5.5", "Sonnet 5.5", "Haiku 5.5", "Fable 5.1"];
// Stacked HTML bars, bars[i] = {label, by:{model:val}}; axis labels in HTML.
function stackBars(bars, { h = 120, top, ticks = [], xl = [], cls = "" } = {}) {
  const mx = top || Math.max(...bars.map((b) => Object.values(b.by).reduce((a, c) => a + c, 0)));
  const cols = bars.map((b) => `<div class="sb-col">${MODELS.filter((m) => b.by[m]).map((m) => `<i class="${mcls(m)}" style="height:${b.by[m] / mx * 100}%"></i>`).join("")}</div>`).join("");
  return `<div class="sb ${cls}" style="--h:${h}px"><div class="sb-y">${ticks.map((t) => `<span style="bottom:${t[0] / mx * 100}%">${t[1]}</span>`).join("")}</div>
    <div class="sb-plot">${ticks.map((t) => `<b style="bottom:${t[0] / mx * 100}%"></b>`).join("")}<div class="sb-cols">${cols}</div></div>
    <div class="sb-x">${xl.map((x) => `<span style="left:${x[0]}%">${x[1]}</span>`).join("")}</div></div>`;
}

// The Live timeline: lanes in tree order on one time axis, with the per-minute bars on the same axis.
function timeline({ at = null, compact = false } = {}) {
  const cutoff = at ? T0 + at : null;
  const mins = LIVE.minutes.map((m) => ({ by: m.by }));
  const xl = [[0, "6:10"], [16.7, "6:15"], [33.3, "6:20"], [50, "6:25"], [66.7, "6:30"], [83.3, "6:35"], [100, S.tl_now]];
  const lanes = RUNS.map((r) => {
    let state = r.state, segs = r.rounds.map((rd) => [xp(rd.started), r.state === "working" && rd === r.rounds[r.rounds.length - 1] ? 100 : xp(rd.last_request)]);
    if (cutoff) { const cx = (cutoff - T0) / SPAN * 100; segs = segs.filter((s) => s[0] < cx).map((s) => [s[0], Math.min(s[1], cx)]); state = !segs.length ? "idle" : segs.some((s) => s[1] >= cx - 0.5) ? "working" : "done"; }
    const open = state === "working"; const notyet = state === "idle" && cutoff;
    const guides = Array.from({ length: r.depth }, (_, i) => `<span class="g" style="left:${i * 16 + 7}px"></span>`).join("");
    const label = `<div class="ln-lab" style="padding-left:${r.depth * 16}px">${guides}<span class="ln-name">${r.name}</span><span class="ln-mod">${sw(r.model_display)}${r.model_display} &middot; ${r.effort}</span></div>`;
    const bars = segs.map((s, i) => `<span class="seg ${mcls(r.model_display)}${open && i === segs.length - 1 ? " open" : ""}" style="left:${s[0]}%;width:${Math.max(0.8, s[1] - s[0])}%"></span>${i > 0 ? `<span class="rnd" style="left:${s[0]}%">${S.tl_round2}</span>` : ""}`).join("");
    const srt = `${r.name}, ${r.model_display} ${r.effort}, started ${clock(r.started)}${r.parent ? " by " + parentName(r) : ""}, ${state}, ${tok(r.tokens)} tokens, ${money(r.cost)}`;
    return `<li class="ln${state === "idle" ? " future" : ""}"><span class="sr">${srt}</span><div aria-hidden="true" class="ln-row">${label}<div class="ln-track">${bars}</div>
      <div class="ln-end"><span class="ln-st">${notyet ? st("idle", S.c_not_started) : st(state)}<small class="muted">${cutoff ? "" : laneAge(r)}</small></span>${notyet ? `<span class="num ln-tok">&#x2013;</span><span class="num ln-cost">&#x2013;</span>` : `<span class="num ln-tok">${tok(cutoff ? Math.round(r.tokens * frac(r, cutoff)) : r.tokens)}</span><span class="num ln-cost">${money(cutoff ? r.cost * frac(r, cutoff) : r.cost)}</span>`}</div></div></li>`;
  }).join("");
  const top = 80000;
  return `<div class="tl${compact ? " compact" : ""}">
    <div class="tl-head" aria-hidden="true"><div class="ln-lab tl-axlab">${S.tl_axis_lab}<div class="legend">${MODELS.slice(0, 3).map((m) => `<span>${sw(m)}${m}</span>`).join("")}</div></div>
      <div class="tl-bars">${cutoff ? `<div class="tl-fade" style="left:${(cutoff - T0) / SPAN * 100}%"></div>` : ""}${stackBars(mins.map((m) => ({ by: m.by })), { h: 64, top, ticks: [[40000, "40K"], [80000, "80K"]], xl })}</div><div class="ln-end"></div></div>
    <ul class="tl-lanes" aria-label="${S.tl_h}">${lanes}</ul>
    ${cutoff ? `<div class="tl-cut" style="--x:${(cutoff - T0) / SPAN * 100}%" aria-hidden="true"></div>` : ""}
  </div>`;
}

function laneAge(r) {
  if (r.state !== "working") return S.tl_ran.replace("{n}", Math.max(1, Math.round(minOf(r.last_request) - minOf(r.rounds[r.rounds.length - 1].started))));
  const s = Math.round((minOf("2026-10-30T18:39:52") - minOf(r.last_request)) * 60); return S.tl_last.replace("{n}", s);
}
function modelCheckLive() {
  return `<div class="chk-hit"><div class="chk-t">${st("lowered", "Lowered")}<b>${S.mc_judge_t}</b></div><p class="muted">${S.mc_judge_why}</p><a class="btn" href="#">${S.mc_open}</a></div>
    <p class="chk-ok">${st("in-effect", "In effect")}<span>${S.mc_ok}</span></p>`;
}
function requestsTable(n = 6) {
  return `<table class="t"><thead><tr><th>${S.rq_time}</th><th>${S.rq_agent}</th><th class="hp">${S.rq_model}</th><th class="r">${S.rq_tokens}</th><th class="r">${S.rq_cost}</th></tr></thead><tbody>
  ${LIVE.requests.slice(0, n).map((q) => `<tr><td class="num">${(q.ts.slice(0, 2) - 12) + q.ts.slice(2)}</td><td>${q.agent}</td><td class="hp">${sw(q.model)}${q.model} &middot; ${q.effort}</td><td class="r num">${tok(q.tokens)}</td><td class="r num">${money(q.cost)}</td></tr>`).join("")}</tbody></table>`;
}

// Review data helpers
const R = REV;
const dayBars = () => R.days.map((d) => { const tot = Object.values(d.by).reduce((a, c) => a + c, 0) || 1; const share = d.tokens ? 1 : 0; return { by: d.by }; });
const tpl = (k, o) => S[k].replace(/\{(\w+)\}/g, (_, x) => o[x]);
// Cost per day by model for the fixture window (October 1 to 30), from tokens scaled to each model's 30-day cost.
function octCostBars() {
  const tokByModel = {}; R.days.forEach((d) => Object.entries(d.by).forEach(([m, v]) => tokByModel[m] = (tokByModel[m] || 0) + v));
  const rate = {}; R.models.forEach((m) => rate[m.display_name] = m.cost / (tokByModel[m.display_name] || 1));
  return R.days.map((d) => { const by = {}; Object.entries(d.by).forEach(([m, v]) => by[m] = v * (rate[m] || 0)); return { by }; });
}
// MADE-UP for the mock: September 1 to 30, the October days rotated by 9 and scaled to the fixture's previous-30-day cost ($234.52).
function sepCostBars() {
  const oct = octCostBars(); const f = R.previous.cost / R.totals.cost;
  return oct.map((_, i) => { const src = oct[(i + 9) % 30].by; const by = {}; Object.entries(src).forEach(([m, v]) => by[m] = v * f); return { by }; });
}
const WIN = {
  oct: { start: "October 1", end: "October 30", bars: octCostBars, xl: [[0, "Oct 1"], [33.3, "Oct 11"], [66.7, "Oct 21"], [100, "Oct 30"]] },
  sep: { start: "September 1", end: "September 30", bars: sepCostBars, xl: [[0, "Sep 1"], [33.3, "Sep 11"], [66.7, "Sep 21"], [100, "Sep 30"]] },
};
function costPerDay(h = 150, w = "oct") {
  const bars = WIN[w].bars();
  const top = 40;
  return stackBars(bars, { h, top, ticks: [[0, "$0"], [20, "$20"], [40, "$40"]], xl: WIN[w].xl });
}
function windowTotals(w) { const t = {}; WIN[w].bars().forEach((b) => Object.entries(b.by).forEach(([m, v]) => t[m] = (t[m] || 0) + v)); return t; }
function pager(w) {
  const newest = w === "oct";
  const prev = newest ? `<button class="btn pg" aria-label="${tpl("pg_prev_aria", { start: WIN.sep.start, end: WIN.sep.end })}"><span aria-hidden="true">&#x2190;</span> ${S.pg_prev}</button>`
    : `<button class="btn pg" aria-disabled="true" aria-describedby="pg-why"><span aria-hidden="true">&#x2190;</span> ${S.pg_prev}</button>`;
  const next = newest ? `<button class="btn pg" aria-disabled="true" aria-describedby="pg-why">${S.pg_next} <span aria-hidden="true">&#x2192;</span></button>`
    : `<button class="btn pg" aria-label="${tpl("pg_next_aria", { start: WIN.oct.start, end: WIN.oct.end })}">${S.pg_next} <span aria-hidden="true">&#x2192;</span></button>`;
  const why = newest ? S.pg_next_none : tpl("pg_prev_none", { date: "September 1" });
  return `<div class="pager">${prev}<b class="pg-win num" aria-live="polite">${tpl("pg_window", { start: WIN[w].start, end: WIN[w].end })}</b>${next}
    <span class="pg-why muted" id="pg-why">${why}</span>${newest ? "" : `<a class="btn quiet" href="#">${S.pg_newest}</a>`}</div>`;
}
function modelLegend(w = "oct") { const t = windowTotals(w); return `<div class="legend">${R.models.map((m) => `<span>${sw(m.display_name)}${m.display_name} <b class="num">${money(t[m.display_name] || 0)}</b></span>`).join("")}</div>`; }
function agentShare() {
  const tot = R.totals.cost; const rows = R.agents.slice().sort((a, b) => b.cost - a.cost);
  return `<ul class="hb">${rows.map((a) => `<li><span class="hb-n">${a.name}<small class="muted">${sw(a.ran[0][0])}${a.ran[0][0]}</small></span><span class="hb-bar"><i class="mfill ${mcls(a.ran[0][0])}" style="width:${a.cost / rows[0].cost * 100}%"></i></span><span class="num hb-v">${money(a.cost)}</span><span class="num muted hb-p">${a.cost / tot < 0.01 ? "<1%" : pct(a.cost / tot)}</span></li>`).join("")}</ul>`;
}
const CHECK = {
  builder: { s: "overridden", w: "Overridden", t: S.mc_ex_builder, set: "Fable 5.1 &middot; xhigh" },
  "Main session": { s: "lowered", w: "Lowered", t: S.mc_ex_main, set: "Opus 5.5 &middot; xhigh" },
  reviewer: { s: "overridden", w: "Overridden", t: S.mc_ex_reviewer, set: "Sonnet 5.5 &middot; high" },
  scribe: { s: "overridden", w: "Overridden", t: S.mc_ex_scribe, set: "Haiku 4.5 &middot; medium" },
};
function sessionName(s) { const d = new Date(s.started); const h = d.getHours(), m = d.getMinutes(); return `${h > 12 ? h - 12 : h}:${String(m).padStart(2, "0")} ${h >= 12 ? "PM" : "AM"}`; }
function dayName(s) { return new Date(s.started).toLocaleDateString("en-US", { month: "long", day: "numeric" }); }
