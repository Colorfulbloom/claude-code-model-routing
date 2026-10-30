// Needs attention. A stub for now: the page head only. Ticket C-1 fills this file.

import { clear } from "../h.js";
import { t } from "../format.js";
import { pageHead } from "../components.js";

export function render(root, ctx) {
  clear(root);
  root.appendChild(pageHead({ title: t("nav_attention"), intro: t("intro_attention") }));
}
