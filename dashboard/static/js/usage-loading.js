// The loading and error states of the usage pages (fillUsage in usage-page.js calls these).
//
// While /api/usage is pending, a strip takes the place of the KPI row. It says what the reader is doing in
// three stages (find the files, read them, add up usage) and shows an honest files-read count and bar. Under it
// Overview and All projects keep the real layout as placeholder cards, so nothing jumps when the numbers land.
// When /api/usage fails, one notice with a Try again button takes the place of both.
//
// The strip node is kept for each page section and reused on every render, and the poll in app.js updates it in
// place (updateStrips). That keeps the screen reader's status line stable: it changes only when the stage
// changes, never on every count. The notice node is kept the same way, so a retry that is still running changes
// the button and nothing else, and does not announce the alert a second time.
//
// Geometry goes through one custom property (--ld-pct, read by .ld-fill in app.css). Nothing here writes a
// style attribute, because the page's Content-Security-Policy refuses one.

import { h, frag, clear } from "./h.js";
import { icon } from "./icons.js";
import { t } from "./format.js";
import { card } from "./components.js";
import { ALL_KEY } from "./router.js";

const count = (n) => n.toLocaleString("en-US");

// What the strip shows for the reader's state. kind is find, read or add. line is the visible stage line, which
// the progress bar also carries as its value text, and sr is the line the screen reader status says when the
// stage changes. n and total feed the bar.
//   find  the reader has not counted the files yet (reader null or reader.files null)
//   add   the reader is warm: every file is read and the server is adding up usage. The bar is full.
//   read  otherwise. n is files_read, kept between 0 and the total.
export function loadStage(reader, projectName, isAll) {
  const files = reader && typeof reader.files === "number" ? reader.files : null;
  if (files === null) {
    const line = t("load_stage_find");
    return { kind: "find", n: 0, total: 0, line, sr: line };
  }
  if (reader.warm === true) {
    const line = isAll ? t("load_stage_add_all") : t("load_stage_add", { project: projectName });
    return { kind: "add", n: files, total: files, line, sr: line };
  }
  const read = typeof reader.files_read === "number" ? reader.files_read : 0;
  const n = Math.min(Math.max(read, 0), files);
  const slots = { n: count(n), total: count(files) };
  return {
    kind: "read",
    n,
    total: files,
    line: files === 1 ? t("load_stage_read_one", slots) : t("load_stage_read", slots),
    sr: files === 1 ? t("load_sr_read_one", { total: slots.total }) : t("load_sr_read", { total: slots.total }),
  };
}

// ---------------------------------------------------------------- the strip

const stripOf = new WeakMap(); // page section -> its strip
const strips = new Set();
let stripSeq = 0;

function buildStrip(root, ctx) {
  const id = "ld-h-" + (stripSeq += 1);
  const meter = h("div", { class: "ld-meter", "aria-hidden": "true" });
  const stage = h("p", { class: "ld-stage" });
  const live = h("p", { class: "sr", role: "status" });
  // Decided once, when the strip is made: a wait that began with the reader already warm gets its own note.
  const note = ctx.usageLoading.warm ? t("load_note_warm") : t("load_note");
  const node = h("section", { class: "cd ld-strip" },
    h("div", { class: "ld-strip-l" },
      h("span", { class: "cd-ic" }, icon("clock")),
      h("div", null, h("h2", { class: "cd-h", id }, t("load_h")), h("p", { class: "cd-sub" }, note))),
    h("div", { class: "ld-strip-r" }, meter, stage),
    live);
  let fill = null;
  let lastKind = null;
  const strip = {
    root,
    key: ctx.usageLoading.key,
    node,
    update(next) {
      clear(stage);
      stage.appendChild(document.createTextNode(next.line));
      if (next.kind === "find") {
        // The track keeps its space, so the cards below do not drop when the read stage starts. It is no
        // progress bar yet, because there is nothing to measure.
        for (const name of ["role", "aria-labelledby", "aria-valuemin", "aria-valuemax", "aria-valuenow", "aria-valuetext"]) {
          meter.removeAttribute(name);
        }
        meter.setAttribute("aria-hidden", "true");
        if (fill) { meter.removeChild(fill); fill = null; }
      } else {
        meter.removeAttribute("aria-hidden");
        meter.setAttribute("role", "progressbar");
        meter.setAttribute("aria-labelledby", id);
        meter.setAttribute("aria-valuemin", "0");
        meter.setAttribute("aria-valuemax", String(next.total));
        meter.setAttribute("aria-valuenow", String(next.n));
        meter.setAttribute("aria-valuetext", next.line);
        if (!fill) { fill = h("span", { class: "ld-fill" }); meter.appendChild(fill); }
        const pct = next.total > 0 ? Math.round((1000 * next.n) / next.total) / 10 : 0;
        fill.style.setProperty("--ld-pct", pct + "%");
      }
      if (next.kind !== lastKind) {
        lastKind = next.kind;
        const kind = next.kind;
        const put = () => {
          if (lastKind !== kind) return;
          clear(live);
          live.appendChild(document.createTextNode(next.sr));
        };
        // A live region announces a change, not the text it was inserted with. The first stage is written just
        // after the strip is on the page, so a screen reader says it.
        if (node.isConnected === false) setTimeout(put, 50);
        else put();
      }
    },
  };
  return strip;
}

const stageOf = (ctx) => loadStage(ctx.reader, ctx.project.name, ctx.project.key === ALL_KEY);

// The strip for this page section. The same strip comes back while the same wait goes on (ctx.usageLoading.key),
// so the section can be drawn again without a new live region.
export function loadingStrip(root, ctx) {
  let strip = stripOf.get(root);
  if (!strip || strip.key !== ctx.usageLoading.key) {
    strip = buildStrip(root, ctx);
    stripOf.set(root, strip);
    strips.add(strip);
  }
  strip.update(stageOf(ctx));
  return strip.node;
}

// The poll's way in: draws the new reader state into every strip that is on screen, without touching the
// rest of the page. project is { key, name }.
export function updateStrips(reader, project) {
  for (const strip of [...strips]) {
    if (!strip.root.contains(strip.node)) { strips.delete(strip); continue; }
    strip.update(loadStage(reader, project.name, project.key === ALL_KEY));
  }
}

// ---------------------------------------------------------------- placeholder cards

const bone = (cls = "") => h("span", { class: ["ld-bone", cls] });

// A card of the real layout with shapes where the body will be. The shapes are hidden from a screen reader, and
// the card says once that it is loading.
function busyCard({ title, icon: iconName, sub = null, kind, shapes }) {
  const node = card({ title, icon: iconName, sub, body: h("div", { class: ["ld-body", "ld-k-" + kind], "aria-hidden": "true" }, shapes) });
  node.setAttribute("aria-busy", "true");
  node.appendChild(h("span", { class: "sr" }, t("load_sr_busy", { card: title })));
  return node;
}

const rowShapes = (labelClass) => [0, 1, 2, 3].map(() => h("div", { class: "ld-row" }, bone(labelClass), bone("ld-track")));

function perBucketBusy(ctx) {
  return busyCard({
    title: ctx.range === "today" ? t("c_per_hour") : t("c_per_day"), icon: "calendar", sub: t("q_time"), kind: "chart", shapes: bone("ld-plot"),
  });
}

function costBusy() {
  return busyCard({
    title: t("c_cost_model"), icon: "coins", sub: t("q_cost_model"), kind: "ring",
    shapes: [h("span", { class: "ld-ring" }), h("div", { class: "ld-lines" }, bone(), bone(), bone(), bone())],
  });
}

// The placeholders for a page, in the order and the nesting of the loaded page. page is overview or all-projects.
// Every other usage page shows the strip alone.
export function loadingCards(page, ctx) {
  const top = h("div", { class: "g21" }, perBucketBusy(ctx), costBusy());
  if (page === "all-projects") {
    return frag(top, h("div", { class: "g2" },
      busyCard({ title: t("c_tokens_project"), icon: "bars", sub: t("q_where"), kind: "rows", shapes: rowShapes("ld-bone-l") }),
      busyCard({ title: t("c_projects_table"), icon: "overview", kind: "rows", shapes: rowShapes("ld-bone-s") })));
  }
  return frag(top, h("div", { class: "g2 g2-fill" },
    busyCard({ title: t("c_tokens_agent"), icon: "agents", sub: t("q_where"), kind: "rows", shapes: rowShapes("ld-bone-l") }),
    h("div", { class: "stack" },
      busyCard({
        title: t("c_cache_agent"), icon: "cache", sub: t("q_cache"), kind: "minis",
        shapes: [0, 1, 2, 3].map(() => h("div", { class: "ld-mini" }, h("span", { class: "ld-ring ld-ring-s" }), bone("ld-bone-s"))),
      }),
      busyCard({ title: t("c_effort"), icon: "sliders", sub: t("q_effort"), kind: "rows", shapes: rowShapes("ld-bone-s") }))));
}

// ---------------------------------------------------------------- the error notice

const noticeOf = new WeakMap(); // page section -> its notice
const notices = new Set();

function setButton(button, retrying) {
  clear(button);
  if (retrying) {
    // Same node, so focus stays on it. aria-disabled, not disabled, because a disabled button drops focus.
    button.setAttribute("aria-disabled", "true");
    button.appendChild(icon("refresh", "ic sm"));
    button.appendChild(document.createTextNode(t("err_retrying")));
  } else {
    button.removeAttribute("aria-disabled");
    button.appendChild(document.createTextNode(t("ed_try_again")));
  }
}

function buildNotice(root, ctx, res) {
  const usage = ctx.usageLoading;
  const mark = h("span", { class: "p2-mk", "aria-hidden": "true" }, "✕");
  const button = h("button", {
    type: "button",
    class: "btn",
    on: { click: () => { if (button.getAttribute("aria-disabled") !== "true") usage.retry(); } },
  });
  // A network failure reads status 0. Anything else (a 5xx, another refusal, or an answer with no view) is the server's.
  const text = res && res.status === 0 ? t("err_t_offline") : t("err_t_server");
  const node = h("section", { class: "nt p2-nt p2-nt-err ld-err", role: "alert" },
    h("div", { class: "p2-nt-h" }, mark, h("h2", { class: "ld-err-h" }, t("err_h"))),
    h("p", null, text),
    h("div", { class: "p2-btns" }, button));
  return { root, key: res, node, button, sync: (retrying) => setButton(button, retrying) };
}

// The notice for this page section and this failed answer. The same answer gives the same node, so a render
// while a retry runs only syncs the button. A new failed answer gives a new node, which a screen reader
// announces again.
export function errorNotice(root, ctx, res) {
  let notice = noticeOf.get(root);
  if (!notice || notice.key !== res) {
    notice = buildNotice(root, ctx, res);
    noticeOf.set(root, notice);
    notices.add(notice);
  }
  notice.sync(ctx.usageLoading.retrying);
  return notice.node;
}

// A retry started or ended: changes the button of every notice on screen and nothing else.
export function setRetrying(on) {
  for (const notice of [...notices]) {
    if (!notice.root.contains(notice.node)) { notices.delete(notice); continue; }
    notice.sync(on);
  }
}

// True when focus is inside this section's notice.
export function noticeFocused(root) {
  const notice = noticeOf.get(root);
  return Boolean(notice && notice.node.contains(document.activeElement));
}

function firstTag(node, tag) {
  for (const child of node.childNodes || []) {
    if (child.tagName && String(child.tagName).toLowerCase() === tag) return child;
    const found = firstTag(child, tag);
    if (found) return found;
  }
  return null;
}

// After a retry that held focus in the notice: the new Try again button when the retry failed and drew a new
// notice, else the page heading, because the notice that held focus is gone and focus would fall to the body.
export function settleFocus(root) {
  const notice = noticeOf.get(root);
  if (notice && root.contains(notice.node)) {
    notice.button.focus();
    return;
  }
  const heading = firstTag(root, "h1");
  if (!heading) return;
  heading.setAttribute("tabindex", "-1");
  heading.focus();
}
