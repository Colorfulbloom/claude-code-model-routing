// Models. A stub for now: the page head only. Ticket U-13 fills this file.

import { clear } from "../h.js";
import { t } from "../format.js";
import { pageHead, rangeControl } from "../components.js";

export function render(root, ctx) {
  clear(root);
  root.appendChild(pageHead({ title: t("nav_models"), intro: t("intro_models"), right: rangeControl(ctx.range, ctx.setRange) }));
}
