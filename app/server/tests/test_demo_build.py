"""The demo build fixture produces transcripts and a truth file."""

from pathlib import Path


def test_demo_build_has_transcripts_and_truth(demo_build: Path) -> None:
    assert (demo_build / "truth.json").is_file()
    assert any(demo_build.rglob("*.jsonl"))
