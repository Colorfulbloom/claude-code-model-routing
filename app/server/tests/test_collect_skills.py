"""The Skills collector (m4-build.md task 7).

Every corpus case's expected.json is the oracle for the part. Crafted folders then cover
the facts, precedence, plugin input in both shapes, front matter, the Couldn't read
state, masking, the body never reaching an answer, the order across two reads and the
signature. Every run reads its own copy inside a temp folder, never a real folder.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import instruction_collect_helpers as ih
import setup_case_helpers as sc

import collect_skills
from collect_plugins import PluginComponents
from models import SetupItem
from setup_contract import Collected

COLLECTOR = collect_skills.COLLECTOR
BODY = "BODY-SENTINEL-NEVER-IN-AN-ANSWER"
NOT_ROOT = os.geteuid() != 0


def skill(name: str, description: str = "A skill.", *extra: str) -> str:
    rows = ["---", f"name: {name}", f"description: {description}", *extra, "---", BODY]
    return "\n".join(rows) + "\n"


def command(description: str = "A command.") -> str:
    return f"---\ndescription: {description}\n---\n{BODY}\n"


def by_id(got: Collected) -> dict[str, SetupItem]:
    return {i.id: i for i in got.items["skills"]}


def put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def mini(tmp_path: Path) -> Path:
    """A scratch tree, with the config folder, the project and the managed folder."""
    sc.scratch(tmp_path, {})
    return tmp_path.resolve()


def read(root: Path, plugins: dict[str, object] | None = None) -> Collected:
    ctx = sc.scratch(root, {})
    return ih.skills(ctx, plugins if plugins is not None else {})


# ---------------------------------------------------------------- the corpus


@pytest.mark.parametrize("case", sc.CASES)
def test_items_match_the_expected_json(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    got = ih.skills(sc.context(root))
    made, wanted = sc.compare_items(got, case, "skills")
    assert made == wanted


@pytest.mark.parametrize("case", sc.CASES)
def test_problems_match_the_expected_json(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    got = ih.skills(sc.context(root))
    made, wanted = sc.compare_problems(got, case, ("skills",))
    assert made == wanted


@pytest.mark.parametrize("case", sc.CASES)
def test_unreadable_files_match_the_expected_json(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    got = ih.skills(sc.context(root))
    _items, listed = ih.expected_part(case, "skills")
    wanted = [(u["file"], u["scope"], u["reason"]) for u in listed]
    assert [(u.file, u.scope, u.reason) for u in got.unreadable] == wanted
    assert {u.part for u in got.unreadable} <= {"skills"}


def test_a_case_with_no_skills_has_no_items(tmp_path: Path, setup_corpus: Path) -> None:
    root = sc.world("empty", tmp_path / "w", setup_corpus)
    got = ih.skills(sc.context(root))
    assert got.items["skills"] == []
    assert got.problems == []
    assert got.unreadable == []


# ---------------------------------------------------------------- item fields


def test_the_facts_of_a_skill_a_command_and_a_plugin_skill(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    items = by_id(ih.skills(sc.context(root)))
    tidy = items["skills:tidy"]
    assert tidy.facts.skill is not None
    assert tidy.facts.skill.invoke == "/tidy"
    assert tidy.facts.skill.namespace is None
    assert tidy.facts.skill.legacy_command is False
    assert tidy.facts.skill.description is not None
    assert tidy.facts.skill.description.text == "Tidy up a messy file."
    assert tidy.facts.skill.description.masked is False
    ship = items["skills:ship"]
    assert ship.facts.skill is not None
    assert ship.facts.skill.legacy_command is True
    assert ship.facts.skill.invoke == "/ship"
    dash = items["skills:routing-dashboard:dashboard"]
    assert dash.facts.skill is not None
    assert dash.facts.skill.invoke == "/routing-dashboard:dashboard"
    assert dash.facts.skill.namespace == "routing-dashboard"
    assert (dash.key, dash.name) == ("dashboard", "dashboard")
    assert dash.read_only_reason is not None
    assert dash.read_only_reason.code == "plugin"
    assert dash.read_only_reason.params == {"plugin": "routing-dashboard"}
    assert [(r.scope, r.visible) for r in dash.reach] == [("plugin", True)]
    assert dash.sources[0].plugin == "routing-dashboard"
    assert items["skills:audit"].read_only_reason is not None
    assert items["skills:audit"].read_only_reason.code == "managed"


def test_every_item_has_the_shared_fields(tmp_path: Path, setup_corpus: Path) -> None:
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    for item in ih.skills(sc.context(root)).items["skills"]:
        assert item.part == "skills"
        assert item.writable is False
        assert item.feature == "core"
        assert item.label_known is True
        assert item.effective is None
        assert item.loads is None
        # Only the skill and command clash (tidy) rests on our reading of the docs.
        assert item.confidence.level == (
            "assumed" if item.id == "skills:tidy" else "documented"
        )
        assert item.not_read is None
        assert item.sources[0].full_path is not None
        assert Path(item.sources[0].full_path).is_absolute()
        assert [r.scope for r in item.reach] == (
            ["plugin"] if item.sources[0].plugin else ["managed", "project", "user"]
        )


def test_the_description_is_masked_and_says_so(mini: Path) -> None:
    put(
        mini / "home" / ".claude" / "skills" / "plain" / "SKILL.md",
        skill("plain", "Does a plain thing"),
    )
    put(
        mini / "home" / ".claude" / "skills" / "bare" / "SKILL.md",
        "---\nname: bare\ndescription: sk-ant-api03-FAKEVALUE\n---\n",
    )
    put(
        mini / "home" / ".claude" / "skills" / "url" / "SKILL.md",
        skill("url", "https://alice:hunter2@example.test/v1"),
    )
    items = by_id(read(mini))
    plain = items["skills:plain"].facts.skill
    assert plain is not None
    assert plain.description is not None
    assert plain.description.masked is False
    bare = items["skills:bare"].facts.skill
    assert bare is not None
    assert bare.description is not None
    assert (bare.description.text, bare.description.masked) == ("hidden", True)
    shown = items["skills:url"].facts.skill
    assert shown is not None
    assert shown.description is not None
    assert shown.description.masked is True
    assert "hunter2" not in shown.description.text


def test_a_skill_with_no_front_matter_takes_its_folder_name(mini: Path) -> None:
    put(mini / "home" / ".claude" / "skills" / "plain" / "SKILL.md", "Just text.\n")
    item = by_id(read(mini))["skills:plain"]
    assert item.status == "in_effect"
    assert (item.sources[0].key, item.sources[0].line) == ("file", None)
    assert item.facts.skill is not None
    assert item.facts.skill.description is None


def test_the_name_in_the_front_matter_wins_over_the_folder(mini: Path) -> None:
    put(
        mini / "home" / ".claude" / "skills" / "folder" / "SKILL.md",
        skill("named"),
    )
    items = by_id(read(mini))
    assert "skills:named" in items
    assert "skills:folder" not in items


def test_front_matter_the_docs_write_is_not_a_problem(mini: Path) -> None:
    put(
        mini / "home" / ".claude" / "skills" / "docs" / "SKILL.md",
        skill(
            "docs",
            "A: colon, in the value".replace(": ", " - "),
            "allowed-tools: Read, Grep",
            "argument-hint: [issue-number]",
            "disable-model-invocation: true",
            "hooks:",
            "  PreToolUse:",
            "    - matcher: Bash",
            "      hooks:",
            "        - type: command",
            "          command: echo hi",
        ),
    )
    got = read(mini)
    assert by_id(got)["skills:docs"].status == "in_effect"
    assert got.problems == []


# ---------------------------------------------------------------- precedence


def test_managed_beats_user_beats_project(mini: Path) -> None:
    put(mini / "managed" / ".claude" / "skills" / "same" / "SKILL.md", skill("same"))
    put(mini / "home" / ".claude" / "skills" / "same" / "SKILL.md", skill("same"))
    put(mini / "proj" / ".claude" / "skills" / "same" / "SKILL.md", skill("same"))
    got = read(mini)
    item = by_id(got)["skills:same"]
    assert [(s.scope, s.status) for s in item.sources] == [
        ("managed", "in_effect"),
        ("user", "overridden"),
        ("project", "overridden"),
    ]
    assert (item.scope, item.winner, item.status) == ("managed", 0, "in_effect")
    assert got.problems == []


def test_a_skill_beats_a_command_of_its_scope(mini: Path) -> None:
    put(mini / "home" / ".claude" / "commands" / "go.md", command())
    put(mini / "home" / ".claude" / "skills" / "go" / "SKILL.md", skill("go"))
    item = by_id(read(mini))["skills:go"]
    assert [(s.file, s.status) for s in item.sources] == [
        ("~/.claude/skills/go/SKILL.md", "in_effect"),
        ("~/.claude/commands/go.md", "overridden"),
    ]
    assert item.facts.skill is not None
    assert item.facts.skill.legacy_command is False


def test_a_skill_and_command_clash_is_assumed_and_a_plain_clash_is_documented(
    mini: Path,
) -> None:
    put(mini / "home" / ".claude" / "commands" / "go.md", command())
    put(mini / "home" / ".claude" / "skills" / "go" / "SKILL.md", skill("go"))
    put(mini / "home" / ".claude" / "skills" / "same" / "SKILL.md", skill("same"))
    put(mini / "proj" / ".claude" / "skills" / "same" / "SKILL.md", skill("same"))
    put(mini / "proj" / ".claude" / "skills" / "solo" / "SKILL.md", skill("solo"))
    items = by_id(read(mini))
    assert items["skills:go"].confidence.level == "assumed"
    assert items["skills:same"].confidence.level == "documented"
    assert items["skills:solo"].confidence.level == "documented"


def test_a_higher_scope_command_beats_a_lower_scope_skill(mini: Path) -> None:
    put(mini / "home" / ".claude" / "commands" / "go.md", command())
    put(mini / "proj" / ".claude" / "skills" / "go" / "SKILL.md", skill("go"))
    item = by_id(read(mini))["skills:go"]
    assert (item.scope, item.sources[0].file) == ("user", "~/.claude/commands/go.md")
    assert item.facts.skill is not None
    assert item.facts.skill.legacy_command is True


def test_a_nested_skill_folder_is_project_scope_and_ranks_after_the_root(
    mini: Path,
) -> None:
    put(mini / "proj" / "pkg" / ".claude" / "skills" / "s" / "SKILL.md", skill("s"))
    put(mini / "proj" / ".claude" / "skills" / "s" / "SKILL.md", skill("s"))
    item = by_id(read(mini))["skills:s"]
    assert [(s.scope, s.file, s.status) for s in item.sources] == [
        ("project", ".claude/skills/s/SKILL.md", "in_effect"),
        ("project", "pkg/.claude/skills/s/SKILL.md", "overridden"),
    ]


def test_two_files_with_one_name_in_one_folder_are_a_problem(mini: Path) -> None:
    base = mini / "proj" / ".claude" / "skills"
    put(base / "a" / "SKILL.md", skill("dup"))
    put(base / "b" / "SKILL.md", skill("dup"))
    got = read(mini)
    item = by_id(got)["skills:dup"]
    assert [(s.file, s.status) for s in item.sources] == [
        (".claude/skills/a/SKILL.md", "in_effect"),
        (".claude/skills/b/SKILL.md", "invalid"),
    ]
    assert [(r.code, r.group, r.line, r.file) for r in got.problems] == [
        ("same_name_in_folder", "wont_load", 2, ".claude/skills/b/SKILL.md")
    ]


def test_overridden_is_never_a_problem(tmp_path: Path, setup_corpus: Path) -> None:
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    got = ih.skills(sc.context(root))
    tidy = by_id(got)["skills:tidy"]
    assert tidy.sources[1].status == "overridden"
    assert got.problems == []


# ---------------------------------------------------------------- front matter


def test_bad_front_matter_is_wont_load_with_the_line(mini: Path) -> None:
    put(
        mini / "home" / ".claude" / "skills" / "bad" / "SKILL.md",
        '---\nname: bad\ndescription: "open\n---\nBody.\n',
    )
    got = read(mini)
    item = by_id(got)["skills:bad"]
    assert (item.status, item.winner) == ("invalid", None)
    assert [(r.code, r.line, r.item_id) for r in got.problems] == [
        ("frontmatter_invalid", 3, "skills:bad")
    ]
    assert got.problems[0].fix.kind == "open_item"


def test_a_fence_that_never_closes_is_invalid_on_line_one(mini: Path) -> None:
    put(mini / "home" / ".claude" / "skills" / "open" / "SKILL.md", "---\nname: open\n")
    got = read(mini)
    assert [(r.code, r.line) for r in got.problems] == [("frontmatter_invalid", 1)]


def test_front_matter_that_is_a_list_is_invalid(mini: Path) -> None:
    put(
        mini / "home" / ".claude" / "skills" / "list" / "SKILL.md",
        "---\n- a\n- b\n---\n",
    )
    assert [r.code for r in read(mini).problems] == ["frontmatter_invalid"]


def test_a_command_with_bad_front_matter_is_invalid(mini: Path) -> None:
    put(
        mini / "home" / ".claude" / "commands" / "oops.md", "---\ndescription: [\n---\n"
    )
    got = read(mini)
    assert by_id(got)["skills:oops"].status == "invalid"
    assert [r.code for r in got.problems] == ["frontmatter_invalid"]


def test_a_folder_with_no_skill_file_is_one_row(mini: Path) -> None:
    put(mini / "proj" / ".claude" / "skills" / "empty" / "notes.txt", "x")
    put(mini / "proj" / ".claude" / "skills" / "loose.md", "not a skill folder")
    got = read(mini)
    assert got.items["skills"] == []
    assert [(r.code, r.item_id, r.file, r.fix.kind) for r in got.problems] == [
        ("skill_no_md", None, ".claude/skills/empty", "copy_path")
    ]


def test_no_reader_gap_row_is_ever_made(mini: Path) -> None:
    """Hyphenated keys fail the strict agent reader, and Claude Code loads them."""
    put(
        mini / "home" / ".claude" / "skills" / "gap" / "SKILL.md",
        "---\nname: gap\nallowed-tools: Read\n---\n",
    )
    assert read(mini).problems == []


# ---------------------------------------------------------------- plugins


def _plugin_tree(root: Path) -> Path:
    base = root / "home" / ".claude" / "plugins" / "cache" / "mk" / "pl" / "1.0.0"
    put(base / "skills" / "one" / "SKILL.md", skill("one"))
    put(base / "skills" / "two" / "SKILL.md", skill("two"))
    put(base / "commands" / "run.md", command())
    return base


def test_plugin_skills_from_the_mapping_shape(mini: Path) -> None:
    base = _plugin_tree(mini)
    got = read(
        mini,
        {
            "skills": [
                {
                    "plugin": "pl@mk",
                    "name": "one",
                    "path": str(base / "skills" / "one"),
                },
                {"plugin": "pl@mk", "name": "two", "path": str(base / "skills")},
            ],
            "commands": [
                {"plugin": "pl@mk", "name": "run", "path": str(base / "commands")}
            ],
        },
    )
    items = by_id(got)
    assert sorted(items) == [
        "skills:pl:one",
        "skills:pl:run",
        "skills:pl:two",
    ]
    assert items["skills:pl:run"].facts.skill is not None
    assert items["skills:pl:run"].facts.skill.invoke == "/pl:run"
    assert items["skills:pl:run"].facts.skill.legacy_command is True
    assert items["skills:pl:one"].sources[0].plugin == "pl"
    # "one" is handed twice, as a folder and inside the root: one source, no problem.
    assert len(items["skills:pl:one"].sources) == 1
    assert got.problems == []


def test_plugin_skills_from_the_components_shape(mini: Path) -> None:
    base = _plugin_tree(mini)
    comp = PluginComponents(
        item_id="plugins:pl@mk",
        plugin_id="pl@mk",
        name="pl",
        root=str(base),
        skills=[str(base / "skills")],
        commands=[str(base / "commands" / "run.md")],
    )
    ctx = sc.scratch(mini, {})
    got = collect_skills.COLLECTOR.read(ctx, {"plugins": [comp]})
    assert sorted(by_id(got)) == ["skills:pl:one", "skills:pl:run", "skills:pl:two"]


def test_a_plugin_skill_never_clashes_with_a_user_skill_of_its_name(
    mini: Path,
) -> None:
    base = _plugin_tree(mini)
    put(mini / "home" / ".claude" / "skills" / "one" / "SKILL.md", skill("one"))
    got = read(
        mini,
        {"skills": [{"plugin": "pl@mk", "name": "one", "path": str(base / "skills")}]},
    )
    items = by_id(got)
    assert items["skills:one"].status == "in_effect"
    assert items["skills:pl:one"].status == "in_effect"
    assert got.problems == []


def test_a_plugin_path_outside_the_plugins_folder_is_not_read_here(mini: Path) -> None:
    other = mini / "elsewhere" / "skills"
    put(other / "x" / "SKILL.md", skill("x"))
    got = read(
        mini,
        {"skills": [{"plugin": "pl@mk", "name": "x", "path": str(other)}]},
    )
    assert got.items["skills"] == []
    assert [(u.reason, u.part, u.scope) for u in got.unreadable] == [
        ("plugin_outside_plugins", "skills", None)
    ]
    assert got.unreadable[0].problem is None
    assert BODY not in ih.dump(got)


def test_odd_plugin_input_is_no_input(mini: Path) -> None:
    ctx = sc.scratch(mini, {})
    for odd in (None, "x", 3, [1, "a"], {"skills": 3}, {"skills": [{"plugin": 1}]}):
        got = collect_skills.COLLECTOR.read(ctx, {"plugins": odd})
        assert got.items["skills"] == []


# ---------------------------------------------------------------- Couldn't read


def _corrupt(root: Path, kind: str, rel: str) -> Collected:
    sc.bc.make_unreadable(root, kind, rel)
    return ih.skills(sc.context(root))


@pytest.fixture
def world(tmp_path: Path, setup_corpus: Path) -> Path:
    return sc.world("typical", tmp_path / "world", setup_corpus)


def test_a_skill_file_that_is_not_utf8_is_couldnt_read(world: Path) -> None:
    got = _corrupt(world, "not_utf8", "home/.claude/skills/tidy/SKILL.md")
    assert [(u.file, u.scope, u.reason, u.part) for u in got.unreadable] == [
        ("~/.claude/skills/tidy/SKILL.md", "user", "not_utf8", "skills")
    ]
    assert "skills:tidy" not in by_id(got)
    # The other skills still read, and the failure is no Won't load row.
    assert "skills:release-check" in by_id(got)
    assert got.problems == []


def test_a_skill_file_over_the_cap_is_couldnt_read(world: Path) -> None:
    got = _corrupt(world, "too_large", "work/parent/proj/.claude/skills/big/SKILL.md")
    assert [(u.reason, u.scope) for u in got.unreadable] == [("too_large", "project")]


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_a_skill_file_at_mode_000_is_couldnt_read(world: Path) -> None:
    got = _corrupt(world, "mode000", "home/.claude/skills/tidy/SKILL.md")
    assert [(u.reason, u.scope) for u in got.unreadable] == [("permission", "user")]
    (world / "home" / ".claude" / "skills" / "tidy" / "SKILL.md").chmod(0o600)


@pytest.mark.skipif(not NOT_ROOT, reason="mode 000 does not stop root")
def test_a_skills_folder_that_will_not_list_is_one_row(world: Path) -> None:
    folder = world / "home" / ".claude" / "skills"
    folder.chmod(0)
    try:
        got = ih.skills(sc.context(world))
    finally:
        folder.chmod(0o700)
    assert [(u.reason, u.part) for u in got.unreadable] == [
        ("folder_unlistable", "skills")
    ]


def test_a_missing_folder_is_not_a_failure(tmp_path: Path, setup_corpus: Path) -> None:
    root = sc.world("empty", tmp_path / "w", setup_corpus)
    assert ih.skills(sc.context(root)).unreadable == []


def test_may_change_follows_the_failed_file(world: Path) -> None:
    got = _corrupt(world, "not_utf8", "home/.claude/skills/tidy/SKILL.md")
    items = by_id(got)
    # A failed user file can change a project skill (user beats project), but not a
    # plugin skill, which has its own namespace.
    assert items["skills:release-check"].may_change is True
    assert items["skills:routing-dashboard:dashboard"].may_change is False


def test_a_failed_project_file_cannot_change_a_user_skill(world: Path) -> None:
    got = _corrupt(world, "too_large", "work/parent/proj/.claude/skills/big/SKILL.md")
    items = by_id(got)
    assert items["skills:tidy"].may_change is False
    assert items["skills:release-check"].may_change is True


# ---------------------------------------------------------------- symlinks


def test_a_single_file_symlink_is_followed_and_shows_its_real_path(mini: Path) -> None:
    target = put(mini / "outside" / "real.md", skill("linked"))
    folder = mini / "home" / ".claude" / "skills" / "linked"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").symlink_to(target)
    got = read(mini)
    item = by_id(got)["skills:linked"]
    assert item.status == "in_effect"
    assert item.real_path is not None
    assert item.real_path == "real.md"  # outside the roots: the last part only
    assert BODY not in ih.dump(got)


def test_a_symlinked_folder_out_of_the_roots_is_not_entered(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("scope-symlink", tmp_path / "w", setup_corpus)
    got = ih.skills(sc.context(root))
    assert got.items["skills"] == []
    assert [(u.file, u.reason) for u in got.unreadable] == [
        ("~/.claude/skills/ext", "outside_scope")
    ]
    assert got.unreadable[0].problem is None
    assert got.problems == []


# ---------------------------------------------------------------- masking and bodies


def test_no_secret_of_the_corpus_reaches_an_answer(
    tmp_path: Path, setup_corpus: Path
) -> None:
    secrets = json.loads((sc.CORPUS / "secrets.json").read_text("utf-8"))
    values = [s["value"] for s in secrets["secrets"] + secrets["never"]]
    assert values
    for case in sc.CASES:
        root = sc.world(case, tmp_path / case, setup_corpus)
        text = ih.dump(ih.skills(sc.context(root)))
        assert [v for v in values if v in text] == [], case


def test_no_body_text_reaches_an_answer(mini: Path) -> None:
    put(mini / "home" / ".claude" / "skills" / "a" / "SKILL.md", skill("a"))
    put(mini / "home" / ".claude" / "commands" / "b.md", command())
    put(
        mini / "proj" / ".claude" / "skills" / "bad" / "SKILL.md",
        f"---\n[\n---\n{BODY}\n",
    )
    got = read(mini)
    assert len(got.items["skills"]) == 3
    assert BODY not in ih.dump(got)


def test_what_a_case_says_is_never_read_is_in_no_answer(
    tmp_path: Path, setup_corpus: Path
) -> None:
    checked = 0
    for case in sc.CASES:
        never = [v for v in sc.expected(case).get("never", []) if v != "hidden"]
        root = sc.world(case, tmp_path / case, setup_corpus)
        text = ih.dump(ih.skills(sc.context(root)))
        for value in never:
            assert value not in text, (case, value)
            checked += 1
    assert checked >= 3


# --------------------------------------------------------- order and the signature


@pytest.mark.parametrize("case", ["typical", "complex", "stress", "broken-skills"])
def test_ids_and_order_are_stable_over_two_reads(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    first = ih.skills(sc.context(root))
    second = ih.skills(sc.context(root))
    assert [i.id for i in first.items["skills"]] == [
        i.id for i in second.items["skills"]
    ]
    assert [i.order for i in first.items["skills"]] == list(
        range(len(first.items["skills"]))
    )
    ids = [i.id for i in first.items["skills"]]
    assert len(ids) == len(set(ids))
    assert [r.id for r in first.problems] == [r.id for r in second.problems]
    assert len({r.id for r in first.problems}) == len(first.problems)


def test_the_signature_is_stat_only_and_changes_with_a_file(world: Path) -> None:
    ctx = sc.context(world)
    got = ih.skills(ctx)
    first = COLLECTOR.signature(ctx, got)
    assert COLLECTOR.signature(ctx, got) == first
    assert COLLECTOR.signature(ctx, None) == COLLECTOR.signature(ctx, None)
    path = world / "home" / ".claude" / "skills" / "tidy" / "SKILL.md"
    put(path, path.read_text("utf-8").replace("Tidy", "Neaten"))
    assert COLLECTOR.signature(ctx, got) != first
    before = COLLECTOR.signature(ctx, got)
    put(world / "home" / ".claude" / "skills" / "fresh" / "SKILL.md", skill("fresh"))
    assert COLLECTOR.signature(ctx, got) != before


def test_the_collector_has_the_contract_shape() -> None:
    assert COLLECTOR.name == "skills"
    assert list(COLLECTOR.parts) == ["skills"]


def test_an_unlisted_project_reads_nothing_under_it(
    tmp_path: Path, setup_corpus: Path
) -> None:
    root = sc.world("scope-unlisted", tmp_path / "w", setup_corpus)
    put(
        root / "work" / "parent" / "proj" / ".claude" / "skills" / "h" / "SKILL.md",
        skill("h"),
    )
    got = ih.skills(sc.context(root))
    assert got.items["skills"] == []
