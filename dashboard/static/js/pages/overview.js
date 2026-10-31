// Overview. Ported from `overview` in gen3.py (screen 01). It reads one view of the /api/usage payload, so
// switching range fetches nothing.
// render(root, ctx) is called on every route, project or range change and when a payload arrives.
// ctx.data.usage and ctx.data.settings are null until they arrive, then { ok, status, data }.

import { h, clear } from "../h.js";
import { t, rangeWord } from "../format.js";
import { pageHead, rangeControl } from "../components.js";
import { fillUsage } from "../usage-page.js";
import { usageKpis, perBucketCard, costByModelCard, tokensByAgentCard, cacheCard, effortCard } from "../usage-cards.js";

export function render(root, ctx) {
  clear(root);
  const intro = ctx.range === "today"
    ? t("intro_usage_today", { project: ctx.project.name })
    : t("intro_usage", { project: ctx.project.name, range: rangeWord(ctx.range).toLowerCase() });
  root.appendChild(pageHead({ title: t("nav_overview"), intro, right: rangeControl(ctx.range, ctx.setRange) }));
  fillUsage(root, ctx, (u) => [
    usageKpis(u),
    h("div", { class: "g21" }, perBucketCard(u), costByModelCard(u)),
    h("div", { class: "g2 g2-fill" },
      tokensByAgentCard(u),
      h("div", { class: "stack" }, cacheCard(u), effortCard(u))),
    // The Needs attention card goes here (#63). It stays out until the Settings branch rebases on this one.
  ]);
}
