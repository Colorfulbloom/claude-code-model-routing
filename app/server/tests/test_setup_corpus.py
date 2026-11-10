"""The setup fixture corpus (m4-build.md task 2): files, expected JSON, demo overlay.

The corpus lives in ``app/fixtures/setup/`` and ``build_corpus.py`` writes it. These
tests check that the committed files equal a fresh generation, that every case copies
to a runnable world, that every expected.json has the shape the collectors will meet
(field names follow ``models.py``), that every planted secret is really in a corpus
file, and that no corpus file names a real home.
"""

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast, get_args

import pytest

from models import (
    SETUP_PARTS,
    SETUP_SCOPES,
    EffectiveOrigin,
    ImportState,
    LoadsKind,
    ModelCheckStatus,
    NotReadCode,
    ProblemGroup,
    UnreadableReason,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SETUP_DIR = REPO_ROOT / "app" / "fixtures" / "setup"
CORPUS = SETUP_DIR / "corpus"
OVERLAY = SETUP_DIR / "demo-overlay"

# The first problem-code list of m4-build.md section 5, by group. A code outside it
# needs the lead's decision, so the schema check fails on it.
CODES: dict[str, set[str]] = {
    "couldnt_read": {
        "permission",
        "not_utf8",
        "too_large",
        "folder_unlistable",
        "transcript_unreadable",
    },
    "wont_load": {
        "json_invalid",
        "not_object",
        "managed_invalid",
        "value_invalid",
        "frontmatter_invalid",
        "agent_no_name",
        "agent_no_description",
        "agent_not_md",
        "same_name_in_folder",
        "skill_no_md",
        "import_missing",
        "import_too_deep",
        "import_cycle",
        "hook_bad_event",
        "hook_bad_handler",
        "mcp_bad_entry",
        "plugin_not_installed",
        "plugin_manifest_invalid",
        "output_style_missing",
        "permission_rule_invalid",
    },
    "not_as_set": {
        "ignored",
        "lowered",
        "plugin_field_ignored",
        "hooks_disabled",
        "agent_lowered",
    },
    "cant_tell": {
        "unknown",
        "import_out_of_scope",
        "env_not_visible",
        "plugin_format_unknown",
        "plugin_outside_plugins",
        "frontmatter_reader_gap",
        "walk_stopped",
    },
    "notice": {"rows_no_usage", "version_gap"},
}
# Real home prefixes, built in pieces so this file holds none of them.
HOME_NEEDLES = ("/Us" + "ers/", "/ho" + "me/")


def _load_builder() -> ModuleType:
    sys.path.insert(0, str(SETUP_DIR))
    spec = importlib.util.spec_from_file_location(
        "build_corpus", SETUP_DIR / "build_corpus.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_corpus"] = module
    spec.loader.exec_module(module)
    return module


bc = _load_builder()
CASE_NAMES = sorted(p.name for p in CORPUS.iterdir() if p.is_dir())


def _expected(case: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (CORPUS / case / "expected.json").read_text("utf-8")
    )
    return data


def _is_str_or_none(value: object) -> bool:
    return value is None or isinstance(value, str)


def _is_int_or_none(value: object) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool))


def _schema_errors(case: str, data: dict[str, Any]) -> list[str]:  # noqa: PLR0912
    """Return what is wrong with one expected.json. A small schema, written here."""
    errors: list[str] = []
    statuses = set(get_args(ModelCheckStatus))
    if data.get("case") != case:
        errors.append("case name does not match the folder")
    project = cast("dict[str, Any]", data.get("project") or {})
    if not {"name", "dir"} <= project.keys():
        errors.append("project needs name and dir")
    problems = cast("list[dict[str, Any]]", data.get("problems", []))
    all_ids: set[str] = set()
    for part, body in data.get("parts", {}).items():
        if part not in SETUP_PARTS:
            errors.append(f"unknown part {part}")
            continue
        ids = [item.get("id") for item in body.get("items", [])]
        if len(ids) != len(set(ids)):
            errors.append(f"{part}: duplicate item ids")
        all_ids.update(i for i in ids if isinstance(i, str))
        if body.get("empty") not in (None, "none_found", "not_visible"):
            errors.append(f"{part}: bad empty reason")
        for item in body.get("items", []):
            errors += _item_errors(part, item, statuses)
        for entry in body.get("unreadable", []):
            if not (_is_str_or_none(entry.get("file")) and entry.get("file")):
                errors.append(f"{part}: unreadable needs a file")
            if (
                entry.get("scope") is not None
                and entry.get("scope") not in SETUP_SCOPES
            ):
                errors.append(f"{part}: unreadable scope {entry.get('scope')}")
            if entry.get("reason") not in get_args(UnreadableReason):
                errors.append(f"{part}: unreadable reason {entry.get('reason')}")
    problem_ids: set[str] = set()
    for row in problems:
        where = f"problem {row.get('id')}"
        if row.get("id") in problem_ids:
            errors.append(f"{where}: duplicate id")
        problem_ids.add(str(row.get("id")))
        if row.get("group") not in get_args(ProblemGroup):
            errors.append(f"{where}: group {row.get('group')}")
        elif row.get("code") not in CODES[row["group"]]:
            errors.append(
                f"{where}: code {row.get('code')} is not a {row['group']} code"
            )
        if row.get("part") is not None and row.get("part") not in SETUP_PARTS:
            errors.append(f"{where}: part {row.get('part')}")
        if not _is_str_or_none(row.get("item_id")):
            errors.append(f"{where}: item_id")
        elif row.get("item_id") is not None and row["item_id"] not in all_ids:
            errors.append(f"{where}: item_id names no item")
        if not (_is_str_or_none(row.get("file")) and _is_int_or_none(row.get("line"))):
            errors.append(f"{where}: file or line")
    return errors


def _item_errors(  # noqa: PLR0912
    part: str, item: dict[str, Any], statuses: set[str]
) -> list[str]:
    errors: list[str] = []
    where = f"{part} item {item.get('id')}"
    if not str(item.get("id", "")).startswith(f"{part}:"):
        errors.append(f"{where}: id must start with the part")
    if not isinstance(item.get("key"), str):
        errors.append(f"{where}: key")
    effective = cast("dict[str, Any] | None", item.get("effective"))
    # An item nothing sets (origin default, no source) has no scope. Settings always
    # lists model and effortLevel this way (m4-build.md task 4).
    unset = (
        effective is not None
        and effective.get("origin") == "default"
        and not item.get("sources")
    )
    if item.get("scope") not in SETUP_SCOPES and not (
        unset and item.get("scope") is None
    ):
        errors.append(f"{where}: scope {item.get('scope')}")
    if item.get("status") not in statuses:
        errors.append(f"{where}: status {item.get('status')}")
    if effective is not None and not (
        (
            isinstance(effective.get("value"), str)
            or (effective.get("value") is None and effective.get("origin") == "default")
        )
        and effective.get("origin") in get_args(EffectiveOrigin)
    ):
        errors.append(f"{where}: effective")
    if item.get("not_read") not in (None, *get_args(NotReadCode)):
        errors.append(f"{where}: not_read")
    if not _is_str_or_none(item.get("group")):
        errors.append(f"{where}: group")
    loads = item.get("loads")
    if loads is not None and not (
        loads.get("kind") in get_args(LoadsKind)
        and isinstance(loads.get("globs"), list)
    ):
        errors.append(f"{where}: loads")
    for ref in item.get("imports", []):
        if not (
            isinstance(ref.get("target"), str)
            and ref.get("state") in get_args(ImportState)
            and isinstance(ref.get("depth"), int)
            and _is_str_or_none(ref.get("target_item"))
            and _is_int_or_none(ref.get("line"))
        ):
            errors.append(f"{where}: import {ref.get('target')}")
    sources = cast("list[dict[str, Any]]", item.get("sources") or [])
    if not sources:
        if not unset:
            errors.append(f"{where}: needs at least one source")
        return errors
    for source in sources:
        if not (
            source.get("scope") in SETUP_SCOPES
            and isinstance(source.get("key"), str)
            and _is_str_or_none(source.get("file"))
            and _is_int_or_none(source.get("line"))
            and source.get("status") in statuses
        ):
            errors.append(f"{where}: source {source.get('key')}")
    return errors


def _real_path(display: str, lay: Any) -> Path:
    """Turn a display path into the file in a materialized world."""
    if display.startswith("~/"):
        return Path(lay.home) / display[2:]
    if display.startswith("managed/"):
        return Path(lay.managed) / display[len("managed/") :]
    return Path(os.path.normpath(Path(lay.project) / display))


def _all_text_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for current, _dirs, names in os.walk(root):
        found.extend(
            Path(current) / n for n in names if not (Path(current) / n).is_symlink()
        )
    return sorted(found)


def test_committed_files_equal_a_fresh_generation() -> None:
    assert bc.check() == []


def test_two_generations_give_the_same_bytes(tmp_path: Path) -> None:
    bc.generate(tmp_path / "a" / "corpus", tmp_path / "a" / "overlay")
    bc.generate(tmp_path / "b" / "corpus", tmp_path / "b" / "overlay")
    assert bc._read_tree(tmp_path / "a") == bc._read_tree(tmp_path / "b")


def test_the_corpus_has_every_planned_case() -> None:
    expected = {
        "empty", "simple", "typical", "complex", "stress",
        "broken-settings", "broken-agents", "agents-capped", "broken-plugins",
        "broken-skills", "broken-instructions", "broken-hooks", "broken-mcp",
        "broken-claude-json", "broken-claude-json-entry",
        "scope-symlink", "scope-unlisted", "scope-memory", "scope-ancestors",
    }  # fmt: skip
    assert set(CASE_NAMES) == expected


@pytest.mark.parametrize("case", CASE_NAMES)
def test_every_case_materializes(case: str, tmp_path: Path, setup_corpus: Path) -> None:
    world = bc.materialize(case, tmp_path / "world", corpus=setup_corpus)
    lay = bc.layout(world)
    for folder in (lay.config, lay.project, lay.managed):
        assert folder.is_dir()
    meta = json.loads((world / "case.json").read_text("utf-8"))
    listing = json.loads((lay.config / "routing-dashboard.json").read_text("utf-8"))
    if meta["listed"]:
        assert listing["projects"] == [{"name": "Proj", "path": str(lay.project)}]
    else:
        assert listing["projects"] == []
    assert (lay.project.parent / ".git").is_dir() is meta["git_root"]
    assert "shell_env" in json.loads(lay.session.read_text("utf-8"))
    for path in _all_text_files(world):
        assert b"@@" not in path.read_bytes(), f"placeholder left in {path}"


def test_materialize_keeps_symlinks_and_fills_absolute_paths(
    tmp_path: Path, setup_corpus: Path
) -> None:
    world = bc.materialize("scope-symlink", tmp_path / "w1", corpus=setup_corpus)
    link = world / "home" / ".claude" / "agents" / "linked.md"
    folder = world / "home" / ".claude" / "skills" / "ext"
    assert link.is_symlink()
    assert folder.is_symlink()
    assert link.resolve() == (world / "outside" / "linked-agent.md").resolve()
    assert folder.resolve() == (world / "outside" / "skills-dir").resolve()
    typical = bc.materialize("typical", tmp_path / "w2", corpus=setup_corpus)
    lay = bc.layout(typical)
    claude_json = json.loads(lay.claude_json.read_text("utf-8"))
    assert str(lay.project) in claude_json["projects"]
    installed = json.loads(
        (lay.config / "plugins" / "installed_plugins.json").read_text("utf-8")
    )
    for installs in installed["plugins"].values():
        for install in installs:
            assert Path(install["installPath"]).is_dir()
            assert str(lay.config / "plugins") in install["installPath"]


@pytest.mark.parametrize("case", CASE_NAMES)
def test_expected_json_matches_the_schema(case: str) -> None:
    assert _schema_errors(case, _expected(case)) == []


@pytest.mark.parametrize("case", CASE_NAMES)
def test_expected_lines_point_at_the_keys(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    world = bc.materialize(case, tmp_path / "w", corpus=setup_corpus)
    lay = bc.layout(world)
    data = _expected(case)
    checked = 0
    for part, body in data.get("parts", {}).items():
        for item in body["items"]:
            for source in item["sources"]:
                if source["line"] is None:
                    continue
                path = _real_path(source["file"], lay)
                assert path.is_file(), f"{part} {item['id']}: no file {source['file']}"
                lines = path.read_text("utf-8").splitlines()
                line = lines[int(source["line"]) - 1]
                needle = source.get("line_has") or source["key"].split(".")[-1]
                assert needle in line, (
                    f"{item['id']} line {source['line']} of {source['file']}"
                )
                checked += 1
    for row in data.get("problems", []):
        if row["line"] is None or row["file"] is None:
            continue
        path = _real_path(row["file"], lay)
        assert path.is_file(), f"problem {row['id']}: no file {row['file']}"
        assert 1 <= row["line"] <= len(path.read_text("utf-8").splitlines())
    if case not in {"empty", "broken-claude-json"}:
        assert checked > 0


def test_expected_problem_rows_sort_by_group_part_file_line() -> None:
    groups = ["couldnt_read", "wont_load", "not_as_set", "cant_tell", "notice"]
    for case in CASE_NAMES:
        rows = _expected(case)["problems"]
        keys = [
            (
                groups.index(r["group"]),
                SETUP_PARTS.index(r["part"]) if r["part"] else -1,
                r["file"] or "",
                r["line"] or 0,
            )
            for r in rows
        ]
        assert keys == sorted(keys), case


def test_generated_flag_marks_complex_and_stress_only() -> None:
    generated = {c for c in CASE_NAMES if _expected(c).get("generated") is True}
    assert generated == {"complex", "stress"}


def test_complex_matches_a_hand_checked_subset() -> None:
    """Literals checked by hand, so the generator is not its own oracle."""
    data = _expected("complex")
    ids = {
        part: [i["id"] for i in body["items"]] for part, body in data["parts"].items()
    }
    assert ids["agents"] == [
        "agents:builder",
        "agents:policy",
        "agents:reviewer",
        "agents:routing-dashboard:scout",
        "agents:scout",
    ]
    assert ids["hooks"] == [
        "hooks:SessionStart:*:0",
        "hooks:PreToolUse:Bash:0",
        "hooks:PreToolUse:Bash:1",
        "hooks:PreToolUse:Bash:2",
        "hooks:PostToolUse:Edit|Write:0",
    ]
    assert [i.split(":")[1] for i in ids["permissions"]] == [
        "deny", "deny", "ask", "allow", "allow", "defaultMode", "directory",
    ]  # fmt: skip
    assert ids["instructions"][0] == "instructions:managed/CLAUDE.md"
    assert ids["instructions"][-1] == "instructions:packages/web/CLAUDE.md"
    items = {i["id"]: i for part in data["parts"].values() for i in part["items"]}
    model = items["settings:model"]
    assert model["scope"] == "managed"
    assert model["effective"] == {"value": "claude-sonnet-5-5", "origin": "set"}
    assert [s["status"] for s in model["sources"]] == ["in_effect", "overridden"]
    user_scout = items["agents:scout"]
    plugin_scout = items["agents:routing-dashboard:scout"]
    assert (user_scout["scope"], plugin_scout["scope"]) == ("user", "plugin")
    assert plugin_scout["facts"]["ignored_fields"] == ["hooks", "permissionMode"]
    assert [s["file"] for s in items["skills:tidy"]["sources"]] == [
        "~/.claude/skills/tidy/SKILL.md",
        ".claude/commands/tidy.md",
    ]
    assert (
        items["settings:env.REPO_FLAG"]["sources"][0]["file"]
        == "../.claude/settings.local.json"
    )
    scopes = {
        s["scope"]
        for body in data["parts"].values()
        for i in body["items"]
        for s in i["sources"]
    }
    assert scopes == {"managed", "project_local", "project", "user", "plugin"}
    # Only the plugin agent's ignored fields (task 6), which are Not as set.
    assert {(p["code"], p["part"]) for p in data["problems"]} == {
        ("plugin_field_ignored", "agents")
    }


def test_stress_has_the_planned_sizes() -> None:
    parts = _expected("stress")["parts"]
    assert len(parts["agents"]["items"]) == 50
    assert len(parts["permissions"]["items"]) == 200
    assert len(parts["plugins"]["items"]) == 20
    names = [i["key"] for i in parts["instructions"]["items"]]
    assert len(names) == 8
    deepest = "level1/level2/level3/level4/level5/level6/CLAUDE.md"
    assert names[-1] == deepest
    assert all(len(i["key"]) >= 55 for i in parts["agents"]["items"])
    assert (CORPUS / "stress" / "work/parent/proj" / deepest).is_file()


def test_every_secret_is_in_a_corpus_file() -> None:
    doc = json.loads((CORPUS / "secrets.json").read_text("utf-8"))
    assert len(doc["secrets"]) >= 15
    for row in [*doc["secrets"], *doc["never"]]:
        base = OVERLAY if row["case"] == "demo-overlay" else CORPUS / row["case"]
        path = base / row["file"]
        assert path.is_file(), f"{row['kind']}: no file {row['file']}"
        assert row["value"] in path.read_text("utf-8"), (
            f"{row['kind']} not in {row['file']}"
        )


def test_secrets_cover_every_planted_shape() -> None:
    doc = json.loads((CORPUS / "secrets.json").read_text("utf-8"))
    kinds = {row["kind"] for row in doc["secrets"]}
    assert {
        "sk_prefix_in_hook_command", "sk_prefix_in_mcp_env", "bearer_header",
        "jwt_in_env", "url_userinfo", "secret_named_header",
        "secret_named_flag_equals_in_args", "github_token_after_secret_flag",
        "secret_named_flag_in_args",
    } <= kinds  # fmt: skip
    cases = {row["case"] for row in doc["secrets"]}
    assert {"typical", "complex"} <= cases


def test_no_expected_json_holds_a_secret() -> None:
    doc = json.loads((CORPUS / "secrets.json").read_text("utf-8"))
    values = [row["value"] for row in [*doc["secrets"], *doc["never"]]]
    for case in CASE_NAMES:
        text = (CORPUS / case / "expected.json").read_text("utf-8")
        for value in values:
            assert value not in text, f"{case}/expected.json holds {value}"


def test_no_corpus_file_names_a_real_home() -> None:
    # conftest points HOME at a temp folder, so the prefixes are the only real check.
    needles = [*HOME_NEEDLES]
    for root in (CORPUS, OVERLAY):
        for current, dirs, names in os.walk(root):
            for name in [*dirs, *names]:
                path = Path(current) / name
                rel = path.relative_to(root).as_posix()
                # The fake HOME folder is itself named home/, so a path is only checked
                # for the macOS prefix and for absolute links.
                assert "Users/" not in rel, f"real home in the path {rel}"
                if path.is_symlink():
                    assert not path.readlink().is_absolute(), f"absolute link {rel}"
                elif path.is_file():
                    text = path.read_bytes().decode("utf-8", errors="replace")
                    assert not any(n in text for n in needles), f"real home in {rel}"


def test_no_corpus_file_is_unreadable_or_oversized() -> None:
    for root in (CORPUS, OVERLAY):
        for path in _all_text_files(root):
            assert path.stat().st_mode & 0o400, f"{path} is not readable"
            assert path.stat().st_size < 1024 * 1024, f"{path} is over the cap"
            path.read_bytes().decode("utf-8")


def test_make_unreadable_not_utf8(tmp_path: Path, setup_corpus: Path) -> None:
    world = bc.materialize("simple", tmp_path / "w", corpus=setup_corpus)
    path = bc.make_unreadable(world, "not_utf8")
    assert path == world / "work/parent/proj/CLAUDE.md"
    with pytest.raises(UnicodeDecodeError):
        path.read_bytes().decode("utf-8")


def test_make_unreadable_too_large(tmp_path: Path, setup_corpus: Path) -> None:
    world = bc.materialize("simple", tmp_path / "w", corpus=setup_corpus)
    path = bc.make_unreadable(world, "too_large")
    assert path.stat().st_size == 1024 * 1024 + 1
    big = bc.make_unreadable(world, "claude_json_too_large")
    assert big.stat().st_size == 32 * 1024 * 1024 + 1


def test_make_unreadable_mode_000(tmp_path: Path, setup_corpus: Path) -> None:
    world = bc.materialize("simple", tmp_path / "w", corpus=setup_corpus)
    path = bc.make_unreadable(world, "mode000")
    try:
        assert path.stat().st_mode & 0o777 == 0
        if os.geteuid() == 0:
            pytest.skip("root reads a mode 000 file")
        with pytest.raises(PermissionError):
            path.read_bytes()
    finally:
        path.chmod(0o600)


def test_make_unreadable_refuses_an_unknown_kind(
    tmp_path: Path, setup_corpus: Path
) -> None:
    world = bc.materialize("simple", tmp_path / "w", corpus=setup_corpus)
    with pytest.raises(ValueError, match="unknown kind"):
        bc.make_unreadable(world, "bogus")


def test_materialize_refuses_an_unknown_case(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        bc.materialize("no-such-case", tmp_path / "w")


def test_demo_overlay_applies_over_the_demo_build(
    demo_build: Path, tmp_path: Path
) -> None:
    demo = tmp_path / "demo"
    shutil.copytree(demo_build, demo, ignore=shutil.ignore_patterns("*.jsonl"))
    before = json.loads((demo / "config" / "settings.json").read_text("utf-8"))
    overlay = bc._read_tree(OVERLAY)
    for rel in overlay:
        if not rel.endswith(".merge.json") and rel != "extra-projects.json":
            assert not (demo / rel).exists(), f"overlay would overwrite {rel}"
    bc.apply_demo_overlay(demo)
    after = json.loads((demo / "config" / "settings.json").read_text("utf-8"))
    for key, value in before.items():
        assert after[key] == value
    assert {"hooks", "permissions", "enabledPlugins"} <= set(after)
    assert (demo / "config" / ".claude.json").is_file()
    assert (demo / "config" / "CLAUDE.md").is_file()
    assert (demo / "config" / "skills" / "standup-notes" / "SKILL.md").is_file()
    assert (demo / "projects" / "tidewater-reporting" / ".mcp.json").is_file()
    installed = json.loads(
        (demo / "config" / "plugins" / "installed_plugins.json").read_text("utf-8")
    )
    assert len(installed["plugins"]) == 2
    listing = json.loads(
        (demo / "config" / "routing-dashboard.json").read_text("utf-8")
    )
    names = [p["name"] for p in listing["projects"]]
    assert names[-3:] == ["Setup empty", "Setup broken", "Setup large"]
    for entry in listing["projects"][-3:]:
        assert Path(entry["path"]).is_dir()
        assert Path(entry["path"]).is_absolute()
    claude_json = json.loads((demo / "config" / ".claude.json").read_text("utf-8"))
    assert (
        str(demo.resolve() / "projects" / "tidewater-reporting")
        in claude_json["projects"]
    )
    snapshot = {p: p.read_bytes() for p in _all_text_files(demo)}
    bc.apply_demo_overlay(demo)
    assert {p: p.read_bytes() for p in _all_text_files(demo)} == snapshot
    assert (
        len(list((demo / "projects" / "setup-large" / ".claude" / "agents").iterdir()))
        == 40
    )
    large = json.loads(
        (demo / "projects" / "setup-large" / ".claude" / "settings.json").read_text(
            "utf-8"
        )
    )
    assert len(large["permissions"]["allow"]) == 120
    assert list((demo / "projects" / "setup-empty").iterdir()) == [
        demo / "projects" / "setup-empty" / "notes.txt"
    ]


def test_apply_demo_overlay_refuses_a_folder_that_is_not_a_demo(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        bc.apply_demo_overlay(tmp_path)
