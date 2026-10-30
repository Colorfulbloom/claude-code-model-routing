// Overview. A stub for now: the page head only. Ticket U-10 fills this file.
// render(root, ctx) is called on every route, project or range change and when a payload arrives.
// ctx.data.usage and ctx.data.settings are null until they arrive, then { ok, status, data }.

import { clear } from "../h.js";
import { t, rangeWord } from "../format.js";
import { pageHead, rangeControl } from "../components.js";

export function render(root, ctx) {
  clear(root);
  const intro = ctx.range === "today"
    ? t("intro_usage_today", { project: ctx.project.name })
    : t("intro_usage", { project: ctx.project.name, range: rangeWord(ctx.range).toLowerCase() });
  root.appendChild(pageHead({ title: t("nav_overview"), intro, right: rangeControl(ctx.range, ctx.setRange) }));
}
