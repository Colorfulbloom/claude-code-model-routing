"""The old ``tests/test_json_edit.py``, ported whole to ``json_edit`` (task a4).

All content is made up. The module opens no file, so these tests never touch a home or
config folder. Two things differ from the old file.

- The old masking tests compared against ``collect.mask``. They compare against
  ``masking.mask_value`` now, the read side's masker under the 26-07 rules. That masker
  also hides URL userinfo and the value of a secret-named flag in an ``args`` list, so
  ``json_edit.mask_text`` does too (the port found that it did not, and the diff would
  have shown such a password).
- The old module has no array-append function, and neither does the new one, so no
  case was dropped. The array cases that remain use an index in a key path, which
  ``value_span`` and ``replace_value`` still take.
"""

# pyright: reportPrivateUsage=false
# ruff: noqa: E501 - the byte strings stay on one line, as the old tests had
# them, and the oracle tests call the private checker.

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import port_helpers as helpers

import json_edit
import masking

RES = helpers.FIXTURES / "resolution"


def code_of(func: Callable[..., object], *args: object) -> str:
    with pytest.raises(json_edit.Refused) as caught:
        func(*args)
    return caught.value.code


def fixture_texts() -> list[tuple[Path, str]]:
    """Every settings-like JSON file under the resolution fixtures that is an object."""
    found: list[tuple[Path, str]] = []
    for path in sorted(RES.rglob("*.json")):
        if path.name in ("session.json", "expected.json"):
            continue
        try:
            text = path.read_bytes().decode("utf-8")
            if isinstance(json.loads(text), dict):
                found.append((path, text))
        except ValueError:
            continue
    return found


class TestParseStrict:
    def test_returns_text_and_data(self) -> None:
        text, data = json_edit.parse_strict(b'{"a": 1}')
        assert text == '{"a": 1}'
        assert data == {"a": 1}

    def test_refuses_what_json_loads_refuses(self) -> None:
        for raw in (
            b'{"a": 1,}',
            b'{"a": 1} // note',
            b'/* c */ {"a": 1}',
            b"{'a': 1}",
            b"",
            b'{"a": 1} x',
            b'{"a": ',
        ):
            assert code_of(json_edit.parse_strict, raw) == "unparsed", raw

    def test_refuses_a_byte_order_mark(self) -> None:
        assert code_of(json_edit.parse_strict, b'\xef\xbb\xbf{"a": 1}') == "unparsed"

    def test_refuses_bad_utf8(self) -> None:
        assert code_of(json_edit.parse_strict, b'{"a": "\xff"}') == "unparsed"
        assert code_of(json_edit.parse_strict, b'{"a": "\xc3("}') == "unparsed"

    def test_refuses_a_top_level_that_is_not_an_object(self) -> None:
        for raw in (b"[1]", b'"x"', b"3", b"null", b"true"):
            assert code_of(json_edit.parse_strict, raw) == "unparsed", raw

    def test_refuses_text_not_bytes(self) -> None:
        assert code_of(json_edit.parse_strict, '{"a": 1}') == "unparsed"

    def test_refuses_deep_nesting(self) -> None:
        raw = b'{"a": ' + b"[" * 100000 + b"]" * 100000 + b"}"
        assert code_of(json_edit.parse_strict, raw) == "unparsed"


class TestValueSpan:
    def span(self, raw: bytes, path: tuple[str | int, ...]) -> bytes:
        start, end = json_edit.value_span(raw, path)
        return raw[start:end]

    def test_object_keys_and_array_indexes(self) -> None:
        raw = b'{"a": {"b": [10, {"c": "deep"}, 30]}, "d": null}'
        assert self.span(raw, ("a", "b", 1, "c")) == b'"deep"'
        assert self.span(raw, ("a", "b", 2)) == b"30"
        assert self.span(raw, ("a", "b")) == b'[10, {"c": "deep"}, 30]'
        assert self.span(raw, ("d",)) == b"null"

    def test_keys_with_dots_are_one_step(self) -> None:
        raw = b'{"modelSettings": {"us.anthropic.x-v1:0": {"effortLevel": "low"}}}'
        path = ("modelSettings", "us.anthropic.x-v1:0", "effortLevel")
        assert self.span(raw, path) == b'"low"'

    def test_string_with_brackets_and_commas_does_not_confuse_the_walk(self) -> None:
        raw = b'{"a": "x]},{\\"q\\": 1", "b": 2}'
        assert self.span(raw, ("b",)) == b"2"

    def test_repeated_key_takes_the_last(self) -> None:
        raw = b'{"a": 1, "a": 2, "a": 3}'
        assert self.span(raw, ("a",)) == b"3"

    def test_repeated_parent_takes_the_last_parent(self) -> None:
        raw = b'{"p": {"k": 1, "z": 5}, "p": {"k": 2}}'
        assert self.span(raw, ("p", "k")) == b"2"
        assert code_of(json_edit.value_span, raw, ("p", "z")) == "key_missing"

    def test_offsets_are_bytes_after_multibyte_text(self) -> None:
        raw = '{"né": "日本", "k": "v"}'.encode()
        start, end = json_edit.value_span(raw, ("k",))
        assert raw[start:end] == b'"v"'
        start, end = json_edit.value_span(raw, ("né",))
        assert raw[start:end] == '"日本"'.encode()

    def test_missing_pieces_raise_key_missing(self) -> None:
        raw = b'{"a": [1, 2], "b": "s", "c": {"d": 1}}'
        for path in (
            ("zz",),
            ("a", 2),
            ("a", -1),
            ("a", "x"),
            ("b", "x"),
            ("b", 0),
            ("c", 0),
            ("a", 0, "q"),
            ("c", "d", "e"),
        ):
            assert code_of(json_edit.value_span, raw, path) == "key_missing", path

    def test_bad_step_types_raise_key_missing(self) -> None:
        raw = b'{"a": [1, 2]}'
        for path in (("a", True), ("a", 1.0), ("a", None), (None,)):
            assert code_of(json_edit.value_span, raw, path) == "key_missing", path

    def test_unparsed_input_raises_unparsed(self) -> None:
        assert code_of(json_edit.value_span, b'{"a": 1,}', ("a",)) == "unparsed"


class TestReplaceValue:
    def check_outside_untouched(
        self, raw: bytes, path: tuple[str | int, ...], value: object
    ) -> bytes:
        start, end = json_edit.value_span(raw, path)
        new = json_edit.replace_value(raw, path, value)
        assert raw[:start] == new[:start]
        assert raw[end:] == new[len(new) - (len(raw) - end) :]
        return new

    def test_replaces_only_the_span(self) -> None:
        raw = b'{\n  "effortLevel": "low",\n  "other": 1\n}\n'
        new = self.check_outside_untouched(raw, ("effortLevel",), "high")
        assert new == b'{\n  "effortLevel": "high",\n  "other": 1\n}\n'

    def test_crlf(self) -> None:
        raw = b'{\r\n  "a": "x",\r\n  "b": [1,\r\n 2]\r\n}\r\n'
        new = self.check_outside_untouched(raw, ("a",), "y")
        assert new == b'{\r\n  "a": "y",\r\n  "b": [1,\r\n 2]\r\n}\r\n'

    def test_tabs(self) -> None:
        raw = b'{\n\t"a": {\n\t\t"b": "x"\n\t}\n}\n'
        new = self.check_outside_untouched(raw, ("a", "b"), "y")
        assert new == b'{\n\t"a": {\n\t\t"b": "y"\n\t}\n}\n'

    def test_no_trailing_newline(self) -> None:
        raw = b'{"a": "x"}'
        assert self.check_outside_untouched(raw, ("a",), "y") == b'{"a": "y"}'

    def test_minified(self) -> None:
        raw = b'{"a":{"b":[1,2,{"c":"x"}],"d":3},"e":"z"}'
        new = self.check_outside_untouched(raw, ("a", "b", 2, "c"), "y")
        assert new == b'{"a":{"b":[1,2,{"c":"y"}],"d":3},"e":"z"}'

    def test_duplicate_keys_edit_the_last(self) -> None:
        raw = b'{"a": "first", "a": "second"}'
        new = self.check_outside_untouched(raw, ("a",), "new")
        assert new == b'{"a": "first", "a": "new"}'
        assert json.loads(new)["a"] == "new"

    def test_unicode_escapes_elsewhere_stay_as_written(self) -> None:
        raw = b'{"n": "caf\\u00e9 \\ud83d\\ude00", "a": "x", "\\u006b": 1.50e+2}'
        new = self.check_outside_untouched(raw, ("a",), "y")
        assert (
            new == b'{"n": "caf\\u00e9 \\ud83d\\ude00", "a": "y", "\\u006b": 1.50e+2}'
        )

    def test_number_spelling_elsewhere_stays_as_written(self) -> None:
        raw = b'{"a": 1.0, "b": 1E5, "c": -0, "d": "x"}'
        new = self.check_outside_untouched(raw, ("d",), "y")
        assert new == b'{"a": 1.0, "b": 1E5, "c": -0, "d": "y"}'

    def test_new_span_is_json_dumps_of_the_value(self) -> None:
        raw = b'{"a": "x"}'
        for value in (
            "café",
            'q"uote\n',
            5,
            1.5,
            True,
            None,
            [1, "b"],
            {"k": "v"},
            "😀",
        ):
            new = json_edit.replace_value(raw, ("a",), value)
            assert new == b'{"a": ' + json.dumps(value).encode("ascii") + b"}"
            assert json.loads(new)["a"] == value

    def test_replaces_a_container_with_a_scalar_and_back(self) -> None:
        raw = b'{"a": {"b": [1, 2]}, "c": 1}'
        assert json_edit.replace_value(raw, ("a",), "s") == b'{"a": "s", "c": 1}'

    def test_replaces_an_array_item(self) -> None:
        raw = b'{"a": [1, 2, 3]}'
        assert json_edit.replace_value(raw, ("a", 1), 9) == b'{"a": [1, 9, 3]}'

    def test_multibyte_text_before_the_span(self) -> None:
        raw = '{"日": "本", "a": "x"}'.encode()
        new = self.check_outside_untouched(raw, ("a",), "y")
        assert new == '{"日": "本", "a": "y"}'.encode()

    def test_missing_key_refuses(self) -> None:
        assert code_of(json_edit.replace_value, b'{"a": 1}', ("b",), 1) == "key_missing"

    def test_unparsed_file_refuses(self) -> None:
        assert code_of(json_edit.replace_value, b'{"a": 1,}', ("a",), 1) == "unparsed"
        raw = b'\xef\xbb\xbf{"a": 1}'
        assert code_of(json_edit.replace_value, raw, ("a",), 1) == "unparsed"

    def test_a_nan_in_the_file_fails_the_oracle(self) -> None:
        raw = b'{"a": NaN, "b": "x"}'
        assert code_of(json_edit.replace_value, raw, ("b",), "y") == "oracle_failed"

    def test_a_value_json_cannot_write_refuses(self) -> None:
        raw = b'{"a": "x"}'
        assert (
            code_of(json_edit.replace_value, raw, ("a",), object()) == "oracle_failed"
        )
        assert (
            code_of(json_edit.replace_value, raw, ("a",), float("nan"))
            == "oracle_failed"
        )

    def test_input_is_not_changed(self) -> None:
        raw = b'{"a": "x"}'
        json_edit.replace_value(raw, ("a",), "y")
        assert raw == b'{"a": "x"}'


class TestOracle:
    OLD = b'{"a": "x", "b": [1, 2]}'

    def good(self) -> tuple[int, int, bytes]:
        start, end = json_edit.value_span(self.OLD, ("a",))
        return start, end, self.OLD[:start] + b'"y"' + self.OLD[end:]

    def oracle(
        self, new: bytes, start: int, end: int, path: tuple[str, ...], value: object
    ) -> str:
        return code_of(json_edit._oracle, self.OLD, new, start, end, path, value)

    def test_accepts_a_correct_edit(self) -> None:
        start, end, new = self.good()
        json_edit._oracle(self.OLD, new, start, end, ("a",), "y")

    def test_refuses_a_changed_prefix(self) -> None:
        start, end, new = self.good()
        assert self.oracle(b"[" + new[1:], start, end, ("a",), "y") == "oracle_failed"

    def test_refuses_a_changed_tail(self) -> None:
        start, end, new = self.good()
        assert self.oracle(new[:-2] + b" }", start, end, ("a",), "y") == "oracle_failed"

    def test_refuses_a_whitespace_only_change_outside_the_span(self) -> None:
        start, end, new = self.good()
        bad = new.replace(b'"b"', b' "b"')
        assert self.oracle(bad, start, end, ("a",), "y") == "oracle_failed"

    def test_refuses_when_the_value_is_not_what_was_asked(self) -> None:
        start, end, new = self.good()
        assert self.oracle(new, start, end, ("a",), "z") == "oracle_failed"

    def test_refuses_when_the_new_bytes_do_not_parse(self) -> None:
        start, end, _ = self.good()
        bad = self.OLD[:start] + b'"y' + self.OLD[end:]
        assert self.oracle(bad, start, end, ("a",), "y") == "oracle_failed"

    def test_refuses_a_second_changed_value(self) -> None:
        start, end, new = self.good()
        bad = new.replace(b"[1, 2]", b"[1, 3]")
        assert self.oracle(bad, start, end, ("a",), "y") == "oracle_failed"

    def test_refuses_a_bad_path(self) -> None:
        start, end, new = self.good()
        assert self.oracle(new, start, end, ("q", "r"), "y") == "oracle_failed"

    def test_replace_value_never_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Break the oracle's view of the span and check the error comes out, not a result.
        def broken(_raw: bytes, _path: tuple[str | int, ...]) -> tuple[int, int]:
            return (1, 2)

        monkeypatch.setattr(json_edit, "value_span", broken)
        assert (
            code_of(json_edit.replace_value, self.OLD, ("a",), "y") == "oracle_failed"
        )


MARKERS = (
    "MARK1",
    "MARK2",
    "MARK3",
    "MARK4",
    "MARK5",
    "MARK6",
    "MARK7",
    "MARK8",
    "MARK9",
    "MARKA",
    "MARKB",
    "MARKC",
)


class TestMaskText:
    def test_repeated_secret_key_loses_both_values(self) -> None:
        out = json_edit.mask_text('{"X_TOKEN":"first","X_TOKEN":"second"}')
        assert out == '{"X_TOKEN":"hidden","X_TOKEN":"hidden"}'

    def test_secret_name_hides_any_type(self) -> None:
        text = '{"API_KEY": {"a": 1, "b": [2]}, "MY_SECRET": [1, 2], "PASSWORD": 5, "AUTH": null, "CREDENTIAL": true}'
        out = json.loads(json_edit.mask_text(text))
        for key in ("API_KEY", "MY_SECRET", "PASSWORD", "AUTH", "CREDENTIAL"):
            assert out[key] == "hidden", key

    def test_secret_names_match_in_any_case(self) -> None:
        out = json.loads(
            json_edit.mask_text('{"my_token": "a", "ApiKey": "b", "x": "c"}')
        )
        assert out == {"my_token": "hidden", "ApiKey": "hidden", "x": "c"}

    def test_secret_prefix_hides_the_string(self) -> None:
        text = '{"a": "sk-abc", "b": " SK-abc", "c": "Bearer x", "d": "bearer x", "e": "ok"}'
        out = json.loads(json_edit.mask_text(text))
        assert out == {
            "a": "hidden",
            "b": "hidden",
            "c": "hidden",
            "d": "hidden",
            "e": "ok",
        }

    def test_escaped_names_and_values_compare_decoded(self) -> None:
        out = json.loads(
            json_edit.mask_text(
                '{"X_\\u0054OKEN": "v", "p": "\\u0073k-abc", "q": "ok"}'
            )
        )
        assert out == {"X_TOKEN": "hidden", "p": "hidden", "q": "ok"}

    def test_list_items_follow_the_lists_name(self) -> None:
        text = '{"TOKENS": ["a", ["b"]], "plain": ["sk-1", "ok", {"AUTH": "z", "k": "v"}, ["Bearer q"]]}'
        out = json.loads(json_edit.mask_text(text))
        assert out["TOKENS"] == "hidden"
        assert out["plain"] == [
            "hidden",
            "ok",
            {"AUTH": "hidden", "k": "v"},
            ["hidden"],
        ]

    def test_nested_objects(self) -> None:
        text = '{"a": {"b": {"c_key": "v", "d": "sk-q", "e": 1}}}'
        out = json.loads(json_edit.mask_text(text))
        assert out == {"a": {"b": {"c_key": "hidden", "d": "hidden", "e": 1}}}

    def test_non_secret_text_is_unchanged(self) -> None:
        text = '{\r\n\t"a": [1,\r\n  2.50, "x"],\r\n  "b": {}\r\n}'
        assert json_edit.mask_text(text) == text

    def test_line_breaks_inside_a_hidden_span_are_kept_in_spelling(self) -> None:
        for brk in ("\n", "\r\n", "\r"):
            text = (
                '{"SECRET": {'
                + brk
                + '"a": 1,'
                + brk
                + '"b": [2,'
                + brk
                + "3]"
                + brk
                + '}, "k": 1}'
            )
            out = json_edit.mask_text(text)
            assert out == '{"SECRET": "hidden"' + brk * 4 + ', "k": 1}'
            assert text.count(brk) == out.count(brk)
            assert json.loads(out) == {"SECRET": "hidden", "k": 1}

    def test_line_count_is_kept(self) -> None:
        text = '{\n  "A_TOKEN": {\n    "x": 1\n  },\n  "b": [\n    "sk-1"\n  ]\n}\n'
        out = json_edit.mask_text(text)
        assert len(re.split(r"\r\n|\n|\r", text)) == len(re.split(r"\r\n|\n|\r", out))
        assert text.count("\n") == out.count("\n")

    def test_masked_fixtures_match_the_read_sides_masker(self) -> None:
        pairs = fixture_texts()
        assert pairs
        for path, text in pairs:
            assert masking.mask_value(json.loads(text)) == json.loads(
                json_edit.mask_text(text)
            ), path

    def test_masked_samples_match_the_read_sides_masker(self) -> None:
        samples = [
            '{"env": {"ANTHROPIC_API_KEY": "sk-x", "FOO": "bar", "N": 1}, "list": ["a", "Bearer b", ["sk-z"]]}',
            '{"a": [{"TOKEN": [1]}, {"b": "sk-1"}], "AUTH": {"x": [1, 2]}, "n": null, "t": true, "f": 1.5e3}',
            '{"X_TOKEN":"first","X_TOKEN":"second","y":1,"y":"sk-2"}',
            "{}",
            '{"a": [], "b": {}, "KEY": []}',
            '{"u": "https://user:pw123@host/x", "v": "see https://tok@h/ and ftp://a:b@c/d"}',
            '{"args": ["--token", "abc", "--ok", "x", "--api-key=zz", "Bearer q", ["--token", "n"], {"k": "v"}]}',
            '{"args": ["--token"]}',
            '{"args": ["--token", "--password", "x", "y"]}',
            '{"ARGS": ["--secret", "s1"], "other": ["--secret", "s2"]}',
        ]
        for text in samples:
            assert masking.mask_value(json.loads(text)) == json.loads(
                json_edit.mask_text(text)
            ), text

    def test_url_userinfo_and_secret_flag_values_are_hidden(self) -> None:
        text = (
            '{"url": "https://me:hunter2@proxy.example/v1", '
            '"args": ["--token", "tok-planted-1", "--password=planted-2"]}'
        )
        out = json_edit.mask_text(text)
        assert "hunter2" not in out
        assert "planted" not in out
        assert json.loads(out) == {
            "url": "https://me:hidden@proxy.example/v1",
            "args": ["--token", "hidden", "--password=hidden"],
        }

    def test_no_marker_survives_in_the_output(self) -> None:
        m = MARKERS
        text = (
            "{\n"
            '  "X_TOKEN": "' + m[0] + '",\n'
            '  "X_TOKEN": "' + m[1] + '",\n'
            '  "plain": "sk-' + m[2] + '",\n'
            '  "plain": "Bearer ' + m[3] + '",\n'
            '  "nested": {"deep": {"API_KEY": {"inner": "'
            + m[4]
            + '"}, "v": "sk-'
            + m[5]
            + '"}},\n'
            '  "list": ["sk-'
            + m[6]
            + '", ["Bearer '
            + m[7]
            + '"], {"SECRET": ["'
            + m[8]
            + '"]}],\n'
            '  "TOKENS": ["' + m[9] + '", {"a": "' + m[10] + '"}],\n'
            '  "keep": [{"PASSWORD": "' + m[11] + '"}, "visible"]\n'
            "}\n"
        )
        json.loads(text)
        out = json_edit.mask_text(text)
        for marker in m:
            assert marker not in out, marker
        assert "visible" in out

    def test_no_marker_survives_in_any_diff(self) -> None:
        m = MARKERS
        before = (
            "{\n"
            '  "effortLevel": "low",\n'
            '  "X_TOKEN": "' + m[0] + '",\n'
            '  "X_TOKEN": "' + m[1] + '",\n'
            '  "env": {"A": "sk-' + m[2] + '", "API_KEY": {"i": "' + m[3] + '"}},\n'
            '  "list": ["Bearer ' + m[4] + '", {"SECRET": ["' + m[5] + '"]}]\n'
            "}\n"
        )
        after = before.replace('"low"', '"high"')
        after2 = after.replace(m[0], "OTHER1").replace(m[2], "OTHER2")
        for a, b in ((before, after), (before, after2), (after2, before)):
            blob = json.dumps(json_edit.structured_diff(a, b, "settings.json"))
            for marker in m[:6]:
                assert marker not in blob, marker
            for marker in ("OTHER1", "OTHER2"):
                assert marker not in blob, marker


class TestStructuredDiff:
    def test_equal_texts_give_no_hunks(self) -> None:
        text = '{\n  "a": 1\n}\n'
        assert json_edit.structured_diff(text, text, "f.json") == {
            "file_display": "f.json",
            "hunks": [],
        }

    def test_shape_and_line_numbers(self) -> None:
        before = '{\n  "a": "x",\n  "b": 1\n}\n'
        after = '{\n  "a": "y",\n  "b": 1\n}\n'
        diff = json_edit.structured_diff(before, after, "~/.claude/settings.json")
        assert diff["file_display"] == "~/.claude/settings.json"
        assert len(diff["hunks"]) == 1
        lines = diff["hunks"][0]["lines"]
        assert lines == [
            {"kind": "context", "old_line": 1, "new_line": 1, "text": "{"},
            {"kind": "del", "old_line": 2, "new_line": None, "text": '  "a": "x",'},
            {"kind": "add", "old_line": None, "new_line": 2, "text": '  "a": "y",'},
            {"kind": "context", "old_line": 3, "new_line": 3, "text": '  "b": 1'},
            {"kind": "context", "old_line": 4, "new_line": 4, "text": "}"},
        ]  # fmt: skip
        for line in lines:
            assert set(line) == {"kind", "old_line", "new_line", "text"}

    def test_three_lines_of_context_and_separate_hunks(self) -> None:
        items = ",\n".join(f'  "k{i:02d}": {i}' for i in range(30))
        before = "{\n" + items + "\n}\n"
        after = before.replace('"k02": 2', '"k02": 99').replace(
            '"k27": 27', '"k27": 99'
        )
        diff = json_edit.structured_diff(before, after, "f.json")
        assert len(diff["hunks"]) == 2
        for hunk in diff["hunks"]:
            kinds = [line["kind"] for line in hunk["lines"]]
            assert [k for k in kinds if k != "context"] == ["del", "add"]
            assert kinds.index("del") <= 3
            assert len(kinds) - 1 - kinds.index("add") == 3

    def test_line_breaks_of_every_spelling_split_lines(self) -> None:
        before = '{"a": 1,\r\n"b": 2,\r"c": 3,\n"d": 4}'
        after = before.replace('"c": 3', '"c": 9')
        lines = json_edit.structured_diff(before, after, "f")["hunks"][0]["lines"]
        assert [line["text"] for line in lines if line["kind"] != "add"] == [
            '{"a": 1,',
            '"b": 2,',
            '"c": 3,',
            '"d": 4}',
        ]
        for line in lines:
            assert not re.search(r"[\r\n]", line["text"])

    def test_added_and_removed_trailing_lines(self) -> None:
        diff = json_edit.structured_diff('{"a": 1}\n', '{"a": 1}\n\n', "f")
        lines = diff["hunks"][0]["lines"]
        assert lines[-1]["kind"] == "add"
        assert lines[-1]["text"] == ""
        assert lines[-1]["new_line"] == 2

    def test_diff_shows_masked_text_only(self) -> None:
        before = '{\n  "a": "x",\n  "API_KEY": "real-one"\n}\n'
        after = '{\n  "a": "y",\n  "API_KEY": "real-two"\n}\n'
        blob = json.dumps(json_edit.structured_diff(before, after, "f"))
        assert "real-one" not in blob
        assert "real-two" not in blob
        assert '\\"API_KEY\\": \\"hidden\\"' in blob

    def test_a_secret_edit_shows_as_no_change(self) -> None:
        before = '{\n  "API_KEY": "one"\n}\n'
        after = '{\n  "API_KEY": "two"\n}\n'
        assert json_edit.structured_diff(before, after, "f")["hunks"] == []

    def test_a_password_in_url_userinfo_never_reaches_a_diff(self) -> None:
        before = '{\n  "a": "x",\n  "ANTHROPIC_BASE_URL": "https://me:planted-one@proxy/v1"\n}\n'
        after = before.replace('"x"', '"y"').replace("planted-one", "planted-two")
        blob = json.dumps(json_edit.structured_diff(before, after, "f"))
        assert "planted" not in blob


class Edits:
    """Shared helpers: prefix and suffix bytes stay put and json.loads agrees."""

    def check_insert(
        self,
        raw: bytes,
        path: tuple[str, ...],
        value: object,
        expected: bytes | None = None,
        *,
        zero_length: bool = True,
    ) -> bytes:
        new = json_edit.insert_value(raw, path, value)
        node: Any = json.loads(new.decode("utf-8"))
        for step in path:
            node = node[step]
        assert node == value
        prefix = 0
        while prefix < min(len(raw), len(new)) and raw[prefix] == new[prefix]:
            prefix += 1
        suffix = 0
        while (
            suffix < len(raw) - prefix
            and raw[len(raw) - 1 - suffix] == new[len(new) - 1 - suffix]
        ):
            suffix += 1
        if zero_length:
            # Nothing is removed: the old bytes are a prefix plus a suffix of the new ones.
            assert prefix + suffix == len(raw)
            assert raw == new[:prefix] + new[len(new) - suffix :]
        if expected is not None:
            assert new == expected
        return new


class TestInsertValue(Edits):
    def test_pretty_lf(self) -> None:
        raw = b'{\n  "a": 1,\n  "b": "x"\n}\n'
        self.check_insert(
            raw, ("c",), "y", b'{\n  "a": 1,\n  "b": "x",\n  "c": "y"\n}\n'
        )

    def test_crlf(self) -> None:
        raw = b'{\r\n  "a": 1\r\n}\r\n'
        self.check_insert(raw, ("c",), 2, b'{\r\n  "a": 1,\r\n  "c": 2\r\n}\r\n')

    def test_tabs(self) -> None:
        raw = b'{\n\t"a": 1\n}\n'
        self.check_insert(raw, ("c",), 2, b'{\n\t"a": 1,\n\t"c": 2\n}\n')

    def test_tabs_nested_create_keeps_the_unit(self) -> None:
        raw = b'{\n\t"a": 1\n}\n'
        self.check_insert(
            raw,
            ("m", "i", "e"),
            "h",
            b'{\n\t"a": 1,\n\t"m": {\n\t\t"i": {\n\t\t\t"e": "h"\n\t\t}\n\t}\n}\n',
        )

    def test_no_trailing_newline(self) -> None:
        self.check_insert(b'{\n  "a": 1\n}', ("c",), 2, b'{\n  "a": 1,\n  "c": 2\n}')

    def test_minified(self) -> None:
        self.check_insert(b'{"a":1,"b":"x"}', ("c",), "y", b'{"a":1,"b":"x","c":"y"}')

    def test_spaced_one_line(self) -> None:
        self.check_insert(b'{ "a": 1 }', ("b",), 2, b'{ "a": 1, "b": 2 }')

    def test_unicode_escapes_elsewhere_stay(self) -> None:
        raw = b'{\n  "a": "\\u00e9\\ud83d\\ude00",\n  "b": "caf\xc3\xa9"\n}\n'
        new = self.check_insert(raw, ("c",), "é")
        assert b'"\\u00e9\\ud83d\\ude00"' in new
        assert b'"c": "\\u00e9"' in new

    def test_repeated_keys_elsewhere_stay(self) -> None:
        raw = b'{\n  "a": 1,\n  "a": 2,\n  "b": 3\n}\n'
        new = self.check_insert(raw, ("c",), 4)
        assert new.count(b'"a"') == 2

    def test_repeated_parent_takes_the_last(self) -> None:
        raw = b'{"m": {"x": 1}, "m": {"y": 2}}'
        new = self.check_insert(
            raw, ("m", "z"), 3, b'{"m": {"x": 1}, "m": {"y": 2,"z": 3}}'
        )
        assert json.loads(new)["m"] == {"y": 2, "z": 3}

    def test_deeper_pretty_member_indent(self) -> None:
        raw = b'{\n  "m": {\n    "x": 1\n  }\n}\n'
        self.check_insert(
            raw, ("m", "y"), 2, b'{\n  "m": {\n    "x": 1,\n    "y": 2\n  }\n}\n'
        )

    def test_empty_objects(self) -> None:
        cases = [
            (b"{}", b'{"k": "v"}'),
            (b"{}\n", b'{\n  "k": "v"\n}\n'),
            (b"{ }", b'{"k": "v"}'),
            (b"{\n}\n", b'{\n  "k": "v"\n}\n'),
            (b"{\r\n}\r\n", b'{\r\n  "k": "v"\r\n}\r\n'),
        ]
        for raw, expected in cases:
            self.check_insert(raw, ("k",), "v", expected, zero_length=False)

    def test_nested_empty_in_pretty_file(self) -> None:
        raw = b'{\n  "a": 1,\n  "m": {},\n  "b": 2\n}\n'
        self.check_insert(
            raw,
            ("m", "k"),
            "v",
            b'{\n  "a": 1,\n  "m": {\n    "k": "v"\n  },\n  "b": 2\n}\n',
        )

    def test_nested_empty_in_minified_file(self) -> None:
        self.check_insert(
            b'{"a":1,"m":{},"b":2}', ("m", "k"), "v", b'{"a":1,"m":{"k":"v"},"b":2}'
        )

    def test_nested_create_pretty(self) -> None:
        raw = b'{\n  "a": 1\n}\n'
        want = (
            b'{\n  "a": 1,\n  "modelSettings": {\n    "claude-opus-5-5": {\n'
            b'      "effortLevel": "high"\n    }\n  }\n}\n'
        )
        path = ("modelSettings", "claude-opus-5-5", "effortLevel")
        self.check_insert(raw, path, "high", want)

    def test_nested_create_minified(self) -> None:
        raw = b'{"a": 1}'
        want = b'{"a": 1,"modelSettings": {"claude-opus-5-5": {"effortLevel": "high"}}}'
        path = ("modelSettings", "claude-opus-5-5", "effortLevel")
        self.check_insert(raw, path, "high", want)

    def test_nested_create_with_other_names_present(self) -> None:
        raw = b'{\n  "modelSettings": {\n    "other": {\n      "effortLevel": "low"\n    }\n  }\n}\n'
        want = (
            b'{\n  "modelSettings": {\n    "other": {\n      "effortLevel": "low"\n    },\n'
            b'    "new": {\n      "effortLevel": "high"\n    }\n  }\n}\n'
        )
        self.check_insert(raw, ("modelSettings", "new", "effortLevel"), "high", want)

    def test_nested_create_with_modelsettings_empty(self) -> None:
        for raw, want in (
            (
                b'{\n  "modelSettings": {}\n}\n',
                b'{\n  "modelSettings": {\n    "new": {\n      "effortLevel": "high"\n    }\n  }\n}\n',
            ),
            (
                b'{"modelSettings":{}}',
                b'{"modelSettings":{"new":{"effortLevel":"high"}}}',
            ),
        ):
            self.check_insert(
                raw, ("modelSettings", "new", "effortLevel"), "high", want
            )

    def test_key_present_even_when_null(self) -> None:
        assert code_of(json_edit.insert_value, b'{"a": 1}', ("a",), 2) == "key_present"
        assert (
            code_of(json_edit.insert_value, b'{"a": null}', ("a",), 2) == "key_present"
        )
        raw = b'{"m": {"a": null}}'
        assert code_of(json_edit.insert_value, raw, ("m", "a"), 2) == "key_present"

    def test_parent_not_object(self) -> None:
        for bad in ('"s"', "3", "null", "[1]", "true"):
            for raw, path in (
                (f'{{"m": {bad}}}', ("m", "k")),
                (f'{{"m": {bad}}}', ("m", "i", "k")),
                (f'{{"o": {{"m": {bad}}}}}', ("o", "m", "k")),
                (f'{{"o": {{"m": {bad}}}}}', ("o", "m", "i", "k")),
            ):
                code = code_of(json_edit.insert_value, raw.encode(), path, 1)
                assert code == "parent_not_object", raw

    def test_bad_input(self) -> None:
        assert code_of(json_edit.insert_value, b"{", ("a",), 1) == "unparsed"
        assert code_of(json_edit.insert_value, b"{}", ("a",), {1, 2}) == "oracle_failed"
        raw = b'{"a": 1}'
        assert (
            code_of(json_edit.insert_value, raw, ("b",), float("nan"))
            == "oracle_failed"
        )

    def test_input_is_not_changed(self) -> None:
        raw = bytearray(b'{"a": 1}')
        json_edit.insert_value(bytes(raw), ("b",), 2)
        assert bytes(raw) == b'{"a": 1}'


class TestRemoveKey:
    RAW = b'{\n  "a": 1,\n  "b": "sk-keep",\n  "c": 3\n}\n'

    def test_first_middle_last(self) -> None:
        assert (
            json_edit.remove_key(self.RAW, ("a",))
            == b'{\n  "b": "sk-keep",\n  "c": 3\n}\n'
        )
        assert json_edit.remove_key(self.RAW, ("b",)) == b'{\n  "a": 1,\n  "c": 3\n}\n'
        assert (
            json_edit.remove_key(self.RAW, ("c",))
            == b'{\n  "a": 1,\n  "b": "sk-keep"\n}\n'
        )

    def test_only_member_leaves_empty_braces(self) -> None:
        assert json_edit.remove_key(b'{\n  "a": 1\n}', ("a",)) == b"{\n}"
        assert json_edit.remove_key(b'{ "a": [1, 2] }\n', ("a",)) == b"{ }\n"
        assert json_edit.remove_key(b'{"a": 1}', ("a",)) == b"{}"

    def test_crlf_and_tabs(self) -> None:
        raw = b'{\r\n  "a": 1,\r\n  "b": 2\r\n}\r\n'
        assert json_edit.remove_key(raw, ("b",)) == b'{\r\n  "a": 1\r\n}\r\n'
        assert (
            json_edit.remove_key(b'{\n\t"a": 1,\n\t"b": 2\n}\n', ("a",))
            == b'{\n\t"b": 2\n}\n'
        )

    def test_minified(self) -> None:
        raw = b'{"a":1,"b":2,"c":3}'
        assert json_edit.remove_key(raw, ("b",)) == b'{"a":1,"c":3}'
        assert json_edit.remove_key(raw, ("a",)) == b'{"b":2,"c":3}'
        assert json_edit.remove_key(raw, ("c",)) == b'{"a":1,"b":2}'

    def test_nested_parent_stays_as_empty_object(self) -> None:
        raw = b'{\n  "name": {\n    "only": 1\n  },\n  "z": 2\n}\n'
        assert (
            json_edit.remove_key(raw, ("name", "only"))
            == b'{\n  "name": {},\n  "z": 2\n}\n'
        )

    def test_removing_a_container_value(self) -> None:
        raw = b'{"a": {"x": [1, {"y": 2}]}, "b": 1}'
        assert json_edit.remove_key(raw, ("a",)) == b'{"b": 1}'

    def test_repeated_key_refuses(self) -> None:
        assert (
            code_of(json_edit.remove_key, b'{"a": 1, "a": 2}', ("a",)) == "repeated_key"
        )
        raw = b'{"m": {"a": 1, "b": 0, "a": 2}}'
        assert code_of(json_edit.remove_key, raw, ("m", "a")) == "repeated_key"

    def test_key_missing(self) -> None:
        for raw, path in (
            (b'{"a": 1}', ("b",)),
            (b'{"a": 1}', ("a", "b")),
            (b'{"a": null}', ("a", "b")),
            (b'{"a": [1]}', ("a", "b")),
            (b'{"a": {}}', ("a", "b")),
            (b'{"a": 1}', ("x", "b")),
            (b'{"a": 1}', ()),
        ):
            assert code_of(json_edit.remove_key, raw, path) == "key_missing", (
                raw,
                path,
            )

    def test_secret_bytes_elsewhere_stay(self) -> None:
        raw = b'{"API_KEY": "sk-planted-1", "x": 1, "inner": {"TOKEN": "sk-planted-2", "y": 2}}'
        new = json_edit.remove_key(raw, ("inner", "y"))
        assert b"sk-planted-1" in new
        assert b"sk-planted-2" in new
        assert (
            new
            == b'{"API_KEY": "sk-planted-1", "x": 1, "inner": {"TOKEN": "sk-planted-2"}}'
        )

    def test_unparsed_refuses(self) -> None:
        assert code_of(json_edit.remove_key, b'{"a": 1,}', ("a",)) == "unparsed"


class TestSharedOracle:
    def test_tampered_insert_span_fails(self) -> None:
        old = b'{"a": 1}'
        new = json_edit.insert_value(old, ("b",), 2)

        def edit(expected: dict[str, Any]) -> None:
            expected["b"] = 2

        json_edit._oracle(old, new, 7, 7, ("b",), 2, edit=edit)
        for bad in (
            new.replace(b"2", b"3"),
            new.replace(b'"a"', b'"q"'),
            new + b" ",
            b"[" + new[1:],
        ):
            assert (
                code_of(json_edit._oracle, old, bad, 7, 7, ("b",), 2, edit)
                == "oracle_failed"
            )

    def test_tampered_remove_span_fails(self) -> None:
        old = b'{"a": 1, "b": 2, "c": 3}'
        new = json_edit.remove_key(old, ("b",))

        def edit(expected: dict[str, Any]) -> None:
            del expected["b"]

        json_edit._oracle(old, new, 8, 16, ("b",), None, edit=edit)
        for bad in (new.replace(b"3", b"4"), old, new.replace(b'"a"', b'"d"')):
            code = code_of(json_edit._oracle, old, bad, 8, 16, ("b",), None, edit)
            assert code == "oracle_failed"

    def test_edit_that_raises_fails_closed(self) -> None:
        def edit(_expected: dict[str, Any]) -> None:
            raise KeyError("x")

        code = code_of(
            json_edit._oracle, b'{"a": 1}', b'{"a": 1}', 0, 0, ("a",), 1, edit
        )
        assert code == "oracle_failed"

    def test_insert_and_remove_never_fall_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(*_args: object, **_kwargs: object) -> None:
            raise json_edit.Refused("oracle_failed")

        monkeypatch.setattr(json_edit, "_oracle", refuse)
        assert code_of(json_edit.insert_value, b"{}", ("a",), 1) == "oracle_failed"
        assert code_of(json_edit.remove_key, b'{"a": 1}', ("a",)) == "oracle_failed"


class TestNewFile:
    def test_flat(self) -> None:
        assert (
            json_edit.new_file(("effortLevel",), "high")
            == b'{\n  "effortLevel": "high"\n}\n'
        )

    def test_nested(self) -> None:
        want = (
            b'{\n  "modelSettings": {\n    "claude-opus-5-5": {\n      "effortLevel": "high"\n'
            b"    }\n  }\n}\n"
        )
        raw = json_edit.new_file(
            ("modelSettings", "claude-opus-5-5", "effortLevel"), "high"
        )
        assert raw == want
        assert json.loads(raw.decode("utf-8")) == {
            "modelSettings": {"claude-opus-5-5": {"effortLevel": "high"}}
        }

    def test_bad_input(self) -> None:
        assert code_of(json_edit.new_file, ("a",), {1}) == "oracle_failed"
        assert code_of(json_edit.new_file, ("a",), float("nan")) == "oracle_failed"


class TestMaskingAfterEdits:
    def blob(self, before: str, after: str) -> str:
        return json.dumps(json_edit.structured_diff(before, after, "f.json"))

    def check(self, before_raw: bytes, path: tuple[str, ...], value: object) -> None:
        after_raw = json_edit.insert_value(before_raw, path, value)
        blob = self.blob(before_raw.decode(), after_raw.decode())
        assert "sk-planted-" not in blob
        assert "hidden" in blob
        assert path[-1] in blob

    def test_secret_as_last_member_one_line(self) -> None:
        self.check(b'{"a": 1, "API_KEY": "sk-planted-1"}', ("effortLevel",), "high")

    def test_secret_as_last_member_across_lines(self) -> None:
        self.check(
            b'{\n  "a": 1,\n  "API_KEY": "sk-planted-\\n1"\n}\n',
            ("effortLevel",),
            "high",
        )
        self.check(
            b'{\n  "a": 1,\n  "TOKEN": {\n    "x": "sk-planted-1"\n  }\n}\n',
            ("effortLevel",),
            "high",
        )

    def test_secret_valued_string_as_last_member(self) -> None:
        self.check(
            b'{\n  "a": 1,\n  "plain": "sk-planted-1"\n}\n', ("effortLevel",), "high"
        )

    def test_repeated_secret_key_in_the_parent(self) -> None:
        raw = b'{\n  "m": {\n    "API_KEY": "sk-planted-1",\n    "API_KEY": "sk-planted-2"\n  }\n}\n'
        self.check(raw, ("m", "effortLevel"), "high")

    def test_nested_create_next_to_a_secret(self) -> None:
        self.check(
            b'{"API_KEY": "sk-planted-1"}',
            ("modelSettings", "id", "effortLevel"),
            "high",
        )

    def test_remove_next_to_a_secret(self) -> None:
        raw = b'{\n  "API_KEY": "sk-planted-1",\n  "effortLevel": "high",\n  "TOKEN": "sk-planted-2"\n}\n'
        after = json_edit.remove_key(raw, ("effortLevel",))
        blob = self.blob(raw.decode(), after.decode())
        assert "sk-planted-" not in blob
        assert "effortLevel" in blob


class TestNewFileDiff:
    def test_none_before_gives_only_add_lines(self) -> None:
        text = json_edit.new_file(("effortLevel",), "high").decode()
        diff = json_edit.structured_diff(None, text, "settings.json")
        assert diff["file_display"] == "settings.json"
        lines = [line for hunk in diff["hunks"] for line in hunk["lines"]]
        assert len(lines) == 3
        for number, line in enumerate(lines, 1):
            assert line == {
                "kind": "add",
                "old_line": None,
                "new_line": number,
                "text": line["text"],
            }
        assert [line["text"] for line in lines] == ["{", '  "effortLevel": "high"', "}"]

    def test_none_before_masks_the_after_text(self) -> None:
        diff = json_edit.structured_diff(
            None, '{\n  "API_KEY": "sk-planted-1"\n}\n', "f"
        )
        assert "sk-planted-" not in json.dumps(diff)


class TestGoneFileDiff:
    def test_none_after_gives_only_del_lines(self) -> None:
        text = json_edit.new_file(("effortLevel",), "high").decode()
        diff = json_edit.structured_diff(text, None, "settings.json")
        assert diff["file_display"] == "settings.json"
        lines = [line for hunk in diff["hunks"] for line in hunk["lines"]]
        assert len(lines) == 3
        for number, line in enumerate(lines, 1):
            assert line == {
                "kind": "del",
                "old_line": number,
                "new_line": None,
                "text": line["text"],
            }
        assert [line["text"] for line in lines] == ["{", '  "effortLevel": "high"', "}"]

    def test_none_after_masks_the_before_text(self) -> None:
        diff = json_edit.structured_diff(
            '{\n  "API_KEY": "sk-planted-1"\n}\n', None, "f"
        )
        assert "sk-planted-" not in json.dumps(diff)
        assert "hidden" in json.dumps(diff)

    def test_both_none_is_an_empty_diff(self) -> None:
        assert json_edit.structured_diff(None, None, "f") == {
            "file_display": "f",
            "hunks": [],
        }

    def test_mask_text_is_called_only_for_a_side_that_has_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[str] = []
        real = json_edit.mask_text

        def spy(text: str) -> str:
            seen.append(text)
            return real(text)

        monkeypatch.setattr(json_edit, "mask_text", spy)
        json_edit.structured_diff(None, None, "f")
        assert seen == []
        json_edit.structured_diff("{}\n", None, "f")
        json_edit.structured_diff(None, "{}\n", "f")
        assert seen == ["{}\n", "{}\n"]


class TestPurity:
    def test_module_source_has_no_file_calls(self) -> None:
        source = Path(json_edit.__file__).read_text(encoding="utf-8")
        for banned in (
            r"\bopen\(",
            r"\.write\(",
            r"\.writelines\(",
            r"\bshutil\b",
            r"\btempfile\b",
            r"\bpathlib\b",
            r"\bsubprocess\b",
            r"os\.(remove|unlink|rename|replace|mkdir|makedirs|rmdir|utime|chmod|symlink|link|truncate|environ|path\.expanduser)\b",
        ):
            assert re.search(banned, source) is None, banned

    def test_edits_leave_the_cwd_and_environment_alone(self) -> None:
        import os

        before = (Path.cwd(), dict(os.environ))
        json_edit.replace_value(b'{"a": "x"}', ("a",), "y")
        json_edit.mask_text('{"a": "sk-1"}')
        json_edit.structured_diff('{"a": 1}', '{"a": 2}', "f")
        assert before == (Path.cwd(), dict(os.environ))
