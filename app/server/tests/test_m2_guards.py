"""M2 test guards: the real Claude folder is out of reach and HOME is a temp folder."""

import os
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest


def test_home_is_a_temp_folder(fake_home: Path) -> None:
    assert os.environ["HOME"] == str(fake_home)
    assert os.environ["CLAUDE_CONFIG_DIR"] == str(fake_home / ".claude")


def test_opening_the_real_claude_folder_fails(
    real_config_prefixes: tuple[str, ...],
) -> None:
    if not real_config_prefixes:
        pytest.skip("no HOME at import")
    target = real_config_prefixes[0].rstrip(os.sep) + os.sep + "nope.json"
    with pytest.raises(RuntimeError, match="real-data guard"):
        open(target, encoding="utf-8")  # noqa: PTH123, SIM115


def test_flow_build_writes_the_scenario(flow_build: Callable[[str], Path]) -> None:
    out = flow_build("empty")
    assert (out / "flow.json").is_file()
    assert (out / "session.json").is_file()


@pytest.mark.parametrize("call", ["listdir", "scandir", "stat", "exists", "sqlite"])
def test_listing_or_statting_the_real_claude_folder_fails(
    real_config_prefixes: tuple[str, ...], call: str
) -> None:
    if not real_config_prefixes:
        pytest.skip("no HOME at import")
    folder = real_config_prefixes[0].rstrip(os.sep)
    actions: dict[str, Callable[[], object]] = {
        "listdir": lambda: os.listdir(folder),  # noqa: PTH208 - the audit event under test
        "scandir": lambda: list(os.scandir(folder)),
        "stat": lambda: os.stat(folder),  # noqa: PTH116
        "exists": lambda: Path(folder).exists(),
        "sqlite": lambda: sqlite3.connect(
            f"file:{folder}{os.sep}x.sqlite?mode=ro", uri=True
        ),
    }
    with pytest.raises(RuntimeError, match="real-data guard"):
        actions[call]()


def test_bytecode_is_not_written_beside_old_app_modules() -> None:
    import sys

    assert sys.dont_write_bytecode
    assert os.environ["PYTHONDONTWRITEBYTECODE"] == "1"
