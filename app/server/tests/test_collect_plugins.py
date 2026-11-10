"""Tests for the plugins collector (m4-build.md task 6).

The corpus cases are held to their expected.json. Crafted folders cover the file shapes
the docs do not give, the manifest's component fields, the moved cache folder, the
``enabledPlugins`` handoff, and the Couldn't read state.
"""

import builtins
import json
import os
import stat
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import agent_collect_helpers as h
from agent_collect_helpers import Mini, lines

import collect_plugins
import collect_settings
from collect_plugins import EnabledEntry
from models import SetupItem
from setup_contract import FILE_CAP_BYTES, Collected

NOT_ROOT = os.geteuid() != 0
PLUGIN_CASES = sorted(
    p.name
    for p in h.CORPUS.iterdir()
    if p.is_dir() and "plugins" in h.expected(p.name)["parts"]
)
MARKET = "mk"


@pytest.fixture
def mini(tmp_path: Path) -> Mini:
    return Mini(tmp_path)


def collector_read(mini: Mini, handoff: dict[str, object] | None = None) -> Collected:
    return collect_plugins.COLLECTOR.read(mini.ctx, handoff or {})


def items(col: Collected) -> dict[str, SetupItem]:
    return {i.key: i for i in col.items["plugins"]}


def install(
    mini: Mini,
    name: str,
    version: str = "1.0.0",
    manifest: dict[str, Any] | str | None = None,
    files: dict[str, str] | None = None,
) -> Path:
    """Make an install folder under the cache and return it."""
    root = mini.config / "plugins" / "cache" / MARKET / name / version
    root.mkdir(parents=True, exist_ok=True)
    if manifest is None:
        manifest = {"name": name, "version": version}
    body = manifest if isinstance(manifest, str) else json.dumps(manifest)
    mini.write(root / ".claude-plugin" / "plugin.json", body)
    for rel, text in (files or {}).items():
        mini.write(root / rel, text)
    return root


def installed(mini: Mini, plugins: dict[str, Any] | str | None) -> None:
    """Write ``installed_plugins.json``. A string is written as is."""
    if plugins is None:
        return
    body = (
        plugins
        if isinstance(plugins, str)
        else json.dumps({"version": 2, "plugins": plugins})
    )
    mini.write(mini.config / "plugins" / "installed_plugins.json", body)


def entry(root: Path, **extra: Any) -> dict[str, Any]:
    return {"scope": "user", "installPath": str(root), **extra}


def enable(mini: Mini, mapping: dict[str, Any]) -> None:
    mini.write(
        mini.config / "settings.json", json.dumps({"enabledPlugins": mapping}, indent=2)
    )


def simple(mini: Mini, name: str = "p", **kwargs: Any) -> Path:
    """One installed and enabled plugin."""
    root = install(mini, name, **kwargs)
    installed(mini, {f"{name}@{MARKET}": [entry(root)]})
    enable(mini, {f"{name}@{MARKET}": True})
    return root


# ---------------------------------------------------------------- the corpus


@pytest.mark.parametrize("case", PLUGIN_CASES)
def test_the_corpus_cases_meet_their_expected_json(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world(case, tmp_path / "w", setup_corpus)
    result = h.run(w.ctx)
    want = h.expected(case)
    assert h.compare("plugins", result.plugins, want, result.problems()) == []


def test_the_stress_case_lists_twenty_plugins(
    tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world("stress", tmp_path / "w", setup_corpus)
    got = collect_plugins.COLLECTOR.read(w.ctx, {})
    assert len(got.items["plugins"]) == 20
    assert [i.order for i in got.items["plugins"]] == list(range(20))


def test_typical_facts_and_handoff(tmp_path: Path, setup_corpus: Path) -> None:
    w = h.world("typical", tmp_path / "w", setup_corpus)
    got = collect_plugins.COLLECTOR.read(w.ctx, {})
    by_key = items(got)
    rd = by_key["routing-dashboard@bartab-demo"]
    assert rd.facts.plugin is not None
    assert rd.facts.plugin.version == "0.1.7"
    assert rd.facts.plugin.marketplace == "bartab-demo"
    assert [(s.scope, s.enabled) for s in rd.facts.plugin.enabled] == [("user", True)]
    assert rd.read_only_reason is not None
    assert rd.read_only_reason.code == "plugin"
    assert rd.read_only_reason.params == {"plugin": "routing-dashboard"}
    assert (rd.writable, rd.applies, rd.feature) == (False, "reload_plugins", "core")
    comps = {c.plugin_id: c for c in h.components(got)}
    assert set(comps) == {"routing-dashboard@bartab-demo", "hivemind@bartab-demo"}
    rd_comp = comps["routing-dashboard@bartab-demo"]
    assert [Path(p).name for p in rd_comp.skills] == ["skills"]
    assert [Path(p).name for p in rd_comp.mcp_files] == [".mcp.json"]
    assert rd_comp.hooks_files == []
    hm_comp = comps["hivemind@bartab-demo"]
    assert [Path(p).name for p in hm_comp.hooks_files] == ["hooks.json"]
    assert hm_comp.agents == []
    assert rd_comp.item_id == "plugins:routing-dashboard@bartab-demo"
    assert w.lay.config.name == ".claude"


def test_complex_lists_the_plugin_agent_in_contents(
    tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world("complex", tmp_path / "w", setup_corpus)
    by_key = items(collect_plugins.COLLECTOR.read(w.ctx, {}))
    rd = by_key["routing-dashboard@bartab-demo"].facts.plugin
    hm = by_key["hivemind@bartab-demo"].facts.plugin
    assert rd is not None
    assert hm is not None
    assert rd.contents == ["agents:routing-dashboard:scout"]
    assert hm.contents == []


def test_with_contents_adds_ids_once(tmp_path: Path, setup_corpus: Path) -> None:
    w = h.world("complex", tmp_path / "w", setup_corpus)
    item = items(collect_plugins.COLLECTOR.read(w.ctx, {}))[
        "routing-dashboard@bartab-demo"
    ]
    more = collect_plugins.with_contents(
        item, ["skills:routing-dashboard:dashboard", "agents:routing-dashboard:scout"]
    )
    assert more.facts.plugin is not None
    assert more.facts.plugin.contents == [
        "agents:routing-dashboard:scout",
        "skills:routing-dashboard:dashboard",
    ]
    assert item.facts.plugin is not None
    assert item.facts.plugin.contents == ["agents:routing-dashboard:scout"]
    plain = item.model_copy(
        update={"facts": item.facts.model_copy(update={"plugin": None})}
    )
    assert collect_plugins.with_contents(plain, ["x"]) is plain


# ---------------------------------------------------------------- file shapes


@pytest.mark.parametrize(
    "body",
    [
        "[]",
        "not json at all",
        '{"plugins": {}}',
        '{"version": "2", "plugins": {}}',
        '{"version": 2, "plugins": []}',
        '{"version": 2, "plugins": {"a@m": [{"scope": "user"}]}}',
        '{"version": 2, "plugins": {"a@m": ["a string"]}}',
    ],
)
def test_an_unknown_installed_plugins_shape_is_cant_tell(mini: Mini, body: str) -> None:
    installed(mini, body)
    enable(mini, {"a@m": True})
    got = collector_read(mini)
    assert [(p.code, p.group, p.item_id) for p in got.problems] == [
        ("plugin_format_unknown", "cant_tell", None)
    ]
    item = items(got)["a@m"]
    assert (item.status, item.reason.code if item.reason else None) == (
        "unknown",
        "plugin_format_unknown",
    )
    assert h.components(got) == []


def test_a_single_install_object_is_accepted(mini: Mini) -> None:
    root = install(mini, "p")
    installed(mini, {f"p@{MARKET}": entry(root)})
    enable(mini, {f"p@{MARKET}": True})
    assert items(collector_read(mini))[f"p@{MARKET}"].status == "in_effect"


def test_known_marketplaces_shapes(mini: Mini) -> None:
    path = mini.config / "plugins" / "known_marketplaces.json"
    mini.write(path, json.dumps({"mk": {"source": {"repo": "x"}}}))
    assert collector_read(mini).problems == []
    for body in ("[1]", '{"mk": []}', "{bad json"):
        mini.write(path, body)
        got = collector_read(mini)
        assert [p.code for p in got.problems] == ["plugin_format_unknown"]
        assert got.problems[0].file == "~/.claude/plugins/known_marketplaces.json"


def test_no_plugin_files_gives_no_items(mini: Mini) -> None:
    got = collector_read(mini)
    assert got.items["plugins"] == []
    assert got.problems == []
    assert got.unreadable == []


def test_an_install_for_another_project_is_not_used(mini: Mini) -> None:
    root = install(mini, "p")
    other = mini.root / "elsewhere"
    installed(
        mini,
        {
            f"p@{MARKET}": [
                entry(root, scope="local", projectPath=str(other)),
            ],
            f"q@{MARKET}": [
                entry(root, scope="project", projectPath=str(mini.project))
            ],
        },
    )
    enable(mini, {f"p@{MARKET}": True, f"q@{MARKET}": True})
    got = items(collector_read(mini))
    assert got[f"p@{MARKET}"].status == "invalid"  # no install applies here
    assert got[f"q@{MARKET}"].status == "in_effect"


def test_the_narrowest_install_scope_wins(mini: Mini) -> None:
    old = install(mini, "p", "1.0.0")
    new = install(mini, "p", "2.0.0")
    installed(
        mini,
        {
            f"p@{MARKET}": [
                entry(old, version="1.0.0"),
                entry(new, scope="project", version="2.0.0"),
            ]
        },
    )
    enable(mini, {f"p@{MARKET}": True})
    facts = items(collector_read(mini))[f"p@{MARKET}"].facts.plugin
    assert facts is not None
    assert facts.version == "2.0.0"


def test_a_relative_install_path_is_under_the_plugins_folder(mini: Mini) -> None:
    install(mini, "p")
    installed(
        mini,
        {f"p@{MARKET}": [{"scope": "user", "installPath": f"cache/{MARKET}/p/1.0.0"}]},
    )
    enable(mini, {f"p@{MARKET}": True})
    item = items(collector_read(mini))[f"p@{MARKET}"]
    assert item.status == "in_effect"
    assert item.facts.plugin is not None
    assert item.facts.plugin.version == "1.0.0"  # from the manifest


# ---------------------------------------------------------------- enabledPlugins


def test_enabled_plugins_are_read_from_settings_when_no_handoff(mini: Mini) -> None:
    root = install(mini, "p")
    installed(mini, {f"p@{MARKET}": [entry(root)]})
    mini.write(
        mini.config / "settings.json",
        json.dumps({"enabledPlugins": {f"p@{MARKET}": False}}, indent=2),
    )
    mini.write(
        mini.project / ".claude" / "settings.json",
        json.dumps({"enabledPlugins": {f"p@{MARKET}": True}}, indent=2),
    )
    item = items(collector_read(mini))[f"p@{MARKET}"]
    assert [(s.scope, s.line, s.status) for s in item.sources] == [
        ("project", 3, "in_effect"),
        ("user", 3, "overridden"),
    ]
    assert item.scope == "project"


def test_managed_and_local_settings_rank_above_project_and_user(mini: Mini) -> None:
    root = install(mini, "p")
    installed(mini, {f"p@{MARKET}": [entry(root)]})
    key = f"p@{MARKET}"
    body = json.dumps({"enabledPlugins": {key: True}})
    for path in (
        mini.config / "settings.json",
        mini.project / ".claude" / "settings.json",
        mini.project / ".claude" / "settings.local.json",
        mini.managed / "managed-settings.json",
        mini.managed / "managed-settings.d" / "10-a.json",
        mini.managed / "managed-settings.d" / "20-b.json",
        mini.managed / "managed-settings.d" / ".hidden.json",
        mini.managed / "managed-settings.d" / "notes.txt",
    ):
        mini.write(path, body)
    item = items(collector_read(mini))[key]
    # One source for each scope. Inside managed the last file of the folder wins.
    assert [s.scope for s in item.sources] == [
        "managed",
        "project_local",
        "project",
        "user",
    ]
    assert item.sources[0].file == "managed/managed-settings.d/20-b.json"


def test_a_settings_file_that_is_not_json_is_skipped(mini: Mini) -> None:
    mini.write(mini.config / "settings.json", "{broken")
    mini.write(mini.project / ".claude" / "settings.json", "[1]")
    mini.write(
        mini.project / ".claude" / "settings.local.json", '{"enabledPlugins": 1}'
    )
    mini.write(
        mini.managed / "managed-settings.json", '{"enabledPlugins": {"a@m": "yes"}}'
    )
    assert collector_read(mini).items["plugins"] == []


def test_the_handoff_wins_over_reading_settings(mini: Mini) -> None:
    root = install(mini, "p")
    installed(mini, {f"p@{MARKET}": [entry(root)]})
    enable(mini, {f"p@{MARKET}": True})  # the files say true, the handoff says false
    handed = [
        EnabledEntry(f"p@{MARKET}", "project", False, ".claude/settings.json", None, 7)
    ]
    got = collector_read(mini, {"enabledPlugins": handed})
    item = items(got)[f"p@{MARKET}"]
    assert item.effective is not None
    assert item.effective.value is not None
    assert item.effective.value.text == "disabled"
    assert item.effective.origin == "set"
    assert item.status == "in_effect"
    assert h.components(got) == []  # a disabled plugin loads nothing
    assert [(s.scope, s.line) for s in item.sources] == [("project", 7)]


def test_the_handoff_accepts_mappings(mini: Mini) -> None:
    root = install(mini, "p")
    installed(mini, {f"p@{MARKET}": [entry(root)]})
    rows: list[object] = [
        {"plugin_id": f"p@{MARKET}", "scope": "managed", "enabled": True, "line": 3},
        {"plugin_id": f"p@{MARKET}", "scope": "weird", "enabled": False},
        {"plugin_id": 5, "enabled": True},
        "junk",
    ]
    item = items(collector_read(mini, {"enabledPlugins": rows}))[f"p@{MARKET}"]
    assert [(s.scope, s.line) for s in item.sources] == [("managed", 3), ("user", None)]


class FakeFile:
    """What the handed layers expose: a path and the line of every key."""

    def __init__(self, full_path: object, lines: object) -> None:
        self.full_path = full_path
        self.lines = lines


class FakeLayers:
    def __init__(self, *files: FakeFile) -> None:
        self.files = files

    def readable(self) -> list[FakeFile]:
        return list(self.files)


def settings_handoff(layers: object | None, *rows: object) -> dict[str, object]:
    shared: dict[str, object] = {"enabledPlugins": list(rows)}
    if layers is not None:
        shared["layers"] = layers
    return {"settings": shared}


def test_the_settings_collectors_handoff_gives_each_plugin_its_line(mini: Mini) -> None:
    root = install(mini, "p")
    installed(mini, {f"p@{MARKET}": [entry(root)]})
    path = str(mini.config / "settings.json")
    layers = FakeLayers(
        FakeFile(path, {("enabledPlugins",): 5, ("enabledPlugins", f"p@{MARKET}"): 6}),
        FakeFile("not-a-path", {}),
    )
    handoff = settings_handoff(
        layers,
        {
            "scope": "user",
            "file": "~/.claude/settings.json",
            "full_path": path,
            "line": 5,
            "value": {f"p@{MARKET}": True, "x@m": "yes"},
        },
        {
            "scope": "user",
            "value": {f"p@{MARKET}": False},
        },  # same scope: the first wins
        {"scope": "project", "value": "not a map"},
        "junk",
    )
    item = items(collector_read(mini, handoff))[f"p@{MARKET}"]
    assert [(s.scope, s.line, s.file) for s in item.sources] == [
        ("user", 6, "~/.claude/settings.json")
    ]
    assert item.status == "in_effect"


def test_the_settings_handoff_falls_back_to_the_line_of_the_key(mini: Mini) -> None:
    root = install(mini, "p")
    installed(mini, {f"p@{MARKET}": [entry(root)]})
    for layers in (None, object(), FakeLayers(FakeFile(1, {}), FakeFile("/x", None))):
        handoff = settings_handoff(
            layers,
            {
                "scope": "user",
                "full_path": "/x",
                "line": 5,
                "value": {f"p@{MARKET}": True},
            },
        )
        item = items(collector_read(mini, handoff))[f"p@{MARKET}"]
        assert [s.line for s in item.sources] == [5]


def test_a_settings_handoff_with_no_list_falls_through_to_the_other_inputs(
    mini: Mini,
) -> None:
    simple(mini)
    for settings in ("nope", {"enabledPlugins": "nope"}, {}):
        got = collector_read(mini, {"settings": settings})
        assert items(got)[f"p@{MARKET}"].sources[0].line == 3


def test_an_empty_settings_handoff_means_nothing_is_enabled(mini: Mini) -> None:
    simple(mini)  # the files say enabled, but the settings collector found no entry
    got = collector_read(mini, settings_handoff(None))
    assert items(got)[f"p@{MARKET}"].status == "default"


@pytest.mark.parametrize("case", PLUGIN_CASES)
def test_the_settings_collector_hands_over_what_the_plugins_collector_needs(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world(case, tmp_path / "w", setup_corpus)
    settings = collect_settings.COLLECTOR.read(w.ctx, {})
    plugins = collect_plugins.COLLECTOR.read(w.ctx, settings.handoff)
    alone = collect_plugins.COLLECTOR.read(w.ctx, {})
    assert [i.model_dump(mode="json") for i in plugins.items["plugins"]] == [
        i.model_dump(mode="json") for i in alone.items["plugins"]
    ]
    want = h.expected(case)
    assert h.compare("plugins", plugins, want, plugins.problems) == []


def test_a_handoff_that_is_not_a_list_falls_back_to_the_files(mini: Mini) -> None:
    simple(mini)
    got = collector_read(mini, {"enabledPlugins": "nope"})
    assert items(got)[f"p@{MARKET}"].sources[0].line == 3


def test_installed_but_not_enabled_is_the_default(mini: Mini) -> None:
    root = install(mini, "p")
    installed(mini, {f"p@{MARKET}": [entry(root)]})
    got = collector_read(mini)
    item = items(got)[f"p@{MARKET}"]
    assert item.status == "default"
    assert item.sources == []
    assert item.winner is None
    assert item.effective is not None
    assert item.effective.value is not None
    assert item.effective.value.text == "disabled"
    assert item.effective.origin == "default"
    assert got.problems == []
    assert h.components(got) == []


def test_disabled_and_not_installed_is_no_problem(mini: Mini) -> None:
    installed(mini, {})
    enable(mini, {"ghost@mk": False})
    got = collector_read(mini)
    assert got.problems == []
    assert items(got)["ghost@mk"].status == "in_effect"


def test_a_missing_install_folder_is_not_installed(mini: Mini) -> None:
    gone = mini.config / "plugins" / "cache" / MARKET / "gone" / "1.0.0"
    installed(mini, {f"gone@{MARKET}": [entry(gone)]})
    enable(mini, {f"gone@{MARKET}": True})
    got = collector_read(mini)
    assert [p.code for p in got.problems] == ["plugin_not_installed"]
    assert items(got)[f"gone@{MARKET}"].status == "invalid"


def test_a_missing_install_folder_of_a_disabled_plugin_is_unknown(mini: Mini) -> None:
    gone = mini.config / "plugins" / "cache" / MARKET / "gone" / "1.0.0"
    installed(mini, {f"gone@{MARKET}": [entry(gone)]})
    enable(mini, {f"gone@{MARKET}": False})
    got = collector_read(mini)
    assert got.problems == []
    assert items(got)[f"gone@{MARKET}"].status == "unknown"


# ---------------------------------------------------------------- the manifest


def test_a_missing_manifest_still_loads_the_defaults(mini: Mini) -> None:
    root = install(
        mini,
        "p",
        files={"agents/a.md": lines("---", "name: a", "description: d", "---")},
    )
    (root / ".claude-plugin" / "plugin.json").unlink()
    installed(mini, {f"p@{MARKET}": [entry(root)]})
    enable(mini, {f"p@{MARKET}": True})
    got = collector_read(mini)
    item = items(got)[f"p@{MARKET}"]
    assert item.status == "in_effect"
    assert item.facts.plugin is not None
    assert item.facts.plugin.contents == ["agents:p:a"]


@pytest.mark.parametrize(
    "manifest",
    ['{"name": "p" "x": 1}', "[]", '{"version": "1"}', '{"name": ""}', '{"name": 7}'],
)
def test_a_bad_manifest_is_invalid(mini: Mini, manifest: str) -> None:
    root = install(mini, "p", manifest=manifest)
    installed(mini, {f"p@{MARKET}": [entry(root)]})
    enable(mini, {f"p@{MARKET}": True})
    got = collector_read(mini)
    assert [p.code for p in got.problems] == ["plugin_manifest_invalid"]
    assert got.problems[0].line == 1
    assert items(got)[f"p@{MARKET}"].status == "invalid"
    assert h.components(got) == []


def test_the_manifest_name_is_the_plugin_name(mini: Mini) -> None:
    root = install(
        mini,
        "dir-name",
        manifest={"name": "real-name"},
        files={"agents/a.md": lines("---", "name: a", "description: d", "---")},
    )
    installed(mini, {f"dir-name@{MARKET}": [entry(root)]})
    enable(mini, {f"dir-name@{MARKET}": True})
    item = items(collector_read(mini))[f"dir-name@{MARKET}"]
    assert item.facts.plugin is not None
    assert item.facts.plugin.contents == ["agents:real-name:a"]
    assert item.read_only_reason is not None
    assert item.read_only_reason.params == {"plugin": "real-name"}


def test_skills_add_to_the_default_folder_and_the_others_replace(mini: Mini) -> None:
    agent = lines("---", "name: {n}", "description: d", "---")
    root = simple(
        mini,
        manifest={
            "name": "p",
            "skills": ["./extra-skills"],
            "agents": "./custom-agents/",
            "commands": ["./cmds"],
            "outputStyles": "./styles",
            "hooks": "./my-hooks.json",
            "mcpServers": "./my-mcp.json",
        },
        files={
            "skills/s/SKILL.md": "x",
            "extra-skills/e/SKILL.md": "x",
            "agents/default.md": agent.format(n="default"),
            "custom-agents/c.md": agent.format(n="c"),
            "commands/default.md": "x",
            "cmds/c.md": "x",
            "output-styles/default.md": "x",
            "styles/s.md": "x",
            "hooks/hooks.json": "{}",
            "my-hooks.json": "{}",
            ".mcp.json": "{}",
            "my-mcp.json": "{}",
        },
    )
    comp = h.components(collector_read(mini))[0]

    def rel(paths: list[str]) -> list[str]:
        return sorted(str(Path(p).relative_to(root)) for p in paths)

    assert rel(comp.skills) == ["extra-skills", "skills"]
    assert rel(comp.agents) == ["custom-agents"]
    assert rel(comp.commands) == ["cmds"]
    assert rel(comp.output_styles) == ["styles"]
    assert rel(comp.hooks_files) == ["my-hooks.json"]
    assert rel(comp.mcp_files) == ["my-mcp.json"]
    assert comp.hooks_inline is None
    assert comp.mcp_inline is None


def test_the_handoff_has_the_lists_the_later_collectors_read(mini: Mini) -> None:
    root = simple(
        mini,
        manifest={"name": "real", "skills": ["./extra"], "outputStyles": "./styles"},
        files={
            "skills/s/SKILL.md": "x",
            "extra/e/SKILL.md": "x",
            "commands/c.md": "x",
            "styles/a.md": "x",
            "hooks/hooks.json": "{}",
            ".mcp.json": "{}",
        },
    )
    got = collector_read(mini)
    shared = cast("dict[str, list[object]]", got.handoff["plugins"])
    assert sorted(shared) == ["commands", "hooks", "mcp", "skills"]

    def row(sub: str) -> dict[str, str]:
        return {
            "plugin": f"p@{MARKET}",
            "name": "real",
            "path": str(root / sub),
        }

    assert shared["skills"] == [row("skills"), row("extra")]
    assert shared["commands"] == [row("commands")]
    assert shared["hooks"] == [row("hooks/hooks.json")]
    assert shared["mcp"] == [row(".mcp.json")]
    assert got.handoff["plugin_output_styles"] == [row("styles")]


def test_the_handoff_lists_are_empty_when_nothing_is_enabled(mini: Mini) -> None:
    root = install(mini, "p")
    installed(mini, {f"p@{MARKET}": [entry(root)]})
    got = collector_read(mini)
    assert got.handoff["plugins"] == {
        "skills": [],
        "commands": [],
        "hooks": [],
        "mcp": [],
    }
    assert got.handoff["plugin_output_styles"] == []


def test_inline_manifest_objects_go_in_with_the_manifest_path(mini: Mini) -> None:
    root = simple(
        mini,
        manifest={
            "name": "p",
            "hooks": {"PreToolUse": []},
            "mcpServers": {"s": {"command": "x"}},
        },
    )
    shared = collector_read(mini).handoff["plugins"]
    assert isinstance(shared, dict)
    manifest = str(root / ".claude-plugin" / "plugin.json")
    assert shared["hooks"] == [
        {
            "plugin": f"p@{MARKET}",
            "name": "p",
            "path": manifest,
            "inline": {"PreToolUse": []},
        }
    ]
    assert shared["mcp"] == [
        {
            "plugin": f"p@{MARKET}",
            "name": "p",
            "path": manifest,
            "inline": {"s": {"command": "x"}},
        }
    ]


def test_every_unreadable_file_names_its_part(mini: Mini) -> None:
    mini.write(mini.config / "plugins" / "installed_plugins.json", "{}")
    mini.write(mini.config / "plugins" / "known_marketplaces.json", "{}")
    got = collect_plugins.COLLECTOR.read(
        replace(mini.ctx, shell_env={"CLAUDE_CODE_PLUGIN_CACHE_DIR": "/elsewhere"}), {}
    )
    assert got.unreadable == []  # nothing enabled, so nothing to refuse
    simple(mini)
    moved = collect_plugins.COLLECTOR.read(
        replace(mini.ctx, shell_env={"CLAUDE_CODE_PLUGIN_CACHE_DIR": "/elsewhere"}), {}
    )
    assert moved.unreadable
    assert {u.part for u in moved.unreadable} == {"plugins"}


def test_inline_hooks_and_mcp_servers_in_the_manifest(mini: Mini) -> None:
    simple(
        mini,
        manifest={
            "name": "p",
            "hooks": {"PreToolUse": []},
            "mcpServers": {"s": {"command": "x"}},
        },
        files={"hooks/hooks.json": "{}", ".mcp.json": "{}"},
    )
    comp = h.components(collector_read(mini))[0]
    assert comp.hooks_files == []
    assert comp.hooks_inline == {"PreToolUse": []}
    assert comp.mcp_files == []
    assert comp.mcp_inline == {"s": {"command": "x"}}


def test_a_manifest_path_that_leaves_the_install_is_dropped(mini: Mini) -> None:
    simple(
        mini,
        manifest={
            "name": "p",
            "agents": ["../../elsewhere", 5, "", "./ok"],
            "skills": 3,
        },
        files={"ok/a.md": lines("---", "name: a", "description: d", "---")},
    )
    comp = h.components(collector_read(mini))[0]
    assert [Path(p).name for p in comp.agents] == ["ok"]
    assert [Path(p).name for p in comp.skills] == []


def test_the_plugin_settings_keep_two_keys_masked(mini: Mini) -> None:
    simple(
        mini,
        files={
            "settings.json": json.dumps(
                {
                    "agent": "main-helper",
                    "subagentStatusLine": {"command": "sk-ant-FAKEPLUGINSETTING01"},
                    "permissions": {"allow": ["Bash"]},
                    "env": {"X": "1"},
                }
            )
        },
    )
    comp = h.components(collector_read(mini))[0]
    assert set(comp.settings) == {"agent", "subagentStatusLine"}
    assert comp.settings["agent"] == "main-helper"
    assert "FAKEPLUGINSETTING01" not in json.dumps(comp.settings)


def test_a_plugin_settings_file_that_is_not_an_object_is_ignored(mini: Mini) -> None:
    simple(mini, files={"settings.json": "[1]"})
    assert h.components(collector_read(mini))[0].settings == {}


def test_orphaned_versions_are_listed_not_read(mini: Mini) -> None:
    current = simple(mini, version="2.0.0")
    for old in ("1.0.0", "1.5.0"):
        folder = current.parent / old
        folder.mkdir()
        (folder / ".orphaned_at").write_text("1761000000000")
    (current.parent / "0.1.0").mkdir()  # an old folder with no marker is not orphaned
    (current.parent / "stray-file").write_text("x")
    item = items(collector_read(mini))[f"p@{MARKET}"]
    assert item.facts.plugin is not None
    assert item.facts.plugin.orphaned_versions == ["1.0.0", "1.5.0"]


# ------------------------------------------------------ outside the plugins folder


def test_an_install_outside_the_plugins_folder_is_not_read(
    mini: Mini, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = mini.root / "home" / "elsewhere" / "p"
    mini.write(outside / ".claude-plugin" / "plugin.json", '{"name": "p"}')
    installed(mini, {f"p@{MARKET}": [entry(outside)]})
    enable(mini, {f"p@{MARKET}": True})
    log: list[tuple[str, str]] = []
    h.spy_on_reads(monkeypatch, log)
    got = collector_read(mini)
    assert not any(str(outside) in path for _event, path in log)
    item = items(got)[f"p@{MARKET}"]
    assert (item.status, item.not_read) == ("unknown", "plugin_outside_plugins")
    assert [(u.reason, u.scope) for u in got.unreadable] == [
        ("plugin_outside_plugins", "user")
    ]
    assert [p.code for p in got.problems] == ["plugin_outside_plugins"]
    assert h.components(got) == []


def test_a_moved_cache_folder_makes_every_plugin_not_read(mini: Mini) -> None:
    root = simple(mini, "a")
    other = install(mini, "b")
    installed(mini, {f"a@{MARKET}": [entry(root)], f"b@{MARKET}": [entry(other)]})
    enable(mini, {f"a@{MARKET}": True, f"b@{MARKET}": True})
    mini.ctx = replace(
        mini.ctx, shell_env={"CLAUDE_CODE_PLUGIN_CACHE_DIR": str(mini.root / "moved")}
    )
    got = collector_read(mini)
    assert {i.key: i.not_read for i in got.items["plugins"]} == {
        f"a@{MARKET}": "plugin_outside_plugins",
        f"b@{MARKET}": "plugin_outside_plugins",
    }
    assert len(got.unreadable) == 1  # the one folder, once
    assert got.unreadable[0].reason == "plugin_outside_plugins"
    assert h.components(got) == []
    assert [p.code for p in got.problems] == ["plugin_outside_plugins"] * 2


@pytest.mark.parametrize("where", ["plugins/cache", "plugins/cache/deeper", "plugins"])
def test_a_cache_folder_inside_the_plugins_folder_changes_nothing(
    mini: Mini, where: str
) -> None:
    simple(mini)
    mini.ctx = replace(
        mini.ctx, shell_env={"CLAUDE_CODE_PLUGIN_CACHE_DIR": str(mini.config / where)}
    )
    assert items(collector_read(mini))[f"p@{MARKET}"].status == "in_effect"


# ---------------------------------------------------------------- Couldn't read


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_an_installed_plugins_file_with_no_permission_is_unreadable(mini: Mini) -> None:
    simple(mini)
    path = mini.config / "plugins" / "installed_plugins.json"
    path.chmod(0)
    try:
        got = collector_read(mini)
    finally:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert [(u.reason, u.file) for u in got.unreadable] == [
        ("permission", "~/.claude/plugins/installed_plugins.json")
    ]
    # What is enabled still shows, as not installed (nothing says otherwise).
    assert items(got)[f"p@{MARKET}"].status == "invalid"


def test_an_installed_plugins_file_that_is_not_utf8_is_unreadable(mini: Mini) -> None:
    mini.write(mini.config / "plugins" / "installed_plugins.json", b"\xff\xfe{}")
    got = collector_read(mini)
    assert [u.reason for u in got.unreadable] == ["not_utf8"]
    assert got.problems == []


def test_an_installed_plugins_file_over_the_cap_is_unreadable(mini: Mini) -> None:
    mini.write(
        mini.config / "plugins" / "installed_plugins.json", b" " * (FILE_CAP_BYTES + 1)
    )
    assert [u.reason for u in collector_read(mini).unreadable] == ["too_large"]


def test_a_manifest_that_is_not_utf8_is_unreadable_and_the_item_unknown(
    mini: Mini,
) -> None:
    root = install(mini, "p", manifest="x")
    (root / ".claude-plugin" / "plugin.json").write_bytes(b"\xff\xfe")
    installed(mini, {f"p@{MARKET}": [entry(root)]})
    enable(mini, {f"p@{MARKET}": True})
    got = collector_read(mini)
    assert [u.reason for u in got.unreadable] == ["not_utf8"]
    item = items(got)[f"p@{MARKET}"]
    assert (item.status, item.may_change) == ("unknown", True)
    assert got.problems == []


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_an_install_folder_that_will_not_list_is_unreadable(mini: Mini) -> None:
    root = simple(mini)
    root.chmod(0)
    try:
        got = collector_read(mini)
    finally:
        root.chmod(stat.S_IRWXU)
    assert [u.reason for u in got.unreadable] == ["folder_unlistable"]
    assert items(got)[f"p@{MARKET}"].may_change is True


def test_an_unreadable_plugin_settings_file_is_listed(mini: Mini) -> None:
    root = simple(mini, files={"settings.json": "{}"})
    (root / "settings.json").write_bytes(b"\xff")
    got = collector_read(mini)
    assert [u.reason for u in got.unreadable] == ["not_utf8"]
    assert items(got)[f"p@{MARKET}"].status == "in_effect"


# ------------------------------------------------------ order, signature, reads


def test_two_reads_give_the_same_items_in_the_same_order(
    tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world("stress", tmp_path / "w", setup_corpus)
    first = collect_plugins.COLLECTOR.read(w.ctx, {})
    second = collect_plugins.COLLECTOR.read(w.ctx, {})
    assert [i.model_dump(mode="json") for i in first.items["plugins"]] == [
        i.model_dump(mode="json") for i in second.items["plugins"]
    ]
    assert [i.id for i in first.items["plugins"]] == sorted(
        i.id for i in first.items["plugins"]
    )


def test_the_signature_is_stat_only_and_follows_the_files(
    mini: Mini, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = simple(mini)
    col = collector_read(mini)
    before = collect_plugins.COLLECTOR.signature(mini.ctx, col)

    def refuse(*_args: object, **_kwargs: object) -> object:
        pytest.fail("signature opened a file")

    monkeypatch.setattr(builtins, "open", refuse)
    monkeypatch.setattr(os, "open", refuse)
    again = collect_plugins.COLLECTOR.signature(mini.ctx, col)
    cold = collect_plugins.COLLECTOR.signature(mini.ctx, None)
    monkeypatch.undo()
    assert again == before
    assert cold != before
    manifest = root / ".claude-plugin" / "plugin.json"
    manifest.write_text(json.dumps({"name": "p", "version": "9"}) + "\n")
    assert collect_plugins.COLLECTOR.signature(mini.ctx, col) != before


def test_the_collector_names_its_part() -> None:
    assert collect_plugins.COLLECTOR.name == "plugins"
    assert list(collect_plugins.COLLECTOR.parts) == ["plugins"]
    assert collect_plugins.plugin_item_id("a@m") == "plugins:a@m"
