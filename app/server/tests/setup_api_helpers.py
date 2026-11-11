"""Helpers for the Setup answer tests: a corpus case or the overlaid demo as an API.

``request_of`` turns a ``SetupContext`` into the ``SetupRequest`` the service answers.
``Api`` is a running app over a ``FixtureProvider`` with a setup world, and ``served``
opens one. ``everything`` joins every string an answer holds, so a secret test can
search all of it at once.
"""

import json
import shutil
import sys
import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import setup_case_helpers as sc
from conftest import INDEX_HTML, PORT, _open  # pyright: ignore[reportPrivateUsage]

import fixture_provider
import main
import problems
import setup_answers
from access import AccessState
from setup_contract import SetupContext

JSON_HEADERS = {"Accept-Encoding": "identity"}


def request_of(  # noqa: PLR0913 - one keyword per piece of a request
    ctx: SetupContext,
    *,
    listed: bool | None = None,
    version: str = "",
    usage: setup_answers.SetupUsage | None = None,
    transcripts: problems.Transcripts | None = None,
    claude_version: str = "",
) -> setup_answers.SetupRequest:
    """Return a request for ``ctx``. ``listed`` defaults to "there is a project"."""
    return setup_answers.SetupRequest(
        project=ctx.project_key,
        ctx=ctx,
        listed=ctx.project_dir is not None if listed is None else listed,
        version=version,
        as_of=None,
        usage=lambda: usage,
        transcripts=lambda: transcripts or problems.Transcripts(),
        claude_version=claude_version,
    )


@dataclass
class Api:
    """A running app that serves a setup world."""

    client: Any
    headers: dict[str, str]
    provider: fixture_provider.FixtureProvider

    def get(self, path: str) -> Any:
        return self.client.get(path, headers=self.headers)

    def ok(self, path: str) -> Any:
        reply = self.get(path)
        assert reply.status_code == 200, reply.text
        return reply.json()


@contextmanager
def served(world: fixture_provider.SetupWorld, base: Path) -> Generator[Api]:
    """Serve ``world`` through the real app, on a wall clock."""
    dist = base / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    state = AccessState()
    provider = fixture_provider.FixtureProvider("demo", time.time, None, world)
    settings = main.Settings(
        port=PORT,
        data_dir=base / "data",
        dist_dir=dist,
        access_state=state,
        provider=provider,
    )
    with _open(main.create_app(settings)) as client:
        yield Api(client, {"X-Bartab-Key": state.read_key, **JSON_HEADERS}, provider)


_WORLDS: dict[str, SetupContext] = {}
_DEMO: dict[str, Path] = {}


def materialized(factory: pytest.TempPathFactory, case: str) -> SetupContext:
    """Return the context of a corpus case, materialized once per process.

    The copy sits in the pytest temp folder, outside every repo (fact T-c826). Treat it
    as read only. A test that damages a file makes its own copy with ``fresh``.
    """
    if case not in _WORLDS:
        root = sc.world(case, factory.mktemp(f"world-{case}") / "w", sc.CORPUS)
        _WORLDS[case] = sc.context(root)
    return _WORLDS[case]


def fresh(factory: pytest.TempPathFactory, case: str) -> Path:
    """Materialize a corpus case into a folder of its own and return its root."""
    return sc.world(case, factory.mktemp(f"fresh-{case}") / "w", sc.CORPUS)


def _skip_transcripts(folder: str, names: list[str]) -> list[str]:
    return [n for n in names if n == "projects" and Path(folder).name == "config"]


def overlaid_demo(factory: pytest.TempPathFactory, demo_build: Path) -> Path:
    """Return a copy of the demo build (without transcripts) with the overlay applied.

    Built once per process. Treat it as read only.
    """
    if "demo" not in _DEMO:
        out = factory.mktemp("overlaid") / "demo"
        shutil.copytree(demo_build, out, ignore=_skip_transcripts)
        # The builder wrote absolute project paths into the list, so they point at the
        # original. Move them to the copy.
        listing = out / "config" / "routing-dashboard.json"
        listing.write_text(
            listing.read_text(encoding="utf-8").replace(
                str(demo_build.resolve()), str(out.resolve())
            ),
            encoding="utf-8",
        )
        _DEMO["demo"] = out
        fixture_provider.demo_world(out)  # applies the overlay in place
    return _DEMO["demo"]


def strings_of(value: object) -> Iterator[str]:
    """Yield every string in a JSON value, keys included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        for key, item in mapping.items():
            yield str(key)
            yield from strings_of(item)
    elif isinstance(value, list):
        for item in cast("list[object]", value):
            yield from strings_of(item)


def everything(*answers: object) -> str:
    """Join the JSON text of several answers into one string."""
    return "\n".join(json.dumps(a, sort_keys=True) for a in answers)
