"""End-to-end checks of the Settings page and the trail in headless Chrome. Opt in with MR_E2E=1.

Built on test_shell_e2e (its Chrome and Page) and on test_pages_e2e (its helpers and the demo set). The server
runs with --fixture on the made-up demo set, so nothing reads the real ~/.claude. The sweep in test_pages_e2e
checks that the words show. These tests check what the sweep cannot: focus and keys, links, the shape of a few
values, and text contrast on both themes.

The module-level scripts are pure, and importing this module starts nothing, so tests/test_e2e_checks.py can
check them with no browser.

Demo facts these tests rely on (tests/fixtures/demo, read through the page):
- tidewater-reporting is the default project. Its effort is xhigh, Lowered, runs as high, from the env block of
  projects/tidewater-reporting/.claude/settings.local.json, line 3. Two other values didn't count.
- builder runs on Fable 5.1, not the main model, so its effort row shows no Effort cap line.
- #/settings/builder/autoCompactWindow and #/settings/@main/maxEffortLevel?project=saltmarsh hold Assumed rules.
"""
import json
import os
import unittest

import helpers
import test_pages_e2e as pages
import test_server as ts
import test_shell_e2e as shell

SETTINGS = "#/settings"
EFFORT_TRAIL = "#/settings/@main/effortLevel"
BUILDER_EFFORT = "#/settings/builder/effort"
COMPACT_TRAIL = "#/settings/builder/autoCompactWindow"
CAP_TRAIL = "#/settings/@main/maxEffortLevel?project=saltmarsh"
EFFORT_SOURCE = "projects/tidewater-reporting/.claude/settings.local.json, line 3"
RULES_REFERENCE = "https://github.com/Colorfulbloom/claude-code-model-routing/blob/main/docs/rules-reference.md#"
EFFORT_TILE = "[data-page=settings] a.tl[data-setting=effortLevel]"

# The pieces both contrast scripts share. They take the one section that is not hidden. A color that is not
# rgb() or rgba() cannot be read, so it comes back as a bad item with its value, and nothing passes silently.
# Backgrounds are read from the element up, until one is opaque. Gradients and images are not part of it, and
# neither is opacity, because no text on these two pages sits on one.
CONTRAST_HELPERS = r"""
  const section = [...document.querySelectorAll('main [data-page]')].find((s) => !s.hidden);
  const parseColor = (value) => {
    const m = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,\/]+([\d.]+%?))?\s*\)$/.exec(String(value).trim());
    if (!m) return null;
    const alpha = m[4] === undefined ? 1 : (m[4].endsWith('%') ? parseFloat(m[4]) / 100 : parseFloat(m[4]));
    return { r: parseFloat(m[1]), g: parseFloat(m[2]), b: parseFloat(m[3]), a: alpha };
  };
  const over = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1,
  });
  const css = (c) => 'rgb(' + [c.r, c.g, c.b].map((v) => Math.round(v)).join(', ') + ')';
  const backdrop = (el) => {
    const layers = [];
    for (let node = el; node; node = node.parentElement) {
      const raw = getComputedStyle(node).backgroundColor;
      const c = parseColor(raw);
      if (!c) return { error: raw };
      if (c.a > 0) layers.push(c);
      if (c.a >= 1) break;
    }
    let color = { r: 255, g: 255, b: 255, a: 1 };
    for (let i = layers.length - 1; i >= 0; i--) color = over(layers[i], color);
    return { color };
  };
  const luminance = (c) => {
    const lin = (v) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4); };
    return 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  };
  const ratioOf = (a, b) => {
    const x = luminance(a);
    const y = luminance(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  };
  const measure = (el) => {
    const fg = parseColor(getComputedStyle(el).color);
    if (!fg) return { error: getComputedStyle(el).color };
    const back = backdrop(el);
    if (back.error !== undefined) return { error: back.error };
    const color = over(fg, back.color);
    return { ratio: ratioOf(color, back.color), fg: css(color), bg: css(back.color) };
  };
  const labelOf = (el) => {
    const classes = String(el.getAttribute('class') || '').split(/\s+/).filter(Boolean).slice(0, 2);
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.data).join(' ').trim().replace(/\s+/g, ' ');
    return el.tagName.toLowerCase() + classes.map((c) => '.' + c).join('') + ' "' + own.slice(0, 30) + '"';
  };
  const report = (el, min, bad) => {
    const m = measure(el);
    const label = labelOf(el);
    if (m.error !== undefined) { bad.push('unreadable color ' + JSON.stringify(m.error) + ': ' + label); return; }
    if (m.ratio < min) bad.push(label + ' ' + m.ratio.toFixed(2) + ':1, needs ' + min + ', ' + m.fg + ' on ' + m.bg);
  };
"""

# Every visible element in the shown section that holds its own text, skipping .sr. WCAG 1.4.3: 4.5, or 3 for
# large text (24px and up, or 18.66px and up in bold). Returns { checked, bad }.
TEXT_CONTRAST_BAD = "(() => {" + CONTRAST_HELPERS + r"""
  if (!section) return { checked: 0, bad: ['no visible section'] };
  const minFor = (el) => {
    const style = getComputedStyle(el);
    const px = parseFloat(style.fontSize);
    const weight = parseInt(style.fontWeight, 10) || 400;
    return px >= 24 || (px >= 18.66 && weight >= 700) ? 3 : 4.5;
  };
  const bad = [];
  let checked = 0;
  section.querySelectorAll('*').forEach((el) => {
    if (el.closest('.sr')) return;
    if (![...el.childNodes].some((n) => n.nodeType === 3 && n.data.trim() !== '')) return;
    if (getComputedStyle(el).visibility === 'hidden' || el.getClientRects().length === 0) return;
    checked += 1;
    report(el, minFor(el), bad);
  });
  return { checked, bad };
})()"""

# The Assumed badge and its definition line: the badge is dashed, both exist, and both reach 4.5. Reads computed
# style only, so it works while the Rules card is closed. Returns { badges, defs, dashed, bad }.
ASSUMED_CHECK = "(() => {" + CONTRAST_HELPERS + r"""
  if (!section) return { badges: 0, defs: 0, dashed: false, bad: ['no visible section'] };
  const bad = [];
  const badges = [...section.querySelectorAll('.cf-assumed')];
  const defs = [...section.querySelectorAll('.ru-def')];
  const dashed = badges.length > 0 && badges.every((el) => {
    const s = getComputedStyle(el);
    return [s.borderTopStyle, s.borderRightStyle, s.borderBottomStyle, s.borderLeftStyle].every((v) => v === 'dashed');
  });
  badges.forEach((el) => report(el, 4.5, bad));
  defs.forEach((el) => report(el, 4.5, bad));
  return { badges: badges.length, defs: defs.length, dashed, bad };
})()"""

OPEN_DETAILS = "document.querySelectorAll('main [data-page] details').forEach((d) => { d.open = true; })"
DESCRIBE_ACTIVE = """(() => {
  const a = document.activeElement;
  if (!a) return 'nothing';
  return a.tagName.toLowerCase() + (a.getAttribute('class') ? '.' + a.getAttribute('class').split(' ').join('.') : '');
})()"""


def press_enter(page):
    """Enter on the focused element, the way a keyboard sends it. Page.key has no Enter, so this stays local."""
    page.call("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r")
    page.call("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)


@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the headless Chrome checks")
@unittest.skipIf(shell.CHROME is None, "Chrome was not found (set MR_CHROME to its path)")
class SettingsE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ts.make_root("mr-e2e-settings-")
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

    # ------------------------------------------------------------ helpers

    def wait_visible(self, section):
        self.page.wait_for("JSON.stringify(%s) === %s" % (shell.VISIBLE, json.dumps(json.dumps([section]))))

    def show(self, hash_, section, theme=None, width=1440):
        """Open a route, then wait until the page has rendered and only `section` is shown."""
        if theme:
            hash_ = pages.add_query(hash_, "theme", theme)
        self.page.open(self.base + hash_, width)
        self.page.wait_for(pages.DATA_RENDERED + " === '1'")
        self.wait_visible(section)
        if theme:
            self.page.wait_for("document.documentElement.getAttribute('data-theme') === %s" % json.dumps(theme))

    def assert_focus(self, selector):
        """The focused element matches the selector. Focus moves in the same render, so it waits a little."""
        expression = "Boolean(document.activeElement && document.activeElement.matches(%s))" % json.dumps(selector)
        try:
            self.page.wait_for(expression, timeout=5)
        except AssertionError:
            self.fail("focus is on %s, wanted %s" % (self.page.eval(DESCRIBE_ACTIVE), selector))

    def texts_of(self, selector):
        return self.page.eval("[...document.querySelectorAll(%s)].map((e) => e.textContent.trim())" % json.dumps(selector))

    def exceptions_since(self, before):
        self.page.drain()
        return [m for m in self.page.messages()[before:] if m.startswith("EXCEPTION")]

    # ------------------------------------------------------------ focus and keys

    def test_click_opens_the_trail_and_escape_returns_to_the_tile(self):
        self.show(SETTINGS, "settings")
        self.page.wait_for("Boolean(document.querySelector(%s))" % json.dumps(EFFORT_TILE))
        self.page.eval("document.querySelector(%s).click()" % json.dumps(EFFORT_TILE))
        self.wait_visible("trail")
        self.assert_focus("h2.tr-title")
        self.page.key("Escape")
        self.wait_visible("settings")
        self.assert_focus("a.tl[data-setting=effortLevel]")

    def test_enter_on_a_tile_opens_the_trail(self):
        self.show(SETTINGS, "settings")
        self.page.wait_for("Boolean(document.querySelector(%s))" % json.dumps(EFFORT_TILE))
        self.page.eval("document.querySelector(%s).focus()" % json.dumps(EFFORT_TILE))
        self.assert_focus("a.tl[data-setting=effortLevel]")
        press_enter(self.page)
        self.wait_visible("trail")
        self.assert_focus("h2.tr-title")

    def test_escape_on_a_row_with_no_card_returns_to_the_heading(self):
        self.show(BUILDER_EFFORT, "trail")
        self.assert_focus("h2.tr-title")
        self.page.key("Escape")
        self.wait_visible("settings")
        self.assert_focus("[data-page=settings] h1")

    # ------------------------------------------------------------ routes with nothing to show

    def test_a_row_that_does_not_exist_shows_no_panel(self):
        before = len(self.page.messages())
        self.show("#/settings/nobody/effort", "trail")
        self.page.wait_for("document.querySelectorAll('[data-page=trail] a.tl').length === 4")
        self.assertIsNone(self.page.eval("document.getElementById('trail') && document.getElementById('trail').id"))
        line = self.page.eval("document.querySelector('[data-page=trail] p.foot').innerText")
        self.assertEqual(line, "This project has no effort for nobody, so there's no trail to show.")
        self.assertEqual(self.exceptions_since(before), [])

    def test_all_projects_on_a_trail_route_shows_the_picker(self):
        before = len(self.page.messages())
        self.show(EFFORT_TRAIL + "?project=all", "trail")
        shown = self.page.eval("document.querySelector('main [data-page=trail]').innerText")
        self.assertIn("Pick a project", shown)
        self.assertEqual(self.page.eval("document.querySelectorAll('[data-page=trail] a.tl').length"), 0)
        self.assertIsNone(self.page.eval("document.getElementById('trail') && document.getElementById('trail').id"))
        self.assertEqual(self.exceptions_since(before), [])

    # ------------------------------------------------------------ the fixes after the Chrome pass

    def test_the_fixes_after_the_chrome_pass(self):
        self.show(SETTINGS, "settings")
        self.page.wait_for("Boolean(document.querySelector(%s))" % json.dumps(EFFORT_TILE))
        self.assertEqual(self.texts_of(EFFORT_TILE + " .tl-src"), [EFFORT_SOURCE])

        self.show(EFFORT_TRAIL, "trail")
        self.page.wait_for("Boolean(document.getElementById('trail'))")
        self.assertEqual(self.texts_of("#trail .win .ly"), ["Local settings"])
        winner = self.page.eval("document.querySelector('#trail .win').closest('details').querySelector(':scope > summary .cd-sum').textContent")
        self.assertEqual(winner, "xhigh Lowered, " + EFFORT_SOURCE)
        others = self.page.eval("document.querySelector('#trail .ens-a').closest('details').querySelector(':scope > summary .cd-sum').textContent")
        self.assertEqual(others, "2 values, 2 didn't count")
        self.assertIn("Effort cap", self.texts_of("#trail dt"))

        self.show(BUILDER_EFFORT, "trail")
        self.page.wait_for("Boolean(document.getElementById('trail'))")
        terms = self.texts_of("#trail dt")
        self.assertIn("Model", terms)  # the meta block is there, so the missing cap line means something
        self.assertNotIn("Effort cap", terms)

    def test_a_lowered_agent_row_on_needs_attention_opens_that_rows_trail(self):
        self.show("#/attention", "attention")
        row = ("[...document.querySelectorAll('[data-page=attention] section.cd')]"
               ".find((c) => c.querySelector('.cd-h').textContent === 'Lowered')"
               ".querySelectorAll('ul.at li a')")
        self.page.wait_for("Boolean(%s.length)" % row)
        names = self.page.eval("[...%s].map((a) => a.querySelector('.at-n').textContent)" % row)
        self.assertIn("builder, Effort", names)
        self.page.eval("[...%s].find((a) => a.querySelector('.at-n').textContent === 'builder, Effort').click()" % row)
        self.wait_visible("trail")
        self.page.wait_for("Boolean(document.querySelector('h2.tr-title'))")
        self.assertEqual(self.texts_of("[data-page=trail] h2.tr-title"), ["What decides the effort for builder"])
        self.assertEqual(self.page.eval("location.hash.split('?')[0]"), "#/settings/builder/effort")

    def test_a_rule_checked_before_the_installed_version_is_due_for_a_new_check(self):
        # The Rules card is closed, so its text is not in the sweep's innerText. Open it, then read it.
        self.show(EFFORT_TRAIL, "trail")
        self.page.wait_for("Boolean(document.getElementById('trail'))")
        self.page.eval("[...document.querySelectorAll('#trail details.cd')]"
                       ".filter((d) => d.querySelector('h3').textContent === 'Rules behind this value')"
                       ".forEach((d) => { d.open = true; })")
        lines = self.texts_of("#trail .ru-ck")
        self.assertGreater(len(lines), 0, "the trail shows no checked line")
        for line in lines:
            self.assertIn("You have 2.1.310, so this rule is due for a new check.", line)

    def test_typing_in_the_rules_search_narrows_the_list_and_keeps_focus(self):
        items = json.dumps("[data-page=rules] ul.rules > li")
        box = json.dumps("[data-page=rules] .search input")
        self.show("#/rules", "rules")
        self.page.wait_for("document.querySelectorAll(%s).length > 20" % items)
        total = self.page.eval("document.querySelectorAll(%s).length" % items)
        self.page.eval("document.querySelector(%s).focus()" % box)
        self.assert_focus("[data-page=rules] .search input")
        self.page.call("Input.insertText", text="winning source")  # a real input event, as typing sends
        self.page.wait_for("document.querySelectorAll(%s).length < %d" % (items, total))
        shown = self.page.eval("document.querySelectorAll(%s).length" % items)
        self.assertGreater(shown, 0)
        self.assertLess(shown, total)
        self.assert_focus("[data-page=rules] .search input")
        self.assertEqual(self.page.eval("document.querySelector(%s).value" % box), "winning source")
        self.assertEqual(self.texts_of("[data-page=rules] .cd-sub"), ["%d of %d rules shown." % (shown, total)])
        for reason in self.texts_of("[data-page=rules] ul.rules > li .ru-rs"):
            self.assertIn("winning source", reason.lower())

    def test_each_file_state_on_installed_files_shows_a_mark_and_a_word(self):
        self.show("#/files", "files")
        cells = ("[...document.querySelectorAll('[data-page=files] tbody .st')].map((el) => ({"
                 "cls: el.className, word: el.textContent.trim(), "
                 "mark: getComputedStyle(el.querySelector(':scope > .mk'), '::before').content}))")
        self.page.wait_for("(%s).length === 6" % cells)
        found = self.page.eval(cells)
        words = {}
        for cell in found:
            self.assertNotIn(cell["mark"], ("none", "normal", '""', "''", ""), cell)
            self.assertTrue(cell["word"], cell)
            words.setdefault(cell["word"], set()).add((cell["cls"], cell["mark"]))
        self.assertEqual(sorted(words), ["Differs", "Matches", "Missing"])
        self.assertEqual({w: len(v) for w, v in words.items()}, {"Differs": 1, "Matches": 1, "Missing": 1})
        self.assertEqual(sorted(c["word"] for c in found), ["Differs", "Matches", "Matches", "Matches", "Matches", "Missing"])
        # Stack's final rule gives Differs and Missing the same cross and invalid pair, so the word tells them apart.
        marks = {word: next(iter(v))[1] for word, v in words.items()}
        self.assertEqual(marks, {"Differs": '"✕"', "Matches": '"✓"', "Missing": '"✕"'})

    def test_a_long_row_name_at_375_stays_clear_of_its_value_and_chip(self):
        clash = """[...document.querySelectorAll('main [data-page=%s] .at li a')].filter((a) => {
          const n = document.createRange();
          n.selectNodeContents(a.querySelector('.at-n'));
          return n.getBoundingClientRect().right > a.querySelector('.at-m').getBoundingClientRect().left + 0.5;
        }).map((a) => a.querySelector('.at-n').textContent)"""
        for route, section in (("#/attention", "attention"), ("#/overview", "overview")):
            self.show(route, section, width=375)
            self.page.wait_for("document.querySelectorAll('main [data-page=%s] .at li a').length > 0" % section)
            self.assertEqual(self.page.eval(clash % section), [], section)

    def test_the_cache_tile_shows_one_short_line_and_the_trail_keeps_the_reason(self):
        self.show("#/settings", "settings")
        tile = "[data-page=settings] a.tl[data-setting=promptCacheTtl]"
        self.page.wait_for("Boolean(document.querySelector(%s))" % json.dumps(tile + " .en-note"))
        self.assertEqual(self.texts_of(tile + " .en-note"), ["Open the trail to see why."])
        self.page.eval("document.querySelector(%s).click()" % json.dumps(tile))
        self.wait_visible("trail")
        reason = "[data-page=trail] .en-rs"
        self.page.wait_for("[...document.querySelectorAll(%s)].some((p) => p.textContent.includes('so the plan decides it'))"
                           % json.dumps(reason))

    def test_external_links_carry_their_guards(self):
        self.show(EFFORT_TRAIL, "trail")
        self.page.wait_for("Boolean(document.getElementById('trail'))")
        links = self.page.eval("""[...document.querySelectorAll('#trail a.ru-id')].map((a) => ({
          id: a.textContent, href: a.getAttribute('href'), target: a.getAttribute('target'), rel: a.getAttribute('rel') }))""")
        self.assertGreater(len(links), 0, "the trail shows no rule links")
        for link in links:
            self.assertTrue((link["href"] or "").startswith(RULES_REFERENCE), link)
            self.assertEqual(link["target"], "_blank", link)
            self.assertEqual(link["rel"], "noopener noreferrer", link)

    # ------------------------------------------------------------ the Assumed badge and text contrast

    def test_assumed_reads_differently_and_meets_aa(self):
        for theme in pages.THEMES:
            for hash_ in (COMPACT_TRAIL, CAP_TRAIL):
                with self.subTest(route=hash_, theme=theme):
                    self.show(hash_, "trail", theme=theme)
                    self.page.wait_for("Boolean(document.getElementById('trail'))")
                    found = self.page.eval(ASSUMED_CHECK)
                    self.assertGreater(found["badges"], 0, "no .cf-assumed badge")
                    self.assertGreater(found["defs"], 0, "no .ru-def line")
                    self.assertTrue(found["dashed"], "an Assumed badge is not dashed on all four sides")
                    self.assertEqual(found["bad"], [])

    def test_settings_text_meets_aa(self):
        # The settings page holds about 18 text elements, so its floor is lower than the trail's.
        failures = []
        for theme in pages.THEMES:
            for hash_, section, floor in ((SETTINGS, "settings", 10), (EFFORT_TRAIL, "trail", 20)):
                where = "%s %s" % (hash_, theme)
                self.show(hash_, section, theme=theme)
                if section == "trail":
                    self.page.wait_for("Boolean(document.getElementById('trail'))")
                else:
                    self.page.wait_for("Boolean(document.querySelector(%s))" % json.dumps(EFFORT_TILE))
                self.page.eval(OPEN_DETAILS)
                result = self.page.eval(TEXT_CONTRAST_BAD)
                if result["checked"] <= floor:
                    failures.append("%s: checked only %d elements, wanted more than %d" % (where, result["checked"], floor))
                failures += ["%s: %s" % (where, item) for item in result["bad"]]
        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
