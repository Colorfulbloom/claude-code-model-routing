// M0 gate and shell round (November 8): More page, project picker, server stopped, first run, locked.
const PROJECTS = [
  ["Tidewater reporting", "~/work/tidewater-reporting", "working", true],
  ["Driftwood", "~/work/driftwood", "ok"],
  ["Saltmarsh", "~/work/saltmarsh", "noclaude"],
  ["Harbor notes", "~/work/old/harbor-notes", "notfound"],
];
const pkState = (k) => ({ ok: `<span class="pks ready"><span aria-hidden="true">&#x2713;</span>${S.pk_st_ok}</span>`, working: `<span class="pks working"><span aria-hidden="true">&#x25CF;</span>${S.pk_st_working}</span>`,
  noclaude: `<span class="pks idle"><span aria-hidden="true">&#x25CB;</span>${S.pk_st_noclaude}</span><small class="muted">${S.pk_st_noclaude_d}</small>`,
  notfound: `<span class="pks bad"><span aria-hidden="true">&#x2715;</span>${S.pk_st_notfound}</span><small class="muted">${S.pk_st_notfound_d}</small>` })[k];
const cmdRow = () => `<div class="cmdrow"><code class="well cmd">${S.lk_cmd}</code><button class="btn">${S.lk_copy}</button></div>`;
function pkList(empty) {
  if (empty) return `<div class="pk-empty"><p><b>${S.pk_empty_h}</b></p><p class="muted">${S.pk_empty_b}</p>${cmdRow()}</div>`;
  return `<ul class="pk-list" role="listbox" aria-label="${S.pk_h}">${PROJECTS.map(([n, p, k, cur], i) => `<li role="option" aria-selected="${!!cur}" class="${cur ? "on" : ""}${i === 1 ? " cur" : ""}"><span class="pk-n">${n}</span><span class="pk-p mono">${p}</span><span class="pk-s">${pkState(k)}</span>${cur ? '<span class="ok" aria-hidden="true">&#x2713;</span>' : ""}</li>`).join("")}</ul>`;
}
function aPicker(empty) {
  const tray = `<div class="pk-scrim only-phone" aria-hidden="true"></div><div class="pk-pop" role="dialog" aria-labelledby="pk-h"><header class="pk-h"><h2 id="pk-h">${S.pk_h}</h2><button class="btn quiet x only-phone" aria-label="${S.ed_close}"><span aria-hidden="true">&#x2715;</span></button></header>${pkList(empty)}</div>`;
  document.title = `${S.live_h1}, ${S.project_name}, ${S.product}`;
  return aPage("live", S.live_h1, `<div class="pk-under">${aLiveBody()}</div>`).replace('<button class="proj" aria-haspopup="listbox" aria-expanded="false"', '<button class="proj is-open" aria-haspopup="listbox" aria-expanded="true"').replace('aria-expanded="false" aria-label="Project', 'aria-expanded="true" aria-label="Project') + tray;
}
function aLiveBody() { const h = aLive(); const m = h.match(/<main class="main" id="main">([\s\S]*)<\/main>/); return m ? m[1] : ""; }

function aMore() {
  return aPage("more", S.nav_more, `<div class="ph"><div><h1>${S.nav_more}</h1></div></div>
    <section class="card more-c" aria-labelledby="mr-ref"><h2 id="mr-ref" class="more-h">${S.nav_ref_h}</h2>
      <ul class="more-l"><li><a href="#"><span class="ic" aria-hidden="true">&#x2318;</span>${S.nav_decides}<span class="chev" aria-hidden="true">&#x203A;</span></a></li><li><a href="#"><span class="ic" aria-hidden="true">&#x2261;</span>${S.nav_glossary}<span class="chev" aria-hidden="true">&#x203A;</span></a></li></ul></section>
    <section class="more-v" aria-labelledby="mr-ver"><h2 id="mr-ver" class="more-h">${S.more_ver_h}</h2><p>${S.version}</p></section>`);
}

const gate = (title, body) => bare(title, `<section class="card gate">${body}</section>`);
function aStopped() {
  return gate(S.st_h, `<h1>${S.st_h}</h1><p>${S.st_body}</p>${cmdRow()}<p class="raised-line">${S.st_route}</p>
    <div class="retry"><p role="status"><span class="st plain idle">${S.st_retry}</span><span class="muted">${S.st_last.replace("{t}", "3:42 PM")}</span></p><button class="btn">${S.st_try}</button></div>`);
}
const step = (cls, chip, label, extra = "") => `<li class="${cls}">${chip}${label}${extra}</li>`;
const DONE = () => step("ok", `<span class="st done">${S.fr_done}</span>`, S.fr_s1) + step("ok", `<span class="st done">${S.fr_done}</span>`, S.fr_s2);
function aFirstRun2() {
  return gate(S.fr_h, `<h1>${S.fr_h}</h1><p>${S.fr_body}</p><ol class="well steps">${DONE()}${step("now", `<span class="st working">${S.fr_now}</span>`, S.fr_s3,
    `<div class="prog" role="progressbar" aria-valuenow="312" aria-valuemin="0" aria-valuemax="1240" aria-valuetext="${S.fr_files.replace("{n}", "312").replace("{m}", "1,240")}" aria-label="${S.fr_s3}"><i style="width:25%"></i></div><small class="muted num">${S.fr_files.replace("{n}", "312").replace("{m}", "1,240")}</small>`)}</ol>
    <p class="muted small">${S.fr_local}</p>`);
}
function aFirstRunFailed() {
  return gate(S.fr_h, `<h1>${S.fr_h}</h1><p>${S.fr_body}</p><ol class="well steps">${DONE()}${step("bad", `<span class="st invalid">${S.fr_failed}</span>`, S.fr_s3, `<small class="muted num">${S.fr_files.replace("{n}", "640").replace("{m}", "1,240")}</small>`)}</ol>
    <div class="raised err" role="alert"><h3><span aria-hidden="true" class="errm">&#x2715;</span>${S.fr_fail_h}</h3><p>${S.fr_fail_reason.replace("{f}", '<code class="mono">~/.claude/projects/tidewater-reporting/9f2c.jsonl</code>')}</p><p>${S.fr_fail_fix}</p>${cmdRow()}</div>`);
}
function aFirstRunRetry() {
  return gate(S.fr_h, `<h1>${S.fr_h}</h1><p>${S.fr_body}</p><ol class="well steps">${DONE()}${step("now", `<span class="st working">${S.fr_now}</span>`, S.fr_s3,
    `<div class="prog" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="1240" aria-valuetext="${S.fr_retrying.replace("{t}", "3:51 PM")}" aria-label="${S.fr_s3}"><i style="width:0%"></i></div><small class="muted num" role="status">${S.fr_retrying.replace("{t}", "3:51 PM")}</small>`)}</ol>
    <p class="muted small">${S.fr_local}</p>`);
}
const LOCK_I = '<svg class="lock gate-i" viewBox="0 0 12 14" width="22" height="26" aria-hidden="true"><rect x="1.5" y="6" width="9" height="7" rx="1.5" fill="currentColor"/><path d="M3.5 6V4.2a2.5 2.5 0 0 1 5 0V6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';
const lockedBody = (r) => `${LOCK_I}<h1>${S.lk_h}</h1><p>${S["lk_r_" + r]} ${S.lk_run}</p>${cmdRow()}<p class="raised-line"><span aria-hidden="true">&#x21BB;</span> ${S.lk_route2}</p>`;
const aLocked2 = () => gate(S.lk_h, lockedBody("restarted"));
const aLockedWait = () => { document.title = S.product; return `<div class="bare wait"><main class="bare-m" id="main"><p class="wordmark">${S.product}</p><p class="sr" role="status">${S.lk_wait}</p></main></div>`; };
const aTabBack = () => aAgents().replace('<main class="main" id="main">', `<main class="main" id="main"><p class="notice raised-line back-n" role="status"><span aria-hidden="true" class="okm">&#x2713;</span><span>${S.lk_back}</span></p>`);
