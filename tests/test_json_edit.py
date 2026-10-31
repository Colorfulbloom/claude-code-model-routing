"""Tests for the pure JSON edit module (dashboard/json_edit.py).

All content is made up. Fixture files are only read from the repo. The module
opens no file, so these tests never touch a home or config folder.
"""
import json
import os
import re
import sys
import unittest

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import collect  # noqa: E402
import json_edit  # noqa: E402

RES = os.path.join(helpers.REPO, "tests", "fixtures", "resolution")


def code_of(testcase, func, *args):
    with testcase.assertRaises(json_edit.Refused) as ctx:
        func(*args)
    return ctx.exception.code


def fixture_texts():
    """Every settings-like JSON file under the resolution fixtures that parses as an object."""
    found = []
    for root, _dirs, files in os.walk(RES):
        for name in sorted(files):
            if not name.endswith(".json") or name in ("session.json", "expected.json"):
                continue
            path = os.path.join(root, name)
            with open(path, "rb") as fh:
                raw = fh.read()
            try:
                text = raw.decode("utf-8")
                if isinstance(json.loads(text), dict):
                    found.append((path, text))
            except ValueError:
                continue
    return found


class ParseStrict(unittest.TestCase):
    def test_returns_text_and_data(self):
        text, data = json_edit.parse_strict(b'{"a": 1}')
        self.assertEqual('{"a": 1}', text)
        self.assertEqual({"a": 1}, data)

    def test_refuses_what_json_loads_refuses(self):
        for raw in (b'{"a": 1,}', b'{"a": 1} // note', b'/* c */ {"a": 1}',
                    b"{'a': 1}", b"", b'{"a": 1} x', b'{"a": '):
            self.assertEqual("unparsed", code_of(self, json_edit.parse_strict, raw), raw)

    def test_refuses_a_byte_order_mark(self):
        self.assertEqual("unparsed", code_of(self, json_edit.parse_strict, b'\xef\xbb\xbf{"a": 1}'))

    def test_refuses_bad_utf8(self):
        self.assertEqual("unparsed", code_of(self, json_edit.parse_strict, b'{"a": "\xff"}'))
        self.assertEqual("unparsed", code_of(self, json_edit.parse_strict, b'{"a": "\xc3("}'))

    def test_refuses_a_top_level_that_is_not_an_object(self):
        for raw in (b"[1]", b'"x"', b"3", b"null", b"true"):
            self.assertEqual("unparsed", code_of(self, json_edit.parse_strict, raw), raw)

    def test_refuses_text_not_bytes(self):
        self.assertEqual("unparsed", code_of(self, json_edit.parse_strict, '{"a": 1}'))

    def test_refuses_deep_nesting(self):
        raw = b'{"a": ' + b"[" * 100000 + b"]" * 100000 + b"}"
        self.assertEqual("unparsed", code_of(self, json_edit.parse_strict, raw))


class ValueSpan(unittest.TestCase):
    def span(self, raw, path):
        start, end = json_edit.value_span(raw, path)
        return raw[start:end]

    def test_object_keys_and_array_indexes(self):
        raw = b'{"a": {"b": [10, {"c": "deep"}, 30]}, "d": null}'
        self.assertEqual(b'"deep"', self.span(raw, ("a", "b", 1, "c")))
        self.assertEqual(b"30", self.span(raw, ("a", "b", 2)))
        self.assertEqual(b'[10, {"c": "deep"}, 30]', self.span(raw, ("a", "b")))
        self.assertEqual(b"null", self.span(raw, ("d",)))

    def test_keys_with_dots_are_one_step(self):
        raw = b'{"modelSettings": {"us.anthropic.x-v1:0": {"effortLevel": "low"}}}'
        self.assertEqual(b'"low"', self.span(raw, ("modelSettings", "us.anthropic.x-v1:0", "effortLevel")))

    def test_string_with_brackets_and_commas_does_not_confuse_the_walk(self):
        raw = b'{"a": "x]},{\\"q\\": 1", "b": 2}'
        self.assertEqual(b"2", self.span(raw, ("b",)))

    def test_repeated_key_takes_the_last(self):
        raw = b'{"a": 1, "a": 2, "a": 3}'
        self.assertEqual(b"3", self.span(raw, ("a",)))

    def test_repeated_parent_takes_the_last_parent(self):
        raw = b'{"p": {"k": 1, "z": 5}, "p": {"k": 2}}'
        self.assertEqual(b"2", self.span(raw, ("p", "k")))
        self.assertEqual("key_missing", code_of(self, json_edit.value_span, raw, ("p", "z")))

    def test_offsets_are_bytes_after_multibyte_text(self):
        raw = '{"né": "日本", "k": "v"}'.encode("utf-8")
        start, end = json_edit.value_span(raw, ("k",))
        self.assertEqual(b'"v"', raw[start:end])
        start, end = json_edit.value_span(raw, ("né",))
        self.assertEqual('"日本"'.encode("utf-8"), raw[start:end])

    def test_missing_pieces_raise_key_missing(self):
        raw = b'{"a": [1, 2], "b": "s", "c": {"d": 1}}'
        for path in (("zz",), ("a", 2), ("a", -1), ("a", "x"), ("b", "x"), ("b", 0),
                     ("c", 0), ("a", 0, "q"), ("c", "d", "e")):
            self.assertEqual("key_missing", code_of(self, json_edit.value_span, raw, path), path)

    def test_bad_step_types_raise_key_missing(self):
        raw = b'{"a": [1, 2]}'
        for path in (("a", True), ("a", 1.0), ("a", None), (None,)):
            self.assertEqual("key_missing", code_of(self, json_edit.value_span, raw, path), path)

    def test_unparsed_input_raises_unparsed(self):
        self.assertEqual("unparsed", code_of(self, json_edit.value_span, b'{"a": 1,}', ("a",)))


class ReplaceValue(unittest.TestCase):
    def check_outside_untouched(self, raw, path, value):
        start, end = json_edit.value_span(raw, path)
        new = json_edit.replace_value(raw, path, value)
        self.assertEqual(raw[:start], new[:start])
        self.assertEqual(raw[end:], new[len(new) - (len(raw) - end):])
        return new

    def test_replaces_only_the_span(self):
        raw = b'{\n  "effortLevel": "low",\n  "other": 1\n}\n'
        new = self.check_outside_untouched(raw, ("effortLevel",), "high")
        self.assertEqual(b'{\n  "effortLevel": "high",\n  "other": 1\n}\n', new)

    def test_crlf(self):
        raw = b'{\r\n  "a": "x",\r\n  "b": [1,\r\n 2]\r\n}\r\n'
        new = self.check_outside_untouched(raw, ("a",), "y")
        self.assertEqual(b'{\r\n  "a": "y",\r\n  "b": [1,\r\n 2]\r\n}\r\n', new)

    def test_tabs(self):
        raw = b'{\n\t"a": {\n\t\t"b": "x"\n\t}\n}\n'
        new = self.check_outside_untouched(raw, ("a", "b"), "y")
        self.assertEqual(b'{\n\t"a": {\n\t\t"b": "y"\n\t}\n}\n', new)

    def test_no_trailing_newline(self):
        raw = b'{"a": "x"}'
        self.assertEqual(b'{"a": "y"}', self.check_outside_untouched(raw, ("a",), "y"))

    def test_minified(self):
        raw = b'{"a":{"b":[1,2,{"c":"x"}],"d":3},"e":"z"}'
        new = self.check_outside_untouched(raw, ("a", "b", 2, "c"), "y")
        self.assertEqual(b'{"a":{"b":[1,2,{"c":"y"}],"d":3},"e":"z"}', new)

    def test_duplicate_keys_edit_the_last(self):
        raw = b'{"a": "first", "a": "second"}'
        new = self.check_outside_untouched(raw, ("a",), "new")
        self.assertEqual(b'{"a": "first", "a": "new"}', new)
        self.assertEqual("new", json.loads(new)["a"])

    def test_unicode_escapes_elsewhere_stay_as_written(self):
        raw = b'{"n": "caf\\u00e9 \\ud83d\\ude00", "a": "x", "\\u006b": 1.50e+2}'
        new = self.check_outside_untouched(raw, ("a",), "y")
        self.assertEqual(b'{"n": "caf\\u00e9 \\ud83d\\ude00", "a": "y", "\\u006b": 1.50e+2}', new)

    def test_number_spelling_elsewhere_stays_as_written(self):
        raw = b'{"a": 1.0, "b": 1E5, "c": -0, "d": "x"}'
        new = self.check_outside_untouched(raw, ("d",), "y")
        self.assertEqual(b'{"a": 1.0, "b": 1E5, "c": -0, "d": "y"}', new)

    def test_new_span_is_json_dumps_of_the_value(self):
        raw = b'{"a": "x"}'
        for value in ("café", "q\"uote\n", 5, 1.5, True, None, [1, "b"], {"k": "v"}, "😀"):
            new = json_edit.replace_value(raw, ("a",), value)
            self.assertEqual(b'{"a": ' + json.dumps(value).encode("ascii") + b"}", new)
            self.assertEqual(value, json.loads(new)["a"])

    def test_replaces_a_container_with_a_scalar_and_back(self):
        raw = b'{"a": {"b": [1, 2]}, "c": 1}'
        new = json_edit.replace_value(raw, ("a",), "s")
        self.assertEqual(b'{"a": "s", "c": 1}', new)

    def test_replaces_an_array_item(self):
        raw = b'{"a": [1, 2, 3]}'
        self.assertEqual(b'{"a": [1, 9, 3]}', json_edit.replace_value(raw, ("a", 1), 9))

    def test_multibyte_text_before_the_span(self):
        raw = '{"日": "本", "a": "x"}'.encode("utf-8")
        new = self.check_outside_untouched(raw, ("a",), "y")
        self.assertEqual('{"日": "本", "a": "y"}'.encode("utf-8"), new)

    def test_missing_key_refuses(self):
        self.assertEqual("key_missing", code_of(self, json_edit.replace_value, b'{"a": 1}', ("b",), 1))

    def test_unparsed_file_refuses(self):
        self.assertEqual("unparsed", code_of(self, json_edit.replace_value, b'{"a": 1,}', ("a",), 1))
        self.assertEqual("unparsed", code_of(self, json_edit.replace_value, b'\xef\xbb\xbf{"a": 1}', ("a",), 1))

    def test_a_nan_in_the_file_fails_the_oracle(self):
        raw = b'{"a": NaN, "b": "x"}'
        self.assertEqual("oracle_failed", code_of(self, json_edit.replace_value, raw, ("b",), "y"))

    def test_a_value_json_cannot_write_refuses(self):
        raw = b'{"a": "x"}'
        self.assertEqual("oracle_failed", code_of(self, json_edit.replace_value, raw, ("a",), object()))
        self.assertEqual("oracle_failed", code_of(self, json_edit.replace_value, raw, ("a",), float("nan")))

    def test_input_is_not_changed(self):
        raw = b'{"a": "x"}'
        json_edit.replace_value(raw, ("a",), "y")
        self.assertEqual(b'{"a": "x"}', raw)


class Oracle(unittest.TestCase):
    OLD = b'{"a": "x", "b": [1, 2]}'

    def good(self):
        start, end = json_edit.value_span(self.OLD, ("a",))
        return start, end, self.OLD[:start] + b'"y"' + self.OLD[end:]

    def test_accepts_a_correct_edit(self):
        start, end, new = self.good()
        json_edit._oracle(self.OLD, new, start, end, ("a",), "y")

    def test_refuses_a_changed_prefix(self):
        start, end, new = self.good()
        bad = b'[' + new[1:]
        self.assertEqual("oracle_failed", code_of(self, json_edit._oracle, self.OLD, bad, start, end, ("a",), "y"))

    def test_refuses_a_changed_tail(self):
        start, end, new = self.good()
        bad = new[:-2] + b" }"
        self.assertEqual("oracle_failed", code_of(self, json_edit._oracle, self.OLD, bad, start, end, ("a",), "y"))

    def test_refuses_a_whitespace_only_change_outside_the_span(self):
        start, end, new = self.good()
        bad = new.replace(b'"b"', b' "b"')
        self.assertEqual("oracle_failed", code_of(self, json_edit._oracle, self.OLD, bad, start, end, ("a",), "y"))

    def test_refuses_when_the_value_is_not_what_was_asked(self):
        start, end, new = self.good()
        self.assertEqual("oracle_failed", code_of(self, json_edit._oracle, self.OLD, new, start, end, ("a",), "z"))

    def test_refuses_when_the_new_bytes_do_not_parse(self):
        start, end, _ = self.good()
        bad = self.OLD[:start] + b'"y' + self.OLD[end:]
        self.assertEqual("oracle_failed", code_of(self, json_edit._oracle, self.OLD, bad, start, end, ("a",), "y"))

    def test_refuses_a_second_changed_value(self):
        start, end, new = self.good()
        bad = new.replace(b"[1, 2]", b"[1, 3]")
        self.assertEqual("oracle_failed", code_of(self, json_edit._oracle, self.OLD, bad, start, end, ("a",), "y"))

    def test_refuses_a_bad_path(self):
        start, end, new = self.good()
        self.assertEqual("oracle_failed", code_of(self, json_edit._oracle, self.OLD, new, start, end, ("q", "r"), "y"))

    def test_replace_value_never_falls_back(self):
        # Break the oracle's view of the span and check the error comes out, not a result.
        real = json_edit.value_span
        json_edit.value_span = lambda raw, path: (1, 2)
        try:
            self.assertEqual("oracle_failed", code_of(self, json_edit.replace_value, self.OLD, ("a",), "y"))
        finally:
            json_edit.value_span = real


MARKERS = ("MARK1", "MARK2", "MARK3", "MARK4", "MARK5", "MARK6", "MARK7", "MARK8", "MARK9", "MARKA", "MARKB", "MARKC")


class MaskText(unittest.TestCase):
    def test_repeated_secret_key_loses_both_values(self):
        out = json_edit.mask_text('{"X_TOKEN":"first","X_TOKEN":"second"}')
        self.assertEqual('{"X_TOKEN":"hidden","X_TOKEN":"hidden"}', out)

    def test_secret_name_hides_any_type(self):
        text = '{"API_KEY": {"a": 1, "b": [2]}, "MY_SECRET": [1, 2], "PASSWORD": 5, "AUTH": null, "CREDENTIAL": true}'
        out = json.loads(json_edit.mask_text(text))
        for key in ("API_KEY", "MY_SECRET", "PASSWORD", "AUTH", "CREDENTIAL"):
            self.assertEqual("hidden", out[key], key)

    def test_secret_names_match_in_any_case(self):
        out = json.loads(json_edit.mask_text('{"my_token": "a", "ApiKey": "b", "x": "c"}'))
        self.assertEqual({"my_token": "hidden", "ApiKey": "hidden", "x": "c"}, out)

    def test_secret_prefix_hides_the_string(self):
        out = json.loads(json_edit.mask_text('{"a": "sk-abc", "b": " SK-abc", "c": "Bearer x", "d": "bearer x", "e": "ok"}'))
        self.assertEqual({"a": "hidden", "b": "hidden", "c": "hidden", "d": "hidden", "e": "ok"}, out)

    def test_escaped_names_and_values_compare_decoded(self):
        out = json.loads(json_edit.mask_text('{"X_\\u0054OKEN": "v", "p": "\\u0073k-abc", "q": "ok"}'))
        self.assertEqual({"X_TOKEN": "hidden", "p": "hidden", "q": "ok"}, out)

    def test_list_items_follow_the_lists_name(self):
        text = '{"TOKENS": ["a", ["b"]], "plain": ["sk-1", "ok", {"AUTH": "z", "k": "v"}, ["Bearer q"]]}'
        out = json.loads(json_edit.mask_text(text))
        self.assertEqual("hidden", out["TOKENS"])
        self.assertEqual(["hidden", "ok", {"AUTH": "hidden", "k": "v"}, ["hidden"]], out["plain"])

    def test_nested_objects(self):
        text = '{"a": {"b": {"c_key": "v", "d": "sk-q", "e": 1}}}'
        out = json.loads(json_edit.mask_text(text))
        self.assertEqual({"a": {"b": {"c_key": "hidden", "d": "hidden", "e": 1}}}, out)

    def test_non_secret_text_is_unchanged(self):
        text = '{\r\n\t"a": [1,\r\n  2.50, "x"],\r\n  "b": {}\r\n}'
        self.assertEqual(text, json_edit.mask_text(text))

    def test_line_breaks_inside_a_hidden_span_are_kept_in_spelling(self):
        for brk in ("\n", "\r\n", "\r"):
            text = '{"SECRET": {' + brk + '"a": 1,' + brk + '"b": [2,' + brk + '3]' + brk + '}, "k": 1}'
            out = json_edit.mask_text(text)
            self.assertEqual('{"SECRET": "hidden"' + brk * 4 + ', "k": 1}', out)
            self.assertEqual(text.count(brk), out.count(brk))
            self.assertEqual({"SECRET": "hidden", "k": 1}, json.loads(out))

    def test_line_count_is_kept(self):
        text = '{\n  "A_TOKEN": {\n    "x": 1\n  },\n  "b": [\n    "sk-1"\n  ]\n}\n'
        out = json_edit.mask_text(text)
        self.assertEqual(len(re.split(r"\r\n|\n|\r", text)), len(re.split(r"\r\n|\n|\r", out)))
        self.assertEqual(text.count("\n"), out.count("\n"))

    def test_masked_fixtures_match_collect_mask(self):
        pairs = fixture_texts()
        self.assertTrue(pairs)
        for path, text in pairs:
            with self.subTest(path=os.path.relpath(path, helpers.REPO)):
                self.assertEqual(collect.mask(json.loads(text)), json.loads(json_edit.mask_text(text)))

    def test_masked_samples_match_collect_mask(self):
        samples = [
            '{"env": {"ANTHROPIC_API_KEY": "sk-x", "FOO": "bar", "N": 1}, "list": ["a", "Bearer b", ["sk-z"]]}',
            '{"a": [{"TOKEN": [1]}, {"b": "sk-1"}], "AUTH": {"x": [1, 2]}, "n": null, "t": true, "f": 1.5e3}',
            '{"X_TOKEN":"first","X_TOKEN":"second","y":1,"y":"sk-2"}',
            '{}',
            '{"a": [], "b": {}, "KEY": []}',
        ]
        for text in samples:
            self.assertEqual(collect.mask(json.loads(text)), json.loads(json_edit.mask_text(text)), text)

    def test_no_marker_survives_in_the_output(self):
        m = MARKERS
        text = (
            '{\n'
            '  "X_TOKEN": "' + m[0] + '",\n'
            '  "X_TOKEN": "' + m[1] + '",\n'
            '  "plain": "sk-' + m[2] + '",\n'
            '  "plain": "Bearer ' + m[3] + '",\n'
            '  "nested": {"deep": {"API_KEY": {"inner": "' + m[4] + '"}, "v": "sk-' + m[5] + '"}},\n'
            '  "list": ["sk-' + m[6] + '", ["Bearer ' + m[7] + '"], {"SECRET": ["' + m[8] + '"]}],\n'
            '  "TOKENS": ["' + m[9] + '", {"a": "' + m[10] + '"}],\n'
            '  "keep": [{"PASSWORD": "' + m[11] + '"}, "visible"]\n'
            '}\n'
        )
        json.loads(text)
        out = json_edit.mask_text(text)
        for marker in m:
            self.assertNotIn(marker, out, marker)
        self.assertIn("visible", out)

    def test_no_marker_survives_in_any_diff(self):
        m = MARKERS
        before = (
            '{\n'
            '  "effortLevel": "low",\n'
            '  "X_TOKEN": "' + m[0] + '",\n'
            '  "X_TOKEN": "' + m[1] + '",\n'
            '  "env": {"A": "sk-' + m[2] + '", "API_KEY": {"i": "' + m[3] + '"}},\n'
            '  "list": ["Bearer ' + m[4] + '", {"SECRET": ["' + m[5] + '"]}]\n'
            '}\n'
        )
        after = before.replace('"low"', '"high"')
        after2 = after.replace(m[0], "OTHER1").replace(m[2], "OTHER2")
        for a, b in ((before, after), (before, after2), (after2, before)):
            blob = json.dumps(json_edit.structured_diff(a, b, "settings.json"))
            for marker in m[:6]:
                self.assertNotIn(marker, blob, marker)
            for marker in ("OTHER1", "OTHER2"):
                self.assertNotIn(marker, blob, marker)


class StructuredDiff(unittest.TestCase):
    def test_equal_texts_give_no_hunks(self):
        text = '{\n  "a": 1\n}\n'
        self.assertEqual({"file_display": "f.json", "hunks": []}, json_edit.structured_diff(text, text, "f.json"))

    def test_shape_and_line_numbers(self):
        before = '{\n  "a": "x",\n  "b": 1\n}\n'
        after = '{\n  "a": "y",\n  "b": 1\n}\n'
        diff = json_edit.structured_diff(before, after, "~/.claude/settings.json")
        self.assertEqual("~/.claude/settings.json", diff["file_display"])
        self.assertEqual(1, len(diff["hunks"]))
        lines = diff["hunks"][0]["lines"]
        self.assertEqual([
            {"kind": "context", "old_line": 1, "new_line": 1, "text": "{"},
            {"kind": "del", "old_line": 2, "new_line": None, "text": '  "a": "x",'},
            {"kind": "add", "old_line": None, "new_line": 2, "text": '  "a": "y",'},
            {"kind": "context", "old_line": 3, "new_line": 3, "text": '  "b": 1'},
            {"kind": "context", "old_line": 4, "new_line": 4, "text": "}"},
        ], lines)
        for line in lines:
            self.assertEqual({"kind", "old_line", "new_line", "text"}, set(line))

    def test_three_lines_of_context_and_separate_hunks(self):
        items = ",\n".join('  "k%02d": %d' % (i, i) for i in range(30))
        before = "{\n" + items + "\n}\n"
        after = before.replace('"k02": 2', '"k02": 99').replace('"k27": 27', '"k27": 99')
        diff = json_edit.structured_diff(before, after, "f.json")
        self.assertEqual(2, len(diff["hunks"]))
        for hunk in diff["hunks"]:
            kinds = [line["kind"] for line in hunk["lines"]]
            self.assertEqual(["del", "add"], [k for k in kinds if k != "context"])
            first = kinds.index("del")
            self.assertLessEqual(first, 3)
            self.assertEqual(3, len(kinds) - 1 - kinds.index("add"))

    def test_line_breaks_of_every_spelling_split_lines(self):
        before = '{"a": 1,\r\n"b": 2,\r"c": 3,\n"d": 4}'
        after = before.replace('"c": 3', '"c": 9')
        lines = json_edit.structured_diff(before, after, "f")["hunks"][0]["lines"]
        self.assertEqual(['{"a": 1,', '"b": 2,', '"c": 3,', '"d": 4}'],
                         [line["text"] for line in lines if line["kind"] != "add"])
        for line in lines:
            self.assertNotRegex(line["text"], r"[\r\n]")

    def test_added_and_removed_trailing_lines(self):
        diff = json_edit.structured_diff('{"a": 1}\n', '{"a": 1}\n\n', "f")
        lines = diff["hunks"][0]["lines"]
        self.assertEqual("add", lines[-1]["kind"])
        self.assertEqual("", lines[-1]["text"])
        self.assertEqual(2, lines[-1]["new_line"])

    def test_diff_shows_masked_text_only(self):
        before = '{\n  "a": "x",\n  "API_KEY": "real-one"\n}\n'
        after = '{\n  "a": "y",\n  "API_KEY": "real-two"\n}\n'
        diff = json_edit.structured_diff(before, after, "f")
        blob = json.dumps(diff)
        self.assertNotIn("real-one", blob)
        self.assertNotIn("real-two", blob)
        self.assertIn('\\"API_KEY\\": \\"hidden\\"', blob)

    def test_a_secret_edit_shows_as_no_change(self):
        before = '{\n  "API_KEY": "one"\n}\n'
        after = '{\n  "API_KEY": "two"\n}\n'
        self.assertEqual([], json_edit.structured_diff(before, after, "f")["hunks"])


class Purity(unittest.TestCase):
    def test_module_source_has_no_file_calls(self):
        with open(json_edit.__file__.replace(".pyc", ".py"), encoding="utf-8") as fh:
            source = fh.read()
        for banned in (r"\bopen\(", r"\.write\(", r"\.writelines\(", r"\bshutil\b", r"\btempfile\b",
                       r"\bpathlib\b", r"\bsubprocess\b", r"os\.(remove|unlink|rename|replace|mkdir|makedirs|rmdir|utime|chmod|symlink|link|truncate|environ|path\.expanduser)\b"):
            self.assertIsNone(re.search(banned, source), banned)

    def test_edits_leave_the_cwd_and_environment_alone(self):
        before = (os.getcwd(), dict(os.environ))
        json_edit.replace_value(b'{"a": "x"}', ("a",), "y")
        json_edit.mask_text('{"a": "sk-1"}')
        json_edit.structured_diff('{"a": 1}', '{"a": 2}', "f")
        self.assertEqual(before, (os.getcwd(), dict(os.environ)))


if __name__ == "__main__":
    unittest.main()
