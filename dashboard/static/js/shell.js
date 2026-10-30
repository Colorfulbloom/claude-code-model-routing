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
  // The panel opens below the top bar, so the menu button stays visible and can close it. Its top and height
  // are measured on open, because the top bar wraps and its height varies at 375, and they are cleared on
  // close. While the panel is open everything behind it is inert, except the menu button: each child of .main
  // other than the top bar, and each child of the top bar other than the button. The nodes marked on open
  // are the nodes cleared on close, whichever path closes. Opening moves focus to the first nav link, and
  // Tab then reaches the menu button after the nav. Escape, a nav link, a click outside and a hashchange
  // close the panel and return focus to the button, because the panel that held focus is gone. Widening past
  // the breakpoint closes it without moving focus, because the button is not where the person was working.
  const main = topbar.parentNode;
  let blocked = [];
  const isOpen = () => sidebar.classList.contains("is-open");
  const elementsOf = (parent) => (parent ? Array.from(parent.childNodes).filter((node) => node.nodeType === 1) : []);
  function setOpen(open) {
    if (open === isOpen()) return;
    sidebar.classList.toggle("is-open", open);
    menu.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      const bottom = Math.max(0, topbar.getBoundingClientRect().bottom);
      sidebar.style.top = bottom + "px";
      sidebar.style.height = "calc(100vh - " + bottom + "px)";
      blocked = elementsOf(main).filter((node) => node !== topbar).concat(elementsOf(topbar).filter((node) => node !== menu));
      blocked.forEach((node) => node.setAttribute("inert", ""));
      const first = links.values().next().value;
      if (first) first.focus();
    } else {
      sidebar.style.top = "";
      sidebar.style.height = "";
      blocked.forEach((node) => node.removeAttribute("inert"));
      blocked = [];
    }
  }
  // Closes and puts focus on the menu button. A nav click closes first, so the hashchange it causes finds the
  // panel already closed and does nothing more.
  function closeToButton() {
    if (!isOpen()) return;
    setOpen(false);
    menu.focus();
  }
  menu.addEventListener("click", () => {
    if (isOpen()) closeToButton();
    else setOpen(true);
  });
  navEl.addEventListener("click", (event) => {
    if (event.target.closest && event.target.closest("a")) closeToButton();
  });
  document.addEventListener("click", (event) => {
    if (!isOpen()) return;
    const target = event.target;
    if (target && (sidebar.contains(target) || menu.contains(target))) return;
    closeToButton();
  });
  window.addEventListener("hashchange", closeToButton);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeToButton();
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
