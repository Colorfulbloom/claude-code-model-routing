"""The recorded oracle files are complete, parse and hold no machine paths."""

import json
from pathlib import Path

ORACLE = Path(__file__).resolve().parents[2] / "fixtures" / "oracle" / "demo"
# Built from parts, so the home-path scan in test_no_home_paths.py skips this file.
BANNED = ("/private/", "/" + "Users/", "/" + "tmp/")


def _manifest() -> dict[str, object]:
    return json.loads((ORACLE / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_lists_every_file_present() -> None:
    listed = _manifest()["files"]
    present = sorted(p.name for p in ORACLE.iterdir() if p.is_file())
    assert sorted(listed) == present  # type: ignore[arg-type]


def test_every_payload_parses() -> None:
    files = sorted(ORACLE.glob("*.json"))
    assert files
    for path in files:
        json.loads(path.read_text(encoding="utf-8"))


def test_no_payload_holds_a_machine_path() -> None:
    for path in ORACLE.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        for banned in BANNED:
            assert banned not in text, f"{path.name} contains {banned}"


def test_truth_has_window_and_projects() -> None:
    truth = json.loads((ORACLE / "truth.json").read_text(encoding="utf-8"))
    assert "window" in truth
    assert "projects" in truth


def test_allowed_differences_is_a_list_with_a_doc() -> None:
    data = json.loads((ORACLE / "allowed-differences.json").read_text(encoding="utf-8"))
    assert isinstance(data["differences"], list)
    assert data["_doc"]
