"""The settings recorder gives the same bytes twice (m4-build.md task 5).

``app/oracle/record.py --only settings`` builds the demo, asks the old ``/api/settings``
route in process for each project and each resolver folder, and writes one payload per
case. Two runs into two temp folders must write the same files with the same bytes. The
whole run takes about a second, so it needs no ``slow`` marker.

The committed payloads are not compared byte for byte. They come from the system
Python (3.9), and one payload holds text that depends on the interpreter (the line of a
trailing comma error). The manifest of a fresh run must list the same cases and files.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_case_helpers as sc

RECORD = sc.REPO_ROOT / "app" / "oracle" / "record.py"
COMMITTED = sc.REPO_ROOT / "app" / "fixtures" / "oracle" / "settings"
OLD_COMMIT_REF = "ad32428"


def _have_old_commit() -> bool:
    done = subprocess.run(  # noqa: S603
        ["git", "cat-file", "-e", f"{OLD_COMMIT_REF}^{{commit}}"],  # noqa: S607
        cwd=sc.REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return done.returncode == 0


pytestmark = pytest.mark.skipif(
    not _have_old_commit(),
    reason=f"the manifest names commit {OLD_COMMIT_REF}, which this clone lacks",
)


def _record(out: Path) -> None:
    subprocess.run(  # noqa: S603
        [sys.executable, str(RECORD), "--only", "settings", "--settings-out", str(out)],
        check=True,
        timeout=120,
        capture_output=True,
        cwd=sc.REPO_ROOT,
    )


def _files(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


@pytest.fixture(scope="module")
def two_runs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    first = tmp_path_factory.mktemp("settings-record") / "one"
    second = tmp_path_factory.mktemp("settings-record") / "two"
    _record(first)
    _record(second)
    return first, second


def test_two_runs_write_the_same_files_with_the_same_bytes(
    two_runs: tuple[Path, Path],
) -> None:
    one, two = (_files(p) for p in two_runs)
    assert sorted(one) == sorted(two)
    assert [n for n in one if one[n] != two[n]] == []


def test_a_run_writes_one_payload_per_case_and_lists_them(
    two_runs: tuple[Path, Path],
) -> None:
    folder = two_runs[0]
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    names = [c["file"] for c in manifest["cases"]]
    assert len(names) == 127
    assert sorted([*names, "allowed-differences.json", "manifest.json"]) == sorted(
        manifest["files"]
    )
    assert sorted(_files(folder)) == sorted(manifest["files"])


def test_a_run_lists_the_same_cases_as_the_committed_manifest(
    two_runs: tuple[Path, Path],
) -> None:
    fresh = json.loads((two_runs[0] / "manifest.json").read_text(encoding="utf-8"))
    kept = json.loads((COMMITTED / "manifest.json").read_text(encoding="utf-8"))
    assert fresh["cases"] == kept["cases"]
    assert fresh["files"] == kept["files"]
    assert fresh["old_commit"] == kept["old_commit"]
    assert fresh["build_args"] == kept["build_args"]


def test_a_run_never_writes_a_machine_path(two_runs: tuple[Path, Path]) -> None:
    banned = ("/private/", "/" + "Users/", "/" + "tmp/", "/var/")
    for name, data in _files(two_runs[0]).items():
        text = data.decode("utf-8")
        for bad in banned:
            assert bad not in text, f"{name} contains {bad}"
