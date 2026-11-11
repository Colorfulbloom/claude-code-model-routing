"""Property tests for the write core's pure parts (task a4, hypothesis).

Four properties.

- ``replace_value``, ``insert_value`` and ``remove_key`` keep every byte outside their
  span, on files written with any indent, separator, line break and escaping.
- ``parse_strict`` accepts exactly what ``json.loads`` accepts as an object, and gives
  the same data.
- ``mask_text`` and ``structured_diff`` never show a planted secret, and the masked
  text parses to what the read side's masker gives.
- ``canonical_body`` and ``choice_key`` ignore key order, ``seq``, ``version`` and
  ``request_id``, and change with every field that makes up the choice.

``BARTAB_PROP_EXAMPLES`` raises the number of examples for a longer hunt. The default
run is derandomized, so CI sees the same examples every time.
"""

# ruff: noqa: PLR0913, PLR0917, S311 - a property takes one argument per drawn part,
# and the shuffle only needs to vary, never to be secret.

import json
import os
import random
import re
from typing import Any, cast

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn, SearchStrategy

import edit_store
import json_edit
import masking
from models import EditPreviewRequest, EditSaveRequest

EXAMPLES = int(os.environ.get("BARTAB_PROP_EXAMPLES", "200"))
PROPS = settings(
    max_examples=EXAMPLES,
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

KeyPath = tuple[str | int, ...]

# JSON building blocks. NaN and infinity are left out because ``json.dumps`` writes them
# as names that strict JSON refuses, and the oracle compares values with ``==``.
_TEXT = st.text(max_size=12)
_KEYS = st.one_of(
    st.sampled_from(
        ["model", "env", "a", "b.c", "x y", "effortLevel", "modelSettings", "k-1", ""]
    ),
    st.text(alphabet="abcxyz.-_ é日", min_size=0, max_size=6),
)
_SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**12), max_value=10**12),
    st.floats(allow_nan=False, allow_infinity=False),
    _TEXT,
)


def _values(depth: int = 3) -> SearchStrategy[Any]:
    if depth == 0:
        return _SCALARS
    inner = _values(depth - 1)
    return st.one_of(
        _SCALARS,
        st.lists(inner, max_size=3),
        st.dictionaries(_KEYS, inner, max_size=3),
    )


VALUES = _values()
OBJECTS = st.dictionaries(_KEYS, VALUES, max_size=5)


@st.composite
def layouts(draw: DrawFn) -> tuple[str | None, tuple[str, str], bool, str, bool, bool]:
    """How a file is written: indent, separators, ASCII escaping, break and ending."""
    indent = draw(st.sampled_from([None, 0, 1, 2, 4, "\t"]))
    separators = draw(
        st.sampled_from([(", ", ": "), (",", ":"), (", ", ":"), (",", ": ")])
    )
    ensure_ascii = draw(st.booleans())
    line_break = draw(st.sampled_from(["\n", "\r\n", "\r"]))
    final_break = draw(st.booleans())
    return (
        cast("str | None", indent),
        separators,
        ensure_ascii,
        line_break,
        final_break,
        draw(st.booleans()),
    )


def render(obj: Any, layout: tuple[Any, ...]) -> bytes:
    """Write ``obj`` as a person's editor might have, in the given layout."""
    indent, separators, ensure_ascii, line_break, final_break, leading_space = layout
    text = json.dumps(
        obj, indent=indent, separators=separators, ensure_ascii=ensure_ascii
    )
    if indent is not None:
        text = text.replace("\n", line_break)
    if leading_space:
        text = "  " + text
    if final_break:
        text += line_break
    return text.encode("utf-8")


def all_paths(node: Any, prefix: KeyPath = ()) -> list[KeyPath]:
    """Every path to a value in ``node``, the root excluded."""
    found: list[KeyPath] = []
    if isinstance(node, dict):
        for key, value in cast("dict[str, Any]", node).items():
            found.append((*prefix, key))
            found.extend(all_paths(value, (*prefix, key)))
    elif isinstance(node, list):
        for index, value in enumerate(cast("list[Any]", node)):
            found.append((*prefix, index))
            found.extend(all_paths(value, (*prefix, index)))
    return found


def key_paths(node: Any, prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Every path made only of object keys, through objects only."""
    found: list[tuple[str, ...]] = []
    if isinstance(node, dict):
        for key, value in cast("dict[str, Any]", node).items():
            found.append((*prefix, key))
            found.extend(key_paths(value, (*prefix, key)))
    return found


def get_at(node: Any, path: KeyPath) -> Any:
    for step in path:
        node = node[step]
    return node


def commonprefix(a: bytes, b: bytes) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def is_pure_insertion(old: bytes, new: bytes) -> bool:
    """True when ``new`` is ``old`` plus one run of added bytes, and nothing else."""
    p = commonprefix(old, new)
    return len(new) >= len(old) and new[len(new) - (len(old) - p) :] == old[p:]


def is_pure_removal(old: bytes, new: bytes) -> bool:
    """True when ``new`` is ``old`` with one run of bytes cut out."""
    return is_pure_insertion(new, old)


# Replace


@PROPS
@given(data=st.data(), obj=OBJECTS, layout=layouts(), value=VALUES)
def test_replace_keeps_every_byte_outside_the_value(
    data: st.DataObject, obj: dict[str, Any], layout: tuple[Any, ...], value: Any
) -> None:
    paths = all_paths(obj)
    assume(paths)
    path = data.draw(st.sampled_from(paths))
    raw = render(obj, layout)
    start, end = json_edit.value_span(raw, path)
    new = json_edit.replace_value(raw, path, value)
    assert new[:start] == raw[:start]
    assert new[len(new) - (len(raw) - end) :] == raw[end:]
    expected = json.loads(raw)
    parent = get_at(expected, path[:-1])
    parent[path[-1]] = value
    assert json_edit.same_value(json.loads(new), expected)
    # the new span is exactly what json.dumps writes
    assert new[start : len(new) - (len(raw) - end)] == json.dumps(value).encode("ascii")


@PROPS
@given(obj=OBJECTS, layout=layouts(), value=VALUES)
def test_replacing_a_value_with_itself_changes_no_byte_that_json_dumps_would_not(
    obj: dict[str, Any], layout: tuple[Any, ...], value: Any
) -> None:
    raw = render({**obj, "target": value}, layout)
    again = json_edit.replace_value(raw, ("target",), value)
    assert json_edit.same_value(json.loads(again), json.loads(raw))
    start, end = json_edit.value_span(raw, ("target",))
    assert again[:start] == raw[:start]
    assert again[start:].endswith(raw[end:])


# Insert


@PROPS
@given(data=st.data(), obj=OBJECTS, layout=layouts(), value=VALUES)
def test_insert_adds_bytes_and_keeps_every_other_byte(
    data: st.DataObject, obj: dict[str, Any], layout: tuple[Any, ...], value: Any
) -> None:
    parents: list[tuple[str, ...]] = [(), *key_paths(obj)]
    parents = [p for p in parents if isinstance(get_at(obj, p), dict)]
    parent = data.draw(st.sampled_from(parents))
    chain = tuple(data.draw(st.lists(_KEYS, min_size=1, max_size=3)))
    names = (*parent, *chain)
    raw = render(obj, layout)
    expected: Any = json.loads(raw)

    # work out what the call must do, walking the names as the spec says
    node: Any = expected
    outcome = "insert"
    for index, step in enumerate(names):
        last = index == len(names) - 1
        if not isinstance(node, dict):
            outcome = "parent_not_object"
            break
        if last:
            outcome = "key_present" if step in node else "insert"
            if outcome == "insert":
                node[step] = value
            break
        if step not in node:
            nest: Any = value
            for name in reversed(names[index + 1 :]):
                nest = {name: nest}
            node[step] = nest
            break
        node = cast("dict[str, Any]", node)[step]

    if outcome != "insert":
        with pytest.raises(json_edit.Refused) as caught:
            json_edit.insert_value(raw, names, value)
        assert caught.value.code == outcome
        return
    new = json_edit.insert_value(raw, names, value)
    assert json_edit.same_value(json.loads(new), expected)
    target = get_at(json.loads(raw), parent)
    if target:  # an empty object may drop its own white space, as the old tests allow
        assert is_pure_insertion(raw, new)


# Remove


@PROPS
@given(data=st.data(), obj=OBJECTS, layout=layouts())
def test_remove_cuts_one_member_and_keeps_every_other_byte(
    data: st.DataObject, obj: dict[str, Any], layout: tuple[Any, ...]
) -> None:
    paths = key_paths(obj)
    assume(paths)
    path = data.draw(st.sampled_from(paths))
    raw = render(obj, layout)
    new = json_edit.remove_key(raw, path)
    expected: Any = json.loads(raw)
    del get_at(expected, path[:-1])[path[-1]]
    assert json_edit.same_value(json.loads(new), expected)
    only_member = len(get_at(json.loads(raw), path[:-1])) == 1
    if not only_member:
        assert is_pure_removal(raw, new)
    else:
        # the last member of an object leaves its braces, so the white space inside
        # may go with it. Bytes outside the braces never change.
        assert len(new) < len(raw)


@PROPS
@given(obj=OBJECTS, layout=layouts(), value=VALUES, key=_KEYS)
def test_insert_then_remove_gives_back_the_same_data(
    obj: dict[str, Any], layout: tuple[Any, ...], value: Any, key: str
) -> None:
    assume(key not in obj)
    raw = render(obj, layout)
    added = json_edit.insert_value(raw, (key,), value)
    removed = json_edit.remove_key(added, (key,))
    assert json_edit.same_value(json.loads(removed), json.loads(raw))


# parse_strict


def reference(raw: bytes) -> dict[str, Any] | None:
    """What ``json.loads`` says about strict UTF-8 bytes, an object or None."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    return cast("dict[str, Any]", data) if isinstance(data, dict) else None


_NOISE = st.text(
    alphabet='{}[]":,0123456789 \t\r\n-+.eEtrufalsnNIiy\\/*xé﻿', max_size=40
)


@PROPS
@given(
    raw=st.one_of(
        st.binary(max_size=40),
        _NOISE.map(lambda t: t.encode("utf-8")),
        st.tuples(OBJECTS, layouts()).map(lambda pair: render(pair[0], pair[1])),
        st.tuples(OBJECTS, layouts(), st.integers(0, 30), st.binary(max_size=3)).map(
            lambda t: _mutate(render(t[0], t[1]), t[2], t[3])
        ),
    )
)
def test_parse_strict_agrees_with_json_loads(raw: bytes) -> None:
    expected = reference(raw)
    if expected is None:
        with pytest.raises(json_edit.Refused) as caught:
            json_edit.parse_strict(raw)
        assert caught.value.code == "unparsed"
        return
    text, data = json_edit.parse_strict(raw)
    assert text == raw.decode("utf-8")
    assert json.dumps(data, sort_keys=True) == json.dumps(expected, sort_keys=True)


def _mutate(raw: bytes, at: int, junk: bytes) -> bytes:
    cut = at % (len(raw) + 1)
    return raw[:cut] + junk + raw[cut + len(junk) :]


@PROPS
@given(obj=OBJECTS, layout=layouts(), data=st.data())
def test_value_span_finds_exactly_the_bytes_json_dumps_wrote_for_unchanged_values(
    obj: dict[str, Any], layout: tuple[Any, ...], data: st.DataObject
) -> None:
    paths = all_paths(obj)
    assume(paths)
    path = data.draw(st.sampled_from(paths))
    raw = render(obj, layout)
    start, end = json_edit.value_span(raw, path)
    assert json_edit.same_value(json.loads(raw[start:end]), get_at(obj, path))


# Masking

_PLANT = "PLANTED"
_PLAIN = st.text(alphabet="abcdefghijklmnopqrstuvwxyz ./:_-", max_size=10).filter(
    lambda s: (
        not masking.is_secret_value(s) and "://" not in s and not s.startswith("-")
    )
)
_SECRET_NAMES = st.sampled_from(
    ["API_KEY", "my_token", "PASSWORD", "x-secret", "AuthToken", "credential", "COOKIE"]
)
_PLAIN_NAMES = st.sampled_from(
    ["model", "env", "note", "a", "b", "url", "name", "list"]
)
_SECRET_SCALARS = st.one_of(
    st.integers(0, 9999).map(lambda n: f"sk-{_PLANT}{n}"),
    st.integers(0, 9999).map(lambda n: f"Bearer {_PLANT}{n}"),
    st.integers(0, 9999).map(lambda n: f"ghp_{_PLANT}{n}"),
    st.integers(0, 9999).map(lambda n: f"https://user:{_PLANT}{n}@host.example/p"),
    st.integers(0, 9999).map(lambda n: f"ssh://{_PLANT}{n}@host.example"),
)


def _planted(depth: int = 2) -> SearchStrategy[Any]:
    """A value that holds the plant somewhere inside it."""
    scalar = st.one_of(_SECRET_SCALARS, st.just(_PLANT))
    if depth == 0:
        return scalar
    inner = _planted(depth - 1)
    return st.one_of(
        scalar,
        st.lists(inner, min_size=1, max_size=3),
        st.dictionaries(_PLAIN_NAMES, inner, min_size=1, max_size=3),
    )


@st.composite
def args_list(draw: DrawFn) -> list[Any]:
    """An ``args`` list with a planted value after a secret flag."""
    items: list[Any] = draw(st.lists(_PLAIN, max_size=3))
    flag = draw(st.sampled_from(["--token", "--api-key", "--password", "-secret"]))
    if draw(st.booleans()):
        items.append(f"{flag}={_PLANT}{draw(st.integers(0, 999))}")
    else:
        items.extend([flag, f"{_PLANT}{draw(st.integers(0, 999))}"])
    items.extend(draw(st.lists(_PLAIN, max_size=2)))
    return items


@st.composite
def secret_documents(draw: DrawFn) -> dict[str, Any]:
    """An object whose secrets all hold the plant, and whose plain values never do."""
    plain = st.dictionaries(
        _PLAIN_NAMES, st.one_of(_PLAIN, st.integers(), st.none()), max_size=3
    )
    doc: dict[str, Any] = draw(plain)
    for _ in range(draw(st.integers(1, 4))):
        place = draw(st.sampled_from(["name", "value", "args", "nested", "list"]))
        if place == "name":
            doc[draw(_SECRET_NAMES)] = draw(_planted())
        elif place == "value":
            doc[draw(_PLAIN_NAMES)] = draw(_SECRET_SCALARS)
        elif place == "args":
            doc["args"] = draw(args_list())
        elif place == "nested":
            inner = draw(plain)
            inner[draw(_SECRET_NAMES)] = draw(_planted())
            doc[draw(_PLAIN_NAMES)] = {"deeper": inner}
        else:
            doc[draw(_PLAIN_NAMES)] = [draw(_PLAIN), draw(_SECRET_SCALARS)]
    return doc


@PROPS
@given(doc=secret_documents(), layout=layouts())
def test_mask_text_never_shows_a_planted_secret(
    doc: dict[str, Any], layout: tuple[Any, ...]
) -> None:
    text = render(doc, layout).decode("utf-8")
    masked = json_edit.mask_text(text)
    assert _PLANT not in masked
    # it is still JSON, in the same number of lines, and it is what the read side shows
    assert json.loads(masked) == masking.mask_value(json.loads(text))
    breaks = re.compile(r"\r\n|\n|\r")
    assert len(breaks.split(masked)) == len(breaks.split(text))


@PROPS
@given(doc=secret_documents(), layout=layouts(), other=_PLAIN)
def test_a_diff_never_shows_a_planted_secret(
    doc: dict[str, Any], layout: tuple[Any, ...], other: str
) -> None:
    before = render({**doc, "model": "low"}, layout).decode("utf-8")
    after_raw = json_edit.replace_value(
        before.encode("utf-8"), ("model",), other or "high"
    )
    after = after_raw.decode("utf-8")
    for old, new in ((before, after), (after, before), (before, None), (None, before)):
        blob = json.dumps(json_edit.structured_diff(old, new, "settings.json"))
        assert _PLANT not in blob


@PROPS
@given(doc=secret_documents(), layout=layouts(), value=_PLAIN)
def test_an_insert_next_to_a_secret_never_shows_the_secret_in_the_diff(
    doc: dict[str, Any], layout: tuple[Any, ...], value: str
) -> None:
    before = render(doc, layout)
    assume("model" not in doc)
    after = json_edit.insert_value(before, ("model",), value)
    blob = json.dumps(json_edit.structured_diff(before.decode(), after.decode(), "f"))
    assert _PLANT not in blob


# canonical_body and choice_key

_PROJECTS = st.text(alphabet="abcdefgh-_0123", min_size=1, max_size=12)
_SCOPES = st.sampled_from(["user", "project", "local"])
_FIELDS_AND_VALUES = st.one_of(
    st.tuples(
        st.just("model"),
        st.text(alphabet="abcdef-0123 ", min_size=1, max_size=20).filter(str.strip),
    ),
    st.tuples(
        st.just("effortLevel"), st.sampled_from(["low", "medium", "high", "xhigh"])
    ),
    st.tuples(st.just("maxEffortLevel"), st.sampled_from(["low", "high", "max"])),
    st.tuples(st.just("autoCompactWindow"), st.integers(100000, 1000000)),
)
_IDS = st.text(alphabet="abcdefABCDEF0123456789_-", min_size=8, max_size=40)


def shuffled(body: dict[str, Any], seed: int) -> dict[str, Any]:
    keys = list(body)
    random.Random(seed).shuffle(keys)
    return {k: body[k] for k in keys}


@PROPS
@given(
    project=_PROJECTS,
    scope=_SCOPES,
    pair=_FIELDS_AND_VALUES,
    seqs=st.tuples(st.integers(0, 10**6), st.integers(0, 10**6)),
    versions=st.tuples(_IDS, _IDS),
    request_ids=st.tuples(_IDS, _IDS),
    seed=st.integers(0, 10**6),
)
def test_canonical_body_is_stable_under_key_order_and_the_volatile_fields(
    project: str,
    scope: str,
    pair: tuple[str, Any],
    seqs: tuple[int, int],
    versions: tuple[str, str],
    request_ids: tuple[str, str],
    seed: int,
) -> None:
    field, value = pair
    choice = {
        "project": project,
        "op": "set",
        "scope": scope,
        "field": field,
        "value": value,
    }
    first = {
        **choice,
        "seq": seqs[0],
        "version": versions[0],
        "request_id": request_ids[0],
    }
    second = {
        **choice,
        "seq": seqs[1],
        "version": versions[1],
        "request_id": request_ids[1],
    }
    a = EditSaveRequest.model_validate(shuffled(first, seed))
    b = EditSaveRequest.model_validate(shuffled(second, seed + 1))
    assert edit_store.canonical_body(a) == edit_store.canonical_body(b)
    assert edit_store.choice_key(a) == edit_store.choice_key(b)
    # the preview of the same choice has the same body, so a token binds both
    preview = EditPreviewRequest.model_validate(
        shuffled({**choice, "seq": seqs[0]}, seed + 2)
    )
    assert edit_store.canonical_body(preview) == edit_store.canonical_body(a)
    body = edit_store.canonical_body(a)
    parsed = json.loads(body)
    assert set(parsed) == {"project", "op", "scope", "field", "value"}
    assert body == json.dumps(
        parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


@PROPS
@given(
    project=_PROJECTS,
    scope=_SCOPES,
    pair=_FIELDS_AND_VALUES,
    other=st.tuples(_PROJECTS, _SCOPES, _FIELDS_AND_VALUES),
)
def test_every_field_of_the_choice_changes_the_choice_key(
    project: str,
    scope: str,
    pair: tuple[str, Any],
    other: tuple[str, str, tuple[str, Any]],
) -> None:
    def make(project_: str, scope_: str, pair_: tuple[str, Any]) -> EditPreviewRequest:
        return EditPreviewRequest.model_validate(
            {
                "project": project_,
                "op": "set",
                "scope": scope_,
                "field": pair_[0],
                "value": pair_[1],
                "seq": 1,
            }
        )

    a = make(project, scope, pair)
    b = make(*other)
    same = (project, scope, pair) == other
    assert (edit_store.choice_key(a) == edit_store.choice_key(b)) == same
