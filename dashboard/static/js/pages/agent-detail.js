// Agent detail, at #/agents/<name or @main>. A stub for now: the page head only.
// Ticket U-12 fills this file. The agent name is data, so it goes in as text and never as markup.

import { clear } from "../h.js";
import { t } from "../format.js";
import { MAIN_KEY } from "../router.js";
import { pageHead, rangeControl } from "../components.js";

export function render(root, ctx) {
  clear(root);
  if (ctx.route.name !== "agent-detail") return; // the route carries the parameters this page needs
  const agent = ctx.route.params.agent;
  root.appendChild(pageHead({
    title: agent === MAIN_KEY ? t("row_main") : agent,
    right: rangeControl(ctx.range, ctx.setRange),
    crumbs: [{ label: t("nav_agents"), href: ctx.hashFor("agents") }],
  }));
}
