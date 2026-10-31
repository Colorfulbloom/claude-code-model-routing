// Needs attention: every value that does not apply as set, or that the dashboard cannot work out, in groups
// by status. Screen 08 in docs/design/usage-stack/a-usage is the reference, and app.css already holds every
// class used here (section "Needs attention"). The server decides the groups and the order of the rows
// (api_settings._attention). Each row links to its trail. Every value and path comes from the server as
// data, so it goes in as text through h.js and renderText, never as markup.
//
// overviewCard is the short form for the Overview page: the first three rows and a link to this page.

import { h, clear } from "../h.js";
import { t, renderText } from "../format.js";
import { MAIN_KEY, ALL_KEY } from "../router.js";
import { icon } from "../icons.js";
import { pageHead, card, chip, projectPickerEmpty } from "../components.js";
import {
  isMissingFolder, missingFolderState, settingLabel, valueString, valueText, sourceText,
} from "./settings.js";

// The server's payload for the shown project, or null while it is missing or failed.
function payloadOf(ctx) {
  const res = ctx.data && ctx.data.settings;
  return res && res.ok && res.data ? res.data : null;
}

// The plain line under a status. Each key is written out, so the strings test sees every call.
function statusPlain(status) {
  switch (status) {
    case "unknown": return t("p_unknown");
    case "lowered": return t("p_lowered");
    case "ignored": return t("p_ignored");
    case "overridden": return t("p_overridden");
    case "invalid": return t("p_invalid");
    default: return "";
  }
}

// "Main session, Effort" or "builder, Model".
function rowName(route) {
  return (route.agent === MAIN_KEY ? t("row_main") : route.agent) + ", " + settingLabel(route.setting);
}

// The rows of one group with their entries. A row whose entry is missing is dropped.
function rowsOf(payload, group) {
  return group.rows
    .map((r) => ({ status: group.status, route: r.route, entry: (payload.entries || [])[r.entry] }))
    .filter((r) => r.entry);
}

// The rows of every group, in order.
function flatRows(payload) {
  return (payload.attention || []).flatMap((group) => rowsOf(payload, group));
}

// The value and the status chip. The value is left out when it has no text.
function valueAndStatus(row, payload) {
  const hasText = valueString(row.entry, payload, true) !== "";
  return h("span", { class: "at-m" },
    hasText ? h("span", { class: "at-v" }, valueText(row.entry, payload, true)) : null,
    chip(row.status));
}

function fullRow(ctx, payload, row) {
  return h("li", null,
    h("a", { href: ctx.hashFor("trail", row.route) },
      h("span", { class: "at-n" }, rowName(row.route)),
      valueAndStatus(row, payload),
      h("span", { class: "at-s" }, renderText(sourceText(row.entry, payload, true))),
      h("span", { class: "at-go" }, t("open_trail"), icon("arrow", "ic sm"))));
}

function plainRow(ctx, payload, row) {
  return h("li", null,
    h("a", { href: ctx.hashFor("trail", row.route) },
      h("span", { class: "at-n" }, rowName(row.route)),
      valueAndStatus(row, payload),
      h("span", { class: "at-p" }, statusPlain(row.status))));
}

function groupCard(ctx, payload, group) {
  return card({
    title: t("status_" + group.status),
    sub: statusPlain(group.status),
    body: h("ul", { class: "at at-full" }, rowsOf(payload, group).map((row) => fullRow(ctx, payload, row))),
  });
}

// The short card for the Overview: the first three rows across the groups and a link to the page. It is
// null when there is no payload or All projects is picked.
export function overviewCard(ctx) {
  const payload = payloadOf(ctx);
  if (!payload || ctx.project.key === ALL_KEY) return null;
  const rows = flatRows(payload);
  const body = rows.length
    ? [
      h("ul", { class: "at at-plain" }, rows.slice(0, 3).map((row) => plainRow(ctx, payload, row))),
      h("p", { class: "at-more" },
        h("a", { href: ctx.hashFor("attention") }, t("see_all_attention", { n: rows.length }))),
    ]
    : h("p", { class: "at-empty" }, t("at_empty"));
  return card({ title: t("nav_attention"), icon: "issues", sub: t("attention_card_sub"), body });
}

export function render(root, ctx) {
  clear(root);
  root.appendChild(pageHead({ title: t("nav_attention"), intro: t("intro_attention") }));
  if (ctx.project.key === ALL_KEY) {
    root.appendChild(projectPickerEmpty());
    return;
  }
  const payload = payloadOf(ctx);
  if (!payload) return;
  if (isMissingFolder(payload)) {
    root.appendChild(missingFolderState(ctx, payload));
    return;
  }
  const groups = payload.attention || [];
  if (!groups.length) {
    root.appendChild(card({ title: t("nav_attention"), body: h("p", { class: "at-empty" }, t("at_empty")) }));
    return;
  }
  for (const group of groups) root.appendChild(groupCard(ctx, payload, group));
}
