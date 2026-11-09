// M1 data core round (November 8): footer, More history, updates-stopped notice, first run by size, store_newer gate, picker placeholder.
window.M1 = { problem: false, stoppedAt: null };
const fl = (txt, warn) => `<p class="fl${warn ? " fwarn" : ""}">${warn ? '<span aria-hidden="true" class="wm">&#x25B2;</span>' : ""}${txt}</p>`;
function footHTML() {
  const p = M1.problem;
  return `<div class="foot m1foot">
    ${p ? fl(S.ft_unreadable.replace("{n}", "3"), true) : ""}
    ${fl(S.ft_updated.replace("{t}", M1.stoppedAt || "6:41 PM"))}
    ${fl(S.ft_since.replace("{d}", "September 3"))}
    ${p ? fl(S.ft_backup_failed.replace("{t}", "4:02 AM"), true) : fl(S.ft_backup.replace("{t}", "4:02 AM"))}
    ${fl(S.ft_prices.replace("{d}", "October 28"))}
    ${fl(S.version)}</div>`;
}
const withFlags = (o, fn) => () => { Object.assign(M1, { problem: false, stoppedAt: null }, o); const h = fn(); Object.assign(M1, { problem: false, stoppedAt: null }); return h; };
const aFooter = withFlags({}, () => aLive());
const aFooterProblem = withFlags({ problem: true }, () => aLive());

function histCard(p) {
  const row = (l, v, warn) => `<div><dt>${l}</dt><dd${warn ? ' class="fwarn"' : ""}>${warn ? '<span aria-hidden="true" class="wm">&#x25B2;</span>' : ""}${v}</dd></div>`;
  const finds = p ? `<div class="raised wfind"><h3><span aria-hidden="true" class="wm">&#x25B2;</span>${S.ft_backup_failed.replace("{t}", "4:02 AM")}</h3><p>${S.mb_backup_b.replace("{d}", "November 7")}</p></div>
    <div class="raised wfind"><h3><span aria-hidden="true" class="wm">&#x25B2;</span>${S.ft_unreadable.replace("{n}", "3")}</h3><p>${S.mb_unread_b}</p></div>` : "";
  return `<section class="card more-c" aria-labelledby="mr-hist"><h2 id="mr-hist" class="more-h">${S.more_hist_h}</h2>${finds}
    <dl class="hist-dl">${row(S.more_l_updated, "6:41 PM")}${row(S.more_l_since, "September 3")}${row(S.more_l_backup, p ? S.ft_backup_failed.replace("{t}", "4:02 AM") : "4:02 AM", p)}${row(S.more_l_prices, "October 28")}</dl></section>`;
}
function aMoreHist(p) {
  return aPage("more", S.nav_more, `<div class="ph"><div><h1>${S.nav_more}</h1></div></div>${histCard(p)}
    <section class="card more-c" aria-labelledby="mr-ref"><h2 id="mr-ref" class="more-h">${S.nav_ref_h}</h2>
      <ul class="more-l"><li><a href="#"><span class="ic" aria-hidden="true">&#x2318;</span>${S.nav_decides}<span class="chev" aria-hidden="true">&#x203A;</span></a></li><li><a href="#"><span class="ic" aria-hidden="true">&#x2261;</span>${S.nav_glossary}<span class="chev" aria-hidden="true">&#x203A;</span></a></li></ul></section>
    <section class="more-v" aria-labelledby="mr-ver"><h2 id="mr-ver" class="more-h">${S.more_ver_h}</h2><p>${S.version}</p></section>`);
}
const noticeStopped = () => `<p class="notice raised-line nt-stop"><span aria-hidden="true" class="wm">&#x25B2;</span><span>${S.nt_stopped.replace("{t}", "6:12 PM").replace("{f}", '<code class="mono">~/.claude/projects</code>')}</span></p>`;
const aNoticeStopped = withFlags({ stoppedAt: "6:12 PM" }, () => aLive().replace('<main class="main" id="main">', `<main class="main" id="main">${noticeStopped()}`));

// First run, M1
const frGate = (inner) => gate(S.fr_h, `<h1>${S.fr_h}</h1><p>${S.fr_body}</p><ol class="well steps">${DONE()}${inner}</ol>`);
const aFirstRunSize = () => frGate(step("now", `<span class="st working">${S.fr_now}</span>`, S.fr_s3,
  `<div class="prog" role="progressbar" aria-valuenow="60" aria-valuemin="0" aria-valuemax="100" aria-valuetext="${S.fr_size.replace("{d}", "1.2").replace("{t}", "2.0 GB")}" aria-label="${S.fr_s3}"><i style="width:60%"></i></div><small class="muted num">${S.fr_size.replace("{d}", "1.2").replace("{t}", "2.0 GB")}</small>`)) ;
const aFirstRunCounting = () => frGate(step("now", `<span class="st working">${S.fr_now}</span>`, S.fr_s3, `<small class="muted" role="status" aria-busy="true">${S.fr_counting}</small>`));
const aFirstRunRetryM1 = () => frGate(step("bad", `<span class="st invalid">${S.fr_failed}</span>`, S.fr_s3, `<small class="muted num">${S.fr_size.replace("{d}", "0.8").replace("{t}", "2.0 GB")}</small>`)).replace("</ol>", `</ol><div class="raised err"><h3><span aria-hidden="true" class="errm">&#x2715;</span>${S.fr_fail_h}</h3><p>${S.fr_fail_reason.replace("{f}", '<code class="mono">~/.claude/projects/tidewater-reporting/9f2c.jsonl</code>')}</p>
  <p class="next-try" role="status"><span aria-hidden="true">&#x21BB;</span> ${S.fr_next_try.replace("{t}", "6:14 PM")}</p><p>${S.fr_fail_fix2}</p>${cmdRow()}</div>`);

// Gate: store_newer
const aStoreNewer = () => gate(S.sn_h, `<span class="gate-w" aria-hidden="true">&#x25B2;</span><h1>${S.sn_h}</h1><p>${S.sn_body.replace("{new}", "0.3.0").replace("{old}", "0.2.1")}</p><p>${S.sn_next}</p>${cmdRow()}`);

// Picker on #/ with no project yet
function aPickerPlaceholder() {
  const tray = `<div class="pk-scrim" aria-hidden="true"></div><div class="pk-pop pk-first" role="dialog" aria-labelledby="pk-h"><header class="pk-h"><h2 id="pk-h">${S.pk_h}</h2></header>${pkList(false).replace(' class="on"', "").replace('aria-selected="true"', 'aria-selected="false"').replace(/<span class="ok" aria-hidden="true">&#x2713;<\/span>/, "")}</div>`;
  document.title = `${S.pk_h}, ${S.product}`;
  let h = aPage("", S.product, ``);
  h = h.replace(`aria-label="${S.project_label}, ${S.project_name}"><small>${S.project_label}</small><b>${S.project_name}<span`, `aria-expanded="true" aria-label="${S.project_label}, ${S.pk_placeholder}"><small>${S.project_label}</small><b class="ph-v">${S.pk_placeholder}<span`).replace('aria-expanded="false" aria-expanded="true"', 'aria-expanded="true"').replace('class="proj"', 'class="proj is-open"');
  h = h.replace(`aria-label="${S.project_label}, ${S.project_name}">${S.project_name}<span`, `aria-label="${S.project_label}, ${S.pk_placeholder}"><span class="ph-v">${S.pk_placeholder}</span><span`).replace('<span class="pname"></span>', `<span class="pname">${S.product}</span>`);
  return h + tray;
}
