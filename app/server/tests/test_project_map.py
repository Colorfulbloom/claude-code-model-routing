"""The project map and the model check in real-mode wiring.

A provider runs over a made-up config folder and a real ingest pass. Listed projects
come from ``routing-dashboard.json``. A transcript cwd the list does not name becomes
an unlisted project, which shows for usage but is never read for settings and never
shows its absolute path.
"""

import json
import os
import sys
import time
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import ingest_helpers as h

import model_check
import project_map
import store_provider
import transcripts
from models import Timeline

Make = Callable[..., store_provider.StoreProvider]


@pytest.fixture
def make(tmp_path: Path) -> Generator[Make]:
    started: list[store_provider.StoreProvider] = []

    def build(
        cwd: str, *, home: str | None = None, listing: object = None
    ) -> store_provider.StoreProvider:
        config = h.Config(tmp_path)
        folder = transcripts._dashed(os.path.realpath(cwd))  # pyright: ignore[reportPrivateUsage]
        config.write(
            config.main(h.S1, folder), [h.assistant(10, "m1", req="r1", cwd=cwd)]
        )
        if listing is not None:
            (config.dir / "routing-dashboard.json").write_text(
                json.dumps(listing), encoding="utf-8"
            )
        made = store_provider.create(
            claude_dir=config.dir,
            store_dir=tmp_path / "store",
            demo=False,
            pace_ms=0,
            price_fetch=False,
            home=home,
        )
        made.start()
        started.append(made)
        return made

    yield build
    for provider in started:
        provider.stop()


def wait_for_projects(provider: store_provider.StoreProvider, name: str) -> list[Any]:
    """Poll until a project called ``name`` shows, dropping the 5 s mapping cache."""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        provider._mapped = None  # pyright: ignore[reportPrivateUsage]
        found = list(provider.projects().projects)
        if any(p.name == name for p in found):
            return found
        time.sleep(0.05)
    pytest.fail("the store never held the project")


def timeline_when_ready(provider: store_provider.StoreProvider, key: str) -> Timeline:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            answer = provider.timeline(key, h.S1, None)
        except Exception:  # noqa: BLE001 - unknown until the first pass lands
            time.sleep(0.05)
            continue
        assert isinstance(answer, Timeline)
        return answer
    pytest.fail("the timeline never answered")


# ------------------------------------------------------------- unlisted: no reads


class Reads:
    """Records the paths opened or listed under one folder while ``on`` is set."""

    def __init__(self, under: Path) -> None:
        self.under = str(under)
        self.on = False
        self.hits: list[str] = []

    def __call__(self, event: str, args: tuple[object, ...]) -> None:
        if not self.on or event not in {"open", "os.listdir", "os.scandir"}:
            return
        target = args[0] if args else None
        if isinstance(target, (str, bytes, Path)):
            text = target.decode() if isinstance(target, bytes) else str(target)
            if text.startswith(self.under):
                self.hits.append(text)


def test_an_unlisted_project_cwd_is_never_read_for_settings(
    make: Make, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "elsewhere" / "secretproj"
    (cwd / ".claude").mkdir(parents=True)
    (cwd / ".claude" / "settings.json").write_text(
        json.dumps({"model": "claude-opus-5-5"}), encoding="utf-8"
    )
    asked: list[Path | None] = []
    real_resolve = model_check.resolve_entries

    def spy(**kwargs: Any) -> Any:
        asked.append(kwargs["project_dir"])
        return real_resolve(**kwargs)

    monkeypatch.setattr(model_check, "resolve_entries", spy)
    provider = make(str(cwd))
    found = wait_for_projects(provider, "secretproj")
    key = next(p.key for p in found if p.name == "secretproj")
    reads = Reads(cwd)
    sys.addaudithook(reads)
    reads.on = True
    try:
        answer = timeline_when_ready(provider, key)
    finally:
        reads.on = False
    assert answer.model_check is not None
    assert asked
    assert all(project_dir is None for project_dir in asked)
    assert reads.hits == []


def test_a_listed_project_is_still_read(
    make: Make, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "listedproj"
    (cwd / ".claude").mkdir(parents=True)
    asked: list[Path | None] = []
    real_resolve = model_check.resolve_entries

    def spy(**kwargs: Any) -> Any:
        asked.append(kwargs["project_dir"])
        return real_resolve(**kwargs)

    monkeypatch.setattr(model_check, "resolve_entries", spy)
    provider = make(
        str(cwd), listing={"projects": [{"name": "Listed", "path": str(cwd)}]}
    )
    found = wait_for_projects(provider, "Listed")
    key = next(p.key for p in found if p.name == "Listed")
    timeline_when_ready(provider, key)
    assert asked
    assert asked[0] == cwd


# ------------------------------------------------------- unlisted: display path


def test_an_unlisted_project_inside_home_shows_a_home_relative_path(
    make: Make, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    cwd = home / "code" / "demoapp"
    cwd.mkdir(parents=True)
    provider = make(str(cwd), home=str(home))
    found = wait_for_projects(provider, "demoapp")
    item = next(p for p in found if p.name == "demoapp")
    assert item.display_path == "~/code/demoapp"


def test_an_unlisted_project_outside_home_shows_its_name_not_its_cwd(
    make: Make, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "other" / "demoapp"
    cwd.mkdir(parents=True)
    provider = make(str(cwd), home=str(home))
    found = wait_for_projects(provider, "demoapp")
    item = next(p for p in found if p.name == "demoapp")
    assert item.display_path == "demoapp"
    for project in found:
        if project.name == "config":  # the implicit launch project, a listed one
            continue
        assert not project.display_path.startswith(("/", "\\"))
        assert str(tmp_path) not in project.display_path


def test_an_unlisted_project_with_no_home_shows_its_name(
    make: Make, tmp_path: Path
) -> None:
    cwd = tmp_path / "plain" / "demoapp"
    cwd.mkdir(parents=True)
    found = wait_for_projects(make(str(cwd)), "demoapp")
    item = next(p for p in found if p.name == "demoapp")
    assert item.display_path == "demoapp"


def test_unlisted_display_with_no_cwd_is_the_name() -> None:
    ctx = project_map.projects.ProjectsContext(config_dir="/c", project_dir="/p")
    assert project_map._unlisted_display(None, "f", ctx) == "f"  # pyright: ignore[reportPrivateUsage]


# ----------------------------------------------------------- listed: home tilde


def test_a_tilde_path_in_the_list_expands_against_home(
    make: Make, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    (home / "code" / "mine" / ".claude").mkdir(parents=True)
    provider = make(
        str(home / "code" / "mine"),
        home=str(home),
        listing={
            "projects": [
                {"name": "Mine", "path": "~/code/mine"},
                {"name": "Home", "path": "~"},
            ]
        },
    )
    found = wait_for_projects(provider, "Mine")
    by_name = {p.name: p for p in found}
    assert by_name["Mine"].display_path == "~/code/mine"
    assert by_name["Mine"].state == "ok"
    assert by_name["Home"].display_path == "~"
    assert by_name["Home"].state != "folder_not_found"


def test_a_tilde_path_with_no_home_is_not_found(make: Make, tmp_path: Path) -> None:
    provider = make(
        str(tmp_path / "x"),
        listing={"projects": [{"name": "Mine", "path": "~/code/mine"}]},
    )
    found = wait_for_projects(provider, "Mine")
    mine = next(p for p in found if p.name == "Mine")
    assert mine.state == "folder_not_found"
    assert mine.display_path == "~/code/mine"
