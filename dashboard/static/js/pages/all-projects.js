// All projects: the overview when the project is All. A stub for now: the page head only.
// Ticket U-11 fills this file.

import { clear } from "../h.js";
import { t, rangeWord } from "../format.js";
import { pageHead, rangeControl } from "../components.js";

export function render(root, ctx) {
  clear(root);
  const intro = ctx.range === "today"
    ? t("intro_all_today")
    : t("intro_all", { range: rangeWord(ctx.range).toLowerCase() });
  root.appendChild(pageHead({ title: t("all_projects"), intro, right: rangeControl(ctx.range, ctx.setRange) }));
}
