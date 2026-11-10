# ruff: noqa: E501, TRY003
"""Build, check and copy the setup fixture corpus (m4-build.md task 2).

Usage (from the worktree root)::

    python3 app/fixtures/setup/build_corpus.py          # write corpus/ and demo-overlay/
    python3 app/fixtures/setup/build_corpus.py --check  # fail when the files differ

``corpus/<case>/`` is one world:

* ``home/`` is the fake HOME, ``home/.claude/`` the config folder and ``home/.claude.json``
  the masked user file.
* ``managed/`` is the managed folder.
* ``work/parent/<project>/`` is the listed project. ``work/parent/`` holds the ancestor
  files and, for a git-root case, a ``.git`` marker made at copy time.
* ``session.json`` holds ``shell_env``. ``case.json`` holds the project folder name,
  whether the project is listed, whether ``work/parent`` is a git root and the plan.
* ``expected.json`` is the spec the collectors must meet. For ``complex`` and ``stress`` it
  is generated with the files. For every other case it is written by hand, so this
  script never touches it and ``--check`` only requires that it exists.

``materialize`` copies a case to a folder, fills the absolute paths in and writes
``home/.claude/routing-dashboard.json``. ``make_unreadable`` makes the files git can't
hold. Two runs give the same bytes. Only the standard library is used.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cases_complex
import cases_core
import cases_edge
import cases_stress
import demo_overlay
from corpus_types import Case, Link, dump_json

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
OVERLAY = HERE / "demo-overlay"

# Same numbers as app/server/setup_contract.py, which this stdlib-only script can't import.
FILE_CAP_BYTES = 1024 * 1024
CLAUDE_JSON_CAP_BYTES = 32 * 1024 * 1024

EXPECTED = "expected.json"
MERGE_SUFFIX = ".merge.json"
PLACEHOLDER = "@@"

Tree = dict[str, "str | bytes | Link"]


class Layout(NamedTuple):
    """Where a materialized case keeps its parts."""

    root: Path
    home: Path
    config: Path
    claude_json: Path
    project: Path
    managed: Path
    session: Path


def all_cases() -> list[Case]:
    """Return every case, sorted by name."""
    found = [
        *cases_core.cases(),
        *cases_edge.cases(),
        cases_complex.case(),
        cases_stress.case(),
    ]
    return sorted(found, key=lambda c: c.name)


def secrets_document() -> dict[str, Any]:
    """Return the content of ``secrets.json``.

    ``secrets`` are fake secrets the masking sweep must never find in an answer.
    ``never`` are values in places no collector may read or keep (dropped keys, auto
    memory), which must not reach an answer either.
    """
    secrets = [
        *cases_core.TYPICAL_SECRETS,
        *cases_complex.COMPLEX_SECRETS,
        *demo_overlay.OVERLAY_SECRETS,
    ]
    never = [
        *cases_core.NEVER,
        {
            "value": "MEMORY-SENTINEL-DO-NOT-READ",
            "kind": "auto_memory",
            "case": "scope-memory",
            "file": "home/.claude/projects/x/memory/MEMORY.md",
        },
    ]

    def order(row: dict[str, object]) -> tuple[str, str, str]:
        return (str(row["case"]), str(row["file"]), str(row["value"]))

    return {
        "note": "Made-up values. The masking sweep must find none of them in any answer.",
        "secrets": sorted(secrets, key=order),
        "never": sorted(never, key=order),
    }


def _render(case: Case) -> dict[str, str | Link]:
    files: dict[str, str | Link] = dict(case.files)
    files["case.json"] = dump_json(case.meta)
    files["session.json"] = dump_json(case.session)
    if case.expected is not None:
        files[EXPECTED] = dump_json(case.expected)
    return files


def _write(files: dict[str, str | Link], dest: Path) -> None:
    for rel in sorted(files):
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        content = files[rel]
        if isinstance(content, Link):
            path.symlink_to(content.target)
        else:
            with path.open("w", encoding="utf-8", newline="") as handle:
                handle.write(content)


def generate(corpus: Path = CORPUS, overlay: Path = OVERLAY) -> None:
    """Write the corpus and the demo overlay, keeping every hand-written expected.json."""
    cases = all_cases()
    corpus.mkdir(parents=True, exist_ok=True)
    names = {case.name for case in cases}
    for stale in sorted(
        p for p in corpus.iterdir() if p.is_dir() and p.name not in names
    ):
        shutil.rmtree(stale)
    for case in cases:
        folder = corpus / case.name
        kept: str | None = None
        if case.expected is None and (folder / EXPECTED).is_file():
            kept = (folder / EXPECTED).read_text(encoding="utf-8")
        if folder.exists():
            shutil.rmtree(folder)
        _write(_render(case), folder)
        if kept is not None:
            (folder / EXPECTED).write_text(kept, encoding="utf-8", newline="")
    (corpus / "secrets.json").write_text(
        dump_json(secrets_document()), encoding="utf-8", newline=""
    )
    if overlay.exists():
        shutil.rmtree(overlay)
    _write(demo_overlay.overlay_files(), overlay)


def _read_tree(root: Path) -> Tree:
    tree: Tree = {}
    if not root.is_dir():
        return tree
    for current, dirs, names in os.walk(root):
        base = Path(current)
        for name in [*dirs, *names]:
            path = base / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                tree[rel] = Link(path.readlink().as_posix())
            elif path.is_file():
                tree[rel] = path.read_bytes()
    return tree


def _same(a: str | bytes | Link, b: str | bytes | Link) -> bool:
    if isinstance(a, Link) or isinstance(b, Link):
        return a == b
    left = a.encode("utf-8") if isinstance(a, str) else a
    right = b.encode("utf-8") if isinstance(b, str) else b
    return left == right


def check(corpus: Path = CORPUS, overlay: Path = OVERLAY) -> list[str]:
    """Compare the committed files with a fresh generation and list every difference.

    Returns:
        A list of messages, empty when the committed files equal a fresh generation.
        A hand-written expected.json is only checked for existing.
    """
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="bartab-corpus-") as tmp:
        fresh_corpus = Path(tmp) / "corpus"
        fresh_overlay = Path(tmp) / "overlay"
        generate(fresh_corpus, fresh_overlay)
        pairs = [
            (fresh_corpus, corpus, "corpus"),
            (fresh_overlay, overlay, "demo-overlay"),
        ]
        hand = {c.name for c in all_cases() if c.expected is None}
        for fresh_root, real_root, label in pairs:
            fresh = _read_tree(fresh_root)
            real = _read_tree(real_root)
            if label == "corpus":
                for name in sorted(hand):
                    if f"{name}/{EXPECTED}" not in real:
                        problems.append(
                            f"{label}/{name}/{EXPECTED} is missing (written by hand)"
                        )
                    real.pop(f"{name}/{EXPECTED}", None)
            for rel in sorted(set(fresh) | set(real)):
                if rel not in real:
                    problems.append(f"{label}/{rel} is missing")
                elif rel not in fresh:
                    problems.append(f"{label}/{rel} is not generated")
                elif not _same(fresh[rel], real[rel]):
                    problems.append(f"{label}/{rel} differs from a fresh generation")
    return problems


def layout(dest: Path) -> Layout:
    """Return where a materialized case keeps its parts."""
    meta = json.loads((dest / "case.json").read_text(encoding="utf-8"))
    return Layout(
        root=dest,
        home=dest / "home",
        config=dest / "home" / ".claude",
        claude_json=dest / "home" / ".claude.json",
        project=dest / "work" / "parent" / meta["project"],
        managed=dest / "managed",
        session=dest / "session.json",
    )


def _fill_placeholders(root: Path, values: dict[str, str]) -> None:
    for current, _dirs, names in os.walk(root):
        for name in names:
            path = Path(current) / name
            if path.is_symlink():
                continue
            data = path.read_bytes()
            if PLACEHOLDER.encode() not in data:
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            for key, value in values.items():
                text = text.replace(key, value)
            path.write_bytes(text.encode("utf-8"))


def materialize(case: str, dest: Path, corpus: Path | None = None) -> Path:
    """Copy a case to ``dest`` and make it a runnable world.

    Symlinks are kept as links. Absolute paths replace ``@@HOME@@``, ``@@CONFIG@@`` and
    ``@@PROJECT@@``, empty folders git can't hold are made, the ``.git`` marker of a
    git-root case is made, and ``home/.claude/routing-dashboard.json`` lists the case's
    project by absolute path (an empty list for an unlisted project).

    Args:
        case: The case name.
        dest: A folder that does not exist yet, outside every repo (fact T-c826).
        corpus: The corpus folder to copy from, default the committed one.

    Returns:
        The real path of the copy.

    Raises:
        FileNotFoundError: The case does not exist.
    """
    source = (corpus or CORPUS) / case
    if not source.is_dir():
        raise FileNotFoundError(f"no corpus case {case!r} under {source.parent}")
    real = Path(os.path.realpath(dest))
    shutil.copytree(source, real, symlinks=True)
    meta: dict[str, Any] = json.loads((real / "case.json").read_text(encoding="utf-8"))
    lay = layout(real)
    for folder in (lay.config, lay.project, lay.managed):
        folder.mkdir(parents=True, exist_ok=True)
    if meta["git_root"]:
        (lay.project.parent / ".git").mkdir(exist_ok=True)
    _fill_placeholders(
        real,
        {
            "@@HOME@@": str(lay.home),
            "@@CONFIG@@": str(lay.config),
            "@@PROJECT@@": str(lay.project),
        },
    )
    projects = (
        [{"name": str(meta["project"]).capitalize(), "path": str(lay.project)}]
        if meta["listed"]
        else []
    )
    listing = {"projects": projects, "plan": meta["plan"]}
    (lay.config / "routing-dashboard.json").write_text(
        dump_json(listing), encoding="utf-8", newline=""
    )
    return real


UNREADABLE_KINDS = ("mode000", "not_utf8", "too_large", "claude_json_too_large")
_UNREADABLE_DEFAULTS = {
    "mode000": "home/.claude/settings.json",
    "not_utf8": "work/parent/proj/CLAUDE.md",
    "too_large": "home/.claude/agents/huge.md",
    "claude_json_too_large": "home/.claude.json",
}


def make_unreadable(dest: Path, kind: str, relpath: str | None = None) -> Path:
    """Make a file a collector can't read, in a materialized copy.

    Git can't hold these, so tests make them in their own temp copy. The mode 000 kind
    needs a non-root user to take effect (m4-build.md section 8).

    Args:
        dest: A materialized case folder.
        kind: ``mode000`` (mode 0), ``not_utf8`` (invalid UTF-8 bytes), ``too_large`` (one
            byte over the 1 MiB cap) or ``claude_json_too_large`` (a sparse file one byte
            over the 32 MiB cap).
        relpath: The file to damage, relative to ``dest``. A default per kind.

    Returns:
        The path of the file.

    Raises:
        ValueError: ``kind`` is not one of ``UNREADABLE_KINDS``.
    """
    if kind not in UNREADABLE_KINDS:
        raise ValueError(f"unknown kind {kind!r}, use one of {UNREADABLE_KINDS}")
    path = dest / (relpath or _UNREADABLE_DEFAULTS[kind])
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "mode000":
        if not path.exists():
            path.write_text("{}\n", encoding="utf-8")
        path.chmod(0)
    elif kind == "not_utf8":
        path.write_bytes(b"# Notes\n\xff\xfe\xfd not utf-8\n")
    elif kind == "too_large":
        head = b"---\nname: huge\ndescription: Over the cap.\n---\n"
        path.write_bytes(head + b"x" * (FILE_CAP_BYTES + 1 - len(head)))
    else:
        with path.open("wb") as handle:
            handle.truncate(CLAUDE_JSON_CAP_BYTES + 1)
    return path


def _merge(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    for key, value in new.items():
        if key not in existing:
            existing[key] = value
        elif isinstance(existing[key], dict) and isinstance(value, dict):
            _merge(existing[key], value)
    return existing


def apply_demo_overlay(demo_dir: Path, overlay: Path | None = None) -> None:
    """Apply the setup overlay over a demo build folder. Idempotent.

    The demo build has ``config/``, ``projects/<dir>/``, ``managed/`` and
    ``session.json``. Overlay files are copied in, ``*.merge.json`` files are merged into
    the demo's existing JSON (its own keys win), ``@@DEMO@@`` and ``@@CONFIG@@`` become
    absolute paths, and the three extra projects are appended to
    ``config/routing-dashboard.json``. Nothing the demo built is overwritten except
    through a merge.

    Args:
        demo_dir: The folder ``tests/fixtures/demo/build_demo.py`` made.
        overlay: The overlay folder, default the committed one.

    Raises:
        FileNotFoundError: The folder is not a demo build.
    """
    root = Path(os.path.realpath(demo_dir))
    config = root / "config"
    listing_path = config / "routing-dashboard.json"
    if not listing_path.is_file():
        raise FileNotFoundError(
            f"{root} is not a demo build (no config/routing-dashboard.json)"
        )
    values = {"@@DEMO@@": str(root), "@@CONFIG@@": str(config)}
    tree = _read_tree(overlay or OVERLAY)
    extra = json.loads(bytes_text(tree.pop("extra-projects.json")))
    for rel in sorted(tree):
        content = tree[rel]
        target = root / rel
        if isinstance(content, Link):
            continue
        text = bytes_text(content)
        for key, value in values.items():
            text = text.replace(key, value)
        if rel.endswith(MERGE_SUFFIX):
            target = root / (rel[: -len(MERGE_SUFFIX)] + ".json")
            base: dict[str, Any] = (
                json.loads(target.read_text(encoding="utf-8"))
                if target.is_file()
                else {}
            )
            text = dump_json(_merge(base, json.loads(text)))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="")
    listing: dict[str, Any] = json.loads(listing_path.read_text(encoding="utf-8"))
    names = {entry["name"] for entry in listing["projects"]}
    for entry in extra["projects"]:
        if entry["name"] not in names:
            listing["projects"].append(
                {"name": entry["name"], "path": str(root / entry["dir"])}
            )
    listing_path.write_text(dump_json(listing), encoding="utf-8", newline="")


def bytes_text(content: str | bytes | Link) -> str:
    """Return a tree entry as text. A link has none."""
    if isinstance(content, Link):
        raise TypeError("a link has no text")
    return content.decode("utf-8") if isinstance(content, bytes) else content


def main(argv: list[str] | None = None) -> int:
    """Write the corpus, or with ``--check`` verify it. Returns the exit code."""
    parser = argparse.ArgumentParser(description="Build the setup fixture corpus.")
    parser.add_argument("--check", action="store_true", help="fail when files differ")
    args = parser.parse_args(argv)
    if args.check:
        problems = check()
        for line in problems:
            sys.stdout.write(line + "\n")
        sys.stdout.write("corpus check: " + ("FAILED\n" if problems else "ok\n"))
        return 1 if problems else 0
    generate()
    sys.stdout.write(f"wrote {len(all_cases())} cases to {CORPUS}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
