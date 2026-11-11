"""Tests for ``json_edit``: find a value's bytes, splice it, mask, diff.

The module is pure, so these tests only pass bytes in and read bytes out. The old
suite is ported whole in task a4. These cover each public function and each refusal.
"""

import json

import pytest

import json_edit
from json_edit import Refused

PRETTY = b'{\n  "model": "opus",\n  "env": {\n    "A": "1"\n  }\n}\n'
UGLY = b'{"model":"opus","env":{"A":"1"}}'


def code_of(call: object) -> str:
    """Run a callable that must refuse, and return the refusal's code."""
    assert callable(call)
    with pytest.raises(Refused) as caught:
        call()
    return caught.value.code


# parse_strict


def test_parse_strict_returns_text_and_data() -> None:
    text, data = json_edit.parse_strict(PRETTY)
    assert text == PRETTY.decode()
    assert data == {"model": "opus", "env": {"A": "1"}}


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"[1]",
        b'{"a": 1,}',
        b'{"a": 1} // note',
        b'\xef\xbb\xbf{"a": 1}',
        b"\xff\xfe",
        b'{"a": NaN, "b": ',
        b"[" * 5000 + b"]" * 5000,
    ],
)
def test_parse_strict_refuses_what_json_loads_refuses(raw: bytes) -> None:
    assert code_of(lambda: json_edit.parse_strict(raw)) == "unparsed"


def test_parse_strict_refuses_a_non_bytes_value() -> None:
    assert code_of(lambda: json_edit.parse_strict("text")) == "unparsed"  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


# value_span


def test_value_span_gives_byte_offsets_with_multibyte_text() -> None:
    raw = '{"note": "café", "model": "opus"}'.encode()
    start, end = json_edit.value_span(raw, ("model",))
    assert raw[start:end] == b'"opus"'


def test_value_span_takes_the_last_of_a_repeated_key() -> None:
    raw = b'{"a": 1, "a": 2}'
    start, end = json_edit.value_span(raw, ("a",))
    assert raw[start:end] == b"2"


def test_value_span_walks_arrays_and_refuses_a_missing_step() -> None:
    raw = b'{"a": [10, {"b": 3}]}'
    start, end = json_edit.value_span(raw, ("a", 1, "b"))
    assert raw[start:end] == b"3"
    assert code_of(lambda: json_edit.value_span(raw, ("a", 5))) == "key_missing"
    assert code_of(lambda: json_edit.value_span(raw, ("a", "x"))) == "key_missing"
    assert code_of(lambda: json_edit.value_span(raw, ("zz",))) == "key_missing"
    assert code_of(lambda: json_edit.value_span(raw, (True,))) == "key_missing"  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


# replace_value


def test_replace_changes_only_the_value_bytes() -> None:
    out = json_edit.replace_value(PRETTY, ("model",), "sonnet")
    assert out == PRETTY.replace(b'"opus"', b'"sonnet"')


def test_replace_a_nested_value_and_a_whole_object() -> None:
    assert json_edit.replace_value(UGLY, ("env", "A"), "2") == UGLY.replace(
        b'"1"', b'"2"'
    )
    out = json_edit.replace_value(UGLY, ("env",), {"B": 2})
    assert json.loads(out) == {"model": "opus", "env": {"B": 2}}


def test_replace_refuses_a_missing_key_and_an_unencodable_value() -> None:
    assert code_of(lambda: json_edit.replace_value(UGLY, ("nope",), 1)) == "key_missing"
    assert (
        code_of(lambda: json_edit.replace_value(UGLY, ("model",), object()))
        == "oracle_failed"
    )


def test_replace_escapes_non_ascii_so_the_file_stays_ascii() -> None:
    out = json_edit.replace_value(UGLY, ("model",), "café")
    assert out.isascii()
    assert json.loads(out)["model"] == "café"


# insert_value


def test_insert_into_a_pretty_file_keeps_its_layout() -> None:
    out = json_edit.insert_value(PRETTY, ("effortLevel",), "high")
    assert out == (
        b'{\n  "model": "opus",\n  "env": {\n    "A": "1"\n  },\n'
        b'  "effortLevel": "high"\n}\n'
    )


def test_insert_into_a_compact_file_stays_compact() -> None:
    out = json_edit.insert_value(UGLY, ("effortLevel",), "high")
    assert out == b'{"model":"opus","env":{"A":"1"},"effortLevel":"high"}'


def test_insert_makes_missing_parents_inside_one_span() -> None:
    out = json_edit.insert_value(PRETTY, ("modelSettings", "m", "effort"), "low")
    assert json.loads(out)["modelSettings"] == {"m": {"effort": "low"}}
    assert out.startswith(PRETTY[:20])
    out = json_edit.insert_value(UGLY, ("modelSettings", "m", "effort"), "low")
    assert json.loads(out)["modelSettings"] == {"m": {"effort": "low"}}


def test_insert_into_an_existing_env_object() -> None:
    out = json_edit.insert_value(PRETTY, ("env", "B"), "2")
    assert json.loads(out)["env"] == {"A": "1", "B": "2"}


def test_insert_into_an_empty_file_object_and_an_empty_nested_object() -> None:
    assert json.loads(json_edit.insert_value(b"{}", ("a",), 1)) == {"a": 1}
    spaced = json_edit.insert_value(b"{\n}\n", ("a",), 1)
    assert json.loads(spaced) == {"a": 1}
    nested = json_edit.insert_value(b'{"env": {}}', ("env", "B"), "2")
    assert json.loads(nested) == {"env": {"B": "2"}}


def test_insert_refuses_a_present_key_and_a_parent_that_is_not_an_object() -> None:
    assert (
        code_of(lambda: json_edit.insert_value(PRETTY, ("model",), "x"))
        == "key_present"
    )
    assert (
        code_of(lambda: json_edit.insert_value(PRETTY, ("model", "x"), 1))
        == "parent_not_object"
    )
    assert code_of(lambda: json_edit.insert_value(PRETTY, (), 1)) == "key_missing"
    assert code_of(lambda: json_edit.insert_value(PRETTY, ("a", 1), 1)) == "key_missing"  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    assert (
        code_of(lambda: json_edit.insert_value(PRETTY, ("a",), object()))
        == "oracle_failed"
    )


# remove_key


def test_remove_takes_one_member_and_its_comma() -> None:
    assert json_edit.remove_key(UGLY, ("model",)) == b'{"env":{"A":"1"}}'
    assert json_edit.remove_key(UGLY, ("env",)) == b'{"model":"opus"}'
    out = json_edit.remove_key(PRETTY, ("model",))
    assert json.loads(out) == {"env": {"A": "1"}}


def test_remove_the_only_key_of_a_file_or_of_a_nested_object() -> None:
    assert json.loads(json_edit.remove_key(b'{\n  "a": 1\n}\n', ("a",))) == {}
    out = json_edit.remove_key(b'{"env": {"A": "1"}}', ("env", "A"))
    assert json.loads(out) == {"env": {}}


def test_remove_refuses_missing_repeated_and_bad_paths() -> None:
    assert code_of(lambda: json_edit.remove_key(UGLY, ("nope",))) == "key_missing"
    assert code_of(lambda: json_edit.remove_key(UGLY, ("model", "x"))) == "key_missing"
    assert (
        code_of(lambda: json_edit.remove_key(b'{"a": 1, "a": 2}', ("a",)))
        == "repeated_key"
    )


# new_file


def test_new_file_is_two_space_indent_lf_and_a_final_newline() -> None:
    assert (
        json_edit.new_file(("effortLevel",), "high")
        == b'{\n  "effortLevel": "high"\n}\n'
    )
    out = json_edit.new_file(("env", "X"), "1")
    assert json.loads(out) == {"env": {"X": "1"}}
    assert out.endswith(b"\n")


def test_new_file_refuses_an_empty_path_and_an_unencodable_value() -> None:
    assert code_of(lambda: json_edit.new_file((), 1)) == "key_missing"
    assert code_of(lambda: json_edit.new_file(("a",), object())) == "oracle_failed"
    assert code_of(lambda: json_edit.new_file(("a",), float("nan"))) == "oracle_failed"


def test_same_value_is_strict_about_types_and_nan() -> None:
    assert json_edit.same_value({"a": [1, "x"]}, {"a": [1, "x"]})
    assert not json_edit.same_value(1, True)
    assert not json_edit.same_value(1, 1.0)
    assert not json_edit.same_value(float("nan"), float("nan"))
    assert not json_edit.same_value({"a": 1}, {"b": 1})
    assert not json_edit.same_value([1], [1, 2])


# mask_text and structured_diff


def test_mask_text_hides_a_secret_value_and_keeps_its_line_breaks() -> None:
    text = (
        '{\n  "apiKey": "abc",\n  "note": "sk-live",\n  "model": "opus",\n'
        '  "token": [\n    1,\n    2\n  ]\n}\n'
    )
    masked = json_edit.mask_text(text)
    assert "abc" not in masked
    assert "sk-live" not in masked
    assert '"opus"' in masked
    assert masked.count("\n") == text.count("\n")
    assert json.loads(masked)["apiKey"] == "hidden"
    assert json.loads(masked)["token"] == "hidden"  # noqa: S105


def test_mask_text_hides_every_repeated_key() -> None:
    masked = json_edit.mask_text('{"secret": "a", "secret": "b"}')
    assert "a" not in masked.replace("secret", "").replace("hidden", "")
    assert masked.count("hidden") == 2


def test_structured_diff_numbers_lines_and_masks_both_sides() -> None:
    before = '{\n  "model": "opus",\n  "apiKey": "one"\n}\n'
    after = '{\n  "model": "sonnet",\n  "apiKey": "two"\n}\n'
    diff = json_edit.structured_diff(before, after, "settings.json")
    assert diff["file_display"] == "settings.json"
    lines = diff["hunks"][0]["lines"]
    kinds = [(line["kind"], line["old_line"], line["new_line"]) for line in lines]
    assert ("del", 2, None) in kinds
    assert ("add", None, 2) in kinds
    shown = json.dumps(diff)
    assert "one" not in shown
    assert "two" not in shown


def test_structured_diff_of_a_new_file_and_a_file_that_goes() -> None:
    created = json_edit.structured_diff(None, '{\n  "a": 1\n}\n', "f")
    assert [line["kind"] for line in created["hunks"][0]["lines"]] == ["add"] * 3
    gone = json_edit.structured_diff('{\n  "a": 1\n}\n', None, "f")
    assert [line["kind"] for line in gone["hunks"][0]["lines"]] == ["del"] * 3
    same = json_edit.structured_diff("{}\n", "{}\n", "f")
    assert same["hunks"] == []
