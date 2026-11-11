"""Tests for ``GET /api/rules`` over the fixture scenario and the demo build."""

import json
import shutil
import sys
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import version_helpers as vh
from conftest import PORT

import main
import rules_reference
from access import AccessState
from model_catalog import RULES_PATH

OpenClient = Callable[..., AbstractContextManager[Any]]


def _rules() -> list[dict[str, Any]]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))["rules"]


def _reasons_absent(body: Any) -> None:
    text = json.dumps(body)
    for rule in _rules():
        assert rule["reason"] not in text


def test_get_rules_in_fixture_mode(client: Any, key_headers: dict[str, str]) -> None:
    reply = client.get("/api/rules", headers=key_headers)
    assert reply.status_code == 200
    body = reply.json()
    assert set(body) == {
        "server_time",
        "etag",
        "unchanged",
        "installed",
        "checked_on",
        "rules",
    }
    assert body["unchanged"] is False
    assert body["installed"] == "2.1.310"
    ids = [r["rule_id"] for r in body["rules"]]
    assert ids == sorted(r["rule_id"] for r in _rules())
    expected = rules_reference.build_answer(None, datetime.now(UTC))
    assert body["checked_on"] == expected.checked_on
    assert set(body["rules"][0]) == {
        "rule_id",
        "key",
        "scope",
        "combine",
        "layer_order",
        "confidence",
        "verified_on",
        "due",
        "outcomes",
        "quotes",
        "experiment",
    }
    sources = {r["rule_id"]: r for r in _rules()}
    for row in body["rules"]:
        seen: list[str] = []
        for condition in sources[row["rule_id"]]["conditions"]:
            if condition["status"] not in seen:
                seen.append(condition["status"])
        assert row["outcomes"] == seen, row["rule_id"]
    # The demo reports 2.1.310 and the rules were checked on 2.1.302.
    assert all(r["due"] for r in body["rules"])
    _reasons_absent(body)


def test_the_etag_round_trip(client: Any, key_headers: dict[str, str]) -> None:
    first = client.get("/api/rules", headers=key_headers).json()
    again = client.get(
        "/api/rules", params={"etag": first["etag"]}, headers=key_headers
    )
    assert again.status_code == 200
    short = again.json()
    assert set(short) == {"server_time", "etag", "unchanged"}
    assert short["unchanged"] is True
    assert short["etag"] == first["etag"]
    stale = client.get("/api/rules", params={"etag": "stale"}, headers=key_headers)
    assert stale.json()["unchanged"] is False
    assert stale.json()["etag"] == first["etag"]


def test_a_bad_or_repeated_etag_is_refused(
    client: Any, key_headers: dict[str, str]
) -> None:
    assert client.get("/api/rules?etag=%20", headers=key_headers).status_code == 422
    repeated = client.get("/api/rules?etag=a&etag=b", headers=key_headers)
    assert repeated.status_code == 400
    assert repeated.json() == {"code": "bad_request", "path": ["query", "etag"]}


def test_the_route_needs_the_read_key(client: Any, key_headers: dict[str, str]) -> None:
    assert client.get("/api/rules").status_code == 401
    assert (
        client.get("/api/rules", headers={"X-Bartab-Key": "wrong"}).status_code == 401
    )
    assert client.get("/api/rules", headers=key_headers).status_code == 200


@pytest.mark.parametrize(
    ("version", "installed", "due"),
    [
        ("", None, False),
        ("abc", "abc", False),
        ("2.1.302", "2.1.302", False),
        ("2.1.310", "2.1.310", True),
        ("2.1.200", "2.1.200", False),
    ],
)
def test_installed_and_due_for_each_version(  # noqa: PLR0913, PLR0917 - fixtures
    open_client: OpenClient,
    tmp_path: Path,
    dist_dir: Path,
    version: str,
    installed: str | None,
    due: bool,
) -> None:
    settings, state = vh.scenario_settings(tmp_path, dist_dir, version)
    with open_client(main.create_app(settings)) as client:
        reply = client.get("/api/rules", headers={"X-Bartab-Key": state.read_key})
        body = reply.json()
    assert reply.status_code == 200
    assert body["installed"] == installed
    assert {r["due"] for r in body["rules"]} == {due}
    _reasons_absent(body)


def test_the_etag_changes_with_the_installed_version(
    open_client: OpenClient, tmp_path: Path, dist_dir: Path
) -> None:
    etags: list[str] = []
    for index, version in enumerate(("2.1.302", "2.1.310")):
        settings, state = vh.scenario_settings(tmp_path / str(index), dist_dir, version)
        with open_client(main.create_app(settings)) as client:
            reply = client.get("/api/rules", headers={"X-Bartab-Key": state.read_key})
            etags.append(reply.json()["etag"])
    assert etags[0] != etags[1]


def test_get_rules_in_demo_store_mode(
    open_client: OpenClient, tmp_path: Path, dist_dir: Path, demo_build: Path
) -> None:
    shutil.copytree(demo_build, tmp_path / "demo")
    state = AccessState()
    settings = main.Settings(
        port=PORT,
        data_dir=tmp_path / "data",
        dist_dir=dist_dir,
        access_state=state,
        claude_dir=tmp_path / "demo" / "config",
        store_dir=tmp_path / "store",
        demo=True,
        price_fetch=False,
    )
    headers = {"X-Bartab-Key": state.read_key}
    with open_client(main.create_app(settings)) as client:
        body = client.get("/api/rules", headers=headers).json()
        app_body = client.get("/api/app", headers=headers).json()
    assert body["installed"] == "2.1.310"
    assert body["installed"] == app_body["claude_version"]
    assert all(r["due"] for r in body["rules"])
    assert app_body["rules_version_gap"] == {
        "installed": "2.1.310",
        "checked_on": body["checked_on"],
        "due": len(body["rules"]),
    }
    _reasons_absent(body)
