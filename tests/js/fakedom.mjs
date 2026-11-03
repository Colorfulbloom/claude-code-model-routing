// A very small DOM, just enough to run the dashboard modules in Node without a browser. It covers what
// h.js, shell.js, app.js and the page modules touch: elements, text, attributes, classes, el.style, events
// that bubble to the document, focus, and the media query and hash change hooks on window.
export class FNode {
  constructor() { this.childNodes = []; this.parentNode = null; }
  get firstChild() { return this.childNodes[0] || null; }
  appendChild(child) {
    if (child instanceof FFragment) {
      for (const c of [...child.childNodes]) this.appendChild(c);
      return child;
    }
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = this;
    this.childNodes.push(child);
    return child;
  }
  removeChild(child) {
    const i = this.childNodes.indexOf(child);
    if (i >= 0) this.childNodes.splice(i, 1);
    child.parentNode = null;
    return child;
  }
  replaceWith(next) {
    const p = this.parentNode;
    const i = p.childNodes.indexOf(this);
    p.childNodes.splice(i, 1, next);
    next.parentNode = p;
    this.parentNode = null;
  }
  contains(node) {
    for (let n = node; n; n = n.parentNode) if (n === this) return true;
    return false;
  }
}

export class FText extends FNode {
  constructor(data) { super(); this.data = data; this.nodeType = 3; }
  get textContent() { return this.data; }
}

export class FFragment extends FNode { constructor() { super(); this.nodeType = 11; } }

class ClassList {
  constructor(el) { this.el = el; }
  list() { return (this.el.getAttribute("class") || "").split(/\s+/).filter(Boolean); }
  contains(c) { return this.list().includes(c); }
  add(c) { if (!this.contains(c)) this.el.setAttribute("class", this.list().concat(c).join(" ")); }
  remove(c) { this.el.setAttribute("class", this.list().filter((x) => x !== c).join(" ")); }
  toggle(c, force) {
    const on = force === undefined ? !this.contains(c) : force;
    if (on) this.add(c); else this.remove(c);
    return on;
  }
}

export class FElement extends FNode {
  constructor(tag, ns) {
    super();
    this.tagName = tag;
    this.namespaceURI = ns || null;
    this.nodeType = 1;
    this.attrs = new Map();
    this.listeners = {};
    this.styleMap = {};
    this.rect = { left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0 };
    const self = this;
    this.style = new Proxy({}, {
      set(_t, k, v) { self.styleMap[k] = v; return true; },
      get(_t, k) {
        if (k === "setProperty") return (n, v) => { self.styleMap[n] = v; };
        return self.styleMap[k];
      },
    });
    this.classList = new ClassList(this);
  }
  setAttribute(k, v) { this.attrs.set(k, String(v)); }
  getAttribute(k) { return this.attrs.has(k) ? this.attrs.get(k) : null; }
  removeAttribute(k) { this.attrs.delete(k); }
  hasAttribute(k) { return this.attrs.has(k); }
  get hidden() { return this.attrs.has("hidden"); }
  set hidden(v) { if (v) this.attrs.set("hidden", ""); else this.attrs.delete("hidden"); }
  get id() { return this.getAttribute("id") || ""; }
  get textContent() { return this.childNodes.map((c) => c.textContent).join(""); }
  set textContent(v) { this.childNodes = []; this.appendChild(new FText(String(v))); }
  get open() { return this.attrs.has("open"); }
  getBoundingClientRect() { return this.rect; }
  // A listener added with true or { capture: true } runs in the capture phase, from the document down to the target.
  addEventListener(type, fn, options) {
    (this.listeners[type] = this.listeners[type] || []).push(fn);
    if (options === true || (options && options.capture)) (this.captureFns = this.captureFns || new Set()).add(fn);
  }
  removeEventListener(type, fn) {
    const list = this.listeners[type];
    if (!list || !list.includes(fn)) return;
    list.splice(list.indexOf(fn), 1);
    if (this.captureFns && !list.includes(fn)) this.captureFns.delete(fn);
  }
  // Pointer capture is only recorded, so a check can see which pointer an element took.
  setPointerCapture(id) { (this.pointerCaptures = this.pointerCaptures || []).push(id); this.capturedPointer = id; }
  releasePointerCapture(id) { if (this.capturedPointer === id) this.capturedPointer = null; }
  // Runs the listeners the way a browser does: capture listeners from the document down to the target, then the
  // target's own, then bubbling listeners up through each ancestor. stopPropagation ends the walk after the current
  // node, stopImmediatePropagation ends it at once, and preventDefault sets defaultPrevented.
  dispatch(type, extra = {}) {
    const path = [];
    for (let n = this; n; n = n.parentNode) path.push(n);
    let stopped = false;
    let immediate = false;
    const event = Object.assign({
      type, target: this, key: undefined, defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; },
      stopPropagation() { stopped = true; },
      stopImmediatePropagation() { stopped = true; immediate = true; },
    }, extra);
    const run = (node, capture) => {
      for (const fn of [...(node.listeners && node.listeners[type] || [])]) {
        if (immediate) return;
        if (Boolean(node.captureFns && node.captureFns.has(fn)) === capture) fn(event);
      }
    };
    for (let i = path.length - 1; i > 0 && !stopped; i--) run(path[i], true);
    if (!stopped) { run(path[0], true); run(path[0], false); }
    for (let i = 1; i < path.length && !stopped; i++) run(path[i], false);
    return event;
  }
  click() { this.dispatch("click"); }
  closest(sel) {
    for (let n = this; n && n.tagName; n = n.parentNode) if (n.tagName.toLowerCase() === sel) return n;
    return null;
  }
  find(pred, out = []) {
    if (pred(this)) out.push(this);
    this.childNodes.forEach((c) => c.find && c.find(pred, out));
    return out;
  }
  // Only the one selector the app uses: the checked radio.
  querySelector(sel) {
    if (!/\[role="radio"\]\[aria-checked="true"\]/.test(sel)) throw new Error("unsupported selector " + sel);
    return this.find((n) => n.getAttribute("role") === "radio" && n.getAttribute("aria-checked") === "true")[0] || null;
  }
  // A disabled control takes no focus, as in a browser.
  focus() {
    if (this.attrs.has("disabled")) return;
    FElement.focused = this;
    this.focusCalls = (this.focusCalls || 0) + 1;
  }
}
FElement.focused = null;

// A Storage with the four calls the dashboard uses. items is the Map behind it.
function makeStore() {
  const items = new Map();
  return {
    getItem: (k) => (items.has(k) ? items.get(k) : null),
    setItem: (k, v) => { items.set(k, String(v)); },
    removeItem: (k) => { items.delete(k); },
    items,
  };
}

// A fresh page for one scenario. Sets the globals the modules read: document, window and Node.
export function createPage({ narrow = true } = {}) {
  FElement.focused = null;
  const listeners = {};
  const media = { matches: narrow, listeners: [], addEventListener(_t, fn) { this.listeners.push(fn); } };
  const win = {
    location: {
      _hash: "",
      get hash() { return this._hash; },
      set hash(v) {
        const next = v.startsWith("#") ? v : "#" + v;
        if (next === this._hash) return;
        this._hash = next;
        (listeners.hashchange || []).forEach((fn) => fn({}));
      },
    },
    history: { replaceState(_a, _b, url) { win.location._hash = url; } },
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    removeEventListener(type, fn) {
      const list = listeners[type] || [];
      if (list.includes(fn)) list.splice(list.indexOf(fn), 1);
    },
    // A sessionStorage for the edit token and a localStorage for the band order. A check can replace either, or make the
    // property throw, as a blocked one does.
    sessionStorage: makeStore(),
    localStorage: makeStore(),
    matchMedia: () => media,
    scrollTo() {},
  };
  const doc = new FElement("#document");
  doc.createElement = (t) => new FElement(t);
  doc.createElementNS = (ns, t) => new FElement(t, ns);
  doc.createTextNode = (d) => new FText(d);
  doc.createDocumentFragment = () => new FFragment();
  doc.documentElement = new FElement("html");
  doc.body = doc.documentElement;
  doc.title = "";
  Object.defineProperty(doc, "activeElement", { get() { return FElement.focused || doc.documentElement; } });
  win.document = doc;
  globalThis.Node = FNode;
  globalThis.document = doc;
  globalThis.window = win;

  const el = (tag, attrs = {}) => {
    const e = new FElement(tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    return e;
  };
  // The same tree as index.html: .app holds the sidebar and .main, and .main holds the top bar and the content.
  const sidebar = el("aside", { id: "sidebar", class: "sb" });
  const topbar = el("header", { id: "topbar", class: "topbar" });
  const content = el("main", { class: "content" });
  const wrap = el("div", { class: "main" });
  const app = el("div", { class: "app" });
  wrap.appendChild(topbar);
  wrap.appendChild(content);
  app.appendChild(sidebar);
  app.appendChild(wrap);
  doc.appendChild(app);
  const pages = ["live", "overview", "all-projects", "agents", "agent-detail", "models", "sessions", "session-detail",
    "settings", "trail", "attention", "files", "rules"];
  const sections = {};
  for (const name of pages) {
    sections[name] = el("section", { "data-page": name, hidden: "" });
    content.appendChild(sections[name]);
  }
  doc.getElementById = (id) => ({ sidebar, topbar }[id] || null);
  doc.querySelectorAll = (sel) => (sel === "main [data-page]" ? Object.values(sections) : []);
  return { win, doc, sidebar, topbar, content, wrap, app, sections, media, listeners };
}
