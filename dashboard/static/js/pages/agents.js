// Agents. A stub for now: the page head only. Ticket U-12 fills this file.

import { clear } from "../h.js";
import { t } from "../format.js";
import { ALL_KEY } from "../router.js";
import { pageHead, rangeControl } from "../components.js";

export function render(root, ctx) {
  clear(root);
  // All projects hides the pin check, so its intro does not mention a pin.
  const intro = ctx.project.key === ALL_KEY ? t("intro_agents_all") : t("intro_agents");
  root.appendChild(pageHead({ title: t("nav_agents"), intro, right: rangeControl(ctx.range, ctx.setRange) }));
}
