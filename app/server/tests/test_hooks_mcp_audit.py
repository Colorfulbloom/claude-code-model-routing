"""The hooks, MCP and masked-reader collectors open only what the read scope allows.

``hooks_audit_child.py`` runs the collectors under an audit hook that logs every
``open``, ``os.listdir`` and ``os.scandir``, on the decoy tree of ``read_audit_helpers``
plus a managed folder with an MCP file, a project ``.mcp.json``, a plugin with hooks and
a home Claude settings file with decoy keys. Every logged path must pass
``Scope.allows`` (or sit under the app's own code and Python), and no decoy may appear.
A second run moves the config folder, and then the home settings file must not be
opened at all. There is no setup route yet, so this runs the collectors directly. Task 9
adds the routes to ``poll_the_pages``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import read_audit_helpers as audit

import read_scope
import setup_contract

CHILD = audit.HERE / "hooks_audit_child.py"
HOME_SENTINEL = "SENTINEL-HOME-FILE-DO-NOT-KEEP"


def _put(path: Path, text: str = audit.DECOY_TEXT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _server(command: str = "node") -> dict[str, object]:
    return {"command": command}


@pytest.fixture
def decoys(tmp_path: Path) -> audit.Decoys:
    world = audit.build_decoys(tmp_path)
    managed = world.root / "managed"
    _put(managed / "managed-mcp.json", json.dumps({"mcpServers": {"m": _server()}}))
    _put(
        managed / "managed-settings.json",
        json.dumps(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "m"}]}]}}
        ),
    )
    _put(
        world.project / ".mcp.json",
        json.dumps({"mcpServers": {"p": _server()}}),
    )
    _put(
        world.project / ".claude" / "settings.json",
        json.dumps(
            {
                "enableAllProjectMcpServers": True,
                "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "p"}]}]},
            }
        ),
    )
    _put(
        world.home / ".claude.json",
        json.dumps(
            {
                "oauthAccount": {"emailAddress": HOME_SENTINEL},
                "mcpServers": {"u": _server()},
                "projects": {
                    str(world.project): {"mcpServers": {"l": _server()}},
                    str(world.unlisted): {"mcpServers": {"x": _server(HOME_SENTINEL)}},
                },
            }
        ),
    )
    # Hooks and MCP of an enabled plugin inside the plugins folder.
    install = world.config / "plugins" / "cache" / "market" / "ok" / "1.0"
    _put(install / ".claude-plugin" / "plugin.json", '{"name": "ok"}')
    _put(
        install / "hooks" / "hooks.json",
        json.dumps(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "ok"}]}]}}
        ),
    )
    _put(install / ".mcp.json", json.dumps({"mcpServers": {"ok": _server()}}))
    _put(
        world.config / "settings.json",
        json.dumps({"enabledPlugins": {"ok@market": True}}),
    )
    _put(
        world.config / "plugins" / "installed_plugins.json",
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "ok@market": [
                        {"scope": "user", "installPath": str(install), "version": "1.0"}
                    ]
                },
            }
        ),
    )
    # A moved config folder, with its own copy of the settings file.
    _put(
        world.root / "moved" / ".claude.json",
        json.dumps({"mcpServers": {"moved": _server()}}),
    )
    # Decoys outside every root that a handoff could name.
    _put(world.outside / "hooks.json")
    _put(world.outside / ".mcp.json")
    return world


def _run(
    world: audit.Decoys, *, listed: bool = True, config: Path | None = None
) -> tuple[list[tuple[str, str]], dict[str, int]]:
    log = world.root / "reads.log"
    log.unlink(missing_ok=True)
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-B",
            str(CHILD),
            str(config or world.config),
            str(world.home),
            str(world.root / "managed"),
            str(world.project) if listed else "-",
            str(world.outside / "hooks.json"),
            str(world.outside / ".mcp.json"),
        ],
        cwd=audit.SERVER_DIR,
        env={**world.env(), audit.LOG_ENV: str(log)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return audit.read_log(log), json.loads(proc.stdout.splitlines()[-1])


def _scope(
    world: audit.Decoys, *, listed: bool = True, config: Path | None = None
) -> read_scope.Scope:
    return read_scope.Scope(
        setup_contract.SetupContext(
            project_key="proj",
            config_dir=config or world.config,
            home=world.home,
            project_dir=world.project if listed else None,
            managed_dir=world.root / "managed",
            real_mode=True,
        )
    )


def test_every_open_and_listing_passes_the_scope(decoys: audit.Decoys) -> None:
    entries, counts = _run(decoys)
    assert counts["hooks"] >= 3
    assert counts["mcp"] >= 4
    scope = _scope(decoys)
    audit.assert_reads_allowed(entries, decoys, scope=scope, followed=[decoys.followed])
    own = [
        (event, path)
        for event, path in entries
        if path.startswith(str(decoys.root) + os.sep) and path != str(decoys.followed)
    ]
    assert own, "the collectors read nothing inside the scope"
    for event, path in own:
        assert scope.allows(path, folder=event != "open"), (event, path)


def test_the_audit_sees_the_files_it_should(decoys: audit.Decoys) -> None:
    entries, _counts = _run(decoys)
    opened = {path for event, path in entries if event == "open"}
    install = decoys.config / "plugins" / "cache" / "market" / "ok" / "1.0"
    for wanted in (
        decoys.home / ".claude.json",
        decoys.project / ".mcp.json",
        decoys.root / "managed" / "managed-mcp.json",
        install / "hooks" / "hooks.json",
        install / ".mcp.json",
        decoys.config / "settings.json",
    ):
        assert str(wanted) in opened, wanted


def test_no_decoy_is_opened_or_listed(decoys: audit.Decoys) -> None:
    entries, counts = _run(decoys)
    for decoy in decoys.decoys:
        hit = [
            p
            for _e, p in entries
            if p == str(decoy) or p.startswith(str(decoy) + os.sep)
        ]
        assert hit == [], decoy
    paths = [p for _e, p in entries]
    assert not any(p.startswith(str(decoys.outside / "hooks.json")) for p in paths)
    assert not any(p.startswith(str(decoys.outside / ".mcp.json")) for p in paths)
    assert counts["decoy_unreadable"] == 2  # both named decoys: not read here


def test_an_unlisted_project_opens_nothing_under_it(decoys: audit.Decoys) -> None:
    entries, _counts = _run(decoys, listed=False)
    paths = [p for _e, p in entries]
    assert not any(p.startswith(str(decoys.project) + os.sep) for p in paths)
    assert not any(p.startswith(str(decoys.unlisted)) for p in paths)
    audit.assert_reads_allowed(
        entries, decoys, scope=_scope(decoys, listed=False), followed=[decoys.followed]
    )


def test_a_moved_config_folder_never_opens_the_home_file(decoys: audit.Decoys) -> None:
    moved = decoys.root / "moved"
    entries, counts = _run(decoys, config=moved)
    opened = {path for event, path in entries if event == "open"}
    assert str(decoys.home / ".claude.json") not in opened
    assert str(moved / ".claude.json") in opened
    assert counts["mcp"] >= 1
    audit.assert_reads_allowed(
        entries,
        decoys,
        scope=_scope(decoys, config=moved),
        followed=[decoys.followed],
    )


def test_the_audit_fails_when_a_read_leaves_the_scope(decoys: audit.Decoys) -> None:
    scope = _scope(decoys)
    stray = [("open", str(decoys.outer / "secrets.txt"))]
    with pytest.raises(pytest.fail.Exception):
        audit.assert_reads_allowed(stray, decoys, scope=scope)
