// Sessions. A stub for now: the page head only. Ticket U-14 fills this file.

import { clear } from "../h.js";
import { t } from "../format.js";
import { pageHead, rangeControl } from "../components.js";

export function render(root, ctx) {
  clear(root);
  root.appendChild(pageHead({ title: t("nav_sessions"), intro: t("intro_sessions"), right: rangeControl(ctx.range, ctx.setRange) }));
}
