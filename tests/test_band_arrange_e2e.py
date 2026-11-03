"""End-to-end checks of arranging in the Settings band (Stage 5 direction A) in headless Chrome. Opt in with MR_E2E=1.

Built like test_settings_e2e: the server runs with --fixture on the made-up demo set, so nothing reads the real
~/.claude. The band is the editor while Arrange is pressed. These tests check what the node checks cannot: real
layout (nothing under the bottom of the window, nothing clipped, clear of the Save bar), real Tab order, real
mouse drags and the card fill of the step buttons in both themes.

The module-level scripts are pure, and importing this module starts nothing, so tests/test_e2e_checks.py could
check them with no browser.

Assumptions about the build (from the Stage 5 plan and its review amendments):
- A position in a status line counts from 1, and the total is every setting in the saved order.
- The saved order is the default order here, because setUp clears every band-order: key before each test.
- The demo set has more settings than fit a 1100 wide window, so the tray holds some at that width.
"""
import json
import os
import unittest

import helpers
import test_pages_e2e as pages
import test_server as ts
import test_shell_e2e as shell

SETTINGS = "#/settings"
PAGE = "[data-page=settings]"
ARRANGE = PAGE + " button.s6-arr"
BAND = PAGE + " nav.s5-a"
CELLS = BAND + " > div.s4-stat[data-setting]"
TRAY = "#settings-arrange.s7-tray"
TRAY_CELLS = TRAY + " .s7-trow > [data-setting]"
FOLD = TRAY + " .s6-fold"
EMPTY = TRAY + " .s7-empty"
RESET = "[data-arrange=reset]"
DONE = "[data-arrange=done]"
MORE = BAND + " > .s5-more"
STATUS = PAGE + " [role=status]"
PHONE_LIST = "#settings-arrange.s6-ap"
PHONE_ROWS = PHONE_LIST + " .s6-ar"
SAVE_BAR = ".s4-rf"

EMPTY_NOTE = "Every setting fits at this window size. In a smaller window, the ones that don't fit show here."
FOLD_NOTE = "More starts here at this window size"
PHONE_NOTE = "On a phone only the open setting gets a cell. This order sets the More settings list."

TAB = {"key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9}

DESCRIBE_ACTIVE = """(() => {
  const a = document.activeElement;
  if (!a) return 'nothing';
  return a.tagName.toLowerCase() + (a.getAttribute('class') ? '.' + a.getAttribute('class').split(' ').join('.') : '');
})()"""

# The keys of the band cells and of the tray cells, each in document order.
KEYS = "(() => { const keys = (sel) => [...document.querySelectorAll(sel)].map((e) => e.getAttribute('data-setting'));" \
       " return { band: keys(%s), tray: keys(%s) }; })()" % (json.dumps(CELLS), json.dumps(TRAY_CELLS))

# What a Tab walk should visit from Arrange, built from the DOM: each cell's enabled Earlier then Later, band
# first and then the tray, then Reset when it is on, then Done. Each stop is the data-arrange value.
EXPECTED_STOPS = """(() => {
  const out = [];
  const cells = [...document.querySelectorAll(%s), ...document.querySelectorAll(%s)];
  cells.forEach((cell) => {
    ['up:', 'down:'].forEach((p) => {
      const b = cell.querySelector('[data-arrange^="' + p + '"]');
      if (b && !b.disabled) out.push(b.getAttribute('data-arrange'));
    });
  });
  const reset = document.querySelector(%s);
  if (reset && !reset.disabled && reset.getAttribute('aria-disabled') !== 'true') out.push('reset');
  out.push('done');
  return out;
})()""" % (json.dumps(CELLS), json.dumps(TRAY_CELLS), json.dumps(RESET))

ACTIVE_STOP = "(() => { const a = document.activeElement; return a && a.getAttribute ? a.getAttribute('data-arrange') : null; })()"

# Nothing sits under the bottom of the window or past its side, and the band and the tray are not clipped by an
# ancestor that hides overflow. Returns { bottom, innerHeight, scrollWidth, innerWidth, clipped }.
FIT = """(() => {
  const done = document.querySelector(%s);
  const els = [...document.querySelectorAll(%s), ...document.querySelectorAll(%s)];
  const clipped = [];
  els.forEach((el) => {
    const r = el.getBoundingClientRect();
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const o = getComputedStyle(p).overflow + getComputedStyle(p).overflowX + getComputedStyle(p).overflowY;
      if (!/hidden|clip/.test(o)) continue;
      const q = p.getBoundingClientRect();
      if (r.right > q.right + 1 || r.left < q.left - 1) clipped.push(el.getAttribute('data-setting') || el.className);
    }
  });
  return {
    bottom: done ? done.getBoundingClientRect().bottom : null,
    innerHeight: window.innerHeight,
    scrollWidth: document.scrollingElement.scrollWidth,
    innerWidth: window.innerWidth,
    clipped,
  };
})()""" % (json.dumps(DONE), json.dumps(CELLS), json.dumps(TRAY_CELLS))

# The top of the Save bar when it shows, else null.
SAVE_TOP = """(() => {
  const bar = document.querySelector(%s);
  if (!bar || bar.hidden) return null;
  const r = bar.getBoundingClientRect();
  if (r.height === 0 || getComputedStyle(bar).display === 'none' || getComputedStyle(bar).visibility === 'hidden') return null;
  return r.top;
})()""" % json.dumps(SAVE_BAR)

# Whether a button's background computes to the card background, and that it is not transparent.
STEP_FILL = """(() => {
  const probe = document.createElement('div');
  probe.style.setProperty('background-color', 'var(--card-bg)');
  document.body.appendChild(probe);
  const card = getComputedStyle(probe).backgroundColor;
  probe.remove();
  const buttons = [...document.querySelectorAll(%s + ' [data-arrange^="up:"], ' + %s + ' [data-arrange^="down:"]')];
  const enabled = buttons.filter((b) => !b.disabled);
  return {
    card,
    count: enabled.length,
    wrong: enabled.map((b) => getComputedStyle(b).backgroundColor).filter((c) => c !== card),
  };
})()""" % (json.dumps(BAND), json.dumps(BAND))


def press_enter(page):
    """Enter on the focused element, the way a keyboard sends it. Page.key has no Enter, so this stays local."""
    page.call("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r")
    page.call("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)


def press_tab(page):
    page.call("Input.dispatchKeyEvent", type="keyDown", **TAB)
    page.call("Input.dispatchKeyEvent", type="keyUp", **TAB)


def mouse(page, kind, x, y):
    page.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left" if kind != "mouseMoved" else "none",
              buttons=0 if kind == "mouseReleased" else 1, clickCount=1 if kind != "mouseMoved" else 0)


def drag(page, start, end, steps=12):
    """A left-button drag from one point to another, in steps, the way a hand moves."""
    mouse(page, "mouseMoved", start[0], start[1])
    mouse(page, "mousePressed", start[0], start[1])
    for i in range(1, steps + 1):
        x = start[0] + (end[0] - start[0]) * i / steps
        y = start[1] + (end[1] - start[1]) * i / steps
        mouse(page, "mouseMoved", x, y)
    mouse(page, "mouseReleased", end[0], end[1])


@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the headless Chrome checks")
@unittest.skipIf(shell.CHROME is None, "Chrome was not found (set MR_CHROME to its path)")
class BandArrangeE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ts.make_root("mr-e2e-arrange-")
        cls.chrome = None
        cls.srv = None
        try:
            folder = os.path.join(cls.root, "set")
            pages.build_demo.build(folder)
            cls.srv = ts.start(cls.root, ["--fixture", folder])
            cls.base = "http://127.0.0.1:%d/" % cls.srv.port
            cls.chrome = shell.Chrome(helpers._tmp_base())
            cls.page = cls.chrome.page
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "chrome", None):
            cls.chrome.close()
        if getattr(cls, "srv", None):
            cls.srv.stop()
        if getattr(cls, "root", None):
            helpers.rmtree_force(cls.root)

    def setUp(self):
        # The browser keeps the saved order between tests, so one test's order must not reach the next.
        self.page.open(self.base + SETTINGS, 1440)
        self.page.eval("""(() => { try {
          Object.keys(localStorage).filter((k) => k.indexOf('band-order:') === 0).forEach((k) => localStorage.removeItem(k));
        } catch (e) {} })()""")

    # ------------------------------------------------------------ helpers

    def show(self, hash_=SETTINGS, width=1440, height=900, theme=None):
        """Open a route and wait until Settings has rendered its band."""
        if theme:
            hash_ = pages.add_query(hash_, "theme", theme)
        self.page.open(self.base + hash_, width, height)
        self.page.wait_for(pages.DATA_RENDERED + " === '1'")
        self.page.wait_for("JSON.stringify(%s) === %s" % (shell.VISIBLE, json.dumps(json.dumps(["settings"]))))
        self.page.wait_for("Boolean(document.querySelector(%s))" % json.dumps(BAND))
        if theme:
            self.page.wait_for("document.documentElement.getAttribute('data-theme') === %s" % json.dumps(theme))

    def q(self, selector):
        return self.page.eval("Boolean(document.querySelector(%s))" % json.dumps(selector))

    def count(self, selector):
        return self.page.eval("document.querySelectorAll(%s).length" % json.dumps(selector))

    def text(self, selector):
        return self.page.eval("(() => { const e = document.querySelector(%s); return e ? e.textContent.trim().replace(/\\s+/g, ' ') : null; })()"
                              % json.dumps(selector))

    def attr(self, selector, name):
        return self.page.eval("(() => { const e = document.querySelector(%s); return e ? e.getAttribute(%s) : null; })()"
                              % (json.dumps(selector), json.dumps(name)))

    def assert_focus(self, selector):
        expression = "Boolean(document.activeElement && document.activeElement.matches(%s))" % json.dumps(selector)
        try:
            self.page.wait_for(expression, timeout=5)
        except AssertionError:
            self.fail("focus is on %s, wanted %s" % (self.page.eval(DESCRIBE_ACTIVE), selector))

    def press_arrange(self):
        # A script click() never moves focus, and over 720px the press leaves focus on Arrange, so focus it and press
        # Enter as a keyboard user does.
        self.page.wait_for("Boolean(document.querySelector(%s))" % json.dumps(ARRANGE))
        self.page.eval("document.querySelector(%s).focus()" % json.dumps(ARRANGE))
        press_enter(self.page)
        self.page.wait_for("document.querySelector(%s).getAttribute('aria-pressed') === 'true'" % json.dumps(ARRANGE)
                           + " || Boolean(document.querySelector(%s))" % json.dumps(PHONE_LIST))

    def keys(self):
        return self.page.eval(KEYS)

    def whole_order(self):
        both = self.keys()
        return both["band"] + both["tray"]

    def reference_order(self):
        """Every setting in the saved order, read at 1440 wide with Arrange pressed, where all of them sit in the band."""
        self.show(SETTINGS, 1440, 640)
        self.press_arrange()
        order = self.whole_order()
        self.assertGreater(len(order), 3)
        self.assertEqual(len(set(order)), len(order))
        return order

    def stop_after_tab(self):
        press_tab(self.page)
        return self.page.eval(ACTIVE_STOP)

    # ------------------------------------------------------------ 1440 wide

    def test_arrange_at_1440_shows_every_setting_in_the_band_and_nothing_is_clipped(self):
        self.show(SETTINGS, 1440, 640)
        # At rest the band cells are links (a.s4-stat); they become div.s4-stat (CELLS) only once Arrange is pressed.
        resting = BAND + " > a.s4-stat[data-setting]"
        self.page.wait_for("document.querySelectorAll(%s).length > 3" % json.dumps(resting))
        normal = self.page.eval("[...document.querySelectorAll(%s)].map((e) => e.getAttribute('data-setting'))" % json.dumps(resting))
        self.press_arrange()
        self.assertEqual(self.attr(ARRANGE, "aria-pressed"), "true")
        self.assert_focus(ARRANGE.replace(PAGE + " ", ""))
        self.assertIn("s7-ed", self.attr(BAND, "class").split())
        keys = self.keys()
        self.assertEqual(keys["tray"], [])
        self.assertEqual(keys["band"], normal)
        self.assertEqual(len(set(keys["band"])), len(keys["band"]))
        self.assertTrue(self.q(TRAY))
        self.assertEqual(self.text(EMPTY), EMPTY_NOTE)
        self.assertFalse(self.q(FOLD))
        fit = self.page.eval(FIT)
        self.assertIsNotNone(fit["bottom"])
        self.assertLessEqual(fit["bottom"], fit["innerHeight"], fit)
        self.assertLessEqual(fit["scrollWidth"], fit["innerWidth"], fit)
        self.assertEqual(fit["clipped"], [])

    # ------------------------------------------------------------ 1100 wide

    def test_arrange_at_1100_shows_the_saved_order_the_fold_line_and_a_clear_done(self):
        reference = self.reference_order()
        self.show(SETTINGS + "?setting=availableModels", 1100, 700)
        self.press_arrange()
        keys = self.keys()
        self.assertEqual(keys["band"] + keys["tray"], reference)
        self.assertGreater(len(keys["band"]), 0)
        self.assertGreater(len(keys["tray"]), 0)
        # The open setting borrows no cell while arranging, so it sits where the saved order puts it.
        self.assertIn("availableModels", reference)
        self.assertIn("availableModels", keys["tray"])
        self.assertNotIn("availableModels", keys["band"])
        self.assertEqual(self.text(FOLD), FOLD_NOTE)
        self.assertFalse(self.q(EMPTY))
        self.assertEqual(self.attr(MORE, "aria-hidden"), "true")
        fit = self.page.eval(FIT)
        save_top = self.page.eval(SAVE_TOP)
        limit = save_top if save_top is not None else fit["innerHeight"]
        self.assertLessEqual(fit["bottom"], limit, (fit, save_top))
        self.assertLessEqual(fit["scrollWidth"], fit["innerWidth"], fit)

    def test_tab_walks_the_band_then_the_tray_then_reset_then_done(self):
        reference = self.reference_order()
        self.show(SETTINGS, 1100, 700)
        self.press_arrange()
        self.assert_focus(ARRANGE.replace(PAGE + " ", ""))
        expected = self.page.eval(EXPECTED_STOPS)
        # The walk the saved order gives: the first Earlier and the last Later are off, Reset is off at the default.
        walk = []
        for i, key in enumerate(reference):
            if i > 0:
                walk.append("up:" + key)
            if i < len(reference) - 1:
                walk.append("down:" + key)
        walk.append("done")
        self.assertEqual(expected, walk)
        seen = [self.stop_after_tab() for _ in expected]
        self.assertEqual(seen, expected)

    def test_later_on_the_last_band_cell_moves_it_under_more_and_earlier_brings_it_back(self):
        self.show(SETTINGS, 1100, 700)
        self.press_arrange()
        before = self.keys()
        self.assertGreater(len(before["tray"]), 0)
        total = len(before["band"]) + len(before["tray"])
        last = before["band"][-1]
        later = '[data-setting=%s] [data-arrange="down:%s"]' % (last, last)
        earlier = '[data-setting=%s] [data-arrange="up:%s"]' % (last, last)
        name = self.attr(later, "aria-label")
        self.assertTrue(name.startswith("Move ") and name.endswith(" later"), name)
        name = name[len("Move "):-len(" later")]
        # The first setting under More is the one the move raises into the band, and it is the one that drops again.
        neighbour = self.text(TRAY + " [data-setting=%s] .s4-sl" % before["tray"][0])
        self.assertTrue(neighbour)
        self.page.eval("document.querySelector(%s).focus()" % json.dumps(later))
        press_enter(self.page)
        self.page.wait_for("document.querySelector(%s).getAttribute('data-setting') === %s"
                           % (json.dumps(TRAY_CELLS), json.dumps(last)))
        after = self.keys()
        self.assertEqual(after["tray"][0], last)
        self.assertEqual(len(after["band"]) + len(after["tray"]), total)
        self.assert_focus(later)
        position = len(before["band"]) + 1
        self.page.wait_for("document.querySelector(%s) && document.querySelector(%s).textContent.trim() === %s" % (
            json.dumps(STATUS), json.dumps(STATUS),
            json.dumps("%s moved to position %d of %d. It is now under More settings. %s moved up from More settings."
                       % (name, position, total, neighbour))))
        # Earlier puts it back, and the line says so.
        self.page.eval("document.querySelector(%s).focus()" % json.dumps(earlier))
        press_enter(self.page)
        self.page.wait_for("document.querySelectorAll(%s)[%d] && document.querySelectorAll(%s)[%d].getAttribute('data-setting') === %s"
                           % (json.dumps(CELLS), len(before["band"]) - 1, json.dumps(CELLS), len(before["band"]) - 1, json.dumps(last)))
        self.assertEqual(self.keys(), before)
        self.assert_focus(earlier)
        self.page.wait_for("document.querySelector(%s).textContent.trim() === %s" % (
            json.dumps(STATUS),
            json.dumps("%s moved to position %d of %d. It is no longer under More settings. %s is now under More settings."
                       % (name, len(before["band"]), total, neighbour))))

    def test_escape_and_done_end_arranging_return_focus_and_the_open_setting_borrows_its_cell_again(self):
        self.show(SETTINGS + "?setting=availableModels", 1100, 700)
        borrowed = BAND + " a.s4-stat[data-setting=availableModels]"
        self.assertTrue(self.q(borrowed))
        # Escape.
        self.press_arrange()
        self.assertFalse(self.q(borrowed))
        self.page.key("Escape")
        self.page.wait_for("document.querySelector(%s).getAttribute('aria-pressed') === 'false'" % json.dumps(ARRANGE))
        self.assert_focus(ARRANGE.replace(PAGE + " ", ""))
        self.page.wait_for("Boolean(document.querySelector(%s))" % json.dumps(borrowed))
        self.assertFalse(self.q(TRAY))
        self.assertNotIn("s7-ed", self.attr(BAND, "class").split())
        # Done.
        self.press_arrange()
        self.assertFalse(self.q(borrowed))
        self.page.eval("document.querySelector(%s).focus()" % json.dumps(DONE))
        press_enter(self.page)
        self.page.wait_for("document.querySelector(%s).getAttribute('aria-pressed') === 'false'" % json.dumps(ARRANGE))
        self.assert_focus(ARRANGE.replace(PAGE + " ", ""))
        self.page.wait_for("Boolean(document.querySelector(%s))" % json.dumps(borrowed))
        self.assertEqual(self.attr(borrowed, "aria-current"), "true")

    def test_dragging_a_tray_setting_into_the_band_lands_at_the_slot_and_survives_a_reload(self):
        self.show(SETTINGS, 1100, 700)
        self.press_arrange()
        before = self.keys()
        self.assertGreaterEqual(len(before["band"]), 3)
        self.assertGreater(len(before["tray"]), 0)
        dragged = before["tray"][0]
        grip = TRAY + " [data-setting=%s] .s6-grip" % dragged
        point = self.page.eval("""(() => {
          const r = (el) => el.getBoundingClientRect();
          const grip = document.querySelector(%s);
          const cell = document.querySelectorAll(%s)[1];
          const g = r(grip), c = r(cell);
          return { from: [g.left + g.width / 2, g.top + g.height / 2], to: [c.left + 6, c.top + c.height / 2] };
        })()""" % (json.dumps(grip), json.dumps(CELLS)))
        drag(self.page, point["from"], point["to"])
        expected_band = [before["band"][0], dragged] + before["band"][1:-1]
        expected_tray = [before["band"][-1]] + before["tray"][1:]
        self.page.wait_for("document.querySelectorAll(%s)[1] && document.querySelectorAll(%s)[1].getAttribute('data-setting') === %s"
                           % (json.dumps(CELLS), json.dumps(CELLS), json.dumps(dragged)))
        after = self.keys()
        self.assertEqual(after["band"], expected_band)
        self.assertEqual(after["tray"], expected_tray)
        # The order is saved, so a fresh load shows it.
        self.show(SETTINGS, 1100, 700)
        self.press_arrange()
        self.assertEqual(self.keys(), after)

    # ------------------------------------------------------------ phone

    def test_phone_arrange_moves_focus_into_the_list_and_keeps_the_save_bar_clear(self):
        self.show(SETTINGS + "?setting=effortLevel", 375, 800)
        self.page.wait_for("Boolean(document.querySelector(%s))" % json.dumps(ARRANGE))
        self.page.eval("document.querySelector(%s).click()" % json.dumps(ARRANGE))
        self.page.wait_for("Boolean(document.querySelector(%s))" % json.dumps(PHONE_LIST))
        first = self.page.eval("(() => { const b = [...document.querySelectorAll(%s + ' [data-arrange^=\"up:\"], ' + %s + ' [data-arrange^=\"down:\"]')]"
                               ".find((x) => !x.disabled); return b ? b.getAttribute('data-arrange') : null; })()"
                               % (json.dumps(PHONE_ROWS), json.dumps(PHONE_ROWS)))
        self.assertIsNotNone(first)
        self.assert_focus('#settings-arrange [data-arrange="%s"]' % first)
        # The band still holds the open setting's cell and More.
        self.assertTrue(self.q(BAND + " [data-setting=effortLevel]"))
        self.assertTrue(self.q(MORE) or self.q(BAND + " .s5-more"))
        self.assertFalse(self.q(FOLD))
        self.assertEqual(self.count(PHONE_LIST + " .s6-fold"), 0)
        self.assertIn(PHONE_NOTE, self.page.eval("document.querySelector(%s).innerText.replace(/\\s+/g, ' ')" % json.dumps(PHONE_LIST)))
        sizes = self.page.eval("""[...document.querySelectorAll(%s + ' [data-arrange^="up:"], ' + %s + ' [data-arrange^="down:"]')]
          .map((b) => { const r = b.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })"""
                               % (json.dumps(PHONE_ROWS), json.dumps(PHONE_ROWS)))
        self.assertGreater(len(sizes), 0)
        for size in sizes:
            self.assertEqual(size, [44, 44])
        # Focus Done the way a keyboard user reaches it, so the browser's own focus scroll and the scroll margins place
        # it. Scrolling to the end of the page would leave Done far above the bar and test nothing.
        self.page.wait_for("Boolean(document.querySelector(%s))" % json.dumps(PHONE_LIST + " " + DONE))
        self.page.eval("window.scrollTo(0, 0)")
        self.page.eval("document.querySelector(%s).focus()" % json.dumps(PHONE_LIST + " " + DONE))
        bottom = self.page.eval("document.querySelector(%s).getBoundingClientRect().bottom" % json.dumps(PHONE_LIST + " " + DONE))
        save_top = self.page.eval(SAVE_TOP)
        if save_top is not None:
            self.assertGreaterEqual(save_top - bottom, 12, (bottom, save_top))
        else:
            self.assertLessEqual(bottom, self.page.eval("window.innerHeight"))
        fit = self.page.eval(FIT)
        self.assertLessEqual(fit["scrollWidth"], fit["innerWidth"], fit)

    # ------------------------------------------------------------ contrast

    def test_step_buttons_fill_with_the_card_background_in_both_themes(self):
        for theme in ("light", "dark"):
            self.show(SETTINGS, 1440, 640, theme=theme)
            self.press_arrange()
            fill = self.page.eval(STEP_FILL)
            self.assertGreater(fill["count"], 0, theme)
            self.assertNotIn(fill["card"], ("rgba(0, 0, 0, 0)", "transparent"), theme)
            self.assertEqual(fill["wrong"], [], "%s: step buttons should fill with %s" % (theme, fill["card"]))


if __name__ == "__main__":
    unittest.main()
