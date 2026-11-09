// Direction A, round 4: Your setup, surface page with inspector and edit rail, To fix, Reference, access states.
const sc = (k) => `<span class="scope"><b>${S["sc_" + k]}</b><small>${S["sc_" + k + "_2"]}</small></span>`;
const stw = (cls) => st(cls, S["st_" + cls.replace("-", "_")] || ({ "in-effect": "In effect", lowered: "Lowered", overridden: "Overridden", invalid: "Invalid" })[cls]);
const nv = () => `<span class="muted nvh">${S.su_nv}</span>`;
const dash = '<span class="muted" aria-label="none">&#x2013;</span>';

// ---------- Your setup ----------
const SETUP = [
  ["settings", ["lowered", "ignored"], { cli: "nv", local: "2 values", project: "2 values", user: "3 values" }],
  ["agents", ["in-effect"], { cli: "nv", project: "2 agents", user: "2 agents", plugin: "linter" }],
  ["instr", ["in-effect"], { local: "CLAUDE.local.md", project: "CLAUDE.md", user: "CLAUDE.md" }],
  ["rules", ["in-effect"], { project: "review.md", user: "writing.md" }],
  ["skills", ["in-effect"], { project: "3 skills", user: "1 skill", plugin: "1 skill" }],
  ["hooks", ["in-effect"], { project: "1 hook", user: "1 hook" }],
  ["perms", ["in-effect"], { local: "4 rules", project: "6 rules", user: "2 rules" }],
  ["mcp", ["invalid", "in-effect"], { project: ".mcp.json, 2", user: "nv" }],
  ["plugins", ["in-effect"], { user: "lint-kit" }],
  ["style", ["default"], {}],
];
const SCOPES = ["managed", "cli", "local", "project", "user", "plugin"];
const RUNKEY = { settings: "settings", agents: "agents", instr: "instr", rules: "rules", skills: "skills", hooks: "hooks", perms: "perms", mcp: "mcp", plugins: "plugins", style: "style" };
function aSetup(on) {
  const cell = (v) => v === "nv" ? nv() : v ? `<span>${v}</span>` : dash;
  const rows = SETUP.map(([k, sts, scp]) => `<tr role="row"><th scope="row" role="rowheader"><a href="#">${S["sf_" + k]}</a></th><td role="cell" class="runs">${S["su_r_" + RUNKEY[k]]}${on ? `<div class="chips only-phone">${SCOPES.filter((s) => scp[s]).map((s) => `<span class="chip"><b>${S["sc_" + s]}</b> ${scp[s] === "nv" ? S.su_nv : scp[s]}</span>`).join("")}</div>` : ""}</td>
    <td role="cell" class="stc"><span class="sts">${sts.map((c) => stw(c)).join("")}</span></td>${on ? SCOPES.map((s) => `<td role="cell" class="hp scol">${cell(scp[s])}</td>`).join("") : ""}</tr>`).join("");
  return aPage("setup", S.su_h1, `
  <div class="ph"><div><h1>${S.su_h1}</h1><p class="sub">${S.su_sub}</p></div>
    <div class="right"><label class="switch-l"><button class="switch" role="switch" aria-checked="${on}"><span></span></button>${S.su_switch}</label></div></div>
  <p class="notice raised-line">${st("unknown", S.st_unknown)}<span>${S.su_version}</span><a href="#">${S.su_version_link}</a></p>
  <section class="card"><header><h2>${S.su_card_h}</h2><span class="q">${S.su_card_q}</span></header>
    <div class="well wide"><table role="table" class="t setup${on ? " on" : ""}"><thead><tr role="row"><th role="columnheader">${S.su_col_what}</th><th role="columnheader">${S.su_col_runs}</th><th role="columnheader">${S.su_col_status}</th>${on ? SCOPES.map((s) => `<th role="columnheader" class="hp scol">${sc(s)}</th>`).join("") : ""}</tr></thead><tbody>${rows}</tbody></table></div>
  </section>`);
}

// ---------- Surface page (Settings) ----------
const SETS = [["model", "in-effect"], ["effort", "lowered"], ["cap", "in-effect"], ["think", "default"], ["compact", "default"], ["cache", "unknown"], ["fallback", "default"], ["allowed", "in-effect"]];
function surfList(sel, vals = {}) {
  return `<nav class="card slist" aria-label="${S.sp_list_h}"><header><h2>${S.sp_list_h}</h2><span class="q">${SETS.length}</span></header><ul class="well items">${SETS.map(([k, s]) =>
    `<li><a href="#"${k === sel ? ' aria-current="true"' : ""}><span class="it-n">${S["sp_" + k]}${k === "allowed" ? ' <svg class="lock" viewBox="0 0 12 14" width="11" height="13" role="img" aria-label="read only"><rect x="1.5" y="6" width="9" height="7" rx="1.5" fill="currentColor"/><path d="M3.5 6V4.2a2.5 2.5 0 0 1 5 0V6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>' : ""}</span><span class="it-v">${vals[k] || S["sp_v_" + k]}</span>${stw(vals[k + "_s"] || s)}</a></li>`).join("")}</ul></nav>`;
}
function whereRows() {
  return `<ul class="well where">
    <li>${sc("local")}<code>env.CLAUDE_CODE_EFFORT_LEVEL</code><b>xhigh</b>${stw("lowered")}<small class="muted mono">settings.local.json:3</small></li>
    <li>${sc("project")}<code>effortLevel</code><b>medium</b>${stw("overridden")}<small class="muted mono">settings.json:7</small></li>
    <li>${sc("user")}<code>effortLevel</code><b>xhigh</b>${stw("ignored")}<small class="muted mono">config/settings.json:3</small></li>
    <li>${sc("shell")}<code>CLAUDE_CODE_EFFORT_LEVEL</code>${nv()}</li>
    <li>${sc("cli")}<code>--effort</code>${nv()}</li></ul>`;
}
function inspector(body, phoneSheet) {
  return `<section class="card insp${phoneSheet ? " sheet" : ""}" aria-label="${S.sp_effort}">${body}</section>`;
}
function inspView() {
  return `<header class="in-h"><h2>${S.sp_effort}</h2>${stw("lowered")}</header>
    <p class="in-runs">${S.in_runs}</p><p class="in-set">${S.in_set}</p>
    <h3>${S.in_where_h}</h3>${whereRows()}
    <div class="raised why"><h3>${S.in_why_h}</h3><p>${S.in_why}</p><p class="muted small">${S.in_conf}</p></div>
    <p class="muted small">${S.in_usage}</p>
    <div class="acts"><button class="btn primary">${S.in_edit}</button><button class="btn">${S.in_copy}</button></div>`;
}
function surfPage(cur, sel, inspBody, opts = {}) {
  return aPage("setup", S.sp_h1, `
  <div class="ph${opts.sheet ? " hide-phone" : ""}"><div><p class="crumb"><a href="#">${S.su_h1}</a> / ${S.sp_h1}</p><h1>${S.sp_h1}</h1><p class="sub">${S.sp_sub}</p></div></div>
  <div class="surf${opts.sheet ? " editing" : ""}">${surfList(sel, opts.vals)}${inspector(inspBody, opts.sheet)}</div>`);
}
const aSurface = () => surfPage("setup", "effort", inspView());
const aSurfaceRO = () => surfPage("setup", "allowed", `<header class="in-h"><h2>${S.sp_allowed}</h2>${stw("in-effect")}</header>
  <p class="in-runs">${S.ro_runs}</p><p class="in-set">${S.ro_set}</p>
  <div class="raised ro"><svg class="lock" viewBox="0 0 12 14" width="11" height="13" aria-hidden="true"><rect x="1.5" y="6" width="9" height="7" rx="1.5" fill="currentColor"/><path d="M3.5 6V4.2a2.5 2.5 0 0 1 5 0V6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg><p>${S.ro_reason}</p><code class="path">/Library/Application Support/ClaudeCode/managed-settings.json</code><button class="btn">${S.in_copy}</button></div>
  <h3>${S.in_where_h}</h3><ul class="well where"><li>${sc("managed")}<code>availableModels</code><b>${S.ro_two}</b>${stw("in-effect")}<small class="muted mono">managed-settings.json:4</small></li><li>${sc("user")}<code>availableModels</code>${dash}${stw("default")}</li></ul>`);

// ---------- Edit rail ----------
function railHead(title) { return `<header class="rail-h"><button class="btn icon only-phone" aria-label="${S.ed_close}">&#x2715;</button><h2>${title}</h2><button class="btn quiet hide-phone">${S.ed_cancel}</button></header>`; }
const levels = ["low", "medium", "high", "xhigh", "max"];
function effectBlock(after) {
  return `<div class="raised effect"><h3>${S.ed_effect_h}</h3><div class="ba"><div><small class="muted">${S.ed_before}</small><b>high</b>${stw("lowered")}</div><span aria-hidden="true" class="arr">&#x2192;</span><div><small class="muted">${S.ed_after}</small><b>${after}</b>${stw("in-effect")}</div></div><p class="applies"><span aria-hidden="true">&#x21BB;</span> ${S.ed_applies}</p></div>`;
}
function diffBlock(file, lines) {
  return `<h3>${S.ed_diff_h}</h3><div class="well diff"><p class="mono dpath">${file}</p><ol class="dl">${lines.map(([k, n, t]) => `<li class="${k === "+" ? "add" : k === "-" ? "del" : ""}"><span class="ln">${n}</span><span class="gm" aria-label="${k === "+" ? "added" : k === "-" ? "removed" : "unchanged"}">${k === " " ? "" : k}</span><code>${t}</code></li>`).join("")}</ol></div>`;
}
const EFF_DIFF = [[" ", 2, '  "env": {'], ["-", 3, '    "CLAUDE_CODE_EFFORT_LEVEL": "xhigh"'], ["+", 3, '    "CLAUDE_CODE_EFFORT_LEVEL": "medium"'], [" ", 4, "  },"]];
function aEditDraft() {
  return surfPage("setup", "effort", `${railHead(S.ed_h)}
    <fieldset class="lvl"><legend>${S.ed_field}</legend><div class="segs" role="radiogroup">${levels.map((l) => `<label class="sg${l === "medium" ? " on" : ""}"><input type="radio" name="e"${l === "medium" ? " checked" : ""}><span>${l}</span>${l === "xhigh" ? `<small>${S.ed_now}</small>` : ""}</label>`).join("")}</div>
    <p class="hint">${S.ed_cap_hint}</p></fieldset>
    <label class="fld"><span>${S.ed_saveto}</span><button class="sel"><b>${S.ed_saveto_v}</b></button></label>
    <div class="acts end"><button class="btn primary">${S.ed_preview}</button></div>`, { sheet: true });
}
function aEditReview() {
  return surfPage("setup", "effort", `${railHead(S.ed_h)}${effectBlock("medium")}${diffBlock("projects/tidewater-reporting/.claude/settings.local.json", EFF_DIFF)}
    <div class="raised warn"><h3>${S.ed_warn_h}</h3><p><code>env.CLAUDE_CODE_EFFORT_LEVEL</code></p><p>${S.ed_warn}</p></div>
    <div class="acts split"><button class="btn">${S.ed_back}</button><button class="btn primary">${S.ed_save}</button></div>`, { sheet: true });
}
function aEditSaved() {
  return surfPage("setup", "effort", `<header class="in-h"><h2>${S.sp_effort}</h2>${stw("in-effect")}</header>
    <div class="raised saved" role="status"><span aria-hidden="true">&#x2713;</span><b>${S.ed_saved}</b><span class="muted small">${S.ed_saved_meta}</span><button class="btn">${S.ed_undo}</button></div>
    <p class="in-runs">${S.ed_runs_after}</p><p class="in-set">${S.ed_set_after}</p>
    <h3>${S.in_where_h}</h3>${whereRows().replace("<b>xhigh</b>" + stw("lowered"), "<b>medium</b>" + stw("in-effect"))}
    <div class="acts"><button class="btn primary">${S.in_edit}</button><button class="btn">${S.in_copy}</button><a class="btn quiet" href="#">${S.ed_history}</a></div>`, { vals: { effort: "medium", effort_s: "in-effect" } });
}
function aEditOver() {
  return surfPage("setup", "effort", `<header class="in-h"><h2>${S.sp_effort}</h2>${stw("in-effect")}</header>
    <div class="raised over" role="status"><p><span aria-hidden="true" class="ovm">&#x25B2;</span>${S.ed_over}</p><p class="muted small">${S.ed_over_keys}</p><code>permissions.allow</code>
      <div class="acts"><button class="btn primary">${S.ed_review_changes}</button><button class="btn">${S.ed_undo}</button></div></div>
    <p class="in-runs">${S.ed_runs_after}</p><p class="in-set">${S.ed_set_after}</p>
    <h3>${S.in_where_h}</h3>${whereRows().replace("<b>xhigh</b>" + stw("lowered"), "<b>medium</b>" + stw("in-effect"))}`, { vals: { effort: "medium", effort_s: "in-effect" } });
}
const MD = ["# Tidewater reporting", "", "Quarterly close reports for the finance team.", "", "## How we work", "", "- Run `make test` before every commit.", "- Keep SQL in `queries/`, one file per report.", "- Ask before changing a migration.", "", "## Review", "", "Use the reviewer agent for every pull request.", "Write commit messages in the past tense."];
function aEditText() {
  return aPage("setup", S.sf_instr, `
  <div class="ph hide-phone"><div><p class="crumb"><a href="#">${S.su_h1}</a> / ${S.sf_instr}</p><h1>${S.sf_instr}</h1></div></div>
  <div class="surf editing">
    <nav class="card slist" aria-label="${S.sf_instr}"><header><h2>${S.sf_instr}</h2><span class="q">3</span></header><ul class="well items">
      ${[["CLAUDE.md", "Shared project", true], ["CLAUDE.local.md", "Project local"], ["CLAUDE.md", "User"]].map((f) => `<li><a href="#"${f[2] ? ' aria-current="true"' : ""}><span class="it-n">${f[0]}</span><span class="it-v">${f[1]}</span>${stw("in-effect")}</a></li>`).join("")}</ul></nav>
    ${inspector(`${railHead(S.tx_h)}<p class="muted small">${S.tx_file}</p>
      <div class="well editor" role="textbox" aria-multiline="true" aria-label="CLAUDE.md"><ol>${MD.map((l, i) => `<li${i === 13 ? ' class="cur"' : ""}><span class="ln">${i + 1}</span><code>${l || "&#x200B;"}</code></li>`).join("")}</ol></div>
      <p class="hint">${S.tx_hint} <span class="badge">${S.tx_changed}</span></p>
      <div class="acts end"><button class="btn primary">${S.ed_preview}</button></div>`, true)}
  </div>`);
}
function aEditRisky() {
  return aPage("setup", S.sf_hooks, `
  <div class="ph hide-phone"><div><p class="crumb"><a href="#">${S.su_h1}</a> / ${S.sf_hooks}</p><h1>${S.sf_hooks}</h1></div></div>
  <div class="surf editing">
    <nav class="card slist" aria-label="${S.sf_hooks}"><header><h2>${S.sf_hooks}</h2><span class="q">3</span></header><ul class="well items">
      ${[["After Bash", "New hook", true, "default"], ["Before Edit", "Shared project", false, "in-effect"], ["Session start", "User", false, "in-effect"]].map((f) => `<li><a href="#"${f[2] ? ' aria-current="true"' : ""}><span class="it-n">${f[0]}</span><span class="it-v">${f[1]}</span>${f[2] ? "" : stw(f[3])}</a></li>`).join("")}</ul></nav>
    ${inspector(`${railHead(S.rk_h)}
      <div class="raised effect"><h3>${S.ed_effect_h}</h3><p>${S.rk_effect}</p><p class="applies"><span aria-hidden="true">&#x21BB;</span> ${S.ed_applies}</p></div>
      ${diffBlock("projects/tidewater-reporting/.claude/settings.json", [[" ", 12, '  "hooks": {'], ["+", 13, '    "PostToolUse": [{ "matcher": "Bash", "hooks": [{ "type": "command",'], ["+", 14, '      "command": "./scripts/lint-changed.sh --fix" }] }]'], [" ", 15, "  }"]])}
      <div class="raised risky"><h3><span aria-hidden="true">&#x26A0;&#xFE0E;</span> ${S.rk_conf_h}</h3>
        <dl><div><dt>${S.rk_cmd}</dt><dd><code class="well cmd">./scripts/lint-changed.sh --fix</code></dd></div><div><dt>${S.rk_when}</dt><dd>${S.rk_when_v}</dd></div></dl>
        <label class="chk"><input type="checkbox"> ${S.rk_check}</label>
        <button class="btn danger" aria-disabled="true" aria-describedby="rk-note">${S.rk_go}</button><p class="hint" id="rk-note">${S.rk_note}</p></div>
      <div class="acts end"><button class="btn">${S.rk_back}</button></div>`, true)}
  </div>`);
}
function aEditMcp() {
  return aPage("setup", S.sf_mcp, `
  <div class="ph hide-phone"><div><p class="crumb"><a href="#">${S.su_h1}</a> / ${S.sf_mcp}</p><h1>${S.sf_mcp}</h1></div></div>
  <div class="surf editing">
    <nav class="card slist" aria-label="${S.sf_mcp}"><header><h2>${S.sf_mcp}</h2><span class="q">2</span></header><ul class="well items">
      ${[["docs-search", "Shared project", false, "invalid"], ["tracker", "Shared project", false, "in-effect"], ["docs-search", "User, new", true, ""]].map((f) => `<li><a href="#"${f[2] ? ' aria-current="true"' : ""}><span class="it-n">${f[0]}</span><span class="it-v">${f[1]}</span>${f[3] ? stw(f[3]) : ""}</a></li>`).join("")}</ul></nav>
    ${inspector(`${railHead(S.mc2_h)}<p>${S.mc2_why}</p>
      <div class="cmdrow"><code class="well cmd">claude mcp add docs-search -s user -- npx docs-search</code><button class="btn">${S.mc2_copy}</button></div>
      <div class="raised"><p>${S.mc2_undo}</p><code class="well cmd">claude mcp remove docs-search -s user</code></div>
      <p class="checkline" role="status">${st("unknown", S.st_unknown)}<span>${S.mc2_status}</span></p>
      <div class="acts end"><button class="btn primary">${S.mc2_check}</button></div>`, true)}
  </div>`);
}

// ---------- To fix ----------
function fxRow(n, action) {
  return `<li class="raised fx"><h4>${S["fx_r" + n + "_t"]}</h4><p class="cause">${S["fx_r" + n + "_c"]}</p><p class="muted">${S["fx_r" + n + "_q"]}</p>${action ? `<a class="btn" href="#">${S["fx_r" + n + "_a"]}</a>` : ""}</li>`;
}
function fxGroup(k, mark, rows, extra = "") { return `<section class="card fxg"><header><h2><span class="st ${mark} plain"></span>${S["fx_g_" + k]}</h2><span class="q">${extra}</span></header><ul class="fxl">${rows}</ul></section>`; }
function aToFix(empty) {
  const cant = `<section class="card fxg cant"><header><h2>${S.fx_g_cant}</h2><span class="q">${S.fx_g_cant_note}</span></header><ul class="fxl">${fxRow(5, false)}</ul></section>`;
  const notes = `<section class="card"><header><h2>${S.fx_notes_h}</h2><span class="q">${S.fx_notes_q}</span></header><ul class="well notes"><li>${S.fx_n1} <a href="#">${S.su_version_link}</a></li><li>${S.fx_n2}</li></ul></section>`;
  const body = empty
    ? `<section class="card empty"><span class="big-ok" aria-hidden="true">&#x2713;</span><h2>${S.fx_empty_h}</h2><p class="muted">${S.fx_empty}</p><a class="btn" href="#">${S.fx_empty_a}</a></section>${cant}`
    : `${fxGroup("read", "invalid", fxRow(1, true), "1")}${fxGroup("load", "invalid", fxRow(2, true), "1")}${fxGroup("notset", "lowered", fxRow(3, true) + fxRow(4, true), "2")}${cant}${notes}`;
  return aPage("tofix", S.fx_h1, `<div class="ph"><div><h1>${S.fx_h1}</h1><p class="sub">${empty ? S.fx_empty_h : S.fx_sub}</p></div></div><div class="fxwrap">${body}</div>`);
}

// ---------- Reference ----------
function aDecides() {
  const rule = (id, conf, t, open) => `<li class="rl"><div class="rl-h"><code>${id}</code><span class="badge conf">${S["rf_" + conf]}</span></div><p>${t}</p><details${open ? " open" : ""}><summary>${S.rf_docs}</summary><blockquote class="well">${S.rf_quote_mock} <a href="#">code.claude.com</a></blockquote></details></li>`;
  return aPage("decides", S.rf_h1, `<div class="ph"><div><h1>${S.rf_h1}</h1><p class="sub">${S.rf_sub}</p></div></div>
  <p class="notice raised-line">${st("unknown", S.st_unknown)}<span>${S.rf_banner}</span></p>
  <div class="rf-tools"><label class="search"><span class="sr">${S.rf_search}</span><input type="search" placeholder="${S.rf_search}"></label><button class="sel"><span class="lab">${S.rf_conf}</span><b>${S.rf_conf_all}</b></button></div>
  <section class="card"><header><h2>${S.rf_g_effort}</h2><span class="q">3</span></header><ul class="well rules">${rule("effort.env-wins", "tested", S.rf_1, true)}${rule("effort.cap", "tested", S.rf_2)}${rule("effort.opus-ignores-user", "documented", S.rf_3)}</ul></section>
  <section class="card" style="margin-top:var(--space-4)"><header><h2>${S.rf_g_model}</h2><span class="q">2</span></header><ul class="well rules">${rule("model.order", "tested", S.rf_4)}${rule("scope.managed-first", "assumed", S.rf_5)}</ul></section>`);
}
function aGlossary() {
  const grp = (h, ids) => `<section class="card"><header><h2>${h}</h2></header><dl class="well gl">${ids.map((i) => `<div><dt>${i <= 7 ? stw(["", "in-effect", "overridden", "ignored", "lowered", "invalid", "default", "unknown"][i]) : `<b>${S["gl_t" + i]}</b>`}</dt><dd>${S["gl_d" + i]}</dd></div>`).join("")}</dl></section>`;
  return aPage("glossary", S.gl_h1, `<div class="ph"><div><h1>${S.gl_h1}</h1><p class="sub">${S.gl_sub}</p></div></div><div class="grid">${grp(S.gl_status, [1, 2, 3, 4, 5, 6, 7])}${grp(S.gl_scopes, [8, 9])}${grp(S.gl_terms, [10])}</div>`);
}

// ---------- Access states ----------
function bare(title, body) { document.title = `${title}, ${S.product}`; return `<div class="bare"><header class="bare-h"><div class="brand">${S.product}</div></header><main class="bare-m" id="main">${body}</main></div>`; }
const aLocked = () => bare(S.lk_h, `<section class="card gate"><svg class="lock gate-i" viewBox="0 0 12 14" width="22" height="26" aria-hidden="true"><rect x="1.5" y="6" width="9" height="7" rx="1.5" fill="currentColor"/><path d="M3.5 6V4.2a2.5 2.5 0 0 1 5 0V6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg><h1>${S.lk_h}</h1><p>${S.lk_body}</p>
  <div class="cmdrow"><code class="well cmd">${S.lk_cmd}</code><button class="btn">${S.lk_copy}</button></div><p class="raised-line">${S.lk_route}</p></section>`);
const aFirstRun = () => bare(S.fr_h, `<section class="card gate"><h1>${S.fr_h}</h1><p>${S.fr_body}</p>
  <ol class="well steps"><li class="ok"><span class="st done">${S.fr_done}</span>${S.fr_s1}</li><li class="now"><span class="st working">${S.fr_now}</span>${S.fr_s2}<div class="prog" role="progressbar" aria-valuenow="50" aria-valuemin="0" aria-valuemax="100" aria-label="${S.fr_s2}"><i style="width:50%"></i></div><small class="muted num">${S.fr_progress}</small></li><li><span class="st idle">${S.fr_next}</span>${S.fr_s3}</li></ol>
  <p class="muted small">${S.fr_net}</p></section>`);
