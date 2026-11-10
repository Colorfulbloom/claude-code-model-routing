"""Model check parity: the repo-root local file and the plan (m4-build.md section 2).

``resolve_entries`` gains ``local_path`` and ``plan``, as ``dashboard/api_settings.py``
passes them to ``collect.collect`` and ``resolve.Inputs``. The local file is read
through ``read_scope``. ``store_provider`` and ``agent_setup.load_setup`` pass both on.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import read_audit_helpers as audit

import agent_setup
import git_root
import model_check
import projects
import store_provider
from usage import Row


@pytest.fixture
def world(tmp_path: Path) -> audit.Decoys:
    """The decoy tree: a project below a git root that has a local settings file."""
    return audit.build_decoys(tmp_path)


def _entries(
    world: audit.Decoys, *, local_path: Path | None = None, plan: str | None = None
) -> list[Row]:
    return model_check.resolve_entries(
        claude_dir=world.config,
        project_dir=world.project,
        managed_dir=None,
        shell_env={},
        local_path=local_path,
        plan=plan,
    )


def _keys(entries: list[Row]) -> set[tuple[object, object, object]]:
    return {(e.get("key"), e.get("status"), e.get("value")) for e in entries}


def _effort(entries: list[Row]) -> Row:
    return next(e for e in entries if e.get("key") == "effortLevel")


def test_without_local_path_the_root_file_is_not_read(world: audit.Decoys) -> None:
    entries = _entries(world)
    assert all(e.get("file") != "../.claude/settings.local.json" for e in entries)
    assert not any(e.get("layer") == "local" for e in entries)


def test_the_root_local_file_is_read_and_shown_relative_to_the_project(
    world: audit.Decoys,
) -> None:
    local = git_root.local_settings_path(world.project)
    assert local == world.outer / ".claude" / "settings.local.json"
    entry = _effort(_entries(world, local_path=local))
    assert entry["value"] == "high"
    assert entry["layer"] == "local"
    assert entry["file"] == "../.claude/settings.local.json"
    # The resolver prose in entry["reason"] still names absolute paths, as in M2.
    # model_check never forwards it, so only file and other_file are shown.
    assert str(world.outer) not in json.dumps(
        {k: entry[k] for k in ("file", "other_file") if k in entry}
    )


def test_the_local_file_is_read_through_the_scope(
    world: audit.Decoys, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = world.outer / ".claude" / "settings.local.json"
    opened: list[str] = []
    real_open = os.open

    def watching(file: str, *args: int, **kwargs: int) -> int:
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(os, "open", watching)
    _entries(world, local_path=local)
    assert str(local) in opened  # opened once, by read_scope; collect gets the bytes


def test_a_local_file_the_scope_refuses_is_dropped(world: audit.Decoys) -> None:
    refused = world.outer / ".claude" / "settings.json"  # not the local file
    refused.write_text('{"effortLevel": "low"}')
    entries = _entries(world, local_path=refused)
    assert all(e.get("file") != "../.claude/settings.json" for e in entries)
    assert not any(e.get("value") == "low" for e in entries)


def test_a_local_file_over_the_cap_is_dropped(world: audit.Decoys) -> None:
    local = world.outer / ".claude" / "settings.local.json"
    local.write_text('{"effortLevel": "low", "pad": "' + "x" * (1024 * 1024) + '"}')
    entries = _entries(world, local_path=local)
    assert not any(e.get("value") == "low" for e in entries)


def test_a_vanished_local_file_leaves_the_rest_alone(world: audit.Decoys) -> None:
    local = world.outer / ".claude" / "settings.local.json"
    plain = _entries(world)
    local.unlink()
    assert _entries(world, local_path=local) == plain


def test_a_local_path_with_no_project_is_ignored(world: audit.Decoys) -> None:
    local = world.outer / ".claude" / "settings.local.json"
    entries = model_check.resolve_entries(
        claude_dir=world.config,
        project_dir=None,
        managed_dir=None,
        shell_env={},
        local_path=local,
    )
    assert not any(e.get("layer") == "local" for e in entries)


def test_the_plan_reaches_the_resolver(world: audit.Decoys) -> None:
    unset = _entries(world)
    api = _entries(world, plan="api_key")
    sub = _entries(world, plan="subscription")
    assert api != unset
    assert sub == unset or sub != api
    # A rule that depends on the plan (the prompt cache lifetime) differs by plan.
    assert _keys(api) != _keys(sub)


def test_load_setup_passes_both_on(world: audit.Decoys) -> None:
    local = world.outer / ".claude" / "settings.local.json"
    setup = agent_setup.load_setup(
        world.config, world.project, None, {}, local_path=local, plan="api_key"
    )
    assert setup.failed is False
    entries = _entries(world, local_path=local, plan="api_key")
    assert list(setup.entries) == entries


def test_load_plan_reads_the_plan_and_warns_of_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "cfg"
    config.mkdir()
    ctx = projects.ProjectsContext(config_dir=str(config), project_dir=str(tmp_path))
    assert projects.load_plan(ctx) is None
    (config / "routing-dashboard.json").write_text('{"plan": "api_key"}')
    assert projects.load_plan(ctx) == "api_key"
    (config / "routing-dashboard.json").write_text('{"plan": "nonsense"}')
    assert projects.load_plan(ctx) is None
    (config / "routing-dashboard.json").write_text("{ not json")
    assert projects.load_plan(ctx) is None
    (config / "routing-dashboard.json").write_text("[1]")
    assert projects.load_plan(ctx) is None
    assert capsys.readouterr().err == ""


def test_the_store_provider_looks_for_a_git_root_in_real_mode_only(
    world: audit.Decoys, tmp_path: Path
) -> None:
    local = world.outer / ".claude" / "settings.local.json"
    real = _provider(world, tmp_path, mode="real")
    assert real._local_path(world.project) == local  # pyright: ignore[reportPrivateUsage]
    assert real._local_path(None) is None  # pyright: ignore[reportPrivateUsage]
    demo = _provider(world, tmp_path, mode="demo")
    assert demo._local_path(world.project) is None  # pyright: ignore[reportPrivateUsage]


def _provider(
    world: audit.Decoys, tmp_path: Path, *, mode: str
) -> store_provider.StoreProvider:
    return store_provider.create(
        claude_dir=world.config,
        store_dir=tmp_path / f"store-{mode}",
        demo=mode == "demo",
        mode="real" if mode == "real" else "demo",
        project_dir=world.project,
        home=str(world.home),
        pace_ms=0,
        price_fetch=False,
    )
