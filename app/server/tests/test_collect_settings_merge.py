"""What a key runs with when several files or the shell set it (m4-build.md task 4).

The differential against the old answer (test_differential_settings.py) found three
new-side answers that were wrong. Each has a test here with its own files, plus the
settings docs rules the plain keys follow (a list key combines across files,
``modelSettings`` resolves one model at a time).
"""

import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_case_helpers as sc

import collect_settings
from models import ProblemRow, SetupItem
from setup_contract import Collected

USER = "home/.claude/settings.json"
PROJECT = "proj/.claude/settings.json"


def read(
    tmp: Path, files: dict[str, str], env: dict[str, str] | None = None
) -> Collected:
    ctx = sc.scratch(tmp, files)
    if env is not None:
        ctx = dataclasses.replace(ctx, shell_env=env)
    return collect_settings.COLLECTOR.read(ctx, {})


def item(got: Collected, key: str) -> SetupItem:
    return next(i for i in got.items["settings"] if i.id == f"settings:{key}")  # pyright: ignore[reportAttributeAccessIssue]


def rows(got: Collected, key: str) -> list[ProblemRow]:
    return [p for p in got.problems if p.item_id == f"settings:{key}"]


def text(it: SetupItem) -> str | None:
    return it.effective.value.text if it.effective and it.effective.value else None


# ------------------------------------------- a row for every source, not the winner's


def test_a_wrong_type_list_that_another_file_beats_still_gets_a_row(
    tmp_path: Path,
) -> None:
    got = read(
        tmp_path,
        {
            USER: '{\n  "availableModels": "sonnet"\n}\n',
            PROJECT: '{\n  "availableModels": ["opus"]\n}\n',
        },
    )
    made = rows(got, "availableModels")
    assert [(p.group, p.file, p.line) for p in made] == [
        ("cant_tell", "~/.claude/settings.json", 2)
    ]
    assert [(s.scope, s.status) for s in item(got, "availableModels").sources] == [
        ("project", "in_effect"),
        ("user", "unknown"),
    ]


def test_an_overridden_source_makes_no_row(tmp_path: Path) -> None:
    got = read(
        tmp_path,
        {
            USER: '{\n  "model": "claude-opus-5-5"\n}\n',
            PROJECT: '{\n  "model": "claude-sonnet-5-5"\n}\n',
        },
    )
    assert [s.status for s in item(got, "model").sources] == [
        "in_effect",
        "overridden",
    ]
    assert rows(got, "model") == []


def test_a_wrong_type_list_beats_nothing_and_still_gets_one_row(
    tmp_path: Path,
) -> None:
    got = read(tmp_path, {USER: '{\n  "availableModels": "sonnet"\n}\n'})
    assert [(p.group, p.line) for p in rows(got, "availableModels")] == [
        ("cant_tell", 2)
    ]


# ------------------------------------------------- a list key shows the merged list


def test_available_models_shows_the_merged_list_that_runs(tmp_path: Path) -> None:
    got = read(
        tmp_path,
        {
            USER: '{\n  "availableModels": ["sonnet", "haiku"]\n}\n',
            PROJECT: '{\n  "availableModels": ["opus", "sonnet"]\n}\n',
        },
    )
    it = item(got, "availableModels")
    assert text(it) == '["opus","sonnet","haiku"]'
    assert it.winner == 0
    assert [s.value.text for s in it.sources if s.value] == [
        '["opus","sonnet"]',
        '["sonnet","haiku"]',
    ]
    assert rows(got, "availableModels") == []


def test_a_plain_list_key_combines_across_files(tmp_path: Path) -> None:
    got = read(
        tmp_path,
        {
            USER: '{\n  "companyAnnouncements": ["a", "b"]\n}\n',
            PROJECT: '{\n  "companyAnnouncements": ["b", "c"]\n}\n',
        },
    )
    it = item(got, "companyAnnouncements")
    assert text(it) == '["b","c","a"]'
    assert [s.status for s in it.sources] == ["in_effect", "in_effect"]
    assert it.effective is not None
    assert it.effective.origin == "set"


def test_a_plain_list_in_one_file_reads_as_it_is(tmp_path: Path) -> None:
    got = read(tmp_path, {USER: '{\n  "companyAnnouncements": ["a", "b"]\n}\n'})
    assert text(item(got, "companyAnnouncements")) == '["a","b"]'


def test_a_list_and_a_string_fall_back_to_the_highest_file(tmp_path: Path) -> None:
    got = read(
        tmp_path,
        {
            USER: '{\n  "companyAnnouncements": "oops"\n}\n',
            PROJECT: '{\n  "companyAnnouncements": ["b"]\n}\n',
        },
    )
    it = item(got, "companyAnnouncements")
    assert text(it) == '["b"]'
    assert [s.status for s in it.sources] == ["in_effect", "overridden"]


def test_a_secret_in_a_merged_list_stays_masked(tmp_path: Path) -> None:
    key = "sk-ant-api03-" + "x" * 40
    got = read(
        tmp_path,
        {
            USER: f'{{\n  "companyAnnouncements": ["{key}"]\n}}\n',
            PROJECT: '{\n  "companyAnnouncements": ["b"]\n}\n',
        },
    )
    shown = item(got, "companyAnnouncements").effective
    assert shown is not None
    assert shown.value is not None
    assert key not in shown.value.text
    assert shown.value.masked


# ------------------------------------------------- modelSettings, one model at a time


def test_model_settings_resolves_each_model_from_its_highest_file(
    tmp_path: Path,
) -> None:
    """The docs: across files, each model is resolved separately, so one file does
    not win the whole key."""
    got = read(
        tmp_path,
        {
            USER: (
                '{\n  "modelSettings": {\n'
                '    "claude-opus-5-5": {"effortLevel": "low"},\n'
                '    "claude-sonnet-5-5": {"effortLevel": "high"}\n  }\n}\n'
            ),
            PROJECT: (
                '{\n  "modelSettings": {\n'
                '    "claude-opus-5-5": {"effortLevel": "xhigh"}\n  }\n}\n'
            ),
        },
    )
    it = item(got, "modelSettings")
    assert text(it) == (
        '{"claude-opus-5-5":{"effortLevel":"xhigh"},'
        '"claude-sonnet-5-5":{"effortLevel":"high"}}'
    )
    assert [s.status for s in it.sources] == ["in_effect", "in_effect"]


def test_a_file_whose_models_are_all_beaten_reads_overridden(tmp_path: Path) -> None:
    got = read(
        tmp_path,
        {
            USER: (
                '{\n  "modelSettings": {"claude-opus-5-5": {"effortLevel": "low"}}\n}\n'
            ),
            PROJECT: (
                '{\n  "modelSettings": {"claude-opus-5-5": {"effortLevel": "high"}}\n}'
                "\n"
            ),
        },
    )
    it = item(got, "modelSettings")
    assert text(it) == '{"claude-opus-5-5":{"effortLevel":"high"}}'
    assert [s.status for s in it.sources] == ["in_effect", "overridden"]


# ------------------------------------------------- an agent-only key and the shell


def test_force_5m_beats_the_subagent_cache_lifetime_a_file_sets(
    tmp_path: Path,
) -> None:
    got = read(
        tmp_path,
        {USER: '{\n  "subagentPromptCacheTtl": "1h"\n}\n'},
        env={"FORCE_PROMPT_CACHING_5M": "1"},
    )
    it = item(got, "subagentPromptCacheTtl")
    assert text(it) == "5m"
    assert it.status == "in_effect"
    assert it.scope == "shell"
    assert [(s.scope, s.status) for s in it.sources] == [
        ("shell", "in_effect"),
        ("user", "overridden"),
    ]
    assert rows(got, "subagentPromptCacheTtl") == []


def test_the_subagent_cache_lifetime_a_file_sets_runs_when_nothing_beats_it(
    tmp_path: Path,
) -> None:
    got = read(tmp_path, {USER: '{\n  "subagentPromptCacheTtl": "1h"\n}\n'})
    it = item(got, "subagentPromptCacheTtl")
    assert text(it) == "1h"
    assert it.status == "in_effect"
    assert it.scope == "user"


def test_the_subagent_variable_beats_the_file(tmp_path: Path) -> None:
    got = read(
        tmp_path,
        {USER: '{\n  "subagentPromptCacheTtl": "1h"\n}\n'},
        env={"CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL": "5m"},
    )
    it = item(got, "subagentPromptCacheTtl")
    assert text(it) == "5m"
    assert it.scope == "shell"
    assert [s.status for s in it.sources] == ["in_effect", "overridden"]


def test_agent_rows_exist_only_for_the_agent_only_keys() -> None:
    assert sorted(collect_settings.AGENT_ONLY) == ["subagentPromptCacheTtl"]


# ------------------------------------------------- combine, alone


@pytest.mark.parametrize(
    ("values", "want", "gives"),
    [
        ([["a"]], ["a"], [True]),
        ([["a", "b"], ["b", "c"]], ["a", "b", "c"], [True, True]),
        ([["a"], "x"], ["a"], [True, False]),
        (["x", "y"], "x", [True, False]),
        ([{"m": 1}, {"m": 2, "n": 3}], {"m": 1, "n": 3}, [True, True]),
        ([{"m": 1}, {"m": 2}], {"m": 1}, [True, False]),
        ([[{"k": 1}], [{"k": 1}, {"k": 2}]], [{"k": 1}, {"k": 2}], [True, True]),
    ],
)
def test_combine(values: list[object], want: object, gives: list[bool]) -> None:
    assert collect_settings.combine(values) == (want, gives)
