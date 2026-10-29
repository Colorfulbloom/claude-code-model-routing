"""Tests for dashboard/agent_frontmatter.py and dashboard/agent_fields.json.

These tests use made-up text and the repo's own files. They never read
~/.claude or any other project.
"""
import copy
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
import contextlib

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import agent_frontmatter as af  # noqa: E402

DOCS_COPY = os.environ.get("MR_SUBAGENT_DOCS")  # optional path to a saved sub-agents.md
SCRIPT = os.path.join(helpers.REPO, "dashboard", "agent_frontmatter.py")


def doc(*lines):
    return "\n".join(("---",) + lines + ("---", "Body text.", ""))


class AcceptedShapesTest(unittest.TestCase):
    def ok(self, *lines):
        fields, errors = af.read_frontmatter(doc(*lines))
        self.assertEqual(errors, [])
        return fields

    def test_plain_values(self):
        f = self.ok("name: probe", "description: Made-up agent.", "model: sonnet")
        self.assertEqual(f, {"name": "probe", "description": "Made-up agent.", "model": "sonnet"})

    def test_double_quoted_description_with_colon_and_comma(self):
        f = self.ok('description: "Lead: plans, dispatches, verifies."')
        self.assertEqual(f["description"], "Lead: plans, dispatches, verifies.")

    def test_double_quote_escapes(self):
        f = self.ok(r'description: "say \"hi\" and use a \\ slash"')
        self.assertEqual(f["description"], 'say "hi" and use a \\ slash')

    def test_single_quoted_value_and_doubled_quote(self):
        f = self.ok("description: 'it''s: fine'")
        self.assertEqual(f["description"], "it's: fine")

    def test_comma_separated_tools_stay_a_string(self):
        f = self.ok("tools: Read, Glob, Grep, Bash")
        self.assertEqual(f["tools"], "Read, Glob, Grep, Bash")

    def test_flow_list(self):
        f = self.ok("tools: [Read, Grep, 'Bash']", 'skills: ["a:b", c]', "hooks: []")
        self.assertEqual(f["tools"], ["Read", "Grep", "Bash"])
        self.assertEqual(f["skills"], ["a:b", "c"])
        self.assertEqual(f["hooks"], [])

    def test_flow_list_item_with_a_comma_inside_quotes(self):
        f = self.ok('tools: ["a, b", c]')
        self.assertEqual(f["tools"], ["a, b", "c"])

    def test_block_list_with_quoted_items(self):
        f = self.ok("skills:", '  - "design:design-system"', "  - 'design:design-critique'",
                    "  - plain-item")
        self.assertEqual(f["skills"],
                         ["design:design-system", "design:design-critique", "plain-item"])

    def test_nested_map(self):
        f = self.ok("experimental:", "  cacheTtl: 1h")
        self.assertEqual(f["experimental"], {"cacheTtl": "1h"})

    def test_blank_and_comment_lines_are_skipped(self):
        f = self.ok("# a comment", "", "name: probe", "  # indented comment", "color: purple")
        self.assertEqual(f, {"name": "probe", "color": "purple"})

    def test_trailing_comment_after_a_value(self):
        f = self.ok("name: probe # note", 'description: "x" # note')
        self.assertEqual(f, {"name": "probe", "description": "x"})

    def test_hash_inside_a_word_is_kept(self):
        self.assertEqual(self.ok("name: a#b")["name"], "a#b")

    def test_unknown_fields_are_kept_as_read(self):
        f = self.ok("name: probe", "foo: bar", "baz:", "  - one")
        self.assertEqual(f["foo"], "bar")
        self.assertEqual(f["baz"], ["one"])

    def test_empty_value_with_nothing_below_is_none(self):
        self.assertIsNone(self.ok("name: probe", "memory:")["memory"])

    def test_numbers_and_booleans_stay_strings(self):
        f = self.ok("maxTurns: 5", "background: true", "autoCompactWindow: 200000")
        self.assertEqual(f, {"maxTurns": "5", "background": "true", "autoCompactWindow": "200000"})

    def test_crlf_line_endings(self):
        text = "---\r\nname: probe\r\n---\r\nBody\r\n"
        self.assertEqual(af.read_frontmatter(text), ({"name": "probe"}, []))

    def test_closing_fence_with_trailing_space(self):
        self.assertEqual(af.read_frontmatter("---\nname: a\n--- \nBody"), ({"name": "a"}, []))

    def test_colon_without_a_following_space_is_part_of_a_plain_value(self):
        self.assertEqual(self.ok("name: my-plugin:reviewer")["name"], "my-plugin:reviewer")

    def test_shape_of_every_agent_in_this_repo(self):
        agents_dir = os.path.join(helpers.REPO, "agents")
        names = sorted(n for n in os.listdir(agents_dir) if n.endswith(".md"))
        self.assertTrue(names)
        for name in names:
            with self.subTest(agent=name):
                with open(os.path.join(agents_dir, name), encoding="utf-8") as fh:
                    fields, errors = af.read_frontmatter(fh.read())
                self.assertEqual(errors, [])
                self.assertIn("name", fields)
                self.assertIn("description", fields)


class RejectedShapesTest(unittest.TestCase):
    def rejected(self, text, kind):
        fields, errors = af.read_frontmatter(text)
        self.assertTrue(any(kind in e for e in errors),
                        "expected %r in %r" % (kind, errors))
        for e in errors:
            self.assertRegex(e, r"^line \d+: ")
        return fields, errors

    def test_no_opening_fence(self):
        self.rejected("name: probe\n---\n", "missing opening fence")

    def test_empty_text(self):
        self.rejected("", "missing opening fence")

    def test_missing_closing_fence(self):
        self.rejected("---\nname: probe\nBody\n", "missing closing fence")

    def test_tab_in_an_indent(self):
        self.rejected(doc("experimental:", "\tcacheTtl: 1h"), "tab in an indent")
        self.rejected(doc("\tname: probe"), "tab in an indent")

    def test_nesting_deeper_than_one_level(self):
        self.rejected(doc("a:", "  b:", "    c: d"), "deeper")
        self.rejected(doc("a:", "  - b", "    - c"), "deeper")

    def test_nested_flow_list(self):
        self.rejected(doc("a: [b, [c]]"), "deeper")
        self.rejected(doc("a:", "  - [b]"), "deeper")

    def test_block_scalars(self):
        self.rejected(doc("description: |", "  text"), "block scalar")
        self.rejected(doc("description: >", "  text"), "block scalar")

    def test_anchors_and_aliases(self):
        self.rejected(doc("a: &x value"), "anchor or alias")
        self.rejected(doc("a: *x"), "anchor or alias")

    def test_flow_map(self):
        self.rejected(doc("a: {b: c}"), "flow map")

    def test_duplicate_keys(self):
        fields, _ = self.rejected(doc("name: a", "name: b"), "duplicate key")
        self.assertEqual(fields["name"], "a")

    def test_duplicate_nested_keys(self):
        self.rejected(doc("a:", "  b: 1", "  b: 2"), "duplicate key")

    def test_unquoted_colon_space_in_a_value(self):
        self.rejected(doc("description: Lead: plans"), "unquoted colon")
        self.rejected(doc("a:", "  - one: two"), "unquoted colon")
        self.rejected(doc("a:", "  b: c: d"), "unquoted colon")

    def test_unclosed_bracket(self):
        self.rejected(doc("tools: [Read, Grep"), "unclosed bracket")

    def test_unclosed_quotes(self):
        self.rejected(doc('description: "oops'), "unclosed quote")
        self.rejected(doc("description: 'oops"), "unclosed quote")
        self.rejected(doc("a: [\"x, y]"), "unclosed quote")

    def test_unsupported_backslash_escape_in_a_double_quoted_value(self):
        # \x41 is not kept as literal text: the reader cannot say what Claude Code makes of it.
        self.rejected(doc(r'description: "a \x41 b"'), "unsupported escape")
        self.rejected(doc(r'description: "\u0041"'), "unsupported escape")
        self.rejected(doc(r'tools: ["a\x41", b]'), "unsupported escape")
        self.rejected(doc(r'skills:', r'  - "\q"'), "unsupported escape")
        # A single-quoted value takes a backslash as it is.
        fields, errors = af.read_frontmatter(doc(r"description: 'a \x41 b'"))
        self.assertEqual((fields, errors), ({"description": r"a \x41 b"}, []))

    def test_long_flow_list_stays_linear(self):
        # A list item that is not at its start never opens a quote, so 200k quotes after
        # "a" used to cost a join of the item for each one (8 seconds at 80k).
        for text in ("tools: [a" + "'" * 200000 + "]", "tools: [a" + '"' * 200000 + "]",
                     "tools: [" + "a, " * 70000 + "b]"):
            start = time.monotonic()
            af.read_frontmatter(doc(text))
            self.assertLess(time.monotonic() - start, 1.0)

    def test_text_after_a_closing_quote(self):
        self.rejected(doc('description: "a" b'), "after a closing quote")

    def test_text_after_a_closing_bracket(self):
        self.rejected(doc("a: [b] c"), "after a closing bracket")

    def test_bad_keys(self):
        self.rejected(doc("not a key"), "not a key")
        self.rejected(doc("1abc: x"), "not a key")
        self.rejected(doc("a-b: x"), "not a key")
        self.rejected(doc("a:b"), "not a key")

    def test_unexpected_indent(self):
        self.rejected(doc("  name: probe"), "unexpected indent")
        self.rejected(doc("name: probe", "  more text"), "unexpected indent")

    def test_inconsistent_block_indent(self):
        self.rejected(doc("a:", "    - one", "  - two"), "inconsistent indent")

    def test_mixed_list_and_map(self):
        self.rejected(doc("a:", "  - one", "  b: two"), "mixed list and map")
        self.rejected(doc("a:", "  b: two", "  - one"), "mixed list and map")

    def test_empty_list_items(self):
        self.rejected(doc("a:", "  -"), "empty list item")
        self.rejected(doc("a: [b, , c]"), "empty list item")

    def test_a_rejected_field_is_not_half_kept(self):
        fields, _ = af.read_frontmatter(doc("name: probe", "a: [b", "c: d"))
        self.assertEqual(fields, {"name": "probe", "c": "d"})

    def test_error_text_never_repeats_content(self):
        secret = "zebra-secret-value"
        cases = [doc("description: Lead: %s" % secret), doc('description: "%s' % secret),
                 doc("%s" % secret), doc("a: [%s" % secret), doc("%s: 1" % secret, "%s: 2" % secret)]
        for text in cases:
            with self.subTest(text=text):
                _, errors = af.read_frontmatter(text)
                self.assertTrue(errors)
                self.assertNotIn(secret, " ".join(errors))

    def test_non_text_input(self):
        self.assertTrue(af.read_frontmatter(None)[1])


def load_fields():
    with open(af.FIELDS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


class FieldsFileTest(unittest.TestCase):
    def test_real_file_passes(self):
        self.assertEqual(af.check_fields(load_fields()), [])

    def test_docs_order_and_required_fields(self):
        data = load_fields()
        self.assertEqual([f["field"] for f in data["fields"]], [
            "name", "description", "tools", "disallowedTools", "model", "permissionMode",
            "maxTurns", "autoCompactWindow", "skills", "mcpServers", "hooks", "memory",
            "background", "omitClaudeMd", "effort", "isolation", "color", "initialPrompt",
            "experimental"])
        self.assertEqual([f["field"] for f in data["fields"] if f["required"]],
                         ["name", "description"])

    def test_column_fields(self):
        data = load_fields()
        self.assertEqual([f["field"] for f in data["fields"] if f["display"] == "column"],
                         ["name", "model", "autoCompactWindow", "effort", "experimental"])

    def test_experimental_knows_cache_ttl(self):
        item = [f for f in load_fields()["fields"] if f["field"] == "experimental"][0]
        self.assertEqual(item["type"], "map")
        self.assertEqual(item["known_keys"], ["cacheTtl"])

    def test_cli_check_prints_ok(self):
        res = subprocess.run([sys.executable, SCRIPT, "check"], capture_output=True, text=True)
        self.assertEqual((res.returncode, res.stdout.strip()), (0, "ok"))


class BrokenFieldsTest(unittest.TestCase):
    def setUp(self):
        self.good = load_fields()

    def broken(self, mutate):
        data = copy.deepcopy(self.good)
        mutate(data)
        return af.check_fields(data)

    def assertFails(self, mutate, fragment=None):
        errs = self.broken(mutate)
        self.assertTrue(errs, "expected errors")
        if fragment:
            self.assertTrue(any(fragment in e for e in errs), "%r not in %r" % (fragment, errs))

    def item(self, data, name):
        return [f for f in data["fields"] if f["field"] == name][0]

    def test_top_level_keys(self):
        self.assertFails(lambda d: d.pop("doc_url"), "missing field doc_url")
        self.assertFails(lambda d: d.update(extra=1), "unknown field extra")
        self.assertFails(lambda d: d.update(schema_version=2), "schema_version")
        self.assertFails(lambda d: d.update(schema_version=True), "schema_version")
        self.assertEqual(af.check_fields([]), ["top level must be an object"])

    def test_verified_on(self):
        self.assertFails(lambda d: d["verified_on"].pop("date"), "verified_on")
        self.assertFails(lambda d: d["verified_on"].update(date="Oct 29"), "date")
        self.assertFails(lambda d: d["verified_on"].update(claude_version=""), "claude_version")

    def test_doc_url_must_be_https(self):
        self.assertFails(lambda d: d.update(doc_url="http://example.com/x"), "https")
        self.assertFails(lambda d: d.update(doc_url=5), "https")

    def test_fields_must_be_a_non_empty_list(self):
        self.assertFails(lambda d: d.update(fields=[]), "non-empty list")
        self.assertFails(lambda d: d.update(fields="x"), "non-empty list")

    def test_item_keys(self):
        self.assertFails(lambda d: d["fields"][0].pop("quote"), "missing field quote")
        self.assertFails(lambda d: d["fields"][0].update(extra=1), "unknown field extra")
        self.assertFails(lambda d: d["fields"].append("name"), "must be an object")

    def test_item_types(self):
        self.assertFails(lambda d: d["fields"][0].update(type="text"), "type must be")
        self.assertFails(lambda d: d["fields"][0].update(required="yes"), "required")
        self.assertFails(lambda d: d["fields"][0].update(display="hidden"), "display")
        self.assertFails(lambda d: d["fields"][0].update(field="bad name"), "field must match")

    def test_unique_fields(self):
        self.assertFails(lambda d: d["fields"][1].update(field="name"), "repeats")

    def test_quote_must_be_non_empty(self):
        self.assertFails(lambda d: d["fields"][0].update(quote=""), "quote")
        self.assertFails(lambda d: d["fields"][0].update(quote="  "), "quote")
        self.assertFails(lambda d: d["fields"][0].update(quote=None), "quote")

    def test_values_only_on_enum(self):
        self.assertFails(lambda d: d["fields"][0].update(values=["a"]), "only for type enum")
        self.assertFails(lambda d: self.item(d, "effort").pop("values"), "needs values")
        self.assertFails(lambda d: self.item(d, "effort").update(values=[]), "values must be")
        self.assertFails(lambda d: self.item(d, "effort").update(values=["low", "low"]), "values")
        self.assertFails(lambda d: self.item(d, "effort").update(values=["low", 5]), "values")

    def test_known_keys_only_on_map(self):
        self.assertFails(lambda d: d["fields"][0].update(known_keys=["a"]), "only for type map")
        self.assertFails(lambda d: self.item(d, "experimental").update(known_keys=[]), "known_keys")
        self.assertFails(lambda d: self.item(d, "experimental").update(known_keys="cacheTtl"),
                         "known_keys")


def _strip_links(text):
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)


class QuoteSubstringTest(unittest.TestCase):
    def test_every_quote_is_a_substring_of_the_link_stripped_docs(self):
        path = DOCS_COPY
        if not path or not os.path.isfile(path):
            self.skipTest("set MR_SUBAGENT_DOCS to a saved copy of the sub-agents docs page")
        with open(path, encoding="utf-8") as fh:
            text = _strip_links(fh.read())
        for item in load_fields()["fields"]:
            with self.subTest(field=item["field"]):
                self.assertIn(item["quote"], text)

    def test_quotes_carry_no_markdown_link(self):
        for item in load_fields()["fields"]:
            with self.subTest(field=item["field"]):
                self.assertIsNone(re.search(r"\]\(", item["quote"]))


class ReadCommandTest(unittest.TestCase):
    def run_read(self, *paths):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = af._cmd_read(list(paths))
        return rc, out.getvalue()

    def test_prints_only_an_index_and_a_result(self):
        with tempfile.TemporaryDirectory(dir=helpers._tmp_base()) as tmp:
            good = os.path.join(tmp, "private-name-one.md")
            bad = os.path.join(tmp, "private-name-two.md")
            with open(good, "w") as fh:
                fh.write(doc("name: secret-agent", "description: Secret text."))
            with open(bad, "w") as fh:
                fh.write(doc("description: Secret: text."))
            rc, out = self.run_read(good, bad, os.path.join(tmp, "missing.md"))
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines(), [
            "1: ok", "2: rejected: unquoted colon in a value", "3: rejected: unreadable"])
        for word in ("private-name", "secret", "Secret", tmp):
            self.assertNotIn(word, out)

    def test_not_utf8(self):
        with tempfile.TemporaryDirectory(dir=helpers._tmp_base()) as tmp:
            path = os.path.join(tmp, "x.md")
            with open(path, "wb") as fh:
                fh.write(b"---\nname: \xff\xfe\n---\n")
            _, out = self.run_read(path)
        self.assertEqual(out.strip(), "1: rejected: not utf-8")

    def test_cli_runs(self):
        res = subprocess.run([sys.executable, SCRIPT, "read", os.path.join(
            helpers.REPO, "agents", "scout.md")], capture_output=True, text=True)
        self.assertEqual((res.returncode, res.stdout.strip()), (0, "1: ok"))

    def test_usage_on_bad_arguments(self):
        res = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True)
        self.assertEqual(res.returncode, 2)


if __name__ == "__main__":
    unittest.main()
