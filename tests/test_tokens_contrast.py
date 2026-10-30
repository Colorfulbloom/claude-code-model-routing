"""Contrast checks for dashboard/static/tokens.css.

Reads only the repo's token sheet. Parses the three theme blocks, resolves var() aliases
(dark falls back to the light :root for anything a dark block does not set), and measures
WCAG 2.1 relative luminance contrast. Token values are never hardcoded here, except the
owner-accepted exception numbers, which are pinned on purpose.
"""
import re
import unittest
from pathlib import Path

TOKENS = Path(__file__).resolve().parent.parent / "dashboard" / "static" / "tokens.css"

NEW_TOKENS = [
    "page-bg", "card-bg", "sidebar-bg", "nav-active-bg", "nav-hover-bg", "shadow-card",
    "chart-track", "chart-gap",
    "cat-1", "cat-2", "cat-3", "cat-4", "rk-1", "rk-2", "rk-3", "rk-4",
    "chart-grid", "chart-axis",
]
STATUSES = ["in-effect", "overridden", "ignored", "invalid", "lowered", "default", "unknown"]

# Accepted by the owner (light only, on --card-bg), on two conditions: legend totals or a kinds
# table on every stacked bar, and a visible start edge.
RAMP_LIGHT_EXCEPTION = {"rk-1": 1.54, "rk-2": 2.50}


def _strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _decls(body):
    return {k: v.strip() for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body)}


def _block(css, opener):
    start = css.index(opener)
    depth, i = 0, css.index("{", start)
    begin = i + 1
    while True:
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[begin:i]
        i += 1


def load():
    raw = TOKENS.read_text(encoding="utf-8")
    css = _strip_comments(raw)
    light = _decls(_block(css, ":root {"))
    dark_media = _decls(_block(css, ':root:not([data-theme="light"])'))
    dark_attr = _decls(_block(css, ':root[data-theme="dark"]'))
    return raw, light, dark_media, dark_attr


def resolve(name, own, light):
    seen = set()
    value = own.get(name, light.get(name))
    while value is not None and value.startswith("var("):
        ref = value[4:-1].strip()
        if ref in seen:
            raise ValueError("alias loop at " + ref)
        seen.add(ref)
        value = own.get(ref, light.get(ref))
    return value


def luminance(hex_color):
    h = hex_color.lstrip("#")
    chans = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    chans = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in chans]
    return 0.2126 * chans[0] + 0.7152 * chans[1] + 0.0722 * chans[2]


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class TokensContrast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.light, cls.dark_media, cls.dark_attr = load()
        cls.themes = {
            "light": (cls.light, cls.light),
            "dark": (cls.dark_attr, cls.light),
        }

    def c(self, theme, fg, bg):
        own, light = self.themes[theme]
        return contrast(resolve("--" + fg, own, light), resolve("--" + bg, own, light))

    def val(self, theme, name):
        own, light = self.themes[theme]
        return resolve("--" + name, own, light)

    # Structure

    def test_dark_blocks_identical(self):
        self.assertEqual(self.dark_media, self.dark_attr)

    def test_new_tokens_in_all_three_blocks(self):
        for block_name, block in (("light", self.light), ("dark media", self.dark_media),
                                  ("dark attr", self.dark_attr)):
            for t in NEW_TOKENS:
                self.assertIn("--" + t, block, f"{t} missing from {block_name} block")

    def test_chart_aliases_add_no_pairs(self):
        for block in (self.light, self.dark_media, self.dark_attr):
            for t in ("chart-grid", "chart-axis"):
                self.assertTrue(block["--" + t].startswith("var("), t)

    # Text pairs

    def test_text_pairs_reach_4_5(self):
        for theme in self.themes:
            for fg in ("text", "text-muted"):
                for bg in ("page-bg", "card-bg", "sidebar-bg", "nav-hover-bg"):
                    self.assertGreaterEqual(self.c(theme, fg, bg), 4.5, f"{theme} {fg} on {bg}")
            for fg in ("text", "accent"):
                self.assertGreaterEqual(self.c(theme, fg, "nav-active-bg"), 4.5,
                                        f"{theme} {fg} on nav-active-bg")
            for s in STATUSES:
                self.assertGreaterEqual(self.c(theme, f"status-{s}-fg", f"status-{s}-bg"), 4.5,
                                        f"{theme} status {s}")

    # Series colors

    def test_cat_on_card(self):
        for theme in self.themes:
            for i in range(1, 5):
                self.assertGreaterEqual(self.c(theme, f"cat-{i}", "card-bg"), 3, f"{theme} cat-{i}")

    # Ramp

    def test_ramp_on_card(self):
        for theme in self.themes:
            for i in (3, 4):
                self.assertGreaterEqual(self.c(theme, f"rk-{i}", "card-bg"), 3, f"{theme} rk-{i}")
        for i in (1, 2):
            self.assertGreaterEqual(self.c("dark", f"rk-{i}", "card-bg"), 3, f"dark rk-{i}")

    def test_ramp_light_exception_pinned(self):
        for name, expected in RAMP_LIGHT_EXCEPTION.items():
            measured = self.c("light", name, "card-bg")
            self.assertLess(measured, 3, name)
            self.assertEqual(round(measured, 2), expected, name)

    def test_ramp_monotonic(self):
        for theme, direction in (("light", -1), ("dark", 1)):
            lums = [luminance(self.val(theme, f"rk-{i}")) for i in range(1, 5)]
            for a, b in zip(lums, lums[1:]):
                self.assertGreater((b - a) * direction, 0, f"{theme} ramp not monotonic")

    # Start edge condition

    def test_border_strong_start_edge(self):
        for theme in self.themes:
            for bg in ("card-bg", "page-bg"):
                self.assertGreaterEqual(self.c(theme, "border-strong", bg), 3,
                                        f"{theme} border-strong on {bg}")

    # Header numbers

    def header_rows(self):
        """Map (theme, label) to the number printed in the header comment."""
        comment = re.match(r"\s*/\*(.*?)\*/", self.raw, re.S).group(1)
        rows = {}
        cell = re.compile(r"(\S[^\n]*?)\s+(\d+\.\d\d)\s+(?:pass\*?|n/a|below 3|FAIL)")
        for line in comment.split("\n"):
            for idx, m in enumerate(cell.finditer(line)):
                theme = ("light", "dark")[idx]
                rows[(theme, m.group(1).strip())] = float(m.group(2))
        return rows

    def token_for(self, label_part):
        m = re.fullmatch(r"([\w-]+) fg", label_part)
        if m:
            return f"status-{m.group(1)}-fg"
        return label_part

    def test_header_numbers_match_computed(self):
        rows = self.header_rows()
        self.assertGreaterEqual(len(rows), 2 * (19 + 22))
        checked = 0
        for (theme, label), printed in rows.items():
            m = re.fullmatch(r"([\w-]+(?: fg)?) on (its bg|[\w-]+)", label)
            self.assertIsNotNone(m, f"unparsed header label {label!r}")
            fg_label, bg_label = m.groups()
            fg = self.token_for(fg_label)
            bg = f"{fg[:-3]}-bg" if bg_label == "its bg" else bg_label
            measured = self.c(theme, fg, bg)
            self.assertEqual(round(measured, 2), printed, f"{theme} {label}: header {printed}, computed {measured:.4f}")
            checked += 1
        self.assertEqual(checked, len(rows))


if __name__ == "__main__":
    unittest.main()
