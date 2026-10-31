// Boot and wiring. Load the strings, then /api/projects, then /api/usage, /api/settings, /api/rules and
// /api/files in parallel. Each page renders again when its own data arrives, and a route the server
// does not answer yet leaves that page's stub showing.
//
// Only the visible section is drawn, the one sectionFor names. A payload that lands for a hidden page waits,
// and moving to that page draws it for the current project and range.
//
// Switching range fetches nothing. Switching project fetches that project's payloads once and keeps
// them in memory. A network error or a 5xx is not kept: /api/projects, the project payloads, rules and files are
// asked for again on the next route change or project change, and never on a range change. A 4xx stays,
// because 404 is the normal answer for a route the server does not have yet.
//
// <html> gets data-rendered="1" when boot finishes, "error" if /api/projects failed ("0" if boot itself failed)
// and data-ox="1" when the page scrolls sideways, for the end-to-end checks. Boot waits for /api/projects,
// /api/settings, rules and files, and never for /api/usage, so a held-back usage payload leaves the
// Settings pages working. A retry that recovers /api/projects sets data-rendered back to "1".
// data-usage="1" follows the first /api/usage answer for the current project, once it is stored and drawn,
// whatever its status. It never resets, and a page that needs usage numbers waits for it.
//
// Editing (js/edit_session.js). The edit token comes in the printed link as #/...?edit=<token>. One session
// takes it from the address before the router reads the hash, at boot and on every hashchange, and then asks
// GET /api/edit for the mode. Boot also waits for that answer before data-rendered, and a failed answer
// leaves the mode null and rejects nothing. After a save, an undo, or a raced or unverified answer, every
// project's cached data is dropped (dropProjectData), the current project is loaded again and the edit
// targets and history are fetched fresh. Targets and history never go through the api cache, and they load
// only on the trail of the main session's effortLevel and on Settings in ready mode, because each targets call runs the resolver many times.
// An answer that was in flight when the data was dropped is thrown away, so it cannot bring the old value back.

import { createApi } from "./api.js";
import { createEditSession } from "./edit_session.js";
import { setStrings, t, DEFAULT_RANGE } from "./format.js";
import {
  PAGES, ALL_KEY, MAIN_KEY, parseHash, hashFor, sectionFor, navFor, showSection, onRouteChange,
} from "./router.js";
import { createShell } from "./shell.js";
import * as overview from "./pages/overview.js";
import * as agents from "./pages/agents.js";
import * as agentDetail from "./pages/agent-detail.js";
import * as models from "./pages/models.js";
import * as sessions from "./pages/sessions.js";
import * as sessionDetail from "./pages/session-detail.js";
import * as settings from "./pages/settings.js";
import * as trail from "./pages/trail.js";
import * as attention from "./pages/attention.js";
import * as files from "./pages/files.js";
import * as rules from "./pages/rules.js";
import * as allProjects from "./pages/all-projects.js";

const MODULES = {
  overview, agents, "agent-detail": agentDetail, models, sessions, "session-detail": sessionDetail,
  settings, trail, attention, files, rules, "all-projects": allProjects,
};

// Which pages each payload feeds. The overview also shows the Needs attention card.
const USAGE_PAGES = ["overview", "agents", "agent-detail", "models", "sessions", "session-detail", "all-projects"];
const SETTINGS_PAGES = ["overview", "settings", "trail", "attention"];

const root = document.documentElement;
const api = createApi();
const state = {
  projects: [],
  current: null,
  version: null,
  route: { name: "overview", params: {}, query: {} },
  project: ALL_KEY,
  range: DEFAULT_RANGE,
  usage: new Map(),
  settings: new Map(),
  rules: null,
  files: null,
  transcriptsDir: null,
  configFile: null,
  reader: null,
  editTargets: null,
  editHistory: null,
};
const loading = new Map();
let generation = 0;
let editSeq = 0;
let sections = {};
let shell = null;

// ---------------------------------------------------------------- the edit session

let storage = null;
try {
  storage = window.sessionStorage || null;
} catch (err) {
  storage = null;
}

const session = createEditSession({
  api,
  storage,
  getHash: () => window.location.hash,
  replaceHash: (hash) => window.history.replaceState(null, "", hash),
  onChange: () => {
    if (!editing()) {
      state.editTargets = null;
      state.editHistory = null;
      editSeq += 1;
    }
    // Draw first: loadEdit does nothing with edits off, and the page still has to show that mode.
    if (started) renderPages(SETTINGS_PAGES);
    if (started && wantsTargets()) loadEdit();
  },
  onWrite: () => refreshAll(),
});

// Runs first on every hashchange, because it is registered before boot adds the router's listener. The router's
// parseHash then never sees edit=.
window.addEventListener("hashchange", () => {
  if (session.take()) session.refresh();
});

const editing = () => session.mode() === "locked" || session.mode() === "ready";

// The one route that shows an edit control: the main session's effortLevel trail.
function onEditRoute() {
  const r = state.route;
  return r.name === "trail" && r.params.agent === MAIN_KEY && r.params.setting === "effortLevel";
}

// Targets load on the edit route, and on Settings in ready mode, where they decide whether the page says editing
// is on. Settings never waits on them: it draws first and draws again when they land. All projects loads none.
function wantsTargets() {
  return onEditRoute() || (state.route.name === "settings" && session.mode() === "ready");
}

// Forgets every project's data, so nothing drawn after a write comes from before it. The generation makes
// an answer that is still on its way, asked for before this call, drop itself when it lands.
function dropProjectData() {
  generation += 1;
  api.dropProjects();
  loading.clear();
  state.settings.clear();
  state.usage.clear();
}

// Forgets the project data and loads it again, with fresh targets and history. It runs after a write, and when
// the edit card learns that a file changed behind its back. It starts both payloads but waits on settings only.
// It must never wait on /api/usage: a warm-up can hold that answer for a long time, and the card stays on
// Saving until this returns.
async function refreshAll() {
  dropProjectData();
  loadProject(state.project);
  await Promise.all([api.settings(state.project), loadEdit()]);
}

// Targets and history for the current project, fetched fresh every time and never cached.
async function loadEdit() {
  if (!editing() || state.project === ALL_KEY) return;
  const project = state.project;
  const mine = ++editSeq;
  const [targets, history] = await Promise.all([api.editTargets(project), api.editHistory(project)]);
  if (mine !== editSeq || project !== state.project) return;
  state.editTargets = targets;
  state.editHistory = history;
  renderPages(SETTINGS_PAGES);
}

// ---------------------------------------------------------------- state to page context

function projectInfo() {
  const known = state.projects.find((p) => p.key === state.project);
  return { key: state.project, name: known ? known.name : t("all_projects"), state: known ? known.state : null };
}

function go(name, params, patch) {
  const query = Object.assign({}, state.route.query, patch);
  window.location.hash = hashFor(name, params, query);
}

// What a page module receives. data.* is null until that payload arrives, then { ok, status, data }.
// transcriptsDir and configFile are the display forms of the transcripts folder and routing-dashboard.json
// (a string, or null), and reader is the reader's state ({ readable, warm, files, skipped }, or null), both from /api/projects.
function context() {
  return {
    route: { name: state.route.name, params: state.route.params },
    project: projectInfo(),
    projects: state.projects,
    range: state.range,
    version: state.version,
    transcriptsDir: state.transcriptsDir,
    configFile: state.configFile,
    reader: state.reader,
    data: {
      usage: state.usage.get(state.project) || null,
      settings: state.settings.get(state.project) || null,
      rules: state.rules,
      files: state.files,
    },
    // patch is optional and wins over the current query, as in a link from All projects to one project.
    hashFor: (name, params, patch) => hashFor(name, params, Object.assign({}, state.route.query, patch)),
    setRange: (range) => go(state.route.name, state.route.params, { range }),
    // The edit session. targets and history are { ok, status, data } or null. The three actions fill in the
    // current project and resolve to an outcome { kind, res }. The token never leaves the session.
    edit: {
      mode: session.mode(),
      targets: state.editTargets,
      history: state.editHistory,
      preview: (target, value) => session.preview(state.project, target, value),
      save: (preview, target, value) => session.save(state.project, preview, target, value),
      undo: (editId) => session.undo(state.project, editId),
      reload: loadEdit,
      refresh: refreshAll,
    },
  };
}

// A rebuilt page head removes the range radio that held focus. Note the section it was in, then focus the
// active radio of the rebuilt control in that section.
function focusedRangeSection() {
  let el = document.activeElement;
  let inGroup = false;
  while (el && el !== document.body) {
    if (el.getAttribute && el.getAttribute("role") === "radiogroup") inGroup = true;
    if (inGroup && el.getAttribute && el.getAttribute("data-page")) return el;
    el = el.parentNode;
  }
  return null;
}

// Draws the pages in names that are on screen. The others wait until a route change shows them.
function renderPages(names) {
  const visible = sectionFor(state.route, state.project);
  const keep = focusedRangeSection();
  const ctx = context();
  for (const name of names) {
    if (name !== visible) continue;
    try {
      MODULES[name].render(sections[name], ctx);
    } catch (err) {
      console.error("page " + name + " failed to render", err);
    }
  }
  if (keep && !keep.contains(document.activeElement)) {
    const radio = keep.querySelector('[role="radio"][aria-checked="true"]');
    if (radio) radio.focus();
  }
  measure();
}

function measure() {
  root.setAttribute("data-ox", root.scrollWidth > root.clientWidth ? "1" : "0");
}

// ---------------------------------------------------------------- data

// Asks for a project's two payloads once. Later calls return the same promise.
function loadProject(key) {
  if (loading.has(key)) return loading.get(key);
  const gen = generation;
  const done = Promise.all([
    api.usage(key).then((res) => {
      if (gen !== generation) return;
      state.usage.set(key, res);
      if (key === state.project) {
        renderPages(USAGE_PAGES);
        root.setAttribute("data-usage", "1");
      }
    }),
    api.settings(key).then((res) => {
      if (gen !== generation) return;
      state.settings.set(key, res);
      if (key === state.project) renderPages(SETTINGS_PAGES);
    }),
  ]);
  loading.set(key, done);
  // A failed answer that the api did not keep (network error, 5xx) is asked for again next time.
  done.then(() => { if (!api.hasProject(key) && loading.get(key) === done) loading.delete(key); });
  return done;
}

// The api returns its kept promise when it has one, so a page already holding that answer is not drawn again.
function loadShared() {
  return Promise.all([
    api.rules().then((res) => { if (state.rules !== res) { state.rules = res; renderPages(["rules"]); } }),
    api.files().then((res) => { if (state.files !== res) { state.files = res; renderPages(["files"]); } }),
  ]);
}

let projectsOk = false;
let projectsRes = null;
let projectsRetry = null;

function readProjects(res) {
  projectsRes = res;
  projectsOk = Boolean(res.ok);
  const body = res.ok && res.data && typeof res.data === "object" ? res.data : {};
  const list = Array.isArray(body.projects) ? body.projects : [];
  state.projects = list.filter((p) => p && typeof p.key === "string" && typeof p.name === "string");
  state.current = typeof body.current === "string" ? body.current : null;
  // The transcripts folder and the reader state come with the usage routes. The version and the time zone
  // arrive in later tickets, so every one of these is optional.
  state.transcriptsDir = typeof body.transcripts_dir_display === "string" ? body.transcripts_dir_display : null;
  state.configFile = typeof body.config_file_display === "string" ? body.config_file_display : null;
  state.reader = body.reader && typeof body.reader === "object" ? body.reader : null;
  const version = body.version;
  state.version = typeof version === "string" ? version : (version && version.installed) || null;
}

// ---------------------------------------------------------------- routing

function applyTheme(theme) {
  if (theme) root.setAttribute("data-theme", theme);
  else root.removeAttribute("data-theme");
}

function resolveProject(wanted) {
  const keys = state.projects.map((p) => p.key);
  if (wanted && (wanted === ALL_KEY || keys.includes(wanted))) return wanted;
  if (state.current && keys.includes(state.current)) return state.current;
  return keys.length ? keys[0] : ALL_KEY;
}

let started = false;

// A failed /api/projects is asked for again, once at a time. When it recovers the page is drawn again from
// the same address, so the switcher fills and data-rendered becomes "1".
function retryProjects() {
  if (projectsOk || projectsRetry) return;
  projectsRetry = api.projects().then((res) => {
    projectsRetry = null;
    if (res === projectsRes) return;
    readProjects(res);
    if (!projectsOk) return;
    root.setAttribute("data-rendered", "1");
    handle(parseHash(window.location.hash), true);
  });
}

// A route is its page and parameters, without the query. The same route in the same project is a range or
// theme change, which fetches nothing.
const routeKey = (route) => hashFor(route.name, route.params, {});

function handle(route, force) {
  let parsed = route;
  if (!parsed.known) {
    // An unknown route shows the overview. Rewrite the address without adding a history entry.
    const hash = hashFor("overview", {}, parsed.query);
    window.history.replaceState(null, "", hash);
    parsed = parseHash(hash);
  }
  const previous = state.route.name;
  const project = resolveProject(parsed.query.project);
  const fetches = !started || force || routeKey(parsed) !== routeKey(state.route) || project !== state.project;
  if (project !== state.project) {
    state.editTargets = null;
    state.editHistory = null;
    editSeq += 1;
  }
  state.route = parsed;
  state.project = project;
  state.range = parsed.query.range || DEFAULT_RANGE;
  applyTheme(parsed.query.theme);
  document.title = t("tab_title", { project: projectInfo().name });
  shell.update({
    projects: state.projects, project: state.project, nav: navFor(parsed), query: parsed.query, version: state.version,
  });
  showSection(sections, sectionFor(parsed, state.project));
  if (fetches) {
    loadProject(state.project);
    if (wantsTargets()) loadEdit();
    if (started && !force) {
      retryProjects();
      loadShared();
    }
  }
  renderPages([sectionFor(parsed, state.project)]);
  if (started && !force && previous !== parsed.name) window.scrollTo(0, 0);
}

// ---------------------------------------------------------------- boot

function collectSections() {
  const found = {};
  document.querySelectorAll("main [data-page]").forEach((el) => { found[el.getAttribute("data-page")] = el; });
  for (const name of PAGES) {
    if (!found[name]) throw new Error("index.html has no section for " + name);
  }
  return found;
}

async function boot() {
  // First, before any await, so the token is out of the address bar while the strings load.
  session.take();
  const editReady = session.refresh().catch((err) => { console.error("the edit status could not be read", err); });
  const strings = await api.strings();
  if (!strings.ok) throw new Error("strings.json did not load");
  setStrings(strings.data);
  readProjects(await api.projects());

  sections = collectSections();
  shell = createShell({
    sidebar: document.getElementById("sidebar"),
    topbar: document.getElementById("topbar"),
    onProject: (key) => go(state.route.name, state.route.params, { project: key }),
  });
  onRouteChange(handle);
  handle(parseHash(window.location.hash));
  started = true;

  // handle() has already asked for the project's payloads. api.settings returns the same kept promise, so
  // this waits on settings, rules and files only. It must never wait on /api/usage: a held-back usage
  // payload leaves the Settings pages working, and data-usage tells a check when the usage pages are drawn.
  await Promise.all([api.settings(state.project), loadShared(), editReady]);
  measure();
  // Only /api/projects decides this. A held-back /api/usage must not block it.
  root.setAttribute("data-rendered", projectsOk ? "1" : "error");
}

window.addEventListener("resize", measure);
boot().catch((err) => {
  console.error("the dashboard could not start", err);
  root.setAttribute("data-rendered", "0");
});
