// The trail of what decides one value, at #/settings/<agent key>/<setting key>. A stub for now: the
// page head only. Ticket #42 fills this file. Both keys are data, so they go in as text.

import { clear } from "../h.js";
import { t } from "../format.js";
import { MAIN_KEY } from "../router.js";
import { pageHead } from "../components.js";

export function render(root, ctx) {
  clear(root);
  if (ctx.route.name !== "trail") return; // the route carries the parameters this page needs
  const { agent, setting } = ctx.route.params;
  const title = agent === MAIN_KEY ? t("trail_h", { setting }) : t("trail_h_agent", { setting, agent });
  root.appendChild(pageHead({ title }));
}
