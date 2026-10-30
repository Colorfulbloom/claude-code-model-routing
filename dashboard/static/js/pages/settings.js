// Settings. A stub for now: the page head only. Ticket #41 fills this file.
// /api/settings answers 400 for the All project, so the real page shows projectPickerEmpty() there.

import { clear } from "../h.js";
import { t } from "../format.js";
import { pageHead } from "../components.js";

export function render(root, ctx) {
  clear(root);
  root.appendChild(pageHead({ title: t("nav_settings"), intro: t("intro_settings") }));
}
