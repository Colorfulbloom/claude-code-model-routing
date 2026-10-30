// Rules reference. A stub for now: the page head only. Ticket R-1 fills this file.
// ctx.data.rules is null until /api/rules answers.

import { clear } from "../h.js";
import { t } from "../format.js";
import { pageHead } from "../components.js";

export function render(root, ctx) {
  clear(root);
  root.appendChild(pageHead({ title: t("nav_rules"), intro: t("intro_rules") }));
}
