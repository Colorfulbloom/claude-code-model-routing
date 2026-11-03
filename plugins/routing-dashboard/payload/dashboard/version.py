"""Claude Code version numbers: parse them, compare them and find the installed one.

The installed version is read from files, never by running claude. The reader
looks for the claude launcher on the PATH text it is given, follows the link to
the real file, and reads the version from where that file sits. It never raises
for a bad install, never reads os.environ and writes nothing.

Standard library only, Python 3.9.
"""
import json
import os
import re
import shutil

_LEADING = re.compile(r"[0-9]+(?:\.[0-9]+)*")
PACKAGE_PREFIX = "@anthropic-ai/claude-code"
PACKAGE_READ_CAP = 65536  # bytes of package.json the reader looks at
PACKAGE_WALK = 3  # folders above the real file that may hold package.json


def parse(text):
    """Return the leading dotted number of text as a tuple of ints, or None.

    "2.1.302" and "2.1.302 (Claude Code)" both give (2, 1, 302). Text that does
    not start with digits and dots, or that is not a str, gives None.
    """
    if not isinstance(text, str):
        return None
    match = _LEADING.match(text)
    if match is None:
        return None
    return tuple(int(part) for part in match.group(0).split("."))


def _padded(a, b):
    """Return a and b padded with zeros to the same length."""
    size = max(len(a), len(b))
    return a + (0,) * (size - len(a)), b + (0,) * (size - len(b))


def older(a, b):
    """True when both parse and a is older than b, part by part as numbers.

    A missing part counts as 0. Anything that does not parse gives False.
    """
    left, right = parse(a), parse(b)
    if left is None or right is None:
        return False
    left, right = _padded(left, right)
    return left < right


def oldest(versions):
    """Return the oldest of the versions that parse, as the original text, or None."""
    best = None
    for text in versions:
        parsed = parse(text)
        if parsed is None:
            continue
        if best is None or older(text, best):
            best = text
    return best


def _native(real):
    """The native installer: the file sits in a folder named versions, named for its version."""
    name = os.path.basename(real)
    if os.path.basename(os.path.dirname(real)) == "versions" and parse(name) is not None:
        return name
    return None


def _cask(real):
    """Homebrew's cask folder: claude-code/<version>/claude.

    This is Homebrew's general Caskroom form. No public source confirms it for
    this cask, so a miss here only means the chip reads unknown.
    """
    if os.path.basename(real) != "claude":
        return None
    folder = os.path.dirname(real)
    name = os.path.basename(folder)
    if parse(name) is not None and os.path.basename(os.path.dirname(folder)) == "claude-code":
        return name
    return None


def _package(real):
    """npm: a package.json up to three folders above the real file, named for the Claude Code package.

    The package ships bin/claude.exe and a postinstall step links it into place,
    so the real file can sit in a bin folder or in a platform package whose name
    starts with the same prefix.
    """
    folder = os.path.dirname(real)
    for _step in range(PACKAGE_WALK):
        data = _read_package(os.path.join(folder, "package.json"))
        if data is not None and isinstance(data.get("name"), str) and data["name"].startswith(PACKAGE_PREFIX):
            version = data.get("version")
            if isinstance(version, str) and parse(version) is not None:
                return version
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    return None


def _read_package(path):
    """Return the JSON object in a package.json (first 64 KB), or None."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(PACKAGE_READ_CAP)
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def read_installed(path_env):
    """Return the installed Claude Code version as "x.y.z" text, or None.

    path_env is the PATH text to search. None or empty gives None. It runs no
    program, and it passes path= to shutil.which so os.environ is never read.
    The layouts it knows are the native installer, a Homebrew cask and npm.
    Anything else gives None, which the chip shows as unknown.
    """
    if not path_env or not isinstance(path_env, str):
        return None
    try:
        found = shutil.which("claude", path=path_env)
        if not found:
            return None
        real = os.path.realpath(found)
        for layout in (_native, _cask, _package):
            version = layout(real)
            if version is not None:
                return version
    except (OSError, ValueError):
        return None
    return None


def installed(ctx):
    """Return ctx.claude_version when it parses, else the version read from ctx.path_env."""
    fixed = getattr(ctx, "claude_version", None)
    if parse(fixed) is not None:
        return fixed
    return read_installed(getattr(ctx, "path_env", None))
