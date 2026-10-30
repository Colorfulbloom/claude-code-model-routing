// The sidebar, the top bar, the project switcher and the version chip.
// Ported from nav3, switcher3 and version_chip in gen3.py. The pieces are built once and then
// updated in place, so a focused link or select keeps focus when the route changes.

import { h, clear } from "./h.js";
import { icon } from "./icons.js";
import { t } from "./format.js";
import { ALL_KEY, hashFor } from "./router.js";

const NARROW = "(max-width: 720px)";

// key, label, icon, route name
function navGroups() {
  return [
    {
      label: (project) => (project === ALL_KEY ? t("all_projects") : t("nav_group_project")),
      items: [
        ["overview", t("nav_overview"), "overview"],
        ["agents", t("nav_agents"), "agents"],
        ["models", t("nav_models"), "cpu"],
        ["sessions", t("nav_sessions"), "session"],
        ["settings", t("nav_settings"), "sliders"],
        ["attention", t("nav_attention"), "issues"],
      ],
    },
    {
      label: () => t("nav_group_reference"),
      items: [
        ["files", t("nav_files"), "files"],
        ["rules", t("nav_rules"), "rules"],
      ],
    },
  ];
}

function versionChip(version) {
  if (!version) {
    return h("span", { class: "vchip vchip-unk", role: "img", "aria-label": t("chip_unknown") },
      icon("version", "ic sm"),
      h("span", { class: "vc-long" }, t("chip_unknown")),
      h("span", { class: "vc-short", "aria-hidden": "true" }, t("chip_unknown_short")));
  }
  return h("span", { class: "vchip" }, icon("version", "ic sm"), t("chip_version", { version }));
}

// sidebar and topbar are the empty <aside> and <header> from index.html. onProject(key) is called when
// the select changes.
export function createShell({ sidebar, topbar, onProject }) {
  clear(sidebar);
  clear(topbar);

  // Sidebar
  const groupLabels = [];
  const links = new Map();
  const navEl = h("nav", { class: "sb-nav", "aria-label": t("nav_label") });
  for (const group of navGroups()) {
    const label = h("p", { class: "sb-g" });
    groupLabels.push([label, group.label]);
    const list = h("ul", null);
    for (const [key, text, iconName] of group.items) {
      const link = h("a", { class: "nv", href: "#" }, icon(iconName), h("span", null, text));
      links.set(key, link);
      list.appendChild(h("li", null, link));
    }
    navEl.appendChild(label);
    navEl.appendChild(list);
  }
  sidebar.appendChild(h("div", { class: "sb-brand" }, icon("ring", "ic brand"), h("span", null, t("h1"))));
  sidebar.appendChild(navEl);

  // Top bar
  const menu = h("button", {
    type: "button", class: "btn btn-icon menu", "aria-label": t("menu"), "aria-expanded": "false", "aria-controls": sidebar.id,
  }, icon("menu"));
  const select = h("select", { id: "project", name: "project" });
  const switcher = h("div", { class: "sw" }, h("label", { for: "project" }, t("project_lbl")), select);
  let chip = versionChip(null);
  const right = h("div", { class: "tb-right" }, switcher, chip);
  topbar.appendChild(menu);
  topbar.appendChild(h("div", { class: "tb-title" }, t("h1")));
  topbar.appendChild(right);

  // The menu: a button that opens the sidebar at 375. aria-expanded follows the open state.
  // Opening moves focus to the first nav link and makes the rest of the page (.main, which holds the top bar
  // and the content) inert. Closing, by any path, lifts the inert state. Escape and a nav link move focus back
  // to the menu button, because the panel that held focus is gone.
  const main = topbar.parentNode;
  function setOpen(open) {
    sidebar.classList.toggle("is-open", open);
    menu.setAttribute("aria-expanded", open ? "true" : "false");
    if (main) {
      if (open) main.setAttribute("inert", "");
      else main.removeAttribute("inert");
    }
    if (open) {
      const first = links.values().next().value;
      if (first) first.focus();
    }
  }
  const isOpen = () => sidebar.classList.contains("is-open");
  menu.addEventListener("click", () => setOpen(!isOpen()));
  navEl.addEventListener("click", (event) => {
    if (isOpen() && event.target.closest && event.target.closest("a")) {
      setOpen(false);
      menu.focus();
    }
  });
  document.addEventListener("click", (event) => {
    if (!isOpen()) return;
    const target = event.target;
    if (target && (sidebar.contains(target) || menu.contains(target))) return;
    setOpen(false);
  });
  window.addEventListener("hashchange", () => { if (isOpen()) setOpen(false); });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isOpen()) {
      setOpen(false);
      menu.focus();
    }
  });
  const narrow = window.matchMedia(NARROW);
  const onWide = () => { if (!narrow.matches) setOpen(false); };
  if (narrow.addEventListener) narrow.addEventListener("change", onWide);
  select.addEventListener("change", () => onProject(select.value));

  let shownProjects = "";

  // state: { projects, project, route, nav, query, version }
  function update(state) {
    // Switcher: the listed projects, then All projects. Unlisted folders are never in this list.
    const wanted = JSON.stringify(state.projects.map((p) => [p.key, p.name, p.state]));
    if (wanted !== shownProjects) {
      shownProjects = wanted;
      clear(select);
      for (const p of state.projects) {
        const text = p.state === "missing_folder" ? t("opt_missing", { name: p.name }) : p.name;
        select.appendChild(h("option", { value: p.key }, text));
      }
      select.appendChild(h("option", { value: ALL_KEY }, t("all_projects")));
    }
    select.value = state.project;

    groupLabels.forEach(([label, text]) => { label.textContent = text(state.project); });
    for (const [key, link] of links) {
      const active = key === state.nav;
      link.setAttribute("href", hashFor(key, {}, state.query));
      link.classList.toggle("is-active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }

    const next = versionChip(state.version);
    chip.replaceWith(next);
    chip = next;
  }

  return { update, setOpen, menu, select };
}
