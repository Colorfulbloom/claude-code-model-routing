"""Scan the Python sources for home path prefixes (sample paths start at /work/)."""

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
# Built in pieces so this file does not contain the prefixes it bans.
NEEDLES = ("/Us" + "ers/", "/ho" + "me/")


def _sources() -> list[Path]:
    found: list[Path] = []
    for folder in ("server", "bin"):
        found.extend(sorted((APP_ROOT / folder).rglob("*.py")))
    return [p for p in found if ".venv" not in p.parts and "__pycache__" not in p.parts]


def test_the_scan_finds_the_server_sources() -> None:
    names = {p.name for p in _sources()}
    assert {"gate.py", "main.py", "test_no_home_paths.py"} <= names


def test_no_source_uses_a_home_path_prefix() -> None:
    hits = [
        f"{path.relative_to(APP_ROOT)}:{number}"
        for path in _sources()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if any(needle in line for needle in NEEDLES)
    ]
    assert hits == []
