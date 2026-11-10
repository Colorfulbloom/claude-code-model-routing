"""The masking sweep: no secret leaves the server in a route answer, log or error.

``corpus/secrets.json`` lists every value planted in the corpus. ``secrets`` are values
that sit in a file the setup half reads and must come out masked. ``never`` are values
in places it must not read at all (auto memory, dropped keys of the home file). The
sweep asks every setup route for every corpus case and for the overlaid demo, and
searches the answers, the log records and the error bodies for each value. It also
checks that no answer carries a body text, a working folder or an absolute path outside
a ``full_path`` field (``EmptyInfo.target`` and ``ProblemFix.target`` carry one by
contract).
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_api_helpers as sah
import setup_case_helpers as sc

import claude_json
import fixture_provider
import setup_answers
from models import SETUP_PARTS

SECRETS = json.loads((sc.CORPUS / "secrets.json").read_text(encoding="utf-8"))
VALUES = [(row["case"], row["value"]) for row in SECRETS["secrets"] + SECRETS["never"]]
# Fields that hold an absolute path by contract. ``real_path`` is not one: a symlink's
# target shows as a display path, and one outside the roots shows its last part only.
PATH_FIELDS = {"full_path", "target"}
ABSOLUTE = re.compile(
    r"(?<![\w.~])/(?:private|var|Users|tmp|work|home|Volumes)/[\w./-]+"
)


def routes(project: str) -> list[str]:
    parts = [f"/api/setup/{part}?project={project}" for part in SETUP_PARTS]
    return [f"/api/setup?project={project}", f"/api/problems?project={project}", *parts]


def paths_outside_path_fields(value: Any, key: str = "") -> list[str]:
    """Return every absolute path found in a string that is not in a path field."""
    found: list[str] = []
    if isinstance(value, str):
        if key not in PATH_FIELDS:
            found += ABSOLUTE.findall(value)
    elif isinstance(value, dict):
        for k, v in value.items():  # pyright: ignore[reportUnknownVariableType]
            found += paths_outside_path_fields(v, str(k))  # pyright: ignore[reportUnknownArgumentType]
    elif isinstance(value, list):
        for v in value:  # pyright: ignore[reportUnknownVariableType]
            found += paths_outside_path_fields(v, key)
    return found


@pytest.mark.parametrize("case", sc.CASES)
def test_no_secret_in_any_route_answer_log_or_error_of_a_case(
    case: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    claude_json.clear_cache()
    world = fixture_provider.corpus_world(case, tmp_path / "w")
    values = [v for c, v in VALUES if c == case]
    with caplog.at_level(logging.DEBUG), sah.served(world, tmp_path) as api:
        answers = [api.ok(route) for route in routes("proj")]
        errors = [
            api.get("/api/setup/nope?project=proj").text,
            api.get("/api/setup?project=nope").text,
            api.get("/api/setup").text,
        ]
    text = sah.everything(*answers, *errors) + "\n".join(
        r.getMessage() for r in caplog.records
    )
    leaked = [v for v in values if v in text]
    assert leaked == [], case
    for answer in answers:
        assert paths_outside_path_fields(answer) == [], case


def test_no_secret_anywhere_in_the_demo_answers(
    tmp_path_factory: pytest.TempPathFactory,
    demo_build: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    demo = sah.overlaid_demo(tmp_path_factory, demo_build)
    base = tmp_path_factory.mktemp("mask-demo")
    world = fixture_provider.demo_world(demo)
    values = [v for _, v in VALUES] + ["FAKEDEMOENV", "FAKEDEMOHEADER"]
    with caplog.at_level(logging.DEBUG), sah.served(world, base) as api:
        answers = [
            api.ok(route) for key in sorted(world.contexts) for route in routes(key)
        ]
    text = sah.everything(*answers) + "\n".join(r.getMessage() for r in caplog.records)
    assert [v for v in values if v in text] == []
    for answer in answers:
        assert paths_outside_path_fields(answer) == []


def test_the_secrets_file_plants_something_to_find() -> None:
    # An empty list would pass the sweep for nothing.
    assert len(SECRETS["secrets"]) >= 15
    assert len(SECRETS["never"]) >= 3
    assert all(len(v) >= 8 for _, v in VALUES)


def test_a_masked_value_says_it_is_masked_and_keeps_no_part_of_the_secret(
    tmp_path: Path,
) -> None:
    case = "complex"
    claude_json.clear_cache()
    world = fixture_provider.corpus_world(case, tmp_path / "w")
    with sah.served(world, tmp_path) as api:
        items = api.ok("/api/setup/mcp?project=proj")["items"]
    masked = [
        value
        for item in items
        for value in sah.strings_of(item["facts"])
        if "masked" in value.lower()
    ]
    assert masked
    for _, secret in [(c, v) for c, v in VALUES if c == case]:
        assert not any(secret[:6] in text for text in sah.strings_of(items))


def test_a_collector_failure_logs_the_type_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    ctx = fixture_provider.corpus_world("complex", tmp_path / "w").contexts["proj"]

    def boom(_ctx: Any, _handoff: Any) -> Any:
        msg = f"cannot read {ctx.home}/.claude.json with token {VALUES[0][1]}"
        raise RuntimeError(msg)

    monkeypatch.setattr(setup_answers._BY_NAME["claude_json"], "read", boom)  # pyright: ignore[reportPrivateUsage]
    with caplog.at_level(logging.DEBUG):
        bundle = setup_answers.build_bundle(sah.request_of(ctx))
    assert bundle.failed
    text = "\n".join(r.getMessage() + str(r.exc_info) for r in caplog.records)
    assert VALUES[0][1] not in text
    assert str(ctx.home) not in text
