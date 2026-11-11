"""Tests for the Claude Code version helpers, as the old dashboard behaved."""

import pytest

import claude_version


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2.1.302", (2, 1, 302)),
        ("2.1.302 (Claude Code)", (2, 1, 302)),
        ("2", (2,)),
        ("2.1", (2, 1)),
        ("10.0.1-beta", (10, 0, 1)),
        ("v2.1.302", None),
        ("abc", None),
        ("", None),
        (".1", None),
    ],
)
def test_parse(text: str, expected: tuple[int, ...] | None) -> None:
    assert claude_version.parse(text) == expected


@pytest.mark.parametrize("value", [None, 2, 2.1, b"2.1.302", ["2.1.302"], (2, 1)])
def test_parse_gives_none_for_a_non_string(value: object) -> None:
    assert claude_version.parse(value) is None


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("2.1.302", "2.1.310", True),
        ("2.1.310", "2.1.302", False),
        ("2.1.302", "2.1.302", False),
        ("2.1.9", "2.1.10", True),  # numbers, not text
        ("2.1", "2.1.1", True),  # a missing part counts as 0
        ("2.1.0", "2.1", False),
        ("2.1", "2.1.0", False),
        ("2", "2.0.1", True),
        ("2.1.302 (Claude Code)", "2.2", True),
        ("abc", "2.1.302", False),
        ("2.1.302", "abc", False),
        ("", "", False),
        (None, "2.1.302", False),
        ("2.1.302", None, False),
    ],
)
def test_older(a: object, b: object, expected: bool) -> None:
    assert claude_version.older(a, b) is expected


def test_oldest_returns_the_original_text() -> None:
    assert (
        claude_version.oldest(["2.1.310", "2.1.302 (Claude Code)", "2.1.305"])
        == "2.1.302 (Claude Code)"
    )


def test_oldest_skips_what_does_not_parse() -> None:
    assert claude_version.oldest([None, "abc", "2.1.5", 7, ""]) == "2.1.5"


def test_oldest_of_nothing_is_none() -> None:
    assert claude_version.oldest([]) is None
    assert claude_version.oldest([None, "abc"]) is None


def test_oldest_keeps_the_first_of_equal_versions() -> None:
    assert claude_version.oldest(["2.1", "2.1.0"]) == "2.1"
