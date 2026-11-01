"""End-to-end sweep of every dashboard page in headless Chrome, at 1440 and 375, light and dark. Opt in with MR_E2E=1.

Built on test_shell_e2e (its Chrome, Page and WebSocket classes). The server runs with --fixture on the
made-up demo set, so nothing reads the real ~/.claude. The text checks come from tests/e2e_checks/<page>.json,
one file per page. Screenshots land in <MR_TEST_TMP>/e2e-pages for the Judge to compare with
docs/design/usage-stack/.

The module-level helpers are pure, and importing this module starts nothing, so tests/test_e2e_checks.py
can test them with no browser.
"""
import base64
import glob
import json
import os
import re
import sys
import tempfile
import time
import unittest
import urllib.parse

import helpers
import test_server as ts
import test_shell_e2e as shell

sys.path.insert(0, os.path.join(helpers.FIXTURES, "demo"))
import build_demo  # noqa: E402

CHECKS_DIR = os.path.join(helpers.REPO, "tests", "e2e_checks")
WIDTHS = (1440, 375)
FULL_PAGE_WIDTH = 375  # the sweep also saves a full-page screenshot at this width, for review
THEMES = ("light", "dark")
TIDEWATER = "Tidewater reporting"
SESSION_TOKEN = "{session}"
LOG_LINE = re.compile(r"^(\S+) (['\"])(/.*)\2 (\S+)$")

# Every status cell and pill needs its mark glyph and its word (components.js chip and pinPill, app.css .st).
# The Read pill on Files read is a file state, not one of the seven statuses, and app.css hides its mark (.st-read .mk), so it is left out.
STATUS_BAD = """(() => {
  const bad = [];
  document.querySelectorAll('main .st:not(.st-read)').forEach((el) => {
    const word = (el.textContent || '').trim();
    const label = '"' + word + '" in ' + el.className;
    const mk = el.querySelector(':scope > .mk');
    if (!mk) { bad.push('no mark: ' + label); return; }
    const content = getComputedStyle(mk, '::before').content;
    if (!content || content === 'none' || content === 'normal' || content === '""' || content === "''") bad.push('no mark: ' + label);
    if (!word) bad.push('no word: ' + label);
  });
  return bad;
})()"""

# Every stacked bar keeps its legend or table in its card, and every bar keeps its start edge (charts.js, app.css .sb-bar).
STACK_BAD = """(() => {
  const bad = [];
  document.querySelectorAll('main .sbars').forEach((el) => {
    const card = el.closest('.cd');
    if (!card || !(card.querySelector('.klg') || card.querySelector('table'))) bad.push('no legend totals or kinds table');
  });
  document.querySelectorAll('main .sb-bar').forEach((el) => {
    const style = getComputedStyle(el);
    if (parseFloat(style.borderLeftWidth) === 0 || style.borderLeftStyle === 'none') bad.push('no start edge');
  });
  return bad;
})()"""

# The narrow layout clips a table's head and draws the column name before every value, as ::before content from
# data-l (app.css .dt td::before). innerText keeps the clipped head and leaves the drawn names out, so a text check
# can't see them. This reads the computed style, so a stacked value with no name on screen fails. Blink resolves
# attr() in the computed value, and a browser that doesn't gets the attribute.
LABEL_BAD = """(() => {
  const drawnLabel = (td) => {
    const content = getComputedStyle(td, '::before').content;
    if (!content || content === 'none' || content === 'normal') return '';
    if (content.startsWith('attr(')) return (td.getAttribute('data-l') || '').trim();
    return content.replace(/^["']|["']$/g, '').trim();
  };
  const bad = [];
  document.querySelectorAll('main [data-page=%s] .dt td').forEach((td) => {
    if (getComputedStyle(td).display === 'table-cell') return;
    if (!drawnLabel(td)) bad.push('no column name beside ' + JSON.stringify(td.innerText.trim()));
  });
  return bad;
})()"""

# The clipped head of the first table on Models: its height, and what it adds to the table (0 when it adds nothing).
HEAD_HEIGHTS = """(() => {
  const table = document.querySelector('main [data-page=models] .dt');
  const height = (el) => el.getBoundingClientRect().height;
  return [height(table.querySelector('thead')), height(table) - height(table.querySelector('tbody'))];
})()"""

DATA_RENDERED = "document.documentElement.getAttribute('data-rendered')"
DATA_USAGE = "document.documentElement.getAttribute('data-usage')"


# ---------------------------------------------------------------- pure helpers

def add_query(hash_, key, value):
    """Add key=value to the query part of a hash route: '?' when it has none, '&' when it has one."""
    pair = "%s=%s" % (urllib.parse.quote(key, safe=""), urllib.parse.quote(value, safe=""))
    return hash_ + ("&" if "?" in hash_ else "?") + pair


def load_checks(directory=CHECKS_DIR):
    """Every checks file as a dict, sorted by file name."""
    out = []
    for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


def routes_of(checks, session_id=""):
    """(page, hash, texts) for every route of every checks file, with {session} replaced."""
    return [(c["page"], r["hash"].replace(SESSION_TOKEN, session_id), r["texts"]) for c in checks for r in c["routes"]]


def non_local_urls(urls, port):
    """The URLs that are not on http://127.0.0.1:<port>, and not data: or about:."""
    bad = []
    for url in urls:
        if url.startswith(("data:", "about:")):
            continue
        parsed = urllib.parse.urlparse(url)
        if not (parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port == port):
            bad.append(url)
    return bad


def same_origin_paths(urls, port):
    """The paths, without query or fragment, of the URLs that are on http://127.0.0.1:<port>."""
    out = set()
    for url in urls:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port == port:
            out.add(parsed.path)
    return out


def log_paths(log_text):
    """The request paths in the server's access log. A line is `METHOD 'path' status` (server.py log_request)."""
    out = []
    for line in log_text.splitlines():
        match = LOG_LINE.match(line.strip())
        if match:
            out.append(match.group(3))
    return out


def screenshot_name(page, hash_, width, theme, suffix=""):
    """<page>-<slug of the hash>-<width>-<theme><suffix>.png"""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", hash_).strip("-") or "root"
    return "%s-%s-%d-%s%s.png" % (page, slug, width, theme, suffix)


def output_dir():
    return os.path.join(helpers._tmp_base() or tempfile.gettempdir(), "e2e-pages")


# ---------------------------------------------------------------- the browser tests

@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the headless Chrome checks")
@unittest.skipIf(shell.CHROME is None, "Chrome was not found (set MR_CHROME to its path)")
class PagesE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out_dir = output_dir()
        os.makedirs(cls.out_dir, exist_ok=True)
        cls.root = ts.make_root("mr-e2e-pages-")
        cls.chrome = None
        cls.srv = None
        try:
            folder = os.path.join(cls.root, "set")
            build_demo.build(folder)
            cls.srv = ts.start(cls.root, ["--fixture", folder])
            cls.base = "http://127.0.0.1:%d/" % cls.srv.port
            cls.session = cls._first_session()
            cls.chrome = shell.Chrome(helpers._tmp_base())
            cls.page = cls.chrome.page
            cls.err_path = cls.chrome.err_path
            cls.page.call("Network.enable")
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _first_session(cls):
        status, _heads, body = cls.srv.request("GET", "/api/projects")
        if status != 200:
            raise AssertionError("/api/projects answered %s" % status)
        listing = json.loads(body)
        keys = [p["key"] for p in listing["projects"] if p["name"] == TIDEWATER]
        if not keys:
            raise AssertionError("the demo set has no project named %s" % TIDEWATER)
        status, _heads, body = cls.srv.request("GET", "/api/usage?project=" + urllib.parse.quote(keys[0], safe=""))
        if status != 200:
            raise AssertionError("/api/usage answered %s" % status)
        sessions = json.loads(body)["views"]["30d"]["sessions"]
        if not sessions:
            raise AssertionError("the demo set has no session for %s" % TIDEWATER)
        return sessions[0]["session_id"]

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "chrome", None):
            cls.chrome.close()
        if getattr(cls, "srv", None):
            cls.srv.stop()
        if getattr(cls, "root", None):
            helpers.rmtree_force(cls.root)

    def wait_rendered(self):
        """Boot is done (data-rendered) and the first /api/usage answer is drawn (data-usage). Either can arrive first, so it waits for both."""
        self.page.wait_for(DATA_RENDERED + " === '1'")
        self.page.wait_for(DATA_USAGE + " === '1'")

    # ------------------------------------------------------------ the sweep

    def check_route(self, page, hash_, texts, width, theme):
        """Open one route at one width and theme. Returns the list of failures, empty when it is fine."""
        where = "%s %s %d %s" % (page, hash_, width, theme)
        bad = []
        self.page.open(self.base + add_query(hash_, "theme", theme), width)
        self.wait_rendered()
        visible = self.page.eval(shell.VISIBLE)
        if visible != [page]:
            bad.append("%s: visible sections %r, wanted %r" % (where, visible, [page]))
        if self.page.eval("document.documentElement.getAttribute('data-ox')") != "0":
            bad.append("%s: data-ox is not 0, the page scrolls sideways" % where)
        if self.page.eval("innerWidth") != width:
            bad.append("%s: innerWidth is %r" % (where, self.page.eval("innerWidth")))
        if self.page.eval("document.documentElement.getAttribute('data-theme')") != theme:
            bad.append("%s: data-theme is not %s" % (where, theme))
        for found in self.page.eval(STATUS_BAD):
            bad.append("%s: status cell, %s" % (where, found))
        for found in self.page.eval(STACK_BAD):
            bad.append("%s: stacked bar, %s" % (where, found))
        for found in self.page.eval(LABEL_BAD % page):
            bad.append("%s: table, %s" % (where, found))
        if texts:
            shown = self.page.eval("(document.querySelector('main [data-page=%s]') || {}).innerText || ''" % page).casefold()
            for text in texts:
                # innerText applies CSS text-transform, so .s4-lab labels and .dt th come back uppercase.
                if text.casefold() not in shown:
                    bad.append("%s: text %r is not on the page" % (where, text))
        self.save_shot(screenshot_name(page, hash_, width, theme))
        if width == FULL_PAGE_WIDTH:
            height = self.page.eval("document.documentElement.scrollHeight")
            self.save_shot(screenshot_name(page, hash_, width, theme, "-full"), captureBeyondViewport=True,
                           clip={"x": 0, "y": 0, "width": width, "height": height, "scale": 1})
        return bad

    def save_shot(self, name, **params):
        """Saves a screenshot for review. Nothing asserts on it."""
        shot = self.page.call("Page.captureScreenshot", format="png", **params)
        with open(os.path.join(self.out_dir, name), "wb") as fh:
            fh.write(base64.b64decode(shot["data"]))

    def test_every_page(self):
        failures = []
        loads = 0
        for page, hash_, texts in routes_of(load_checks(), self.session):
            for theme in THEMES:
                for width in WIDTHS:
                    loads += 1
                    try:
                        failures += self.check_route(page, hash_, texts, width, theme)
                    except AssertionError as err:
                        failures.append("%s %s %d %s: %s" % (page, hash_, width, theme, err))
        self.assertGreater(loads, 0)
        self.assertEqual(failures, [], "\n".join(failures))

    # ------------------------------------------------------------ the checks catch a bad page

    def test_checks_catch_a_bad_page(self):
        self.page.open(self.base + "#/overview", 1440)
        self.wait_rendered()
        before_status = self.page.eval(STATUS_BAD)
        before_stack = self.page.eval(STACK_BAD)
        self.page.eval("""(() => {
          const main = document.querySelector('main');
          const add = (tag, cls) => { const el = document.createElement(tag); el.className = cls; el.setAttribute('data-e2e-control', '1'); main.appendChild(el); return el; };
          add('span', 'st st-match');
          const noWord = add('span', 'st st-in_effect');
          const mark = document.createElement('i'); mark.className = 'mk'; noWord.appendChild(mark);
          const bars = add('div', 'sbars');
          const bar = document.createElement('div'); bar.className = 'sb-bar'; bar.style.borderLeft = 'none'; bars.appendChild(bar);
        })()""")
        try:
            status = self.page.eval(STATUS_BAD)[len(before_status):]
            stack = self.page.eval(STACK_BAD)[len(before_stack):]
            self.assertEqual(len(status), 2, status)
            self.assertTrue(status[0].startswith("no mark"), status)
            self.assertTrue(status[1].startswith("no word"), status)
            self.assertEqual(sorted(stack), ["no legend totals or kinds table", "no start edge"], stack)
        finally:
            self.page.eval("document.querySelectorAll('[data-e2e-control]').forEach(el => el.remove())")
        self.assertEqual(self.page.eval(STATUS_BAD), before_status)
        self.assertEqual(self.page.eval(STACK_BAD), before_stack)

    def test_clipped_head_stays_in_the_text_and_adds_no_height(self):
        self.page.open(self.base + "#/models", 375)
        self.wait_rendered()
        shown = self.page.eval("document.querySelector('main [data-page=models]').innerText").casefold()
        self.assertIn("used by", shown)
        head, added = self.page.eval(HEAD_HEIGHTS)
        self.assertLessEqual(head, 1)
        self.assertLess(abs(added), 1)

    def test_label_check_catches_a_lost_column_name(self):
        self.page.open(self.base + "#/models", 375)
        self.wait_rendered()
        self.assertEqual(self.page.eval(LABEL_BAD % "models"), [])
        self.page.eval("document.querySelector('main [data-page=models] .dt td').removeAttribute('data-l')")
        self.assertEqual(len(self.page.eval(LABEL_BAD % "models")), 1)

    def test_phone_menu_screenshot(self):
        """A screenshot for review, with the menu open at 375. It asserts only that the menu opened."""
        self.page.open(self.base + add_query("#/overview", "theme", "light"), 375)
        self.wait_rendered()
        self.page.eval("document.querySelector('.btn.menu').click()")
        self.page.wait_for("document.querySelector('.btn.menu').getAttribute('aria-expanded') === 'true'")
        time.sleep(0.3)  # any slide-in finishes before the capture
        self.save_shot(screenshot_name("menu", "#/overview", 375, "light"))

    # ------------------------------------------------------------ /api/usage held back

    def paused(self):
        return [e for e in self.page.events if e.get("method") == "Fetch.requestPaused"]

    def test_settings_pages_render_while_usage_is_held_back(self):
        page = self.page
        page.call("Fetch.enable", patterns=[{"urlPattern": "*/api/usage*", "requestStage": "Request"}])
        try:
            page.call("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
            page.call("Page.navigate", url="about:blank")
            time.sleep(0.2)
            seen = len(self.paused())
            page.call("Page.navigate", url=self.base + "#/settings")
            for index, (route, section) in enumerate((("#/settings", "settings"), ("#/attention", "attention"),
                                                      ("#/files", "files"), ("#/rules", "rules"))):
                if index:  # the first route is the one navigated to; setting its hash before the page loads would hit about:blank
                    page.eval("location.hash = %s" % json.dumps(route))
                page.wait_for("""(() => {
                  const s = document.querySelector('main [data-page=%s]');
                  const h1 = s && s.querySelector('h1');
                  return Boolean(s && !s.hidden && h1 && h1.textContent.trim().length > 0);
                })()""" % section)
                self.assertEqual(page.eval(shell.VISIBLE), [section], route)
            deadline = time.time() + 10
            while len(self.paused()) == seen and time.time() < deadline:
                page.drain(0.2)
            self.assertGreater(len(self.paused()), seen, "no /api/usage request was held back")
            # The four pages that never go through fillUsage show no waiting line while the answer is held.
            wait_tail = "Only the first load takes this long"
            for section in ("settings", "attention", "files", "rules"):
                text = page.eval("(document.querySelector('main [data-page=%s]') || {textContent: ''}).textContent" % section)
                self.assertNotIn(wait_tail, text, "the waiting line shows on " + section)
            # A usage page does show it. The demo's reader has counted its files by now, so the line has a
            # number, whatever that number is.
            page.eval("location.hash = '#/overview'")
            page.wait_for("""(() => {
              const s = document.querySelector('main [data-page=overview]');
              const w = s && s.querySelector('[role=status]');
              return Boolean(s && !s.hidden && w && w.textContent.trim().indexOf('Reading') === 0);
            })()""")
            waiting = page.eval("document.querySelector('main [data-page=overview] [role=status]').textContent")
            self.assertRegex(waiting, r"^Reading [\d,]+ transcript files\. " + wait_tail)
            # Boot does not wait on /api/usage: data-rendered is set while the request is still held, and
            # data-usage stays unset until the answer is drawn.
            page.wait_for(DATA_RENDERED + " === '1'")
            self.assertEqual(page.eval(DATA_RENDERED), "1", "boot waited on the held /api/usage request")
            self.assertIsNone(page.eval(DATA_USAGE), "data-usage was set while /api/usage was held")
        finally:
            try:
                for event in self.paused():
                    try:
                        page.call("Fetch.continueRequest", requestId=event["params"]["requestId"])
                    except AssertionError:
                        pass  # that request already finished or was cancelled by a navigation
                page.call("Fetch.disable")
            except (AssertionError, EOFError, OSError):
                pass
        self.wait_rendered()

    # ------------------------------------------------------------ the window-size spike

    def test_window_size_spike(self):
        """Does --headless=new --window-size=375,900 alone give 375 CSS pixels? The sweep does not rely on it."""
        chrome = shell.Chrome(helpers._tmp_base(), extra_args=["--window-size=375,900"])
        try:
            width = chrome.page.eval("innerWidth")
        finally:
            chrome.close()
        self.assertIsInstance(width, int, "innerWidth could not be read")
        with open(os.path.join(self.out_dir, "window-size-spike.json"), "w", encoding="utf-8") as fh:
            json.dump({"inner_width": width}, fh)
        print("window-size spike: innerWidth is %d with --window-size=375,900 and no override" % width)

    # ------------------------------------------------------------ nothing left the machine

    def test_zz_nothing_left_the_machine(self):
        self.page.drain()
        urls = [e["params"]["request"]["url"] for e in self.page.events if e.get("method") == "Network.requestWillBeSent"]
        self.assertGreater(len(urls), 0)
        self.assertEqual(non_local_urls(urls, self.srv.port), [])
        logged = log_paths(self.srv.stderr())
        self.assertIn("/api/usage", logged)
        missing = sorted(same_origin_paths(urls, self.srv.port) - set(logged))
        self.assertEqual(missing, [], "the browser asked for paths the server never logged")
        bad = [m for m in self.page.messages() if "Content Security Policy" in m or "Refused to" in m or m.startswith("EXCEPTION")]
        self.assertEqual(bad, [])
        with open(self.err_path, encoding="utf-8", errors="replace") as fh:
            stderr = fh.read()
        self.assertNotIn("Content Security Policy", stderr)
        self.assertNotIn("Refused to", stderr)


if __name__ == "__main__":
    unittest.main()
