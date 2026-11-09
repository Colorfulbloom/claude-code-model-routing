// Direction A component sheet: every component and state side by side. Canonical variants live in components.css (scoped to .cs).
function aComponents() {
  const cap = (k) => `<span class="cs-cap">${S["cs_s_" + k] || k}</span>`;
  const cell = (html, k, wide) => `<div class="cs-cell${wide ? " wide" : ""}"><div class="cs-demo">${html}</div>${cap(k)}</div>`;
  const sec = (k, body, note = "") => `<section class="card cs-sec" aria-labelledby="cs-${k}"><header><h2 id="cs-${k}">${S["cs_n_" + k]}</h2>${note ? `<span class="q">${note}</span>` : ""}</header>${body}</section>`;
  const row = (label, cells) => `<div class="cs-row">${label ? `<h3 class="cs-rl">${label}</h3>` : ""}<div class="cs-cells">${cells}</div></div>`;
  const STATES = ["default", "hover", "focus", "pressed", "disabled", "loading"];
  const btn = (cls, label, s) => `<button class="btn ${cls}${s === "hover" ? " is-hover" : s === "focus" ? " is-focus" : s === "pressed" ? " is-active" : ""}"${s === "disabled" ? ' aria-disabled="true"' : ""}${s === "loading" ? ' aria-disabled="true" aria-busy="true"' : ""}>${s === "loading" ? `${S.cs_saving}` : label}</button>`;
  const buttons = [["primary", S.ed_save], ["", S.in_copy], ["quiet", S.ed_cancel], ["danger", S.rk_go]].map(([c, l]) =>
    row(S["cs_v_" + (c || "secondary")], STATES.map((s) => cell(btn(c, l, s), s)).join(""))).join("") +
    row(S.cs_v_icon, ["default", "hover", "focus"].map((s) => cell(btn("icon", "&#x2715;", s).replace("<button", `<button aria-label="${S.ed_close}"`), s)).join(""));

  const status = `<div class="cs-wrap">${["in-effect", "overridden", "ignored", "lowered", "invalid", "default", "unknown"].map((k) => stw(k)).join("")}</div>`;
  const run = `<div class="cs-wrap">${st("working", S.st_working)}${st("done", S.st_done)}${st("idle", S.st_idle)}${st("idle", S.c_not_started)}</div>`;
  const badge = `<div class="cs-wrap"><span class="badge">${S.rf_tested}</span><span class="badge">${S.tx_changed}</span><span class="chip"><b>${S.sc_project}</b> ${S.su_n_files.replace("{n}", 2)}</span><span class="chip"><b>${S.sc_cli}</b> ${S.su_nv}</span>${sc("local")}</div>`;
  const swatch = `<div class="cs-wrap legend">${R.models.map((x) => x.display_name).map((m) => `<span>${sw(m)}<b>${m}</b></span>`).join("")}</div>`;

  const sw2 = (on, s) => `<label class="switch-l"><button class="switch${s === "hover" ? " is-hover" : s === "focus" ? " is-focus" : ""}" role="switch" aria-checked="${on}"${s === "disabled" ? ' aria-disabled="true"' : ""}><span></span></button>${S.su_switch}</label>`;
  const switches = row("", [cell(sw2(false), "off"), cell(sw2(true), "on"), cell(sw2(false, "hover"), "hover"), cell(sw2(true, "focus"), "focus"), cell(sw2(false, "disabled"), "disabled")].join(""));

  const tabs = (s) => `<nav class="seg-tabs" aria-label="${S.nav_review}">${["summary", "sessions", "agents", "models"].map((k, i) => `<a href="#"${i === 0 ? ' aria-current="page"' : ""}${i === 1 && s ? ` class="is-${s}"` : ""}>${S["rv_tab_" + k]}</a>`).join("")}</nav>`;
  const lv = (s) => `<div class="segs" role="radiogroup" aria-label="${S.ed_field}">${["low", "medium", "high", "xhigh", "max"].map((l) => `<label class="sg${l === "medium" ? " on" : ""}${l === "high" && s ? " is-" + s : ""}"><input type="radio" name="cs${s || "d"}"${l === "medium" ? " checked" : ""}${s === "disabled" ? " disabled" : ""}><span>${l}</span>${l === "xhigh" ? `<small>${S.ed_now}</small>` : ""}</label>`).join("")}</div>`;
  const segs = row(S.cs_v_tabs, [cell(tabs(), "selected"), cell(tabs("hover"), "hover"), cell(tabs("focus"), "focus")].join("")) +
    row(S.cs_v_radio, [cell(lv(), "selected"), cell(lv("hover"), "hover"), cell(lv("focus"), "focus"), cell(lv("disabled"), "disabled")].join(""));

  const sel = (s) => `<button class="sel${s ? " is-" + s : ""}"><span class="lab">${S.rv_range_lab}</span><b>${S.rv_range}</b></button>`;
  const srch = (s, v = "") => `<label class="search cs-search${s ? " is-" + s : ""}"><span class="sr">${S.rf_search}</span><input type="search" placeholder="${S.rf_search}" value="${v}"></label>`;
  const selects = row("", [cell(sel(), "default"), cell(sel("hover"), "hover"), cell(sel("focus"), "focus"), cell(srch(), "default"), cell(srch("focus", "cache"), "focus"),
    cell(`${srch("", "cache")}<p class="cs-inline-empty">${S.cs_search_empty} <button class="btn quiet">${S.cs_search_clear}</button></p>`, "empty", true)].join(""));
  const ck = (s, on) => `<label class="chk${s ? " is-" + s : ""}"><input type="checkbox"${on ? " checked" : ""}${s === "disabled" ? " disabled" : ""}> ${S.rk_check}</label>`;
  const checks = row("", [cell(ck(), "default"), cell(ck("hover"), "hover"), cell(ck("focus"), "focus"), cell(ck("", true), "checked"), cell(ck("disabled"), "disabled")].join(""));

  const tiles = `<div class="tiles cs-tiles">${tile(S.rv_t_cost, "$319.40", S.rv_t_cost_d, spark([3, 5, 4, 6, 8, 7, 9, 11]))}${tile(S.rv_t_cache, "62%", S.rv_t_cache_d, ring(62))}${tile(S.rv_t_sessions, "53", S.rv_t_sessions_d, dots(3, 1))}${tile(S.rv_t_tokens, '<i class="bone big" aria-hidden="true"></i>', S.cs_tb_loading)}</div>`;
  const bars = `<div class="well">${agentShare()}</div>`;
  const stack = `<div class="well">${costPerDay(120, "oct")}${pager("oct")}</div>`;
  const tline = `<div class="cs-tl">${timeline({ compact: true })}</div>`;
  const replay = `<div class="cs-tl">${timeline({ at: 15, compact: true })}</div>`;

  const th = `<thead><tr><th>${S.rv_tab_sessions}</th><th class="r">${S.rv_t_cost}</th><th class="r hp">${S.rv_t_tokens}</th></tr></thead>`;
  const tbl = (body) => `<div class="well"><table class="t">${th}<tbody>${body}</tbody></table></div>`;
  const tr = (a, b, c, cls = "") => `<tr${cls}><td><a href="#">${a}</a></td><td class="r num">${b}</td><td class="r num hp">${c}</td></tr>`;
  const tables = `<div class="cs-grid2">${cell(tbl(tr("October 30, 6:10 PM", "$18.42", "4.1M") + tr("October 30, 2:05 PM", "$11.07", "2.6M", ' class="is-hover"') + tr("October 29, 9:40 AM", "$6.30", "1.4M")), "default")}
    ${cell(tbl(`<tr><td colspan="3"><div class="cs-tb-msg"><p>${S.cs_tb_empty}</p><button class="btn">${S.cs_tb_empty_a}</button></div></td></tr>`), "empty")}
    ${cell(tbl(tr("October 30, 6:10 PM", "$18.42", "4.1M") + `<tr><td colspan="3"><div class="raised cs-tb-err" role="status"><span aria-hidden="true" class="cs-x">&#x2715;</span><span>${S.cs_tb_error}</span><button class="btn">${S.cs_tb_error_a}</button></div></td></tr>`), "error")}
    ${cell(tbl([1, 2, 3].map(() => `<tr aria-hidden="true"><td><i class="bone" style="width:60%"></i></td><td class="r"><i class="bone" style="width:48px"></i></td><td class="r hp"><i class="bone" style="width:40px"></i></td></tr>`).join("")).replace('<div class="well">', `<div class="well" aria-busy="true"><p class="sr">${S.cs_tb_loading}</p>`), "loading")}</div>`;

  const li = (n, v, s, cls = "") => `<li><a href="#"${cls}><span class="it-n">${n}</span><span class="it-v">${v}</span>${s ? stw(s) : ""}</a></li>`;
  const list = `<div class="cs-grid2">${cell(`<ul class="well items">${li(S.sp_model, S.sp_v_model, "in-effect")}${li(S.sp_effort, S.sp_v_effort, "lowered", ' aria-current="true"')}${li(S.sp_cap, S.sp_v_cap, "in-effect", ' class="is-hover"')}${li(S.sp_think, S.sp_v_think, "default", ' class="is-focus"')}</ul>`, `${S.cs_s_selected}, ${S.cs_s_hover}, ${S.cs_s_focus}`)}
    ${cell(`<div class="well cs-empty-l"><p>${S.cs_list_empty}</p><button class="btn">${S.cs_list_empty_a}</button></div>`, "empty")}
    ${cell(`<div class="cs-insp">${`<header class="in-h"><h2>${S.sp_effort}</h2>${stw("lowered")}</header><p class="in-runs">${S.in_runs}</p><p class="in-set">${S.in_set}</p>`}</div>`, "default", true)}</div>`;

  const raised = `<div class="cs-grid2">
    ${cell(`<div class="chk-hit cs-chk"><div class="chk-t"><b>builder</b>${stw("lowered")}</div><p class="muted">${S.mc_ex_builder || S.fx_r3_q}</p></div>`, S.cs_v_check)}
    ${cell(`<div class="raised warn"><h3>${S.ed_warn_h}</h3><p><code>env.CLAUDE_CODE_EFFORT_LEVEL</code></p><p>${S.ed_warn}</p></div>`, S.cs_v_warn)}
    ${cell(`<div class="raised saved" role="status"><span aria-hidden="true">&#x2713;</span><b>${S.ed_saved}</b><span class="muted small">${S.ed_saved_meta}</span><button class="btn">${S.ed_undo}</button></div>`, S.cs_v_saved)}
    ${cell(`<div class="raised over" role="status"><p><span aria-hidden="true" class="ovm">&#x25B2;</span>${S.ed_over}</p><div class="acts"><button class="btn primary">${S.ed_review_changes}</button><button class="btn">${S.ed_undo}</button></div></div>`, S.cs_v_over)}
    ${cell(`<div class="raised cs-err" role="alert"><p><span aria-hidden="true" class="cs-x">&#x2715;</span>${S.cs_prev_err}</p><button class="btn">${S.cs_prev_err_a}</button></div>`, S.cs_v_err)}</div>`;
  const notice = cell(`<p class="notice raised-line">${st("unknown", S.st_unknown)}<span>${S.su_version}</span><a href="#">${S.su_version_link}</a></p>`, "default", true);
  const diff = `<div class="cs-grid2">${cell(diffBlock("projects/tidewater-reporting/.claude/settings.local.json", EFF_DIFF).replace(/<h3>[^<]*<\/h3>/, ""), "default")}${cell(`<div class="well editor" role="textbox" aria-multiline="true" aria-label="CLAUDE.md"><ol>${MD.slice(0, 7).map((l, i) => `<li${i === 6 ? ' class="cur"' : ""}><span class="ln">${i + 1}</span><code>${l || "&#x200B;"}</code></li>`).join("")}</ol></div>`, "focus")}</div>`;
  const cmd = row("", [cell(`<div class="cmdrow"><code class="well cmd">claude mcp add docs-search -s user -- npx docs-search</code><button class="btn">${S.mc2_copy}</button></div>`, "default", true), cell(`<p class="checkline" role="status">${st("unknown", S.st_unknown)}<span>${S.mc2_status}</span></p><div class="acts"><button class="btn primary">${S.mc2_check}</button></div>`, "default")].join(""));
  const fix = `<ul class="fxl">${fxRow(2, true)}</ul>`;
  const confirm = (on) => `<div class="raised risky"><h3><span aria-hidden="true">&#x26A0;&#xFE0E;</span> ${S.rk_conf_h}</h3><dl><div><dt>${S.rk_cmd}</dt><dd><code class="well cmd">./scripts/lint-changed.sh --fix</code></dd></div></dl><label class="chk"><input type="checkbox"${on ? " checked" : ""}> ${S.rk_check}</label><button class="btn danger"${on ? "" : ' aria-disabled="true"'}>${S.rk_go}</button></div>`;
  const confirms = `<div class="cs-grid2">${cell(confirm(false), "disabled")}${cell(confirm(true), "checked")}</div>`;
  const scope = cell(`<div class="cs-scope">${scopeBar(false, S.nav_summary)}</div>`, "default", true) + cell(`<div class="cs-scope">${scopeBar(true, S.rv_session_value)}</div>`, "selected", true);
  const nav = `<div class="cs-grid2">${cell(`<div class="cs-side side">${["live", "summary", "sessions"].map((k, i) => `<a class="nv${i === 1 ? " is-hover" : ""}${i === 2 ? " is-focus" : ""}" href="#"${i === 0 ? ' aria-current="page"' : ""}><span class="ic" aria-hidden="true">${["&#x25C9;", "&#x25A4;", "&#x2261;"][i]}</span>${S["nav_" + k]}</a>`).join("")}</div>`, `${S.cs_s_selected}, ${S.cs_s_hover}, ${S.cs_s_focus}`)}
    ${cell(`<nav class="cs-tabbar">${[["&#x25C9;", S.nav_live, 1], ["&#x25A4;", S.nav_review], ["&#x2699;", S.nav_setup_h], ["&#x25B3;", S.nav_tofix, 0, S.tofix_count], ["&#x2261;", S.nav_more]].map(([ic, l, cur, n]) => `<a href="#"${cur ? ' aria-current="page"' : ""}><span class="ic" aria-hidden="true">${ic}${n ? `<span class="cnt">${n}</span>` : ""}</span>${l}</a>`).join("")}</nav>`, "selected")}</div>`;
  const sheet = cell(`<div class="cs-phone"><div class="cs-sheet"><header class="rail-h"><button class="btn icon" aria-label="${S.ed_close}">&#x2715;</button><h2>${S.ed_h}</h2></header>${effectBlock("medium")}<div class="cs-sheet-foot"><button class="btn primary">${S.ed_save}</button><button class="btn">${S.ed_back}</button></div></div></div>`, "default");
  const cards = cell(`<div class="cs-ph ph"><div><h1>${S.su_h1}</h1><p class="sub">${S.su_sub}</p></div></div><section class="card"><header><h2>${S.rv_chk_h}</h2><span class="q">${S.rv_chk_q}</span></header><div class="well"><p>${S.rv_chk_sum}</p></div></section>`, "default", true);
  const empty = cell(`<section class="card empty"><span class="big-ok" aria-hidden="true">&#x2713;</span><h2>${S.fx_empty_h}</h2><p class="muted">${S.fx_empty}</p><a class="btn" href="#">${S.fx_empty_a}</a></section>`, "empty", true);
  const steps = cell(`<ol class="well steps">${DONE()}${step("now", `<span class="st working">${S.fr_now}</span>`, S.fr_s3, `<div class="prog" role="progressbar" aria-valuenow="312" aria-valuemin="0" aria-valuemax="1240" aria-valuetext="${S.fr_files.replace("{n}", "312").replace("{m}", "1,240")}" aria-label="${S.fr_s3}"><i style="width:25%"></i></div><small class="muted num">${S.fr_files.replace("{n}", "312").replace("{m}", "1,240")}</small>`)}</ol>`, "loading", true);

  // M0 additions (November 8): picker, gate variants, More, first-run states, new-tab line.
  const m0picker = `<div class="cs-grid2">${cell(`<div class="pk-pop cs-static">${pkList(false)}</div>`, "open", false)}${cell(`<div class="pk-pop cs-static">${pkList(true)}</div>`, "empty", false)}</div>`;
  const m0gates = `<div class="cs-grid2">${["no_key", "code_used", "code_expired", "restarted"].map((r) => cell(`<div class="card gate">${lockedBody(r.replace("restarted", "restarted"))}</div>`, r)).join("")}</div>
    <div class="cs-grid2">${cell(`<div class="retry"><p role="status"><span class="st plain idle">${S.st_retry}</span><span class="muted">${S.st_last.replace("{t}", "3:42 PM")}</span></p><button class="btn">${S.st_try}</button></div>`, "default")}${cell(`<div class="retry"><p role="status"><span class="st plain idle">${S.st_retry}</span><span class="muted">${S.st_last.replace("{t}", "3:42 PM")}</span></p><button class="btn" aria-busy="true">${S.st_trying}</button></div>`, "loading")}</div>
    <div class="cs-grid2">${cell(`<ol class="well steps">${DONE()}${step("bad", `<span class="st invalid">${S.fr_failed}</span>`, S.fr_s3)}</ol><div class="raised err" role="alert"><h3><span aria-hidden="true" class="errm">&#x2715;</span>${S.fr_fail_h}</h3><p>${S.fr_fail_reason.replace("{f}", '<code class="mono">~/.claude/projects/tidewater-reporting/9f2c.jsonl</code>')}</p><p>${S.fr_fail_fix}</p>${cmdRow()}</div>`, "error")}${cell(`<p class="notice raised-line back-n" role="status"><span aria-hidden="true" class="okm">&#x2713;</span><span>${S.lk_back}</span></p><div class="cs-wait"><p class="wordmark">${S.product}</p><p class="sr">${S.lk_wait}</p></div>`, "default")}</div>`;
  const m0more = cell(`<ul class="more-l"><li><a href="#"><span class="ic" aria-hidden="true">&#x2318;</span>${S.nav_decides}<span class="chev" aria-hidden="true">&#x203A;</span></a></li><li><a href="#" class="is-focus"><span class="ic" aria-hidden="true">&#x2261;</span>${S.nav_glossary}<span class="chev" aria-hidden="true">&#x203A;</span></a></li></ul>`, "focus");
  return aPage("components", S.cs_h1, `<div class="ph"><div><h1>${S.cs_h1}</h1><p class="sub">${S.cs_sub}</p></div></div>
  <div class="cs">
    ${sec("buttons", buttons)}
    <div class="cs-grid2">${sec("status", status)}${sec("run", run)}${sec("badge", badge)}${sec("swatch", swatch)}</div>
    ${sec("switch", switches)}${sec("segment", segs)}${sec("select", selects)}${sec("check", checks)}
    ${sec("tiles", cell(tiles, "default", true))}
    <div class="cs-grid2">${sec("bars", bars)}${sec("stack", stack)}</div>
    ${sec("timeline", tline)}${sec("replay", replay)}
    ${sec("table", tables)}${sec("list", list)}${sec("raised", raised)}${sec("notice", notice)}
    ${sec("diff", diff)}${sec("cmd", cmd)}
    <div class="cs-grid2">${sec("fix", fix)}${sec("confirm", confirms)}</div>
    ${sec("scope", scope)}${sec("nav", nav)}
    <div class="cs-grid2">${sec("sheet", sheet)}${sec("steps", steps)}</div>
    ${sec("card", cards)}${sec("empty", empty)}
    ${sec("picker", m0picker)}${sec("gates", m0gates)}${sec("more", m0more)}
  </div>`);
}
