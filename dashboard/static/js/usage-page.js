// The one place every usage page goes through. A page module does clear(root), appends its own page head,
// then calls fillUsage(root, ctx, (u) => nodes). Overview, Agents, Models, Sessions and the detail pages all
// share this, so the empty, waiting and error states (#62) are drawn by this one function and no page checks
// ctx.data.usage itself.
//
// u, the argument draw receives:
//   payload   the /api/usage body
//   view      payload.views[ctx.range]
//   range     "today", "7d" or "30d"
//   project   ctx.project ({ key, name, state })
//   hashFor   ctx.hashFor(name, params, patch), a link to a route in the same project and range; patch
//             changes query keys, such as { project: key } for a link to another project
//   model(id) the display name of a model id, or the id itself when the payload has no name for it
//   est()     the "Estimated at API list price" line

import { h, frag } from "./h.js";
import { t, renderText } from "./format.js";
import { card, estLine, footerLine, emptyState, rangeControl } from "./components.js";
import { ALL_KEY } from "./router.js";

const LONGEST_RANGE = "30d";

// The server sends axis ticks as a list from 0, such as [0, 5, 10, 15]. daybars wants the step and the
// number of steps. A list shorter than two cannot give a step, so it draws one step of 1.
export function ticksOf(list) {
  if (!Array.isArray(list) || list.length < 2) return { step: 1, steps: 1 };
  return { step: list[1] - list[0], steps: list.length - 1 };
}

// The subline under an agent's stacked bar: its most common model and effort, then "and n more" when its
// runs disagree. ran_with is sorted by requests, so the first row is the most common pair.
export function ranWithLine(u, agent) {
  const rows = Array.isArray(agent.ran_with) ? agent.ran_with : [];
  if (!rows.length) return "";
  const first = rows[0];
  const effort = first.effort === null || first.effort === undefined ? t("effort_not_recorded_inline") : first.effort;
  const line = u.model(first.model) + " · " + effort;
  return rows.length > 1 ? line + " " + t("ran_with_more", { n: rows.length - 1 }) : line;
}

// The session with this id, from the 30 day view. That is the widest view, so a session page opened from a
// link in a shorter range still finds its session. Returns null when the view does not hold it.
export function findSession(payload, id) {
  const view = payload && payload.views ? payload.views["30d"] : null;
  const list = view && Array.isArray(view.sessions) ? view.sessions : [];
  return list.find((s) => s.session_id === id) || null;
}

function modelNamer(payload) {
  const names = payload.model_names && typeof payload.model_names === "object" ? payload.model_names : {};
  return (id) => (Object.prototype.hasOwnProperty.call(names, id) && typeof names[id] === "string" ? names[id] : id);
}

// "~/.claude/projects" is the transcripts folder, and the footer sentence adds "/projects" itself.
function configDirOf(transcriptsDir) {
  return transcriptsDir.replace(/\/projects\/?$/, "");
}

// The "No usage in this range" card, with the range switch so a longer range is one click away.
function noRangeCard(ctx, text) {
  return card({
    title: t("c_per_day"),
    icon: "calendar",
    sub: t("q_time"),
    body: h("div", { class: "es" },
      h("p", { class: "es-h" }, renderText(t("s_no_range_h"))),
      h("p", { class: "es-t" }, renderText(text)),
      rangeControl(ctx.range, ctx.setRange)),
  });
}

// The text under "No usage in this range": All projects, a project on the longest range, or any other range.
function noRangeText(ctx) {
  if (ctx.project.key === ALL_KEY) return t("s_no_range_all_t");
  return ctx.range === LONGEST_RANGE ? t("s_no_range_longest_t") : t("s_no_range_t");
}

// The "Folder not found" state of a listed project whose folder is gone. Ported from the Lantern block of
// screen 12. The path comes from the project list, the file from /api/projects.
function missingFolder(ctx) {
  const listed = (ctx.projects || []).find((p) => p.key === ctx.project.key);
  const text = t("es_missing_t", { name: ctx.project.name, path: listed ? listed.path_display : "", config_file: ctx.configFile || "" });
  return h("section", { class: "cd cd-row" },
    h("section", { class: "nt nt-empty", "aria-label": t("es_missing_h") },
      h("h2", { class: "nt-h" }, renderText(t("es_missing_h"))),
      h("p", { class: "nt-t" }, renderText(text))));
}

function transcriptsState(ctx) {
  return emptyState(t("s_transcripts_h"), t("s_transcripts_t", { path: ctx.transcriptsDir }));
}

// Draws the usage page body, or the state that stands in for it. The first match wins, in this order:
//   1. a listed project whose folder is missing
//   2. a transcripts folder the dashboard cannot read
//   3. the payload has not arrived: one waiting line
//   4. the payload failed or has no view for this range: the transcripts state (nothing until the folder is known)
//   5. the project has no usage at all
//   6. the view holds no requests (skipped when opts.anyRange is set, for a page that ignores the range)
//   7. draw(u)
export function fillUsage(root, ctx, draw, opts = {}) {
  if (ctx.project.state === "missing_folder") {
    root.appendChild(missingFolder(ctx));
    return;
  }
  if (ctx.reader && ctx.reader.readable === false) {
    root.appendChild(transcriptsState(ctx));
    return;
  }
  const res = ctx.data.usage;
  if (!res) {
    const files = ctx.reader ? ctx.reader.files : null;
    const line = typeof files === "number" ? t("usage_wait", { n: files.toLocaleString("en-US") }) : t("usage_wait_no_count");
    root.appendChild(h("p", { class: "es-t", role: "status" }, renderText(line)));
    return;
  }
  const payload = res.ok && res.data && typeof res.data === "object" ? res.data : null;
  const view = payload && payload.views ? payload.views[ctx.range] : null;
  if (!view) {
    if (ctx.transcriptsDir) root.appendChild(transcriptsState(ctx));
    return;
  }

  const footer = () => {
    if (ctx.transcriptsDir) root.appendChild(footerLine(configDirOf(ctx.transcriptsDir), payload.generated_at));
  };
  if (payload.no_usage) {
    root.appendChild(ctx.project.key === ALL_KEY
      ? noRangeCard(ctx, t("s_no_range_all_t"))
      : emptyState(t("s_no_usage_h"), t("s_no_usage_t")));
    footer();
    return;
  }
  if (!opts.anyRange && view.totals && view.totals.requests === 0) {
    root.appendChild(noRangeCard(ctx, noRangeText(ctx)));
    footer();
    return;
  }

  const u = {
    payload,
    view,
    range: ctx.range,
    project: ctx.project,
    hashFor: ctx.hashFor,
    model: modelNamer(payload),
    est: () => estLine(payload.prices ? payload.prices.verified_on : null),
  };
  root.appendChild(frag(draw(u)));
  footer();
}
