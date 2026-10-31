// A tiny DOM builder. Text goes in with createTextNode and styles through el.style,
// so a value from the server is never parsed as markup and never needs a style attribute.
// The page's Content-Security-Policy allows exactly this: no inline script, no inline style.

const SVG_NS = "http://www.w3.org/2000/svg";
// The set is lower case, and an attribute name is compared in lower case, so HREF and Href count as href.
const URL_ATTRS = new Set(["href", "src", "action", "formaction", "xlink:href"]);
// A link value is allowed only when it starts with "#" or with a single "/" (not "//" and not "/\\", which
// browsers read as a host) and holds no control character. A URL parser strips tab and newline before it
// reads the value, so "/\t/host" would turn into "//host". Any other value is refused and the attribute is
// dropped, so the element is built without it.
const SAFE_URL = /^(?:#|\/(?![\/\\]))[^\x00-\x1f\x7f]*$/;
// The one way to a page outside the dashboard, used only by externalLink. https only, with a plain host and
// an optional port. No credentials before the host, no whitespace, control character or backslash anywhere.
const EXTERNAL_URL = /^https:\/\/[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?(?::[0-9]+)?(?:[\/?#][^\s\\\x00-\x1f\x7f]*)?$/;

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
    } else if (URL_ATTRS.has(String(name).toLowerCase()) && !SAFE_URL.test(String(value))) {
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

// An <a> to a page outside the dashboard, opened in a new tab with no opener or referrer. A value that fails
// EXTERNAL_URL gives the same element with no href, so the label still shows as text.
export function externalLink(attrs, url, label) {
  const link = h("a", attrs, label);
  if (typeof url !== "string" || !EXTERNAL_URL.test(url)) return link;
  link.setAttribute("href", url);
  link.setAttribute("target", "_blank");
  link.setAttribute("rel", "noopener noreferrer");
  return link;
}

// Change the href of an element that already exists. The value passes SAFE_URL, as in h(), or the href goes.
export function setLocalHref(el, value) {
  if (SAFE_URL.test(String(value))) el.setAttribute("href", String(value));
  else el.removeAttribute("href");
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
