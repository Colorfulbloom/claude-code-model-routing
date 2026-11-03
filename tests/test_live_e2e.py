"""End-to-end check of the Live page in headless Chrome, at 1440 and 375, light and dark. Opt in with MR_E2E=1.

Built on test_shell_e2e (its Chrome and Page classes) and gated like test_pages_e2e. Three servers run with --fixture on
the made-up demo set, built into temp folders, so nothing reads the real ~/.claude. The demo clock decides the state.
It is "2026-10-30T20:24:44+00:00" for a working session, "2026-10-30T20:52:10+00:00" for an idle one and the demo's
default for none. Screenshots land in <MR_TEST_TMP>/e2e-live for review. Importing this module starts nothing.
"""
import base64
import json
import os
import sys
import tempfile
import unittest

import helpers
import test_pages_e2e as pages
import test_server as ts
import test_shell_e2e as shell

sys.path.insert(0, os.path.join(helpers.FIXTURES, "demo"))
import build_demo  # noqa: E402

PROJECT = "tidewater-reporting"
LIVE_NOW = "2026-10-30T20:24:44+00:00"
IDLE_NOW = "2026-10-30T20:52:10+00:00"
WIDTHS = (1440, 375)
THEMES = ("light", "dark")
ROWS_AT_375 = 5
ROWS_MAX = 8

SECTION = "document.querySelector('main [data-page=live]')"
LIVE_STATE = "(" + SECTION + ".getAttribute('data-live') || '')"
LEFT_WAIT = "(() => { const s = " + SECTION + ".getAttribute('data-live'); return Boolean(s) && s !== 'wait'; })()"
OX = "document.documentElement.getAttribute('data-ox')"

# Every activity or status pill on the page needs its glyph (the ::before mark) and its word, never hue alone.
PILL_BAD = """(() => {
  const bad = [];
  document.querySelectorAll('main [data-page=live] .lv-act, main [data-page=live] .lv-pill:not([hidden])').forEach((el) => {
    const word = (el.textContent || '').trim();
    const mark = el.classList.contains('lv-pill') ? el.querySelector('.lv-mk') : el;
    const content = mark ? getComputedStyle(mark, '::before').content : '';
    if (!word) bad.push('no word in ' + el.className);
    if (!content || content === 'none' || content === 'normal' || content === '""' || content === "''") bad.push('no glyph: ' + word);
  });
  return bad;
})()"""

COUNTS = """(() => {
  const s = document.querySelector('main [data-page=live]');
  const rows = [...s.querySelectorAll('.lv-req tbody tr')];
  return {
    kpis: s.querySelectorAll('.kpi').length,
    columns: s.querySelectorAll('.dbars .col').length,
    legend: s.querySelectorAll('.klg li').length,
    rows: rows.length,
    shown: rows.filter((r) => getComputedStyle(r).display !== 'none').length,
    pills: s.querySelectorAll('.lv-act').length,
  };
})()"""


def move_clock(path, now):
    """Set the fixture clock in a built demo set's session.json."""
    with open(path, encoding="utf-8") as fh:
        session = json.load(fh)
    session["now"] = now
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(session, fh, indent=2)


def output_dir():
    return os.path.join(helpers._tmp_base() or tempfile.gettempdir(), "e2e-live")


@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the headless Chrome checks")
@unittest.skipIf(shell.CHROME is None, "Chrome was not found (set MR_CHROME to its path)")
class LiveE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out_dir = output_dir()
        os.makedirs(cls.out_dir, exist_ok=True)
        cls.roots = []
        cls.servers = {}
        cls.chrome = None
        try:
            for name, now in (("live", LIVE_NOW), ("idle", IDLE_NOW), ("empty", None)):
                root = ts.make_root("mr-e2e-live-%s-" % name)
                cls.roots.append(root)
                folder = os.path.join(root, "set")
                # The demo's data depends on its clock, so build at the default clock and move only
                # session.json's "now" into (or past) the Tidewater session.
                build_demo.build(folder)
                if now is not None:
                    move_clock(os.path.join(folder, "session.json"), now)
                srv = ts.start(root, ["--fixture", folder], name=name)
                cls.servers[name] = [srv, "http://127.0.0.1:%d/" % srv.port, folder, root]
            cls.chrome = shell.Chrome(helpers._tmp_base())
            cls.page = cls.chrome.page
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "chrome", None):
            cls.chrome.close()
        for entry in getattr(cls, "servers", {}).values():
            if entry[0] is not None:
                entry[0].stop()
        for root in getattr(cls, "roots", []):
            helpers.rmtree_force(root)

    # ------------------------------------------------------------ helpers

    def base(self, name):
        return self.servers[name][1]

    def open_live(self, name, width, theme, project=PROJECT):
        url = self.base(name) + pages.add_query("#/live?project=" + project, "theme", theme)
        self.page.open(url, width)
        self.page.wait_for(shell_rendered())
        self.page.wait_for(LEFT_WAIT)

    def save_shot(self, name):
        shot = self.page.call("Page.captureScreenshot", format="png")
        with open(os.path.join(self.out_dir, name), "wb") as fh:
            fh.write(base64.b64decode(shot["data"]))

    def check_common(self, where, width, theme):
        bad = []
        if self.page.eval(OX) != "0":
            bad.append("%s: data-ox is not 0, the page scrolls sideways" % where)
        if self.page.eval("innerWidth") != width:
            bad.append("%s: innerWidth is %r" % (where, self.page.eval("innerWidth")))
        if self.page.eval("document.documentElement.getAttribute('data-theme')") != theme:
            bad.append("%s: data-theme is not %s" % (where, theme))
        for found in self.page.eval(PILL_BAD):
            bad.append("%s: pill, %s" % (where, found))
        return bad

    # ------------------------------------------------------------ the states

    def test_a_working_session(self):
        failures = []
        for theme in THEMES:
            for width in WIDTHS:
                where = "live %d %s" % (width, theme)
                self.open_live("live", width, theme)
                state = self.page.eval(LIVE_STATE)
                if state != "live":
                    failures.append("%s: data-live is %r, wanted 'live'" % (where, state))
                failures += self.check_common(where, width, theme)
                counts = self.page.eval(COUNTS)
                if counts["kpis"] != 4:
                    failures.append("%s: %d KPI tiles, wanted 4" % (where, counts["kpis"]))
                if counts["columns"] < 1:
                    failures.append("%s: the chart has no columns" % where)
                if counts["legend"] < 1:
                    failures.append("%s: the chart has no legend" % where)
                if not 1 <= counts["rows"] <= ROWS_MAX:
                    failures.append("%s: %d request rows, wanted 1 to %d" % (where, counts["rows"], ROWS_MAX))
                limit = ROWS_AT_375 if width == 375 else ROWS_MAX
                if not 1 <= counts["shown"] <= limit:
                    failures.append("%s: %d rows on screen, wanted 1 to %d" % (where, counts["shown"], limit))
                if counts["pills"] < 2:
                    failures.append("%s: %d activity pills, wanted the session and its agents" % (where, counts["pills"]))
                self.save_shot("live-working-%d-%s.png" % (width, theme))
        self.assertEqual(failures, [], "\n".join(failures))

    def test_an_idle_session(self):
        failures = []
        for theme in THEMES:
            for width in WIDTHS:
                where = "idle %d %s" % (width, theme)
                self.open_live("idle", width, theme)
                state = self.page.eval(LIVE_STATE)
                if state != "idle":
                    failures.append("%s: data-live is %r, wanted 'idle'" % (where, state))
                failures += self.check_common(where, width, theme)
                counts = self.page.eval(COUNTS)
                if counts["kpis"] != 4:
                    failures.append("%s: %d KPI tiles, wanted 4" % (where, counts["kpis"]))
                shown = self.page.eval("(" + SECTION + ".querySelector('.lv-sess') || {}).innerText || ''")
                if "Last request at" not in shown or "Ended" in shown:
                    failures.append("%s: the session line reads %r" % (where, shown))
                self.save_shot("live-idle-%d-%s.png" % (width, theme))
        self.assertEqual(failures, [], "\n".join(failures))

    def test_no_session(self):
        failures = []
        for theme in THEMES:
            for width in WIDTHS:
                where = "empty %d %s" % (width, theme)
                self.open_live("empty", width, theme)
                state = self.page.eval(LIVE_STATE)
                if state != "empty":
                    failures.append("%s: data-live is %r, wanted 'empty'" % (where, state))
                failures += self.check_common(where, width, theme)
                self.save_shot("live-empty-%d-%s.png" % (width, theme))
        self.assertEqual(failures, [], "\n".join(failures))

    def test_all_projects_asks_for_a_project(self):
        self.open_live("live", 1440, "light", project="all")
        self.assertEqual(self.page.eval(LIVE_STATE), "pick")
        self.assertEqual(self.page.eval(OX), "0")

    def test_zz_not_updating_when_the_server_stops(self):
        """Runs last: it stops the live server. The pill shows its mark and its word, and the last data stays."""
        entry = self.servers["live"]
        failures = []
        for theme in THEMES:
            for width in WIDTHS:
                where = "lost %d %s" % (width, theme)
                self.open_live("live", width, theme)
                self.assertEqual(self.page.eval(LIVE_STATE), "live", where)
                entry[0].stop()
                self.page.wait_for("(" + SECTION + ".getAttribute('data-live')) === 'lost'", timeout=30)
                failures += self.check_common(where, width, theme)
                word = self.page.eval("(" + SECTION + ".querySelector('.lv-pill') || {}).innerText || ''").strip()
                if word != "Not updating":
                    failures.append("%s: the pill reads %r" % (where, word))
                if self.page.eval(COUNTS)["rows"] < 1:
                    failures.append("%s: the last good rows are gone" % where)
                self.save_shot("live-lost-%d-%s.png" % (width, theme))
                # The first pass stopped the server, so the rest of the loop needs a fresh one.
                root = entry[3]
                srv = ts.start(root, ["--fixture", entry[2]], name="live-again")
                entry[0] = srv
                entry[1] = "http://127.0.0.1:%d/" % srv.port
        self.assertEqual(failures, [], "\n".join(failures))


def shell_rendered():
    """Boot is done, so the router has drawn the page."""
    return pages.DATA_RENDERED + " === '1'"


if __name__ == "__main__":
    unittest.main()
