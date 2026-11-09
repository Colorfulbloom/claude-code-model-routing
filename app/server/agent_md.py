"""Agent file helpers: frontmatter parsing and rendering, and the agent file walks.

Frontmatter parsing and rendering, the agent file walks, and the sorted file
listing. Python 3.9+, standard library only.
"""

# ruff: noqa: PLR2004, PTH112, PTH118, PTH123, UP031
#
# Ported unchanged so the old tests keep passing. The old code builds paths as
# strings with os.path, formats messages with %, and compares sizes as numbers.

import os
import re


class MissingFieldsError(Exception):
    """An agent file lacks a model: or an effort: line. `.label` names the file."""

    def __init__(self, label: str) -> None:
        """Keep the label of the file that lacks a model or effort line."""
        super().__init__(label)
        self.label = label


def read_bytes_text(path: str) -> str:
    """Read a file as text, keeping bytes that are not UTF-8 as surrogates."""
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8", "surrogateescape")


LINE_RE = re.compile(r"[^\n]*\n|[^\n]+")


def split_line(line: str) -> tuple[str, str]:
    r"""(content, ending) with ending one of \r\n, \n or empty."""
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def frontmatter_span(lines: list[str]) -> tuple[int, int] | None:
    """Index range (1, end) of frontmatter lines, or None without frontmatter."""
    if not lines or split_line(lines[0])[0] != "---":
        return None
    for idx in range(1, len(lines)):
        if split_line(lines[idx])[0] == "---":
            return (1, idx)
    return None


def strip_quotes(value: str) -> str:
    """Strip spaces and one pair of matching quotes from a frontmatter value."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value.strip()


def find_field_lines(lines: list[str], span: tuple[int, int]) -> dict[str, int]:
    """Map model and effort to the index of their first line inside the span."""
    found: dict[str, int] = {}
    for idx in range(span[0], span[1]):
        content = split_line(lines[idx])[0]
        for key in ("model", "effort"):
            if key not in found and content.startswith(key + ":"):
                found[key] = idx
    return found


def parse_agent_defaults(text: str, label: str) -> tuple[str, str]:
    """(model, effort) from the frontmatter.

    Raises:
        MissingFieldsError: When a model: or effort: line is missing. Carries `label`.
    """
    lines = LINE_RE.findall(text)
    span = frontmatter_span(lines)
    found = find_field_lines(lines, span) if span else {}
    if "model" not in found or "effort" not in found:
        raise MissingFieldsError(label)
    values: list[str] = []
    for key in ("model", "effort"):
        content = split_line(lines[found[key]])[0]
        values.append(strip_quotes(content[len(key) + 1 :]))
    return (values[0], values[1])


def render_agent(text: str, model: str, effort: str, label: str = "agent file") -> str:
    """Replaces only the first model: and effort: lines inside the frontmatter."""
    lines = LINE_RE.findall(text)
    span = frontmatter_span(lines)
    found = find_field_lines(lines, span) if span else {}
    if "model" not in found or "effort" not in found:
        raise MissingFieldsError(label)
    for key, value in (("model", model), ("effort", effort)):
        ending = split_line(lines[found[key]])[1]
        lines[found[key]] = "%s: %s%s" % (key, value, ending)
    return "".join(lines)


def frontmatter_name(path: str) -> str | None:
    """The value of the first name: line inside the frontmatter, or None."""
    try:
        text = read_bytes_text(path)
    except OSError:
        return None
    lines = text.split("\n")
    if lines[0] != "---":
        return None
    for line in lines[1:]:
        if line == "---":
            return None
        if line.startswith("name:"):
            value = line[len("name:") :].strip(" \t\n\r\v\f")
            if len(value) >= 3 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value
    return None


def find_agent_md_files(agents_dir: str) -> list[str]:
    """List the agent files under agents_dir, in the order `find` prints them.

    These are regular files and symlinks named *.md, anywhere under agents_dir, in
    directory order, descending into a real directory right when it is met. Not
    sorted.
    """
    found: list[str] = []
    try:
        entries = list(os.scandir(agents_dir))
    except OSError:
        return found
    for entry in entries:
        is_link = entry.is_symlink()
        if entry.name.endswith(".md") and (
            is_link or entry.is_file(follow_symlinks=False)
        ):
            found.append(entry.path)
        if not is_link and entry.is_dir(follow_symlinks=False):
            found.extend(find_agent_md_files(entry.path))
    return found


def list_files_sorted(folder: str) -> list[str]:
    """Return every non-hidden file under folder, sorted, as absolute paths."""
    if not os.path.isdir(folder):
        return []
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if not name.startswith("."):
                found.append(os.path.join(dirpath, name))
    return found
