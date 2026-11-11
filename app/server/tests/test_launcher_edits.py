"""Tests for the launcher's edit switch: ``start --allow-edits`` and the mode line.

The launcher runs as a subprocess in a throwaway checkout under the system temp folder,
with a fake uv and a fake server, exactly as test_launcher.py does (L-979a). Nothing
here touches a real data folder, a real Claude folder or a real server. The fake server
records ``edits`` in its server.json the way serve.py does.
"""

# ruff: noqa: F811 - each test names the reused `tree` fixture as a parameter
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from test_launcher import (  # noqa: F401 - the fixture is reused
    Tree,
    pid_alive,
    tree,  # pyright: ignore[reportUnusedImport]
)

# Launcher tests bind real ports in the 47000 range, so one xdist worker runs them.
pytestmark = pytest.mark.xdist_group("launcher")

SKILL_SESSION = "skill-session"
LINK = "Bar Tab preview: http://127.0.0.1:"


def mode_lines(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("Editing is ")]


def argv_flags(argv: list[str]) -> list[str]:
    return [word for word in argv if word.startswith("--")]


def edits_of(record: dict[str, object] | None) -> object:
    assert record is not None
    return record.get("edits")


# ------------------------------------------------------------------ a fresh start


def test_start_with_the_flag_passes_it_on_and_records_edits_on(tree: Tree) -> None:
    proc = tree.start(None, "--allow-edits")
    assert proc.returncode == 0, proc.stderr
    assert "--allow-edits" in tree.serve_argv()
    assert edits_of(tree.record()) is True
    assert mode_lines(proc.stdout) == ["Editing is on"]
    assert "This link can change your settings files." in proc.stdout
    assert LINK in proc.stdout


def test_a_plain_start_runs_with_edits_off_and_says_so(tree: Tree) -> None:
    proc = tree.start(None)
    assert proc.returncode == 0, proc.stderr
    assert "--allow-edits" not in tree.serve_argv()
    assert edits_of(tree.record()) is False
    assert mode_lines(proc.stdout) == ["Editing is off"]
    assert "can change your settings files" not in proc.stdout


def test_a_preview_skill_argument_list_with_real_and_the_flag(tree: Tree) -> None:
    # The skill runs: --default-project D --session S --real $ARGUMENTS, and
    # $ARGUMENTS holds "--allow-edits" here. An unprefixed option list is a start.
    tree.config.mkdir(parents=True)
    proc = tree.run_real("--no-open", "--allow-edits", session=SKILL_SESSION)
    assert proc.returncode == 0, proc.stderr
    assert not proc.stdout.startswith("error:"), proc.stdout
    argv = tree.real_serve_argv()
    assert "--real" in argv
    assert "--allow-edits" in argv
    assert "--data" not in argv
    record = tree.real_record()
    assert edits_of(record) is True
    assert mode_lines(proc.stdout) == ["Editing is on"]


def test_a_preview_skill_argument_list_with_the_flag_alone(tree: Tree) -> None:
    tree.config.mkdir(parents=True)
    proc = tree.run_real("--allow-edits", "--no-open", session=SKILL_SESSION)
    assert proc.returncode == 0, proc.stderr
    assert edits_of(tree.real_record()) is True


def test_the_flag_works_with_the_other_start_options(tree: Tree) -> None:
    proc = tree.run(
        "start",
        "--allow-edits",
        "--no-open",
        "--fixture",
        "demo",
        session=SKILL_SESSION,
    )
    assert proc.returncode == 0, proc.stderr
    argv = tree.serve_argv()
    assert "--allow-edits" in argv
    assert argv[argv.index("--fixture") + 1] == "demo"


def test_a_preview_skill_argument_list_without_the_flag_has_edits_off(
    tree: Tree,
) -> None:
    tree.config.mkdir(parents=True)
    proc = tree.run_real("--no-open", session=SKILL_SESSION)
    assert proc.returncode == 0, proc.stderr
    assert "--allow-edits" not in tree.real_serve_argv()
    assert edits_of(tree.real_record()) is False
    assert mode_lines(proc.stdout) == ["Editing is off"]


# ------------------------------------------------------------------- the restart


def test_the_flag_restarts_a_server_that_runs_with_edits_off(tree: Tree) -> None:
    first = tree.start("session-a")
    assert first.returncode == 0, first.stderr
    old_pid = tree.pid()
    old_port = int(str(tree.record()["port"]))  # type: ignore[index]
    assert edits_of(tree.record()) is False

    second = tree.start("session-b", "--allow-edits")
    assert second.returncode == 0, second.stderr
    assert "Restarting Bar Tab with editing on." in second.stdout
    assert mode_lines(second.stdout) == ["Editing is on"]
    assert tree.pid() != old_pid
    assert not pid_alive(old_pid)
    assert pid_alive(tree.pid())
    assert edits_of(tree.record()) is True
    assert int(str(tree.record()["port"])) == old_port  # type: ignore[index]
    assert len(tree.serve_runs()) == 2
    assert "--allow-edits" not in tree.serve_argv(0)
    assert "--allow-edits" in tree.serve_argv(1)
    # Both sessions still own the new server, so neither's end stops it early.
    assert sorted(tree.sessions()) == ["session-a", "session-b"]


def test_a_plain_start_beside_a_server_with_edits_on_keeps_it(tree: Tree) -> None:
    assert tree.start("session-a", "--allow-edits").returncode == 0
    pid = tree.pid()
    again = tree.start("session-b")
    assert again.returncode == 0, again.stderr
    assert tree.pid() == pid
    assert len(tree.serve_runs()) == 1
    assert edits_of(tree.record()) is True
    assert mode_lines(again.stdout) == ["Editing is on"]
    assert "Restarting" not in again.stdout


def test_the_flag_beside_a_server_with_edits_on_keeps_it(tree: Tree) -> None:
    assert tree.start("session-a", "--allow-edits").returncode == 0
    pid = tree.pid()
    again = tree.start("session-b", "--allow-edits")
    assert again.returncode == 0, again.stderr
    assert tree.pid() == pid
    assert len(tree.serve_runs()) == 1
    assert "Restarting" not in again.stdout
    assert mode_lines(again.stdout) == ["Editing is on"]


def test_a_plain_start_beside_a_server_with_edits_off_keeps_it(tree: Tree) -> None:
    assert tree.start("session-a").returncode == 0
    pid = tree.pid()
    again = tree.start("session-b")
    assert again.returncode == 0, again.stderr
    assert tree.pid() == pid
    assert mode_lines(again.stdout) == ["Editing is off"]


def test_turning_edits_off_takes_a_stop_then_a_plain_start(tree: Tree) -> None:
    assert tree.start("session-a", "--allow-edits").returncode == 0
    assert tree.run("stop", session="session-a").returncode == 0
    assert tree.record() is None
    proc = tree.start("session-a")
    assert proc.returncode == 0, proc.stderr
    assert edits_of(tree.record()) is False
    assert mode_lines(proc.stdout) == ["Editing is off"]


def test_a_real_server_restarts_into_edits_on_too(tree: Tree) -> None:
    tree.config.mkdir(parents=True)
    first = tree.start_real(SKILL_SESSION)
    assert first.returncode == 0, first.stderr
    old = tree.real_record()
    assert edits_of(old) is False
    second = tree.run_real("--no-open", "--allow-edits", session=SKILL_SESSION)
    assert second.returncode == 0, second.stderr
    new = tree.real_record()
    assert edits_of(new) is True
    assert new is not None
    assert old is not None
    assert new["pid"] != old["pid"]
    assert "--real" in tree.real_serve_argv(1)


def test_a_record_with_no_edits_key_counts_as_off_and_is_restarted(
    tree: Tree,
) -> None:
    first = tree.start("session-a", FAKE_SERVE_EDITS="no_key")
    assert first.returncode == 0, first.stderr
    assert "edits" not in (tree.record() or {})
    assert mode_lines(first.stdout) == ["Editing is off"]
    old_pid = tree.pid()
    second = tree.start("session-b", "--allow-edits")
    assert second.returncode == 0, second.stderr
    assert tree.pid() != old_pid
    assert edits_of(tree.record()) is True


# ------------------------------------------------------------------------- code


def test_code_beside_edits_on_says_the_link_can_edit(tree: Tree) -> None:
    assert tree.start("session-a", "--allow-edits").returncode == 0
    proc = tree.run("code", "--no-open", session="session-a")
    assert proc.returncode == 0, proc.stderr
    assert LINK in proc.stdout
    assert mode_lines(proc.stdout) == ["Editing is on"]
    assert "This link can change your settings files." in proc.stdout


def test_code_beside_edits_off_says_so_and_keeps_the_mode(tree: Tree) -> None:
    assert tree.start("session-a").returncode == 0
    pid = tree.pid()
    proc = tree.run("code", "--no-open", session="session-a")
    assert proc.returncode == 0, proc.stderr
    assert mode_lines(proc.stdout) == ["Editing is off"]
    assert "can change your settings files" not in proc.stdout
    assert tree.pid() == pid
    assert len(tree.serve_runs()) == 1


def test_code_does_not_take_the_flag(tree: Tree) -> None:
    proc = tree.run("code", "--allow-edits")
    assert proc.returncode == 2
    assert "--allow-edits is not an option of code" in proc.stderr
    skill = tree.run("code", "--allow-edits", session=SKILL_SESSION)
    assert skill.returncode == 0
    assert skill.stdout.startswith("error: ")


# ------------------------------------------------------------- refusal and usage


def test_a_server_that_refuses_the_flag_leaves_edits_off_and_the_launcher_says_so(
    tree: Tree,
) -> None:
    proc = tree.start("session-a", "--allow-edits", FAKE_SERVE_EDITS="refuse")
    assert proc.returncode == 0, proc.stderr
    assert edits_of(tree.record()) is False
    assert mode_lines(proc.stdout) == ["Editing is off"]
    lines = proc.stdout.splitlines()
    log = tree.data / "logs" / "server.log"
    refusal = (
        f"Bar Tab turned down --allow-edits for this run. The log at {log} says why."
    )
    assert refusal in lines
    # the refusal comes after the mode line
    assert lines.index("Editing is off") < lines.index(refusal)
    assert "can change your settings files" not in proc.stdout


def test_the_flag_twice_is_a_usage_error(tree: Tree) -> None:
    proc = tree.start(None, "--allow-edits", "--allow-edits")
    assert proc.returncode == 2
    assert "--allow-edits was given twice" in proc.stderr
    assert tree.serve_runs() == []


def test_the_flag_is_not_a_global_option(tree: Tree) -> None:
    proc = tree.run("--allow-edits", "stop")
    # Before the action, an unprefixed list reads "--allow-edits" as start's option,
    # so "stop" is then a word after start.
    assert proc.returncode == 2
    assert tree.serve_runs() == []


def test_help_names_the_flag(tree: Tree) -> None:
    proc = tree.run("--help")
    assert proc.returncode == 0
    assert "[--allow-edits]" in proc.stdout


def test_the_launcher_never_writes_the_mode_into_a_log_or_the_port_file(
    tree: Tree,
) -> None:
    assert tree.start("session-a", "--allow-edits").returncode == 0
    for name in ("port",):
        text = (tree.data / name).read_text()
        assert "edit" not in text.lower()
    record = json.loads((tree.data / "server.json").read_text())
    assert not [key for key in record if "key" in key and key != "mint_secret"]
