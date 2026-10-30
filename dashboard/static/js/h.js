// A tiny DOM builder. Text goes in with createTextNode and styles through el.style,
// so a value from the server is never parsed as markup and never needs a style attribute.
// The page's Content-Security-Policy allows exactly this: no inline script, no inline style.

const SVG_NS = "http://www.w3.org/2000/svg";
const URL_ATTRS = new Set(["href", "src", "action", "formaction", "xlink:href"]);
// A link value is allowed only when it starts with "#" or with a single "/" (not "//" and not "/\\", which
// browsers read as a host). Any other value is refused and the attribute is dropped, so the element is
// built without it.
const SAFE_URL = /^(?:#|\/(?![\/\\]))/;

function classText(value) {
  if (Array.isArray(value)) return value.filter(Boolean).join(" ");
  return String(value);
}

function applyStyle(el, style) {
  for (const [name, value] of Object.entries(style)) {
    if (value === null || value === undefined || value === false) continue;
    if (name.startsWith("--")) el.style.setProperty(name, String(value));
    else el.style[name] = String(value);
  }
}

function applyAttrs(el, attrs) {
  if (!attrs) return;
  for (const [name, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (name === "class" || name === "className") {
      const text = classText(value);
      if (text) el.setAttribute("class", text);
    } else if (name === "style") {
      if (typeof value !== "object") throw new TypeError("style must be an object");
      applyStyle(el, value);
    } else if (name === "on") {
      for (const [type, handler] of Object.entries(value)) el.addEventListener(type, handler);
    } else if (/^on/i.test(name)) {
      throw new TypeError("use { on: { click: fn } } instead of " + name);
    } else if (name === "value") {
      el.value = value;
    } else if (URL_ATTRS.has(name) && !SAFE_URL.test(String(value))) {
      continue;
    } else {
      el.setAttribute(name, value === true ? "" : String(value));
    }
  }
}

function appendAll(el, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false || child === true) continue;
    if (Array.isArray(child)) appendAll(el, child);
    else if (child instanceof Node) el.appendChild(child);
    else el.appendChild(document.createTextNode(String(child)));
  }
}

// h("div", { class: "kpi" }, "text", childNode). Attribute values that are null, undefined
// or false are skipped, and true sets an empty attribute.
export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  applyAttrs(el, attrs);
  appendAll(el, children);
  return el;
}

// The same for SVG elements, which need their own namespace.
export function s(tag, attrs, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  applyAttrs(el, attrs);
  appendAll(el, children);
  return el;
}

export function frag(...children) {
  const node = document.createDocumentFragment();
  appendAll(node, children);
  return node;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}
