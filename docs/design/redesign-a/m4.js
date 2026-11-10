// M4 Setup passes 10 to 12 (designer boards, November 9). Builds on a.js, a2.js, ui.js, m2.js, m3.js. Prefix m4 everywhere.
const ANN4 = (t) => `<p class="m2-ann m3-ann" aria-hidden="true">${t}</p>`;
const PROJ = "Tidewater reporting";
const TOFIX_N = "7";
const LOCK4 = (lab) => `<svg class="lock m4-lock" viewBox="0 0 12 14" width="11" height="13" ${lab ? `role="img" aria-label="${lab}"` : 'aria-hidden="true"'}><rect x="1.5" y="6" width="9" height="7" rx="1.5" fill="currentColor"/><path d="M3.5 6V4.2a2.5 2.5 0 0 1 5 0V6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>`;
const DASH = '<span class="muted m4-dash" aria-label="none">&#x2013;</span>';
const ORDER = ["invalid", "lowered", "ignored", "overridden", "unknown", "in-effect", "default"];
const chips = (sts) => sts.slice().sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b)).map((c) => stw(c)).join("");
const badge = (t) => `<span class="badge m4-badge">${t}</span>`;
const scl = (k) => k === "shell" ? `<span class="scope"><b>${S.sc_shell}</b><small>${S4.sc_shell_2}</small></span>` : k === "parent" ? `<span class="scope"><b>${S4.ins_parent}</b><small>${S.sc_project_2}</small></span>` : sc(k);

// ---------- Page shell ----------
function P4(cur, title, body, o = {}) {
  let h = m3Page(cur, title, body, o);
  const n = o.count === undefined ? TOFIX_N : o.count;
  h = h.replace(`<span class="end">${S.tofix_count}</span>`, n ? `<span class="end m4-cnt">${n}<span class="sr"> to fix</span></span>` : "")
    .replace(`<span class="cnt">${S.tofix_count}<span class="sr"> to fix</span></span>`, n ? `<span class="cnt">${n}<span class="sr"> to fix</span></span>` : "")
    .replace('class="shell a m2 m3"', `class="shell a m2 m3 m4${o.cls ? " " + o.cls : ""}"`);
  return h;
}
function crumb4(cur) { return `<nav class="m4-crumb" aria-label="Breadcrumb"><a href="#">${S.su_h1}</a><span aria-hidden="true">/</span><span aria-current="page">${cur}</span></nav>`; }
function cardHead(title, o = {}) { return `<header><h2${o.id ? ` id="${o.id}"` : ""}>${o.mark || ""}${title}</h2>${o.n !== undefined ? `<span class="m4-n num">${o.n}</span>` : ""}${o.q ? `<span class="q">${o.q}</span>` : ""}${o.right ? `<span class="right">${o.right}</span>` : ""}</header>`; }

// ---------- Pass 10: Your setup ----------
const SC_ORDER = ["managed", "cli", "shell", "local", "project", "user", "plugin"];
const NV = "nv";
const PARTS = [
  { k: "settings", runs: S4.su_r_settings, sts: ["invalid", "lowered", "in-effect"], sc: { managed: S4.su_cell_value, cli: NV, shell: S4.su_cell_value, local: f4("su_cell_values", { n: 2 }), project: f4("su_cell_values", { n: 3 }), user: f4("su_cell_values", { n: 4 }) } },
  { k: "agents", runs: S4.su_r_agents, sts: ["ignored", "in-effect"], unread: 1, sc: { cli: NV, project: f4("su_cell_agents", { n: 3 }), user: f4("su_cell_agents", { n: 2 }), plugin: "linter" } },
  { k: "instr", runs: S4.su_r_instr, sts: ["unknown", "in-effect"], sc: { local: "CLAUDE.local.md", project: f4("su_cell_files", { n: 3 }), user: "CLAUDE.md" } },
  { k: "rules", runs: S4.su_r_rules, sts: ["in-effect"], sc: { project: "sql.md", user: "writing.md" } },
  { k: "skills", runs: S4.su_r_skills, sts: ["in-effect"], sc: { project: f4("su_cell_skills", { n: 3 }), user: S4.su_cell_skill, plugin: S4.su_cell_skill } },
  { k: "hooks", runs: S4.su_r_hooks, sts: ["in-effect"], sc: { project: f4("su_cell_hooks", { n: 2 }), user: S4.su_cell_hook } },
  { k: "perms", runs: S4.su_r_perms, sts: ["in-effect"], sc: { local: f4("su_cell_rules", { n: 4 }), project: f4("su_cell_rules", { n: 6 }), user: f4("su_cell_rules", { n: 2 }) } },
  { k: "mcp", runs: S4.su_r_mcp, sts: ["invalid", "in-effect"], sc: { project: f4("su_cell_servers", { n: 2 }), user: f4("su_cell_servers", { n: 2 }) } },
  { k: "plugins", runs: S4.su_r_plugins, sts: ["unknown", "in-effect"], sc: { user: "lint-kit, team-tools" } },
  { k: "style", runs: S4.su_r_style, sts: ["default"], sc: {} },
];
function mapRow(p, on) {
  const cell = (v) => v === NV ? `<span class="muted m4-nv">${S.su_nv}</span>` : v === "nr" ? `<span class="muted m4-nv">${S4.su_nr}</span>` : v ? `<span>${v}</span>` : DASH;
  const unread = p.unread ? `<span class="m4-unread"><span aria-hidden="true" class="errm">&#x2715;</span>${f4(p.unread > 1 ? "su_unread_n" : "su_unread", { n: p.unread })}</span>` : "";
  const status = p.nv ? DASH : p.none ? `<span class="muted">${DASH}</span>` : `<span class="sts">${chips(p.sts)}</span>`;
  const cols = on === true || on === "cols";
  const chipsPh = on && !p.none ? `<div class="chips m4-chips${cols ? " only-phone" : ""}">${SC_ORDER.filter((s) => p.sc[s]).map((s) => `<span class="chip"><b>${s === "shell" ? S.sc_shell : S["sc_" + s]}</b> ${p.sc[s] === NV ? S.su_nv : p.sc[s] === "nr" ? S4.su_nr : p.sc[s]}</span>`).join("") || `<span class="muted m4-none">${S4.sc_none}</span>`}</div>` : "";
  if (cols) return `<tr role="row"><th scope="row" role="rowheader"><a href="#">${S["sf_" + p.k]}</a><span class="m4-runs m4-runs2">${p.runs}</span>${unread}${chipsPh}</th>
    <td role="cell" class="stc">${status}</td>${SC_ORDER.map((s) => `<td role="cell" class="hp scol">${cell(p.sc[s])}</td>`).join("")}</tr>`;
  return `<tr role="row"><th scope="row" role="rowheader"><a href="#">${S["sf_" + p.k]}</a></th><td role="cell" class="runs"><span class="m4-runs">${p.runs}</span>${unread}${chipsPh}</td>
    <td role="cell" class="stc">${status}</td></tr>`;
}
function mapTable(parts, on) {
  const cols = on === true || on === "cols";
  const head = cols ? `<th role="columnheader">${S.su_col_what}</th><th role="columnheader">${S.su_col_status}</th>${SC_ORDER.map((s) => `<th role="columnheader" class="hp scol">${scl(s)}</th>`).join("")}`
    : `<th role="columnheader">${S.su_col_what}</th><th role="columnheader">${S.su_col_runs}</th><th role="columnheader">${S.su_col_status}</th>`;
  return `<div class="well wide m4-mapw"><table role="table" class="t setup m4-map${cols ? " on" : on ? " chipmode" : ""}"><thead><tr role="row">${head}</tr></thead><tbody>${parts.map((p) => mapRow(p, on)).join("")}</tbody></table></div>`;
}
function setupHead(on, sub) {
  return `<div class="ph m2-ph m4-ph"><div class="m2-tt"><h1>${S.su_h1}</h1><p class="sub">${sub || f4("su_sub", { project: PROJ })}</p></div>
    <div class="right"><label class="switch-l m4-switch"><button class="switch" role="switch" aria-checked="${!!on}"><span></span></button>${S.su_switch}</label></div></div>`;
}
function mapCard(parts, on, o = {}) {
  return `<section class="card m4-mapc" aria-labelledby="map-h">${cardHead(S.su_card_h, { id: "map-h", q: S4.su_card_q })}${o.pre || ""}${mapTable(parts, on)}</section>`;
}
const m4Map = (on) => P4("setup", S.su_h1, `${setupHead(on)}${mapCard(PARTS, on)}`);
function m4MapStates() {
  const rows = [
    { ...PARTS[1] },
    { k: "skills", runs: S4.su_none_skills, sts: [], none: true, sc: {} },
    { k: "plugins", runs: S4.su_long_plugins, sts: ["unknown", "in-effect"], sc: { user: "lint-kit, quarterly-close-reporting-toolkit, team-tools, sql-helpers" } },
    { k: "mcp", runs: S4.su_nv_part, sts: [], nv: true, sc: { project: "nr", local: "nr" } },
  ];
  const unl = PARTS.map((p) => ({ ...p, sc: Object.fromEntries(Object.entries(p.sc).map(([k, v]) => [k, ["local", "project"].includes(k) ? "nr" : v])) }));
  unl[0] = { ...unl[0], runs: S4.su_r_settings_unl, sts: ["invalid", "in-effect"] };
  const fr = (lab, html) => `<section class="m2-frame" aria-label="${lab}">${ANN4(lab)}${html}</section>`;
  return P4("setup", S.su_h1, `${setupHead("chips")}
    ${fr("Row states, Switch on (direction B, chips): Couldn't read 1 file, nothing found, long values, a part Bar Tab can't see", mapCard(rows, "chips"))}
    ${fr("A project not on Bar Tab's list: project scopes read \"Not read here\" (open question 4)", `<p class="raised-line m4-nline"><span class="st unknown">${S.st_unknown}</span><span>${f4("su_unlisted", { project: PROJ })}</span><a href="#">${S4.su_unlisted_link}</a></p>${mapCard(unl.slice(0, 5), "chips")}`)}`);
}
function m4MapLoading() {
  const bones = `<div class="well wide" aria-hidden="true"><div class="m4-bones-map">${PARTS.map(() => `<div><span class="bone" style="width:96px"></span><span class="bone" style="width:220px"></span><span class="bone" style="width:80px;height:20px"></span></div>`).join("")}</div></div>`;
  const fr = (lab, html) => `<section class="m2-frame" aria-label="${lab}">${ANN4(lab)}${html}</section>`;
  return P4("setup", S.su_h1, `${setupHead(false)}
    ${fr("First load: bones at the loaded row height, one screen-reader line", `<section class="card m4-mapc" aria-busy="true">${cardHead(S.su_card_h, { q: S4.su_card_q })}<span class="sr">${S4.su_ld}</span>${bones}</section>`)}
    ${fr("Card error: the setup map didn't answer", `<section class="card m4-mapc">${cardHead(S.su_card_h, { q: S4.su_card_q })}<div class="raised err m3-err" role="alert"><h3><span aria-hidden="true" class="errm">&#x2715;</span>${S4.su_err_h}</h3><p>${S4.su_err_b}</p><div><button class="btn">${S4.su_err_try}</button></div></div></section>`)}`);
}

// ---------- Pass 11: list and inspector ----------
function listCard(part, items, sel, o = {}) {
  const row = (it) => `<li><a href="#"${it.n === sel ? ' aria-current="true"' : ""}><span class="it-n${it.mono ? " mono" : ""}">${it.n}${it.lock ? " " + LOCK4(S4.ro_h) : ""}</span><span class="it-v${it.vmono ? " mono" : ""}">${it.v}</span>${it.s && !(o.quiet && it.s === "in-effect") ? stw(it.s) : ""}</a></li>`;
  const groups = o.groups ? o.groups.map((g) => `<li class="m4-lg" role="presentation"><span id="lg-${g.id}">${g.h}</span><span class="num muted">${g.n}</span></li>${g.items.map(row).join("")}${g.more ? `<li class="m4-more" role="presentation"><button class="btn">${f4("sp_more", { n: g.more })}</button></li>` : ""}`).join("") : items.map(row).join("");
  return `<nav class="card slist m4-list" aria-labelledby="ls-h">${cardHead(S["sf_" + part], { id: "ls-h", n: o.n !== undefined ? o.n : items.length })}${o.pre || ""}${o.jump ? `<p class="m4-jump"><span class="muted">${S4.sp_jump}</span>${o.jump.map((j) => `<a href="#" class="chip">${j[0]} <span class="num">${j[1]}</span></a>`).join("")}</p>` : ""}${o.empty || `<ul class="well items m4-items">${groups}</ul>`}${o.foot ? `<p class="m4-lfoot muted">${o.foot}</p>` : ""}</nav>`;
}
function whereWell(rows) {
  return `<h3>${S.in_where_h}</h3><ul class="well m4-where">${rows.map((r) => `<li><span class="w-sc">${scl(r.sc)}</span><code class="w-key mono">${r.key}</code>${r.nv ? `<span class="w-val muted m4-nv">${r.nv}</span>` : `<b class="w-val">${r.val}</b>`}<span class="w-st">${r.s && !r.nv ? stw(r.s) : ""}${r.badge ? badge(r.badge) : ""}</span>${r.file ? `<small class="w-file muted mono">${r.file}</small>` : ""}</li>`).join("")}</ul>`;
}
const factDl = (rows, h) => `${h === false ? "" : `<h3>${h || S4.in_details_h}</h3>`}<dl class="m4-dl">${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>`;
function roBox(text, o = {}) {
  return `<div class="raised ro m4-ro">${LOCK4()}<div><p class="m4-roh">${S4.ro_h}</p><p>${text}</p>${o.more ? `<p class="muted small">${o.more}</p>` : ""}${o.cmd ? `<div class="cmdrow m4-cmd"><code class="well cmd">${o.cmd}</code><button class="btn">${S4.ro_copy_cmd}</button></div>` : ""}${o.path ? `<div class="m4-path"><code class="mono">${o.path}</code><button class="btn">${S.in_copy}</button></div>` : ""}</div></div>`;
}
function insp(o) {
  const back = `<a class="m4-back only-phone" href="#"><span aria-hidden="true">&#x2190;</span> ${o.part}</a>`;
  return `<section class="card insp m4-insp" aria-labelledby="in-h">${back}<header class="in-h"><h2 id="in-h"${o.mono ? ' class="mono"' : ""}>${o.name}</h2>${o.s ? stw(o.s) : ""}${o.badge ? badge(o.badge) : ""}</header>
    ${o.runs ? `<p class="in-runs m4-runsl">${o.runs}</p>` : ""}${o.set ? `<p class="in-set">${o.set}</p>` : ""}${o.link ? `<p class="m4-link"><span aria-hidden="true">&#x21AA;</span> ${o.link}</p>` : ""}
    ${o.check || ""}${o.body || ""}${o.where ? whereWell(o.where) : ""}
    ${o.why ? `<div class="raised why"><h3>${S.in_why_h}</h3><p>${o.why}</p>${o.conf ? `<p class="muted small">${o.conf}</p>` : ""}</div>` : ""}
    ${o.usage ? `<p class="muted small m4-usage">${o.usage}</p>` : ""}
    ${o.ro || ""}
    ${o.acts === false ? "" : `<div class="acts">${o.acts || `<button class="btn">${S.in_copy}</button>`}</div>`}</section>`;
}
function surf(part, sub, list, inspHtml, o = {}) {
  return P4(o.cur || "setup", S["sf_" + part], `<div class="ph m2-ph m4-sph${o.listPage ? "" : " m4-hph"}"><div class="m2-tt">${crumb4(S["sf_" + part])}<h1>${S["sf_" + part]}</h1><p class="sub">${sub}</p></div></div>
    <div class="surf m4-surf${o.listPage ? " m4-listpage" : " m4-picked"}">${list}${inspHtml}</div>`);
}

// Settings
const SET_ITEMS = [
  { n: S.sp_model, v: "Opus 5.5", s: "in-effect" }, { n: S.sp_effort, v: "high", s: "lowered" }, { n: S.sp_cap, v: "high", s: "in-effect" }, { n: S.sp_think, v: "On", s: "default" },
  { n: S.sp_compact, v: "1M tokens", s: "default" }, { n: S.sp_cache, v: S.sp_v_cache, s: "unknown" }, { n: S.sp_fallback, v: S.sp_v_fallback, s: "default" }, { n: S.sp_allowed, v: S.sp_v_allowed, s: "in-effect", lock: true },
];
const SET_OTHER = [{ n: "cleanupPeriodDays", v: "-1", s: "invalid", mono: true, vmono: true, lock: true }, { n: "includeCoAuthoredBy", v: "false", s: "in-effect", mono: true, vmono: true }, { n: "spinnerTipsEnabled", v: "false", s: "in-effect", mono: true, vmono: true }, { n: "env.DOCS_TOKEN", v: "&#x2022;&#x2022;&#x2022;&#x2022;", s: "in-effect", mono: true, vmono: true }];
const setList = (sel) => listCard("settings", [], sel, { n: 12, groups: [{ id: "m", h: S4.sp_g_model, n: 8, items: SET_ITEMS }, { id: "o", h: S4.sp_g_other, n: 4, items: SET_OTHER }] });
function m4Settings() {
  return surf("settings", f4("sp_sub_settings", { project: PROJ }), setList(S.sp_effort), insp({
    part: S.sf_settings, name: S.sp_effort, s: "lowered", runs: S.in_runs, set: S4.in_set_effort,
    where: [{ sc: "local", key: "env.CLAUDE_CODE_EFFORT_LEVEL", val: "xhigh", s: "lowered", file: "settings.local.json:3" }, { sc: "shell", key: "CLAUDE_CODE_EFFORT_LEVEL", nv: S4.in_nset_shell, badge: S4.in_assumed }, { sc: "cli", key: "--effort", nv: S.su_nv }, { sc: "project", key: "effortLevel", val: "medium", s: "overridden", file: "settings.json:7" }, { sc: "user", key: "effortLevel", val: "xhigh", s: "ignored", file: "~/.claude/settings.json:3" }],
    why: S.in_why, conf: S.in_conf, usage: S.in_usage }));
}
function m4SettingsShell() {
  return surf("settings", f4("sp_sub_settings", { project: PROJ }), setList(S.sp_model), insp({
    part: S.sf_settings, name: S.sp_model, s: "in-effect", badge: S4.in_assumed, runs: S4.in_runs_model, set: S4.in_set_model,
    where: [{ sc: "cli", key: "--model", nv: S.su_nv }, { sc: "shell", key: "ANTHROPIC_MODEL", val: "claude-opus-5-5", s: "in-effect", badge: S4.in_assumed }, { sc: "project", key: "model", val: "sonnet", s: "overridden", file: "settings.json:2" }, { sc: "user", key: "model", val: "opus", s: "overridden", file: "~/.claude/settings.json:2" }],
    body: `<p class="m4-note muted small">${S4.in_shell_note}</p>`, why: S4.in_why_model, conf: S4.in_conf_assumed, usage: S4.in_usage_model }));
}

// Agents (setup surface)
const AG_ITEMS = [{ n: "builder", v: S.sc_user, s: "in-effect" }, { n: "judge", v: S.sc_project, s: "lowered" }, { n: "reviewer", v: S.sc_project, s: "in-effect" }, { n: "migrator", v: S.sc_project, s: "in-effect" }, { n: "release-notes", v: S.sc_user, s: "in-effect" }, { n: "linter", v: "Plugin lint-kit", s: "ignored", lock: true }];
function agJudge(o = {}) {
  return insp({ part: o.part || S.sf_agents, name: "judge", s: "lowered", runs: S4.ag_runs_judge, set: S4.ag_set_judge,
    check: `<div class="raised m4-chk"><p>${st("lowered", "Lowered")} ${S4.ag_check_judge}</p><p class="muted small">${S4.ag_check_judge_why}</p></div>`,
    body: factDl([[S4.ag_f_desc, S4.ag_v_desc_judge], [S4.ag_f_model, `${sw("Opus 5.5")}Opus 5.5 <small class="muted mono">line 4</small>`], [S4.ag_f_effort, `high <small class="muted mono">line 5</small>`], [S4.ag_f_tools, `<span class="mono">${S4.ag_v_tools_judge}</span>`], [S4.ag_f_color, `<span class="m4-sw" style="background:var(--agent-purple)" aria-hidden="true"></span>purple`]]),
    where: [{ sc: "project", key: ".claude/agents/judge.md", val: "judge", s: "in-effect", file: "line 2" }, { sc: "user", key: "~/.claude/agents/judge.md", val: "judge", s: "overridden", file: "line 2" }],
    usage: S4.ag_runs_cost, acts: `<button class="btn">${S.in_copy}</button>${o.review ? "" : `<a class="btn quiet" href="#">${S.nav_agents} <span aria-hidden="true">&#x2192;</span></a>`}` });
}
const agList = (sel, o = {}) => listCard("agents", AG_ITEMS, sel, o);
const m4Agents = () => surf("agents", f4("sp_sub_agents", { project: PROJ }), agList("judge"), agJudge());
function linterInsp(o = {}) {
  return insp({ part: o.part || S.sf_agents, name: "linter", s: "ignored", runs: S4.ag_runs_linter, set: S4.ag_set_linter,
    ro: roBox(f4("ro_plugin", { plugin: "lint-kit" }), { more: S4.ro_plugin_2, path: "~/.claude/plugins/cache/team/lint-kit/1.4.2/agents/linter.md" }),
    body: `<h3>${S4.ag_ignored_h}</h3><p class="muted small m4-ig">${S4.ag_ignored_b}</p><ul class="well m4-where m4-igl">${[["permissionMode", "acceptEdits", 6], ["hooks", "1 hook", 7], ["mcpServers", "docs-search", 9]].map(([k, v, l]) => `<li><code class="w-key mono">${k}</code><b class="w-val">${v}</b><span class="w-st">${stw("ignored")}</span><small class="w-file muted mono">agents/linter.md:${l}</small></li>`).join("")}</ul>
      ${factDl([[S4.ag_f_model, `${sw("Haiku 5.5")}Haiku 5.5`], [S4.ag_f_effort, "low"], [S4.ag_f_tools, '<span class="mono">Read, Bash</span>']])}`,
    usage: o.usage || S4.ag_linter_none, acts: false });
}
const m4AgentPlugin = () => surf("agents", f4("sp_sub_agents", { project: PROJ }), agList("linter"), linterInsp());
function m4CouldntRead() {
  const pre = `<div class="raised err m4-cr" role="alert"><h3><span aria-hidden="true" class="errm">&#x2715;</span>${f4("cr_h", { n: 1 })}</h3><p>${f4("cr_b", { file: '<code class="mono">~/.claude/agents/notes.md</code>' })}</p><p class="muted small">${S4.cr_fix}</p><div><button class="btn">${S.in_copy}</button></div></div>`;
  return surf("agents", f4("sp_sub_agents", { project: PROJ }), agList("judge", { pre }), agJudge());
}

// Instructions
const INS_ITEMS = [{ n: "CLAUDE.md", v: S.sc_user, s: "in-effect" }, { n: "/work/CLAUDE.md", v: S4.ins_parent, s: "in-effect" }, { n: "CLAUDE.md", v: S.sc_project, s: "unknown", cur: true }, { n: "CLAUDE.local.md", v: S.sc_local, s: "in-effect" }, { n: "services/api/CLAUDE.md", v: S4.ins_nested, s: "in-effect" }];
function m4Instructions() {
  const imp = [[0, "CLAUDE.md", f4("ins_lines", { n: 42 }), "ok"], [1, "@docs/conventions.md", f4("ins_lines", { n: 66 }), "ok"], [2, "@docs/sql-style.md", f4("ins_lines", { n: 31 }), "ok"], [1, "@~/notes/team-glossary.md", S4.ins_imp_out, "out"], [1, "@docs/old-onboarding.md", S4.ins_imp_missing, "missing"]];
  const list = listCard("instr", [], null, { n: 5, foot: S4.ins_memory, groups: [{ id: "i", h: "", n: "", items: [] }] }).replace(/<ul class="well items m4-items">[\s\S]*?<\/ul>/, `<ol class="well items m4-items m4-ord">${INS_ITEMS.map((it, i) => `<li><a href="#"${it.cur ? ' aria-current="true"' : ""}><span class="it-n"><span class="m4-ordn num" aria-hidden="true">${i + 1}</span><span class="mono">${it.n}</span></span><span class="it-v">${it.v}</span>${stw(it.s)}</a></li>`).join("")}</ol>`);
  const chain = `<h3>${S4.ins_imports_h}</h3><ol class="well m4-chain">${imp.map(([d, p, t, k]) => `<li class="m4-d${d}${k !== "ok" ? " m4-" + k : ""}"><code class="mono">${p}</code><span class="m4-cs">${k === "ok" ? `<span class="muted">${t}</span>` : k === "out" ? `${stw("unknown")}<span class="muted small">${t}</span>` : `${stw("invalid")}<span class="muted small">${t}</span>`}</span></li>`).join("")}</ol>`;
  return surf("instr", S4.sp_sub_instr, list, insp({ part: S.sf_instr, name: "CLAUDE.md", mono: true, s: "unknown", runs: S4.ins_runs, set: S4.ins_set, body: chain, why: S4.ins_why, conf: S.in_conf }));
}
// Rules
function m4Rules() {
  const items = [{ n: "writing.md", v: S.sc_user + ", always", s: "in-effect", mono: true }, { n: "sql.md", v: S.sc_project + ", SQL files", s: "in-effect", mono: true }];
  return surf("rules", S4.sp_sub_rules, listCard("rules", items, "sql.md"), insp({ part: S.sf_rules, name: "sql.md", mono: true, s: "in-effect", runs: S4.ru_runs, set: S4.ru_set,
    body: `<h3>${S4.ru_globs_h}</h3><ul class="well m4-globs">${["**/*.sql", "queries/**"].map((g) => `<li><code class="mono">${g}</code></li>`).join("")}</ul>`, why: S4.ru_why, conf: S.in_conf }));
}
// Skills
function m4Skills() {
  const items = [{ n: "close-books", v: S.sc_project, s: "in-effect" }, { n: "ledger-check", v: S.sc_project, s: "in-effect" }, { n: "sql-format", v: S.sc_project, s: "in-effect" }, { n: "weekly-notes", v: S.sc_user, s: "in-effect" }, { n: "lint-kit:check-style", v: "Plugin lint-kit", s: "in-effect", lock: true }];
  return surf("skills", f4("sp_sub_skills", { project: PROJ }), listCard("skills", items, "lint-kit:check-style"), insp({ part: S.sf_skills, name: "lint-kit:check-style", s: "in-effect", runs: S4.sk_runs, set: S4.sk_set,
    ro: roBox(f4("ro_plugin", { plugin: "lint-kit" }), { path: "~/.claude/plugins/cache/team/lint-kit/1.4.2/skills/check-style/SKILL.md" }),
    body: factDl([[S4.ag_f_desc, S4.sk_v_desc], [S4.sk_call, '<code class="mono">/lint-kit:check-style</code>'], [S4.ag_f_tools, '<span class="mono">Read, Grep</span>']]), acts: false }));
}
// Hooks
function m4Hooks() {
  const items = [{ n: S4.hk_name_1, v: S.sc_project, s: "in-effect" }, { n: S4.hk_name_2, v: S.sc_project, s: "in-effect" }, { n: S4.hk_name_3, v: S.sc_user, s: "in-effect" }];
  return surf("hooks", S4.sp_sub_hooks, listCard("hooks", items, S4.hk_name_1), insp({ part: S.sf_hooks, name: S4.hk_name_1, s: "in-effect", runs: S4.hk_runs, set: S4.hk_set,
    body: factDl([[S4.hk_f_event, '<span>${S4.hk_event_v}</span> <code class="mono muted">PostToolUse</code>'], [S4.hk_f_matcher, '<code class="mono">Bash</code>'], [S4.hk_f_cmd, '<code class="well cmd m4-cmdv">./scripts/notify.sh --channel ops --token &#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;</code>']]) + `<p class="muted small m4-mask">${S4.hk_masked}</p><details class="m4-raw"><summary>${S4.in_raw}</summary></details>`, conf: null }));
}
// Permissions, long list
function m4Perms() {
  const deny = ["Read(./.env)", "Read(./secrets/**)", "Bash(rm -rf:*)", "Bash(git push --force:*)", "WebFetch(domain:pastebin.com)", "Bash(curl:*)"];
  const ask = ["Bash(git push:*)", "Bash(npm publish:*)", "Edit(./migrations/**)", "Bash(psql:*)"];
  const allow = ["Bash(npm run test:*)", "Bash(npm run lint)", "Bash(make test)", "Bash(git status)", "Bash(git diff:*)", "Read(./docs/**)", "Edit(./src/**)", "Edit(./queries/**)"];
  const it = (r, s, sc) => ({ n: r, v: sc, s, mono: true });
  const groups = [{ id: "d", h: S4.sp_g_deny, n: 28, items: deny.map((r, i) => it(r, "in-effect", i < 2 ? S.sc_project : S.sc_user)), more: 22 },
    { id: "a", h: S4.sp_g_ask, n: 12, items: ask.map((r) => it(r, "in-effect", S.sc_project)), more: 8 },
    { id: "l", h: S4.sp_g_allow, n: 160, items: [it("Bash(npm run build", "invalid", S.sc_local), ...allow.map((r, i) => it(r, "in-effect", i < 3 ? S.sc_local : S.sc_project))], more: 151 }];
  return surf("perms", S4.sp_sub_perms, listCard("perms", [], "Bash(npm run test:*)", { n: 200, quiet: true, groups, jump: [[S4.sp_g_deny, 28], [S4.sp_g_ask, 12], [S4.sp_g_allow, 160]] }),
    insp({ part: S.sf_perms, name: "Bash(npm run test:*)", mono: true, s: "in-effect", runs: S4.pm_runs, set: S4.pm_set, body: factDl([[S4.pm_f_tool, "Bash"], [S4.pm_f_match, '<code class="mono">npm run test:*</code>']]), why: S4.pm_why, conf: S.in_conf }));
}
// MCP
function m4Mcp() {
  const items = [{ n: "docs-search", v: S.sc_project, s: "invalid" }, { n: "tracker", v: S.sc_project, s: "in-effect" }, { n: "notes", v: S.sc_user, s: "in-effect", lock: true }, { n: "archive", v: S.sc_user, s: "invalid", lock: true }];
  return surf("mcp", S4.sp_sub_mcp, listCard("mcp", items, "notes"), insp({ part: S.sf_mcp, name: "notes", s: "in-effect", runs: S4.mc_runs, set: S4.mc_set,
    ro: roBox(S4.ro_json, { cmd: "claude mcp get notes" }),
    body: factDl([[S4.mc_f_transport, "stdio"], [S4.mc_f_cmd, '<code class="mono">npx -y @team/notes-mcp --api-key &#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;</code>'], [S4.mc_f_env, `<span class="m4-envs">${["NOTES_TOKEN", "NOTES_URL"].map((e) => `<code class="mono">${e}</code>`).join("")}</span><small class="muted">${f4("mc_f_env_v", { n: 2 })}</small>`]]), acts: false }));
}
// Plugins
function m4Plugins() {
  const items = [{ n: "lint-kit", v: S.sc_user + ", 1.4.2", s: "in-effect", lock: true }, { n: "team-tools", v: S.sc_user, s: "unknown", lock: true }];
  const contents = `<h3>${S4.pl_contents_h}</h3><ul class="well m4-pc">${[[S.sf_agents, "linter", "ignored"], [S.sf_skills, "lint-kit:check-style", "in-effect"], [S.sf_hooks, "After Edit", "in-effect"]].map(([p, n, s]) => `<li><span class="muted">${p}</span><a href="#">${n}</a>${stw(s)}</li>`).join("")}</ul>`;
  return surf("plugins", f4("sp_sub_plugins", { project: PROJ }), listCard("plugins", items, "lint-kit"), insp({ part: S.sf_plugins, name: "lint-kit", s: "in-effect", runs: S4.pl_runs, set: S4.pl_set,
    ro: roBox(f4("ro_plugin", { plugin: "lint-kit" }), { path: "~/.claude/plugins/cache/team/lint-kit/1.4.2" }), body: contents, acts: false }));
}
// Output style
function m4Style() {
  const items = [{ n: "Default", v: S4.st_builtin, s: "default" }, { n: "Proactive", v: S4.st_builtin, s: "" }, { n: "Concise", v: S4.st_builtin, s: "" }, { n: "Explanatory", v: S4.st_builtin, s: "" }, { n: "Learning", v: S4.st_builtin, s: "" }, { n: "team-voice", v: S.sc_project + ", " + S4.st_file_unused, s: "" }];
  return surf("style", S4.sp_sub_style, listCard("style", items, "Default"), insp({ part: S.sf_style, name: "Default", s: "default", runs: S4.st_runs, set: S4.st_set,
    where: [{ sc: "local", key: "outputStyle", val: "", nv: "&#x2013;" }, { sc: "project", key: "outputStyle", nv: "&#x2013;" }, { sc: "user", key: "outputStyle", nv: "&#x2013;" }], acts: false }));
}

// Read-only reasons, not-read states, empty and unknown (frames)
function frames(cur, title, list) {
  const fr = (lab, html) => `<section class="m2-frame m4-fr" aria-label="${lab}">${ANN4(lab)}${html}</section>`;
  return P4(cur, title, `<h1 class="sr">${title}</h1>${list.map(([l, h]) => fr(l, h)).join("")}`);
}
function m4ReadOnly() {
  const m6 = listCard("settings", SET_ITEMS.slice(0, 3).concat([SET_ITEMS[7]]), S.sp_effort, { n: 4 });
  return frames("setup", S.sf_settings, [
    ["Managed: lock in the list, reason with Copy path", insp({ part: S.sf_settings, name: S.sp_allowed, s: "in-effect", runs: S.ro_runs, set: S.ro_set, ro: roBox(S4.ro_managed, { path: "/Library/Application Support/ClaudeCode/managed-settings.json" }), acts: false })],
    ["Plugin: reason, how to override, Copy path", linterInsp()],
    ["User or local MCP server (~/.claude.json): reason with the claude mcp command", insp({ part: S.sf_mcp, name: "notes", s: "in-effect", runs: S4.mc_runs, set: S4.mc_set, ro: roBox(S4.ro_json, { cmd: "claude mcp get notes" }), acts: false })],
    ["Command line: no file, so no Copy path", insp({ part: S.sf_settings, name: S.sp_model, s: "unknown", runs: S.sp_v_cache, set: "", ro: roBox(S4.ro_cli), acts: false })],
    ["An item M6 makes editable: no Edit, no lock (only Allowed models has one)", m6],
  ]);
}
function m4NotRead() {
  return frames("setup", S.sf_plugins, [
    ["Plugin installed outside <config>/plugins/: Can't tell, not read here", insp({ part: S.sf_plugins, name: "team-tools", s: "unknown", runs: S4.pl_outside_runs, set: S4.pl_outside_set, body: `<div class="raised m4-nr"><p>${st("unknown", S.st_unknown)} ${S4.pl_outside}</p></div>`, acts: `<button class="btn">${S.in_copy}</button>` })],
    ["Import outside the roots: listed, not opened (see Instructions board for the chain)", `<ol class="well m4-chain m4-solo"><li class="m4-d1 m4-out"><code class="mono">@~/notes/team-glossary.md</code><span class="m4-cs">${stw("unknown")}<span class="muted small">${S4.ins_imp_out}</span></span></li></ol>`],
    ["Parent folder above home, only if the walk stops at home (open question 6)", `<ol class="well items m4-items m4-ord"><li><a href="#"><span class="it-n"><span class="mono">/CLAUDE.md</span></span><span class="it-v">${S4.nr_parent}</span>${stw("unknown")}</a></li></ol>`],
    ["MCP ${VAR} with no default: Can't tell", insp({ part: S.sf_mcp, name: "tracker", s: "unknown", runs: S4.nr_mcp_runs, set: S4.nr_mcp_set, body: `<div class="raised m4-nr"><p>${st("unknown", S.st_unknown)} ${S4.nr_env}</p></div>`, acts: false })],
    ["Single-file symlink: real path under the file", insp({ part: S.sf_agents, name: "builder", s: "in-effect", runs: S4.ag_runs_builder, set: S4.ag_set_builder, link: f4("ag_link", { path: '<code class="mono">/work/dotfiles/agents/builder.md</code>' }), acts: `<button class="btn">${S.in_copy}</button>` })],
  ]);
}
function m4Empty() {
  const em = `<div class="well m4-lempty"><p>${S4.em_skills}</p><button class="btn">${S4.em_skills_a}</button></div>`;
  const gone = `<section class="card insp m4-insp" aria-labelledby="g-h"><div class="raised m4-gone"><h2 id="g-h">${f4("gone_h", { part: S.sf_settings })}</h2><p>${S4.gone_b}</p><a class="btn" href="#">${f4("sp_back", { part: S.sf_settings })}</a></div></section>`;
  const ld = `<nav class="card slist m4-list" aria-busy="true">${cardHead(S.sf_hooks)}<span class="sr">${f4("ld_list", { part: "hooks" })}</span><ul class="well items m4-items" aria-hidden="true">${[1, 2, 3].map(() => `<li><a><span class="bone" style="width:140px"></span><span class="bone" style="width:90px"></span><span class="bone" style="width:72px;height:20px;grid-row:1/3;grid-column:2"></span></a></li>`).join("")}</ul></nav>`;
  return frames("setup", S.sf_skills, [
    ["Empty list: what would appear, and an action", listCard("skills", [], null, { n: 0, empty: em })],
    ["Unknown item: the picked item left the part on a refresh", gone],
    ["List loading", ld],
  ]);
}
const m4ListPage = () => surf("settings", f4("sp_sub_settings", { project: PROJ }), setList(S.sp_effort), insp({ part: S.sf_settings, name: S.sp_effort, s: "lowered", runs: S.in_runs, set: S4.in_set_effort, acts: false }), { listPage: true });

// ---------- Pass 12: To fix ----------
function fxRow4(r) {
  const act = r.k === "open" ? `<a class="btn" href="#">${f4("fx_open", { item: r.item })}</a>` : r.k === "path" ? `<button class="btn">${S.in_copy}</button>` : r.k === "cmd" ? `<div class="cmdrow m4-cmd"><code class="well cmd">${r.cmd}</code><button class="btn">${S4.ro_copy_cmd}</button></div>` : r.k === "cant" ? `<p class="m4-cant">${LOCK4()}<span>${S4.fx_cant_here}</span></p><a class="btn" href="#">${f4("fx_open", { item: r.item })}</a>` : "";
  return `<li class="raised fx m4-fx${r.k === "cmd" ? " m4-fxcmd" : ""}"><h3>${r.t}</h3><p class="cause">${r.c}</p><p class="muted">${r.q}</p>${act ? `<div class="m4-fxa">${act}</div>` : ""}</li>`;
}
const GMARK = { read: '<span aria-hidden="true" class="errm m4-gm">&#x2715;</span>', load: '<span aria-hidden="true" class="errm m4-gm">&#x2715;</span>', notset: '<span aria-hidden="true" class="m4-gm m4-lw">&#x25BC;</span>', cant: '<span aria-hidden="true" class="m4-gm m4-ct">?</span>' };
function fxGroup4(k, rows, o = {}) { return `<section class="card fxg m4-fxg" aria-labelledby="g-${k}">${cardHead(S["fx_g_" + k], { id: "g-" + k, mark: GMARK[k], n: o.n !== undefined ? o.n : rows.length, q: S4["fx_q_" + k] })}<ul class="fxl">${rows.map(fxRow4).join("")}</ul>${o.more ? `<div class="m4-fxmore"><button class="btn">${f4("fx_more", { n: o.more })}</button></div>` : ""}</section>`; }
const FX = {
  read: [{ t: S4.fx_ro_t, c: S4.fx_ro_c, q: S4.fx_ro_q, k: "path" }, { t: S4.fx_tr_t, c: S4.fx_tr_c, q: S4.fx_tr_q, k: "path" }],
  load: [{ t: S4.fx_ld_t, c: S4.fx_ld_c, q: S4.fx_ld_q, k: "open", item: "docs-search" }, { t: S4.fx_ld2_t, c: S4.fx_ld2_c, q: S4.fx_ld2_q, k: "cmd", cmd: "claude mcp remove archive -s user" }, { t: S4.fx_mg_t, c: S4.fx_mg_c, q: S4.fx_mg_q, k: "cant", item: "cleanupPeriodDays" }],
  notset: [{ t: S4.fx_ns1_t, c: S4.fx_ns1_c, q: S4.fx_ns1_q, k: "open", item: S.sp_effort }, { t: S4.fx_ns2_t, c: S4.fx_ns2_c, q: S4.fx_ns2_q, k: "open", item: "linter" }],
  cant: [{ t: S4.fx_ct1_t, c: S4.fx_ct1_c, q: S4.fx_ct1_q, k: "open", item: S.sp_cache }, { t: S4.fx_ct2_t, c: S4.fx_ct2_c, q: S4.fx_ct2_q, k: "open", item: "team-tools" }, { t: S4.fx_ct3_t, c: S4.fx_ct3_c, q: S4.fx_ct3_q, k: "open", item: "CLAUDE.md" }],
};
const notesCard = () => `<section class="card" aria-labelledby="g-notes">${cardHead(S.fx_notes_h, { id: "g-notes", n: 1, q: S4.fx_q_notes })}<ul class="well notes"><li>${S.fx_n2}</li></ul></section>`;
const fxHead = (n) => `<div class="ph m2-ph"><div class="m2-tt"><h1>${S.fx_h1}</h1><p class="sub">${n ? f4("fx_sub", { n, project: PROJ }) : f4("fx_sub_none", { project: PROJ })}</p></div></div>`;
const m4ToFix = () => P4("tofix", S.fx_h1, `${fxHead(7)}<div class="fxwrap m4-fxwrap">${fxGroup4("read", FX.read)}${fxGroup4("load", FX.load)}${fxGroup4("notset", FX.notset)}${fxGroup4("cant", FX.cant)}${notesCard()}</div>`);
const m4ToFixEmpty = () => P4("tofix", S.fx_h1, `${fxHead(0)}<div class="fxwrap m4-fxwrap"><section class="card empty m4-fxempty"><span class="big-ok" aria-hidden="true">&#x2713;</span><h2>${S.fx_empty_h}</h2><p class="muted">${S4.fx_empty}</p><a class="btn" href="#">${S.fx_empty_a}</a></section>${fxGroup4("cant", FX.cant.slice(0, 2))}${notesCard()}</div>`, { count: "" });
function m4ToFixLong() {
  const files = ["~/.claude/plugins/cache/team/sql-helpers/2.0.1/agents/a01.md", "agents/a02.md", "agents/a03.md", "agents/a04.md", "agents/a05.md"];
  const rows = files.map((f) => ({ t: f4("fx_long_t", { file: f.split("/").pop() }), c: f4("fx_long_c", { file: f }), q: S4.fx_long_q, k: "open", item: f.split("/").pop().replace(".md", "") }));
  return P4("tofix", S.fx_h1, `${fxHead(29)}<div class="fxwrap m4-fxwrap">${fxGroup4("read", FX.read)}${fxGroup4("load", rows, { n: 25, more: 20 })}${fxGroup4("notset", FX.notset)}${fxGroup4("cant", FX.cant)}</div>`, { count: "29" });
}

// ---------- Pass 12: Agents setup half ----------
function agTable4(sel) {
  const rows = [["builder", S.sc_user, "overridden", "Overridden", "$240.85"], ["Main session", S.ag_main_src, "lowered", "Lowered", "$62.61"], ["reviewer", S.sc_project, "overridden", "Overridden", "$14.70"], ["judge", S.sc_project, "lowered", "Lowered", "$9.12"], ["scribe", S.sc_user, "overridden", "Overridden", "$0.33"], ["Explore", S3.ag_src_none, "default", S.st_default, "$0.05"]];
  const none = [["migrator", S.sc_project], ["release-notes", S.sc_user], ["linter", "Plugin lint-kit"]];
  const link = (n) => n === "Main session" || n === "Explore" ? `<span class="m3-an">${n}</span>` : `<a href="#" class="m4-an">${n}</a>`;
  const r = (n, s, c, cost) => `<tr${n === sel ? ' class="picked" aria-current="true"' : ""}><td>${link(n)}<div class="muted small">${s}</div></td><td>${c}</td><td class="r num">${cost}</td></tr>`;
  return `<section class="card slist agtable m4-agt" aria-labelledby="agt-h">${cardHead(S.ag_h, { id: "agt-h", q: S4.ag_q_picked })}<div class="well"><table class="t ag"><thead><tr><th>${S.ag_col_agent}</th><th>${S.ag_col_check}</th><th class="r">${S.ag_col_cost}</th></tr></thead><tbody>
    ${rows.map(([n, s, k, w, c]) => r(n, s, st(k, w), c)).join("")}<tr class="grp"><th colspan="3" scope="colgroup">${S3.ag_none_h}</th></tr>${none.map(([n, s]) => r(n, s, `<span class="muted" aria-label="none">&#x2013;</span>`, "$0.00")).join("")}</tbody></table></div></section>`;
}
function builderInsp() {
  return insp({ part: S.nav_agents, name: "builder", s: "overridden", runs: S4.ag_runs_builder, set: S4.ag_set_builder, link: f4("ag_link", { path: '<code class="mono">/work/dotfiles/agents/builder.md</code>' }),
    check: `<div class="raised m4-chk"><p>${st("overridden", "Overridden")} ${S.mc_ex_builder}</p><p class="muted small">${S4.ag_check_builder_why}</p></div>`,
    body: factDl([[S4.ag_f_model, `${sw("Fable 5.1")}Fable 5.1 <small class="muted mono">line 4</small>`], [S4.ag_f_effort, 'xhigh <small class="muted mono">line 5</small>'], [S4.ag_f_tools, '<span class="mono">Read, Edit, Bash</span>']]),
    usage: S4.ag_cost_builder, acts: `<button class="btn">${S.in_copy}</button><a class="btn quiet" href="#">${S4.ag_open_setup} <span aria-hidden="true">&#x2192;</span></a>` });
}
function agPage4(sel, inspHtml) {
  return P4("agents", S.nav_agents, `${m3Scope(S.nav_agents, "30d")}${rvTabs("agents")}<div class="m4-agwrap m4-picked">${agTable4(sel)}${inspHtml}</div>`, { cls: "m4-ag" });
}
const m4AgReview = () => agPage4("builder", builderInsp());
const m4AgReviewPlugin = () => agPage4("linter", linterInsp({ part: S.nav_agents }).replace('<div class="acts">', '<div class="acts">'));
function m4SeeWhy() {
  const card = `<section class="card" aria-labelledby="mc-h">${cardHead(S.mc_h, { id: "mc-h", q: S.mc_q })}<div class="chk-hit m4-mchit"><div class="chk-t">${st("lowered", "Lowered")}<b>${S.mc_judge_t}</b></div><p class="muted">${S.mc_judge_why}</p><a class="btn" href="#">${S.mc_open} <span aria-hidden="true">&#x2192;</span></a></div><p class="note">${S.mc_ok}</p></section>`;
  const fr = (lab, html) => `<section class="m2-frame m4-fr" aria-label="${lab}">${ANN4(lab)}${html}</section>`;
  return P4("live", S.live_h1 || S.nav_live, `<h1 class="sr">${S.nav_live}</h1>${fr("Live, Model check: See why is a link to Your setup, Agents, judge (board p11-agents)", card)}`);
}

window.M4B = {
  "p10-map": () => m4Map(false), "p10-scopes": () => m4Map("cols"), "p10-scopes-chips": () => m4Map("chips"), "p10-states": m4MapStates, "p10-loading": m4MapLoading,
  "p11-settings": m4Settings, "p11-settings-shell": m4SettingsShell, "p11-list": m4ListPage, "p11-readonly": m4ReadOnly, "p11-agents": m4Agents, "p11-agent-plugin": m4AgentPlugin,
  "p11-instructions": m4Instructions, "p11-rules": m4Rules, "p11-skills": m4Skills, "p11-hooks": m4Hooks, "p11-permissions": m4Perms, "p11-mcp": m4Mcp, "p11-plugins": m4Plugins, "p11-output-style": m4Style,
  "p11-not-read": m4NotRead, "p11-couldnt-read": m4CouldntRead, "p11-empty": m4Empty,
  "p12-tofix": m4ToFix, "p12-tofix-empty": m4ToFixEmpty, "p12-tofix-long": m4ToFixLong, "p12-agents": m4AgReview, "p12-agents-plugin": m4AgReviewPlugin, "p12-see-why": m4SeeWhy,
};
