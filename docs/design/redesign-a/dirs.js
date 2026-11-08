// Agent form layout round: three layouts for add and edit. Fields, values and words match the rail boards; only layout differs.
const LOCK = '<svg class="lock" viewBox="0 0 12 14" width="11" height="13" aria-hidden="true"><rect x="1.5" y="6" width="9" height="7" rx="1.5" fill="currentColor"/><path d="M3.5 6V4.2a2.5 2.5 0 0 1 5 0V6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';
function parts(mode, uid) {
  const edit = mode === "edit", name = edit ? "builder" : "planner", n = (k) => `${k}${uid}`;
  const P = { edit, name };
  const lv = (on, now) => `<div class="segs" role="radiogroup" aria-label="${S.agf_effort}">${["low", "medium", "high", "xhigh", "max"].map((l) => `<label class="sg${l === on ? " on" : ""}"><input type="radio" name="${n("e")}"${l === on ? " checked" : ""}><span>${l}</span>${now && l === on ? `<small>${S.agf_now}</small>` : ""}</label>`).join("")}</div>`;
  P.role = fld(S.an_role, roleCards("lead") + `<p class="hint">${S.an_role_hint}</p>` + roleSet("lead", false));
  P.start = fld(S.an_start, `<label class="switch-l"><button class="switch" role="switch" aria-checked="true"><span></span></button>${S.an_yes}</label><p class="hint">${S.an_start_hint}</p>`);
  P.model = edit ? fld(S.agf_model, modelSelect(false, "sonnet"), lineM(4, true)) : fld(S.agf_model, modelRadios("opus"));
  P.effort = edit ? fld(S.agf_effort, lv("xhigh", true) + `<p class="hint">${st("lowered", "Lowered")} ${S.agf_cap_hint}</p>`, lineM(5)) : fld(S.agf_effort, lv("high"));
  P.name = edit ? fld(S.agf_name, `<p class="ro-val"><span class="mono">builder</span></p><p class="hint">${LOCK} ${S.agf_name_ro}</p>`, lineM(2))
    : fld(S.an_name, `<input class="tfield one" aria-label="${S.an_name}" value="planner" aria-describedby="${n("nn")}"><p class="hint ok-line" id="${n("nn")}"><span aria-hidden="true" class="okm">&#x2713;</span>${S.an_name_ok}</p><p class="hint">${S.an_name_hint}</p>`);
  P.where = edit ? "" : fld(S.an_where, `<div class="wlist" role="radiogroup" aria-label="${S.an_where}"><label class="cl on"><input type="radio" name="${n("w")}" checked>${S.an_where_user}</label><label class="cl"><input type="radio" name="${n("w")}">${S.an_where_project}</label></div><p class="hint mono">config/agents/planner.md</p>`);
  P.desc = edit ? fld(S.agf_desc, `<textarea class="tfield" rows="3" aria-label="${S.agf_desc}">${S.agf_desc_v}</textarea><p class="hint">${S.agf_desc_hint}</p>`, lineM(3))
    : fld(S.agf_desc, `<textarea class="tfield" rows="3" aria-label="${S.agf_desc}">${S.an_desc_lead}</textarea><p class="hint">${S.an_desc_hint}</p>`);
  const cc = edit ? "green" : "purple";
  P.color = fld(S.agf_color, `<div class="colors" role="radiogroup" aria-label="${S.agf_color}">${COLORS.map((c) => `<label class="cl${c === cc ? " on" : ""}"><input type="radio" name="${n("c")}"${c === cc ? " checked" : ""}><i class="csw" style="--c:var(--agent-${c})" aria-hidden="true"></i>${c}</label>`).join("")}</div>${edit ? `<p class="hint">${S.agf_color_hint}</p>` : ""}`, edit ? lineM(8) : "");
  P.tools = edit ? fld(S.agf_tools, tags(["Read", "Edit", "Write", "Bash", "Grep", "Glob"], S.agf_tools_add, S.agf_tools) + `<p class="hint">${S.agf_tools_hint}</p>`, lineM(6))
    : fld(S.agf_tools, `<p class="ro-val">${S.an_tools_all}</p><button class="btn sm add">+ ${S.an_limit_tools}</button>`);
  P.notools = edit ? fld(S.agf_notools, tags(["WebFetch"], S.agf_notools_add, S.agf_notools), lineM(7)) : "";
  P.more = `<details class="more"><summary><span>${S.agf_more}</span><small class="muted">${edit ? S.agf_more_sum : S.an_more_sum}</small></summary></details>`;
  const lines = edit ? BODY : STARTER(), off = edit ? 11 : 1;
  P.prompt = () => fld(S.an_prompt, `<div class="well editor ly-ed" role="textbox" aria-multiline="true" aria-label="${S.an_prompt}"><ol>${lines.map((l, i) => `<li${i === 0 ? ' class="cur"' : ""}><span class="ln">${i + off}</span><code>${l || "&#x200B;"}</code></li>`).join("")}</ol></div><p class="hint">${S.an_prompt_hint} ${S.tx_hint}</p>`);
  const fm = edit ? ["---", "name: builder", `description: ${S.agf_desc_v}`, "model: sonnet", "effort: xhigh", "tools: Read, Edit, Write, Bash, Grep, Glob", "disallowedTools: WebFetch", "color: green", "---"]
    : ["---", "name: planner", `description: ${S.an_desc_lead}`, "model: opus", "effort: high", "color: purple", "---"];
  P.file = (hid) => `<section class="card filecard" aria-labelledby="${n("fh")}"><header><h2 id="${n("fh")}">${S.ly_file_h}</h2></header><p class="q small">${S.ly_file_q}</p><p class="muted small mono">config/agents/${name}.md</p>
    <div class="well fileprev"><ol>${[...fm, "", ...lines].map((l, i) => `<li${edit && i === 3 ? ' class="chg"' : ""}><span class="ln">${i + 1}</span><code>${l || "&#x200B;"}</code>${edit && i === 3 ? `<span class="sr">changed</span>` : ""}</li>`).join("")}</ol></div>${edit ? `<p class="aglink small"><span aria-hidden="true">&#x21AA;</span> ${S.agr_link} <span class="badge">mock path</span></p>` : ""}</section>`;
  P.title = edit ? S.agf_h : S.an_h;
  P.primary = edit ? S.agf_preview : S.an_preview;
  P.foot = edit ? `<span class="badge">${S.agf_changed}</span>` : `<span class="hint">${S.an_required}</span>`;
  return P;
}
const GROUPS = (edit) => [edit ? ["model", S.ly_s_model] : ["role", S.ly_s_role], ["ident", S.ly_s_ident], ["tools", S.ly_s_tools], ["prompt", S.ly_s_prompt]];
const gBody = (P, k) => ({ role: P.role + P.model + P.effort, model: P.model + P.effort, ident: P.name + P.where + P.desc + P.color, tools: (P.edit ? "" : P.start) + P.tools + P.notools + P.more, prompt: P.prompt() })[k];
const crumb = (P) => `<p class="crumb"><a href="#">&#x2190; ${S.nav_agents}</a></p>`;
const acts = (P) => `${P.foot}<a class="btn quiet" href="#">${S.ed_cancel}</a><button class="btn primary">${P.primary}</button>`;

// ---------- A. One page, all sections, section list and live file ----------
function dirA(mode) {
  const P = parts(mode, "a"), G = GROUPS(P.edit);
  return aPage("agents", P.title, `<div class="lyfocus lyA-page">
    <div class="ph lyh">${crumb(P)}<h1>${P.title}</h1><div class="right hide-phone">${acts(P)}</div></div>
    <div class="cs lyA">
      <section class="card lyA-form">${G.map(([k, l]) => `<div class="lyA-sec" id="a-${k}"><h2>${l}</h2><div class="ffields">${gBody(P, k)}</div></div>`).join("")}
        <details class="only-phone filedis"><summary>${S.ly_file_show}</summary>${P.file()}</details></section>
      <aside class="lyA-file hide-phone"><nav class="lyA-nav" aria-label="${S.ly_jump}"><p class="rset-h">${S.ly_jump}</p><ol>${G.map(([k, l], i) => `<li><a href="#a-${k}"${i === 0 ? ' aria-current="location"' : ""}>${l}</a></li>`).join("")}</ol></nav>${P.file()}</aside>
    </div>
    <div class="lyfoot only-phone">${acts(P)}</div></div>`);
}

// ---------- B. Stepped dialog over the Agents table ----------
function dirB(mode, step = 0) {
  const P = parts(mode, "b"), G = [...GROUPS(P.edit), ["review", S.ly_s_review]];
  const k = G[step][0];
  const steps = `<nav aria-label="${P.title}"><ol class="lyB-steps">${G.map(([kk, l], i) => `<li${i < step ? ' class="done"' : ""}><a href="#"${i === step ? ' aria-current="step"' : ""}><span class="n" aria-hidden="true">${i < step ? "&#x2713;" : i + 1}</span>${l}${i < step ? `<span class="sr">, ${S.ly_done}</span>` : ""}</a>${P.edit && kk === "model" ? `<span class="badge">${S.ly_changed.replace("{n}", 1)}</span>` : ""}</li>`).join("")}</ol></nav>`;
  const next = step < G.length - 1 ? G[step + 1][1] : "";
  const foot = P.edit
    ? `${P.foot}<button class="btn">${S.ly_next.replace("{s}", next)}</button><button class="btn primary">${P.primary}</button>`
    : `${step === 0 ? `<span class="hint">${S.an_required}</span>` : ""}<button class="btn"${step === 0 ? ' aria-disabled="true"' : ""}>${S.ly_back}</button><button class="btn primary">${S.ly_next.replace("{s}", next)}</button>`;
  const dlg = `<div class="lyB-scrim" aria-hidden="true"></div><div class="lyB" role="dialog" aria-modal="true" aria-labelledby="lyB-h">
    <header class="lyB-h"><div><h2 id="lyB-h">${P.title}</h2><p class="muted small only-phone">${S.ly_step.replace("{n}", step + 1).replace("{t}", G.length)}, ${G[step][1]}</p></div><button class="btn quiet x" aria-label="${S.ly_close}"><span aria-hidden="true">&#x2715;</span></button></header>
    <div class="lyB-grid">${steps}<div class="lyB-body">${k === "prompt" ? `<div class="ffields">${gBody(P, k)}</div>` : `<div class="ffields">${gBody(P, k)}</div>`}</div></div>
    <footer class="lyB-f">${foot}</footer></div>`;
  return aPage("agents", P.title, `<div class="lyB-under">${scopeBar(false, S.nav_agents)}<div class="cs">${agTable(P.edit ? "builder" : "", { add: P.edit ? "off" : "on" })}</div></div>${dlg}`);
}


// ----- C revision (November 8): stronger selected state, grouped fields -----
function rolesC(cur) {
  const card = (k) => `<label class="rcard${cur === k ? " on" : ""}"><input type="radio" name="rolec"${cur === k ? " checked" : ""}><b>${S["an_" + k]}</b><small>${S["an_" + k + "_d"]}</small>${cur === k ? SELW() : ""}</label>`;
  return `<div class="rcards" role="radiogroup" aria-label="${S.an_role}">${card("lead")}${card("worker")}${card("reviewer")}</div>`;
}
function roleSetShort() {
  return `<div class="well rset short"><p class="rset-h">${S.an_set_short_h.replace("{r}", S.an_lead)}</p><dl><div><dt>${S.an_start}</dt><dd>${S.an_yes}</dd></div><div><dt>${S.agf_tools}</dt><dd>${S.an_tools_all}</dd></div></dl></div>`;
}
function modelsC(cur) {
  const M = [["inherit", S.an_inherit_cost, ""], ["opus", S.an_cost_more, "hi"], ["sonnet", S.an_cost_same, "mid"], ["haiku", S.an_cost_less, "lo"], ["fable", S.an_cost_unknown, "na"]];
  return `<div class="mlist" role="radiogroup" aria-label="${S.agf_model}">${M.map(([m, c, k]) => `<label class="mrow${m === cur ? " on" : ""}"><input type="radio" name="amc"${m === cur ? " checked" : ""}><span class="mono">${m}</span><small class="muted">${c}</small>${m === cur ? SELW() : "<span></span>"}${k ? `<span class="pmark ${k}" aria-hidden="true"><i></i><i></i><i></i></span>` : "<span></span>"}</label>`).join("")}</div>
  <p class="hint">${S.an_model_cost} <button class="btn quiet sm">${S.an_full_name}</button></p>`;
}
const effC = (on, now) => `<div class="segs" role="radiogroup" aria-label="${S.agf_effort}">${["low", "medium", "high", "xhigh", "max"].map((l) => `<label class="sg${l === on ? " on" : ""}"><input type="radio" name="ec"${l === on ? " checked" : ""}><span>${l}</span>${now && l === on ? `<small>${S.agf_now}</small>` : ""}</label>`).join("")}</div>`;
function partsC(mode) {
  const P = parts(mode, "c");
  P.role = fld(S.an_role, rolesC("lead") + `<p class="hint">${S.an_role_hint}</p>` + roleSetShort());
  P.model = P.edit ? fld(S.agf_model, modelsC("sonnet"), lineM(4, true)) : fld(S.agf_model, modelsC("opus"));
  P.effort = P.edit ? fld(S.agf_effort, effC("xhigh", true) + `<p class="hint">${st("lowered", "Lowered")} ${S.agf_cap_hint}</p>`, lineM(5)) : fld(S.agf_effort, effC("high"));
  return P;
}

// ---------- C. Page with tabs, one group at a time, live file beside ----------
function dirC(mode, tab = 0) {
  const P = partsC(mode), G = GROUPS(P.edit);
  const tabs = `<div class="lyC-tabs" role="tablist" aria-label="${P.title}">${G.map(([k, l], i) => `<button role="tab" id="ct-${k}" aria-selected="${i === tab}" aria-controls="cp" tabindex="${i === tab ? 0 : -1}">${l}${P.edit && k === "model" ? ` <span class="badge">${S.ly_changed.replace("{n}", 1)}</span>` : ""}</button>`).join("")}<button role="tab" class="only-phone" id="ct-file" aria-selected="false" aria-controls="cp" tabindex="-1">${S.ly_file_h}</button></div>`;
  const nxt = tab < G.length - 1 ? `<div class="acts end lyC-next"><button class="btn">${S.ly_next.replace("{s}", G[tab + 1][1])}</button></div>` : "";
  return aPage("agents", P.title, `<div class="lyfocus lyC-page">
    <div class="ph lyh">${crumb(P)}<h1>${P.title}</h1><div class="right hide-phone">${acts(P)}</div></div>
    <div class="cs lyC"><div class="lyC-left">${tabs}
      <section class="card lyC-panel" role="tabpanel" id="cp" aria-labelledby="ct-${G[tab][0]}"><div class="ffields">${gBody(P, G[tab][0])}</div>${nxt}</section></div>
      <aside class="lyC-file hide-phone">${P.file()}</aside></div>
    <div class="lyfoot only-phone">${acts(P)}</div></div>`);
}
const aDirANew = () => dirA("new"), aDirAEdit = () => dirA("edit");
const aDirBNew = () => dirB("new"), aDirBEdit = () => dirB("edit"), aDirBPrompt = () => dirB("new", 3);
const aDirCNew = () => dirC("new"), aDirCEdit = () => dirC("edit"), aDirCPrompt = () => dirC("new", 3);

// ---------- Full page (owner's pick, November 8): every group stacked, sticky actions, file beside ----------
function dirFull(mode) {
  const P = partsC(mode), edit = P.edit;
  const G = [[edit ? "model" : "role", edit ? S.ly_s_model : S.ly_s_role, (edit ? "" : P.role) + P.model + P.effort], ["ident", S.ly_s_ident, P.name + P.where + P.desc + P.color], ["tools", S.ly_s_tools, (edit ? "" : P.start) + P.tools + P.notools + P.more], ["prompt", S.ly_s_prompt, P.prompt()]];
  const bar = `<div class="lyF-bar"><h1><a class="back" href="#">&#x2190; ${S.nav_agents}</a><span class="sep" aria-hidden="true">/</span>${P.title}</h1><div class="right hide-phone">${acts(P)}</div></div>`;
  const jump = `<nav class="lyA-nav lyF-jump" aria-label="${S.ly_jump}"><p class="rset-h">${S.ly_jump}</p><ol>${G.map(([k, l], i) => `<li><a href="#f-${k}"${i === 0 ? ' aria-current="location"' : ""}>${l}</a></li>`).join("")}</ol></nav>`;
  const sec = ([k, l, body]) => `<section class="lyF-sec" id="f-${k}" aria-labelledby="fh-${k}"><h2 id="fh-${k}">${l}</h2><div class="ffields">${body}</div></section>`;
  return aPage("agents", P.title, `<div class="lyfocus lyF-page">${bar}
    <div class="cs lyC lyF"><div class="lyF-form">${G.map(sec).join("")}
      <details class="only-phone filedis lyF-dis"><summary>${S.ly_file_show}</summary>${P.file()}</details></div>
      <aside class="lyC-file lyF-side hide-phone">${jump}${P.file()}</aside></div>
    <div class="lyfoot only-phone">${acts(P)}</div></div>`);
}
const aDirFullNew = () => dirFull("new"), aDirFullEdit = () => dirFull("edit");
