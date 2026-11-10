// M3 Review passes 7 to 9 (designer boards, November 9). Builds on a.js, ui.js, m2.js helpers. Prefix m3 everywhere.
const f3 = (k, o = {}) => (S3[k] || k).replace(/\{(\w+)\}/g, (_, x) => (o[x] !== undefined ? o[x] : "{" + x + "}"));
const NOW_T = "6:41 PM";
const M3_ANN = (t) => `<p class="m2-ann m3-ann" aria-hidden="true">${t}</p>`;
const money0 = (v) => v >= 1000 ? "$" + Math.round(v).toLocaleString("en-US") : money(v);
const pctS = (a) => (a < 0.01 ? "<1%" : pct(a));

// ---------- Daily cost by model and kind, September 3 to October 30 ----------
const KIND_KEYS = ["cache_write", "output", "input", "cache_read"]; // biggest first in the fixture
const KIND_PAT = { cache_read: 1, input: 2, cache_write: 3, output: 4 }; // kp classes, as Models
const KMIX = {}; R.models.forEach((m) => { const s = Object.values(m.cost_by_kind).reduce((a, c) => a + c, 0); KMIX[m.display_name] = Object.fromEntries(Object.entries(m.cost_by_kind).map(([k, v]) => [k, v / s])); });
const OCTB = octCostBars(), SEPB = sepCostBars();
const DAYS3 = [...SEPB.slice(2).map((b, i) => ({ d: new Date(2026, 8, 3 + i), by: b.by })), ...OCTB.map((b, i) => ({ d: new Date(2026, 9, 1 + i), by: b.by }))];
const dkey = (d) => d.getMonth() * 100 + d.getDate();
const DMAP = Object.fromEntries(DAYS3.map((x) => [dkey(x.d), x.by]));
const addBy = (a, b) => { Object.entries(b || {}).forEach(([m, v]) => (a[m] = (a[m] || 0) + v)); return a; };
const sumOf = (by) => Object.values(by).reduce((a, c) => a + c, 0);
const mdy = (d, o = { month: "long", day: "numeric" }) => d.toLocaleDateString("en-US", o);
const daysBack = (n) => new Date(2026, 9, 30 - n);
// Today by hour: work hours 9 to 6, $14.20 so far, the 6 PM hour still open.
const HOURW = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0.6, 1.1, 1.3, 0.5, 0.9, 1.4, 1.2, 0.8, 1.0, 0.45];
const TODAY_COST = 14.2;
function m3HourBars() {
  const tw = HOURW.reduce((a, c) => a + c, 0), mix = { "Fable 5.1": 0.7, "Opus 5.5": 0.24, "Sonnet 5.5": 0.055, "Haiku 5.5": 0.005 };
  const bars = Array.from({ length: 24 }, (_, h) => { if (h >= HOURW.length || !HOURW[h]) return { by: {}, future: h >= HOURW.length }; const by = {}; Object.entries(mix).forEach(([m, f]) => (by[m] = TODAY_COST * HOURW[h] / tw * f * (h % 3 === 1 && m === "Opus 5.5" ? 1.5 : 1))); return { by, open: h === 18 }; });
  const k = TODAY_COST / bars.reduce((a, b) => a + sumOf(b.by), 0); bars.forEach((b) => Object.keys(b.by).forEach((m) => (b.by[m] *= k)));
  return bars;
}
function m3DayBars(n, end = 0) { return Array.from({ length: n }, (_, i) => ({ by: { ...(DMAP[dkey(daysBack(end + n - 1 - i))] || {}) } })); }
function m3WeekBars(n) { return Array.from({ length: n }, (_, i) => { const by = {}; for (let j = 0; j < 7; j++) addBy(by, DMAP[dkey(daysBack((n - 1 - i) * 7 + j))]); return { by, start: daysBack((n - 1 - i) * 7 + 6) }; }); }
function m3MonthBars() { return Array.from({ length: 12 }, (_, i) => { const mo = (10 + i) % 12, by = {}; DAYS3.forEach((x) => { if (x.d.getMonth() === mo && i >= 10) addBy(by, x.by); }); return { by, open: i === 11 }; }); }
const totalBy = (bars) => bars.reduce((a, b) => addBy(a, b.by), {});

// ---------- Ranges ----------
const T30 = R.totals, P30 = R.previous;
const ALL_COST = sumOf(totalBy(DAYS3)), ALL_DAYS = DAYS3.length;
const deltaPct = (v, p) => { const c = (v - p) / p; return Math.abs(c) < 0.02 ? f3("t_same", { v: "before" }) : f3(c > 0 ? "t_up" : "t_down", { p: Math.round(Math.abs(c) * 100) + "%", v: "{v}" }); };
const RG = {
  today: { lab: S3.rg_today, win: f3("rg_w_today", { time: NOW_T }), sub: f3("sub_today", { time: NOW_T }), unit: "hour" },
  "7d": { lab: S3.rg_7d, win: f3("rg_w_span", { start: "October 24", end: "October 30" }), sub: f3("sub_span", { start: "October 24", end: "October 30", n: 7 }), unit: "day" },
  "30d": { lab: S3.rg_30d, win: f3("rg_w_span", { start: "October 1", end: "October 30" }), sub: f3("sub_span", { start: "October 1", end: "October 30", n: 30 }), unit: "day" },
  "90d": { lab: S3.rg_90d, win: f3("rg_w_span", { start: "August 2", end: "October 30" }), sub: f3("sub_short", { start: "August 2", end: "October 30", date: "September 3" }), unit: "week" },
  "12m": { lab: S3.rg_12m, win: f3("rg_w_span", { start: "October 31, 2025", end: "October 30, 2026" }), sub: f3("sub_short", { start: "October 31, 2025", end: "October 30, 2026", date: "September 3" }), unit: "month" },
  all: { lab: S3.rg_all, win: f3("rg_w_all", { date: "September 3" }), sub: f3("sub_all", { date: "September 3" }), unit: "week" },
};
const RG_ORDER = ["today", "7d", "30d", "90d", "12m", "all"];

// ---------- Page shell ----------
function m3Page(cur, title, body, o = {}) {
  let h = aPage(cur, title, body);
  h = h.replace(`<div class="brand">${S.product}</div>`, `<div class="brand">${S.product}<span class="badge m2-demo">${S2.demo}</span></div>`)
    .replace(`<span class="pname">${title}</span>`, `<span class="pname">${title}</span><span class="badge m2-demo">${S2.demo}</span>`)
    .replace('class="shell a"', 'class="shell a m2 m3"').replace(/<button class="proj" aria-haspopup="listbox" aria-expanded="false" aria-label="[^"]*">/, '<button class="proj" aria-haspopup="listbox" aria-expanded="false">');
  return h + (o.after || "");
}
function rangeSel(k, open) { return `<button class="sel m3-sel${open ? " is-open" : ""}" aria-haspopup="listbox" aria-expanded="${!!open}"><span class="lab">${S3.rg_h}</span><b>${RG[k].lab}</b></button>`; }
function m3Scope(title, k, o = {}) {
  return `<div class="ph m2-ph m3-ph"><div class="m2-tt"><h1>${title}</h1><p class="sub">${o.sub || RG[k].sub}</p></div><div class="right">${rangeSel(k, o.open)}</div></div>`;
}
function rangePop(k) {
  const li = RG_ORDER.map((r) => `<li role="option" aria-selected="${r === k}"${r === k ? ' class="on"' : ""}><span class="pk-n">${RG[r].lab}</span>${r === k ? '<span class="ok" aria-hidden="true">&#x2713;</span>' : ""}<span class="pk-p m3-rw">${RG[r].win}</span></li>`).join("");
  return `<div class="pk-scrim only-phone" aria-hidden="true"></div><div class="pk-pop m3-pop" role="dialog" aria-labelledby="rg-h"><header class="pk-h"><h2 id="rg-h">${S3.rg_h}</h2><button class="btn quiet x only-phone" aria-label="${S.ed_close}"><span aria-hidden="true">&#x2715;</span></button></header><ul class="pk-list" role="listbox" aria-labelledby="rg-h">${li}</ul></div>`;
}

// ---------- Tiles ----------
function rvTiles(t, o = {}) {
  if (o.loading) return `<div class="tiles" aria-busy="true">${[S3.t_cost_kx, 1, 2, 3].map((_, i) => `<div class="tile m2-tile"><div class="k">${[S.rv_t_cost, S.rv_t_sessions, S.rv_t_tokens, S.rv_t_cache][i]}</div><span class="bone big" aria-hidden="true"></span><div class="d"><span class="bone" style="width:70%" aria-hidden="true"></span></div></div>`).join("")}</div>`;
  return `<div class="tiles">
    ${m2Tile(S.rv_t_cost, t.cost, t.costD, { kx: S3.t_cost_kx, d2: t.unpriced ? f3("t_unpriced", { n: t.unpriced }) : "" })}
    ${m2Tile(S.rv_t_sessions, t.sessions, t.sessD)}
    ${m2Tile(S.rv_t_tokens, t.tokens, t.tokD)}
    ${m2Tile(S.rv_t_cache, t.cache, t.cacheD)}</div>`;
}
function tilesFor(k, o = {}) {
  if (k === "30d") return { cost: money(o.unpriced ? T30.cost - 7.22 : T30.cost), costD: f3("t_up", { p: o.unpriced ? "33%" : "36%", v: money(P30.cost) }), unpriced: o.unpriced ? 12 : 0, sessions: 53, sessD: f3("t_up_n", { v: 38 }), tokens: tok(T30.tokens), tokD: f3("t_up", { p: "34%", v: tok(P30.tokens) }), cache: pct(T30.hit_rate), cacheD: f3("t_same", { v: pct(P30.hit_rate) }) };
  if (k === "7d") { const c = sumOf(totalBy(m3DayBars(7))), p = sumOf(totalBy(m3DayBars(7, 7))); return { cost: money(c), costD: f3(c > p ? "t_up" : "t_down", { p: Math.round(Math.abs(c - p) / p * 100) + "%", v: money(p) }), sessions: 13, sessD: f3("t_up_n", { v: 11 }), tokens: "27.4M", tokD: f3("t_up", { p: "12%", v: "24.5M" }), cache: "79%", cacheD: f3("t_up_pt", { p: 2, v: "77%" }) }; }
  if (k === "today") return { cost: money(TODAY_COST), costD: f3("t_yday", { v: "$12.68", time: NOW_T }), sessions: 3, sessD: f3("t_yday", { v: 2, time: NOW_T }), tokens: "4.9M", tokD: f3("t_yday", { v: "4.4M", time: NOW_T }), cache: "81%", cacheD: f3("t_yday", { v: "79%", time: NOW_T }) };
  // 90d, 12m and all: the store starts September 3, so there's no prior window.
  return { cost: money(ALL_COST), costD: f3("t_avg_cost", { v: money(ALL_COST / ALL_DAYS) }), sessions: 89, sessD: f3("t_avg_sessions", { v: "1.5" }), tokens: "198M", tokD: f3("t_avg_tokens", { v: "3.4M" }), cache: "78%", cacheD: S3.t_avg_cache };
}

// ---------- Cost chart (pass 8) ----------
function dTicks(mx) { const raw = mx / 2, p = Math.pow(10, Math.floor(Math.log10(raw))); const step = [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw); return { top: step * 2, ticks: [step, step * 2] }; }
function m3Chart(bars, o) {
  const { top, ticks } = dTicks(Math.max(...bars.map((b) => sumOf(b.by))));
  const n = bars.length;
  const col = (b, i) => {
    if (o.cut !== undefined && i >= o.cut && sumOf(b.by)) return `<div class="m3-col fut"><i style="height:${sumOf(b.by) / top * 100}%"></i></div>`;
    const segs = MODELS.filter((m) => b.by[m]).map((m) => {
      const h = b.by[m] / top * 100;
      if (!o.pattern) return `<i class="${mcls(m)}" style="height:${h}%"></i>`;
      return `<i class="${mcls(m)} m3-kst" style="height:${h}%">${KIND_KEYS.slice().reverse().map((k) => `<b class="kp kp${KIND_PAT[k]}" style="flex:${KMIX[m][k]}"></b>`).join("")}</i>`;
    }).join("");
    return `<div class="m3-col${b.open ? " open" : ""}${b.unp ? " unp" : ""}">${segs}${b.unp ? `<span class="m3-unp" style="height:${b.unp / top * 100}%"></span>` : ""}</div>`;
  };
  const norec = o.norec ? `<div class="m3-norec" style="--w:${o.norec / n}"><span>${f3("ch_norec", { date: "September 3" })}</span></div>` : "";
  const now = o.now !== undefined ? `<div class="m3-nowl" style="--p:${o.now / 100}"><span>${S3.ch_now}</span></div>` : "";
  return `<div class="m3-ch${n > 26 ? " dense" : ""}" style="--h:${o.h || 150}px" role="img" aria-label="${o.aria || ""}">
    <div class="m2-plot m3-plot">${ticks.map((t) => `<b style="bottom:${t / top * 100}%"><span>${money0(t).replace(".00", "")}</span></b>`).join("")}<b class="m3-zero" style="bottom:0"><span>$0</span></b>${norec}<div class="m3-cols">${bars.map(col).join("")}</div>${now}</div>
    <div class="m2-x m3-x">${o.xl.map((x) => `<span class="${x[2] ? "" : "dk"}" style="left:${x[0]}%">${x[1]}</span>`).join("")}</div></div>`;
}
function m3Legend(bars, o = {}) {
  const t = totalBy(bars);
  return `<div class="legend m3-leg">${MODELS.filter((m) => t[m]).map((m) => `<span>${sw(m)}${m} <b class="num">${o.least === m ? f3("ch_legend_least", { v: money(t[m]) }) : money0(t[m])}</b></span>`).join("")}</div>`;
}
function kindsTotals(bars) { const t = totalBy(bars), k = {}; Object.entries(t).forEach(([m, v]) => KIND_KEYS.forEach((kk) => (k[kk] = (k[kk] || 0) + v * KMIX[m][kk]))); return k; }
function kindsLine(bars, pattern) {
  const k = kindsTotals(bars), names = { cache_read: S.k_cache_read, input: S.k_input, cache_write: S.k_cache_write, output: S.k_output };
  const items = KIND_KEYS.map((kk) => `<span>${pattern ? `<i class="kp kp${KIND_PAT[kk]}" aria-hidden="true"></i>` : ""}${names[kk]} <b class="num">${money0(k[kk])}</b></span>`).join("");
  return pattern ? `<div class="legend kl m3-kl">${items}</div>` : `<p class="m3-kline"><span class="muted">${S3.ch_kinds}</span> ${items}<a href="#" class="m3-klink">${S3.ch_kinds_link}</a></p>`;
}
function m3Pager(p) {
  const prev = p.prevEnd ? `<button class="btn pg" aria-disabled="true" aria-describedby="pg-why"><span aria-hidden="true">&#x2190;</span> ${S.pg_prev}</button>` : `<button class="btn pg" aria-label="${f3("ch_prev_aria", { window: p.prevWin })}"><span aria-hidden="true">&#x2190;</span> ${S.pg_prev}</button>`;
  const next = p.nextEnd ? `<button class="btn pg" aria-disabled="true" aria-describedby="pg-why">${S.pg_next} <span aria-hidden="true">&#x2192;</span></button>` : `<button class="btn pg" aria-label="${f3("ch_next_aria", { window: p.nextWin })}">${S.pg_next} <span aria-hidden="true">&#x2192;</span></button>`;
  const why = p.prevEnd ? f3("ch_none_earlier", { date: "September 3" }) : S3.ch_none_later;
  return `<div class="pager m3-pager">${prev}<b class="pg-win num" aria-live="polite">${p.win}</b>${next}<span class="pg-why muted" id="pg-why">${why}</span>${p.newest ? `<a class="btn quiet" href="#">${S.pg_newest}</a>` : ""}</div>`;
}
// x labels sit under bar centres; the first and last align to the plot edges.
const xc = (n, l) => l.map(([i, t, k]) => [i === 0 ? 0 : i === n - 1 ? 100 : (i + 0.5) / n * 100, t, k]);
const XL = {
  hour: xc(24, [[0, "12 AM", 1], [6, "6 AM"], [12, "12 PM", 1], [18, "6 PM"], [23, "11 PM", 1]]),
  d7: xc(7, [[0, "Oct 24", 1], [1, "Oct 25"], [2, "Oct 26"], [3, "Oct 27", 1], [4, "Oct 28"], [5, "Oct 29"], [6, "Oct 30", 1]]),
  d30: xc(30, [[0, "Oct 1", 1], [10, "Oct 11"], [15, "Oct 16", 1], [20, "Oct 21"], [29, "Oct 30", 1]]),
  w13: xc(13, [[0, "Aug 2", 1], [4, "Aug 30"], [6, "Sep 13", 1], [8, "Sep 27"], [12, "Oct 24", 1]]),
  m12: xc(12, [[0, "Nov 2025", 1], [3, "Feb"], [6, "May 2026", 1], [9, "Aug"], [11, "Oct", 1]]),
  all: xc(9, [[0, "Sep 3", 1], [4, "Sep 26", 1], [8, "Oct 24", 1]]),
};
// One chart spec per range: bars, x labels, pager, window.
function chartSpec(k, o = {}) {
  if (k === "today") return { bars: m3HourBars(), xl: XL.hour, now: (18 + 41 / 60) / 24 * 100, pager: { win: f3("ch_win_today", { time: NOW_T }), prevWin: "October 29", nextEnd: true }, aria: "Cost per hour today by model" };
  if (k === "7d") return { bars: m3DayBars(7), xl: XL.d7, pager: { win: f3("ch_win_span", { start: "October 24", end: "October 30" }), prevWin: "October 17 to October 23", nextEnd: true } };
  if (k === "90d") return { bars: m3WeekBars(13), xl: XL.w13, norec: 4.4, pager: { win: f3("ch_win_span", { start: "August 2", end: "October 30" }), prevEnd: true, nextEnd: true } };
  if (k === "12m") return { bars: m3MonthBars(), xl: XL.m12, norec: 10.1, pager: { win: f3("ch_win_span", { start: "November 2025", end: "October 2026" }), prevEnd: true, nextEnd: true } };
  if (k === "all") { const b = m3WeekBars(9).map((x, i) => (i === 0 ? { by: x.by } : x)); return { bars: b, xl: XL.all, pager: null }; }
  if (k === "all-months") return { bars: m3MonthBars().slice(10), xl: [[0, "Sep", 1], [100, "Oct", 1]], pager: null };
  if (k === "sep") return { bars: SEPB, xl: xc(30, [[0, "Sep 1", 1], [10, "Sep 11"], [15, "Sep 16", 1], [20, "Sep 21"], [29, "Sep 30", 1]]), norec: 2, pager: { win: f3("ch_win_span", { start: "September 1", end: "September 30" }), prevEnd: true, nextWin: "October 1 to October 30", newest: true } };
  return { bars: OCTB.map((b, i) => (o.unpriced && i >= 28 ? { by: { ...b.by, "Fable 5.1": b.by["Fable 5.1"] * (i === 29 ? 0.55 : 0.9) }, unp: b.by["Fable 5.1"] * (i === 29 ? 0.45 : 0.1) } : b)), xl: XL.d30, pager: { win: f3("ch_win_span", { start: "October 1", end: "October 30" }), prevWin: "September 1 to September 30", nextEnd: true } };
}
const UNIT_H = { hour: S3.ch_h_hour, day: S3.ch_h_day, week: S3.ch_h_week, month: S3.ch_h_month };
function costCard(k, o = {}) {
  const sp = chartSpec(o.win || k, o), unit = o.unit || RG[k].unit;
  const h = UNIT_H[unit];
  if (o.loading) return `<section class="card m3-cc" aria-busy="true"><header><h2>${h}</h2><span class="q">${S3.ch_q}</span></header><span class="sr">${f3("ld_line", { card: h.toLowerCase() })}</span><div class="m3-bar-row" aria-hidden="true"><span class="bone" style="width:96px;height:32px"></span><span class="bone" style="width:180px"></span><span class="bone" style="width:96px;height:32px"></span></div><div class="legend" aria-hidden="true">${[120, 110, 110, 100].map((w) => `<span class="bone" style="width:${w}px"></span>`).join("")}</div><div class="well m3-bones-chart" aria-hidden="true">${Array.from({ length: 30 }, (_, i) => `<i style="height:${20 + ((i * 37) % 60)}%"></i>`).join("")}</div></section>`;
  if (o.error) return `<section class="card m3-cc"><header><h2>${h}</h2><span class="q">${S3.ch_q}</span></header>${errFinding(h)}</section>`;
  const legend = m3Legend(sp.bars, { least: o.unpriced ? "Fable 5.1" : null });
  const note = `${o.unpriced ? `<p class="m3-unpl">${f3("ch_unpriced", { n: 12, model: "Fable 5.1" })}</p>` : ""}<p>${f3("foot_est", { date: "October 28" })}</p>${o.disagree ? `<p class="fwarn"><span aria-hidden="true" class="wm">&#x25B2;</span>${f3("foot_disagree", { model: "Opus 5.5" })}</p>` : ""}`;
  return `<section class="card m3-cc"><header><h2>${h}</h2><span class="q">${S3.ch_q}</span></header>
    <div class="chart-bar m3-chbar">${sp.pager ? m3Pager(sp.pager) : ""}${legend}</div>${o.scopeNote ? `<p class="pg-note">${tpl("pg_scope_note", { range: "the last 30 days" })}</p>` : ""}
    <div class="well m3-chw">${m3Chart(sp.bars, { xl: sp.xl, now: sp.now, norec: sp.norec, pattern: o.pattern, h: o.h, aria: sp.aria || h })}</div>
    ${o.pattern ? kindsLine(sp.bars, true) : kindsLine(sp.bars, false)}<div class="m2-rqf m3-foot">${note}</div></section>`;
}
function errFinding(card) { return `<div class="raised err m3-err" role="alert"><h3><span aria-hidden="true" class="errm">&#x2715;</span>${f3("er_h", { card: card.toLowerCase() })}</h3><p>${S3.er_b}</p><div><button class="btn">${S3.er_try}</button></div></div>`; }

// ---------- Summary lower cards ----------
const AG3 = (() => {
  const a = Object.fromEntries(R.agents.map((x) => [x.name, x]));
  return [
    { name: "builder", src: S.ag_src_project, model: "Fable 5.1", cost: a.builder.cost - 1.07, runs: 79, set: "Fable 5.1 &middot; xhigh", ran: "Fable 5.1 &middot; medium", s: "overridden", w: "Overridden", t: S.mc_ex_builder },
    { name: "Main session", src: S.ag_main_src, model: "Opus 5.5", cost: a["Main session"].cost, runs: 53, set: "Opus 5.5 &middot; xhigh", ran: "Opus 5.5 &middot; high", s: "lowered", w: "Lowered", t: S.mc_ex_main },
    { name: "reviewer", src: S.ag_src_project, model: "Sonnet 5.5", cost: a.reviewer.cost, runs: 31, set: "Sonnet 5.5 &middot; high", ran: "Sonnet 5.5 &middot; xhigh", also: ["Sonnet 5.5 &middot; high", 4], s: "overridden", w: "Overridden", t: S.mc_ex_reviewer },
    { name: S3.ag_unnamed, src: S3.ag_src_unnamed, model: "Fable 5.1", cost: 1.07, runs: 3, set: null, ran: "Fable 5.1 &middot; medium", s: "default", w: S.st_default },
    { name: "scribe", src: S.ag_src_user, model: "Haiku 5.5", cost: a.scribe.cost - 0.05, runs: 22, set: "Haiku 4.5 &middot; medium", ran: "Haiku 5.5 &middot; medium", s: "overridden", w: "Overridden", t: S.mc_ex_scribe },
    { name: "Explore", src: S3.ag_src_none, model: "Haiku 5.5", cost: 0.05, runs: 2, set: null, ran: "Haiku 5.5 &middot; low", s: "default", w: S.st_default },
  ];
})();
function moneyCard(o = {}) {
  const tot = AG3.reduce((a, x) => a + x.cost, 0), mx = AG3[0].cost, f = o.scale || 1;
  const body = o.loading ? `<ul class="hb" aria-hidden="true">${[1, 2, 3, 4].map(() => `<li><span class="bone" style="width:100px"></span><span class="bone" style="width:100%;height:12px"></span><span class="bone" style="width:60px"></span><span class="bone" style="width:30px"></span></li>`).join("")}</ul>`
    : `<ul class="hb m3-hb">${AG3.map((a) => `<li><span class="hb-n">${a.name}<small class="muted">${sw(a.model)}${a.model}</small></span><span class="hb-bar"><i class="mfill ${mcls(a.model)}" style="width:${Math.max(0.6, a.cost / mx * 100)}%"></i></span><span class="num hb-v">${o.unpriced && a.name === "builder" ? `<span class="m2-cleast">${f2("c_least", { cost: `<b>${money(a.cost * f - 7.22)}</b>` })}</span>` : money(a.cost * f)}</span><span class="num muted hb-p">${pctS(a.cost / tot)}</span></li>`).join("")}</ul>`;
  return `<section class="card"${o.loading ? ' aria-busy="true"' : ""}><header><h2>${S.rv_who_h}</h2><span class="q">${S.rv_who_q}</span></header>${o.loading ? `<span class="sr">${f3("ld_line", { card: S.rv_who_h.toLowerCase() })}</span>` : ""}<div class="well">${body}</div></section>`;
}
function checkCard(o = {}) {
  const hits = AG3.filter((a) => a.t);
  if (o.error) return `<section class="card"><header><h2>${S.rv_chk_h}</h2><span class="q">${S.rv_chk_q}</span></header>${errFinding(S.rv_chk_h)}</section>`;
  return `<section class="card"${o.loading ? ' aria-busy="true"' : ""}><header><h2>${S.rv_chk_h}</h2><span class="q">${o.loading ? S.rv_chk_q : f3("mc_sum_n", { n: hits.length, m: hits.length })}</span></header>
    ${o.loading ? `<ul class="chk-list" aria-hidden="true">${[1, 2, 3].map(() => `<li><span class="bone" style="width:96px;height:20px"></span><span class="bone" style="width:80%"></span></li>`).join("")}</ul>` : `<ul class="chk-list">${hits.map((a) => `<li>${st(a.s, a.w)}<span>${a.t}</span></li>`).join("")}</ul>`}</section>`;
}
const TODAY_SESS = [{ day: "October 30", time: "6:10 PM", running: true, branch: "feature/quarter-close", agents: ["deep-reasoner", "judge", "tech-writer", "fast-worker", "scout"], runs: 8, tokens: 2.9e6, cost: 8.28 },
  { day: "October 30", time: "9:02 AM", running: true, branch: "feature/quarter-close", agents: ["builder", "scribe"], runs: 26, tokens: 1.6e6, cost: 4.71 }, { day: "October 30", time: "7:48 AM", branch: "fix/ledger-rounding", agents: ["reviewer"], runs: 2, tokens: 0.4e6, cost: 1.21 }];
function topCard(o = {}) {
  const top = o.today ? TODAY_SESS : R.sessions.slice().sort((a, b) => b.cost - a.cost).slice(0, 4);
  return `<section class="card" style="margin-top:var(--space-4)"${o.loading ? ' aria-busy="true"' : ""}><header><h2>${S.rv_top_h}</h2><span class="q">${S.rv_top_q}</span><a class="right btn quiet" href="#">${f3("top_all", { n: o.n || 53 })} <span aria-hidden="true">&#x2192;</span></a></header>
    <div class="well">${o.loading ? boneTable(4) : m3SessTable(top, { group: false, today: o.today })}</div></section>`;
}
const boneTable = (n) => `<div class="m3-bones-t" aria-hidden="true">${Array.from({ length: n }, () => `<div><span class="bone" style="width:160px"></span><span class="bone" style="width:120px"></span><span class="bone" style="width:40px"></span><span class="bone" style="width:70px"></span></div>`).join("")}</div>`;

// ---------- Summary ----------
function m3Summary(k = "30d", o = {}) {
  const t = tilesFor(k, o);
  const scale = k === "today" ? TODAY_COST / T30.cost : k === "7d" ? 0.24 : ["90d", "12m", "all"].includes(k) ? ALL_COST / T30.cost : 1;
  const body = `${m3Scope(S.nav_summary, k, { open: o.open })}${rvTabs("summary")}
    ${rvTiles(t, o)}
    ${costCard(k, { ...o, error: o.errorChart, loading: o.loading })}
    <div class="grid two" style="margin-top:var(--space-4)">${moneyCard({ ...o, scale })}${checkCard({ ...o, error: o.errorCheck })}</div>
    ${topCard({ ...o, today: k === "today", n: k === "today" ? 3 : ["90d", "12m", "all"].includes(k) ? 89 : k === "7d" ? 13 : 53 })}`;
  return m3Page("summary", S.nav_summary, body, { after: o.open ? rangePop(k) : "" });
}
function m3Empty() {
  const body = `${m3Scope(S.nav_summary, "today")}${rvTabs("summary")}<section class="card m2-empty">${emptyMark()}<h2>${S3.em_h}</h2><p class="muted">${S3.em_b}</p><div class="m2-acts"><a class="btn primary" href="#">${S3.em_a}</a><a class="btn" href="#">${S3.em_live}</a></div></section>`;
  return m3Page("summary", S.nav_summary, body).replace(/<span class="live-dot">.*?<\/span><\/span>/, "");
}

// ---------- Sessions ----------
function m3SessTable(rows, o = {}) {
  let last = "";
  const max = Math.max(...rows.map((s) => s.cost));
  const lab = (dn) => (dn === "October 30" ? S3.ss_today : dn === "October 29" ? S3.ss_yday : dn);
  return `<table class="t ss m3-ss"><thead><tr><th>${S.ss_col_session}</th><th class="hp">${S.ss_col_agents}</th><th class="r hp">${S.ss_col_runs}</th><th class="r hp">${S.ss_col_tokens}</th><th class="r">${S.ss_col_cost}</th></tr></thead><tbody>
  ${rows.map((s) => { const dn = s.day || dayName(s); const gh = o.group && dn !== last ? `<tr class="grp"><th colspan="5" scope="colgroup">${lab(dn)}</th></tr>` : ""; last = dn;
    return `${gh}<tr${s.running ? ' class="live-row"' : ""}><td><a href="#">${o.group || o.today ? (s.time || sessionName(s)) : dn + ", " + sessionName(s)}</a>${s.running ? " " + rs("working") : ""}<div class="muted small">${s.branch}</div></td><td class="hp">${s.agents.map((a) => `<span class="badge">${a}</span>`).join(" ")}</td><td class="r num hp">${s.runs}</td><td class="r num hp">${tok(s.tokens)}</td>
      <td class="r"><div class="share"><span class="num">${money(s.cost)}</span><span class="bar hide-phone"><i style="width:${s.cost / max * 100}%"></i></span></div></td></tr>`; }).join("")}</tbody></table>`;
}
function m3Sessions(o = {}) {
  const run = { running: true, day: "October 30", time: "6:10 PM", branch: LIVE.branch, agents: ["deep-reasoner", "judge", "tech-writer", "fast-worker", "scout"], runs: 8, tokens: LIVE.totals.tokens, cost: LIVE.totals.cost };
  const rows = [run, ...R.sessions.slice().sort((a, b) => b.started.localeCompare(a.started)).slice(0, o.all ? 52 : 49)];
  const foot = o.all ? `<p class="m3-pgfoot muted">${f3("ss_page", { a: 53, n: 53 })}</p>` : `<div class="m3-pgfoot"><span class="muted">${f3("ss_page", { a: 50, n: 53 })}</span><button class="btn">${f3("ss_more", { n: 3 })}</button></div>`;
  const body = o.loading ? `<div class="well" aria-busy="true"><span class="sr">${f3("ld_line", { card: "sessions" })}</span>${boneTable(8)}</div>` : o.error ? errFinding(S.ss_h) : `<div class="well">${m3SessTable(rows, { group: true })}</div>${foot}<div class="m2-rqf m3-foot"><p>${f3("foot_est", { date: "October 28" })}</p></div>`;
  return m3Page("sessions", S.nav_sessions, `${m3Scope(S.nav_sessions, "30d")}${rvTabs("sessions")}
  <section class="card"><header><h2>${S.ss_h}</h2><span class="q num">53</span></header>${body}</section>`);
}

// ---------- Agents (usage half) ----------
function m3Agents(o = {}) {
  const max = AG3[0].cost, tot = AG3.reduce((a, x) => a + x.cost, 0);
  const none = [["migrator", "Opus 5.5 &middot; high", S.ag_src_project], ["release-notes", "Sonnet 5.5 &middot; medium", S.ag_src_user]];
  const dash = `<span class="muted" aria-label="none">&#x2013;</span>`;
  const rows = AG3.map((a) => `<tr><td><span class="m3-an">${a.name}</span><div class="muted small">${a.src}</div></td><td class="hp">${a.set || `<span class="muted">${S3.ag_nothing}</span>`}</td><td class="hp">${sw(a.model)}${a.ran}${a.also ? `<div class="muted small">${f3("ag_also", { setup: a.also[0], n: a.also[1] })}</div>` : ""}</td><td>${st(a.s, a.w)}</td><td class="r num hp">${a.runs}</td>
    <td class="r"><div class="share"><span class="num">${money(a.cost)}</span><span class="bar hide-phone"><i class="mfill ${mcls(a.model)}" style="width:${Math.max(0.6, a.cost / max * 100)}%"></i></span></div></td></tr>`).join("");
  const body = o.error ? errFinding(S.ag_h) : o.loading ? `<div class="well" aria-busy="true"><span class="sr">${f3("ld_line", { card: "agents" })}</span>${boneTable(6)}</div>` : `<div class="well"><table class="t ag m3-ag"><thead><tr><th>${S.ag_col_agent}</th><th class="hp">${S.ag_col_set}</th><th class="hp">${S.ag_col_ran}</th><th>${S.ag_col_check}</th><th class="r hp">${S.ag_col_runs}</th><th class="r">${S.ag_col_cost}</th></tr></thead><tbody>${rows}
    <tr class="grp"><th colspan="6" scope="colgroup">${S3.ag_none_h}</th></tr>
    ${none.map((n) => `<tr class="none"><td><span class="m3-an">${n[0]}</span><div class="muted small">${n[2]}</div></td><td class="hp">${n[1]}</td><td class="hp">${dash}</td><td>${dash}</td><td class="r num hp muted">0</td><td class="r num muted">$0.00</td></tr>`).join("")}</tbody></table></div><div class="m2-rqf m3-foot"><p>${f3("foot_est", { date: "October 28" })}</p></div>`;
  return m3Page("agents", S.nav_agents, `${m3Scope(S.nav_agents, "30d")}${rvTabs("agents")}<section class="card"><header><h2>${S.ag_h}</h2><span class="q">${S3.ag_q}</span></header>${body}</section>`);
}

// ---------- Models ----------
function m3Models(o = {}) {
  const ms = R.models.slice().sort((a, b) => b.cost - a.cost), max = ms[0].cost;
  const used = { "Fable 5.1": ["builder", S3.ag_unnamed], "Opus 5.5": ["Main session"], "Sonnet 5.5": ["reviewer"], "Haiku 5.5": ["scribe", "Explore"] };
  const kinds = [["cache_read", S.k_cache_read], ["input", S.k_input], ["cache_write", S.k_cache_write], ["output", S.k_output]];
  const tk = R.cost_by_kind;
  const table = o.loading ? `<div class="well" aria-busy="true"><span class="sr">${f3("ld_line", { card: "models" })}</span>${boneTable(4)}</div>` : `<div class="well"><table class="t md m3-md"><thead><tr><th>${S.md_col_model}</th><th class="r">${S.md_col_cost}</th><th class="hp">${S.md_col_share}</th><th class="r hp">${S.md_col_tokens}</th><th class="r hp">${S.md_col_cache}</th><th class="hp">${S.md_col_used}</th></tr></thead><tbody>
  ${ms.map((m) => `<tr><td><span class="m3-an">${sw(m.display_name)}${m.display_name}</span><div class="muted small only-phone">${m.share_pct < 1 ? "<1" : m.share_pct}% &middot; ${tok(m.tokens)} &middot; ${pct(m.hit_rate)} ${S.md_col_cache.toLowerCase()}</div></td><td class="r num">${money(m.cost)}</td><td class="hp"><div class="share" style="justify-content:flex-start"><span class="bar"><i class="mfill ${mcls(m.display_name)}" style="width:${m.cost / max * 100}%"></i></span><span class="num muted">${m.share_pct < 1 ? "<1" : m.share_pct}%</span></div></td><td class="r num hp">${tok(m.tokens)}</td><td class="r num hp">${pct(m.hit_rate)}</td><td class="hp">${used[m.display_name].map((a) => `<span class="badge">${a}</span>`).join(" ")}</td></tr>`).join("")}
  </tbody></table></div><div class="m2-rqf m3-foot"><p>${f3("foot_est", { date: "October 28" })}</p></div>`;
  return m3Page("models", S.nav_models, `${m3Scope(S.nav_models, "30d")}${rvTabs("models")}
  <section class="card"><header><h2>${S.md_h}</h2><span class="q">${S.md_q}</span></header>${table}</section>
  <section class="card" style="margin-top:var(--space-4)"><header><h2>${S.md_kind_h}</h2><span class="q">${S.md_kind_q}</span></header>
    <div class="legend kl">${kinds.map((k, i) => `<span><i class="kp kp${i + 1}" aria-hidden="true"></i>${k[1]} <b class="num">${money(tk[k[0]])}</b></span>`).join("")}</div><p class="note kl-note">${S.kind_legend_note}</p>
    <div class="well"><ul class="kind-rows m3-kr">${ms.map((m) => { const s = Object.values(m.cost_by_kind).reduce((a, c) => a + c, 0); return `<li><span class="kn">${sw(m.display_name)}${m.display_name}</span><span class="kstack ${mcls(m.display_name)}" style="width:${Math.max(2, m.cost / max * 100)}%">${kinds.map((k, i) => `<i class="kp kp${i + 1}" style="width:${m.cost_by_kind[k[0]] / s * 100}%"></i>`).join("")}</span><span class="num kv">${money(m.cost)}</span><span class="kparts muted">${kinds.slice().sort((a, b) => m.cost_by_kind[b[0]] - m.cost_by_kind[a[0]]).map((k) => `${k[1]} ${money(m.cost_by_kind[k[0]])}`).join(", ")}</span></li>`; }).join("")}</ul></div>
  </section>`);
}

// ---------- States board for the table pages ----------
function m3TableStates() {
  const strip = (h) => h.replace(/^[\s\S]*?<main class="main" id="main">/, "").replace(/<\/main>[\s\S]*$/, "");
  const fr = (lab, html) => `<section class="m2-frame" aria-label="${lab}">${M3_ANN(lab)}${strip(html).replace(/<h1>/, '<h2 class="m2-h1">').replace(/<\/h1>/, "</h2>")}</section>`;
  return m3Page("sessions", S.nav_sessions, `<h1 class="sr">${S.nav_sessions}</h1>${fr("Sessions, loading", m3Sessions({ loading: true }))}${fr("Agents, error", m3Agents({ error: true }))}${fr("Models, loading", m3Models({ loading: true }))}`);
}

// ---------- Pass 8 boards ----------
function m3Units() {
  const fr = (lab, k, o = {}) => `<section class="m2-frame m3-uf" aria-label="${lab}">${M3_ANN(lab)}${costCard(k, { ...o, unit: o.unit })}</section>`;
  return m3Page("summary", S.nav_summary, `<h1 class="sr">${S.nav_summary}</h1>
    ${fr("Today: 24 hours, the open hour hatched, Now marker", "today")}
    ${fr("7 days: days", "7d")}
    ${fr("30 days: days", "30d")}
    ${fr("90 days: 13 weeks, records start September 3", "90d")}
    ${fr("12 months: months, records start September 3", "12m")}
    ${fr("All, recommended: unit from the span (58 days, so weeks), no pager", "all")}
    ${fr("All, as months (the rule as asked): two bars", "all", { win: "all-months", unit: "month" })}`);
}
function m3PagerEnds() {
  const fr = (lab, k, o = {}) => `<section class="m2-frame m3-uf" aria-label="${lab}">${M3_ANN(lab)}${costCard(k, o)}</section>`;
  return m3Page("summary", S.nav_summary, `<h1 class="sr">${S.nav_summary}</h1>
    ${fr("30 days, paged back once: Earlier at the records start, Back to newest, tiles note", "30d", { win: "sep", scopeNote: true })}
    ${fr("Price disagreement and unpriced requests", "30d", { unpriced: true, disagree: true })}`);
}
function m3Kinds() {
  const fr = (lab, k, o = {}) => `<section class="m2-frame m3-uf" aria-label="${lab}">${M3_ANN(lab)}${costCard(k, o)}</section>`;
  return m3Page("summary", S.nav_summary, `<h1 class="sr">${S.nav_summary}</h1>
    ${fr("A, recommended: bars by model, kinds as a text line", "30d")}
    ${fr("B: every model block split by kind pattern", "30d", { pattern: true })}
    ${fr("B at 24 bars (Today)", "today", { pattern: true })}`);
}

// ---------- Pass 9: Session review ----------
const hm = (sec, base) => { const t = base + Math.round(sec / 60); const h = Math.floor(t / 60) % 24, m = t % 60; return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h >= 12 ? "PM" : "AM"}`; };
function rowsAt(runs, T, opt) {
  const byKey = Object.fromEntries(runs.map((r) => [r.key, r]));
  const Tq = opt.bucket ? Math.floor(T / opt.bucket) * opt.bucket : T;
  const ivs = (r) => [[r.start, r.end === null ? opt.Tend : r.end], ...r.extra];
  const x = (s) => (s - opt.x0) / opt.span * 100;
  runs.forEach((r) => {
    r.name = r.name || nm2(r.agent, r.n);
    const rate = RATE[r.model] * (r.agent ? 1 : 1.3) / 60;
    const act = (t) => ivs(r).reduce((a, [s, e]) => a + Math.max(0, Math.min(e, t) - s), 0);
    r.tokT = Math.round(act(Tq) * rate); r.tokAll = Math.round(act(opt.Tend) * rate);
    r.costT = r.tokT / 1e6 * PRICE[r.model]; r.costAll = r.tokAll / 1e6 * PRICE[r.model];
    if (r.tokFix) { const f = act(Tq) / act(opt.Tend); r.tokT = Math.round(r.tokFix * f); r.tokAll = r.tokFix; r.costT = r.costFix * f; r.costAll = r.costFix; }
    r.started = r.start <= T;
    r.working = ivs(r).some(([s, e]) => s <= T && (T < e || (!opt.ended && e >= opt.Tend))) || (r.end === null && r.start <= T && !opt.ended);
    r.doneAt = r.started && !r.working;
    r.lastEnd = Math.max(...ivs(r).filter(([s]) => s <= T).map(([s, e]) => Math.min(e, T)), r.start);
  });
  const kids = (k) => runs.filter((r) => r.parent === k);
  const sub = (r) => [r, ...kids(r.key).flatMap(sub)];
  const segsOf = (r) => ivs(r).flatMap(([s, e]) => { const out = []; if (s < T) out.push([x(s), x(Math.min(e, T)), 0, e > T]); if (e > T) out.push([x(Math.max(s, T)), x(e), 1]); return out; });
  const row = (r, depth) => {
    const state = !r.started ? "notyet" : r.working ? "working" : "done";
    const cost = r.costT;
    const age = state === "working" ? f3("sr_since", { time: hm(r.start, opt.base) }) : state === "done" ? f3("sr_ran", { n: Math.max(1, Math.round((r.lastEnd - r.start) / 60)) }) : "";
    return { name: r.name, depth, model: r.model, effort: r.effort, state, segs: segsOf(r), tok: r.tokT, cost: { v: cost, kind: "ok" }, age, unl: r.unl, by: depth > 3 && r.parent ? byKey[r.parent].name : null };
  };
  const out = [];
  const walk = (r, depth) => {
    out.push(row(r, depth));
    const ks = kids(r.key);
    const old = (k) => sub(k).every((q) => q.doneAt && ivs(q).every(([s, e]) => e <= T - 120 || s > T));
    const later = (k) => sub(k).every((q) => !q.started);
    const fold = ks.length > 4 ? ks.filter(old) : [], wait = ks.length > 4 ? ks.filter(later) : [];
    if (fold.length) { const all = fold.flatMap(sub); out.push({ fold: all.length, depth: depth + 1, model: "Sonnet 5.5", state: "done", segs: all.flatMap(segsOf), tok: all.reduce((a, q) => a + q.tokT, 0), cost: { v: all.reduce((a, q) => a + q.costT, 0), kind: "ok" }, age: "" }); }
    ks.filter((k) => !fold.includes(k) && !wait.includes(k)).forEach((k) => walk(k, depth + 1));
    if (wait.length) { const all = wait.flatMap(sub); out.push({ fold: all.length, later: true, depth: depth + 1, model: "Sonnet 5.5", state: "notyet", segs: all.flatMap(segsOf), tok: 0, cost: { v: 0, kind: "ok" }, age: "" }); }
  };
  walk(runs[0], 0);
  return out;
}
function laneAt(r, o) {
  const dD = Math.min(r.depth, 3), dP = Math.min(r.depth, 2);
  const by = r.by ? `<span class="m2-by">${f2("tl_by", { name: r.by })}</span>` : "";
  const unl = r.unl ? `<span class="badge m2-unl">${r.unl === "may" ? S2.tl_unl_may : S2.tl_unl_never}</span>` : "";
  const segs = r.segs.map((s) => `<span class="seg ${mcls(r.model)}${s[2] ? " fut" : ""}${s[3] ? " cut" : ""}${r.fold ? " fold" : ""}" style="left:${s[0]}%;width:max(4px, ${s[1] - s[0]}%)"></span>`).join("");
  const grid = o.grid.map((x) => `<b class="m2-gl" style="left:${x}%"></b>`).join("");
  const notyet = r.state === "notyet";
  const state = notyet ? `<span class="st idle m2st">${S.c_not_started}</span>` : rs(r.state);
  const lab = r.fold ? `<div class="m2-lab"><span class="m2-name m2-foldn">${r.later ? f3("sr_later", { n: r.fold }) : f2("tl_fold", { n: r.fold })}</span></div>`
    : `<div class="m2-lab"><span class="m2-nl"><span class="m2-name">${r.name}</span>${unl}</span><span class="ln-mod">${sw(r.model)}${r.model} &middot; ${r.effort}</span>${by}</div>`;
  const srt = r.fold ? (r.later ? f3("sr_later", { n: r.fold }) : f2("tl_fold", { n: r.fold })) : `${r.name}, ${r.model} ${r.effort}, ${notyet ? "not started yet" : r.state === "done" ? "finished" : "working"}, ${tok(r.tok)} tokens, ${money(r.cost.v)}`;
  const btn = r.fold ? `<button class="btn quiet m2-foldb" aria-expanded="false">${S2.tl_fold_show}</button>` : "";
  const nums = notyet ? `<span class="num m2-tok muted">&#x2013;</span><span class="num m2-cost muted">&#x2013;</span>` : `<span class="num m2-tok">${tok(r.tok)}</span><span class="num m2-cost">${costCell(r.cost)}</span>`;
  return `<li class="m2-ln${r.fold ? " is-fold" : ""}${notyet ? " m3-notyet" : ""}${r.unl ? " unl" : ""}" style="--ind-d:${dD * 16}px;--ind-p:${dP * 16}px"><span class="sr">${srt}</span>
    <div class="m2-row" aria-hidden="true">${guides(r.depth, 3, "dk", r.unl)}${guides(r.depth, 2, "ph", r.unl)}${lab}
      <div class="m2-track">${grid}${segs}<i class="m3-tcut" style="left:${o.x}%"></i></div>
      <div class="m2-sa">${state}<small class="muted">${r.age || ""}</small></div>${nums}</div>${btn}</li>`;
}
function replayRow(o) {
  const atEnd = o.x >= 100;
  const prec = o.prec ? `<span class="m3-prec">${o.prec}</span>` : "";
  return `<div class="m3-rp${o.cls ? " " + o.cls : ""}"><div class="m3-rpl"><span class="m3-rpv"><span class="muted">${S3.sr_showing}</span> <b class="num">${o.label}</b></span>${prec}</div>
    <div class="m3-rpt"><label class="sr" for="rp-${o.id}">${S3.sr_label}</label><input class="m3-range" id="rp-${o.id}" type="range" min="0" max="${o.max}" step="1" value="${Math.round(o.x / 100 * o.max)}" aria-valuetext="${o.label}" style="--x:${o.x}%"></div>
    <div class="m3-rpe"><span class="muted m3-keys">${S3.sr_keys}</span></div></div>`;
}
function whoAt(o) {
  const chartBk = o.buckets.map((b, i) => ({ by: b.by, open: b.open }));
  const cut = o.cutBucket;
  const cols = chartBk.map((b, i) => { const tot = Object.values(b.by).reduce((a, c) => a + c, 0); return i >= cut ? { fut: tot } : b; });
  const mx = Math.max(...chartBk.map((b) => Object.values(b.by).reduce((a, c) => a + c, 0)));
  const { top, ticks } = niceTicks(mx);
  const colH = cols.map((b) => b.fut !== undefined ? `<div class="m2-col m3-fut"><i style="height:${b.fut / top * 100}%"></i></div>` : `<div class="m2-col${b.open !== undefined ? " open" : ""}" style="flex:${b.open !== undefined ? b.open : 1}">${MODELS.filter((m) => b.by[m]).map((m) => `<i class="${mcls(m)}" style="height:${b.by[m] / top * 100}%"></i>`).join("")}</div>`).join("");
  const chart = `<div class="m2-ch" style="--h:72px"><div class="m2-plot"><i class="m3-tcut m3-pcut" style="left:${o.x}%"></i>${ticks.map((t) => `<b style="bottom:${t[0] / top * 100}%"><span>${t[1]}</span></b>`).join("")}<div class="m2-cols">${colH}</div></div><div class="m2-x">${o.xl.map((x) => `<span class="${x[2] ? "" : "dk"}" style="left:${x[0]}%">${x[1]}</span>`).join("")}</div></div>`;
  const btn = o.x >= 100 ? "" : `<button class="btn right">${o.running ? S3.sr_to_now : S3.sr_to_end}</button>`;
  return `<section class="card m2-who m3-who" style="--cx:${o.x}"><header><h2>${S3.sr_tl_h}</h2>${btn}</header>
    <div class="m3-stage"><div class="m2-head" aria-hidden="true"><div class="m2-axlab">${o.axis || S.tl_axis_lab}${legendTotals(o.buckets.slice(0, cut))}</div>${chart}<div></div></div>
    ${replayRow(o)}
    <ul class="m2-lanes" aria-label="${S3.sr_tl_h}">${o.rows.map((r) => laneAt(r, o)).join("")}</ul>
    <div class="m3-cutwrap" aria-hidden="true"><div class="m3-cuttrack"><i class="m3-cut"></i></div></div></div>
    <p class="note">${S3.sr_note}</p></section>`;
}
function srHead(h) {
  const right = `${h.gone ? "" : `<button class="sel m2-sel m3-ssel${h.selOpen ? " is-open" : ""}" aria-haspopup="listbox" aria-expanded="${!!h.selOpen}"><span class="lab">${S.rv_session_scope}</span><b${h.gone ? ' class="ph-v"' : ""}>${h.sel}</b></button>`}${h.running ? `<a class="btn" href="#">${S.rv_open_live}</a>` : ""}`;
  return `<div class="ph m2-ph m3-ph m3-srh"><div class="m2-tt"><a class="m3-back" href="#"><span aria-hidden="true">&#x2190;</span> ${S3.sr_back}</a>${h.title ? `<h1>${h.title}</h1>` : `<div class="lv-state">${rs(h.state)}<h1>${h.branch}</h1></div>`}${h.sub ? `<p class="sub">${h.sub}</p>` : ""}</div><div class="right">${right}</div></div>`;
}
function atTiles(t, mode) {
  if (mode === "sofar") return `<div class="tiles">${m2Tile(S.rv_t_cost, t.costAll, S3.t_sofar, { kx: S3.t_cost_kx })}${m2Tile(S.t_tokens, t.tokAll, S3.t_sofar)}${m2Tile(S.t_cache, t.cacheAll, S3.t_sofar, { proof: ring(t.hitAll) })}${m2Tile(S3.t_runs, t.runsAll, f3("t_of_runs_w", { w: t.working }), { proof: m2Dots(t.working, t.runsAll - t.working) })}</div>`;
  if (mode === "whole") return `<div class="tiles">${m2Tile(S.rv_t_cost, t.costAll, S3.t_whole, { kx: S3.t_cost_kx })}${m2Tile(S.t_tokens, t.tokAll, S3.t_whole)}${m2Tile(S.t_cache, t.cacheAll, S3.t_whole, { proof: ring(t.hitAll) })}${m2Tile(S3.t_runs, t.runsAll, f3("t_runs_d", { n: t.runsAll }), { proof: m2Dots(0, t.runsAll) })}</div>`;
  const time = t.time;
  return `<div class="tiles">${m2Tile(f3("t_at_cost", { time }), t.cost, f3("t_of_cost", { v: t.costAll }), { kx: S3.t_cost_kx })}${m2Tile(f3("t_at_tokens", { time }), t.tok, f3("t_of_tokens", { v: t.tokAll }))}${m2Tile(f3("t_at_cache", { time }), t.cache, f3("t_of_cache", { v: t.cacheAll }), { proof: ring(t.hit) })}${m2Tile(f3("t_at_runs", { time: t.timeRuns || time }), t.runs, f3(t.notyet ? "t_of_runs" : "t_of_runs_w", { w: t.working, n: t.notyet }), { proof: m2Dots(t.working, t.runs - t.working) })}</div>`;
}
function manyEnded() { return MANY.map((r) => ({ ...r, end: r.end === null ? 3540 + (r.start % 7) * 20 : r.end, extra: r.extra.slice() })); }
function srPage(o) {
  const runs = o.runs, T = o.T;
  const rows = rowsAt(runs, T, o.opt);
  const buckets = bucketsFrom(runs.map((r) => ({ ...r, end: r.end === null ? o.opt.Tend : r.end })), o.opt.Tend, 0, o.opt.bucket || 60, o.nb, o.openFrac);
  const cutBucket = Math.floor((o.opt.bucket ? Math.floor(T / o.opt.bucket) * o.opt.bucket : T) / (o.opt.bucket || 60));
  const x = T / o.opt.span * 100;
  const all = runs.reduce((a, r) => a + r.tokAll, 0), at = runs.reduce((a, r) => a + r.tokT, 0);
  const cAll = runs.reduce((a, r) => a + r.costAll, 0), cAt = runs.reduce((a, r) => a + r.costT, 0);
  const label = o.label || hm(T, o.opt.base);
  const t = { time: o.tileTime || label, timeRuns: label, cost: money(cAt), costAll: money(cAll), tok: tok(at), tokAll: tok(all), cache: o.cache || "82%", cacheAll: o.cacheAll || "84%", hit: 0.82, hitAll: o.hitAll || 0.84, runs: runs.filter((r) => r.started).length, runsAll: runs.length, working: runs.filter((r) => r.working).length, notyet: runs.filter((r) => !r.started).length };
  const head = srHead({ ...o.head, running: o.running });
  const who = whoAt({ buckets, rows, xl: o.xl, grid: o.grid, x, cutBucket, label, prec: o.prec, max: Math.round(o.opt.span / 60), id: "a", running: o.running, axis: o.axis, cls: o.rpcls });
  return m3Page("sessions", S.nav_sessions, `${head}${atTiles(t, x >= 100 ? "sofar" : o.tiles || "at")}${who}`, { after: o.after || "" });
}
const XMANY = [[0, "2:00", 1], [16.7, "2:10"], [33.3, "2:20", 1], [50, "2:30"], [66.7, "2:40", 1], [83.3, "2:50"], [100, "3:00", 1]];
const MANY_HEAD = { state: "ended", branch: "feature/ledger-sync", sub: f3("sr_sub_ended", { date: "October 29", start: "2:00 PM", end: "3:00 PM", dur: "60 minutes" }), sel: "October 29, 2:00 PM" };
function manyAt(T, o = {}) { return srPage({ runs: manyEnded(), T, opt: { span: 3600, x0: 0, Tend: 3600, base: 14 * 60, ended: true }, nb: 60, xl: XMANY, grid: [16.7, 33.3, 50, 66.7, 83.3], head: MANY_HEAD, ...o }); }
const m3Replay = () => manyAt(25 * 60, { rpcls: "is-focus" });
const m3TilesWhole = () => manyAt(25 * 60, { tiles: "whole" });
// The October 30 session, still running (6:10 to 6:40 so far), plus an Explore run nobody claimed.
function octRuns() {
  const s = (iso) => Math.round((minOf(iso) - T0) * 60);
  const keyOf = {};
  const out = RUNS.map((r, i) => { keyOf[r.run_id] = "k" + i; return { tokFix: r.tokens, costFix: r.cost, key: "k" + i, agent: r.agent, n: r.label_n || 1, name: r.name, parent: r.parent, model: r.model_display, effort: r.effort, start: s(r.rounds[0].started), end: r.state === "working" && r.rounds.length === 1 ? null : s(r.rounds[0].last_request), extra: r.rounds.slice(1).map((rd) => [s(rd.started), r.state === "working" ? 1800 : s(rd.last_request)]) }; });
  out.forEach((r) => (r.parent = r.parent ? keyOf[r.parent] : null));
  out.splice(5, 0, { key: "ex", agent: "Explore", n: 1, name: "Explore", parent: "k0", model: "Haiku 5.5", effort: "low", start: 290, end: 420, extra: [], unl: "never", tokFix: 21000, costFix: 0.0014 });
  return out;
}
function octAt(T, o = {}) { return srPage({ runs: octRuns(), T, opt: { span: 1800, x0: 0, Tend: 1800, base: 18 * 60 + 10 }, nb: 30, xl: X30, grid: G30, running: true, cache: "76%", cacheAll: "78%", hitAll: 0.78, head: { state: "working", branch: LIVE.branch, sub: f3("sr_sub_running", { start: "6:10 PM" }), sel: "Today, 6:10 PM" }, ...o }); }
const m3RunningNow = () => octAt(1800, { label: S3.sr_at_now + ", 6:40 PM", tileTime: "6:40 PM" });
const m3Early = () => octAt(6 * 60);
const m3RunningMoved = () => octAt(6 * 60, { rpcls: "is-drag" });
function m3Long() {
  const runs = longRuns(), T = (11 * 60 + 43 - 9 * 60) * 60;
  return srPage({ runs, T, opt: { span: 484 * 60, x0: 0, Tend: 484 * 60, base: 9 * 60, bucket: 600, ended: false }, nb: 49, openFrac: 0.4, running: true, xl: [[0, "9 AM", 1], [12.4, "10"], [24.8, "11", 1], [37.2, "12 PM"], [49.6, "1", 1], [62, "2"], [74.4, "3", 1], [86.8, "4"], [100, S.tl_now, 1]], grid: [12.4, 24.8, 37.2, 49.6, 62, 74.4, 86.8], axis: f2("tl_axis_avg", { n: 10 }),
    prec: f3("sr_prec", { time: "11:40 AM", n: 10 }), tileTime: "11:40 AM", head: { state: "working", branch: "feature/quarter-close", sub: f3("sr_sub_running", { start: "9:02 AM" }), sel: "Today, 9:02 AM" } });
}
function m3SrSelect() {
  const opt = (t, b, stt, cur) => `<li role="option" aria-selected="${!!cur}"${cur ? ' class="on"' : ""}><span class="pk-n">${t}</span>${cur ? '<span class="ok" aria-hidden="true">&#x2713;</span>' : ""}<span class="pk-s">${stt ? rs(stt) : ""}<small class="muted">${b}</small></span></li>`;
  const grp = (id, h, items) => `<div role="group" aria-labelledby="${id}"><div class="m2-gh" id="${id}" role="presentation">${h}</div><ul class="pk-list" role="presentation">${items}</ul></div>`;
  const pop = `<div class="pk-scrim only-phone" aria-hidden="true"></div><div class="pk-pop m2-pop m3-spop" role="dialog" aria-labelledby="ss-h"><header class="pk-h"><h2 id="ss-h">${S3.sel_h}</h2><button class="btn quiet x only-phone" aria-label="${S.ed_close}"><span aria-hidden="true">&#x2715;</span></button></header>
    <div role="listbox" aria-labelledby="ss-h" class="m2-sl">${grp("g1", S3.ss_today, opt("6:10 PM", "feature/quarter-close", "working") + opt("9:02 AM", "feature/quarter-close", "working"))}${grp("g2", S3.ss_yday, opt("2:00 PM", "feature/ledger-sync", null, true) + opt("10:14 AM", "feature/invoice-export"))}${grp("g3", "October 28", opt("4:30 PM", "feature/quarter-close"))}</div><a class="m2-all" href="#">${f3("sel_all", { n: 53 })}<span aria-hidden="true"> &#x2192;</span></a></div>`;
  return manyAt(25 * 60, { head: { ...MANY_HEAD, selOpen: true }, after: pop });
}
function m3Gone() {
  const head = srHead({ title: S3.gone_title, gone: true });
  return m3Page("sessions", S.nav_sessions, `${head}<div class="raised err m2-gone" role="alert"><h2><span aria-hidden="true" class="errm">&#x2715;</span>${S3.gone_h}</h2><p>${S3.gone_b}</p><div class="m2-acts"><a class="btn primary" href="#">${S3.gone_all}</a></div></div>`);
}

// ---------- Board map ----------
window.M3B = {
  "p7-summary": () => m3Summary("30d"), "p7-range-open": () => m3Summary("30d", { open: true }), "p7-today": () => m3Summary("today"), "p7-all": () => m3Summary("all"), "p7-history": () => m3Summary("12m"),
  "p7-loading": () => m3Summary("30d", { loading: true }), "p7-error": () => m3Summary("30d", { errorChart: true, errorCheck: true }), "p7-empty": m3Empty, "p7-unpriced": () => m3Summary("30d", { unpriced: true, disagree: true }),
  "p7-sessions": () => m3Sessions(), "p7-agents": () => m3Agents(), "p7-models": () => m3Models(), "p7-table-states": m3TableStates,
  "p8-units": m3Units, "p8-pager": m3PagerEnds, "p8-kinds": m3Kinds,
  "p9-replay": m3Replay, "p9-tiles-whole": m3TilesWhole, "p9-running-now": m3RunningNow, "p9-running-moved": m3RunningMoved, "p9-long": m3Long, "p9-select-open": m3SrSelect, "p9-gone": m3Gone,
};
