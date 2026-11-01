"""Checks for the dashboard shell in dashboard/static: index.html, app.css and the js modules.

Static checks read repo files only. One class starts the server with --fixture (never without it, and
never on the real ~/.claude) and asks it for every file under static/, to check the type and the
Content-Security-Policy header.
"""
import html.parser
import json
import os
import re
import unittest
from pathlib import Path

import helpers
from test_server import CSP, make_root, start, write_json  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
STATIC = REPO / "dashboard" / "static"
JS_DIR = STATIC / "js"

PAGES = ("overview", "agents", "agent-detail", "models", "sessions", "session-detail",
         "settings", "trail", "attention", "files", "rules", "all-projects")
CORE = ("h", "format", "charts", "components", "icons", "shell", "api", "router", "app")

# A hard-coded color in app.css needs a named allowance with its reason. The approved screens had
# hex colors only in their proposed-token blocks, and tokens.css holds those values now.
COLOR_ALLOWANCES = {
    # "rule": "reason",
}
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json"}


# ---------------------------------------------------------------- helpers

def strip_css_comments(text):
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def strip_js_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(?m)^\s*//.*$", "", text)
    return re.sub(r"(?m)\s//\s.*$", "", text)


EXTERNAL_LITERAL = re.compile(r"const EXTERNAL_URL = /(.*)/;")
# Ways to put a URL into the page without h(), externalLink or setLocalHref, or to name a scheme in code.
LINK_BYPASS_OUTSIDE_H = (
    r"\.setAttribute\(\s*[\"'](?:href|src|action|formaction|xlink:href)[\"']",  # a link attribute by name
    r"\.setAttribute\(\s*[^\"'\s]",  # a name worked out at run time, or a template string
    r"\.setAttribute\(\s*[\"'][^\"']*[\"']\s*\+",  # a name built by joining strings
    r"(?i)\.setAttributeNS\(",
    r"(?i)\[\s*[\"'`]setAttribute",
)
# An assignment operator, not a comparison (== and ===) and not an arrow (=>).
ASSIGNMENT = r"(?:[-+*/%&|^]|\*\*|<<|>>>?|&&|\|\||\?\?)?=(?![=>])"
LINK_BYPASS_EVERYWHERE = (
    r"\.(?:href|src|action|formAction)\s*=(?!=)",
    r"\[\s*[\"'`](?:href|src|action|formAction)[\"'`]\s*\]\s*=(?!=)",
    r"(?i)\bhttps?\b",  # any scheme, whichever way its slashes are written
    r"(?i)\\x2f|\\u002f|\\u\{0*2f\}",  # an escaped slash spelled as a code
    # Ways to move the page or open another one without a link value.
    r"\blocation\s*\.\s*(?:assign|replace)\s*\(",  # location.assign( and location.replace(, with or without window.
    r"\blocation\s*\[\s*[\"'`](?:assign|replace)[\"'`]\s*\]",  # location["assign"]
    r"\b(?:window|globalThis|self)\s*\.\s*open\s*\(",
    r"(?<![\w$.])open\s*\(",  # a bare open(, not a method and not part of a longer name such as setOpen(
    r"\[\s*[\"'`]open[\"'`]\s*\]\s*\(",
    r"\blocation\s*" + ASSIGNMENT,  # location = x and window.location = x
    r"\blocation\s*\.\s*(?!hash\b)\w+\s*" + ASSIGNMENT,  # location.href = x, any property but hash
    r"\blocation\s*\[[^\]]*\]\s*" + ASSIGNMENT,
    r"\bObject\s*\.\s*assign\s*\((?!\s*\{)",  # Object.assign( on anything but an object literal
    r"\bObject\s*\[\s*[\"'`]assign[\"'`]\s*\]",
    r"\bReflect\s*\.\s*set\s*\(",
    r"\bReflect\s*\[\s*[\"'`]set[\"'`]\s*\]",
)


def link_bypasses(text, name):
    """Return the patterns text breaks. In h.js the one EXTERNAL_URL literal and its helpers are exempt."""
    if name == "h.js":
        text = EXTERNAL_LITERAL.sub("", text, count=1)
    patterns = LINK_BYPASS_EVERYWHERE if name == "h.js" else LINK_BYPASS_EVERYWHERE + LINK_BYPASS_OUTSIDE_H
    return [pattern for pattern in patterns if re.search(pattern, text)]


def js_function(text, name):
    """Return the body of a top-level `export function name`, up to its closing brace at column 0."""
    start = text.index("export function %s(" % name)
    return text[start:text.index("\n}\n", start)]


def split_top(text, sep):
    """Split on sep outside brackets and quotes (a data: URL holds a semicolon)."""
    out, depth, quote, cur = [], 0, None, []
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            cur.append(ch)
            continue
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == sep and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def parse_css(text, media=""):
    """Return [(media, selector, {property: value})] in source order, one entry per selector."""
    text = strip_css_comments(text)
    out, i = [], 0
    while True:
        j = text.find("{", i)
        if j < 0:
            return out
        head = text[i:j].strip()
        depth, k, quote = 1, j + 1, None
        while k < len(text) and depth:
            ch = text[k]
            if quote:
                quote = None if ch == quote else quote
            elif ch in "\"'":
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            k += 1
        body = text[j + 1:k - 1]
        if head.startswith("@media"):
            out += parse_css(body, " ".join(head[6:].split()))
        else:
            decls = {}
            for decl in split_top(body, ";"):
                if ":" in decl:
                    name, value = decl.split(":", 1)
                    decls[name.strip()] = " ".join(value.split())
            for selector in split_top(head, ","):
                out.append((media, " ".join(selector.split()), decls))
        i = k


def final_value(rules, selector, prop, media=""):
    """The value the last matching rule gives selector.prop in a media context, or None."""
    value = None
    for m, sel, decls in rules:
        if m == media and sel == selector and prop in decls:
            value = decls[prop]
    return value


class PageParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []  # (tag, {attr: value})

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, {k: (v if v is not None else "") for k, v in attrs}))

    handle_startendtag = handle_starttag


def read_index():
    parser = PageParser()
    parser.feed((STATIC / "index.html").read_text(encoding="utf-8"))
    return parser.tags


# ---------------------------------------------------------------- index.html

class IndexHtml(unittest.TestCase):
    def test_no_inline_script_style_or_handlers(self):
        raw = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertNotRegex(raw, r"(?i)<script(?![^>]*\bsrc=)")
        self.assertNotRegex(raw, r"(?i)<style")
        for tag, attrs in read_index():
            self.assertNotIn("style", attrs, tag)
            for name in attrs:
                self.assertFalse(name.lower().startswith("on"), "%s has %s" % (tag, name))

    def test_links_and_scripts_are_local(self):
        loaded = []
        for tag, attrs in read_index():
            if tag == "script":
                self.assertTrue(attrs.get("src"), "script without src")
                loaded.append(attrs["src"])
            if tag == "link":
                loaded.append(attrs.get("href", ""))
        self.assertIn("/static/tokens.css", loaded)
        self.assertIn("/static/app.css", loaded)
        self.assertIn("/static/js/app.js", loaded)
        self.assertLess(loaded.index("/static/tokens.css"), loaded.index("/static/app.css"))
        for ref in loaded:
            self.assertTrue(ref.startswith("/static/"), ref)
            self.assertNotRegex(ref, r"^(?:[a-z]+:)?//")
        module = [a for t, a in read_index() if t == "script"]
        self.assertEqual([a.get("type") for a in module], ["module"])

    def test_one_section_per_page(self):
        sections = [a for t, a in read_index() if t == "section" and "data-page" in a]
        names = [a["data-page"] for a in sections]
        self.assertEqual(sorted(names), sorted(PAGES))
        self.assertEqual(len(names), len(set(names)))
        ids = [a.get("id") for t, a in read_index() if a.get("id")]
        self.assertEqual(len(ids), len(set(ids)))

    def test_shell_hooks_exist(self):
        ids = {a.get("id") for _t, a in read_index()}
        self.assertTrue({"sidebar", "topbar"} <= ids)

    def test_page_text_is_not_in_the_markup(self):
        # Copy comes from strings.json at run time, so the file holds no text between tags.
        raw = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertEqual(re.search(r"<title>(.*?)</title>", raw).group(1), "")
        self.assertEqual(re.sub(r"<[^>]+>", "", raw).split(), [])
        self.assertNotRegex(raw, r"(?i)\b(?:aria-label|alt|placeholder|title)=\"[^\"]")


# ---------------------------------------------------------------- js

class JsModules(unittest.TestCase):
    def test_modules_exist(self):
        for name in CORE:
            self.assertTrue((JS_DIR / (name + ".js")).is_file(), name)
        for name in PAGES:
            self.assertTrue((JS_DIR / "pages" / (name + ".js")).is_file(), name)

    def test_each_page_module_exports_render(self):
        for name in PAGES:
            text = (JS_DIR / "pages" / (name + ".js")).read_text(encoding="utf-8")
            self.assertRegex(text, r"export function render\(root, ctx\)", name)

    def test_no_html_injection_or_eval(self):
        banned = (r"\.innerHTML", r"\.outerHTML", r"insertAdjacentHTML", r"document\.write", r"\beval\s*\(",
                  r"new\s+Function\s*\(", r"setAttribute\(\s*[\"']style[\"']", r"createContextualFragment", r"srcdoc",
                  r"\bDOMParser\b", r"setHTMLUnsafe")
        for path in sorted(JS_DIR.rglob("*.js")):
            text = strip_js_comments(path.read_text(encoding="utf-8"))
            for pattern in banned:
                self.assertNotRegex(text, pattern, "%s: %s" % (path.name, pattern))

    def test_link_values_use_an_allow_list(self):
        # Run the pattern itself. A URL parser strips tab and newline before it reads a value, so a
        # control character inside the value must fail the pattern. Python's "$" also matches before a
        # final newline, so the literal's trailing "$" becomes "\\Z" here.
        text = strip_js_comments((JS_DIR / "h.js").read_text(encoding="utf-8"))
        found = re.search(r"const SAFE_URL = /(.*)/;", text)
        self.assertIsNotNone(found, "h.js has no SAFE_URL literal")
        source = found.group(1)
        self.assertTrue(source.endswith("$"), source)
        pattern = re.compile(source[:-1] + r"\Z")
        refused = ["/\t/evil.example/x", "/\n/evil.example/x", "/\r\\evil.example/x", "//evil", "/\\evil",
                   "https://x", "javascript:x", " /x", "/x\n", ""]
        allowed = ["#", "#/x", "/", "/api/x"]
        for value in refused:
            self.assertIsNone(pattern.match(value), repr(value))
        for value in allowed:
            self.assertIsNotNone(pattern.match(value), repr(value))
        self.assertNotIn("UNSAFE_URL", text)
        self.assertRegex(text, r"URL_ATTRS\.has\(String\(name\)\.toLowerCase\(\)\) && !SAFE_URL\.test\(")

    def external_url(self):
        # The EXTERNAL_URL literal as a Python pattern, with the same "$" change as above.
        text = strip_js_comments((JS_DIR / "h.js").read_text(encoding="utf-8"))
        found = EXTERNAL_LITERAL.findall(text)
        self.assertEqual(len(found), 1, "h.js needs one EXTERNAL_URL literal")
        self.assertTrue(found[0].endswith("$"), found[0])
        return re.compile(found[0][:-1] + r"\Z")

    def test_the_external_link_pattern_refuses_hostile_values(self):
        pattern = self.external_url()
        refused = [
            "", "x", "#/x", "/api/x", " https://a.example/", "https://", "https:/a.example", "https:a.example",
            "HTTPS://a.example/",
            "http://a.example/", "ftp://a.example/", "file:///etc/passwd", "data:text/html,x",
            "javascript:alert(1)", "JaVaScRiPt:alert(1)", "java\tscript:alert(1)", "https://a.example/javascript:x y",
            "//a.example/x", "/\\a.example/x", "\\\\a.example\\x",
            "https://user@a.example/", "https://user:pw@a.example/", "https://a.example@b.example/",
            "https://a.example:pw@b.example/", "https://a.example\\@b.example/", "https://@a.example/",
            "https://a.example\\x", "https://a.example/\\x", "https://-a.example/", "https://a.example:port/",
            "https://a.example/\tx", "https://a.\texample/", "https://a.example/\nx", "https://a.example/\rx",
            "https://a.example/x\n", "https://a.example/\x00", "https://a.example/\x1f", "https://a.example/\x7f",
            "https://a.example/ x", "https://a.example/ x",
        ]
        allowed = [
            "https://code.claude.com/docs/en/settings-reference#maxeffortlevel",
            "https://github.com/Colorfulbloom/claude-code-model-routing/blob/main/docs/rules-reference.md#a-rule",
            "https://a.example", "https://a.example:8443/x?y=z#w", "https://a.example/@x",
        ]
        for value in refused:
            self.assertIsNone(pattern.match(value), repr(value))
        for value in allowed:
            self.assertIsNotNone(pattern.match(value), repr(value))

    def test_every_link_the_server_sends_passes_the_external_pattern(self):
        pattern = self.external_url()
        rules = json.loads((REPO / "dashboard" / "rules.json").read_text(encoding="utf-8"))
        urls = {quote["doc_url"] for item in rules["rules"] + rules["models"] for quote in item.get("quotes", [])}
        api = (REPO / "dashboard" / "api_settings.py").read_text(encoding="utf-8")
        urls.update(re.findall(r"REPO_BLOB = \"([^\"]+)\"", api))
        self.assertGreater(len(urls), 10)
        for url in sorted(urls):
            self.assertIsNotNone(pattern.match(url), url)

    def test_link_paths_go_through_the_two_helpers_in_h_js(self):
        text = strip_js_comments((JS_DIR / "h.js").read_text(encoding="utf-8"))
        external = js_function(text, "externalLink")
        local = js_function(text, "setLocalHref")
        self.assertRegex(external, r"!EXTERNAL_URL\.test\(url\)\) return link;")
        self.assertRegex(external, r"typeof url !== \"string\"")
        self.assertRegex(local, r"if \(SAFE_URL\.test\(")
        self.assertEqual(external.count('setAttribute("href"'), 1)
        self.assertEqual(local.count('setAttribute("href"'), 1)
        self.assertEqual(text.count('setAttribute("href"'), 2, "h.js sets href only in the two helpers")
        self.assertEqual(text.count("EXTERNAL_URL.test("), 1, "only externalLink runs EXTERNAL_URL")
        self.assertEqual(text.count("EXTERNAL_URL"), 2, "the literal and its one use")

    def test_no_file_gets_around_the_link_helpers(self):
        for path in sorted(JS_DIR.rglob("*.js")):
            text = strip_js_comments(path.read_text(encoding="utf-8")).replace(SVG_NAMESPACE, "")
            self.assertEqual(link_bypasses(text, path.name), [], path.name)

    def test_the_link_check_catches_each_bypass(self):
        # Each of these must fail the check above, in any file that is not h.js.
        bypasses = [
            'link.setAttribute("href", url);', "link.setAttribute('href', url);", "link.setAttribute(`href`, url);",
            'link.setAttribute( "href", url);', 'link.setAttribute("src", url);', 'link.setAttribute("xlink:href", url);',
            'link.setAttribute("hr" + "ef", url);', "link.setAttribute(name, url);",
            'link.setAttributeNS(null, "href", url);', 'link["setAttribute"]("href", url);',
            "link.href = url;", 'link["href"] = url;', "const u = /^https:\\/\\/x/;", "const u = /^https:\\x2f\\x2f/;",
            'const u = "https:\\u002f\\u002fx";', 'const u = "https:" + "//x";', 'const u = "HTTP" + ":";',
            'const u = "a\\/\\x2f";',
            "location.assign(url);", "window.location.assign(url);", "location.replace(url);",
            "window.location.replace(url);", 'location["assign"](url);', 'window.location["replace"](url);',
            "window.open(url);", "globalThis.open(url);", "self.open(url);", "open(url);", "x = open (url);",
            "location = url;", "window.location = url;", "document.location = url;", "location.href = url;",
            "window.location.pathname = url;", "location.search = url;", "location.href += url;",
            "location.hashX = url;", 'location["href"] = url;',
            "Object.assign(target, source);", "Object.assign(location, source);", "Object.assign(window.location, x);",
            "Reflect.set(location, 'href', url);",
        ]
        for line in bypasses:
            self.assertNotEqual(link_bypasses(line, "trail.js"), [], line)
        allowed = [
            'link.setAttribute("aria-label", word);', "window.location.hash = x;", "location.hash = x;",
            "if (location.href == x) {}", "if (location.href === x) {}", "if (location === x) {}",
            "if (location.pathname >= x) {}", "const here = location.pathname;", "setOpen(true);", "isOpen(x);",
            "el.open(x);", "this.open(x);", "reopen(x);", "Object.assign({}, a, b);", "Object.assign( { a: 1 }, b);",
            "const f = (location) => location.hash;", "const open = true;",
        ]
        for line in allowed:
            self.assertEqual(link_bypasses(line, "trail.js"), [], line)
        self.assertEqual(link_bypasses("\n".join(allowed), "trail.js"), [])

    def test_references_stay_local(self):
        for path in sorted(JS_DIR.rglob("*.js")):
            text = strip_js_comments(path.read_text(encoding="utf-8")).replace(SVG_NAMESPACE, "")
            self.assertNotRegex(text, r"https?://", path.name)
            self.assertNotRegex(text, r"[\"']//[A-Za-z]", path.name)
            for spec in re.findall(r"(?:import|from)\s+[\"']([^\"']+)[\"']", text):
                self.assertRegex(spec, r"^\.{1,2}/", "%s imports %s" % (path.name, spec))
                self.assertTrue((path.parent / spec).resolve().is_file(), "%s imports %s" % (path.name, spec))
            for target in re.findall(r"fetch\(\s*[\"']([^\"']+)[\"']", text):
                self.assertTrue(target.startswith("/"), target)

    def test_app_loads_every_page_module(self):
        # app.js loads every page module, so a ticket only fills its own file.
        text = (JS_DIR / "app.js").read_text(encoding="utf-8")
        for name in PAGES:
            self.assertIn("./pages/%s.js" % name, text)

    def test_stacked_bar_class_comes_from_one_place(self):
        found = [p.name for p in sorted(JS_DIR.rglob("*.js")) if "sb-bar" in strip_js_comments(p.read_text(encoding="utf-8"))]
        self.assertEqual(found, ["charts.js"])

    def test_cost_icon_is_not_the_cache_icon(self):
        text = (JS_DIR / "icons.js").read_text(encoding="utf-8")
        coins = re.search(r"(?m)^  coins: (.*),$", text)
        cache = re.search(r"(?m)^  cache: (.*),$", text)
        self.assertTrue(coins and cache)
        self.assertNotEqual(coins.group(1), cache.group(1))


# ---------------------------------------------------------------- app.css

class AppCss(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (STATIC / "app.css").read_text(encoding="utf-8")
        cls.clean = strip_css_comments(cls.text)
        cls.rules = parse_css(cls.text)

    def test_braces_balance(self):
        self.assertEqual(self.clean.count("{"), self.clean.count("}"))

    def test_no_color_literals(self):
        # Everything goes through tokens.css. The data: URL in the search field names "black" and
        # "none" as SVG paint, which are keywords, not theme colors.
        hits = re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", self.clean)
        left = [h for h in hits if h not in COLOR_ALLOWANCES]
        self.assertEqual(left, [])

    def test_no_prototype_only_rules(self):
        self.assertNotRegex(self.clean, r"(?<![\w-])\.(?:board|bd|bd-l|st-match-note)(?![\w-])")

    def test_urls_stay_local(self):
        for target in re.findall(r"url\(\s*([^)]*)\)", self.clean):
            value = target.strip().strip("'\"")
            if value.startswith(("data:", "#", "/static/")):
                continue
            self.assertNotRegex(value, r"^(?://|[A-Za-z][A-Za-z0-9+.-]*:)", value)
        self.assertNotIn("@import", self.clean)

    def test_proposed_token_blocks_are_not_repeated(self):
        for _media, selector, decls in self.rules:
            if selector.startswith(":root"):
                self.fail("app.css redefines tokens under %s" % selector)

    def test_stacked_bars_keep_the_start_edge(self):
        bar = [(m, d) for m, sel, d in self.rules if sel == ".sb-bar"]
        self.assertTrue(bar)
        self.assertEqual(final_value(self.rules, ".sb-bar", "border-left"), "var(--border-width) solid var(--border-strong)")
        for media, decls in bar:
            for prop in decls:
                if prop.startswith("border"):
                    self.assertEqual((media, prop), ("", "border-left"))
        for _m, sel, decls in self.rules:
            if ".sb-bar" in sel and sel != ".sb-bar":
                self.assertFalse([p for p in decls if p.startswith("border")], sel)

    def test_one_section_per_page_with_shared_first(self):
        titles = re.findall(r"(?m)^ \* ([A-Z][\w ,]+)$", self.text)
        self.assertEqual(titles, ["Shared", "Overview", "Agents", "Agent detail", "Models", "Sessions", "Session detail",
                                  "Settings and trail", "Needs attention", "Installed files", "Rules reference", "All projects"])

    def test_settings_page_layout_stays_inside_its_scope(self):
        # The white flat page, the locked panes and the Stat band belong to the Settings route alone. Every rule of the
        # block starts from an s4-, s5- or s6- class, except the two that frame the route, and those name the Settings
        # section. Nothing in it styles a shared class, a tag, or another page on its own.
        start = self.text.index("/* Settings page, round 6")
        end = self.text.index(" * Needs attention")
        block = parse_css(self.text[start:end])
        self.assertGreater(len(block), 60)
        framing = {".content:has(>[data-page=\"settings\"]:not([hidden]))",
                   ".main:has(>.content>[data-page=\"settings\"]:not([hidden]))>.topbar"}
        for media, selector, _decls in block:
            if selector in framing:
                continue
            # The leftmost class is the page's own, so a shared class such as .st or .btn is only reached inside it.
            self.assertRegex(selector, r"^(?:\.s[456]-[a-z]|\.s4(?![\w-]))", "outside the Settings scope: " + selector)
        self.assertEqual({s for _m, s, _d in block if s in framing}, framing)
        for media, selector, decls in block:
            if selector == ".main:has(>.content>[data-page=\"settings\"]:not([hidden]))>.topbar":
                self.assertEqual(media, "(max-width: 720px)")

    def test_the_rail_foot_docks_by_itself_at_1240_and_the_page_holds_no_second_dock(self):
        # One DOM, no copies: a second Save or a second radio set would be a safety risk. At 1240 and under the rail
        # stacks under the body and its own foot is fixed to the window's bottom. At 1241 and up it stays the rail's foot.
        r = self.rules
        narrow = "(max-width: 1240px)"
        for prop, want in (("position", "fixed"), ("display", "grid"), ("bottom", "0"), ("left", "0"), ("right", "0")):
            self.assertEqual(final_value(r, ".s4-rf", prop, narrow), want, ".s4-rf " + prop)
        self.assertEqual(final_value(r, ".s4-rf", "grid-template-columns", narrow), "minmax(0,1fr) auto")
        self.assertEqual(final_value(r, ".s4-rf .s4-hint", "grid-column", narrow), "1/-1")
        self.assertEqual(final_value(r, ".s4-rf .s4-wide", "width", narrow), "auto")
        self.assertIsNone(final_value(r, ".s4-rf", "position"), "the foot sits in the rail's flow above 1240")
        self.assertNotEqual(final_value(r, ".s4-rf", "display", narrow), "none", "the narrow foot is not hidden")
        self.assertIsNone(final_value(r, ".s4-rf", "padding", "(max-width: 720px)"), "a phone keeps the dock's padding")
        # The rail takes the bottom padding while the foot holds something, so the dock never covers the last line.
        padded = [sel for m, sel, d in r if m == narrow and "padding-bottom" in d and sel.startswith(".s4-rail")]
        self.assertEqual(padded, [".s4-rail:has(.s4-rf:has(:not(.s4-slot)))"])
        # An empty foot takes no room at any width.
        self.assertEqual(final_value(r, ".s4-rf:not(:has(:not(.s4-slot)))", "display"), "none")
        self.assertNotRegex(self.clean, r"\.s5-dock|\.s4-inl|\.s5-pad")

    def test_old_tiles_are_gone_and_the_kpi_label_stays(self):
        self.assertNotRegex(self.clean, r"(?<![\w-])\.(?:tiles|tl|tl-top|tl-mid|tl-v|tl-src)(?![\w-])")
        self.assertIsNotNone(final_value(self.rules, ".tl-l", "font-size"))

    def test_notes_fixes_are_in(self):
        r = self.rules
        narrow = "(max-width: 720px)"
        self.assertEqual(final_value(r, ".rseg.mini-arc", "transform-origin"), "32px 32px")                  # mini ring full arc
        self.assertEqual(final_value(r, ".ring-n", "font-size"), "14px")                                    # cost ring centre number
        self.assertEqual(final_value(r, ".dbars .pt-bg", "fill"), "var(--chart-track)")                      # day columns hatch
        self.assertEqual(final_value(r, ".dbars .pt-fg", "fill"), "var(--text-muted)")
        for _m, sel, decls in r:                                                                            # no CSS paint on cat-other marks
            if "cat-other" in sel:
                self.assertFalse({"fill", "stroke"} & set(decls), sel)
        self.assertEqual(final_value(r, ".g2", "align-items"), "start")                                     # grid rows do not stretch
        self.assertEqual(final_value(r, ".g21", "align-items"), "start")
        self.assertEqual(final_value(r, ".g21 .ring-row", "flex-wrap"), "nowrap")                           # legend beside the ring
        self.assertEqual(final_value(r, ".g21-pin", "align-items"), "stretch")                              # pin card matches tiles
        self.assertEqual(final_value(r, ".st-match .mk::before", "content"), '"\\2713"')                    # Matches pin check mark
        self.assertEqual(final_value(r, ".at-n", "overflow-wrap"), "anywhere")                                # raw keys wrap at 375
        self.assertEqual(final_value(r, ".cw", "white-space"), "nowrap")                                    # count and words together
        self.assertEqual(final_value(r, ".dt td>.cw", "text-align", narrow), "right")
        self.assertEqual(final_value(r, ".nw", "white-space"), "nowrap")                                    # flags do not break
        self.assertEqual(final_value(r, ".vc-short", "display"), "none")                                    # header wraps at 375
        self.assertEqual(final_value(r, ".vc-long", "display", narrow), "none")
        self.assertEqual(final_value(r, ".vc-short", "display", narrow), "inline")
        self.assertEqual(final_value(r, ".topbar", "flex-wrap", narrow), "wrap")
        self.assertEqual(final_value(r, ".seg.is-active", "box-shadow"), "var(--shadow-card)")              # active segment
        self.assertEqual(final_value(r, ".g21 .kpis", "grid-template-columns", narrow), "repeat(2,minmax(0,1fr))")  # 2x2 KPIs
        self.assertEqual(final_value(r, ".kpis", "grid-template-columns", narrow), "repeat(2,minmax(0,1fr))")
        self.assertEqual(final_value(r, ".lg th", "padding"), "6px 0")                                      # legend row borders
        self.assertEqual(final_value(r, ".lg td", "border-bottom"), "var(--border-width) solid var(--border)")
        self.assertEqual(final_value(r, ".lg th", "border-bottom"), "var(--border-width) solid var(--border)")

    def test_dark_ramp_flip_is_in_the_token_sheet(self):
        tokens = (STATIC / "tokens.css").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"--rk-1: #256abf; --rk-2: #3987e5; --rk-3: #86b6ef; --rk-4: #cde2fb;", tokens)), 2)
        self.assertIn("--rk-1: #b7d3f6;", tokens)

    def test_mobile_menu_has_an_open_state(self):
        self.assertEqual(final_value(self.rules, ".sb", "display", "(max-width: 720px)"), "none")
        self.assertEqual(final_value(self.rules, ".sb.is-open", "display", "(max-width: 720px)"), "block")
        self.assertEqual(final_value(self.rules, ".content>[data-page]:not([hidden])", "display"), "contents")


# ---------------------------------------------------------------- served by the server

class ServedFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = make_root("mr-shell-")
        folder = os.path.join(cls.root, "fixture")
        write_json(os.path.join(folder, "config", "routing-dashboard.json"), {"projects": []})
        os.makedirs(os.path.join(folder, "project"), exist_ok=True)
        cls.srv = start(cls.root, ["--fixture", folder])

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()
        helpers.rmtree_force(cls.root)

    def test_every_static_file_is_served_with_its_type_and_csp(self):
        files = sorted(p for p in STATIC.rglob("*") if p.is_file())
        self.assertGreater(len(files), 20)
        for path in files:
            rel = path.relative_to(STATIC).as_posix()
            status, heads, body = self.srv.request("GET", "/static/" + rel)
            self.assertEqual(status, 200, rel)
            self.assertTrue(heads["content-type"].startswith(TYPES[path.suffix]), (rel, heads["content-type"]))
            self.assertEqual(heads["content-security-policy"], CSP, rel)
            self.assertEqual(heads["x-content-type-options"], "nosniff", rel)
            self.assertEqual(body, path.read_bytes(), rel)

    def test_root_serves_the_shell(self):
        status, heads, body = self.srv.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertTrue(heads["content-type"].startswith("text/html"))
        self.assertEqual(heads["content-security-policy"], CSP)
        self.assertEqual(body, (STATIC / "index.html").read_bytes())

    def test_modules_are_javascript(self):
        for rel in ("js/app.js", "js/pages/overview.js"):
            _status, heads, _body = self.srv.request("GET", "/static/" + rel)
            self.assertTrue(heads["content-type"].startswith("text/javascript"), rel)


if __name__ == "__main__":
    unittest.main()
