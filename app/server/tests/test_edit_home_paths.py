"""A demo, fixture or e2e server shows real paths with "~" for the home folder.

``main.make_provider`` used to hand the store provider a home folder in real mode only,
so every other server sent a link target or a real path as a bare file name. These
tests build the provider the way ``main`` does, over a copy of the demo with HOME on a
throwaway folder, mount the edit routes over it, and read the preview and the history
the way the page does. Every folder is under ``tmp_path``, outside any git work tree.
"""

import os
import shutil
import sys
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from edit_api_helpers import FakeNow, dump, write_json

import api_edit
import errors
import main
import store_provider
import write_guard
from access import AccessState
from edit_service import EditService

OpenClient = Callable[..., AbstractContextManager[Any]]


@pytest.fixture(autouse=True)
def _edits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(write_guard.STATE, "edits", True)


def _provider(
    tmp_path: Path, demo_build: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[store_provider.StoreProvider, Path, Path]:
    """Return a demo store provider, its Claude folder and the HOME folder."""
    home = (tmp_path / "home").resolve()
    (home / "dotfiles" / "claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    shutil.copytree(demo_build, tmp_path / "demo")
    config = (tmp_path / "demo" / "config").resolve()
    settings = main.Settings(
        port=47000,
        data_dir=tmp_path / "data",
        dist_dir=tmp_path / "dist",
        access_state=AccessState(edits="on"),
        claude_dir=config,
        store_dir=tmp_path / "store",
        demo=True,
        price_fetch=False,
        edits="on",
    )
    provider = main.make_provider(settings)
    assert isinstance(provider, store_provider.StoreProvider)
    return provider, config, home


def test_a_demo_server_hands_the_provider_the_home_folder(
    tmp_path: Path,
    demo_build: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, _config, home = _provider(tmp_path, demo_build, monkeypatch)
    key = provider.projects().projects[0].key
    assert provider.edit_inputs(key).setup.home == home


def test_a_link_into_the_home_shows_its_real_path_with_a_tilde_on_a_demo_server(
    open_client: OpenClient,
    tmp_path: Path,
    demo_build: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, config, home = _provider(tmp_path, demo_build, monkeypatch)
    real = write_json(
        home / "dotfiles" / "claude" / "settings.json", dump({"effortLevel": "low"})
    )
    (config / "settings.json").unlink(missing_ok=True)
    (config / "settings.json").symlink_to(real)
    (config / "routing-dashboard" / "bartab").mkdir(parents=True, exist_ok=True)
    key = provider.projects().projects[0].key
    state = AccessState(edits="on")
    clock = FakeNow()

    def schedule(delay: float, work: Callable[[], None]) -> None:
        del delay, work  # no recheck timer outlives the test

    service = EditService(
        provider, state, clock=clock, scheduler=schedule, secret=b"s" * 32
    )
    app = FastAPI()
    errors.install(app)
    app.include_router(api_edit.build_always_router(provider, state, config, service))
    app.include_router(api_edit.build_edits_router(state, provider, service))
    body = {
        "project": key,
        "op": "set",
        "scope": "user",
        "field": "effortLevel",
        "value": "high",
        "seq": 1,
    }
    with open_client(app) as client:
        shown = client.post("/api/edit/preview", json=body)
        assert shown.status_code == 200, shown.text
        preview = shown.json()
        assert preview["refusal"] is None
        target = preview["target"]
        assert target["link"] is True
        assert target["real_path"] == "~/dotfiles/claude/settings.json"
        user = next(row for row in preview["scopes"] if row["scope"] == "user")
        assert user["real_path"] == "~/dotfiles/claude/settings.json"
        saved = client.post(
            "/api/edit/save",
            json={
                **body,
                "seq": 2,
                "version": preview["version"],
                "request_id": os.urandom(8).hex(),
            },
        )
        assert saved.status_code == 200, saved.text
        history = client.get(f"/api/edit/history?project={key}").json()
    (row,) = history["rows"]
    assert row["scope"] == "user"
    assert row["real_path"] == "~/dotfiles/claude/settings.json"
