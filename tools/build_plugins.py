#!/usr/bin/env python3
"""Build the generated payload of each plugin under plugins/ (routing-dashboard and hivemind).

    python3 tools/build_plugins.py           write plugins/<name>/payload/ and plugins/<name>/LICENSE
    python3 tools/build_plugins.py --check   write nothing, print each differing path, exit 1 on drift

The build also writes plugins/<name>/payload/BUILD.json: the plugin.json version and a sha256
over the payload (the sorted relative path, exec bit and bytes of every payload file except
BUILD.json itself; the plugin-level LICENSE sits outside payload/ and is not hashed). The
version in plugin.json pins what installed users get, so a plain build refuses to write a
changed payload under an unchanged version. Bump the version, then build again.

The payload is a byte copy of repo files (the dashboard and installer for routing-dashboard,
hooks/hivemind_lib.py for hivemind), so a colleague who installs a plugin gets the same code
the repo holds. Nobody edits the payload by hand. The drift test
in tests/test_plugin_build.py runs --check, so a change to a source file without a rebuild
fails the suite.

Python 3.9 standard library only. It never imports install.py or any dashboard module; it
reads HOOK_NAMES by parsing the text of install.py.
"""
import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import ast  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
PLUGINS_DIR = "plugins"
GIT_TIMEOUT = 20
BUILD_NAME = "BUILD.json"


class BuildError(Exception):
    """A problem that stops the run with exit code 2."""


# ---- Source lists -----------------------------------------------------------

def hook_names(repo):
    """HOOK_NAMES from the text of install.py, without importing it."""
    path = os.path.join(repo, "install.py")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), path)
    except (OSError, SyntaxError) as exc:
        raise BuildError("cannot read HOOK_NAMES from %s: %s" % (path, exc))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "HOOK_NAMES":
                    value = ast.literal_eval(node.value)
                    if (isinstance(value, list) and value
                            and all(isinstance(v, str) for v in value)):
                        return value
    raise BuildError("install.py has no HOOK_NAMES list of strings")


def keep_name(name):
    return not name.startswith(".") and name != "__pycache__"


def is_file(path):
    return os.path.isfile(path) and not os.path.islink(path)


def top_files(repo, folder, suffixes):
    """Regular files directly inside repo/folder whose name ends with one of suffixes."""
    base = os.path.join(repo, folder)
    if not os.path.isdir(base):
        return []
    return ["%s/%s" % (folder, name) for name in sorted(os.listdir(base))
            if keep_name(name) and name.endswith(suffixes) and is_file(os.path.join(base, name))]


def tree_files(repo, folder):
    """Every regular file under repo/folder, skipping dotfiles, dot folders and __pycache__."""
    found = []
    top = os.path.join(repo, folder)
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames[:] = sorted(d for d in dirnames
                             if keep_name(d) and not os.path.islink(os.path.join(dirpath, d)))
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if keep_name(name) and is_file(full):
                found.append(os.path.relpath(full, repo).replace(os.sep, "/"))
    return found


def routing_dashboard_files(repo):
    """Source paths (relative to the repo root, forward slashes) for the routing-dashboard payload."""
    rels = ["install.py", "agent_md.py"]
    rels += top_files(repo, "dashboard", (".py", ".json"))
    rels.append("dashboard/reference_copy.md")
    rels += tree_files(repo, "dashboard/static")
    rels += top_files(repo, "agents", (".md",))
    rels += top_files(repo, "rules", (".md",))
    rels += ["hooks/" + name for name in hook_names(repo)]
    rels += tree_files(repo, "skills")
    rels.append("docs/model-routing-reference.md")
    return sorted(set(rels))


def hivemind_files(repo):
    """Source paths for the hivemind payload: the HiveMind library and nothing else."""
    return ["hooks/hivemind_lib.py"]


# One row per plugin. `files` is a callable(repo) that returns the source paths. `folders` is
# what the --check message names as the sources to rebuild from.
PLUGINS = [
    {
        "name": "routing-dashboard",
        "files": routing_dashboard_files,
        "folders": ["install.py", "agent_md.py", "dashboard/", "agents/", "rules/", "hooks/",
                    "skills/", "docs/model-routing-reference.md", "LICENSE"],
    },
    {"name": "hivemind", "files": hivemind_files, "folders": ["hooks/hivemind_lib.py", "LICENSE"]},
]


# ---- Tracked files ----------------------------------------------------------

def tracked_files(repo):
    """The set of tracked paths when git's work tree is exactly repo, else None.

    A copy of the repo inside some other git tree (or none) walks the folders instead, so
    the parent repo's file list can never decide what the copy builds.
    """
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_NO_LAZY_FETCH"] = "1"

    def git(*args):
        return subprocess.run(
            ["git", "-c", "core.fsmonitor=false"] + list(args),
            cwd=repo, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=GIT_TIMEOUT)

    try:
        top = git("rev-parse", "--show-toplevel")
        if top.returncode != 0:
            return None
        if os.path.realpath(top.stdout.decode("utf-8", "surrogateescape").strip()) \
                != os.path.realpath(repo):
            return None
        proc = git("ls-files", "-z")
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    return set(p for p in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if p)


# ---- Expected tree ----------------------------------------------------------

def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def exec_mode(path):
    return 0o755 if os.stat(path).st_mode & stat.S_IXUSR else 0o644


def manifest_path(plugin):
    return "%s/%s/.claude-plugin/plugin.json" % (PLUGINS_DIR, plugin["name"])


def manifest_version(repo, plugin):
    path = os.path.join(repo, *manifest_path(plugin).split("/"))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            version = json.load(fh).get("version")
    except (OSError, ValueError, AttributeError) as exc:
        raise BuildError("cannot read the version from %s: %s" % (manifest_path(plugin), exc))
    if not isinstance(version, str) or not version:
        raise BuildError("%s has no version string" % manifest_path(plugin))
    return version


def payload_sha256(want, base):
    """sha256 over the sorted (relative path, exec bit, bytes) of every payload file but BUILD.json."""
    items = []
    for rel, (data, mode) in want.items():
        if rel.startswith(base + "/") and rel != "%s/%s" % (base, BUILD_NAME):
            items.append((rel[len(base) + 1:], mode, data))
    digest = hashlib.sha256()
    for sub, mode, data in sorted(items):
        digest.update(sub.encode("utf-8", "surrogateescape") + b"\0")
        digest.update(b"x\0" if mode & stat.S_IXUSR else b"-\0")
        digest.update(str(len(data)).encode("ascii") + b"\0")
        digest.update(data)
    return digest.hexdigest()


def build_record(version, digest):
    text = json.dumps({"plugin_version": version, "payload_sha256": digest}, indent=2, sort_keys=True)
    return (text + "\n").encode("utf-8")


def read_build_record(repo, plugin):
    """The parsed BUILD.json on disk as a dict, or None when it is missing or unreadable."""
    path = os.path.join(repo, PLUGINS_DIR, plugin["name"], "payload", BUILD_NAME)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def expected(repo, plugin, tracked):
    """{repo-relative destination: (bytes, mode)} for one plugin."""
    name = plugin["name"]
    payload = "%s/%s/payload" % (PLUGINS_DIR, name)
    out = {}
    for rel in plugin["files"](repo):
        src = os.path.join(repo, rel)
        if not is_file(src):
            raise BuildError("source file is missing: %s" % rel)
        if tracked is not None and rel not in tracked:
            continue
        out["%s/%s" % (payload, rel)] = (read_bytes(src), exec_mode(src))
    out["%s/%s" % (payload, BUILD_NAME)] = (
        build_record(manifest_version(repo, plugin), payload_sha256(out, payload)), 0o644)
    license_src = os.path.join(repo, "LICENSE")
    if not is_file(license_src):
        raise BuildError("source file is missing: LICENSE")
    out["%s/%s/LICENSE" % (PLUGINS_DIR, name)] = (read_bytes(license_src), exec_mode(license_src))
    return out


def existing_payload(repo, plugin):
    """Repo-relative paths of everything under payload/: {path: kind} with kind file, dir or other."""
    base = "%s/%s/payload" % (PLUGINS_DIR, plugin["name"])
    top = os.path.join(repo, base)
    found = {}
    for dirpath, dirnames, filenames in os.walk(top):
        for d in dirnames:
            full = os.path.join(dirpath, d)
            rel = os.path.relpath(full, repo).replace(os.sep, "/")
            found[rel] = "other" if os.path.islink(full) else "dir"
        for f in filenames:
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, repo).replace(os.sep, "/")
            found[rel] = "file" if is_file(full) else "other"
    return found


# ---- Compare and write ------------------------------------------------------

def differences(repo, plugin, want):
    """Sorted (path, reason) pairs between the wanted files and what is on disk."""
    base = "%s/%s/payload" % (PLUGINS_DIR, plugin["name"])
    diffs = []
    have = existing_payload(repo, plugin)
    for rel, (data, mode) in sorted(want.items()):
        full = os.path.join(repo, rel)
        if not os.path.lexists(full):
            diffs.append((rel, "missing"))
        elif not is_file(full):
            diffs.append((rel, "not a regular file"))
        else:
            if read_bytes(full) != data:
                diffs.append((rel, build_reason(repo, plugin, data)
                              if rel == "%s/%s" % (base, BUILD_NAME) else "changed bytes"))
            elif exec_mode(full) != mode:
                diffs.append((rel, "changed exec bit"))
    for rel, kind in sorted(have.items()):
        if kind == "dir":
            continue
        if rel not in want:
            diffs.append((rel, "extra"))
    wanted_dirs = set()
    for rel in want:
        parent = os.path.dirname(rel)
        while parent.startswith(base) and parent != os.path.dirname(base):
            wanted_dirs.add(parent)
            parent = os.path.dirname(parent)
    for rel, kind in sorted(have.items()):
        if kind == "dir" and rel not in wanted_dirs:
            diffs.append((rel + "/", "extra empty folder"))
    return diffs


def build_reason(repo, plugin, data):
    """Why BUILD.json on disk differs from the one the sources produce."""
    want = json.loads(data.decode("utf-8"))
    have = read_build_record(repo, plugin)
    if have is None:
        return "unreadable BUILD.json"
    if have.get("plugin_version") != want["plugin_version"]:
        return "BUILD.json plugin_version %s differs from plugin.json %s" % (
            have.get("plugin_version"), want["plugin_version"])
    if have.get("payload_sha256") != want["payload_sha256"]:
        return "BUILD.json payload_sha256 does not match the payload sources"
    return "changed bytes"


def write_file(path, data, mode):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.islink(path) or (os.path.exists(path) and not os.path.isfile(path)):
        remove_any(path)
    with open(path, "wb") as fh:
        fh.write(data)
    os.chmod(path, mode)


def remove_any(path):
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        for name in os.listdir(path):
            remove_any(os.path.join(path, name))
        os.rmdir(path)


def build(repo, plugin, want):
    """Write the wanted files, then delete stale files and empty folders under payload/.
    Returns (written, removed)."""
    written = removed = 0
    for rel, (data, mode) in sorted(want.items()):
        full = os.path.join(repo, rel)
        same = (is_file(full) and read_bytes(full) == data and exec_mode(full) == mode)
        if not same:
            write_file(full, data, mode)
            written += 1
    have = existing_payload(repo, plugin)
    for rel, kind in sorted(have.items()):
        if kind != "dir" and rel not in want:
            remove_any(os.path.join(repo, rel))
            removed += 1
    base = os.path.join(repo, PLUGINS_DIR, plugin["name"], "payload")
    for dirpath, dirnames, filenames in os.walk(base, topdown=False):
        if dirpath != base and not os.listdir(dirpath):
            os.rmdir(dirpath)
            removed += 1
    return written, removed


# ---- Main -------------------------------------------------------------------

def version_guard(repo, plugin, want):
    """The refusal text when the payload changed but plugin.json still has the recorded version."""
    base = "%s/%s/payload" % (PLUGINS_DIR, plugin["name"])
    have = read_build_record(repo, plugin)
    new = json.loads(want["%s/%s" % (base, BUILD_NAME)][0].decode("utf-8"))
    if (have is not None and have.get("plugin_version") == new["plugin_version"]
            and have.get("payload_sha256") != new["payload_sha256"]):
        return ("the payload changed but %s still says version %s; bump it, then run the build again"
                % (manifest_path(plugin), new["plugin_version"]))
    return None


def run(repo, check):
    tracked = tracked_files(repo)
    all_diffs = []
    totals = []
    wants = [(plugin, expected(repo, plugin, tracked)) for plugin in PLUGINS]
    if not check:
        for plugin, want in wants:
            refusal = version_guard(repo, plugin, want)
            if refusal:
                print("error: " + refusal, file=sys.stderr)
                return 1
    for plugin, want in wants:
        if check:
            for rel, reason in differences(repo, plugin, want):
                all_diffs.append("%s: %s" % (reason, rel))
        else:
            written, removed = build(repo, plugin, want)
            size = sum(len(data) for data, _ in want.values())
            totals.append("%s: %d files, %d bytes, %d written, %d removed"
                          % (plugin["name"], len(want), size, written, removed))
    if check:
        if not all_diffs:
            print("plugin payloads match their sources")
            return 0
        for line in all_diffs:
            print(line)
        folders = sorted(set(f for p in PLUGINS for f in p["folders"]))
        print("The payload drifted from its sources (%s). Run `python3 tools/build_plugins.py` "
              "to rebuild it." % ", ".join(folders))
        return 1
    for line in totals:
        print(line)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the generated plugin payloads.")
    parser.add_argument("--check", action="store_true",
                        help="write nothing; list differing paths and exit 1 on any difference")
    args = parser.parse_args(argv)
    try:
        return run(REPO, args.check)
    except BuildError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
