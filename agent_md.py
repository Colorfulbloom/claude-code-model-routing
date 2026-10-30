"""Agent file helpers shared by install.py and the dashboard.

Frontmatter parsing and rendering, the agent file walks, and the sorted file
listing. Python 3.9+, standard library only.
"""
import os
import re


class MissingFieldsError(Exception):
    """An agent file lacks a model: or an effort: line. `.label` names the file."""

    def __init__(self, label):
        super().__init__(label)
        self.label = label


def read_bytes_text(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8", "surrogateescape")


LINE_RE = re.compile(r"[^\n]*\n|[^\n]+")


def split_line(line):
    """(content, ending) with ending one of \\r\\n, \\n or empty."""
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def frontmatter_span(lines):
    """Index range (1, end) of frontmatter lines, or None without frontmatter."""
    if not lines or split_line(lines[0])[0] != "---":
        return None
    for idx in range(1, len(lines)):
        if split_line(lines[idx])[0] == "---":
            return (1, idx)
    return None


def strip_quotes(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value.strip()


def find_field_lines(lines, span):
    found = {}
    for idx in range(span[0], span[1]):
        content = split_line(lines[idx])[0]
        for key in ("model", "effort"):
            if key not in found and content.startswith(key + ":"):
                found[key] = idx
    return found


def parse_agent_defaults(text, label):
    """(model, effort) from the frontmatter. Raises MissingFieldsError carrying `label`."""
    lines = LINE_RE.findall(text)
    span = frontmatter_span(lines)
    found = find_field_lines(lines, span) if span else {}
    if "model" not in found or "effort" not in found:
        raise MissingFieldsError(label)
    values = []
    for key in ("model", "effort"):
        content = split_line(lines[found[key]])[0]
        values.append(strip_quotes(content[len(key) + 1:]))
    return (values[0], values[1])


def render_agent(text, model, effort, label="agent file"):
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


def frontmatter_name(path):
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
            value = line[len("name:"):].strip(" \t\n\r\v\f")
            if len(value) >= 3 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value
    return None


def find_agent_md_files(agents_dir):
    """Regular files and symlinks named *.md, anywhere under agents_dir, in the
    order `find` prints them: directory order, descending into a real directory
    right when it is met. Not sorted."""
    found = []
    try:
        entries = list(os.scandir(agents_dir))
    except OSError:
        return found
    for entry in entries:
        is_link = entry.is_symlink()
        if entry.name.endswith(".md") and (is_link or entry.is_file(follow_symlinks=False)):
            found.append(entry.path)
        if not is_link and entry.is_dir(follow_symlinks=False):
            found.extend(find_agent_md_files(entry.path))
    return found


def list_files_sorted(folder):
    """Return every non-hidden file under folder, sorted, as absolute paths."""
    if not os.path.isdir(folder):
        return []
    found = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if not name.startswith("."):
                found.append(os.path.join(dirpath, name))
    return found
