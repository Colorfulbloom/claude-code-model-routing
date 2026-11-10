"""``masking.mask_url`` scans in linear time and answers as its reference regex does.

The regex ``_USERINFO.sub`` retried at every letter of a long run of scheme
characters, so one long line in an agent field took minutes to mask. Every secret
here is made up.
"""

import re
import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import collect
import masking

HIDDEN = collect.HIDDEN


def _reference(url: str) -> str:
    def replace(found: re.Match[str]) -> str:
        scheme, user, password = found["scheme"], found["user"], found["password"]
        if password is None:
            return f"{scheme}{HIDDEN}@"
        return f"{scheme}{user}:{HIDDEN}@"

    return masking._USERINFO.sub(replace, url)  # pyright: ignore[reportPrivateUsage]


CASES = [
    "https://u:p@host/x",
    "https://token@host",
    "see https://u:p@a.b and ftp://t@c",
    "9https://u:p@host",
    "a1+b.c-d://u@h",
    "x=https://u:p@h y",
    "https://u:p/@h",
    "https://u p@h",
    "://u@h",
    "1://u@h",
    "a://b://u:p@h",
    "a://u:p:q@h",
    "https://u:p@h://v:w@i",
    "",
    "no scheme here",
    "https://@h",
    "https://:@h",
    "ä://u@h é://u:p@h",
    "a\u2003b://u@h",
]


@pytest.mark.parametrize("url", CASES)
def test_mask_url_matches_the_regex(url: str) -> None:
    assert masking.mask_url(url) == _reference(url)


_ALPHABET = st.sampled_from(list("ab9+.-:/@ \t\u2003é_xs"))


@settings(max_examples=400, derandomize=True, deadline=None)
@given(st.lists(_ALPHABET, max_size=40).map("".join))
def test_mask_url_matches_the_regex_on_any_text(url: str) -> None:
    assert masking.mask_url(url) == _reference(url)


@pytest.mark.parametrize(
    "text",
    [
        "a" * 1_048_576,
        "a1" * 524_288,
        "a" * 1_048_000 + "://u",
        "a://" * 262_144,
        ("a" * 1000 + "://" + "b" * 1000 + ":") * 500,
    ],
)
def test_one_mebibyte_line_masks_in_well_under_a_second(text: str) -> None:
    started = time.monotonic()
    masking.mask_url(text)
    assert time.monotonic() - started < 1.0
