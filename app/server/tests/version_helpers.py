"""Helpers for the version gap tests: a scenario that reports a chosen version."""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from conftest import PORT

import fixture_provider
import main
from access import AccessState

# The four installed cases of the brief, and an older one: (version the scenario
# reports, whether a rules gap shows).
CASES: list[tuple[str, bool]] = [
    ("", False),
    ("abc", False),
    ("2.1.302", False),
    ("2.1.310", True),
    ("2.1.200", False),
]


def scenario_settings(
    tmp_path: Path, dist_dir: Path, version: str
) -> tuple[main.Settings, AccessState]:
    """Return settings for the demo fixture scenario with ``claude_version`` set.

    Args:
        tmp_path: A folder outside every repo, where the scenario copy goes.
        dist_dir: A built-page folder.
        version: The Claude Code version the scenario reports.

    Returns:
        The settings and the access state that holds the read key.
    """
    folder = tmp_path / "m0"
    shutil.copytree(fixture_provider.DEFAULT_FIXTURES_DIR, folder)
    scenario = json.loads((folder / "demo.json").read_text(encoding="utf-8"))
    scenario["claude_version"] = version
    (folder / "demo.json").write_text(json.dumps(scenario), encoding="utf-8")
    state = AccessState()
    settings = main.Settings(
        port=PORT,
        data_dir=tmp_path / "data",
        dist_dir=dist_dir,
        fixture="demo",
        fixtures_dir=folder,
        access_state=state,
    )
    return settings, state
