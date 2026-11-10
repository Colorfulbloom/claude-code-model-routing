"""An agent's setup item and the Model check say the same thing (m4-build.md task 20).

The item's ``status`` is the outcome of what runs: lowered when a cap lowers it,
overridden when a higher layer replaces its file's value, invalid, ignored or unknown
as the resolver says, in effect only when it runs as its file sets it. The Model check
(``model_check.judge_agent`` over no runs, through ``agent_setup``) reads the same
resolver entries, so the two must agree for every agent of the demo and of every corpus
case. The load status stays in the reason.
"""

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import agent_collect_helpers as h
import setup_api_helpers as sah
from agent_collect_helpers import Mini, lines

import agent_setup
import collect_agents
import fixture_provider
import git_root
import model_catalog
import model_check
from models import SetupItem
from setup_contract import SetupContext

CASES = sorted(p.name for p in h.CORPUS.iterdir() if p.is_dir())


def entries_of(ctx: SetupContext) -> list[dict[str, object]]:
    """The resolver entries the agents collector reads, with the same arguments."""
    local = (
        git_root.local_settings_path(ctx.project_dir, ctx.home)
        if ctx.project_dir is not None
        else None
    )
    return model_check.resolve_entries(
        claude_dir=ctx.config_dir,
        project_dir=ctx.project_dir,
        managed_dir=ctx.managed_dir,
        shell_env=ctx.shell_env,
        local_path=local,
        plan=ctx.plan,
    )


def agreement(ctx: SetupContext) -> list[tuple[str, str, str]]:
    """Check every agent item of ``ctx`` against the Model check.

    Returns the (item id, item status, check status) of each agent judged, so a caller
    can see that the demo and the corpus cover more than one outcome.
    """
    items = h.run(ctx).agents.items["agents"]
    entries = entries_of(ctx)
    setup = agent_setup.from_entries(entries)
    catalog = model_catalog.load_catalog()
    seen: list[tuple[str, str, str]] = []
    for item in items:
        if item.scope not in ("user", "project") or item.reason is None:
            # Managed and plugin agents are not judged, so the item keeps its load
            # status and the check says so too.
            assert item.check is None, item.id
            continue
        if item.winner is None:
            # A file that does not load keeps its load status and has nothing to check.
            assert item.status in ("invalid", "unknown"), item.id
            assert item.check is None, item.id
            continue
        name = item.name
        row = model_check.build_model_check_from_runs(
            entries=entries, runs_by_agent={name: []}, catalog=catalog
        ).rows[0]
        from_setup = agent_setup.check_agent(setup, name, [])
        assert from_setup.status == row.status, item.id
        if row.status is None:
            # The file sets neither a model nor an effort: the load status stands.
            assert item.status == "in_effect", item.id
            assert item.check is None, item.id
            seen.append((item.id, item.status, "none"))
            continue
        assert item.status == row.status == from_setup.status, item.id
        assert item.check is not None, item.id
        assert item.check.code == row.reason_code, item.id
        assert item.check.params == row.params, item.id
        seen.append((item.id, item.status, row.status))
    return seen


@pytest.mark.parametrize("case", CASES)
def test_every_corpus_case_agrees(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    w = h.world(case, tmp_path / "w", setup_corpus)
    agreement(w.ctx)


def test_every_demo_agent_agrees(
    tmp_path_factory: pytest.TempPathFactory, demo_build: Path
) -> None:
    demo = sah.overlaid_demo(tmp_path_factory, demo_build)
    world = fixture_provider.demo_world(demo)
    assert world.contexts
    seen: list[tuple[str, str, str]] = []
    for ctx in world.contexts.values():
        seen.extend(agreement(ctx))
    assert seen
    # The demo's tidewater-reporting agents are overridden, so not all are green.
    assert {status for _id, status, _check in seen} >= {"in_effect", "overridden"}


# ---------------------------------------------------------------- crafted outcomes


@pytest.fixture
def mini(tmp_path: Path) -> Mini:
    return Mini(tmp_path)


def user_agent(mini: Mini, name: str, *extra: str) -> None:
    mini.write(
        mini.config / "agents" / f"{name}.md",
        lines("---", f"name: {name}", "description: d", *extra, "---", "Body."),
    )


def item_of(mini: Mini, name: str) -> SetupItem:
    got = collect_agents.COLLECTOR.read(mini.ctx, {})
    return {i.id: i for i in got.items["agents"]}[f"agents:{name}"]


def test_a_cap_makes_the_item_lowered_and_the_load_reason_stays(mini: Mini) -> None:
    mini.write(mini.config / "settings.json", json.dumps({"maxEffortLevel": "medium"}))
    user_agent(mini, "capped", "model: claude-opus-5-5", "effort: high")
    item = item_of(mini, "capped")
    assert item.status == "lowered"
    assert item.reason is not None
    assert item.reason.code == "agent_loads"
    assert item.check is not None
    assert item.check.code == "lowered_by_cap"
    assert item.check.params["expected"] == "medium"
    assert item.check.params["value"] == "high"
    assert item.check.params["setting"] == "effort"
    assert [(s.key, s.status) for s in item.sources if s.key == "name"] == [
        ("name", "in_effect")
    ]
    assert agreement(mini.ctx) == [("agents:capped", "lowered", "lowered")]


def test_a_higher_layer_makes_the_item_overridden(mini: Mini) -> None:
    mini.ctx = replace(mini.ctx, shell_env={"CLAUDE_CODE_EFFORT_LEVEL": "low"})
    user_agent(mini, "a", "model: claude-opus-5-5", "effort: high")
    item = item_of(mini, "a")
    assert item.status == "overridden"
    assert item.check is not None
    assert item.check.code == "pin_overridden"
    assert item.check.params["expected"] == "low"
    assert item.check.params["value"] == "high"
    assert item.reason is not None
    assert item.reason.code == "agent_loads"
    assert item.effective is not None
    assert item.effective.value is not None
    assert item.effective.value.text.endswith("/ low")
    assert agreement(mini.ctx) == [("agents:a", "overridden", "overridden")]


def test_an_agent_that_runs_as_its_file_sets_it_is_in_effect(mini: Mini) -> None:
    user_agent(mini, "plain", "model: claude-sonnet-5-5")
    item = item_of(mini, "plain")
    assert item.status == "in_effect"
    assert item.check is not None
    assert item.check.code == "in_effect"
    assert agreement(mini.ctx) == [("agents:plain", "in_effect", "in_effect")]


def test_an_agent_that_sets_nothing_has_no_check(mini: Mini) -> None:
    user_agent(mini, "bare")
    item = item_of(mini, "bare")
    assert item.status == "in_effect"
    assert item.check is None
    assert agreement(mini.ctx) == [("agents:bare", "in_effect", "none")]


def test_a_file_that_does_not_load_keeps_its_load_status(mini: Mini) -> None:
    mini.write(
        mini.config / "agents" / "nodesc.md", lines("---", "name: nodesc", "---", "x")
    )
    item = item_of(mini, "nodesc")
    assert item.status == "invalid"
    assert item.check is None
    assert item.reason is not None
    assert item.reason.code == "agent_no_description"
    assert agreement(mini.ctx) == []
