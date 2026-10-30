// Installed files. A stub for now: the page head only. Ticket E-1 fills this file.
// ctx.data.files is null until /api/files answers.

import { clear } from "../h.js";
import { t } from "../format.js";
import { pageHead } from "../components.js";

export function render(root, ctx) {
  clear(root);
  root.appendChild(pageHead({ title: t("nav_files"), intro: t("intro_files") }));
}
