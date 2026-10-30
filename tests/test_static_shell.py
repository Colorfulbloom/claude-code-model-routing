"""Checks for the dashboard shell in dashboard/static: index.html, app.css and the js modules.

Static checks read repo files only. One class starts the server with --fixture (never without it, and
never on the real ~/.claude) and asks it for every file under static/, to check the type and the
Content-Security-Policy header.
"""
import html.parser
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
                  r"new\s+Function\s*\(", r"setAttribute\(\s*[\"']style[\"']", r"createContextualFragment", r"\.srcdoc")
        for path in sorted(JS_DIR.rglob("*.js")):
            text = strip_js_comments(path.read_text(encoding="utf-8"))
            for pattern in banned:
                self.assertNotRegex(text, pattern, "%s: %s" % (path.name, pattern))

    def test_link_values_use_an_allow_list(self):
        # h.js drops a href, src or action unless it starts with "#" or a single "/".
        text = strip_js_comments((JS_DIR / "h.js").read_text(encoding="utf-8"))
        self.assertIn("SAFE_URL", text)
        self.assertNotIn("UNSAFE_URL", text)
        self.assertRegex(text, r"URL_ATTRS\.has\(name\) && !SAFE_URL\.test\(")

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
