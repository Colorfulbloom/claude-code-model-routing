"""Tests for ``masking``: the 26-07 rules over the ported ``collect.mask``.

The spike's ``mask_test.py`` is not in the repository, so the 18 cases below are
written from what note 26-07 lists (the old gaps, the new rules and the one fake MCP
payload it prints). Every secret here is made up.
"""

import json
from typing import Any

import pytest

import collect
import masking

HIDDEN = collect.HIDDEN

# Name rules (26-07 "Name hides the whole value").
NAME_CASES = [
    ("ANTHROPIC_API_KEY", True),
    ("db_password", True),
    ("DB_PASSWD", True),
    ("MY_CREDENTIAL", True),
    ("Authorization", True),
    ("Cookie", True),
    ("X-Bearer-Id", True),
    ("api-key", True),
    ("MAX_THINKING_TOKENS", False),
    ("max-thinking-tokens", False),
    ("ANTHROPIC_MODEL", False),
]


@pytest.mark.parametrize(("name", "secret"), NAME_CASES)
def test_name_rules(name: str, secret: bool) -> None:
    assert masking.is_secret_name(name) is secret
    assert masking.mask_value("plain", name) == (HIDDEN if secret else "plain")


def test_a_name_that_is_not_a_string_is_never_secret() -> None:
    assert masking.is_secret_name(None) is False
    assert masking.is_secret_name(7) is False


# Value rules (26-07 "Value prefix hides"). Each value sits under a harmless name.
VALUE_CASES = [
    "sk-fake-planted-one",
    "Bearer fake-planted-two",
    "Basic ZmFrZTpwbGFudGVk",
    "ghp_fakeplantedthree",
    "gho_fakeplantedfour",
    "ghu_fakeplantedfive",
    "ghs_fakeplantedsix",
    "github_pat_fakeplantedseven",
    "xoxb-fake-planted-eight",
    "xoxp-fake-planted-nine",
    "AKIAFAKEPLANTED0123",
    "eyJhbGciOiJub25lIn0.eyJmYWtlIjoxfQ.ZmFrZQ",
]


@pytest.mark.parametrize("value", VALUE_CASES)
def test_value_rules_hide_under_a_harmless_name(value: str) -> None:
    assert masking.is_secret_value(value)
    assert masking.mask_value(value, "NOTE") == HIDDEN
    assert masking.mask_value(f"  {value}", "NOTE") == HIDDEN


@pytest.mark.parametrize(
    "value",
    ["disk-1", "Bearer", "a sk- b", "AKIA", "AKIASHORT", "eyJonlyone", "xoxz-x", ""],
)
def test_values_that_are_not_secrets_pass(value: str) -> None:
    assert not masking.is_secret_value(value)


def test_non_strings_are_not_secret_values() -> None:
    for value in (5, None, True, ["sk-x"], {"a": "sk-x"}):
        assert not masking.is_secret_value(value)


def test_a_secret_shape_still_hides_under_the_exempt_name() -> None:
    assert masking.mask_value("8000", "MAX_THINKING_TOKENS") == "8000"
    assert masking.mask_value("sk-fake-planted", "MAX_THINKING_TOKENS") == HIDDEN


# URL userinfo (26-07 "URL userinfo").
URL_CASES = [
    (
        "https://user:pass@example.invalid/mcp",
        "https://user:hidden@example.invalid/mcp",
    ),
    ("https://fake-token@example.invalid/x", "https://hidden@example.invalid/x"),
    ("https://user:@example.invalid/", "https://user:hidden@example.invalid/"),
    (
        "postgres://u:p@db.invalid:5432/app?x=1",
        "postgres://u:hidden@db.invalid:5432/app?x=1",
    ),
    ("https://example.invalid/a@b", "https://example.invalid/a@b"),
    ("see https://u:p@h.invalid now", "see https://u:hidden@h.invalid now"),
    ("no url here", "no url here"),
]


@pytest.mark.parametrize(("url", "shown"), URL_CASES)
def test_url_userinfo(url: str, shown: str) -> None:
    assert masking.mask_url(url) == shown
    assert masking.mask_value(url, "url") == shown


# Args (26-07 "Under a key called args").
def test_args_hide_the_value_of_a_secret_flag() -> None:
    payload = {
        "args": ["--api-key", "fake-abc", "--token=fake-abc", "--model", "x"],
        "url": "https://user:pass@example.invalid/mcp",
    }
    masked = masking.mask_value(payload)
    assert masked == {
        "args": ["--api-key", HIDDEN, f"--token={HIDDEN}", "--model", "x"],
        "url": "https://user:hidden@example.invalid/mcp",
    }
    text = json.dumps(masked)
    assert "fake-abc" not in text
    assert "pass@" not in text


def test_args_other_items_go_through_the_value_rules() -> None:
    assert masking.mask_args(["run", "Bearer fake-one", "https://u:p@h.invalid"]) == [
        "run",
        HIDDEN,
        "https://u:hidden@h.invalid",
    ]


def test_a_secret_flag_at_the_end_has_nothing_to_hide() -> None:
    assert masking.mask_args(["--password"]) == ["--password"]


def test_a_dash_alone_and_numbers_are_plain_args() -> None:
    assert masking.mask_args(["-", "-1", 5, None]) == ["-", "-1", 5, None]


def test_only_a_list_named_args_reads_flags() -> None:
    masked = masking.mask_value({"other": ["--token", "fake-x"]})
    assert masked == {"other": ["--token", "fake-x"]}


def test_args_inside_a_secret_name_hide_whole() -> None:
    assert masking.mask_value({"auth_args": ["a"]}) == {"auth_args": HIDDEN}


# Maps.
def test_env_and_header_maps() -> None:
    env = {"ANTHROPIC_API_KEY": "fake", "PATH": "/usr/bin", "NOTE": "ghp_fakeplanted"}
    assert masking.mask_env(env) == {
        "ANTHROPIC_API_KEY": HIDDEN,
        "PATH": "/usr/bin",
        "NOTE": HIDDEN,
    }
    headers = {"Authorization": "Bearer fake", "Cookie": "a=b", "Accept": "text/html"}
    assert masking.mask_headers(headers) == {
        "Authorization": HIDDEN,
        "Cookie": HIDDEN,
        "Accept": "text/html",
    }


def test_masking_does_not_change_its_input() -> None:
    value: dict[str, Any] = {"args": ["--token", "fake"], "env": {"A_KEY": "x"}}
    masking.mask_value(value)
    assert value == {"args": ["--token", "fake"], "env": {"A_KEY": "x"}}


def test_scalars_pass_through() -> None:
    for value in (1, 2.5, True, None, "text"):
        assert masking.mask_value(value, "NOTE") == value


# masked_text.
def test_masked_text_says_whether_it_hid_anything() -> None:
    assert masking.masked_text("plain").masked is False
    assert masking.masked_text("plain").text == "plain"
    hidden = masking.masked_text("sk-fake-planted")
    assert (hidden.text, hidden.masked) == (HIDDEN, True)
    url = masking.masked_text("https://u:p@h.invalid/x")
    assert (url.text, url.masked) == ("https://u:hidden@h.invalid/x", True)
    assert masking.masked_text(8000, "MAX_THINKING_TOKENS").text == "8000"
    assert masking.masked_text("v", "API_KEY").masked is True


# Old rules keep working: the new mask agrees with collect.mask wherever the old rules
# already hid something, and hides nothing the old one showed under the old inputs.
OLD_CASES: list[tuple[object, object]] = [
    ("sk-planted-bravo", "NOTE"),
    ("Bearer planted-charlie", "NOTE"),
    ("plain", "NOTE"),
    ("0", "MAX_THINKING_TOKENS"),
    ("sk-x", "MAX_THINKING_TOKENS"),
    ({"hooks": ["Bearer z", "ok"]}, None),
    (
        {"ok": "fine", "madeUpKey": "x", "nest": {"a": "sk-q", "b": [1, "Bearer z"]}},
        None,
    ),
    ("plain", "MADE_UP_TOKEN"),
    ([1, 2.5, True, None], "NOTE"),
]


@pytest.mark.parametrize(("value", "name"), OLD_CASES)
def test_the_old_cases_give_the_old_answers(value: object, name: object) -> None:
    assert masking.mask_value(value, name) == collect.mask(value, name)


def test_the_hidden_word_is_the_old_one() -> None:
    assert masking.HIDDEN == collect.HIDDEN == "hidden"
