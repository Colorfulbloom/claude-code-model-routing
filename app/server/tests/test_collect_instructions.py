"""The CLAUDE.md and Rules files collector (m4-build.md task 7).

Every corpus case's expected.json is the oracle for both parts, field by field (id,
scope, status, loads, imports, location and sources). Crafted folders then cover import
chains, cycles, the hop limit, imports out of the roots, ancestor files up to the
filesystem root, the nested walk and its cap, rules front matter, the Couldn't read
state per part, masking, the body never reaching an answer, the order across two reads
and the signature.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import instruction_collect_helpers as ih
import setup_case_helpers as sc

import collect_instructions
import collect_settings
import read_scope
from models import SetupItem
from setup_contract import Collected, SetupContext

COLLECTOR = collect_instructions.COLLECTOR
BODY = "BODY-SENTINEL-NEVER-IN-AN-ANSWER"
NOT_ROOT = os.geteuid() != 0
PARTS = ("instructions", "rules")


def put(path: Path, text: str = f"# Notes\n{BODY}\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def ctx_for(tmp: Path, *, project: str = "proj", listed: bool = True) -> SetupContext:
    """Return a context over ``tmp``: config ``home/.claude``, managed ``managed``."""
    root = tmp.resolve()
    for folder in ("home/.claude", "managed", project):
        (root / folder).mkdir(parents=True, exist_ok=True)
    return SetupContext(
        project_key="proj",
        config_dir=root / "home" / ".claude",
        home=root / "home",
        project_dir=root / project if listed else None,
        managed_dir=root / "managed",
    )


def read(tmp: Path, **kw: object) -> Collected:
    return ih.instructions(ctx_for(tmp, **kw))  # pyright: ignore[reportArgumentType]


def ids(got: Collected, part: str = "instructions") -> list[str]:
    return [i.id for i in got.items[part]]  # pyright: ignore[reportArgumentType]


def by_id(got: Collected, part: str = "instructions") -> dict[str, SetupItem]:
    return {i.id: i for i in got.items[part]}  # pyright: ignore[reportArgumentType]


# ---------------------------------------------------------------- the corpus


@pytest.mark.parametrize("case", sc.CASES)
@pytest.mark.parametrize("part", PARTS)
def test_items_match_the_expected_json(
    case: str, part: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    got = ih.instructions(sc.context(root))
    items, _unreadable = ih.expected_part(case, part)
    made = [ih.instruction_view(i) for i in got.items[part]]  # pyright: ignore[reportArgumentType]
    assert made == [ih.wanted_instruction(i) for i in items]


@pytest.mark.parametrize("case", sc.CASES)
def test_problems_match_the_expected_json(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    got = ih.instructions(sc.context(root))
    made, wanted = sc.compare_problems(got, case, PARTS)
    assert made == wanted


@pytest.mark.parametrize("case", sc.CASES)
def test_unreadable_files_match_the_expected_json(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    got = ih.instructions(sc.context(root))
    wanted = [
        (u["file"], u["scope"], u["reason"])
        for part in PARTS
        for u in ih.expected_part(case, part)[1]
    ]
    assert [(u.file, u.scope, u.reason) for u in got.unreadable] == wanted
    assert all(u.part in PARTS for u in got.unreadable)


def test_an_empty_case_has_no_items(tmp_path: Path, setup_corpus: Path) -> None:
    root = sc.world("empty", tmp_path / "w", setup_corpus)
    got = ih.instructions(sc.context(root))
    assert got.items["instructions"] == []
    assert got.items["rules"] == []
    assert got.problems == []


# ---------------------------------------------------------------- item fields


def test_the_item_fields_of_an_instruction_file(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("typical", tmp_path / "w", setup_corpus)
    got = ih.instructions(sc.context(root))
    item = by_id(got)["instructions:CLAUDE.md"]
    assert (item.part, item.key, item.name, item.label_known) == (
        "instructions",
        "CLAUDE.md",
        "CLAUDE.md",
        True,
    )
    assert item.writable is False
    assert item.read_only_reason is None
    assert item.feature == "core"
    assert item.winner == 0
    assert item.effective is None
    assert item.confidence.level == "documented"
    assert item.reason is not None
    assert item.reason.code == "in_effect"
    assert item.facts.instruction is not None
    assert item.facts.instruction.lines == 3
    assert item.facts.instruction.bytes == len(
        (root / "work" / "parent" / "proj" / "CLAUDE.md").read_bytes()
    )
    assert [r.scope for r in item.reach] == [
        "managed",
        "project_local",
        "project",
        "user",
    ]
    source = item.sources[0]
    assert source.full_path is not None
    assert Path(source.full_path).is_absolute()
    assert source.value is None


def test_a_managed_file_is_read_only(tmp_path: Path, setup_corpus: Path) -> None:
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    item = by_id(ih.instructions(sc.context(root)))["instructions:managed/CLAUDE.md"]
    assert item.read_only_reason is not None
    assert item.read_only_reason.code == "managed"
    assert item.scope == "managed"


def test_load_order_is_managed_user_ancestors_project_then_nested(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    got = ih.instructions(sc.context(root))
    assert ids(got) == [
        "instructions:managed/CLAUDE.md",
        "instructions:~/.claude/CLAUDE.md",
        "instructions:../CLAUDE.md",
        "instructions:../CLAUDE.local.md",
        "instructions:CLAUDE.md",
        "instructions:docs/guide.md",
        "instructions:.claude/CLAUDE.md",
        "instructions:CLAUDE.local.md",
        "instructions:packages/web/CLAUDE.md",
    ]
    loads = {i.id: i.loads.kind for i in got.items["instructions"] if i.loads}
    assert loads["instructions:packages/web/CLAUDE.md"] == "on_demand"
    assert loads["instructions:CLAUDE.md"] == "always"


# ---------------------------------------------------------------- imports


def test_an_import_chain_shows_in_order_with_its_depth(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("typical", tmp_path / "w", setup_corpus)
    got = ih.instructions(sc.context(root))
    chain = [
        (i.id, [(r.target, r.depth, r.state) for r in i.facts.instruction.imports])  # pyright: ignore[reportOptionalMemberAccess]
        for i in got.items["instructions"]
        if i.id.startswith("instructions:docs") or i.id == "instructions:CLAUDE.md"
    ]
    assert chain == [
        ("instructions:CLAUDE.md", [("docs/style.md", 1, "read")]),
        ("instructions:docs/style.md", [("tone.md", 2, "read")]),
        ("instructions:docs/tone.md", [("words.md", 3, "read")]),
        ("instructions:docs/words.md", []),
    ]
    # The imported files follow their importer, before the next startup file.
    assert (
        ids(got).index("instructions:docs/words.md")
        == ids(got).index("instructions:CLAUDE.md") + 3
    )


def test_a_cycle_is_reported_once_at_the_import_that_closes_it(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("broken-instructions", tmp_path / "w", setup_corpus)
    got = ih.instructions(sc.context(root))
    cycles = [r for r in got.problems if r.code == "import_cycle"]
    assert [(r.item_id, r.line, r.file) for r in cycles] == [
        ("instructions:notes/b.md", 2, "notes/b.md")
    ]
    closing = by_id(got)["instructions:notes/b.md"].facts.instruction
    assert closing is not None
    assert [(r.state, r.target_item, r.depth) for r in closing.imports] == [
        ("cycle", "instructions:notes/a.md", 3)
    ]
    # No second item for the file the loop returns to.
    assert ids(got).count("instructions:notes/a.md") == 1


def test_a_file_that_imports_itself_is_a_cycle(tmp_path: Path) -> None:
    put(tmp_path / "proj" / "CLAUDE.md", "See @CLAUDE.md here.\n")
    got = read(tmp_path)
    assert [(r.code, r.line) for r in got.problems] == [("import_cycle", 1)]
    assert ids(got) == ["instructions:CLAUDE.md"]


def test_the_hop_limit_is_four(tmp_path: Path) -> None:
    for n in range(1, 7):
        put(tmp_path / "proj" / f"n{n}.md", f"next @n{n + 1}.md\n")
    put(tmp_path / "proj" / "CLAUDE.md", "start @n1.md\n")
    got = read(tmp_path)
    assert ids(got) == [
        "instructions:CLAUDE.md",
        "instructions:n1.md",
        "instructions:n2.md",
        "instructions:n3.md",
        "instructions:n4.md",
    ]
    last = by_id(got)["instructions:n4.md"].facts.instruction
    assert last is not None
    assert [(r.state, r.depth, r.target_item) for r in last.imports] == [
        ("too_deep", 5, None)
    ]
    assert [(r.code, r.item_id) for r in got.problems] == [
        ("import_too_deep", "instructions:n4.md")
    ]


def test_a_missing_import_is_wont_load_and_a_diamond_is_not(tmp_path: Path) -> None:
    put(tmp_path / "proj" / "CLAUDE.md", "@a.md\n@b.md\n@gone.md\n")
    put(tmp_path / "proj" / "a.md", "@shared.md\n")
    put(tmp_path / "proj" / "b.md", "@shared.md\n")
    put(tmp_path / "proj" / "shared.md", "x\n")
    got = read(tmp_path)
    assert ids(got) == [
        "instructions:CLAUDE.md",
        "instructions:a.md",
        "instructions:shared.md",
        "instructions:b.md",
    ]
    b = by_id(got)["instructions:b.md"].facts.instruction
    assert b is not None
    assert [(r.state, r.target_item) for r in b.imports] == [
        ("read", "instructions:shared.md")
    ]
    assert [(r.code, r.group, r.line) for r in got.problems] == [
        ("import_missing", "wont_load", 3)
    ]


def test_an_import_out_of_the_roots_is_not_read(tmp_path: Path) -> None:
    """The audit test proves the file is never opened. This one proves the answer."""
    put(tmp_path / "outside" / "secret.md", "OUTSIDE-SENTINEL\n")
    put(tmp_path / "proj" / "CLAUDE.md", "go @../outside/secret.md\n")
    got = read(tmp_path)
    item = by_id(got)["instructions:CLAUDE.md"].facts.instruction
    assert item is not None
    assert [(r.state, r.target_item) for r in item.imports] == [("not_read", None)]
    assert [(u.file, u.scope, u.reason, u.problem, u.part) for u in got.unreadable] == [
        ("../outside/secret.md", "project", "outside_scope", None, "instructions")
    ]
    assert [(r.code, r.group, r.kind, r.part) for r in got.problems] == [
        ("import_out_of_scope", "cant_tell", "cant_tell", "instructions")
    ]
    assert "OUTSIDE-SENTINEL" not in ih.dump(got)


def test_a_home_import_reads_inside_the_config_folder_only(tmp_path: Path) -> None:
    put(tmp_path / "home" / ".claude" / "shared.md", "shared\n")
    put(tmp_path / "home" / "other.md", "other\n")
    put(tmp_path / "proj" / "CLAUDE.md", "@~/.claude/shared.md\n@~/other.md\n")
    got = read(tmp_path)
    assert ids(got) == ["instructions:CLAUDE.md", "instructions:~/.claude/shared.md"]
    assert by_id(got)["instructions:~/.claude/shared.md"].scope == "user"
    assert [u.reason for u in got.unreadable] == ["outside_scope"]
    assert got.unreadable[0].file == Path("..", "home", "other.md").as_posix()


def test_an_import_in_a_file_with_no_home_is_not_read(tmp_path: Path) -> None:
    put(tmp_path / "proj" / "CLAUDE.md", "@~/x.md\n")
    ctx = ctx_for(tmp_path)
    ctx = SetupContext(
        project_key="proj",
        config_dir=ctx.config_dir,
        home=None,
        project_dir=ctx.project_dir,
        managed_dir=ctx.managed_dir,
    )
    got = ih.instructions(ctx)
    item = by_id(got)["instructions:CLAUDE.md"].facts.instruction
    assert item is not None
    assert [r.state for r in item.imports] == ["not_read"]
    assert [r.code for r in got.problems] == ["import_out_of_scope"]


def test_what_counts_as_an_import(tmp_path: Path) -> None:
    text = "\n".join(
        [
            "real @one.md and @two.md.",
            "mail me at user@host.example please",
            "mention @someone only",
            "code `@code.md` span",
            "```",
            "@fenced.md",
            "```",
            "<!-- @commented.md -->",
            "<!--",
            "@block-commented.md",
            "-->",
            "(see @three.md)",
            '"@quoted.md"',
            "after all @four.md",
        ]
    )
    put(tmp_path / "proj" / "CLAUDE.md", text + "\n")
    got = read(tmp_path)
    item = by_id(got)["instructions:CLAUDE.md"].facts.instruction
    assert item is not None
    assert [(r.target, r.line) for r in item.imports] == [
        ("one.md", 1),
        ("two.md", 1),
        ("three.md", 12),
        ("four.md", 14),
    ]
    assert {r.state for r in item.imports} == {"missing"}


def test_import_refs_reads_line_numbers_and_never_returns_text() -> None:
    refs = collect_instructions.import_refs("a\n\nsee @x/y.md\r\nand @z.md\n")
    assert refs == [("x/y.md", 3), ("z.md", 4)]
    assert collect_instructions.import_refs("") == []


def test_an_import_of_a_directory_or_a_non_file_is_missing(tmp_path: Path) -> None:
    (tmp_path / "proj" / "folder.d").mkdir(parents=True)
    put(tmp_path / "proj" / "CLAUDE.md", "@folder.d\n")
    got = read(tmp_path)
    assert [r.code for r in got.problems] == ["import_missing"]


# ---------------------------------------------------------------- ancestors


def _deep(tmp_path: Path) -> SetupContext:
    return ctx_for(tmp_path, project="a/b/proj")


def test_ancestor_files_are_read_to_the_root_and_marked_parent(tmp_path: Path) -> None:
    put(tmp_path / "a" / "b" / "CLAUDE.md")
    put(tmp_path / "a" / "b" / "CLAUDE.local.md")
    put(tmp_path / "a" / "CLAUDE.md")
    put(tmp_path / "CLAUDE.md")
    put(tmp_path / "a" / "b" / "proj" / "CLAUDE.md")
    got = ih.instructions(_deep(tmp_path))
    assert ids(got) == [
        "instructions:../../../CLAUDE.md",
        "instructions:../../CLAUDE.md",
        "instructions:../CLAUDE.md",
        "instructions:../CLAUDE.local.md",
        "instructions:CLAUDE.md",
    ]
    items = by_id(got)
    assert [(i.scope, i.location) for i in got.items["instructions"]] == [
        ("project", "parent"),
        ("project", "parent"),
        ("project", "parent"),
        ("project_local", "parent"),
        ("project", None),
    ]
    assert items["instructions:../CLAUDE.md"].sources[0].location == "parent"
    assert items["instructions:CLAUDE.md"].sources[0].location is None
    assert got.unreadable == []


def test_only_the_two_exact_names_are_read_above_the_project(tmp_path: Path) -> None:
    put(tmp_path / "a" / "b" / "AGENTS.md")
    put(tmp_path / "a" / "b" / ".claude" / "CLAUDE.md")
    put(tmp_path / "a" / "b" / "notes.md")
    put(tmp_path / "a" / "b" / "proj" / "CLAUDE.md")
    got = ih.instructions(_deep(tmp_path))
    assert ids(got) == ["instructions:CLAUDE.md"]


def test_an_unlisted_project_reads_only_managed_and_user(tmp_path: Path) -> None:
    put(tmp_path / "managed" / "CLAUDE.md")
    put(tmp_path / "home" / ".claude" / "CLAUDE.md")
    put(tmp_path / "proj" / "CLAUDE.md")
    put(tmp_path / "CLAUDE.md")
    got = read(tmp_path, listed=False)
    assert ids(got) == [
        "instructions:managed/CLAUDE.md",
        "instructions:~/.claude/CLAUDE.md",
    ]
    assert got.items["rules"] == []


def test_a_single_file_symlink_is_followed_and_shows_its_real_path(
    tmp_path: Path,
) -> None:
    target = put(tmp_path / "dotfiles" / "CLAUDE.md")
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "CLAUDE.md").symlink_to(target)
    got = read(tmp_path)
    item = by_id(got)["instructions:CLAUDE.md"]
    assert item.real_path is not None
    assert item.real_path == "CLAUDE.md"  # outside the roots: the last part only
    assert not item.real_path.startswith("/")
    assert BODY not in ih.dump(got)


# ---------------------------------------------------------------- AGENTS.md


def test_agents_md_loads_only_when_no_claude_file_exists(tmp_path: Path) -> None:
    put(tmp_path / "proj" / "AGENTS.md")
    got = read(tmp_path)
    item = by_id(got)["instructions:AGENTS.md"]
    assert item.loads is not None
    assert item.loads.kind == "when_no_claude_md"
    put(tmp_path / "proj" / ".claude" / "CLAUDE.md")
    assert ids(read(tmp_path)) == ["instructions:.claude/CLAUDE.md"]


def test_a_claude_file_in_an_ancestor_keeps_agents_md_out(tmp_path: Path) -> None:
    put(tmp_path / "a" / "CLAUDE.md")
    put(tmp_path / "a" / "b" / "proj" / "AGENTS.md")
    assert ids(ih.instructions(_deep(tmp_path))) == ["instructions:../../CLAUDE.md"]


# ---------------------------------------------------------------- the nested walk


def test_nested_files_load_on_demand_and_skip_the_skipped_folders(
    tmp_path: Path,
) -> None:
    put(tmp_path / "proj" / "CLAUDE.md")
    put(tmp_path / "proj" / "pkg" / "CLAUDE.md")
    put(tmp_path / "proj" / "pkg" / "CLAUDE.local.md")
    put(tmp_path / "proj" / "node_modules" / "dep" / "CLAUDE.md")
    put(tmp_path / "proj" / ".hidden" / "CLAUDE.md")
    got = read(tmp_path)
    assert ids(got) == [
        "instructions:CLAUDE.md",
        "instructions:pkg/CLAUDE.md",
        "instructions:pkg/CLAUDE.local.md",
    ]
    nested = got.items["instructions"][1:]
    assert [(i.scope, i.loads.kind) for i in nested if i.loads] == [  # pyright: ignore[reportOptionalMemberAccess]
        ("project", "on_demand"),
        ("project_local", "on_demand"),
    ]
    assert got.problems == []


def test_a_nested_file_imported_at_start_is_not_listed_twice(tmp_path: Path) -> None:
    put(tmp_path / "proj" / "CLAUDE.md", "@pkg/CLAUDE.md\n")
    put(tmp_path / "proj" / "pkg" / "CLAUDE.md")
    got = read(tmp_path)
    assert ids(got) == ["instructions:CLAUDE.md", "instructions:pkg/CLAUDE.md"]
    assert got.items["instructions"][1].loads.kind == "always"  # pyright: ignore[reportOptionalMemberAccess]


def test_a_walk_a_cap_stopped_is_a_cant_tell_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(read_scope, "WALK_MAX_FOLDERS", 2)
    for name in ("a", "b", "c"):
        put(tmp_path / "proj" / name / "CLAUDE.md")
    got = read(tmp_path)
    stopped = [r for r in got.problems if r.code == "walk_stopped"]
    assert [(r.group, r.kind, r.part, r.item_id, r.line) for r in stopped] == [
        ("cant_tell", "cant_tell", "instructions", None, None)
    ]
    assert stopped[0].id == "walk_stopped:instructions"
    assert 0 < len(got.items["instructions"]) < 3


def test_a_tree_past_the_depth_cap_is_a_cant_tell_row(tmp_path: Path) -> None:
    here = tmp_path / "proj"
    for level in range(1, 9):
        here = here / f"l{level}"
        put(here / "CLAUDE.md")
    got = read(tmp_path)
    assert [r.code for r in got.problems] == ["walk_stopped"]
    assert "instructions:l1/l2/l3/l4/l5/l6/l7/l8/CLAUDE.md" not in ids(got)
    assert "instructions:l1/CLAUDE.md" in ids(got)


# ---------------------------------------------------------------- rules


def _rule(tmp_path: Path, front: str) -> SetupItem:
    put(tmp_path / "proj" / ".claude" / "rules" / "r.md", f"{front}{BODY}\n")
    got = read(tmp_path)
    return by_id(got, "rules")["rules:.claude/rules/r.md"]


def test_paths_as_a_yaml_list_become_on_demand_globs(tmp_path: Path) -> None:
    item = _rule(tmp_path, "---\npaths:\n  - src/**/*.ts\n  - docs/*.md\n---\n")
    assert item.loads is not None
    assert (item.loads.kind, item.loads.globs) == (
        "on_demand",
        ["src/**/*.ts", "docs/*.md"],
    )
    assert (item.sources[0].key, item.sources[0].line) == ("paths", 2)


def test_paths_as_a_comma_separated_string(tmp_path: Path) -> None:
    item = _rule(tmp_path, '---\npaths: "src/**, lib/**"\n---\n')
    assert item.loads is not None
    assert item.loads.globs == ["src/**", "lib/**"]


@pytest.mark.parametrize(
    "front",
    ["", "---\ndescription: x\n---\n", "---\npaths:\n---\n", "---\npaths: []\n---\n"],
)
def test_a_rule_with_no_paths_loads_at_launch(tmp_path: Path, front: str) -> None:
    item = _rule(tmp_path, front)
    assert item.loads is not None
    assert (item.loads.kind, item.loads.globs) == ("always", [])
    assert (item.sources[0].key, item.sources[0].line) == (
        ("paths", 2) if "paths" in front else ("file", None)
    )


@pytest.mark.parametrize(
    "front",
    [
        "---\npaths: [unclosed\n---\n",
        "---\npaths: {a: 1}\n---\n",
        "---\npaths: 3\n---\n",
    ],
)
def test_bad_front_matter_loads_with_no_paths_and_is_not_as_set(
    tmp_path: Path, front: str
) -> None:
    put(tmp_path / "proj" / ".claude" / "rules" / "r.md", front + "Body.\n")
    got = read(tmp_path)
    item = by_id(got, "rules")["rules:.claude/rules/r.md"]
    assert item.status == "in_effect"
    assert item.loads is not None
    assert (item.loads.kind, item.loads.globs) == ("always", [])
    assert [(r.code, r.group, r.kind, r.line, r.item_id) for r in got.problems] == [
        ("ignored", "not_as_set", "problem", 2, "rules:.claude/rules/r.md")
    ]
    assert got.problems[0].fix.kind == "open_item"


def test_rules_are_read_recursively_user_first(tmp_path: Path) -> None:
    put(tmp_path / "home" / ".claude" / "rules" / "u.md")
    put(tmp_path / "proj" / ".claude" / "rules" / "b.md")
    put(tmp_path / "proj" / ".claude" / "rules" / "a" / "deep" / "c.md")
    put(tmp_path / "proj" / ".claude" / "rules" / "notes.txt")
    put(tmp_path / "proj" / ".claude" / "rules" / ".hidden.md")
    got = read(tmp_path)
    assert ids(got, "rules") == [
        "rules:~/.claude/rules/u.md",
        "rules:.claude/rules/a/deep/c.md",
        "rules:.claude/rules/b.md",
    ]
    assert [i.scope for i in got.items["rules"]] == ["user", "project", "project"]
    fact = got.items["rules"][0].facts.instruction
    assert fact is not None
    assert fact.imports == []
    assert [r.scope for r in got.items["rules"][0].reach] == ["project", "user"]


def test_a_rules_folder_that_is_a_link_cycle_does_not_loop(tmp_path: Path) -> None:
    rules = tmp_path / "proj" / ".claude" / "rules"
    put(rules / "x.md")
    (rules / "loop").symlink_to(rules)
    got = read(tmp_path)
    assert ids(got, "rules") == ["rules:.claude/rules/x.md"]


# ---------------------------------------------------------------- Couldn't read


@pytest.fixture
def world(tmp_path: Path, setup_corpus: Path) -> Path:
    return sc.world("typical", tmp_path / "world", setup_corpus)


def _corrupt(root: Path, kind: str, rel: str) -> Collected:
    sc.bc.make_unreadable(root, kind, rel)
    return ih.instructions(sc.context(root))


def test_a_claude_file_that_is_not_utf8_is_couldnt_read(world: Path) -> None:
    got = _corrupt(world, "not_utf8", "work/parent/proj/CLAUDE.md")
    assert [(u.file, u.scope, u.reason, u.part) for u in got.unreadable] == [
        ("CLAUDE.md", "project", "not_utf8", "instructions")
    ]
    assert "instructions:CLAUDE.md" not in ids(got)
    assert "instructions:~/.claude/CLAUDE.md" in ids(got)
    assert got.problems == []


def test_a_rules_file_that_is_not_utf8_is_couldnt_read_for_rules(world: Path) -> None:
    got = _corrupt(world, "not_utf8", "work/parent/proj/.claude/rules/review.md")
    assert [(u.reason, u.part) for u in got.unreadable] == [("not_utf8", "rules")]
    assert got.items["rules"] == []


def test_a_file_over_the_cap_is_couldnt_read(world: Path) -> None:
    got = _corrupt(world, "too_large", "home/.claude/CLAUDE.md")
    assert [(u.reason, u.scope, u.part) for u in got.unreadable] == [
        ("too_large", "user", "instructions")
    ]


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_a_file_at_mode_000_is_couldnt_read(world: Path) -> None:
    got = _corrupt(world, "mode000", "work/parent/proj/CLAUDE.local.md")
    assert [(u.reason, u.scope) for u in got.unreadable] == [
        ("permission", "project_local")
    ]
    (world / "work" / "parent" / "proj" / "CLAUDE.local.md").chmod(0o600)


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_a_rules_folder_that_will_not_list_is_one_row(world: Path) -> None:
    folder = world / "work" / "parent" / "proj" / ".claude" / "rules"
    folder.chmod(0)
    try:
        got = ih.instructions(sc.context(world))
    finally:
        folder.chmod(0o700)
    assert [(u.reason, u.part) for u in got.unreadable] == [
        ("folder_unlistable", "rules")
    ]


def test_an_import_that_is_not_utf8_is_not_read_with_its_own_reason(
    tmp_path: Path,
) -> None:
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "bin.md").write_bytes(b"\xff\xfe not utf-8")
    put(tmp_path / "proj" / "CLAUDE.md", "@bin.md\n")
    got = read(tmp_path)
    item = by_id(got)["instructions:CLAUDE.md"].facts.instruction
    assert item is not None
    assert [r.state for r in item.imports] == ["not_read"]
    assert [(u.file, u.reason, u.part) for u in got.unreadable] == [
        ("bin.md", "not_utf8", "instructions")
    ]
    assert got.problems == []


def test_a_missing_file_is_not_a_failure(tmp_path: Path, setup_corpus: Path) -> None:
    root = sc.world("empty", tmp_path / "w", setup_corpus)
    assert ih.instructions(sc.context(root)).unreadable == []


def test_a_failed_file_changes_no_other_file_but_an_importer_may_change(
    world: Path,
) -> None:
    got = _corrupt(world, "not_utf8", "home/.claude/CLAUDE.md")
    assert not any(i.may_change for i in got.items["instructions"])
    got = _corrupt(world, "not_utf8", "work/parent/proj/docs/style.md")
    flagged = [i.id for i in got.items["instructions"] if i.may_change]
    assert flagged == ["instructions:CLAUDE.md"]


# ---------------------------------------------------------------- masking and bodies


def test_no_body_text_reaches_an_answer(tmp_path: Path) -> None:
    put(tmp_path / "home" / ".claude" / "CLAUDE.md")
    put(tmp_path / "proj" / "CLAUDE.md", f"@a.md\n@missing.md\n{BODY}\n")
    put(tmp_path / "proj" / "a.md", f"{BODY}\n@../out.md\n")
    put(tmp_path / "out.md")
    put(
        tmp_path / "proj" / ".claude" / "rules" / "bad.md",
        f"---\npaths: [\n---\n{BODY}\n",
    )
    put(
        tmp_path / "proj" / ".claude" / "rules" / "ok.md",
        f"---\npaths: x/**\n---\n{BODY}\n",
    )
    put(tmp_path / "proj" / "pkg" / "CLAUDE.md")
    got = read(tmp_path)
    assert len(got.items["instructions"]) == 4
    assert len(got.items["rules"]) == 2
    assert BODY not in ih.dump(got)


def test_no_secret_of_the_corpus_reaches_an_answer(
    tmp_path: Path, setup_corpus: Path
) -> None:
    secrets = json.loads((sc.CORPUS / "secrets.json").read_text("utf-8"))
    values = [s["value"] for s in secrets["secrets"] + secrets["never"]]
    assert values
    for case in sc.CASES:
        root = sc.world(case, tmp_path / case, setup_corpus)
        text = ih.dump(ih.instructions(sc.context(root)))
        assert [v for v in values if v in text] == [], case


def test_what_a_case_says_is_never_read_is_in_no_answer(
    tmp_path: Path, setup_corpus: Path
) -> None:
    checked = 0
    for case in sc.CASES:
        never = [v for v in sc.expected(case).get("never", []) if v != "hidden"]
        root = sc.world(case, tmp_path / case, setup_corpus)
        text = ih.dump(ih.instructions(sc.context(root)))
        for value in never:
            assert value not in text, (case, value)
            checked += 1
    assert checked >= 3


def test_auto_memory_is_never_an_item_or_an_import(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("scope-memory", tmp_path / "w", setup_corpus)
    memory = root / "home" / ".claude" / "projects" / "x" / "memory" / "MEMORY.md"
    project_file = root / "work" / "parent" / "proj" / "CLAUDE.md"
    project_file.write_text(f"@{memory}\n", encoding="utf-8")
    got = ih.instructions(sc.context(root))
    assert "MEMORY" not in ih.dump(got).replace("MEMORY.md", "")  # the sentinel text
    assert [r.code for r in got.problems] == ["import_out_of_scope"]
    assert [u.reason for u in got.unreadable] == ["outside_scope"]


# --------------------------------------------------------- order and the signature


@pytest.mark.parametrize(
    "case", ["typical", "complex", "stress", "broken-instructions", "scope-ancestors"]
)
def test_ids_and_order_are_stable_over_two_reads(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    first = ih.instructions(sc.context(root))
    second = ih.instructions(sc.context(root))
    for part in PARTS:
        one = first.items[part]  # pyright: ignore[reportArgumentType]
        two = second.items[part]  # pyright: ignore[reportArgumentType]
        assert [i.id for i in one] == [i.id for i in two]
        assert [i.order for i in one] == list(range(len(one)))
        assert len({i.id for i in one}) == len(one)
    assert [r.id for r in first.problems] == [r.id for r in second.problems]
    assert len({r.id for r in first.problems}) == len(first.problems)


def test_the_signature_is_stat_only_and_changes_with_a_file(world: Path) -> None:
    ctx = sc.context(world)
    got = ih.instructions(ctx)
    first = COLLECTOR.signature(ctx, got)
    assert COLLECTOR.signature(ctx, got) == first
    assert COLLECTOR.signature(ctx, None) == COLLECTOR.signature(ctx, None)
    path = world / "work" / "parent" / "proj" / "docs" / "words.md"
    put(path, "changed words\n")
    assert COLLECTOR.signature(ctx, got) != first
    before = COLLECTOR.signature(ctx, got)
    put(world / "work" / "parent" / "proj" / ".claude" / "rules" / "new.md")
    assert COLLECTOR.signature(ctx, got) != before


def test_the_collector_has_the_contract_shape() -> None:
    assert COLLECTOR.name == "instructions"
    assert list(COLLECTOR.parts) == ["instructions", "rules"]


# ------------------------------------------------------------ claudeMdExcludes


def with_excludes(tmp: Path, **layers: list[str]) -> Collected:
    """Write claudeMdExcludes into the named layers, then run settings and ours."""
    where = {
        "user": tmp / "home" / ".claude" / "settings.json",
        "project": tmp / "proj" / ".claude" / "settings.json",
        "local": tmp / "proj" / ".claude" / "settings.local.json",
        "managed": tmp / "managed" / "managed-settings.json",
    }
    for name, patterns in layers.items():
        put(where[name], json.dumps({"claudeMdExcludes": patterns}))
    ctx = ctx_for(tmp)
    settings = collect_settings.COLLECTOR.read(ctx, {})
    return COLLECTOR.read(ctx, settings.handoff)


def test_an_excluded_file_is_ignored_loads_nothing_and_is_no_problem(
    tmp_path: Path,
) -> None:
    put(tmp_path / "proj" / "CLAUDE.md", "@extra.md\n")
    put(tmp_path / "proj" / "extra.md")
    put(tmp_path / "proj" / "CLAUDE.local.md")
    got = with_excludes(tmp_path, local=["**/proj/CLAUDE.md"])
    items = by_id(got)
    gone = items["instructions:CLAUDE.md"]
    assert (gone.status, gone.loads, gone.winner) == ("ignored", None, None)
    assert gone.sources[0].status == "ignored"
    assert gone.reason is not None
    assert gone.reason.code == "ignored"
    assert gone.reason.ref_item == "settings:claudeMdExcludes"
    assert gone.reason.params["setting"] == "claudeMdExcludes"
    # An excluded file is not loaded, so its import is not followed.
    assert gone.facts.instruction is not None
    assert gone.facts.instruction.imports == []
    assert "instructions:extra.md" not in items
    assert items["instructions:CLAUDE.local.md"].status == "in_effect"
    assert got.problems == []


def test_exclude_lists_merge_across_layers(tmp_path: Path) -> None:
    put(tmp_path / "home" / ".claude" / "CLAUDE.md")
    put(tmp_path / "proj" / "CLAUDE.md")
    put(tmp_path / "proj" / "CLAUDE.local.md")
    put(tmp_path / "proj" / ".claude" / "CLAUDE.md")
    got = with_excludes(
        tmp_path,
        user=["**/proj/CLAUDE.md"],
        project=["**/proj/.claude/CLAUDE.md"],
        local=["**/CLAUDE.local.md"],
    )
    assert {i.id: i.status for i in got.items["instructions"]} == {
        "instructions:~/.claude/CLAUDE.md": "in_effect",
        "instructions:CLAUDE.md": "ignored",
        "instructions:.claude/CLAUDE.md": "ignored",
        "instructions:CLAUDE.local.md": "ignored",
    }


def test_a_managed_claude_md_cannot_be_excluded(tmp_path: Path) -> None:
    put(tmp_path / "managed" / "CLAUDE.md")
    put(tmp_path / "proj" / "CLAUDE.md")
    got = with_excludes(tmp_path, user=["**"])
    items = by_id(got)
    assert items["instructions:managed/CLAUDE.md"].status == "in_effect"
    assert items["instructions:CLAUDE.md"].status == "ignored"


def test_a_rules_file_can_be_excluded(tmp_path: Path) -> None:
    put(tmp_path / "proj" / ".claude" / "rules" / "a.md", "---\npaths: x/**\n---\n")
    put(tmp_path / "proj" / ".claude" / "rules" / "b.md")
    got = with_excludes(tmp_path, user=["**/rules/a.md"])
    rules = by_id(got, "rules")
    assert rules["rules:.claude/rules/a.md"].status == "ignored"
    assert rules["rules:.claude/rules/a.md"].loads is None
    assert rules["rules:.claude/rules/b.md"].status == "in_effect"
    assert got.problems == []


def test_an_imported_file_can_be_excluded(tmp_path: Path) -> None:
    put(tmp_path / "proj" / "CLAUDE.md", "@docs/a.md\n")
    put(tmp_path / "proj" / "docs" / "a.md", "@b.md\n")
    put(tmp_path / "proj" / "docs" / "b.md")
    got = with_excludes(tmp_path, user=["**/docs/a.md"])
    assert {i.id: i.status for i in got.items["instructions"]} == {
        "instructions:CLAUDE.md": "in_effect",
        "instructions:docs/a.md": "ignored",
    }


def test_no_settings_handoff_means_no_excludes(tmp_path: Path) -> None:
    put(tmp_path / "proj" / "CLAUDE.md")
    for odd in ({}, {"settings": 3}, {"settings": {"layers": object()}}):
        got = COLLECTOR.read(ctx_for(tmp_path), odd)
        assert by_id(got)["instructions:CLAUDE.md"].status == "in_effect"


def test_excluded_patterns_are_matched_as_globs_on_the_absolute_path(
    tmp_path: Path,
) -> None:
    root = tmp_path.resolve()
    put(tmp_path / "proj" / "sub" / "CLAUDE.md")
    put(tmp_path / "proj" / "CLAUDE.md")
    # One star stays inside a folder name, so this misses the nested file.
    got = with_excludes(tmp_path, user=[f"{root}/proj/*/CLAUDE.md"])
    status = {i.id: i.status for i in got.items["instructions"]}
    assert status == {
        "instructions:CLAUDE.md": "in_effect",
        "instructions:sub/CLAUDE.md": "ignored",
    }
    got = with_excludes(tmp_path, user=["proj/CLAUDE.md"])
    assert by_id(got)["instructions:CLAUDE.md"].status == "in_effect"


def test_a_symlink_is_excluded_by_its_link_or_its_target(tmp_path: Path) -> None:
    target = put(tmp_path / "dotfiles" / "shared.md")
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "CLAUDE.md").symlink_to(target)
    by_target = with_excludes(tmp_path, user=["**/dotfiles/shared.md"])
    assert by_id(by_target)["instructions:CLAUDE.md"].status == "ignored"
    by_link = with_excludes(tmp_path, user=["**/proj/CLAUDE.md"])
    assert by_id(by_link)["instructions:CLAUDE.md"].status == "ignored"
