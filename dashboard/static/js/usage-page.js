// The one place every usage page goes through. A page module does clear(root), appends its own page head,
// then calls fillUsage(root, ctx, (u) => nodes). Overview, Agents, Models, Sessions and the detail pages all
// share this, so the empty, waiting and error states (#62) land in this one function and no page checks
// ctx.data.usage itself.
//
// u, the argument draw receives:
//   payload   the /api/usage body
//   view      payload.views[ctx.range]
//   range     "today", "7d" or "30d"
//   project   ctx.project ({ key, name, state })
//   hashFor   ctx.hashFor(name, params), a link to a route in the same project and range
//   model(id) the display name of a model id, or the id itself when the payload has no name for it
//   est()     the "Estimated at API list price" line

import { frag } from "./h.js";
import { t } from "./format.js";
import { estLine, footerLine } from "./components.js";

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

export function fillUsage(root, ctx, draw) {
  const res = ctx.data.usage;
  const payload = res && res.ok && res.data && typeof res.data === "object" ? res.data : null;
  const view = payload && payload.views ? payload.views[ctx.range] : null;
  if (!view) return; // #62 draws the empty, waiting and error states here

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
  if (ctx.transcriptsDir) root.appendChild(footerLine(configDirOf(ctx.transcriptsDir), payload.generated_at));
}
