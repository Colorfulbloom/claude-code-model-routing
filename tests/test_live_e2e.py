"""End-to-end check of the Live page in headless Chrome, at 1440 and 375, light and dark. Opt in with MR_E2E=1.

Built on test_shell_e2e (its Chrome and Page classes) and gated like test_pages_e2e. Three servers run with --fixture on
the made-up demo set, built into temp folders, so nothing reads the real ~/.claude. The demo clock decides the state.
It is "2026-10-30T20:24:44+00:00" for a working session, "2026-10-30T20:52:10+00:00" for an idle one and the demo's
default for none. Screenshots land in <MR_TEST_TMP>/e2e-live for review. Importing this module starts nothing.
"""
import base64
import json
import os
import re
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
KIND_NAMES = ["Cache read", "Input", "Cache write", "Output"]
TOKEN_SHAPE = r"^[0-9][0-9,.]*[KMB]?$"
COLUMNS = ["Time", "Agent", "Model", "Effort", "Tokens", "Cache read", "Output", "Estimated cost"]
NOTE = "New means input, cache write and output. The chart and the lane have separate scales."

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

# The chart card of direction B: the session bar by kind, the New tokens chart, the cache lane with the Now band,
# the note, the wait line, the header age and the eight-column table. Read from the DOM, so it works at any width.
CARD_FACTS = """(() => {
  const s = document.querySelector('main [data-page=live]');
  const q = (sel, root) => (root || s).querySelector(sel);
  const text = (el) => (el ? el.textContent.trim() : '');
  const bar = q('.lv-meter .sb-bar');
  const lane = q('.lv-lane');
  const main = q('.lv-main');
  const wait = q('.lv-wait');
  const mainBand = main && q('.lv-nowband', main);
  const laneBand = lane && q('.lv-nowband', lane);
  const row = q('.lv-req tbody tr');
  const cells = row ? [...row.querySelectorAll('td')] : [];
  const box = (el) => (el ? el.getBoundingClientRect() : { height: 0, width: 0 });
  return {
    edge: bar ? parseFloat(getComputedStyle(bar).borderLeftWidth) : -1,
    segs: s.querySelectorAll('.lv-meter .sb-seg').length,
    bars: s.querySelectorAll('.lv-meter .sb-row').length,
    kindsHead: text(q('.lv-meter .sb-n')),
    legend: [...s.querySelectorAll('.lv-meter .klg li')].map((li) => text(li)),
    newHead: text(q('.lv-row-h .lv-row-t')),
    modelLegend: s.querySelectorAll('.lv-row-h .klg li').length,
    laneHead: text(q('.lv-lane-h .lv-row-t')),
    laneRects: lane ? lane.querySelectorAll('.lv-cr').length : -1,
    laneTitles: lane ? [...lane.querySelectorAll('.lv-cr title')].map((t) => t.textContent) : [],
    laneDy: lane ? [...lane.querySelectorAll('.dy span')].map((x) => text(x)) : [],
    laneAxis: lane ? [...lane.querySelectorAll('.dx span')].map((x) => text(x)) : [],
    mainAxis: main ? main.querySelectorAll('.dx').length : -1,
    bands: [mainBand ? 1 : 0, laneBand ? 1 : 0],
    bandX: mainBand ? mainBand.getAttribute('x') : '',
    bandFill: mainBand ? getComputedStyle(mainBand).fill : '',
    bandH: [mainBand ? parseFloat(mainBand.getAttribute('height')) : -1, laneBand ? parseFloat(laneBand.getAttribute('height')) : -1],
    mainHeight: Math.round(box(q('.dbars', main)).height),
    laneHeight: Math.round(box(q('.dbars', lane)).height),
    note: text(q('.lv-note')),
    age: text(q('.lv-time')),
    waitShown: Boolean(wait) && getComputedStyle(wait).display !== 'none',
    waitText: text(wait),
    heads: [...s.querySelectorAll('.lv-req thead th')].map((th) => text(th)),
    cellCount: cells.length,
    cacheCell: cells[5] ? text(cells[5]) : '',
    cacheCellDisplay: cells[5] ? getComputedStyle(cells[5]).display : '',
    cellDisplay: cells[0] ? getComputedStyle(cells[0]).display : '',
    cellGap: cells[0] ? parseFloat(getComputedStyle(cells[0]).columnGap) : -1,
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

    def check_card(self, where, width, facts, state):
        """What the chart card, the header and the table must show. Returns the failures."""
        bad = []
        if facts["bars"] != 1 or facts["segs"] < 1:
            bad.append("%s: session bar has %d rows and %d segments" % (where, facts["bars"], facts["segs"]))
        if facts["edge"] <= 0:
            bad.append("%s: the session bar's start edge is %r px wide, wanted more than 0" % (where, facts["edge"]))
        if facts["kindsHead"] != "This session by kind":
            bad.append("%s: session bar label is %r" % (where, facts["kindsHead"]))
        names = [item.rsplit(" ", 1)[0] for item in facts["legend"]]
        if names != KIND_NAMES:
            bad.append("%s: session bar legend reads %r, wanted all four kinds in order" % (where, facts["legend"]))
        for item in facts["legend"]:
            if not re.match(TOKEN_SHAPE, item.rsplit(" ", 1)[-1]):
                bad.append("%s: legend item %r has no total" % (where, item))
        if facts["newHead"] != "New tokens" or facts["modelLegend"] < 1:
            bad.append("%s: New tokens head is %r with %d legend items" % (where, facts["newHead"], facts["modelLegend"]))
        if facts["laneHead"] != "Cache reads":
            bad.append("%s: lane head is %r" % (where, facts["laneHead"]))
        if facts["note"] != NOTE:
            bad.append("%s: note reads %r" % (where, facts["note"]))
        if facts["mainAxis"] != 0 or len(facts["laneAxis"]) < 2:
            bad.append("%s: the x labels belong under the lane (%r in the chart, %r under the lane)" % (where, facts["mainAxis"], facts["laneAxis"]))
        if facts["bands"] != [1, 1] or facts["bandX"] != "581.6" or facts["bandFill"] in ("", "none"):
            bad.append("%s: Now band %r at x %r fill %r" % (where, facts["bands"], facts["bandX"], facts["bandFill"]))
        if min(facts["bandH"]) < 0:
            bad.append("%s: Now band heights %r" % (where, facts["bandH"]))
        if facts["mainHeight"] != (140 if width == 375 else 170) or facts["laneHeight"] != 48:
            bad.append("%s: chart is %r px and lane %r px tall" % (where, facts["mainHeight"], facts["laneHeight"]))
        if facts["heads"] != COLUMNS:
            bad.append("%s: table columns are %r" % (where, facts["heads"]))
        if facts["cellCount"] != len(COLUMNS):
            bad.append("%s: a row has %d cells, wanted %d" % (where, facts["cellCount"], len(COLUMNS)))
        if width == 375:
            if facts["cellDisplay"] != "flex" or not facts["cellGap"] > 0:
                bad.append("%s: a request cell is display %r with a column gap of %r" % (where, facts["cellDisplay"], facts["cellGap"]))
            if facts["cacheCellDisplay"] != "none":
                bad.append("%s: the Cache read cell shows on the phone (display %r)" % (where, facts["cacheCellDisplay"]))
        elif facts["cacheCellDisplay"] == "none":
            bad.append("%s: the Cache read cell is hidden at %d" % (where, width))
        if state == "live":
            if facts["laneRects"] < 1 or len(facts["laneDy"]) != 2 or facts["laneDy"][1] != "0":
                bad.append("%s: lane has %r rects and labels %r, wanted rects and a peak label above 0" % (where, facts["laneRects"], facts["laneDy"]))
            if any("Cache reads " not in title for title in facts["laneTitles"]):
                bad.append("%s: lane titles %r" % (where, facts["laneTitles"]))
            if not re.match(r"^Last request \d+ (s|min) ago$", facts["age"]):
                bad.append("%s: header reads %r, wanted a Last request age" % (where, facts["age"]))
        if state == "idle":
            if not re.match(r"^Last request \d+ min ago$", facts["age"]):
                bad.append("%s: header reads %r, wanted a Last request age in minutes" % (where, facts["age"]))
            if not facts["waitShown"] or facts["waitText"] != "A request shows up here once it's written to the transcript.":
                bad.append("%s: the wait line is %r, shown %r, wanted it shown when idle" % (where, facts["waitText"], facts["waitShown"]))
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
                failures += self.check_card(where, width, self.page.eval(CARD_FACTS), "live")
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
                failures += self.check_card(where, width, self.page.eval(CARD_FACTS), "idle")
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
