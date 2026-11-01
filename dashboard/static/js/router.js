// Hash routes. The router only parses the hash and shows or hides the page sections. Each section is
// filled by its own module in js/pages/.
//
//   #/overview                         #/models
//   #/agents                           #/sessions
//   #/agents/<name or @main>           #/sessions/<id>
//   #/settings                         #/settings/<agent key>/<setting key>   (the trail)
//   #/attention   #/files   #/rules
//
// Project, range and theme travel in the query part of the hash: #/agents?project=api&range=7d.
// The Settings page also reads setting, the cell of the band it shows: #/settings?setting=model.
// "@main" is the stable key for the main session, so it cannot clash with an agent named main. Every
// other name is URL-encoded. An unknown route goes to the overview.

import { RANGES } from "./format.js";

// One section and one module per page. The overview route fills "all-projects" when the project is All.
export const PAGES = [
  "overview", "agents", "agent-detail", "models", "sessions", "session-detail",
  "settings", "trail", "attention", "files", "rules", "all-projects",
];

export const MAIN_KEY = "@main";
export const ALL_KEY = "all";
const THEMES = ["light", "dark"];

// The settings that have a cell in the Settings band, in the saved order of the cells. pages/settings.js keeps
// the same keys in TILES, and a check holds the two together. An unknown value of ?setting= reads as null.
export const BAND_SETTINGS = ["model", "effortLevel", "maxEffortLevel", "autoCompactWindow", "promptCacheTtl"];

const encodeKey = (value) => (value === MAIN_KEY ? MAIN_KEY : encodeURIComponent(value));

// The path part of a route, such as "/agents/builder".
export function routePath(name, params = {}) {
  switch (name) {
    case "agent-detail": return "/agents/" + encodeKey(params.agent);
    case "session-detail": return "/sessions/" + encodeURIComponent(params.id);
    case "trail": return "/settings/" + encodeKey(params.agent) + "/" + encodeURIComponent(params.setting);
    case "overview": case "agents": case "models": case "sessions":
    case "settings": case "attention": case "files": case "rules":
      return "/" + name;
    default: return "/overview";
  }
}

export function queryString(query = {}) {
  const parts = new URLSearchParams();
  if (query.project) parts.set("project", query.project);
  if (query.range) parts.set("range", query.range);
  if (query.theme) parts.set("theme", query.theme);
  if (query.setting) parts.set("setting", query.setting);
  return parts.toString();
}

export function hashFor(name, params, query) {
  const q = queryString(query);
  return "#" + routePath(name, params) + (q ? "?" + q : "");
}

function decode(segment) {
  try {
    const value = decodeURIComponent(segment);
    return value === "" ? null : value;
  } catch (err) {
    return null;
  }
}

// Returns { name, params, query, known }. An unknown route comes back as the overview with known false,
// so the app can rewrite the hash. query.project is the raw value; the app decides if it is a real project.
// query.setting belongs to the Settings page alone, so every other route reads it as null.
export function parseHash(hash) {
  const parsed = parseRoute(hash);
  if (parsed.name !== "settings") parsed.query.setting = null;
  return parsed;
}

function parseRoute(hash) {
  const raw = String(hash || "").replace(/^#/, "");
  const cut = raw.indexOf("?");
  const path = cut < 0 ? raw : raw.slice(0, cut);
  const search = new URLSearchParams(cut < 0 ? "" : raw.slice(cut + 1));
  const range = search.get("range");
  const theme = search.get("theme");
  const setting = search.get("setting");
  const query = {
    project: search.get("project") || null,
    range: RANGES.includes(range) ? range : null,
    theme: THEMES.includes(theme) ? theme : null,
    setting: BAND_SETTINGS.includes(setting) ? setting : null,
  };
  const segments = path.replace(/^\/+/, "").replace(/\/+$/, "").split("/");
  const [first, second, third] = segments;
  const route = (name, params = {}) => ({ name, params, query, known: true });
  const unknown = { name: "overview", params: {}, query, known: false };

  if (path === "" || path === "/") return { name: "overview", params: {}, query, known: true };
  if (segments.length === 1) {
    return ["overview", "agents", "models", "sessions", "settings", "attention", "files", "rules"].includes(first)
      ? route(first) : unknown;
  }
  if (first === "agents" && segments.length === 2) {
    const agent = decode(second);
    return agent ? route("agent-detail", { agent }) : unknown;
  }
  if (first === "sessions" && segments.length === 2) {
    const id = decode(second);
    return id ? route("session-detail", { id }) : unknown;
  }
  if (first === "settings" && segments.length === 3) {
    const agent = decode(second);
    const setting = decode(third);
    return agent && setting ? route("trail", { agent, setting }) : unknown;
  }
  return unknown;
}

// The section a route shows.
export function sectionFor(route, project) {
  return route.name === "overview" && project === ALL_KEY ? "all-projects" : route.name;
}

// The sidebar item a route lights up. The all-projects page is the overview in all mode (review #23).
export function navFor(route) {
  switch (route.name) {
    case "agent-detail": return "agents";
    case "session-detail": return "sessions";
    case "trail": return "settings";
    default: return route.name;
  }
}

// Show the active section and hide the rest. Nothing else.
export function showSection(sections, name) {
  for (const [page, el] of Object.entries(sections)) el.hidden = page !== name;
}

export function onRouteChange(handler) {
  window.addEventListener("hashchange", () => handler(parseHash(window.location.hash)));
}
