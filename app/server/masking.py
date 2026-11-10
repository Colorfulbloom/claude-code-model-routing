"""Masking for the setup read side: hide secrets before anything else sees them.

This extends the ported ``collect.mask`` with the rules of research note 26-07
(``docs/rebuild/research/26-07-read-gate.md``, "Masking"). Hooks, MCP env, headers and
args are new places a secret can live, so the old six name parts and two value
prefixes are not enough. Everything a collector shows from those places goes through
this module. The hidden word is ``collect.HIDDEN``, the same one the old tests use.

Rules.

- A name that holds KEY, TOKEN, SECRET, PASSWORD, PASSWD, CREDENTIAL, AUTH, COOKIE or
  BEARER, in any case with ``-`` read as ``_``, hides the whole value, a dict or list
  included. A name in ``collect.NOT_SECRET_NAMES`` (``MAX_THINKING_TOKENS``, fact
  R-8829) is exempt by name only. A value with a secret shape under it still hides.
- A value that starts with ``sk-``, ``Bearer ``, ``Basic ``, a GitHub token prefix
  (``ghp_``, ``gho_``, ``ghu_``, ``ghs_``, ``github_pat_``), ``xox`` plus ``a``, ``b``,
  ``p``, ``r`` or ``s`` and ``-``, or ``AKIA`` plus twelve or more characters, or that
  has the shape of a JWT (``eyJ`` and two dots), hides.
- URL userinfo is masked in place. ``scheme://user:pass@host`` becomes
  ``scheme://user:hidden@host``. A user-only form (``https://ghp_x@host``) hides the
  user. The host stays.
- Under a list named ``args``, a flag whose name holds a secret word hides the next
  item (``--api-key abc``) or the part after ``=`` (``--token=abc``). Other items go
  through the value rules.

Gaps these rules leave, from 26-07: a secret under an unrelated name and with no known
prefix, a flag name with no secret word (``--pat abc``), and a secret inside free text
such as a shell command in a hook. A caller that knows the schema should show a field
by allowlist instead of relying on this module.

Nothing here reads a file or the environment, and no input is changed.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

import collect
from models import MaskedText

HIDDEN = collect.HIDDEN
SECRET_NAME_PARTS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "AUTH",
    "COOKIE",
    "BEARER",
)
# Matched case-insensitively against the start of the value, leading space ignored.
_PREFIXES = ("sk-", "bearer ", "basic ", "ghp_", "gho_", "ghu_", "ghs_", "github_pat_")
_SHAPES = (
    re.compile(r"xox[abprs]-"),
    re.compile(r"AKIA\S{12,}"),
    re.compile(r"eyJ[\w-]*\.[\w-]*\.[\w-]*"),
)
# scheme://userinfo@ where userinfo is user or user:password. The host is not matched.
# mask_url scans for this by hand in linear time; the pattern stays as the reference
# its tests compare against.
_SCHEME_FIRST = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
_SCHEME_CHARS = _SCHEME_FIRST | frozenset("0123456789+.-")
_USERINFO = re.compile(
    r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*://)(?P<user>[^/\s@:]*)(?::(?P<password>[^/\s@]*))?@"
)
_ARGS_NAME = "args"


def is_secret_name(name: object) -> bool:
    """True when the name holds a secret word. A non-string name never does.

    Case does not matter and ``-`` reads as ``_``. A name in
    ``collect.NOT_SECRET_NAMES`` is not secret.
    """
    if not isinstance(name, str):
        return False
    upper = name.upper().replace("-", "_")
    if upper in collect.NOT_SECRET_NAMES:
        return False
    return any(part in upper for part in SECRET_NAME_PARTS)


def is_secret_value(value: object) -> bool:
    """True for a string with a secret prefix or a secret shape.

    Leading white space is ignored, so `` sk-...`` hides too.
    """
    if not isinstance(value, str):
        return False
    start = value.lstrip()
    if start.lower().startswith(_PREFIXES):
        return True
    return any(shape.match(start) for shape in _SHAPES)


def mask_url(url: str) -> str:
    """Mask URL userinfo in a string, wherever it appears in it.

    ``scheme://user:pass@host`` gives ``scheme://user:hidden@host``, and a user-only
    ``scheme://token@host`` gives ``scheme://hidden@host``. The host, path and query
    are kept.

    It gives the same answer as ``_USERINFO.sub``, but in linear time. The regex
    retries at every letter of a long run of scheme characters and scans to its end
    each time, so a 1 MiB agent field took minutes. Here each ``://`` is found once
    and its scheme is the run before it, from its first letter.
    """
    out: list[str] = []
    done = 0
    at = url.find("://")
    while at != -1:
        start = at
        while start > done and url[start - 1] in _SCHEME_CHARS:
            start -= 1
        while start < at and url[start] not in _SCHEME_FIRST:
            start += 1
        end = _userinfo_end(url, at + 3) if start < at else None
        if end is None:
            at = url.find("://", at + 3)
            continue
        user_end, password_at, at_sign = end
        scheme = url[start : at + 3]
        out.append(url[done:start])
        if password_at is None:
            out.append(f"{scheme}{HIDDEN}@")
        else:
            out.append(f"{scheme}{url[at + 3 : user_end]}:{HIDDEN}@")
        done = at_sign + 1
        at = url.find("://", done)
    out.append(url[done:])
    return "".join(out)


def _userinfo_end(url: str, at: int) -> tuple[int, int | None, int] | None:
    """Read ``user`` or ``user:password`` and ``@`` from ``at``, as ``_USERINFO`` does.

    Returns (end of user, start of password or None, index of ``@``), or None when no
    ``@`` closes it. A user stops at ``/``, ``@``, ``:`` or white space, a password at
    ``/``, ``@`` or white space.
    """
    i = at
    n = len(url)
    while i < n and url[i] not in "/@:" and not url[i].isspace():
        i += 1
    if i < n and url[i] == "@":
        return i, None, i
    if i < n and url[i] == ":":
        j = i + 1
        while j < n and url[j] not in "/@" and not url[j].isspace():
            j += 1
        if j < n and url[j] == "@":
            return i, i + 1, j
    return None


def _flag_secret(item: str) -> tuple[bool, bool]:
    """Return (is a secret-named flag, it carries its value after ``=``)."""
    if not item.startswith("-"):
        return False, False
    name, equals, _rest = item.lstrip("-").partition("=")
    return is_secret_name(name), bool(equals)


def mask_args(args: Sequence[object]) -> list[object]:
    """Mask an args list.

    A secret-named flag hides the next item, or the part after ``=``. Every other
    item goes through ``mask_value``, so a bare ``Bearer x`` or a URL with userinfo
    still hides.

    Args:
        args: The list, such as an MCP server's ``args``.

    Returns:
        A new list. The input is not changed.
    """
    out: list[object] = []
    hide_next = False
    for item in args:
        if hide_next:
            out.append(HIDDEN)
            hide_next = False
            continue
        if isinstance(item, str):
            secret, inline = _flag_secret(item)
            if secret and inline:
                out.append(f"{item.partition('=')[0]}={HIDDEN}")
                continue
            if secret:
                out.append(item)
                hide_next = True
                continue
        out.append(mask_value(item))
    return out


def mask_value(value: object, name: object = None) -> object:
    """Return value with every secret part replaced, under the 26-07 rules.

    A secret name hides the whole value. A dict masks each item under its own key. A
    list masks each item under the list's name, and a list named ``args`` also hides
    the values of secret-named flags (``mask_args``). A string with a secret prefix or
    shape hides, and one with URL userinfo keeps its shape with the secret part
    hidden. Anything else is unchanged.

    Args:
        value: Any JSON-shaped value.
        name: The key it sits under, or None.

    Returns:
        The masked copy.
    """
    if is_secret_name(name):
        return HIDDEN
    if isinstance(value, dict):
        return {
            key: mask_value(item, key)
            for key, item in cast("dict[str, Any]", value).items()
        }
    if isinstance(value, list):
        items = cast("list[object]", value)
        if isinstance(name, str) and name.lower() == _ARGS_NAME:
            return mask_args(items)
        return [mask_value(item, name) for item in items]
    if isinstance(value, str):
        return HIDDEN if is_secret_value(value) else mask_url(value)
    return value


def mask_env(env: Mapping[str, object]) -> dict[str, object]:
    """Mask an env map. Each variable is masked by its name and by its value."""
    return {name: mask_value(value, name) for name, value in env.items()}


def mask_headers(headers: Mapping[str, object]) -> dict[str, object]:
    """Mask a header map. ``Authorization``, ``Cookie`` and ``X-Api-Key`` hide whole."""
    return {name: mask_value(value, name) for name, value in headers.items()}


def masked_text(value: object, name: object = None) -> MaskedText:
    """Return a string value as ``MaskedText``, saying whether masking hid anything.

    Args:
        value: The value to show. A non-string is shown as its JSON-like text.
        name: The key it sits under, or None.

    Returns:
        ``MaskedText`` with the masked text and ``masked`` True when it differs from
        the original text.
    """
    original = value if isinstance(value, str) else str(value)
    shown = mask_value(original, name)
    text = shown if isinstance(shown, str) else str(shown)
    return MaskedText(text=text, masked=text != original)
