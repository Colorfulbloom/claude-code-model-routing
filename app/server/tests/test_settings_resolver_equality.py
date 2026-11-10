"""The 122 resolver folders give the same entries through the collector as through
``resolve.load_fixture`` (m4-build.md task 4).

``load_fixture`` reads a folder with ``collect`` straight off the disk. The setup read
side reads the same files through ``read_scope`` and hands ``collect`` the bytes
(``settings_layers.read_layers``). Both then run ``resolve.resolve`` with the same
flags, plan and labels, so every entry must be equal. The agent and rules-file records
come from the old reader in both runs: the Agents collector owns them, so only the
settings and environment side is under test here.

The folders sit inside the repo, which has a git root, so the test copies them to a temp
folder first. No git root above the copy means no repo-root local file can join in.
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_case_helpers as sc

import collect
import resolve
import settings_layers
from setup_contract import SetupContext

FIXTURES = sc.REPO_ROOT / "tests" / "fixtures" / "resolution"
NAMES = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())


@pytest.fixture(scope="module")
def copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("resolution") / "resolution"
    shutil.copytree(FIXTURES, out, symlinks=True)
    return out


def _public(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in e.items() if not k.startswith("_")} for e in entries]


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return data


def test_the_corpus_has_122_folders() -> None:
    assert len(NAMES) == 122


@pytest.mark.parametrize("name", NAMES)
def test_entries_equal_load_fixture(name: str, copy: Path) -> None:
    folder = copy / name
    inputs, _expected = resolve.load_fixture(str(folder))
    want = resolve.resolve(inputs, resolve.load_rules(), resolve.load_agent_fields())

    session = _json(folder / "session.json")
    ctx = SetupContext(
        project_key=name,
        config_dir=folder / "config",
        home=None,
        project_dir=folder / "project",
        managed_dir=folder / "managed",
        shell_env=dict(session.get("shell_env") or {}),
        plan=_json(folder / "dashboard.json").get("plan"),
    )
    layers = settings_layers.read_layers(ctx)
    old = inputs.collected
    for key in ("settings", "settings_files", "env"):
        assert layers.collected[key] == old[key], key
    collected = {
        **layers.collected,
        "agents": old["agents"],
        "rules_files": old["rules_files"],
    }
    got = settings_layers.resolver_entries(
        collected,
        ctx.plan,
        flags=inputs.flags,
        cli_settings=inputs.cli_settings,
        home=None,
        root=str(folder),
        shell_label=resolve.LABEL_SHELL,
    )
    assert _public(got) == _public(want)
    assert layers.unreadable == []


def test_the_replay_never_reads_the_disk(copy: Path) -> None:
    """``collect`` sees only what was read through the scope, so a file the scope
    never read is missing to it, even when it exists."""
    folder = copy / NAMES[0]
    stray = folder / "project" / ".claude" / "settings.json"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text('{"model": "claude-opus-5-5"}', encoding="utf-8")
    ctx = SetupContext(
        project_key="x",
        config_dir=folder / "config",
        home=None,
        project_dir=None,  # an unlisted project: its files are never read
        managed_dir=None,
    )
    layers = settings_layers.read_layers(ctx)
    assert all(f["layer"] == "user" for f in layers.collected["settings_files"])
    assert not any(str(stray) == f["path"] for f in layers.collected["settings_files"])
    # Direct ``collect`` on the same folders does read it.
    direct = collect.collect(
        str(folder / "config"),
        str(folder / "project"),
        None,
        {},
        resolve.load_rules(),
    )
    assert any(str(stray) == f["path"] for f in direct["settings_files"])


@pytest.mark.parametrize("name", NAMES)
def test_the_probe_agent_changes_no_main_entry(name: str, copy: Path) -> None:
    """The probe agent adds agent rows and touches nothing else in the answer."""
    folder = copy / name
    inputs, _expected = resolve.load_fixture(str(folder))
    session = _json(folder / "session.json")
    ctx = SetupContext(
        project_key=name,
        config_dir=folder / "config",
        home=None,
        project_dir=folder / "project",
        managed_dir=folder / "managed",
        shell_env=dict(session.get("shell_env") or {}),
        plan=_json(folder / "dashboard.json").get("plan"),
    )
    layers = settings_layers.read_layers(ctx)
    kwargs: dict[str, Any] = {
        "flags": inputs.flags,
        "cli_settings": inputs.cli_settings,
        "home": None,
        "root": str(folder),
        "shell_label": resolve.LABEL_SHELL,
    }
    plain = settings_layers.resolver_entries(layers.collected, ctx.plan, **kwargs)
    probed = settings_layers.resolver_entries(
        layers.collected, ctx.plan, probe_agent=True, **kwargs
    )
    probe = settings_layers.PROBE_AGENT
    assert [e for e in probed if e.get("agent") != probe] == plain
    assert {e["key"] for e in probed if e.get("agent") == probe} <= {
        "agentFile",
        "model",
        "effort",
        "autoCompactWindow",
        "subagentPromptCacheTtl",
    }
