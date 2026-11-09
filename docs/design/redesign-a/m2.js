// M2 Live passes 1 to 3 (designer boards, November 9). Builds on a.js, ui.js, m0.js and m1.js helpers.
const f2 = (k, o = {}) => S2[k].replace(/\{(\w+)\}/g, (_, x) => (o[x] !== undefined ? o[x] : "{" + x + "}"));
const rs = (k, w) => `<span class="st ${k} m2st">${w || (k === "ended" ? S2.st_ended : S["st_" + k])}</span>`;
const nm2 = (agent, n) => (agent ? agent + (n > 1 ? " " + n : "") : S2.tl_main);
const PRICE = { "Opus 5.5": 1.65, "Sonnet 5.5": 1.0, "Haiku 5.5": 0.07, "Fable 5.1": 0 };

// ---------- Cost cells ----------
function costCell(c) {
  if (c.kind === "none") return `<span class="m2-cnone">${f2("c_none", { model: c.model })}</span>`;
  if (c.kind === "part") return `<span class="m2-cleast">${f2("c_least", { cost: `<b>${money(c.v)}</b>` })}</span>`;
  return money(c.v);
}

// ---------- Chart ----------
function niceTicks(mx) {
  const raw = mx / 2, p = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw);
  return { top: Math.max(step * 2, mx) * 1.12, ticks: [[step, tok(step)], [step * 2, tok(step * 2)]] };
}
function m2Chart(buckets, o) {
  const sums = buckets.map((b) => Object.values(b.by).reduce((a, c) => a + c, 0));
  const { top, ticks } = niceTicks(Math.max(...sums));
  const cols = buckets.map((b) => `<div class="m2-col${b.open !== undefined ? " open" : ""}" style="flex:${b.open !== undefined ? b.open : 1}">${MODELS.filter((m) => b.by[m]).map((m) => `<i class="${mcls(m)}" style="height:${b.by[m] / top * 100}%"></i>`).join("")}</div>`).join("");
  return `<div class="m2-ch" style="--h:${o.h || 72}px">
    <div class="m2-plot">${ticks.map((t) => `<b style="bottom:${t[0] / top * 100}%"><span>${t[1]}</span></b>`).join("")}<div class="m2-cols">${cols}</div></div>
    <div class="m2-x">${o.xl.map((x) => `<span class="${x[2] ? "" : "dk"}" style="left:${x[0]}%">${x[1]}</span>`).join("")}</div></div>`;
}
function legendTotals(buckets, mult = 1) {
  const t = {}; buckets.forEach((b) => Object.entries(b.by).forEach(([m, v]) => (t[m] = (t[m] || 0) + v * mult * (b.open !== undefined ? b.open : 1))));
  return `<div class="legend m2-leg">${MODELS.filter((m) => t[m]).map((m) => `<span>${sw(m)}${m} <b class="num">${tok(t[m])}</b></span>`).join("")}</div>`;
}

// ---------- Lanes ----------
function guides(depth, cap, cls, dashed) {
  const d = Math.min(depth, cap);
  return Array.from({ length: d }, (_, i) => `<span class="g ${cls}${i === d - 1 ? " el" : ""}${i === d - 1 && dashed ? " dash" : ""}" style="left:${i * 16 + 7}px"></span>`).join("");
}
function laneRow(r, o) {
  const dD = Math.min(r.depth, 3), dP = Math.min(r.depth, 2);
  const by = r.by ? `<span class="m2-by${r.depth > 3 ? "" : " p-only"}">${f2("tl_by", { name: r.by })}</span>` : "";
  const unl = r.unl ? `<span class="badge m2-unl">${r.unl === "may" ? S2.tl_unl_may : S2.tl_unl_never}</span>` : "";
  const segs = r.segs.map((s, i) => `<span class="seg ${mcls(r.model)}${r.state === "working" && i === r.segs.length - 1 ? " open" : ""}${r.fold ? " fold" : ""}" style="left:${s[0]}%;width:max(4px, ${s[1] - s[0]}%)"></span>${i > 0 && !r.fold ? `<span class="rnd${s[0] > 85 ? " end" : ""}" style="${s[0] > 85 ? `right:${100 - s[1]}%` : `left:${s[0]}%`}">${S.tl_round2.replace("2", i + 1)}</span>` : ""}`).join("");
  const grid = o.grid.map((x) => `<b class="m2-gl" style="left:${x}%"></b>`).join("");
  const state = rs(r.fold ? "done" : r.state);
  const lab = r.fold
    ? `<div class="m2-lab"><span class="m2-name m2-foldn">${f2("tl_fold", { n: r.fold })}</span></div>`
    : `<div class="m2-lab"><span class="m2-nl"><span class="m2-name">${r.name}</span>${unl}</span><span class="ln-mod">${sw(r.model)}${r.model} &middot; ${r.effort}</span>${by}</div>`;
  const srt = r.fold ? f2("tl_fold", { n: r.fold }) + `, ${tok(r.tok)} tokens, ${money(r.cost.v)}`
    : `${r.name}, ${r.model} ${r.effort}${r.parent ? ", started by " + r.parent : ""}, ${r.state === "done" ? "finished" : r.state}, ${tok(r.tok)} tokens, ${r.cost.kind === "none" ? "no price" : money(r.cost.v)}`;
  const btn = r.fold ? `<button class="btn quiet m2-foldb" aria-expanded="${!!r.open}">${r.open ? S2.tl_fold_hide : S2.tl_fold_show}</button>` : "";
  return `<li class="m2-ln${r.fold ? " is-fold" : ""}${r.moved ? " moved" : ""}${r.unl ? " unl" : ""}" style="--ind-d:${dD * 16}px;--ind-p:${dP * 16}px"><span class="sr">${srt}</span>
    <div class="m2-row" aria-hidden="true">${guides(r.depth, 3, "dk", r.unl)}${guides(r.depth, 2, "ph", r.unl)}${lab}
      <div class="m2-track">${grid}${segs}</div>
      <div class="m2-sa">${state}<small class="muted">${r.age || ""}</small></div>
      <span class="num m2-tok">${tok(r.tok)}</span><span class="num m2-cost">${costCell(r.cost)}</span></div>${btn}</li>`;
}
function m2Lanes(rows, o) { return `<ul class="m2-lanes" aria-label="${S.tl_h}">${rows.map((r) => laneRow(r, o)).join("")}</ul>`; }
function whoCard(o) {
  return `<section class="card m2-who"><header><h2>${S.tl_h}</h2><span class="q">${S.tl_q}</span></header>
    <div class="m2-head" aria-hidden="true"><div class="m2-axlab">${o.axis || S.tl_axis_lab}${legendTotals(o.buckets)}</div>${m2Chart(o.buckets, o)}<div></div></div>
    ${m2Lanes(o.rows, o)}<p class="note">${o.note || S2.tl_note2}</p></section>`;
}

// ---------- Tiles ----------
function m2Tile(k, v, d, o = {}) {
  return `<div class="tile m2-tile"><div class="k">${k}${o.kx ? `<span class="m2-kx">${o.kx}</span>` : ""}</div><div class="v num">${v}</div>${o.proof ? `<div class="proof" aria-hidden="true">${o.proof}</div>` : ""}<div class="d">${d}${o.d2 ? `<span class="m2-d2">${o.d2}</span>` : ""}</div></div>`;
}
function m2Dots(on, ok, cap = 8) {
  const a = Math.min(on, cap), b = Math.min(ok, cap - a), more = on + ok - a - b;
  return `<div class="dots m2-dots">${'<i class="on"></i>'.repeat(a)}${'<i class="ok"></i>'.repeat(b)}${more > 0 ? `<span class="m2-more">${f2("t_agents_more", { n: more })}</span>` : ""}</div>`;
}
function m2Spark(vals) {
  const mx = Math.max(...vals.filter((v) => v !== null));
  return `<div class="spark${vals.length > 32 ? " dense" : ""}">${vals.map((v, i) => v === null ? `<i class="m2-nul"></i>` : `<i${i === vals.length - 1 ? ' class="last"' : ""} style="height:${Math.max(4, v / mx * 100)}%"></i>`).join("")}</div>`;
}
function tilesRow(t) {
  return `<div class="tiles">
    ${m2Tile(t.ended ? S2.t_cost_ended : S.t_cost, t.cost, t.costD, { kx: S2.t_cost_kx, d2: t.unpriced ? f2("t_unpriced", { n: t.unpriced }) : "", proof: m2Spark(t.spark) })}
    ${m2Tile(S.t_tokens, t.tokens, t.tokD)}
    ${m2Tile(S.t_cache, t.cache, t.cacheD, { proof: ring(t.hit) })}
    ${m2Tile(t.ended ? S2.t_agents_ended : S.t_agents, t.ended ? t.finished : t.working, t.agD, { proof: m2Dots(t.working, t.finished) })}</div>`;
}

// ---------- Lower cards ----------
function m2Req(rows) {
  return `<table class="t m2-rq"><thead><tr><th>${S.rq_time}</th><th>${S.rq_agent}</th><th class="hp">${S.rq_model}</th><th class="r">${S.rq_tokens}</th><th class="r">${S.rq_cost}</th></tr></thead><tbody>
  ${rows.map((q) => `<tr><td class="num">${q.t}</td><td>${q.agent}</td><td class="hp">${sw(q.model)}${q.model} &middot; ${q.effort}</td><td class="r num">${tok(q.tokens)}</td><td class="r num">${q.cost === null ? `<span class="m2-cnone">${S2.c_none_short}</span>` : money(q.cost)}</td></tr>`).join("")}</tbody></table>`;
}
function reqFoot(disagree) {
  return `<div class="m2-rqf"><p>${S2.rq_f_est} ${f2("rq_f_prices", { date: "November 8" })}.</p><p>${S2.rq_f_sub}</p>${disagree ? `<p class="fwarn"><span aria-hidden="true" class="wm">&#x25B2;</span>${f2("rq_f_disagree", { model: "Opus 5.5" })}</p>` : ""}</div>`;
}
const mcNoWhy = () => modelCheckLive().replace(/<a class="btn" href="#">[^<]*<\/a>/, "");
function lowerCards(o) {
  return `<div class="grid two m2-low">
    <section class="card"><header><h2>${S.mc_h}</h2><span class="q">${S.mc_q}</span></header>${mcNoWhy()}</section>
    <section class="card"><header><h2>${S.rq_h}</h2><span class="q">${S.rq_q}</span></header><div class="well">${m2Req(o.req)}</div>${reqFoot(o.disagree)}</section></div>`;
}

// ---------- Header ----------
function selBtn(value, open, muted) {
  return `<button class="sel m2-sel${open ? " is-open" : ""}" aria-haspopup="listbox" aria-expanded="${!!open}"><span class="lab">${S.live_pick_label}</span><b${muted ? ' class="ph-v"' : ""}>${value}</b></button>`;
}
function liveHead(h) {
  const when = h.mode === "paused" ? f2("hd_paused", { time: h.at }) : h.mode === "lost" ? f2("hd_lost", { time: h.at }) : h.mode === "ended" ? f2("hd_ended", { time: h.at }) : "";
  const btn = h.mode === "ended" ? "" : `<button class="btn">${h.mode === "paused" ? S.live_resume : S.live_pause}</button>`;
  return `<div class="ph lv-head m2-ph">
    <div class="m2-tt"><div class="lv-state">${rs(h.state)}<h1>${h.branch || `<span class="muted">${S2.hd_no_branch}</span>`}</h1></div><p class="sub">${h.sub}</p></div>
    <div class="right">${selBtn(h.sel || S.live_pick_value, h.selOpen)}${when ? `<span class="muted upd m2-when" role="status">${when}</span>` : `<span class="sr" role="status"></span>`}${btn}</div></div>`;
}
const lostFinding = (t) => `<div class="raised wfind m2-lost" role="status"><h3><span aria-hidden="true" class="wm">&#x25B2;</span>${S2.lost_h}</h3><p>${f2("lost_b", { time: t })}</p><div><button class="btn">${S2.lost_try}</button></div></div>`;
const switchNotice = () => `<div class="notice raised-line m2-nt" role="status"><span aria-hidden="true" class="m2-ntm">&#x25CF;</span><span>${f2("nt_switch", { branch: "<b>feature/invoice-export</b>", time: "7:02 PM" })}</span><button class="btn">${S2.nt_switch_btn}</button></div>`;

// ---------- Page wrapper with the demo mark ----------
function m2Page(body, o = {}) {
  let h = aPage("live", S.live_h1, body);
  h = h.replace(`<div class="brand">${S.product}</div>`, `<div class="brand">${S.product}<span class="badge m2-demo">${S2.demo}</span></div>`)
    .replace(`<span class="pname">${S.live_h1}</span>`, `<span class="pname">${S.live_h1}</span><span class="badge m2-demo">${S2.demo}</span>`)
    .replace('class="shell a"', 'class="shell a m2"').replace(/<button class="proj" aria-haspopup="listbox" aria-expanded="false" aria-label="[^"]*">/, '<button class="proj" aria-haspopup="listbox" aria-expanded="false">');
  if (o.idleNav) h = h.replace(/<span class="live-dot">.*?<\/span><\/span>/, "").replace(/<span class="live-dot"><span aria-hidden="true">&#x25CF;<\/span>[^<]*<\/span>/, "");
  return h + (o.after || "");
}

// ---------- Data: the October 30 fixture (30 minutes, 6:10 to 6:40) ----------
const X30 = [[0, "6:10", 1], [16.7, "6:15"], [33.3, "6:20", 1], [50, "6:25"], [66.7, "6:30", 1], [83.3, "6:35"], [100, S.tl_now, 1]];
const G30 = [16.7, 33.3, 50, 66.7, 83.3];
function liveRows(o = {}) {
  return RUNS.map((r) => {
    const segs = r.rounds.map((rd, i) => [xp(rd.started), r.state === "working" && i === r.rounds.length - 1 ? 100 : xp(rd.last_request)]);
    const name = nm2(r.agent, r.label_n);
    let cost = { v: r.cost, kind: "ok" }, model = r.model_display;
    if (o.unpriced && name === "tech-writer") { model = "Fable 5.1"; cost = { kind: "none", model }; }
    if (o.unpriced && name === "judge") cost = { v: r.cost * 0.8, kind: "part" };
    const st0 = r.state === "done" ? "done" : r.state;
    return { name, depth: r.depth, model, effort: r.effort, state: o.paused && st0 === "working" ? "working" : st0, segs, age: laneAge(r), tok: r.tokens, cost, parent: r.parent ? nm2((LIVE.runs.find((x) => x.run_id === r.parent) || {}).agent, (LIVE.runs.find((x) => x.run_id === r.parent) || {}).label_n) : null };
  });
}
const liveBuckets = (o = {}) => LIVE.minutes.map((m) => { const by = { ...m.by }; if (o.unpriced && by["Sonnet 5.5"] && ((m.t >= "18:20" && m.t <= "18:24") || m.t >= "18:39")) { by["Fable 5.1"] = Math.round(by["Sonnet 5.5"] * 0.4); by["Sonnet 5.5"] -= by["Fable 5.1"]; } return { by }; });
const liveReq = (o = {}) => LIVE.requests.slice(0, 5).map((q) => ({ t: (o.hour || (q.ts.slice(0, 2) - 12)) + (o.hour ? ":59" + q.ts.slice(5) : q.ts.slice(2)), agent: q.agent, model: o.unpriced && q.agent === "tech-writer" ? "Fable 5.1" : q.model, effort: q.effort, tokens: q.tokens, cost: o.unpriced && q.agent === "tech-writer" ? null : q.cost }));
function liveTiles(o = {}) {
  const t = LIVE.totals;
  const ended = o.mode === "ended";
  return { cost: money(o.unpriced ? 7.05 : t.cost), costD: ended ? S2.t_ended_d : S.t_cost_d, unpriced: o.unpriced ? 12 : 0, spark: LIVE.minutes.map((m) => m.tokens),
    tokens: tok(t.tokens), tokD: ended ? S2.t_ended_d : S.t_tokens_d, cache: pct(t.hit_rate), cacheD: ended ? S2.t_ended_d : S.t_cache_d, hit: t.hit_rate,
    working: ended ? 0 : 4, finished: ended ? 8 : 4, agD: ended ? S2.t_agents_ended_d : S.t_agents_d, ended };
}
const HEAD = {
  working: { state: "working", mode: "live" }, idle: { state: "idle", mode: "live" },
  paused: { state: "working", mode: "paused", at: "6:39:52 PM" }, lost: { state: "working", mode: "lost", at: "6:39:52 PM" },
  ended: { state: "ended", mode: "ended", at: "6:52 PM" },
};
function headFor(k) { const h = { ...HEAD[k], branch: LIVE.branch }; h.sub = k === "ended" ? f2("hd_sub_ended", { start: "6:10 PM", end: "6:52 PM", dur: "42 minutes" }) : f2("hd_sub_live", { start: "6:10 PM", dur: "30 minutes" }); return h; }

function m2Live(o = {}) {
  const k = o.head || "working";
  const rows = liveRows(o);
  if (k === "ended") rows.forEach((r) => { if (r.state !== "done") { r.state = "done"; r.age = S.tl_ran.replace("{n}", 12); r.segs[r.segs.length - 1][1] = Math.min(r.segs[r.segs.length - 1][1], 99); } });
  const body = `${o.top || ""}${liveHead({ ...headFor(k), selOpen: o.selOpen })}${k === "lost" ? lostFinding("6:39:52 PM") : ""}
    ${tilesRow(liveTiles({ ...o, mode: k }))}
    ${whoCard({ buckets: liveBuckets(o), rows, xl: X30, grid: G30 })}
    ${lowerCards({ req: liveReq(o), disagree: o.unpriced })}`;
  return m2Page(body, { after: o.after });
}

// ---------- Pass 1 boards ----------
const ann = (t) => `<p class="m2-ann" aria-hidden="true">${t}</p>`;
function m2Headers() {
  const blocks = ["working", "idle", "paused", "lost", "ended"].map((k) => `<section class="m2-frame" aria-label="${k}">${ann(k)}${liveHead(headFor(k))}${k === "lost" ? lostFinding("6:39:52 PM") : ""}</section>`).join("");
  return m2Page(`<h1 class="sr">${S.live_h1}</h1>${blocks}`).replace(/<h1>feature\/quarter-close<\/h1>/g, '<h2 class="m2-h1">feature/quarter-close</h2>');
}
function unlinkedRows(after) {
  const rows = liveRows().map((r) => ({ ...r }));
  const scout3 = { name: "scout 3", depth: 1, model: "Haiku 5.5", effort: "medium", state: "working", segs: [[93, 100]], age: S.tl_last.replace("{n}", 3), tok: 38000, cost: { v: 0.004, kind: "ok" }, unl: "may", parent: null };
  const ex = { name: "Explore", depth: 1, model: "Haiku 5.5", effort: "low", state: "done", segs: [[40, 48]], age: S.tl_ran.replace("{n}", 2), tok: 21000, cost: { v: 0.002, kind: "ok" }, unl: "never", parent: null };
  if (!after) { rows.splice(rows.length - 1, 0, ex); rows.push(scout3); return rows; }
  const i = rows.findIndex((r) => r.name === "judge");
  rows.splice(i + 1, 0, { ...scout3, depth: 2, state: "done", unl: null, moved: true, segs: [[93, 99.5]], age: S.tl_ran.replace("{n}", 2), parent: "deep-reasoner" });
  rows.splice(rows.length - 1, 0, ex);
  return rows;
}
function m2Unlinked() {
  const card = (after) => `${ann(after ? "after" : "before")}${whoCard({ buckets: liveBuckets(), rows: unlinkedRows(after), xl: X30, grid: G30 })}`;
  return m2Page(`<h1 class="sr">${S.live_h1}</h1>${card(false)}<div style="height:var(--space-4)"></div>${card(true)}`);
}

// ---------- Pass 2: the many scenario (60 minutes, 2:00 to 3:00 PM) ----------
function scen(spec) {
  // spec rows: [key, agent, parentKey, model, effort, start s, end s or null (working), extra rounds [[s,e]]]
  const cnt = {}, out = [];
  spec.forEach((s) => { cnt[s[1]] = (cnt[s[1]] || 0) + 1; out.push({ key: s[0], agent: s[1], n: cnt[s[1]], parent: s[2], model: s[3], effort: s[4], start: s[5], end: s[6], extra: s[7] || [] }); });
  return out;
}
const MANY = scen([
  ["m", null, null, "Opus 5.5", "high", 0, null],
  ["dr", "deep-reasoner", "m", "Opus 5.5", "high", 60, null],
  ["de", "designer", "m", "Opus 5.5", "high", 90, null],
  ["s1", "scout", "dr", "Haiku 5.5", "medium", 300, 470, [[2000, 2060]]], ["s2", "scout", "dr", "Haiku 5.5", "medium", 300, 520], ["s3", "scout", "dr", "Haiku 5.5", "medium", 300, 430],
  ["s4", "scout", "de", "Haiku 5.5", "medium", 450, 610], ["s5", "scout", "de", "Haiku 5.5", "medium", 450, 700],
  ["tw", "tech-writer", "m", "Sonnet 5.5", "high", 600, 840],
  ["w1", "fast-worker", "dr", "Sonnet 5.5", "medium", 800, 1080], ["w2", "fast-worker", "dr", "Sonnet 5.5", "medium", 800, 1010],
  ["w3", "fast-worker", "de", "Sonnet 5.5", "medium", 1200, 1440], ["w4", "fast-worker", "de", "Sonnet 5.5", "medium", 1200, 1380], ["j1", "judge", "de", "Opus 5.5", "medium", 1200, 1350],
  ["w5", "fast-worker", "dr", "Sonnet 5.5", "medium", 1400, 1690], ["w6", "fast-worker", "dr", "Sonnet 5.5", "medium", 1400, 1610], ["w7", "fast-worker", "dr", "Sonnet 5.5", "medium", 1400, 1560],
  ["w8", "fast-worker", "dr", "Sonnet 5.5", "medium", 2200, 2470], ["j2", "judge", "dr", "Opus 5.5", "medium", 2200, 2390],
  ["w9", "fast-worker", "de", "Sonnet 5.5", "medium", 3200, 3420], ["w10", "fast-worker", "de", "Sonnet 5.5", "medium", 3200, 3390], ["w11", "fast-worker", "de", "Sonnet 5.5", "medium", 3200, null],
  ["w12", "fast-worker", "dr", "Sonnet 5.5", "medium", 3300, 3510], ["w13", "fast-worker", "dr", "Sonnet 5.5", "medium", 3300, null],
  ["vf", "verifier", "m", "Opus 5.5", "high", 3300, null],
]);
const RATE = { "Opus 5.5": 32000, "Sonnet 5.5": 21000, "Haiku 5.5": 9000 };
function buildRows(runs, T, opt) {
  // opt: {span seconds, x0 seconds, foldKeep seconds, openKeys}
  const byKey = Object.fromEntries(runs.map((r) => [r.key, r]));
  const dur = (r) => ((r.end === null ? T : r.end) - r.start) + r.extra.reduce((a, e) => a + e[1] - e[0], 0);
  runs.forEach((r) => { r.tok = Math.round(dur(r) / 60 * RATE[r.model] * (r.agent ? 1 : 1.3)); r.costv = r.tok / 1e6 * PRICE[r.model]; r.name = nm2(r.agent, r.n); });
  const kids = (k) => runs.filter((r) => r.parent === k);
  const sub = (r) => [r, ...kids(r.key).flatMap(sub)];
  const x = (s) => (s - opt.x0) / opt.span * 100;
  const row = (r, depth) => {
    const segs = [[x(r.start), r.end === null ? 100 : x(r.end)], ...r.extra.map((e) => [x(e[0]), x(e[1])])];
    const done = r.end !== null && r.extra.every((e) => e[1] <= T);
    const last = Math.max(r.end || T, ...r.extra.map((e) => e[1]));
    return { name: r.name, depth, model: r.model, effort: r.effort, state: done ? "done" : "working", segs, tok: r.tok, cost: { v: r.costv, kind: "ok" }, parent: r.parent ? byKey[r.parent].name : null,
      age: done ? S.tl_ran.replace("{n}", Math.max(1, Math.round((last - (r.extra.length ? r.extra[r.extra.length - 1][0] : r.start)) / 60))) : S.tl_last.replace("{n}", r.key === "m" ? 2 : 4 + (r.start % 23)),
      by: depth > 2 && r.parent ? byKey[r.parent].name : null };
  };
  const out = [];
  const walk = (r, depth) => {
    out.push(row(r, depth));
    const ks = kids(r.key);
    const isOld = (k) => sub(k).every((q) => q.end !== null && Math.max(q.end, ...q.extra.map((e) => e[1])) < T - opt.keep);
    const fold = ks.length > 4 ? ks.filter(isOld) : [];
    if (fold.length) {
      const all = fold.flatMap(sub);
      const open = (opt.open || []).includes(r.key);
      const segs = all.flatMap((q) => [[x(q.start), x(q.end)], ...q.extra.map((e) => [x(e[0]), x(e[1])])]);
      out.push({ fold: all.length, open, depth: depth + 1, model: "Sonnet 5.5", state: "done", segs, tok: all.reduce((a, q) => a + q.tok, 0), cost: { v: all.reduce((a, q) => a + q.costv, 0), kind: "ok" }, age: "" });
      if (open) fold.forEach((k) => walk(k, depth + 1));
    }
    ks.filter((k) => !fold.includes(k)).forEach((k) => walk(k, depth + 1));
  };
  walk(runs[0], 0);
  return out;
}
function bucketsFrom(runs, T, x0, size, n, openFrac) {
  return Array.from({ length: n }, (_, i) => {
    const a = x0 + i * size, b = Math.min(a + size, T); const by = {};
    runs.forEach((r) => [[r.start, r.end === null ? T : r.end], ...r.extra].forEach(([s, e]) => { const ov = Math.max(0, Math.min(b, e) - Math.max(a, s)); if (ov > 0) by[r.model] = (by[r.model] || 0) + ov / 60 * RATE[r.model] * (0.75 + 0.5 * Math.abs(Math.sin(i * 1.7 + s))); }));
    Object.keys(by).forEach((m) => (by[m] = by[m] / ((b - a) / 60)));
    return i === n - 1 && openFrac ? { by, open: openFrac } : { by };
  });
}
function manyPage(open) {
  const T = 3600, runs = MANY.map((r) => ({ ...r }));
  const rows = buildRows(runs, T, { span: 3600, x0: 0, keep: 120, open: open ? ["dr"] : [] });
  const buckets = bucketsFrom(runs, T, 0, 60, 60);
  const xl = [[0, "2:00", 1], [16.7, "2:10"], [33.3, "2:20", 1], [50, "2:30"], [66.7, "2:40", 1], [83.3, "2:50"], [100, S.tl_now, 1]];
  const tot = runs.reduce((a, r) => a + r.tok, 0), cost = runs.reduce((a, r) => a + r.costv, 0), working = runs.filter((r) => r.end === null).length;
  const h = { state: "working", mode: "live", branch: "feature/ledger-sync", sub: f2("hd_sub_live", { start: "2:00 PM", dur: "60 minutes" }), sel: "feature/ledger-sync, 2:00 PM" };
  const t = { cost: money(cost), costD: "$1.12 in the last minute", spark: buckets.map((b) => Object.values(b.by).reduce((a, c) => a + c, 0)), tokens: tok(tot), tokD: "141K in the last minute", cache: "84%", cacheD: "86% in the last minute", hit: 0.84, working, finished: runs.length - working, agD: `${runs.length - working} finished, ${runs.length} runs in all` };
  return m2Page(`${liveHead(h)}${tilesRow(t)}${whoCard({ buckets, rows, xl, grid: [16.7, 33.3, 50, 66.7, 83.3] })}${lowerCards({ req: liveReq({ hour: 2 }) })}`);
}
const m2Many = () => manyPage(false);
const m2ManyOpen = () => manyPage(true);

// ---------- Pass 2: an 8-hour session (9:00 AM to 5:04 PM, 10-minute buckets) ----------
function longRuns() {
  const H = (h, m) => ((h - 9) * 60 + m) * 60; // seconds from 9:00
  const spec = [["m", null, null, "Opus 5.5", "high", H(9, 2), null]];
  const lead = (k, a, s, e, kidsN, model = "Sonnet 5.5") => { spec.push([k, a, "m", "Opus 5.5", "high", s, e]); for (let i = 0; i < kidsN; i++) { const ks = s + 600 + i * Math.floor((e - s - 900) / kidsN); spec.push([k + i, i % 3 === 0 ? "scout" : "fast-worker", k, i % 3 === 0 ? "Haiku 5.5" : model, "medium", ks, ks + 300 + (i % 4) * 120]); } };
  lead("a", "deep-reasoner", H(9, 5), H(10, 50), 9);
  spec.push(["tw1", "tech-writer", "m", "Sonnet 5.5", "high", H(10, 55), H(11, 10)]);
  lead("b", "designer", H(11, 20), H(12, 5), 4);
  lead("c", "deep-reasoner", H(13, 5), H(13, 55), 6);
  spec.push(["tw2", "tech-writer", "m", "Sonnet 5.5", "high", H(14, 0), H(14, 12)]);
  spec.push(["d", "deep-reasoner", "m", "Opus 5.5", "high", H(14, 10), null]);
  for (let i = 0; i < 8; i++) { const ks = H(14, 25) + i * 780; spec.push(["d" + i, i % 3 === 0 ? "scout" : "fast-worker", "d", i % 3 === 0 ? "Haiku 5.5" : "Sonnet 5.5", "medium", ks, ks + 360]); }
  spec.push(["e", "designer", "d", "Opus 5.5", "high", H(15, 30), null]);
  spec.push(["f", "judge", "e", "Opus 5.5", "medium", H(16, 40), null]);
  spec.push(["g", "scout", "f", "Haiku 5.5", "medium", H(16, 58), null]);
  spec.push(["tw3", "tech-writer", "m", "Sonnet 5.5", "high", H(16, 20), H(16, 25), [[H(17, 1), H(17, 3)]]]);
  return scen(spec);
}
function m2Long() {
  const T = 484 * 60, runs = longRuns();
  const rows = buildRows(runs, T, { span: T, x0: 0, keep: 120 });
  const buckets = bucketsFrom(runs, T, 0, 600, 49, 0.4);
  const xl = [[0, "9 AM", 1], [12.4, "10"], [24.8, "11", 1], [37.2, "12 PM"], [49.6, "1", 1], [62, "2"], [74.4, "3", 1], [86.8, "4"], [100, S.tl_now, 1]];
  const tot = runs.reduce((a, r) => a + r.tok, 0), cost = runs.reduce((a, r) => a + r.costv, 0), working = runs.filter((r) => r.end === null).length;
  const h = { state: "working", mode: "live", branch: "feature/quarter-close", sub: f2("hd_sub_live", { start: "9:02 AM", dur: "8 hours 2 minutes" }), sel: "feature/quarter-close, 9:02 AM" };
  const t = { cost: money(cost), costD: "$0.61 in the last minute", spark: buckets.map((b) => Object.values(b.by).reduce((a, c) => a + c, 0)), tokens: tok(tot), tokD: "98K in the last minute", cache: "83%", cacheD: "88% in the last minute", hit: 0.83, working, finished: runs.length - working, agD: `${runs.length - working} finished, ${runs.length} runs in all` };
  return m2Page(`${liveHead(h)}${tilesRow(t)}${whoCard({ buckets, rows, xl, grid: [12.4, 24.8, 37.2, 49.6, 62, 74.4, 86.8], axis: f2("tl_axis_avg", { n: 10 }) })}${lowerCards({ req: liveReq({ hour: 5 }).map((q) => ({ ...q, t: q.t.replace(':59', ':03') })) })}`);
}

// ---------- Pass 3 ----------
const P1 = () => m2Live();
const m2Unpriced = () => m2Live({ unpriced: true });
const m2Ended = () => m2Live({ head: "ended", top: switchNotice() });
const OTHER = [["Saltmarsh", "fix/login-timeout", "5:48 PM", "working"], ["Driftwood", "main", "6:30 PM", "idle"]];
function otherCard() {
  return `<section class="card m2-other"><header><h2>${S2.nr_other_h}</h2><span class="q">${S2.nr_other_q}</span></header><ul class="well m2-olist">${OTHER.map((o) => `<li><a href="#"><span class="m2-on">${o[1]}</span><span class="muted m2-op">${o[0]}, ${o[2]}</span>${rs(o[3])}<span class="chev" aria-hidden="true">&#x203A;</span></a></li>`).join("")}</ul></section>`;
}
const emptyMark = () => `<span class="m2-emk" aria-hidden="true">&#x25CC;</span>`;
function plainHead(selVal) { return `<div class="ph m2-ph"><div class="m2-tt"><h1>${S.live_h1}</h1></div><div class="right">${selBtn(selVal, false, true)}</div></div>`; }
function m2Nothing(withOther) {
  return m2Page(`${plainHead(S2.sel_none)}<section class="card m2-empty">${emptyMark()}<h2>${S2.nr_h}</h2><p class="muted">${S2.nr_b}</p>
    <div class="m2-acts"><a class="btn primary" href="#">${S2.nr_last}</a><span class="muted">${f2("nr_last_meta", { branch: "feature/quarter-close", time: "6:52 PM" })}</span></div></section>${withOther ? otherCard() : ""}`, { idleNav: !withOther });
}
const m2NothingOther = () => m2Nothing(true);
const m2NothingAlone = () => m2Nothing(false);
function m2NoSessions() {
  return m2Page(`${plainHead(S2.sel_none)}<section class="card m2-empty">${emptyMark()}<h2>${S2.ns_h}</h2><p class="muted">${S2.ns_b}</p>
    <div class="cmdrow"><code class="well cmd">${S2.ns_cmd}</code><button class="btn">${S.lk_copy}</button></div></section>`, { idleNav: true });
}
function m2Gone() {
  return m2Page(`${plainHead(S2.sel_pick)}<div class="raised err m2-gone" role="alert"><h2><span aria-hidden="true" class="errm">&#x2715;</span>${S2.gone_h}</h2><p>${S2.gone_b}</p>
    <div class="m2-acts"><a class="btn primary" href="#">${S2.gone_open}</a><span class="muted">${f2("ss_opt", { branch: "feature/quarter-close", time: "6:10 PM" })}</span></div><p><a class="m2-tl" href="#">${S2.gone_all}</a></p></div>`);
}
function sessList() {
  const opt = (b, t, p, st, cur) => `<li role="option" aria-selected="${!!cur}"${cur ? ' class="on"' : ""}><span class="pk-n">${f2("ss_opt", { branch: b, time: t })}</span>${cur ? '<span class="ok" aria-hidden="true">&#x2713;</span>' : ""}<span class="pk-s">${rs(st)}${p ? `<small class="muted">${p}</small>` : ""}</span></li>`;
  return `<div role="listbox" aria-labelledby="ss-h" class="m2-sl"><div role="group" aria-labelledby="ss-g1"><div class="m2-gh" id="ss-g1" role="presentation">${S2.ss_this}</div><ul class="pk-list" role="presentation">
    ${opt("feature/quarter-close", "6:10 PM", "", "working", true)}${opt("feature/invoice-export", "7:02 PM", "", "working")}</ul></div>
    <div role="group" aria-labelledby="ss-g2"><div class="m2-gh" id="ss-g2" role="presentation">${S2.ss_other}</div><ul class="pk-list" role="presentation">
    ${OTHER.map((o) => opt(o[1], o[2], o[0], o[3])).join("")}</ul></div></div><a class="m2-all" href="#">${S2.ss_all}<span aria-hidden="true"> &#x2192;</span></a>`;
}
function m2Select() {
  const pop = `<div class="pk-scrim only-phone" aria-hidden="true"></div><div class="pk-pop m2-pop" role="dialog" aria-labelledby="ss-h"><header class="pk-h"><h2 id="ss-h">${S2.ss_h}</h2><button class="btn quiet x only-phone" aria-label="${S.ed_close}"><span aria-hidden="true">&#x2715;</span></button></header>${sessList()}</div>`;
  return m2Live({ selOpen: true, after: pop });
}
