// Agent edit round: Agents page with inspector, edit rail (fields, review, body), saved, plugin read-only.
// Demo fixture: builder from usage-tidewater.json (config/agents/builder.md line 4). The symlink target is labelled mock.
const AG_PATH = "config/agents/builder.md";
function agTable(sel, opts = {}) {
  const rows = R.agents.slice().sort((a, b) => b.cost - a.cost);
  const src = { builder: S.ag_src_user, reviewer: S.ag_src_project, scribe: S.ag_src_user, "Main session": S.ag_main_src };
  const none = [["migrator", S.ag_src_project], ["release-notes", S.ag_src_user], ["linter", S.ag_src_plugin]];
  const chk = (n) => n === "builder" && opts.saved ? st("unknown", S.st_unknown) : st(CHECK[n].s, CHECK[n].w);
  const r = (n, s, c, cost, cur) => `<tr${cur ? ' class="picked" aria-current="true"' : ""}><td><a href="#">${n}</a><div class="muted small">${s}</div></td><td>${c}</td><td class="r num">${cost}</td></tr>`;
  return `<section class="card slist agtable"><header><h2>${S.ag_h}</h2><span class="q">${S.ag_q}</span>${opts.add ? `<span class="right"><button class="btn${opts.add === "on" ? " is-pressed" : ""}"${opts.add === "on" ? ' aria-pressed="true"' : ""}>+ ${S.an_add}</button></span>` : ""}</header>
  <div class="well"><table class="t ag"><thead><tr><th>${S.ag_col_agent}</th><th>${S.ag_col_check}</th><th class="r">${S.ag_col_cost}</th></tr></thead><tbody>
  ${rows.map((a) => r(a.name, src[a.name], chk(a.name), money(a.cost), a.name === sel)).join("")}
  ${opts.newRow ? `<tr class="grp"><th colspan="3" scope="colgroup">${S.ans_none_h}</th></tr>${r(opts.newRow, S.ans_sub, '<span class="muted" aria-label="none">&#x2013;</span>', "$0.00", true)}` : ""}
  <tr class="grp"><th colspan="3" scope="colgroup">${S.ag_none_h}</th></tr>
  ${none.map((n) => r(n[0], n[1], '<span class="muted" aria-label="none">&#x2013;</span>', "$0.00", n[0] === sel)).join("")}
  </tbody></table></div></section>`;
}
function agPage(sel, insp, { editing = false, saved = false, add = "", newRow = "" } = {}) {
  return aPage("agents", S.nav_agents, `<div class="hide-phone">${scopeBar(false, S.nav_agents)}</div>
  <p class="crumb only-phone ag-crumb"><a href="#">&#x2190; ${S.agi_back}</a></p>
  <div class="cs"><div class="agsplit surf${editing ? " editing" : " agsel"}">${agTable(sel, { saved, add, newRow })}<section class="card insp${editing ? " sheet" : ""}" aria-label="${sel || S.an_h}">${insp}</section></div></div>`);
}
const fileBlock = (link = true) => `<div class="well agf"><div class="agf-row"><span class="mono">${AG_PATH}</span>${sc("user")}</div>${link ? `<p class="aglink"><span aria-hidden="true">&#x21AA;</span> ${S.agi_file_link} <span class="badge">mock path</span></p>` : ""}</div>`;
function agInspector(saved) {
  return `<header class="in-h"><h2>builder</h2>${saved ? st("unknown", S.st_unknown) : st("overridden", "Overridden")}</header>
    ${saved ? `<div class="raised saved" role="status"><span aria-hidden="true">&#x2713;</span><b>${S.ags_saved}</b><span class="muted small">${S.ags_meta}</span><button class="btn">${S.ed_undo}</button></div>` : ""}
    <h3>${S.agi_file_h}</h3>${fileBlock()}
    <dl class="agdl">
      <div><dt>${S.agi_set_h}</dt><dd><span>${sw(saved ? "Sonnet 5.5" : "Fable 5.1")}<b>${saved ? S.ags_set_v : S.agi_set_v}</b></span><small class="muted mono">${S.agi_set_src}</small></dd></div>
      <div><dt>${S.agi_ran_h}</dt><dd><span>${sw("Fable 5.1")}${S.agi_ran_v}</span></dd></div>
    </dl>
    <h3>${S.agi_check_h}</h3>
    ${saved ? `<div class="raised"><p>${st("unknown", S.st_unknown)} ${S.ags_check}</p></div>` : `<div class="chk-hit"><div class="chk-t"><b>builder</b>${st("overridden", "Overridden")}</div><p>${S.mc_ex_builder}</p><p class="muted small">${S.agi_why}</p></div>`}
    <dl class="agdl"><div><dt>${S.agi_cost_h}</dt><dd>${S.agi_cost_v}</dd></div></dl>
    <div class="acts"><button class="btn primary">${S.agi_edit}</button><button class="btn">${S.in_copy}</button></div>`;
}
const aAgentInspector = () => agPage("builder", agInspector(false));
const aAgentSaved = () => agPage("builder", agInspector(true), { saved: true });

// ----- Fields rail -----
const fld = (label, ctl, meta = "", id = "") => `<div class="ffield"${id ? ` id="${id}"` : ""}><div class="ff-h"><span class="ff-l">${label}</span>${meta}</div>${ctl}</div>`;
const lineM = (n, reset) => `<span class="muted small mono">${S.agf_line.replace("{n}", n)}</span>${reset ? `<button class="btn quiet sm">${S.agf_reset}</button>` : ""}`;
const tags = (list, add, label) => `<div class="tags" role="group" aria-label="${label}">${list.map((t) => `<span class="tag">${t}<button class="tag-x" aria-label="${S.agf_remove.replace("{t}", t)}">&#x2715;</button></span>`).join("")}<button class="btn sm add">+ ${add}</button></div>`;
const COLORS = ["red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"];
function modelSelect(open, value) {
  const btn = `<button class="sel wide-sel${open ? " is-focus" : ""}" aria-expanded="${open}"><b>${value}</b></button>`;
  if (!open) return btn;
  const opt = (v, d, cur, on) => `<li role="option" aria-selected="${!!on}" class="${on ? "on" : ""}${cur ? " cur" : ""}"><span class="mono">${v}</span>${d ? `<small class="muted">${d}</small>` : ""}${on ? '<span class="ok" aria-hidden="true">&#x2713;</span>' : ""}</li>`;
  return `${btn}<div class="pop" role="listbox" aria-label="${S.agf_model}"><p class="pop-g">${S.agf_model_short}</p><ul>
    ${opt("inherit", S.agf_inherit_d)}${opt("opus", S.agf_alias_d.replace("{m}", "Opus"))}${opt("sonnet", S.agf_alias_d.replace("{m}", "Sonnet"), true, true)}${opt("haiku", S.agf_alias_d.replace("{m}", "Haiku"))}${opt("fable", S.agf_alias_d.replace("{m}", "Fable"))}</ul>
    <p class="pop-g">${S.agf_model_full}</p><ul>${opt("claude-opus-5-5", "Opus 5.5")}${opt("claude-sonnet-5-5", "Sonnet 5.5")}${opt("claude-haiku-5-5", "Haiku 5.5")}${opt("claude-fable-5-1", `Fable 5.1 &middot; ${S.agf_now}`)}</ul></div>`;
}
function agFields() {
  const lv = `<div class="segs" role="radiogroup" aria-label="${S.agf_effort}">${["low", "medium", "high", "xhigh", "max"].map((l) => `<label class="sg${l === "xhigh" ? " on" : ""}"><input type="radio" name="age"${l === "xhigh" ? " checked" : ""}><span>${l}</span>${l === "xhigh" ? `<small>${S.agf_now}</small>` : ""}</label>`).join("")}</div><p class="hint">${st("lowered", "Lowered")} ${S.agf_cap_hint}</p>`;
  return `${railHead(S.agf_h)}<div class="ffields">
    ${fld(S.agf_name, `<p class="ro-val"><span class="mono">builder</span></p><p class="hint"><svg class="lock" viewBox="0 0 12 14" width="11" height="13" aria-hidden="true"><rect x="1.5" y="6" width="9" height="7" rx="1.5" fill="currentColor"/><path d="M3.5 6V4.2a2.5 2.5 0 0 1 5 0V6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg> ${S.agf_name_ro}</p>`, lineM(2))}
    ${fld(S.agf_desc, `<textarea class="tfield" rows="3" aria-describedby="agd-h">${S.agf_desc_v}</textarea><p class="hint" id="agd-h">${S.agf_desc_hint}</p>`, lineM(3))}
    ${fld(S.agf_model, modelSelect(true, "sonnet"), lineM(4, true), "agm")}
    ${fld(S.agf_effort, lv, lineM(5))}
    ${fld(S.agf_tools, tags(["Read", "Edit", "Write", "Bash", "Grep", "Glob"], S.agf_tools_add, S.agf_tools) + `<p class="hint">${S.agf_tools_hint}</p>`, lineM(6))}
    ${fld(S.agf_notools, tags(["WebFetch"], S.agf_notools_add, S.agf_notools), lineM(7))}
    ${fld(S.agf_color, `<div class="colors" role="radiogroup" aria-label="${S.agf_color}">${COLORS.map((c) => `<label class="cl${c === "green" ? " on" : ""}"><input type="radio" name="agc"${c === "green" ? " checked" : ""}><i class="csw" style="--c:var(--agent-${c})" aria-hidden="true"></i>${c}</label>`).join("")}</div><p class="hint">${S.agf_color_hint}</p>`, lineM(8))}
    <details class="more"><summary><span>${S.agf_more}</span><small class="muted">${S.agf_more_sum}</small></summary></details>
  </div><div class="acts end"><span class="badge">${S.agf_changed}</span><button class="btn primary">${S.agf_preview}</button></div>`;
}
const aAgentEditFields = () => agPage("builder", agFields(), { editing: true });

// ----- Review -----
const FM_DIFF = [[" ", 1, "---"], [" ", 2, "name: builder"], [" ", 3, "description: Builds and runs features from a spec. Use for..."], ["-", 4, "model: claude-fable-5-1"], ["+", 4, "model: sonnet"], [" ", 5, "effort: xhigh"], [" ", "&#x22EE;", ""], [" ", 9, "---"]];
function agReview() {
  return `${railHead(S.agf_h)}
  <div class="raised effect"><h3>${S.ed_effect_h}</h3><div class="ba"><div><small class="muted">${S.ed_before}</small><b>${sw("Fable 5.1")}Fable 5.1</b><span class="muted small mono">claude-fable-5-1</span></div><span aria-hidden="true" class="arr">&#x2192;</span><div><small class="muted">${S.ed_after}</small><b>${sw("Sonnet 5.5")}Sonnet 5.5</b><span class="muted small mono">sonnet</span></div></div>
    <p class="applies"><span aria-hidden="true">&#x21BB;</span> ${S.agr_applies}</p></div>
  ${diffBlock(AG_PATH, FM_DIFF)}
  <p class="same"><span aria-hidden="true">=</span> ${S.agr_body_same}</p>
  <div class="raised warn"><h3>${S.ed_warn_h}</h3><p>${S.agr_runs_note}</p></div>
  <div class="raised linkw"><p><span aria-hidden="true">&#x21AA;</span> ${S.agr_link} <span class="badge">mock path</span></p></div>
  <div class="acts split"><button class="btn">${S.ed_back}</button><button class="btn primary">${S.agr_save}</button></div>`;
}
const aAgentEditReview = () => agPage("builder", agReview(), { editing: true });

// ----- Body -----
const BODY = ["You build features from a written spec.", "", "## How you work", "", "- Read the spec and the files it names first.", "- Follow the patterns already in the code.", "- Run the project's tests before you report.", "- Report what changed, file by file."];
function agBody() {
  const ed = `<div class="well editor" role="textbox" aria-multiline="true" aria-label="builder instructions"><ol>${BODY.map((l, i) => `<li${i === 6 ? ' class="cur"' : ""}><span class="ln">${i + 11}</span><code>${l || "&#x200B;"}</code></li>`).join("")}</ol></div>
    <p class="hint">${S.tx_hint} <span class="badge">${S.tx_changed}</span></p>`;
  return `${railHead(S.agb_h)}<p class="muted small mono">${AG_PATH}</p>${ed}
  <div class="raised effect"><h3>${S.ed_effect_h}</h3><p>${S.agb_effect}</p><p class="applies"><span aria-hidden="true">&#x21BB;</span> ${S.agr_applies}</p></div>
  ${diffBlock(AG_PATH, [[" ", 16, "- Follow the patterns already in the code."], ["-", 17, "- Run the tests before you report."], ["+", 17, "- Run the project's tests before you report."], [" ", 18, "- Report what changed, file by file."]])}
  <p class="same"><span aria-hidden="true">=</span> ${S.agb_fm_same}</p>
  <div class="acts split"><button class="btn">${S.ed_back}</button><button class="btn primary">${S.agr_save}</button></div>`;
}
const aAgentEditBody = () => agPage("builder", agBody(), { editing: true });

// ----- Plugin read-only -----
const aAgentPlugin = () => agPage("linter", `<header class="in-h"><h2>linter</h2><span class="muted small">${S.ag_src_plugin}</span></header>
  <h3>${S.agi_file_h}</h3><div class="well agf"><div class="agf-row"><span class="mono">plugins/lint-kit/agents/linter.md</span>${sc("plugin")}</div></div>
  <div class="raised ro"><svg class="lock" viewBox="0 0 12 14" width="11" height="13" aria-hidden="true"><rect x="1.5" y="6" width="9" height="7" rx="1.5" fill="currentColor"/><path d="M3.5 6V4.2a2.5 2.5 0 0 1 5 0V6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg><p>${S.agp_ro}</p><p class="path muted">${S.agp_how}</p><button class="btn">${S.in_copy}</button></div>
  <dl class="agdl"><div><dt>${S.agi_set_h}</dt><dd><span>${sw("Haiku 5.5")}<b>Haiku 5.5 at low</b></span></dd></div><div><dt>${S.agi_cost_h}</dt><dd>${S.ag_none_h}</dd></div></dl>`);
