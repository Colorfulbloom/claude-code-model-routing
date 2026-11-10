"""The Output style part: the setting and the style files (m4-build.md task 4).

The corpus cases (typical, complex, broken-settings) are checked in
``test_collect_settings.py``. These tests build small worlds for the rest.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_case_helpers as sc

import collect_output_style
import collect_settings
from models import SetupItem
from setup_contract import Collected

COLLECTOR = collect_settings.COLLECTOR


def run(
    tmp_path: Path, files: dict[str, str], handoff: dict[str, object] | None = None
) -> Collected:
    return COLLECTOR.read(sc.scratch(tmp_path, files), handoff or {})


def styles(got: Collected) -> dict[str, SetupItem]:
    return {i.id: i for i in got.items["output_style"]}


def setting(value: object) -> str:
    return json.dumps({"outputStyle": value})


STYLE = "---\nname: {name}\ndescription: A style.\n---\nBody text that is never read.\n"


@pytest.mark.parametrize("name", collect_output_style.BUILTINS)
def test_a_built_in_name_is_in_effect(tmp_path: Path, name: str) -> None:
    got = run(tmp_path, {"home/.claude/settings.json": setting(name)})
    item = styles(got)["output_style:outputStyle"]
    assert item.status == "in_effect"
    assert item.effective is not None
    assert (item.effective.origin, item.effective.value.text) == ("set", name)  # pyright: ignore[reportOptionalMemberAccess]
    assert item.facts.output_style is not None
    assert (item.facts.output_style.active, item.facts.output_style.builtin) == (
        name,
        True,
    )
    assert got.problems == []


@pytest.mark.parametrize("name", ["concise", "CONCISE", "learning", "explanatory"])
def test_a_wrong_case_falls_back_to_default_and_is_not_as_set(
    tmp_path: Path, name: str
) -> None:
    got = run(tmp_path, {"home/.claude/settings.json": setting(name)})
    item = styles(got)["output_style:outputStyle"]
    assert item.status == "ignored"
    assert item.effective is not None
    assert (item.effective.origin, item.effective.value.text) == ("default", "default")  # pyright: ignore[reportOptionalMemberAccess]
    assert item.facts.output_style is not None
    assert item.facts.output_style.active == "default"
    assert item.facts.output_style.builtin is False
    assert [
        (r.group, r.code, r.part) for r in got.problems if r.part == "output_style"
    ] == [("not_as_set", "ignored", "output_style")]


def test_default_is_a_known_style(tmp_path: Path) -> None:
    got = run(tmp_path, {"home/.claude/settings.json": setting("default")})
    assert styles(got)["output_style:outputStyle"].status == "in_effect"
    assert got.problems == []


def test_a_name_with_no_file_and_no_built_in_is_missing(tmp_path: Path) -> None:
    got = run(
        tmp_path, {"home/.claude/settings.json": '{\n  "outputStyle": "ghost"\n}'}
    )
    item = styles(got)["output_style:outputStyle"]
    assert item.status == "invalid"
    assert item.effective is not None
    assert item.effective.origin == "unknown"
    (row,) = got.problems
    assert (row.group, row.code, row.line, row.params) == (
        "wont_load",
        "output_style_missing",
        2,
        {"style": "ghost"},
    )
    assert row.id == "output_style_missing:output_style:outputStyle:2"


def test_a_value_that_is_not_a_string_is_missing(tmp_path: Path) -> None:
    got = run(tmp_path, {"home/.claude/settings.json": setting(5)})
    assert styles(got)["output_style:outputStyle"].status == "invalid"


def test_no_setting_means_no_setting_item(tmp_path: Path) -> None:
    got = run(
        tmp_path,
        {"home/.claude/output-styles/terse.md": STYLE.format(name="terse")},
    )
    assert list(styles(got)) == ["output_style:terse"]
    item = styles(got)["output_style:terse"]
    assert item.facts.output_style is not None
    assert item.facts.output_style.active is None


def test_a_style_file_names_a_setting_it_satisfies(tmp_path: Path) -> None:
    got = run(
        tmp_path,
        {
            "home/.claude/settings.json": setting("terse"),
            "home/.claude/output-styles/terse.md": STYLE.format(name="terse"),
        },
    )
    setting_item = styles(got)["output_style:outputStyle"]
    assert setting_item.status == "in_effect"
    assert setting_item.reason is not None
    assert setting_item.reason.ref_item == "output_style:terse"
    assert styles(got)["output_style:terse"].facts.output_style.active == "terse"  # pyright: ignore[reportOptionalMemberAccess]
    assert styles(got)["output_style:terse"].facts.output_style.builtin is False  # pyright: ignore[reportOptionalMemberAccess]


def test_a_file_without_a_name_takes_its_file_name(tmp_path: Path) -> None:
    got = run(
        tmp_path,
        {
            "home/.claude/output-styles/plain.md": "No front matter at all.\n",
            "home/.claude/output-styles/empty-fm.md": "---\n---\nBody.\n",
            "home/.claude/output-styles/no-name.md": "---\ndescription: x\n---\n",
        },
    )
    assert sorted(styles(got)) == [
        "output_style:empty-fm",
        "output_style:no-name",
        "output_style:plain",
    ]
    assert styles(got)["output_style:plain"].sources[0].key == "file"
    assert styles(got)["output_style:plain"].sources[0].line is None


def test_the_name_line_is_the_front_matter_line(tmp_path: Path) -> None:
    got = run(
        tmp_path,
        {"home/.claude/output-styles/a.md": "---\ndescription: d\nname: terse\n---\n"},
    )
    source = styles(got)["output_style:terse"].sources[0]
    assert (source.key, source.line, source.file) == (
        "name",
        3,
        "~/.claude/output-styles/a.md",
    )


def test_a_name_that_clashes_resolves_managed_then_project_then_user(
    tmp_path: Path,
) -> None:
    got = run(
        tmp_path,
        {
            "home/.claude/output-styles/x.md": STYLE.format(name="same"),
            "proj/.claude/output-styles/x.md": STYLE.format(name="same"),
            "managed/.claude/output-styles/x.md": STYLE.format(name="same"),
        },
    )
    item = styles(got)["output_style:same"]
    assert [(s.scope, s.status) for s in item.sources] == [
        ("managed", "in_effect"),
        ("project", "overridden"),
        ("user", "overridden"),
    ]
    assert item.scope == "managed"
    assert item.read_only_reason is not None
    assert item.read_only_reason.code == "managed"
    assert [r.scope for r in item.reach] == ["managed", "project", "user", "plugin"]


def test_hidden_files_and_other_files_are_not_styles(tmp_path: Path) -> None:
    got = run(
        tmp_path,
        {
            "home/.claude/output-styles/.hidden.md": STYLE.format(name="hidden"),
            "home/.claude/output-styles/notes.txt": "x",
            "home/.claude/output-styles/real.md": STYLE.format(name="real"),
        },
    )
    assert list(styles(got)) == ["output_style:real"]


@pytest.mark.parametrize(
    "text",
    [
        "---\nname: [unclosed\n---\n",
        "---\nname: a\nname: b\n---\n",
        "---\nname: terse\nno closing fence\n",
        "---\n- a list\n- not a map\n---\n",
    ],
)
def test_front_matter_that_will_not_parse_is_wont_load(
    tmp_path: Path, text: str
) -> None:
    got = run(tmp_path, {"home/.claude/output-styles/bad.md": text})
    item = styles(got)["output_style:bad"]
    assert item.status == "invalid"
    assert [(r.group, r.code, r.item_id) for r in got.problems] == [
        ("wont_load", "frontmatter_invalid", "output_style:bad")
    ]


def test_a_hyphenated_key_that_the_agent_reader_rejects_still_reads(
    tmp_path: Path,
) -> None:
    text = (
        "---\nname: terse\nkeep-coding-instructions: true\n"
        "force-for-plugin: false\n---\n"
    )
    got = run(tmp_path, {"home/.claude/output-styles/t.md": text})
    assert styles(got)["output_style:terse"].status == "in_effect"
    assert got.problems == []


def test_no_body_reaches_an_item(tmp_path: Path) -> None:
    text = STYLE.format(name="terse").replace("Body text", "SENTINEL-BODY-TEXT")
    got = run(tmp_path, {"home/.claude/output-styles/t.md": text})
    assert "SENTINEL-BODY-TEXT" not in json.dumps(
        [i.model_dump() for i in got.items["output_style"]]
    )


def test_a_style_file_that_is_not_utf8_is_couldnt_read(tmp_path: Path) -> None:
    ctx = sc.scratch(
        tmp_path, {"home/.claude/output-styles/ok.md": STYLE.format(name="ok")}
    )
    (tmp_path / "home" / ".claude" / "output-styles" / "bad.md").write_bytes(
        b"---\n\xff\xfe\n---\n"
    )
    got = COLLECTOR.read(ctx, {})
    assert [(u.file, u.scope, u.reason) for u in got.unreadable] == [
        ("~/.claude/output-styles/bad.md", "user", "not_utf8")
    ]
    assert list(styles(got)) == ["output_style:ok"]


@pytest.mark.skipif(os.geteuid() == 0, reason="mode 000 does not stop root")
def test_a_folder_that_will_not_list_is_one_row(tmp_path: Path) -> None:
    ctx = sc.scratch(
        tmp_path, {"home/.claude/output-styles/ok.md": STYLE.format(name="ok")}
    )
    folder = tmp_path / "home" / ".claude" / "output-styles"
    folder.chmod(0)
    try:
        got = COLLECTOR.read(ctx, {})
    finally:
        folder.chmod(0o700)
    assert [(u.reason, u.scope) for u in got.unreadable] == [
        ("folder_unlistable", "user")
    ]


def test_a_symlinked_folder_that_leaves_the_roots_is_not_entered(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    (outside).mkdir()
    (outside / "evil.md").write_text(STYLE.format(name="evil"), encoding="utf-8")
    ctx = sc.scratch(tmp_path, {})
    (tmp_path / "home" / ".claude" / "output-styles").symlink_to(outside)
    got = COLLECTOR.read(ctx, {})
    assert styles(got) == {}
    assert [u.reason for u in got.unreadable] == ["outside_scope"]


def test_a_symlinked_file_is_read_and_reports_its_real_path(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "linked.md").write_text(STYLE.format(name="linked"), encoding="utf-8")
    ctx = sc.scratch(tmp_path, {})
    folder = tmp_path / "home" / ".claude" / "output-styles"
    folder.mkdir()
    (folder / "linked.md").symlink_to(outside / "linked.md")
    got = COLLECTOR.read(ctx, {})
    item = styles(got)["output_style:linked"]
    assert item.real_path == "linked.md"


def test_the_plugin_handoff_adds_plugin_styles(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {"home/.claude/settings.json": setting("from-plugin")})
    path = (
        ctx.config_dir
        / "plugins"
        / "cache"
        / "m"
        / "p"
        / "1"
        / "output-styles"
        / "x.md"
    )
    path.parent.mkdir(parents=True)
    path.write_text(STYLE.format(name="from-plugin"), encoding="utf-8")
    handoff: dict[str, object] = {
        collect_output_style.PLUGIN_STYLES: [
            {"plugin": "p", "path": str(path), "name": "x"},
            {"plugin": "q", "path": str(ctx.config_dir / "plugins" / "gone.md")},
            {"plugin": 5, "path": "x"},
            "not a mapping",
        ]
    }
    got = COLLECTOR.read(ctx, handoff)
    item = styles(got)["output_style:from-plugin"]
    assert item.scope == "plugin"
    assert item.sources[0].plugin == "p"
    assert item.read_only_reason is not None
    assert (item.read_only_reason.code, item.read_only_reason.params) == (
        "plugin",
        {"plugin": "p"},
    )
    assert styles(got)["output_style:outputStyle"].status == "in_effect"


def test_a_plugin_style_outside_the_plugins_folder_is_not_read(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    other = tmp_path / "elsewhere" / "x.md"
    other.parent.mkdir()
    other.write_text(STYLE.format(name="elsewhere"), encoding="utf-8")
    got = COLLECTOR.read(
        ctx, {collect_output_style.PLUGIN_STYLES: [{"plugin": "p", "path": str(other)}]}
    )
    assert styles(got) == {}
    assert [u.reason for u in got.unreadable] == ["plugin_outside_plugins"]


def test_the_folders_name_the_three_places(tmp_path: Path) -> None:
    ctx = sc.scratch(tmp_path, {})
    assert [
        p.relative_to(tmp_path.resolve()).as_posix()
        for p in collect_output_style.folders(ctx)
    ] == [
        "managed/.claude/output-styles",
        "proj/.claude/output-styles",
        "home/.claude/output-styles",
    ]
