"""Collectors for the dashboard: settings files, environment, agent files, rules files.

Each collector reads files the caller names and returns plain data with the
path and line of every value. Secret-looking values are replaced with the word
"hidden" here, before anything else sees them. Standard library only, Python 3.9.

The module never calls os.path.expanduser or Path.home, never reads os.environ
and writes nothing. Every folder and the environment come in as arguments, and
every path in the output is built with os.path.join from those arguments.

It does not return launch flags, --settings content, MDM (mobile device
management) settings or server-managed settings, because the dashboard cannot
see them.
"""
import bisect
import copy
import json
import json.decoder
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for _path in (HERE, REPO):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import agent_frontmatter  # noqa: E402
import agent_md  # noqa: E402

HIDDEN = "hidden"
SECRET_NAME_PARTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")
SECRET_VALUE_PREFIXES = ("sk-", "Bearer ")

MANAGED_FILE = "managed-settings.json"
MANAGED_FOLDER = "managed-settings.d"

# Managed settings merge rules, from
# https://code.claude.com/docs/en/managed-settings#split-a-file-based-policy-across-teams
# A later file replaces these top-level values whole.
_REPLACE_WHOLE = (("fallbackModel",), ("modelPicker",))
# A later file replaces these top-level objects entry by entry.
_REPLACE_ENTRY = (("extraKnownMarketplaces",), ("managedMcpServers",))

_LINE_BREAK_RE = re.compile(r"\r\n|\n|\r")
_JSON_SPACE = " \t\n\r"


# Masking

def is_secret_name(name):
    """True when the name contains any secret part, in any case."""
    if not isinstance(name, str):
        return False
    upper = name.upper()
    return any(part in upper for part in SECRET_NAME_PARTS)


def is_secret_value(value):
    """True for a string that starts with a secret prefix, in any case.

    Leading white space is ignored, so " sk-..." hides too.
    """
    if not isinstance(value, str):
        return False
    start = value.lstrip().lower()
    return any(start.startswith(prefix.lower()) for prefix in SECRET_VALUE_PREFIXES)


def mask(value, name=None):
    """Return value with every secret-looking part replaced by HIDDEN.

    A secret name hides the whole value, a dict or list included. A dict masks
    each item under its own key, a list masks each item under the list's name,
    and a string with a secret prefix is hidden. Anything else is unchanged.
    """
    if is_secret_name(name):
        return HIDDEN
    if isinstance(value, dict):
        return {key: mask(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [mask(item, name) for item in value]
    if is_secret_value(value):
        return HIDDEN
    return value


# Key lines

def json_key_lines(text):
    """Return {path tuple: 1-based line} for every object key of valid JSON.

    The path is the tuple of keys from the top, so ("env", "FOO") and
    ("modelSettings", "us.anthropic.x-v1:0", "effortLevel") work even when a key
    holds dots. Arrays are skipped without looking inside. When an object
    repeats a key the last one wins, as json.loads does. Call it only on text
    json.loads accepted.
    """
    starts = [0] + [m.end() for m in _LINE_BREAK_RE.finditer(text)]
    decoder = json.JSONDecoder()
    scanstring = json.decoder.scanstring
    found = {}

    def line_of(pos):
        return bisect.bisect_right(starts, pos)

    def skip(i):
        while i < len(text) and text[i] in _JSON_SPACE:
            i += 1
        return i

    def drop(path):
        size = len(path)
        for other in [k for k in found if k[:size] == path]:
            del found[other]

    def value(i, path):
        ch = text[i]
        if ch == "{":
            return obj(i, path)
        if ch == '"':
            return scanstring(text, i + 1)[1]
        return decoder.raw_decode(text, i)[1]

    def obj(i, path):
        i = skip(i + 1)
        if text[i] == "}":
            return i + 1
        seen = set()
        while True:
            line = line_of(i)
            key, i = scanstring(text, i + 1)
            i = skip(skip(i) + 1)  # past the colon
            child = path + (key,)
            if key in seen:
                drop(child)
            seen.add(key)
            found[child] = line
            i = skip(value(i, child))
            if text[i] == ",":
                i = skip(i + 1)
                continue
            return i + 1

    value(skip(0), ())
    return found


# Settings

def _read_bytes(path):
    """Return (bytes, status). Status is "ok", "missing" or "unreadable"."""
    try:
        with open(path, "rb") as fh:
            return fh.read(), "ok"
    except (FileNotFoundError, NotADirectoryError):
        return None, "missing"
    except OSError:
        return None, "unreadable"


def _read_settings_file(layer, path, managed):
    """Return (record, data, where). record is None for a missing file.

    data and where are None unless the record's status is "ok". data is not
    masked yet.
    """
    raw, status = _read_bytes(path)
    if status == "missing":
        return None, None, None
    if status == "unreadable":
        return {"layer": layer, "path": path, "status": "unreadable", "line": None}, None, None

    def unparsed(line):
        return {"layer": layer, "path": path, "status": "unparsed", "line": line}, None, None

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return unparsed(raw[:exc.start].count(b"\n") + 1)
    if managed and text == "":
        return {"layer": layer, "path": path, "status": "ok", "line": None}, {}, {}
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return unparsed(1)
        lines = json_key_lines(text)
    except json.JSONDecodeError as exc:
        return unparsed(exc.lineno)
    except (ValueError, IndexError, RecursionError):
        return unparsed(1)
    where = {key: {"path": path, "line": line} for key, line in lines.items()}
    return {"layer": layer, "path": path, "status": "ok", "line": None}, data, where


def _managed_paths(managed_dir):
    """Return (paths in merge order, a record for an unlistable folder or None)."""
    paths = [os.path.join(managed_dir, MANAGED_FILE)]
    folder = os.path.join(managed_dir, MANAGED_FOLDER)
    try:
        names = os.listdir(folder)
    except (FileNotFoundError, NotADirectoryError):
        return paths, None
    except OSError:
        return paths, {"layer": "managed", "path": folder, "status": "unreadable", "line": None}
    for name in sorted(names):
        full = os.path.join(folder, name)
        if name.endswith(".json") and not name.startswith(".") and os.path.isfile(full):
            paths.append(full)
    return paths, None


def _drop_where(where, path):
    size = len(path)
    for key in [k for k in where if k[:size] == path]:
        del where[key]


def _take_where(where, path, other):
    """Point path and everything under it at the entries `other` holds."""
    _drop_where(where, path)
    size = len(path)
    for key, entry in other.items():
        if key[:size] == path:
            where[key] = entry


def _combine_lists(old, new):
    out = []
    seen = set()
    for item in list(old) + list(new):
        marker = json.dumps(item, sort_keys=True)
        if marker not in seen:
            seen.add(marker)
            out.append(item)
    return out


def _merge_into(acc, where, new, new_where, path):
    """Merge the dict `new` into `acc`, and keep `where` pointing at the right file."""
    for key, value in new.items():
        child = path + (key,)
        if key not in acc:
            acc[key] = copy.deepcopy(value)
            _take_where(where, child, new_where)
            continue
        old = acc[key]
        if len(child) == 1 and child in _REPLACE_WHOLE:
            acc[key] = copy.deepcopy(value)
            _take_where(where, child, new_where)
        elif len(child) == 1 and child in _REPLACE_ENTRY and isinstance(old, dict) \
                and isinstance(value, dict):
            for name, entry in value.items():
                acc[key][name] = copy.deepcopy(entry)
                _take_where(where, child + (name,), new_where)
            where[child] = new_where[child]
        elif isinstance(old, dict) and isinstance(value, dict):
            _merge_into(old, where, value, new_where, child)
            where[child] = new_where[child]
        elif isinstance(old, list) and isinstance(value, list):
            acc[key] = _combine_lists(old, value)
            _take_where(where, child, new_where)
        else:
            acc[key] = copy.deepcopy(value)
            _take_where(where, child, new_where)


def collect_settings(config_dir, project_dir, managed_dir):
    """Read the settings files.

    Returns {"sources": [...], "files": [...]}. "files" has one record per file
    that exists, with its status (ok, unparsed or unreadable) and, for an
    unparsed file, the line of the problem. "sources" has one entry per layer
    that parsed, highest first: the merged managed files, local, project, user.
    Each is {"layer", "data", "where"}, with data masked and where mapping each
    key path to {"path", "line"}.
    """
    files = []
    managed = []  # (data, where) of each ok managed file, in merge order
    if managed_dir is not None:
        paths, folder_record = _managed_paths(managed_dir)
        for path in paths:
            record, data, where = _read_settings_file("managed", path, True)
            if record is None:
                continue
            files.append(record)
            if data is not None:
                managed.append((mask(data), where))
        if folder_record is not None:
            files.append(folder_record)
    plain = []
    for layer, path in (
        ("local", os.path.join(project_dir, ".claude", "settings.local.json")),
        ("project", os.path.join(project_dir, ".claude", "settings.json")),
        ("user", os.path.join(config_dir, "settings.json")),
    ):
        record, data, where = _read_settings_file(layer, path, False)
        if record is None:
            continue
        files.append(record)
        if data is not None:
            plain.append({"layer": layer, "data": mask(data), "where": where})
    sources = []
    if managed:
        merged = {}
        merged_where = {}
        for data, where in managed:
            _merge_into(merged, merged_where, data, where, ())
        sources.append({"layer": "managed", "data": merged, "where": merged_where})
    sources.extend(plain)
    return {"sources": sources, "files": files}


# Environment

def collect_env(sources, shell_env, variable_names):
    """Return {NAME: [record, ...]} with settings records first, then the shell's.

    A settings record comes from an env block in `sources`, in source order,
    and carries its layer, path and line. The shell record carries no path. A
    shell variable is kept only when `variable_names` names it or an env block
    set it, so nothing else of the shell leaves this function. Values are
    masked by variable name and by value.
    """
    out = {}
    for source in sources:
        block = source["data"].get("env")
        if not isinstance(block, dict):
            continue
        for name, value in block.items():
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                continue
            spot = source["where"].get(("env", name), {})
            out.setdefault(name, []).append({
                "value": mask(str(value), name),
                "origin": "settings",
                "layer": source["layer"],
                "path": spot.get("path"),
                "line": spot.get("line"),
            })
    named = set(variable_names)
    for name, value in shell_env.items():
        if not isinstance(value, str):
            continue
        if name in named or name in out:
            out.setdefault(name, []).append({"value": mask(value, name), "origin": "shell"})
    return out


# Agents and rules files

def collect_agents(config_dir, project_dir):
    """Read every file under the two agent folders, subfolders included.

    Returns one {"layer", "path", "fields", "errors", "lines"} per file, project
    folder first. fields is masked. A file the reader rejects keeps its errors.
    No file text is returned.
    """
    out = []
    for layer, folder in (
        ("project", os.path.join(project_dir, ".claude", "agents")),
        ("user", os.path.join(config_dir, "agents")),
    ):
        for path in agent_md.list_files_sorted(folder):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                text = None
            fields, errors, lines = agent_frontmatter.read_frontmatter_lines(text)
            out.append({
                "layer": layer,
                "path": path,
                "fields": mask(fields),
                "errors": errors,
                "lines": lines,
            })
    return out


def collect_rules_files(config_dir, project_dir):
    """List every file under the two rules folders as {"layer", "path"}."""
    out = []
    for layer, folder in (
        ("project", os.path.join(project_dir, ".claude", "rules")),
        ("user", os.path.join(config_dir, "rules")),
    ):
        for path in agent_md.list_files_sorted(folder):
            out.append({"layer": layer, "path": path})
    return out


def collect(config_dir, project_dir, managed_dir, shell_env, rules):
    """Run every collector. `rules` is the rules.json document."""
    settings = collect_settings(config_dir, project_dir, managed_dir)
    names = [v["name"] for v in rules.get("variables", [])]
    return {
        "settings": settings["sources"],
        "settings_files": settings["files"],
        "env": collect_env(settings["sources"], shell_env, names),
        "agents": collect_agents(config_dir, project_dir),
        "rules_files": collect_rules_files(config_dir, project_dir),
    }
