"""Mask a command line: the free text of a hook command or an MCP ``command``.

``masking.mask_value`` hides a whole value by its name or its shape, but a secret inside
free text (``python3 check.py --api-key sk-...``) is a gap it names (26-07). Here the
command is split on white space and each word goes through the same rules.

- A secret-named flag hides the next word, or the part after ``=``.
- ``NAME=value`` with a secret-named ``NAME`` hides the value.
- The words ``Bearer`` and ``Basic`` hide the word after them.
- A word with a secret prefix or shape hides (quotes are looked through), and URL
  userinfo is masked in place.

The white space between words is kept. Nothing here reads a file.
"""

import re

import masking
from models import MaskedText

HIDDEN = masking.HIDDEN
_SPLIT = re.compile(r"(\s+)")
_ASSIGN = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$", re.DOTALL)
_SCHEMES = ("bearer", "basic")
_QUOTES = "'\""


def _word(word: str) -> tuple[str, bool]:
    """Return (the masked word, True when the word after it hides too)."""
    bare = word.strip(_QUOTES)
    if bare.startswith("-"):
        name, equals, _value = bare.lstrip("-").partition("=")
        if masking.is_secret_name(name):
            if equals:
                return f"{bare.partition('=')[0]}={HIDDEN}", False
            return word, True
    found = _ASSIGN.match(bare)
    if found is not None and masking.is_secret_name(found["name"]):
        return f"{found['name']}={HIDDEN}", False
    if bare.lower() in _SCHEMES:
        return word, True
    if masking.is_secret_value(bare):
        return HIDDEN, False
    return masking.mask_url(word), False


def mask_command(text: str) -> str:
    """Return the command with every secret word hidden. White space is kept."""
    parts = _SPLIT.split(text)
    out: list[str] = []
    hide_next = False
    for at, part in enumerate(parts):
        if at % 2 == 1 or not part:  # white space between words
            out.append(part)
            continue
        if hide_next:
            # A closing quote stays, so the rest of the command still reads.
            out.append(HIDDEN + part[len(part.rstrip(_QUOTES)) :])
            hide_next = False
            continue
        shown, hide_next = _word(part)
        out.append(shown)
    return "".join(out)


def masked_command(text: str) -> MaskedText:
    """Return a command as ``MaskedText``, saying whether masking hid anything."""
    shown = mask_command(text)
    return MaskedText(text=shown, masked=shown != text)
