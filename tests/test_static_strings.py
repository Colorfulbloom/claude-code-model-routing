"""Checks for dashboard/static/strings.json and the t("key") calls in dashboard/static/js.

Reads only repo files. The copy deck has one key per line, sorted, and follows the owner's style
rules (no em dash, no colon in a prose string, month-first dates). Every literal key a page asks for
must exist. A key with no caller must be listed in tests/strings_pending.txt, which page tickets shrink.
"""
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATIC = REPO / "dashboard" / "static"
STRINGS = STATIC / "strings.json"
JS_DIR = STATIC / "js"
PENDING = Path(__file__).resolve().parent / "strings_pending.txt"

# Keys that code builds at run time, as t("status_" + status). Their members are never listed as
# unused, and the code may only build keys from these prefixes.
RUNTIME_PREFIXES = ("status_", "conf_", "layer_", "slot_", "f_action_")

# A string that breaks a style rule on purpose gets a named allowance with its reason. Empty today.
STYLE_ALLOWANCES = {
    # "key": ("rule", "reason"),
}

DAY_FIRST = re.compile(
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b")
NUMERIC_DATE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")
CALL = re.compile(r"\btn?\(\s*[\"']([A-Za-z0-9_]+)[\"']\s*([,)+]?)")


def strip_js_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(?m)^\s*//.*$", "", text)
    return re.sub(r"(?m)\s//\s.*$", "", text)


def js_files():
    return sorted(JS_DIR.rglob("*.js"))


def load_pairs():
    def pairs(items):
        keys = [k for k, _v in items]
        if len(keys) != len(set(keys)):
            raise AssertionError("strings.json repeats a key")
        return items
    with open(STRINGS, encoding="utf-8") as fh:
        return json.load(fh, object_pairs_hook=pairs)


def calls():
    """Return (exact literal keys, prefixes) found in the page code, with the file for each."""
    exact, prefixes = {}, {}
    for path in js_files():
        text = strip_js_comments(path.read_text(encoding="utf-8"))
        for key, after in CALL.findall(text):
            (prefixes if after == "+" else exact).setdefault(key, set()).add(path.name)
    return exact, prefixes


class StringsFile(unittest.TestCase):
    def test_keys_are_sorted_one_per_line(self):
        raw = STRINGS.read_text(encoding="utf-8")
        pairs = load_pairs()
        keys = [k for k, _v in pairs]
        self.assertEqual(keys, sorted(keys), "keys must be sorted")
        lines = raw.rstrip("\n").split("\n")
        self.assertEqual(lines[0], "{")
        self.assertEqual(lines[-1], "}")
        self.assertEqual(len(lines) - 2, len(keys), "one key per line")
        for line in lines[1:-1]:
            self.assertRegex(line, r'^  "[a-z0-9_]+": ".*"(,)?$', line)
        self.assertTrue(raw.endswith("}\n"))

    def test_every_value_is_text(self):
        for key, value in load_pairs():
            self.assertIsInstance(value, str, key)
            self.assertTrue(value.strip(), key)

    def test_style_rules(self):
        problems = []
        for key, value in load_pairs():
            found = []
            if "—" in value:
                found.append(("em dash", value))
            if ":" in value:
                found.append(("colon", value))
            if DAY_FIRST.search(value) or NUMERIC_DATE.search(value):
                found.append(("date not month first", value))
            for rule, text in found:
                allowed = STYLE_ALLOWANCES.get(key)
                if allowed is None or allowed[0] != rule:
                    problems.append("%s: %s in %r" % (key, rule, text))
        self.assertEqual(problems, [])

    def test_allowances_are_still_needed(self):
        pairs = dict(load_pairs())
        for key, (rule, reason) in STYLE_ALLOWANCES.items():
            self.assertIn(key, pairs)
            self.assertTrue(reason.strip())
            value = pairs[key]
            hit = {"em dash": "—" in value, "colon": ":" in value,
                   "date not month first": bool(DAY_FIRST.search(value) or NUMERIC_DATE.search(value))}
            self.assertTrue(hit.get(rule), "%s no longer needs its %s allowance" % (key, rule))


class StringCalls(unittest.TestCase):
    def test_every_literal_key_exists(self):
        known = dict(load_pairs())
        exact, _prefixes = calls()
        missing = {k: sorted(v) for k, v in exact.items() if k not in known}
        self.assertEqual(missing, {}, "t() asks for keys that strings.json does not have")

    def test_built_keys_use_known_prefixes(self):
        known = dict(load_pairs())
        _exact, prefixes = calls()
        for prefix, files in prefixes.items():
            self.assertIn(prefix, RUNTIME_PREFIXES, "%s builds keys from %s" % (sorted(files), prefix))
            self.assertTrue([k for k in known if k.startswith(prefix)], prefix)

    def test_every_key_is_used_or_pending(self):
        # Pages are stubs until their tickets land, so a key with no caller yet goes in
        # tests/strings_pending.txt. A page ticket deletes the lines it starts using.
        known = [k for k, _v in load_pairs()]
        exact, _prefixes = calls()
        pending = pending_keys()
        by_prefix = [k for k in known if k.startswith(RUNTIME_PREFIXES)]
        unused = [k for k in known if k not in exact and k not in by_prefix]
        self.assertEqual([k for k in unused if k not in pending], [], "unused and not in strings_pending.txt")
        self.assertEqual([k for k in pending if k in exact], [], "in strings_pending.txt but now used")
        self.assertEqual([k for k in pending if k in by_prefix], [], "run-time prefix keys never go in the pending list")
        self.assertEqual([k for k in pending if k not in known], [], "pending key is not in strings.json")

    def test_pending_file_is_sorted_one_per_line(self):
        text = PENDING.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n") or text == "")
        keys = text.split("\n")[:-1] if text else []
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(keys), len(set(keys)))
        for key in keys:
            self.assertRegex(key, r"^[a-z0-9_]+$")


def pending_keys():
    text = PENDING.read_text(encoding="utf-8")
    return [k for k in text.split("\n") if k]


if __name__ == "__main__":
    unittest.main()
