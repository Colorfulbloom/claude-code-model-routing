// Session detail, at #/sessions/<id>. A stub for now: the page head only. Ticket U-14 fills this file.
// The title is the session id until the usage payload says when the session started. The id is data,
// so it goes in as text and never as markup.

import { clear } from "../h.js";
import { t } from "../format.js";
import { pageHead } from "../components.js";

export function render(root, ctx) {
  clear(root);
  if (ctx.route.name !== "session-detail") return; // the route carries the parameters this page needs
  root.appendChild(pageHead({
    title: ctx.route.params.id,
    crumbs: [{ label: t("nav_sessions"), href: ctx.hashFor("sessions") }],
  }));
}
