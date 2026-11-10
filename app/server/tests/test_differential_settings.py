"""Differential tests: the new Settings and Permissions collectors against the old app's
recorded ``/api/settings`` answers (m4-build.md task 5, section 6).

``app/fixtures/oracle/settings/`` holds what the old ``api_settings.settings`` answered
for each project of the demo build (``demo/``) and for each of the 122 folders of
``tests/fixtures/resolution`` (``resolution/``). This test runs the new collector over
the same input and compares, per case and per key

* the main session's entries (key, masked value, status, scope, file, line, rule id),
  against the item's sources, winner, status, scope, effective value and reason,
* the settings files that exist, with their status,
* the old attention rows, against the To fix rows, through section 6's group mapping,
* the old rows, against the items that exist.

* the old ``agentFile`` entries (the load status of each agent file), against the Agents
  part's ``name`` sources and Won't load rows, in ``agent_status``.

The other agent entries (``agent`` set: model, effort and the rest) belong to the Agents
collector, which the M3 Agents set and Check differential (``test_agent_setup.py``)
compares with the old app. They are not compared here. The old answer has no items for
permissions, output styles and the other
parts (section 6, item 5), so nothing compares those.

Every difference is a ``Diff`` with a kind. ``allowed-differences.json`` lists the kinds
that may differ, each with its reason, plan section and how many diffs it covers. Any
other difference fails with the case, the key and both answers. A listed entry that
covers a different number of diffs fails too, so a stale entry or a silent new
difference shows up.

The fixture folders sit inside the repo, which has a git root, so each is copied to a
temp folder first: no repo-root local file can join in. Nothing here reads real data.
"""

import json
import shutil
import sys
from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_case_helpers as sc

import collect
import collect_agents
import collect_settings
import projects
import resolve
import settings_layers
from models import ProblemRow, SetupItem, SetupSource
from setup_contract import Collected, SetupContext

ORACLE = sc.REPO_ROOT / "app" / "fixtures" / "oracle" / "settings"
RESOLUTION = sc.REPO_ROOT / "tests" / "fixtures" / "resolution"
Row = dict[str, Any]

MANIFEST: Row = json.loads((ORACLE / "manifest.json").read_text(encoding="utf-8"))
CASES: list[Row] = MANIFEST["cases"]
CASE_IDS = [str(c["file"]).removesuffix(".json") for c in CASES]

NOT_ROWS = ("settingsFile", "agentFile", "rulesFile")
ALWAYS = ("model", "effortLevel")
SHELL_LABEL = resolve.LABEL_SHELL
LAYER_SCOPE = {
    "user": "user",
    "project": "project",
    "local": "project_local",
    "managed": "managed",
    "flag": "command_line",
    "cli": "command_line",
}
FILE_SCOPES = ("managed", "project_local", "project", "user")  # top wins
# Section 6, item 2: the old attention status and the To fix group and code it maps to.
ATTENTION = {
    "unknown": ("cant_tell", "unknown"),
    "lowered": ("not_as_set", "lowered"),
    "ignored": ("not_as_set", "ignored"),
    "invalid": ("wont_load", "value_invalid"),
}
FILE_CODES = ("json_invalid", "not_object", "managed_invalid")
# The old rule of an agent file whose status differs, and the Diff kind it gets.
AGENT_KINDS = {
    "agent-file-same-name-one-tree": "agent-same-name",
    "agent-file-unknown-field": "agent-unknown-field",
}
FileKey = tuple[str, str | None, str]  # layer, display path, status


# ---------------------------------------------------------------- the diff


@dataclass(frozen=True)
class Diff:
    """One difference between the old answer and the new one."""

    kind: str
    key: str
    field: str
    old: object
    new: object

    def text(self, case: str) -> str:
        return (
            f"{case} | {self.key} | {self.field} | {self.kind}\n"
            f"    old {self.old!r}\n    new {self.new!r}"
        )


def _allowed_doc() -> Row:
    doc: Row = json.loads(
        (ORACLE / "allowed-differences.json").read_text(encoding="utf-8")
    )
    return doc


def _allowed_for(case: str) -> dict[str, Row]:
    """Return {kind: entry} of the allowed entries that cover a case."""
    return {
        str(e["kind"]): e
        for e in _allowed_doc()["differences"]
        if e["cases"] == "*" or case in e["cases"]
    }


# ---------------------------------------------------------------- the new side


def _json(path: Path) -> Row:
    if not path.is_file():
        return {}
    data: Row = json.loads(path.read_text("utf-8"))
    return data


def _read(ctx: SetupContext, flags: list[str], cli: object) -> Collected:
    """Run the collector, feeding the resolver the session's flags and --settings.

    The server never sees a flag (section 6, item 6). A fixture folder with flags in its
    ``session.json`` still feeds the resolver, so those entries compare as recorded.
    The seam leaves ``home`` and ``root`` alone, so entry paths stay absolute and the
    scope shows them.
    """
    real = settings_layers.resolver_entries

    def seam(collected: dict[str, Any], plan: str | None, **kw: Any) -> Any:
        return real(collected, plan, flags=flags, cli_settings=cli, **kw)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings_layers, "resolver_entries", seam)
        return collect_settings.COLLECTOR.read(ctx, {})


def _resolution_context(folder: Path) -> tuple[SetupContext, list[str], object]:
    session = _json(folder / "session.json")
    ctx = SetupContext(
        project_key=folder.name,
        config_dir=folder / "config",
        home=None,
        project_dir=folder / "project",
        managed_dir=folder / "managed",
        shell_env=dict(session.get("shell_env") or {}),
        plan=_json(folder / "dashboard.json").get("plan"),
    )
    raw: list[Any] = session.get("flags") or []
    flags = [str(f) for f in raw]
    return ctx, flags, collect.mask(session.get("cli_settings"))


def _demo_context(root: Path, key: str) -> SetupContext:
    listing = projects.load(
        projects.ProjectsContext(
            config_dir=str(root / "config"),
            project_dir=str(root / "project"),
            root=str(root),
        )
    )
    project = listing.find(key)
    assert project is not None, key
    session = _json(root / "session.json")
    return SetupContext(
        project_key=key,
        config_dir=root / "config",
        home=None,
        project_dir=Path(project.path),
        managed_dir=root / "managed",
        shell_env=dict(session.get("shell_env") or {}),
        plan=listing.plan,
    )


# ---------------------------------------------------------------- the comparison


def _main_rows(old: Row) -> dict[str, list[Row]]:
    rows: dict[str, list[Row]] = {}
    for entry in old["entries"]:
        if entry["scope"] == "main" and entry["key"] not in NOT_ROWS:
            rows.setdefault(entry["key"], []).append(entry)
    return rows


def _text(value: object) -> str:
    return settings_layers.json_text(value)


class _Compare:
    """Compares one recorded answer with one new read and collects the diffs."""

    def __init__(
        self, old: Row, got: Collected, rel: str, agents: Collected | None = None
    ) -> None:
        self.old = old
        self.got = got
        self.agents_got = agents  # the Agents part's read, or None to skip agents
        self.rel = rel  # the project folder, relative to the fixture root
        self.diffs: list[Diff] = []
        self.layers: settings_layers.Layers = got.handoff["settings"]["layers"]  # pyright: ignore[reportIndexIssue,reportUnknownMemberType,reportUnknownVariableType]
        self.items = {i.key: i for i in got.items["settings"]}

    def add(self, kind: str, key: str, field: str, old: object, new: object) -> None:
        self.diffs.append(Diff(kind, key, field, old, new))

    # ------------------------------------------------------------ paths and scopes

    def new_file(self, old_file: object) -> str | None:
        """Map an old display path (relative to the fixture root) to the new one.

        Section 6, item 4. The old answer shows ``config/settings.json`` and
        ``project/.claude/settings.json``. The new one shows ``~/config/settings.json``
        and ``.claude/settings.json``. A managed file and the session labels stay.
        """
        if not isinstance(old_file, str) or old_file.startswith("session.json"):
            return None
        if old_file.startswith(self.rel + "/"):
            return old_file[len(self.rel) + 1 :]
        if old_file.startswith("config/"):
            return "~/" + old_file
        return old_file

    def old_scope(self, entry: Row) -> str:
        layer = entry["layer"]
        if layer != "env":
            return LAYER_SCOPE[layer]
        shown = self.new_file(entry["file"])
        if shown is None:
            return "shell"
        if shown.startswith("~/"):
            return "user"
        if shown.startswith("managed/"):
            return "managed"
        return "project_local" if shown.endswith("settings.local.json") else "project"

    # ------------------------------------------------------------ rows and items

    def run(self) -> list[Diff]:
        if self.old["state"] == "missing_folder" and not self.old["entries"]:
            self.missing_folder()
            return self.diffs
        self.rows()
        self.plain_keys()
        self.files()
        self.attention()
        self.file_problems()
        self.unreadable()
        self.agent_status()
        return self.diffs

    def missing_folder(self) -> None:
        """A listed project whose folder is gone.

        The old route answers with no entries and no files, so it says nothing about
        the user and managed scopes. The new Settings part still reads those two. Its
        project scopes must stay empty.
        """
        for item in self.items.values():
            for src in item.sources:
                if src.scope in ("project", "project_local"):
                    self.add("project-scope", item.key, "sources", None, src.scope)
        shown = sum(1 for item in self.items.values() if item.sources)
        self.add("missing-folder", str(self.old["project"]), "items", 0, shown)

    def plain_keys(self) -> None:
        """Check the keys the old answer has no main row for against its agent rows.

        A key such as ``subagentPromptCacheTtl`` has only agent rows in the old answer.
        When a shell variable or a flag wins every agent's row, a settings file value
        is beaten. The item's status is the status of what runs, so it reads in effect,
        but each file source reads overridden and the effective value is the winner's.
        """
        old_rows = _main_rows(self.old)
        for key, item in self.items.items():
            if key in old_rows:
                continue
            by_agent: dict[str, list[Row]] = {}
            for e in self.old["entries"]:
                if e["scope"] == "agent" and e["key"] == key:
                    by_agent.setdefault(str(e["agent"]), []).append(e)
            for agent, entries in by_agent.items():
                top = next((e for e in entries if e["status"] in resolve.WINNING), None)
                if top is None or top["layer"] not in ("env", "flag", "cli"):
                    continue
                kept = [
                    s.status
                    for s in item.sources
                    if s.scope in FILE_SCOPES and s.status != "overridden"
                ]
                shown = None if item.effective is None else item.effective.value
                wrong_value = top["value"] != collect.HIDDEN and (
                    shown is None or shown.text != _text(top["value"])
                )
                if kept or wrong_value:
                    self.add(
                        "plain-key-beaten",
                        key,
                        "sources",
                        f"{agent}: {top['layer']} {top.get('via', '')} wins".strip(),
                        {"file statuses": kept, "effective": shown and shown.text},
                    )
                    break

    def rows(self) -> None:
        old_rows = _main_rows(self.old)
        for key, entries in old_rows.items():
            sets = [e for e in entries if e["layer"] != "default"]
            item = self.items.get(key)
            if item is None:
                kind = (
                    "default-only-row"
                    if not sets and key not in ALWAYS
                    else "missing-item"
                )
                self.add(kind, key, "item", [e["status"] for e in entries], None)
                continue
            self.item(key, entries, sets, item)
        for key, item in self.items.items():
            if key not in old_rows:
                self.add("plain-key", key, "item", None, item.id)

    def item(
        self, key: str, entries: list[Row], sets: list[Row], item: SetupItem
    ) -> None:
        win = next((e for e in entries if e["status"] in resolve.WINNING), None)
        set_win = win is not None and win["layer"] != "default"
        self.sources(key, sets, item)
        want = sets.index(win) if set_win and win in sets else None
        if item.winner != want:
            self.add("winner", key, "winner", want, item.winner)
        want_scope = self.old_scope(win) if set_win and win is not None else None
        if item.scope != want_scope:
            self.add("scope", key, "scope", want_scope, item.scope)
        status, driving = self.driving(entries, win, set_win=set_win)
        if item.status != status:
            self.add("status", key, "status", status, item.status)
        reason = item.reason
        if reason is None or reason.code != item.status:
            self.add("reason-code", key, "reason.code", item.status, reason)
        rule = driving.get("rule_id") if driving is not None else None
        if reason is None or reason.rule_id != rule:
            self.add(
                "rule-id",
                key,
                "reason.rule_id",
                rule,
                None if reason is None else reason.rule_id,
            )
        self.effective(key, win, item)

    @staticmethod
    def driving(
        entries: list[Row], win: Row | None, *, set_win: bool
    ) -> tuple[str, Row | None]:
        """Return the status the item should read and the entry that gives its rule."""
        if set_win and win is not None:
            return str(win["status"]), win
        excluded = [e for e in entries if e["status"] in resolve.EXCLUDING]
        if excluded:
            invalid = next((e for e in excluded if e["status"] == "invalid"), None)
            return (
                "invalid" if invalid is not None else "ignored"
            ), invalid or excluded[0]
        return (str(win["status"]) if win is not None else "unknown"), win

    def effective(self, key: str, win: Row | None, item: SetupItem) -> None:
        got = item.effective
        if got is None:
            self.add("effective", key, "effective", "present", None)
            return
        if win is None:
            want_origin, shown = "unknown", None
        elif win["status"] == "lowered":
            want_origin, shown = "cap", win.get("becomes")
        elif win["layer"] == "default":
            want_origin, shown = "default", win["value"]
        else:
            want_origin = "unknown" if win["status"] == "unknown" else "set"
            shown = win["value"]
            if win.get("merged") is not None and shown != win["merged"]:
                # A list key merges across files. What runs is the merged list, and
                # the winner's own list is only its part.
                if got.value is None or got.value.text != _text(win["merged"]):
                    self.add(
                        "effective-merged",
                        key,
                        "effective.value",
                        _text(win["merged"]),
                        None if got.value is None else got.value.text,
                    )
                shown = got.value.text if got.value is not None else None
        if got.origin != want_origin:
            self.add("effective", key, "effective.origin", want_origin, got.origin)
        if shown is None:
            if got.value is not None:
                self.add("effective", key, "effective.value", None, got.value.text)
        elif got.value is None:
            self.add("effective", key, "effective.value", shown, None)
        else:
            self.value(
                key, "effective.value", shown, got.value.text, masked=got.value.masked
            )

    def value(
        self, key: str, field: str, old: object, new: str, *, masked: bool
    ) -> None:
        """Compare an old masked value with the new masked text."""
        if old == collect.HIDDEN:
            if not masked:
                self.add("value-visible", key, field, old, new)
        elif new != _text(old):
            self.add("value", key, field, _text(old), new)

    # ------------------------------------------------------------ sources

    def sources(self, key: str, sets: list[Row], item: SetupItem) -> None:
        if len(sets) != len(item.sources):
            self.add(
                "sources",
                key,
                "count",
                [(e["layer"], e["file"], e.get("line")) for e in sets],
                [(s.scope, s.file, s.line) for s in item.sources],
            )
            return
        for at, (entry, src) in enumerate(zip(sets, item.sources, strict=True)):
            self.source(key, f"sources[{at}]", entry, src, item)

    def source(
        self, key: str, where: str, entry: Row, src: SetupSource, item: SetupItem
    ) -> None:
        if src.scope != (scope := self.old_scope(entry)):
            self.add("scope", key, where + ".scope", scope, src.scope)
        if src.file != (shown := self.new_file(entry.get("file"))):
            self.add("file", key, where + ".file", shown, src.file)
        if src.line != entry.get("line"):
            self.add("line", key, where + ".line", entry.get("line"), src.line)
        if src.status != entry["status"]:
            kind = (
                "ignored-beaten"
                if entry["status"] == "ignored"
                and src.status == "overridden"
                and self.beaten(src, item)
                else "status"
            )
            self.add(kind, key, where + ".status", entry["status"], src.status)
        if src.value is None:
            if entry["value"] is not None:
                self.add("value", key, where + ".value", entry["value"], None)
        else:
            self.value(
                key,
                where + ".value",
                entry["value"],
                src.value.text,
                masked=src.value.masked,
            )

    @staticmethod
    def beaten(src: SetupSource, item: SetupItem) -> bool:
        """True when a file scope above this source holds the item's winning value."""
        if item.winner is None or src.scope not in FILE_SCOPES:
            return False
        top = item.sources[item.winner].scope
        return top in FILE_SCOPES and FILE_SCOPES.index(top) < FILE_SCOPES.index(
            src.scope
        )

    # ------------------------------------------------------------ files

    def files(self) -> None:
        old: Counter[FileKey] = Counter(
            (str(f["layer"]), self.new_file(f["path"]), str(f["status"]))
            for f in self.old["files"]
        )
        new: Counter[FileKey] = Counter(
            (
                f.layer,
                f.display,
                "unparsed" if f.state in ("json_invalid", "not_object") else f.state,
            )
            for f in self.layers.files
        )
        for lost in sorted((old - new).elements(), key=str):
            self.add("files", str(lost[1]), "files", lost, None)
        for extra in sorted((new - old).elements(), key=str):
            self.add("files", str(extra[1]), "files", None, extra)
        for file in self.layers.files:
            if file.state in ("json_invalid", "not_object"):
                self.add(
                    "file-unparsed",
                    file.display,
                    "files.status",
                    "unparsed",
                    file.state,
                )

    def file_problems(self) -> None:
        """Each old settingsFile entry is a Won't load row for its file."""
        rows = [
            p for p in self.got.problems if p.part == "settings" and p.item_id is None
        ]
        used: set[int] = set()
        for entry in self.old["entries"]:
            if entry["key"] != "settingsFile":
                continue
            shown = self.new_file(entry["file"])
            found = next(
                (
                    at
                    for at, p in enumerate(rows)
                    if at not in used and p.file == shown and p.group == "wont_load"
                ),
                None,
            )
            if found is None:
                self.add("file-problem", str(shown), "problem", entry["status"], None)
                continue
            used.add(found)
            row = rows[found]
            if row.code not in FILE_CODES:
                self.add("file-problem", str(shown), "code", FILE_CODES, row.code)
            want = entry.get("line")
            if row.line != want:
                # Python 3.13 reports a trailing comma on the line before the closing
                # brace, where 3.9 (the recorder) reports the closing brace.
                near = (
                    isinstance(want, int)
                    and isinstance(row.line, int)
                    and want - row.line == 1
                )
                kind = "json-error-line" if near else "file-problem-line"
                self.add(kind, str(shown), "line", want, row.line)
        for at, row in enumerate(rows):
            if at not in used:
                self.add("file-problem", str(row.file), "problem", None, row.code)

    def unreadable(self) -> None:
        old = sorted(
            str(self.new_file(f["path"]))
            for f in self.old["files"]
            if f["status"] == "unreadable"
        )
        new = sorted(u.file for u in self.got.unreadable)
        if old != new:
            self.add("unreadable", "files", "unreadable", old, new)

    # ------------------------------------------------------------ agent load status

    def new_agent_status(self) -> dict[str, str]:
        """Return {display path: status} of what the Agents part says of each file.

        A file that names an agent has a ``name`` source on its item, and its status is
        the load status. A file with no usable name has a Won't load row, shown here as
        ``problem:<code>``.
        """
        assert self.agents_got is not None
        found: dict[str, str] = {}
        for item in self.agents_got.items["agents"]:
            for src in item.sources:
                if src.key == "name" and src.file is not None:
                    found[src.file] = src.status
        for row in self.agents_got.problems:
            if row.part == "agents" and row.item_id is None and row.file is not None:
                found[row.file] = f"problem:{row.code}"
        return found

    def agent_status(self) -> None:
        """Compare each old agent file's status with the Agents part's load status.

        The old answer has one ``agentFile`` entry per file, its status the load status
        (``in_effect``, ``overridden``, ``ignored`` or ``unknown``). The new side keeps
        that status on the item's ``name`` source. Kinds, one per cause, so each can
        carry its own reason in ``allowed-differences.json``.
        """
        if self.agents_got is None:
            return
        new = self.new_agent_status()
        seen: set[str] = set()
        for entry in self.old["entries"]:
            if entry["key"] != "agentFile":
                continue
            shown = str(self.new_file(entry["file"]))
            seen.add(shown)
            got = new.get(shown)
            if got is None:
                self.add("agent-missing", shown, "agent.status", entry["status"], None)
            elif got != entry["status"]:
                self.add(
                    self.agent_kind(entry, got),
                    shown,
                    "agent.status",
                    entry["status"],
                    got,
                )
        for shown, got in sorted(new.items()):
            if shown not in seen:
                self.add("agent-extra", shown, "agent.status", None, got)

    @staticmethod
    def agent_kind(entry: Row, got: str) -> str:
        """Name a status difference by the old rule that gave it."""
        if got == "problem:agent_not_md":
            return "agent-not-md"
        if got.startswith("problem:"):
            return "agent-load-problem"
        return AGENT_KINDS.get(str(entry.get("rule_id")), "agent-status")

    # ------------------------------------------------------------ attention

    def attention(self) -> None:
        """Compare the old attention rows with the To fix rows of the Settings part."""
        old_rows: list[tuple[tuple[str, str, str, str | None, int | None], Row]] = []
        for group in self.old["attention"]:
            status = group["status"]
            if status not in ATTENTION:  # overridden never counts (section 6, item 2)
                continue
            for row in group["rows"]:
                entry = self.old["entries"][row["entry"]]
                if row["route"]["agent"] != "@main" or entry["key"] in NOT_ROWS:
                    continue
                kind, code = ATTENTION[status]
                old_rows.append(
                    (
                        (
                            kind,
                            code,
                            entry["key"],
                            self.new_file(entry.get("file")),
                            entry.get("line"),
                        ),
                        entry,
                    )
                )
        new_rows = Counter(self.problem_tuple(p) for p in self.settings_problems())
        for tup, entry in old_rows:
            if new_rows[tup] > 0:
                new_rows[tup] -= 1
                continue
            self.add(self.missing_kind(tup, entry), tup[2], "attention", tup, None)
        for tup in sorted((+new_rows).elements(), key=str):
            self.add("attention-extra", tup[2], "attention", None, tup)

    def settings_problems(self) -> list[ProblemRow]:
        return [
            p
            for p in self.got.problems
            if p.part == "settings" and p.item_id is not None
        ]

    @staticmethod
    def problem_tuple(row: ProblemRow) -> tuple[str, str, str, str | None, int | None]:
        key = (row.item_id or "").removeprefix("settings:")
        return (row.group, row.code, key, row.file, row.line)

    def missing_kind(
        self, tup: tuple[str, str, str, str | None, int | None], entry: Row
    ) -> str:
        """Name an old attention row the new answer has no row for."""
        if entry["status"] == "unknown" and entry["layer"] == "default":
            return "default-unknown"
        if (
            entry["status"] == "ignored"
            and entry["layer"] == "env"
            and entry.get("value") == ""
        ):
            return "ignored-empty-variable"
        item = self.items.get(tup[2])
        if entry["status"] == "ignored" and item is not None:
            for src in item.sources:
                if (src.file, src.line, src.status) == (
                    tup[3],
                    tup[4],
                    "overridden",
                ) and self.beaten(src, item):
                    return "ignored-beaten"
        return "attention-missing"


def compare(
    old: Row, got: Collected, rel: str, agents: Collected | None = None
) -> list[Diff]:
    """Return every difference between a recorded answer and a new read.

    ``agents`` is the Agents part's read of the same input. Without it the agent load
    statuses are not compared.
    """
    return _Compare(old, got, rel, agents).run()


# ---------------------------------------------------------------- the cases


@dataclass(frozen=True)
class Run:
    """One recorded answer, the new read of the same input and the project's path."""

    old: Row
    got: Collected
    rel: str
    agents: Collected


@pytest.fixture(scope="module")
def runs(demo_build: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Run]:
    """Run the new collector on every recorded case."""
    copy = tmp_path_factory.mktemp("resolution") / "resolution"
    shutil.copytree(RESOLUTION, copy, symlinks=True)
    out: dict[str, Run] = {}
    for case in CASES:
        name = str(case["file"]).removesuffix(".json")
        old: Row = json.loads((ORACLE / case["file"]).read_text(encoding="utf-8"))
        if case["kind"] == "demo":
            ctx = _demo_context(demo_build.resolve(), str(case["project"]))
            rel, flags, cli = str(old["path_display"]), [], None
        else:
            ctx, flags, cli = _resolution_context(copy / str(case["folder"]))
            rel = "project"
        agents = collect_agents.COLLECTOR.read(ctx, {})
        out[name] = Run(old, _read(ctx, flags, cli), rel, agents)
    return out


@pytest.fixture(scope="module")
def results(runs: dict[str, Run]) -> dict[str, list[Diff]]:
    """Return the diffs per case."""
    return {name: compare(r.old, r.got, r.rel, r.agents) for name, r in runs.items()}


@pytest.mark.parametrize("case", CASE_IDS)
def test_new_answer_equals_the_old_one_but_for_the_allowed_differences(
    case: str, results: dict[str, list[Diff]]
) -> None:
    allowed = _allowed_for(case)
    left = [
        d
        for d in results[case]
        if d.kind not in allowed and (case, d.kind) not in KNOWN_WRONG
    ]
    assert left == [], "\n" + "\n".join(d.text(case) for d in left)


# New-side answers that look wrong. They are not allowed differences: each stays a
# failing check, marked as an expected failure so the suite stays green. When the
# collector is fixed the strict marker turns it into a failure, and the entry goes.
KNOWN_WRONG: dict[tuple[str, str], str] = {}


@pytest.mark.parametrize(
    ("case", "kind"),
    [
        pytest.param(
            case,
            kind,
            id=f"{case}-{kind}",
            marks=pytest.mark.xfail(strict=True, reason=reason),
        )
        for (case, kind), reason in sorted(KNOWN_WRONG.items())
    ],
)
def test_known_wrong_new_answers(
    case: str, kind: str, results: dict[str, list[Diff]]
) -> None:
    found = [d for d in results[case] if d.kind == kind]
    assert found == [], "\n" + "\n".join(d.text(case) for d in found)


def _bounds(count: object) -> tuple[int, int]:
    """Return the (least, most) number of diffs an allowed entry covers."""
    if isinstance(count, int):
        return count, count
    assert isinstance(count, list)
    low, high = count  # pyright: ignore[reportUnknownVariableType]
    return int(low), int(high)  # pyright: ignore[reportUnknownArgumentType]


def test_every_allowed_difference_covers_exactly_the_diffs_it_lists(
    results: dict[str, list[Diff]],
) -> None:
    seen: Counter[str] = Counter()
    for case, diffs in results.items():
        allowed = _allowed_for(case)
        seen.update(d.kind for d in diffs if d.kind in allowed)
    bad: list[str] = []
    for entry in _allowed_doc()["differences"]:
        low, high = _bounds(entry["count"])
        found = seen[str(entry["kind"])]
        if not low <= found <= high:
            bad.append(f"{entry['kind']}: found {found}, listed {entry['count']}")
    assert bad == [], "allowed-differences.json counts differ:\n" + "\n".join(bad)


def test_every_allowed_difference_names_a_reason_and_a_plan_section() -> None:
    doc = _allowed_doc()
    kinds: list[str] = []
    for entry in doc["differences"]:
        for field in ("id", "kind", "reason", "plan_ref"):
            assert isinstance(entry.get(field), str), entry
            assert entry[field].strip(), entry
        _bounds(entry["count"])
        assert entry["cases"] == "*" or isinstance(entry["cases"], list), entry
        kinds.append(entry["kind"])
    assert len(kinds) == len(set(kinds)), "a kind is listed twice"
    for entry in doc["mappings"]:
        for field in ("id", "applies", "reason", "plan_ref"):
            assert isinstance(entry.get(field), str), entry
            assert entry[field].strip(), entry
    ids = [e["id"] for e in doc["differences"] + doc["mappings"]]
    assert len(ids) == len(set(ids)), "an id is listed twice"


PROBE = "resolution/agent-effort-flag-no-frontmatter"  # a user model, line 2


def _probe_kinds(runs: dict[str, Run], change: Callable[[Row], None]) -> set[str]:
    """Return the diff kinds after a change to the probe case's old answer."""
    run = runs[PROBE]
    old = deepcopy(run.old)
    change(old["entries"][0])
    assert old["entries"][0]["key"] == "model"
    return {d.kind for d in compare(old, run.got, run.rel)}


def test_the_probe_case_has_no_diff_but_the_listed_kinds(runs: dict[str, Run]) -> None:
    run = runs[PROBE]
    assert {d.kind for d in compare(run.old, run.got, run.rel)} <= {
        "default-only-row",
        "default-unknown",
    }


def _set(**fields: Any) -> Callable[[Row], None]:
    """Return a change that sets fields on an old entry."""

    def change(entry: Row) -> None:
        entry.update(fields)

    return change


@pytest.mark.parametrize(
    ("kind", "change"),
    [
        ("value", _set(value="claude-haiku-5-5")),
        ("status", _set(status="overridden")),
        ("line", _set(line=9)),
        ("file", _set(file="project/.claude/settings.json")),
        ("scope", _set(layer="project")),
        ("rule-id", _set(rule_id="model-other-rule")),
    ],
    ids=["value", "status", "line", "file", "scope", "rule-id"],
)
def test_the_comparison_reports_a_changed_old_entry(
    kind: str, change: Callable[[Row], None], runs: dict[str, Run]
) -> None:
    assert kind in _probe_kinds(runs, change)


def _agent_diffs(runs: dict[str, Run], change: Callable[[Row], None]) -> list[Diff]:
    """Return the agent diffs after a change to the old agentFile entry of a case."""
    run = runs["resolution/agent-project-over-user"]
    old = deepcopy(run.old)
    for entry in old["entries"]:
        if entry["key"] == "agentFile" and entry["layer"] == "user":
            change(entry)
    return [
        d
        for d in compare(old, run.got, run.rel, run.agents)
        if d.field == "agent.status"
    ]


def test_an_agent_case_with_no_change_has_no_agent_diff(runs: dict[str, Run]) -> None:
    assert _agent_diffs(runs, _set()) == []


def test_the_comparison_reports_a_changed_old_agent_status(
    runs: dict[str, Run],
) -> None:
    got = _agent_diffs(runs, _set(status="in_effect"))
    assert [(d.kind, d.old, d.new) for d in got] == [
        ("agent-status", "in_effect", "overridden")
    ]


def test_the_comparison_reports_an_old_agent_file_the_new_side_lacks(
    runs: dict[str, Run],
) -> None:
    got = _agent_diffs(runs, _set(file="config/agents/gone.md"))
    assert {d.kind for d in got} == {"agent-missing", "agent-extra"}


def test_the_comparison_reports_a_dropped_old_file(runs: dict[str, Run]) -> None:
    run = runs[PROBE]
    old = deepcopy(run.old)
    old["files"] = []
    assert "files" in {d.kind for d in compare(old, run.got, run.rel)}


def test_a_hidden_old_value_needs_a_masked_new_one(runs: dict[str, Run]) -> None:
    kinds = _probe_kinds(runs, _set(value=collect.HIDDEN))
    assert "value-visible" in kinds


def test_the_manifest_covers_127_cases() -> None:
    assert len([c for c in CASES if c["kind"] == "demo"]) == 5
    assert len([c for c in CASES if c["kind"] == "resolution"]) == 122
    assert len(CASES) == 127


def test_the_manifest_names_the_old_commit_and_the_placeholder() -> None:
    assert len(MANIFEST["old_commit"]) == 40
    assert MANIFEST["path_placeholder"]["placeholder"] == "/work/settings"


def test_every_listed_file_exists_and_no_payload_holds_a_machine_path() -> None:
    banned = ("/private/", "/" + "Users/", "/" + "tmp/", "/var/")
    on_disk = sorted(p.relative_to(ORACLE).as_posix() for p in ORACLE.rglob("*.json"))
    assert sorted(MANIFEST["files"]) == on_disk
    for name in on_disk:
        text = (ORACLE / name).read_text(encoding="utf-8")
        for bad in banned:
            assert bad not in text, f"{name} contains {bad}"
