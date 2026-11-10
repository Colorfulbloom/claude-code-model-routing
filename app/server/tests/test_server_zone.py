"""Tests for the server's zone, on fake paths and a fake environment."""

import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import main
import server_zone
import store_provider

PARIS = "Europe/Paris"


def link(tmp_path: Path, target: str) -> Path:
    """Make a symlink named like /etc/localtime that points at ``target``."""
    path = tmp_path / "localtime"
    path.symlink_to(target)
    return path


def test_a_valid_tz_variable_wins_over_the_symlink(tmp_path: Path) -> None:
    found = server_zone.machine_zone(
        {"TZ": "Asia/Tokyo"}, link(tmp_path, "/usr/share/zoneinfo/" + PARIS)
    )
    assert found.key == "Asia/Tokyo"


def test_a_leading_colon_in_tz_is_dropped(tmp_path: Path) -> None:
    assert server_zone.machine_zone({"TZ": ":Asia/Tokyo"}, tmp_path / "none").key == (
        "Asia/Tokyo"
    )


@pytest.mark.parametrize("bad", ["", "Not/AZone", "../../etc/passwd", "EST5EDT4", ":"])
def test_an_invalid_tz_falls_back_to_the_symlink(tmp_path: Path, bad: str) -> None:
    found = server_zone.machine_zone(
        {"TZ": bad}, link(tmp_path, "/usr/share/zoneinfo/" + PARIS)
    )
    assert found.key == PARIS


@pytest.mark.parametrize(
    "target",
    [
        "/usr/share/zoneinfo/" + PARIS,
        "/var/db/timezone/zoneinfo/" + PARIS,
        "../usr/share/zoneinfo/" + PARIS,
        "/etc/zoneinfo/" + PARIS,
    ],
)
def test_the_symlink_target_after_zoneinfo_is_the_zone(
    tmp_path: Path, target: str
) -> None:
    assert server_zone.machine_zone({}, link(tmp_path, target)).key == PARIS


@pytest.mark.parametrize(
    "target",
    ["/usr/share/zoneinfo/Not/AZone", "/somewhere/else", "/usr/share/zoneinfo/"],
)
def test_a_symlink_that_names_no_zone_gives_utc(tmp_path: Path, target: str) -> None:
    assert server_zone.machine_zone({}, link(tmp_path, target)).key == "UTC"


def test_no_variable_and_no_link_gives_utc(tmp_path: Path) -> None:
    assert server_zone.machine_zone({}, tmp_path / "missing").key == "UTC"
    plain = tmp_path / "plain"
    plain.write_text("not a link", encoding="utf-8")
    assert server_zone.machine_zone({}, plain).key == "UTC"


def write_session(folder: Path, body: object) -> None:
    (folder / "session.json").write_text(json.dumps(body), encoding="utf-8")


def test_a_build_names_its_zone_in_session_json(tmp_path: Path) -> None:
    write_session(
        tmp_path, {"tz": "America/New_York", "now": "2026-10-30T22:00:00+00:00"}
    )
    assert server_zone.session_zone(tmp_path).key == "America/New_York"


@pytest.mark.parametrize("body", [{}, {"tz": 5}, {"tz": "Nope/Nope"}, {"tz": ""}, [1]])
def test_a_build_with_no_usable_zone_is_utc(tmp_path: Path, body: object) -> None:
    write_session(tmp_path, body)
    assert server_zone.session_zone(tmp_path).key == "UTC"


def test_a_build_with_no_session_file_or_a_broken_one_is_utc(tmp_path: Path) -> None:
    assert server_zone.session_zone(tmp_path).key == "UTC"
    (tmp_path / "session.json").write_text("{not json", encoding="utf-8")
    assert server_zone.session_zone(tmp_path).key == "UTC"


def make(
    tmp_path: Path, *, demo: bool, tz: ZoneInfo | None = None
) -> store_provider.StoreProvider:
    build = tmp_path / "build"
    (build / "config").mkdir(parents=True, exist_ok=True)
    write_session(build, {"tz": PARIS})
    return store_provider.create(
        claude_dir=build / "config",
        store_dir=tmp_path / "store",
        demo=demo,
        pace_ms=0,
        price_fetch=False,
        tz=tz,
    )


def test_create_takes_the_zone_from_a_demo_build_or_the_argument(
    tmp_path: Path,
) -> None:
    assert make(tmp_path, demo=True)._tz.key == PARIS  # pyright: ignore[reportPrivateUsage]
    # a build that is not a demo or flow build names no zone, and a given one wins
    assert make(tmp_path, demo=False)._tz.key == "UTC"  # pyright: ignore[reportPrivateUsage]
    given = ZoneInfo("Asia/Tokyo")
    assert make(tmp_path, demo=True, tz=given)._tz is given  # pyright: ignore[reportPrivateUsage]


def test_the_settings_zone_reaches_the_provider(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    settings = main.Settings(
        port=1,
        data_dir=tmp_path / "data",
        dist_dir=tmp_path / "dist",
        claude_dir=tmp_path / "config",
        store_dir=tmp_path / "store",
        tz=ZoneInfo(PARIS),
        price_fetch=False,
    )
    provider = main.make_provider(settings)
    assert isinstance(provider, store_provider.StoreProvider)
    assert provider._tz.key == PARIS  # pyright: ignore[reportPrivateUsage]
