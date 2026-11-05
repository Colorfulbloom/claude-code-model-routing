"""End-to-end check of the Live page's dispatch canvas in headless Chrome. Opt in with MR_E2E=1.

Built on test_live_e2e (its helpers) and test_shell_e2e (Chrome and Page). One server per scenario runs with
--fixture on a made-up world from tests/fixtures/live_flow/build_flow.py, built into a temp folder, so nothing reads
the real ~/.claude. The scenario's own clock is in the built session.json. The checks read the DOM contract of the
card (section.cd.lv-fl) at 1440 and 375, light and dark, plus a reduced-motion run for the busy world. Screenshots
of the Live page section land in <MR_TEST_TMP or the system temp dir>/e2e-live-flow, named
<scenario>-<width>-<theme>[-reduced].png. Importing this module starts nothing.
"""
import base64
import json
import os
import re
import sys
import tempfile
import time
import unittest

import helpers
import test_live_e2e as live
import test_pages_e2e as pages
import test_server as ts
import test_shell_e2e as shell

sys.path.insert(0, os.path.join(helpers.FIXTURES, "live_flow"))
import build_flow  # noqa: E402

PROJECT = live.PROJECT
WIDTHS = live.WIDTHS
THEMES = live.THEMES
MAIN_NAME = "main session"
BUSY_NAMES = [MAIN_NAME, "deep-reasoner", "scout 1", "scout 2", "tech-writer", "fast-worker 1", "fast-worker 2", "judge"]
BUSY_STATES = ["working", "working", "done", "done", "working", "done", "done", "working"]
UNLINKED_NAMES = BUSY_NAMES + ["scout 3"]
UNLINKED_STATES = BUSY_STATES + ["working"]
MANY_RUNS = 25

CARD = "document.querySelector('main [data-page=live] section.cd.lv-fl')"

FACTS = """(() => {
  const card = document.querySelector('main [data-page=live] section.cd.lv-fl');
  if (!card) return { card: false };
  const text = (el) => (el ? el.textContent.trim().replace(/\\s+/g, ' ') : '');
  const canvas = card.querySelector('.lv-fl-canvas');
  const nodes = [...card.querySelectorAll('.lv-fl-node:not(.lv-fl-stub)')].map((n) => {
    const st = n.querySelector('.lv-fl-st');
    return {
      run: n.getAttribute('data-run'), s: n.getAttribute('data-s'),
      n: text(n.querySelector('.lv-fl-n')), name: text(n.querySelector('.lv-fl-name')),
      bdg: text(n.querySelector('.lv-fl-bdg')), rnd: text(n.querySelector('.lv-fl-rnd')),
      st: text(st), stS: st ? st.getAttribute('data-s') : null,
      glyph: st ? getComputedStyle(st, '::before').content : '',
      meta: text(n.querySelector('.lv-fl-meta')), tc: text(n.querySelector('.lv-fl-tc')),
      hidden: Boolean(n.closest('[aria-hidden="true"]')), top: n.getBoundingClientRect().top,
    };
  });
  const stubs = [...card.querySelectorAll('button.lv-fl-node.lv-fl-stub')].map((b) => ({
    expanded: b.getAttribute('aria-expanded'), text: text(b), exposed: !b.closest('[aria-hidden="true"]'),
  }));
  const infinite = card.getAnimations({ subtree: true }).filter((a) => {
    const t = a.effect && a.effect.getComputedTiming ? a.effect.getComputedTiming() : null;
    return t && t.iterations === Infinity;
  }).length;
  return {
    card: true,
    title: text(card.querySelector('h2, .cd-h, .hd')),
    narrowClass: canvas ? canvas.classList.contains('lv-fl-narrow') : null,
    stage: Boolean(card.querySelector('.lv-fl-stage')),
    edgesHidden: Boolean(card.querySelector('svg.lv-fl-edges[aria-hidden="true"]')),
    paths: card.querySelectorAll('svg.lv-fl-edges path.lv-fl-e').length,
    guess: card.querySelectorAll('path.lv-fl-e-guess').length,
    nodes, stubs,
    chipsG: [...card.querySelectorAll('.lv-fl-chip.lv-fl-chip-g')].map(text),
    chipsR: [...card.querySelectorAll('.lv-fl-chip.lv-fl-chip-r')].map(text),
    sr: [...card.querySelectorAll('ol.lv-fl-sr li')].map((li) => ({ run: li.getAttribute('data-run'), text: text(li) })),
    srHead: text(card.querySelector('.lv-fl-srw h3')),
    note: Boolean(card.querySelector('p.lv-fl-note')),
    unlinked: [...card.querySelectorAll('p.lv-fl-note.lv-fl-unlinked')]
      .filter((p) => !p.hidden && getComputedStyle(p).display !== 'none').map(text),
    empty: [...card.querySelectorAll('.lv-fl-empty')].map(text),
    motionClasses: card.querySelectorAll('.lv-fl-enter, .lv-fl-draw, .lv-fl-renew').length,
    infinite, animations: card.getAnimations({ subtree: true }).length,
    bodyScroll: document.body.scrollWidth, rootScroll: document.documentElement.scrollWidth, inner: innerWidth,
    between: (() => {
      const kids = [...card.parentElement.children];
      const at = kids.indexOf(card);
      const before = kids[at - 1], after = kids[at + 1];
      return [before ? before.className : '', after ? text(after.querySelector('h2, .cd-h, .hd')) : ''];
    })(),
  };
})()"""


def output_dir():
    return os.path.join(helpers._tmp_base() or tempfile.gettempdir(), "e2e-live-flow")


def node_count_is(expected):
    """JS that is true once the canvas has drawn `expected` cards (None means at least one)."""
    count = CARD + " ? " + CARD + ".querySelectorAll('.lv-fl-node:not(.lv-fl-stub)').length : 0"
    if expected is None:
        return "(" + count + ") >= 1"
    return "(" + count + ") === %d" % expected


@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the headless Chrome checks")
@unittest.skipIf(shell.CHROME is None, "Chrome was not found (set MR_CHROME to its path)")
class LiveFlowE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out_dir = output_dir()
        os.makedirs(cls.out_dir, exist_ok=True)
        cls.roots = []
        cls.servers = {}
        cls.chrome = None
        try:
            for name in build_flow.SCENARIOS:
                root = ts.make_root("mr-e2e-flow-%s-" % name)
                cls.roots.append(root)
                folder = os.path.join(root, "set")
                build_flow.build(folder, name)
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
        print("\nLive dispatch canvas screenshots: %s" % output_dir())

    # ------------------------------------------------------------ helpers

    def set_reduced(self, reduced):
        self.page.call("Emulation.setEmulatedMedia", features=[
            {"name": "prefers-reduced-motion", "value": "reduce" if reduced else "no-preference"}])

    def open_flow(self, name, width, theme, expected):
        url = self.servers[name][1] + pages.add_query("#/live?project=" + PROJECT, "theme", theme)
        self.page.open(url, width)
        self.page.wait_for(live.shell_rendered())
        self.page.wait_for(live.LEFT_WAIT)
        self.page.wait_for(node_count_is(expected))

    def save_shot(self, name, suffix=""):
        rect = self.page.eval(
            "(() => { let el = document.querySelector('main [data-page=live]');"
            " while (el && !el.getBoundingClientRect().width) el = el.parentElement;"
            " const r = (el || document.body).getBoundingClientRect();"
            " return { x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height }; })()")
        shot = self.page.call("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                              clip={"x": rect["x"], "y": rect["y"], "width": rect["width"],
                                    "height": max(1, min(rect["height"], 6000)), "scale": 1})
        with open(os.path.join(self.out_dir, name + suffix + ".png"), "wb") as fh:
            fh.write(base64.b64decode(shot["data"]))

    def check_common(self, where, width, theme, facts):
        bad = live_common(self.page, where, width, theme)
        if not facts["card"]:
            return bad + ["%s: no section.cd.lv-fl card" % where]
        if facts["bodyScroll"] > facts["inner"] or facts["rootScroll"] > facts["inner"]:
            bad.append("%s: the page scrolls sideways (body %d, root %d, window %d)" % (
                where, facts["bodyScroll"], facts["rootScroll"], facts["inner"]))
        if not facts["stage"]:
            bad.append("%s: no div.lv-fl-stage inside the canvas" % where)
        if facts["narrowClass"] != (width == 375):
            bad.append("%s: lv-fl-narrow is %r at %d" % (where, facts["narrowClass"], width))
        if not facts["edgesHidden"]:
            bad.append("%s: svg.lv-fl-edges is missing or not aria-hidden" % where)
        if "lv-g21" not in facts["between"][0] or "Latest" not in facts["between"][1]:
            bad.append("%s: the card sits after %r and before %r, wanted after the charts grid and before Latest requests" % (
                where, facts["between"][0], facts["between"][1]))
        if facts["motionClasses"]:
            bad.append("%s: %d lv-fl-enter/draw/renew classes on the first answer" % (where, facts["motionClasses"]))
        if facts["infinite"]:
            bad.append("%s: %d infinite animations in the card" % (where, facts["infinite"]))
        if not facts["srHead"]:
            bad.append("%s: the screen reader list has no heading" % where)
        for node in facts["nodes"]:
            who = "%s: card %r" % (where, node["name"])
            if node["stS"] != node["s"] or node["st"].lower() != node["s"]:
                bad.append("%s: state word %r with data-s %r and node data-s %r" % (who, node["st"], node["stS"], node["s"]))
            if node["glyph"] in ("", "none", "normal", '""', "''"):
                bad.append("%s: the state has no glyph (::before content %r)" % (who, node["glyph"]))
            if not node["hidden"]:
                bad.append("%s: the card is not inside an aria-hidden layer" % who)
            if not node["bdg"] or not node["tc"] or not node["meta"]:
                bad.append("%s: badge %r, figures %r or meta %r is empty" % (who, node["bdg"], node["tc"], node["meta"]))
        for stub in facts["stubs"]:
            if not stub["exposed"] or stub["expanded"] not in ("true", "false"):
                bad.append("%s: stub %r is hidden or has aria-expanded %r" % (where, stub["text"], stub["expanded"]))
        runs = [n["run"] for n in facts["nodes"]]
        if len(set(runs)) != len(runs):
            bad.append("%s: duplicate data-run values" % where)
        return bad

    def check_busy_like(self, where, width, facts, names, states):
        bad = []
        if len(facts["nodes"]) != len(names):
            return ["%s: %d cards, wanted %d" % (where, len(facts["nodes"]), len(names))]
        by_sr = [item["text"].lower() for item in facts["sr"]]
        if len(by_sr) != len(names):
            bad.append("%s: %d screen reader items, wanted %d" % (where, len(by_sr), len(names)))
        for want, text in zip(names, by_sr):
            if not text.startswith(want):
                bad.append("%s: screen reader order, %r does not start with %r" % (where, text, want))
        if facts["sr"] and facts["sr"][0]["run"] != "@main":
            bad.append("%s: the first screen reader item is %r, wanted @main" % (where, facts["sr"][0]["run"]))
        order = [item["run"] for item in facts["sr"]]
        ordered = sorted(facts["nodes"], key=lambda n: order.index(n["run"]) if n["run"] in order else len(order))
        if [n["name"].lower() for n in ordered] != names:
            bad.append("%s: card labels %r, wanted %r" % (where, [n["name"] for n in ordered], names))
        if [n["s"] for n in ordered] != states:
            bad.append("%s: states %r, wanted %r" % (where, [n["s"] for n in ordered], states))
        main = ordered[0]
        if main["n"] or main["bdg"] != "Opus 5.5 · high":
            bad.append("%s: main card has number %r and badge %r" % (where, main["n"], main["bdg"]))
        for node in ordered[1:]:
            if not node["n"]:
                bad.append("%s: card %r has no dispatch number" % (where, node["name"]))
        rounds = [n["name"].lower() for n in ordered if n["rnd"]]
        if rounds != ["tech-writer"] or any(n["rnd"] != "Round 2" for n in ordered if n["rnd"]):
            bad.append("%s: Round badges on %r, wanted only tech-writer reading Round 2" % (where, rounds))
        writer = [n for n in ordered if n["name"].lower() == "tech-writer"][0]
        if width == 375:
            # The narrow list follows the dispatch tree: each agent's children come right under it.
            seen = [n["name"].lower() for n in sorted(ordered, key=lambda n: n["top"])]
            tree = [name for name in names if name != "tech-writer"] + ["tech-writer"]
            if seen != tree:
                bad.append("%s: the narrow list reads %r on screen, wanted %r" % (where, seen, tree))
            if not re.match(r"^Resumed by Main session · \S", writer["meta"]):
                bad.append("%s: tech-writer meta reads %r, wanted Resumed by Main session · time" % (where, writer["meta"]))
        else:
            if facts["chipsG"] != ["2 agents at once"] * 2:
                bad.append("%s: group chips %r, wanted two reading 2 agents at once" % (where, facts["chipsG"]))
            if len(facts["chipsR"]) != 1 or not re.match(r"^Round 2 · \S", facts["chipsR"][0]):
                bad.append("%s: round chips %r, wanted one reading Round 2 · time" % (where, facts["chipsR"]))
            if facts["paths"] < len(names):
                bad.append("%s: %d connectors for %d cards" % (where, facts["paths"], len(names)))
        if facts["empty"]:
            bad.append("%s: the empty state shows with %d agents" % (where, len(names) - 1))
        return bad

    # ------------------------------------------------------------ the scenarios

    def test_busy(self):
        failures = []
        for theme in THEMES:
            for width in WIDTHS:
                where = "busy %d %s" % (width, theme)
                self.open_flow("busy", width, theme, len(BUSY_NAMES))
                facts = self.page.eval(FACTS)
                failures += self.check_common(where, width, theme, facts)
                failures += self.check_busy_like(where, width, facts, BUSY_NAMES, BUSY_STATES)
                if facts["unlinked"]:
                    failures.append("%s: the no-dispatcher note shows with every run linked" % where)
                if facts["guess"]:
                    failures.append("%s: %d dashed guessed connectors, wanted none" % (where, facts["guess"]))
                # An unchanged answer adds no motion class, even after a few polls.
                time.sleep(2.5)
                again = self.page.eval(FACTS)
                if again["motionClasses"]:
                    failures.append("%s: motion classes appeared on an unchanged answer" % where)
                self.save_shot("busy-%d-%s" % (width, theme))
        self.assertEqual(failures, [], "\n".join(failures))

    def test_busy_reduced_motion(self):
        failures = []
        self.set_reduced(True)
        try:
            for width in WIDTHS:
                where = "busy %d light reduced" % width
                self.open_flow("busy", width, "light", len(BUSY_NAMES))
                self.assertTrue(self.page.eval("matchMedia('(prefers-reduced-motion: reduce)').matches"))
                facts = self.page.eval(FACTS)
                failures += self.check_common(where, width, "light", facts)
                failures += self.check_busy_like(where, width, facts, BUSY_NAMES, BUSY_STATES)
                if facts["animations"]:
                    failures.append("%s: %d animations running under reduced motion, wanted none" % (where, facts["animations"]))
                self.save_shot("busy-%d-light" % width, "-reduced")
        finally:
            self.set_reduced(False)
        self.assertEqual(failures, [], "\n".join(failures))

    def test_unlinked(self):
        failures = []
        for theme in THEMES:
            for width in WIDTHS:
                where = "unlinked %d %s" % (width, theme)
                self.open_flow("unlinked", width, theme, len(UNLINKED_NAMES))
                facts = self.page.eval(FACTS)
                failures += self.check_common(where, width, theme, facts)
                if len(facts["nodes"]) == len(UNLINKED_NAMES):
                    order = [item["run"] for item in facts["sr"]]
                    ordered = sorted(facts["nodes"], key=lambda n: order.index(n["run"]) if n["run"] in order else len(order))
                    if [n["name"].lower() for n in ordered] != UNLINKED_NAMES:
                        failures.append("%s: card labels %r" % (where, [n["name"] for n in ordered]))
                    if [n["s"] for n in ordered] != UNLINKED_STATES:
                        failures.append("%s: states %r" % (where, [n["s"] for n in ordered]))
                if len(facts["unlinked"]) != 1 or not facts["unlinked"][0]:
                    failures.append("%s: wanted one p.lv-fl-note.lv-fl-unlinked with text, got %r" % (where, facts["unlinked"]))
                if width != 375 and facts["guess"] != 1:
                    failures.append("%s: %d dashed guessed connectors, wanted 1" % (where, facts["guess"]))
                if facts["sr"] and "dispatched by main session" in facts["sr"][-1]["text"].lower():
                    failures.append("%s: the unlinked run's screen reader item says Dispatched by Main session" % where)
                self.save_shot("unlinked-%d-%s" % (width, theme))
        self.assertEqual(failures, [], "\n".join(failures))

    def test_empty(self):
        failures = []
        for theme in THEMES:
            for width in WIDTHS:
                where = "empty %d %s" % (width, theme)
                self.open_flow("empty", width, theme, 1)
                facts = self.page.eval(FACTS)
                failures += self.check_common(where, width, theme, facts)
                if len(facts["nodes"]) != 1 or facts["nodes"][0]["run"] != "@main":
                    failures.append("%s: cards %r, wanted only the main session" % (where, [n["run"] for n in facts["nodes"]]))
                if len(facts["empty"]) != 1 or "No agents yet" not in facts["empty"][0]:
                    failures.append("%s: empty state %r, wanted No agents yet" % (where, facts["empty"]))
                if len(facts["sr"]) != 1:
                    failures.append("%s: %d screen reader items, wanted 1" % (where, len(facts["sr"])))
                if facts["chipsG"] or facts["chipsR"] or facts["unlinked"]:
                    failures.append("%s: chips %r %r or note %r with no agents" % (where, facts["chipsG"], facts["chipsR"], facts["unlinked"]))
                self.save_shot("empty-%d-%s" % (width, theme))
        self.assertEqual(failures, [], "\n".join(failures))

    def test_many(self):
        failures = []
        for theme in THEMES:
            for width in WIDTHS:
                where = "many %d %s" % (width, theme)
                self.open_flow("many", width, theme, None)
                facts = self.page.eval(FACTS)
                failures += self.check_common(where, width, theme, facts)
                if len(facts["sr"]) != MANY_RUNS:
                    failures.append("%s: %d screen reader items, wanted %d" % (where, len(facts["sr"]), MANY_RUNS))
                if facts["sr"] and facts["sr"][0]["run"] != "@main":
                    failures.append("%s: the first screen reader item is not @main" % where)
                badges = [n["rnd"] for n in facts["nodes"] if n["rnd"]]
                if badges != ["Round 2"]:
                    failures.append("%s: Round badges %r, wanted one Round 2 (the peer-resumed scout)" % (where, badges))
                if not facts["stubs"]:
                    failures.append("%s: no collapse stub with %d runs" % (where, MANY_RUNS))
                    continue
                if any(stub["expanded"] != "false" for stub in facts["stubs"]):
                    failures.append("%s: a stub starts expanded: %r" % (where, facts["stubs"]))
                for chip in facts["chipsG"]:
                    if not re.match(r"^[2-9] agents at once$", chip):
                        failures.append("%s: group chip %r" % (where, chip))
                self.save_shot("many-%d-%s" % (width, theme))
                failures += self.toggle_stub(where)
        self.assertEqual(failures, [], "\n".join(failures))

    def toggle_stub(self, where):
        """Press the first stub: it expands, shows more cards, then collapses back."""
        bad = []
        stub = CARD + ".querySelector('button.lv-fl-stub')"
        before = self.page.eval(FACTS)
        shown = re.match(r"^Show (\d+) finished", before["stubs"][0]["text"])
        self.page.eval(stub + ".click()")
        self.page.wait_for(stub + ".getAttribute('aria-expanded') === 'true'", timeout=5)
        opened = self.page.eval(FACTS)
        if shown and len(opened["nodes"]) <= len(before["nodes"]):
            bad.append("%s: %d cards after Show, wanted more than %d" % (where, len(opened["nodes"]), len(before["nodes"])))
        if "Hide finished" not in opened["stubs"][0]["text"]:
            bad.append("%s: expanded stub reads %r, wanted Hide finished" % (where, opened["stubs"][0]["text"]))
        # Finished workers hide behind the stubs, so group chips are checked once one is open.
        if self.page.eval("innerWidth") != 375:
            if not opened["chipsG"]:
                bad.append("%s: no group chips with a stub open" % where)
            for chip in opened["chipsG"]:
                if not re.match(r"^[2-9] agents at once$", chip):
                    bad.append("%s: group chip %r with a stub open" % (where, chip))
        if opened["motionClasses"] and not self.page.eval("matchMedia('(prefers-reduced-motion: no-preference)').matches"):
            bad.append("%s: motion classes under reduced motion" % where)
        self.page.eval(CARD + ".querySelector('button.lv-fl-stub').click()")
        self.page.wait_for(CARD + ".querySelector('button.lv-fl-stub').getAttribute('aria-expanded') === 'false'", timeout=5)
        closed = self.page.eval(FACTS)
        if len(closed["nodes"]) != len(before["nodes"]):
            bad.append("%s: %d cards after Hide, wanted %d" % (where, len(closed["nodes"]), len(before["nodes"])))
        return bad


def live_common(page, where, width, theme):
    """The page-wide checks every Live test makes (test_live_e2e.check_common, without needing its class)."""
    bad = []
    if page.eval(live.OX) != "0":
        bad.append("%s: data-ox is not 0, the page scrolls sideways" % where)
    if page.eval("innerWidth") != width:
        bad.append("%s: innerWidth is %r" % (where, page.eval("innerWidth")))
    if page.eval("document.documentElement.getAttribute('data-theme')") != theme:
        bad.append("%s: data-theme is not %s" % (where, theme))
    for found in page.eval(live.PILL_BAD):
        bad.append("%s: pill, %s" % (where, found))
    return bad


if __name__ == "__main__":
    unittest.main()
