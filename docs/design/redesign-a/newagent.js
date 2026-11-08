const SELW = () => `<span class="selw" aria-hidden="true">&#x2713; ${S.sel_word}</span>`;
// New-agent round: Add an agent from the Agents page. Role is a preset that fills real fields; it is never saved.
const ROLES = { lead: { start: true, model: "opus", effort: "high", tools: null }, worker: { start: false, model: "sonnet", effort: "medium", tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob"] }, reviewer: { start: false, model: "sonnet", effort: "high", tools: ["Read", "Grep", "Glob"] } };
const STARTER = () => [S.an_st_1, "", S.an_st_2, "", S.an_st_3, S.an_st_4, S.an_st_5, S.an_st_6];
function roleCards(cur) {
  const card = (k) => `<label class="rcard${cur === k ? " on" : ""}"><input type="radio" name="role"${cur === k ? " checked" : ""}><b>${S["an_" + k]}</b><small>${S["an_" + k + "_d"]}</small>${cur === k ? SELW() : ""}</label>`;
  return `<div class="rcards" role="radiogroup" aria-label="${S.an_role}">${card("lead")}${card("worker")}${card("reviewer")}${cur === "custom" ? `<div class="rcard custom on" aria-current="true"><b>${S.an_custom}</b><small>${S.an_custom_d}</small></div>` : ""}</div>`;
}
function roleSet(role, changed) {
  const v = ROLES.lead;
  const row = (k, val, ch) => `<div${ch ? ' class="ch"' : ""}><dt>${k}</dt><dd>${val}${ch ? ` <span class="badge">${S.an_you_changed}</span>` : ""}</dd></div>`;
  return `<div class="well rset"><p class="rset-h">${S.an_set_h.replace("{r}", S.an_lead)}</p><dl>
    ${row(S.an_start, changed ? `<s>${S.an_yes}</s> ${S.an_no}` : S.an_yes, changed)}
    ${row(S.agf_model, `<span class="mono">${v.model}</span>`)}${row(S.agf_effort, v.effort)}
    ${row(S.agf_tools, changed ? `${S.an_tools_all}, ${S.an_tools_noagent}` : S.an_tools_all, changed)}</dl></div>`;
}
function modelRadios(cur) {
  const M = [["inherit", S.an_inherit_cost, ""], ["opus", S.an_cost_more, "hi"], ["sonnet", S.an_cost_same, "mid"], ["haiku", S.an_cost_less, "lo"], ["fable", S.an_cost_unknown, "na"]];
  return `<div class="mlist" role="radiogroup" aria-label="${S.agf_model}">${M.map(([m, c, k]) => `<label class="mrow${m === cur ? " on" : ""}"><input type="radio" name="am"${m === cur ? " checked" : ""}><span class="mono">${m}</span><small class="muted">${c}</small>${m === cur ? SELW() : "<span></span>"}${k ? `<span class="pmark ${k}" aria-hidden="true"><i></i><i></i><i></i></span>` : "<span></span>"}</label>`).join("")}</div>
  <p class="hint">${S.an_model_cost} <button class="btn quiet sm">${S.an_full_name}</button></p>`;
}
function newForm({ custom = false } = {}) {
  const name = custom ? "reviewer" : "planner";
  const lv = `<div class="segs" role="radiogroup" aria-label="${S.agf_effort}">${["low", "medium", "high", "xhigh", "max"].map((l) => `<label class="sg${l === "high" ? " on" : ""}"><input type="radio" name="ane"${l === "high" ? " checked" : ""}><span>${l}</span></label>`).join("")}</div>`;
  const nameBlock = custom
    ? `<input class="tfield one" aria-label="${S.an_name}" value="${name}" aria-invalid="false" aria-describedby="an-n"><div class="raised warn nwarn" id="an-n"><p><span aria-hidden="true" class="ovm">&#x25B2;</span>${S.an_name_clash}</p><button class="btn">${S.an_name_clash_a}</button></div>`
    : `<input class="tfield one" aria-label="${S.an_name}" value="${name}" aria-describedby="an-n"><p class="hint ok-line" id="an-n"><span aria-hidden="true" class="okm">&#x2713;</span>${S.an_name_ok}</p>`;
  const where = `<div class="wlist" role="radiogroup" aria-label="${S.an_where}"><label class="cl on"><input type="radio" name="aw" checked>${S.an_where_user}</label><label class="cl"><input type="radio" name="aw">${S.an_where_project}</label></div><p class="hint mono">config/agents/${name}.md</p>`;
  const tools = `<p class="ro-val">${custom ? S.an_tools_all + ", " + S.an_tools_noagent : S.an_tools_all}</p><button class="btn sm add">+ ${S.an_limit_tools}</button>`;
  const ed = `<div class="well editor" role="textbox" aria-multiline="true" aria-label="${S.an_prompt}"><ol>${STARTER().map((l, i) => `<li${i === 0 ? ' class="cur"' : ""}><span class="ln">${i + 1}</span><code>${l || "&#x200B;"}</code></li>`).join("")}</ol></div>`;
  return `${railHead(S.an_h)}<div class="ffields">
    ${fld(S.an_role, roleCards(custom ? "custom" : "lead") + `<p class="hint">${S.an_role_hint}</p>` + roleSet("lead", custom))}
    ${fld(S.an_start, `<label class="switch-l"><button class="switch" role="switch" aria-checked="${!custom}"><span></span></button>${custom ? S.an_no : S.an_yes}</label><p class="hint">${S.an_start_hint}</p>`)}
    ${fld(S.agf_model, modelRadios("opus"))}
    ${fld(S.agf_effort, lv)}
    ${fld(S.an_name, nameBlock + `<p class="hint">${S.an_name_hint}</p>`)}
    ${fld(S.an_where, where)}
    ${fld(S.agf_desc, `<textarea class="tfield" rows="3" aria-label="${S.agf_desc}">${S.an_desc_lead}</textarea><p class="hint">${S.an_desc_hint}</p>`)}
    ${fld(S.agf_tools, tools)}
    ${fld(S.agf_color, `<div class="colors" role="radiogroup" aria-label="${S.agf_color}">${COLORS.map((c) => `<label class="cl${c === "purple" ? " on" : ""}"><input type="radio" name="anc"${c === "purple" ? " checked" : ""}><i class="csw" style="--c:var(--agent-${c})" aria-hidden="true"></i>${c}</label>`).join("")}</div>`)}
    ${fld(S.an_prompt, ed + `<p class="hint">${S.an_prompt_hint} ${S.tx_hint}</p>`)}
    <details class="more"><summary><span>${S.agf_more}</span><small class="muted">${S.an_more_sum}</small></summary></details>
  </div><div class="acts end"><span class="hint">${S.an_required}</span><button class="btn primary">${S.an_preview}</button></div>`;
}
const aAgentNew = () => agPage("", newForm(), { editing: true, add: "on" });
const aAgentNewCustom = () => agPage("", newForm({ custom: true }), { editing: true, add: "on" });
function newReview() {
  const file = ["---", "name: planner", `description: ${S.an_desc_lead}`, "model: opus", "effort: high", "color: purple", "---", "", ...STARTER()];
  return `${railHead(S.an_h)}
  <div class="raised effect"><h3>${S.ed_effect_h}</h3><p>${S.anr_effect}</p><p class="applies"><span aria-hidden="true">&#x21BB;</span> ${S.anr_pickup}</p></div>
  <h3>${S.anr_where} <span class="badge">${S.anr_new_file}</span></h3>
  ${diffBlock("config/agents/planner.md", file.map((l, i) => ["+", i + 1, l])).replace(/<h3>[^<]*<\/h3>/, "")}
  <div class="acts split"><button class="btn">${S.ed_back}</button><button class="btn primary">${S.anr_save}</button></div>`;
}
const aAgentNewReview = () => agPage("", newReview(), { editing: true, add: "on" });
const aAgentNewSaved = () => agPage("planner", `<header class="in-h"><h2>planner</h2></header>
  <div class="raised saved" role="status"><span aria-hidden="true">&#x2713;</span><b>${S.ans_saved}</b><span class="muted small">${S.ans_meta}</span><button class="btn">${S.ed_undo}</button></div>
  <h3>${S.agi_file_h}</h3><div class="well agf"><div class="agf-row"><span class="mono">config/agents/planner.md</span>${sc("user")}</div></div>
  <dl class="agdl"><div><dt>${S.agi_set_h}</dt><dd><span>${sw("Opus 5.5")}<b>${S.ans_set_v}</b></span></dd></div><div><dt>${S.agi_ran_h}</dt><dd class="muted">${S.ans_none_h}</dd></div></dl>
  <h3>${S.agi_check_h}</h3><div class="raised"><p>${S.ans_check}</p></div>
  <div class="acts"><button class="btn primary">${S.ans_edit}</button><button class="btn">${S.in_copy}</button></div>`, { add: "off", newRow: "planner" });
