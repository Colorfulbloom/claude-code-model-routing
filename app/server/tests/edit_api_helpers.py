"""Shared helpers for the edit API tests (``test_edit_api_*.py``).

One ``Api`` is one throwaway machine under ``tmp_path``: a config folder, a project (and
optionally a second one), the routers mounted on a bare FastAPI app, and a writer with a
recording scheduler (so no timer thread outlives a test) and a clock the test moves. The
gate is not in front, because ``test_edit_gate.py`` covers it. The one test that needs
real keys builds the full app itself. Nothing here touches the real Claude folder.
"""

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI

import api_edit
import edit_preview
import errors
from access import AccessState
from edit_preview import EditInputs
from edit_service import EditService
from edit_store import EditStore
from fixture_provider import FixtureProvider
from models import EditsMode, Project, ProjectList
from provider import UnknownProjectError
from setup_contract import SetupContext

PROJECT = "edit-project"
OTHER = "other-project"
FIELD = "effortLevel"
OpenClient = Callable[..., AbstractContextManager[Any]]


class FakeNow:
    """A clock the test moves by hand. Calling it gives an aware UTC time."""

    def __init__(self) -> None:
        self.now = datetime(2026, 11, 11, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class EditProvider(FixtureProvider):
    """A fixture provider that also says where its projects' files are."""

    def __init__(self, entries: dict[str, EditInputs]) -> None:
        super().__init__("demo")
        self._entries = entries

    def projects(self) -> ProjectList:
        return ProjectList(
            projects=[
                Project(
                    key=key,
                    name=f"name of {key}",
                    display_path=key,
                    state="ok",
                    running=False,
                    listed=True,
                )
                for key in self._entries
            ]
        )

    def edit_inputs(self, project: str) -> EditInputs:
        try:
            return self._entries[project]
        except KeyError:
            raise UnknownProjectError from None


def inputs_for(
    key: str,
    config: Path,
    project: Path | None,
    store_root: Path,
    *,
    shell_env: dict[str, str] | None = None,
) -> EditInputs:
    """Build one project's inputs the way ``StoreProvider.edit_inputs`` does."""
    setup = SetupContext(
        project_key=key,
        config_dir=config,
        home=config.parent,
        project_dir=project,
        managed_dir=None,
        shell_env=shell_env or {},
        plan=None,
        real_mode=False,
    )
    return EditInputs(setup=setup, claude_version=None, store_root=store_root)


@dataclass
class Api:
    """One mounted app and the folders behind it."""

    client: Any
    service: EditService
    state: AccessState
    provider: EditProvider
    clock: FakeNow
    config: Path
    project: Path
    store_root: Path
    inputs: EditInputs
    timers: list[tuple[float, Callable[[], None]]] = field(
        default_factory=list[tuple[float, Callable[[], None]]]
    )

    @property
    def store(self) -> EditStore:
        """The one writer the routes use."""
        return self.service.store(self.inputs)

    @property
    def backups(self) -> Path:
        """The backups folder under the throwaway config folder."""
        return self.config / "routing-dashboard" / "backups"

    def user_file(self) -> Path:
        return self.config / "settings.json"

    def project_file(self) -> Path:
        return self.project / ".claude" / "settings.json"

    def local_file(self) -> Path:
        return self.project / ".claude" / "settings.local.json"

    def targets(self) -> list[Any]:
        """The registry's targets for the project."""
        return edit_preview.targets_of(self.store, self.inputs)

    def body(
        self,
        value: str | int,
        scope: str = "project",
        field_name: str = FIELD,
        seq: int = 1,
        project: str = PROJECT,
    ) -> dict[str, Any]:
        return {
            "project": project,
            "op": "set",
            "scope": scope,
            "field": field_name,
            "value": value,
            "seq": seq,
        }

    def preview(
        self,
        value: str | int,
        scope: str = "project",
        field_name: str = FIELD,
        seq: int = 1,
    ) -> Any:
        return self.client.post(
            "/api/edit/preview", json=self.body(value, scope, field_name, seq)
        )

    def save(  # noqa: PLR0913 - the pieces of one press, keyword-only after three
        self,
        value: str | int,
        scope: str = "project",
        field_name: str = FIELD,
        *,
        version: str | None = None,
        rid: str | None = None,
        seq: int = 2,
    ) -> Any:
        """Preview, then save with that preview's token (or the given one)."""
        if version is None:
            shown = self.preview(value, scope, field_name, seq=seq - 1)
            assert shown.status_code == 200, shown.text
            version = shown.json()["version"]
        body = {
            **self.body(value, scope, field_name, seq),
            "version": version,
            "request_id": rid or os.urandom(8).hex(),
        }
        return self.client.post("/api/edit/save", json=body)

    def undo(
        self,
        row_id: str,
        *,
        anyway: bool = False,
        version: str | None = None,
        rid: str | None = None,
    ) -> Any:
        body: dict[str, Any] = {
            "project": PROJECT,
            "row_id": row_id,
            "request_id": rid or os.urandom(8).hex(),
            "anyway": anyway,
        }
        if version is not None:
            body["version"] = version
        return self.client.post("/api/edit/undo", json=body)

    def history(self) -> Any:
        return self.client.get(f"/api/edit/history?project={PROJECT}")

    def row(self, row_id: str) -> Any:
        return self.client.get(f"/api/edit/rows/{row_id}?project={PROJECT}")

    def drift(self, row_id: str) -> Any:
        return self.client.get(f"/api/edit/rows/{row_id}/drift?project={PROJECT}")

    def seen(self, row_id: str, project: str = PROJECT) -> Any:
        return self.client.post(
            f"/api/edit/rows/{row_id}/seen", json={"project": project}
        )

    def open_warning(self, item: str | None = None) -> Any:
        extra = "" if item is None else f"&item={item}"
        return self.client.get(f"/api/edit/open?project={PROJECT}{extra}")

    def run_timers(self) -> None:
        """Run every recorded recheck, as the two timers would."""
        for _delay, work in list(self.timers):
            work()
        self.timers.clear()


@contextmanager
def open_api(  # noqa: PLR0913 - the pieces of one machine, keyword-only after three
    open_client: OpenClient,
    config: Path,
    project: Path,
    *,
    edits: EditsMode = "on",
    other: Path | None = None,
    shell_env: dict[str, str] | None = None,
    clock: FakeNow | None = None,
) -> Generator[Api]:
    """Mount the edit routers over a machine and yield a client for them."""
    store_root = config.parent / "bartab-store"
    store_root.mkdir(mode=0o700, exist_ok=True)
    (config / "routing-dashboard" / "bartab").mkdir(parents=True, exist_ok=True)
    entries = {
        PROJECT: inputs_for(PROJECT, config, project, store_root, shell_env=shell_env)
    }
    if other is not None:
        entries[OTHER] = inputs_for(
            OTHER, config, other, store_root, shell_env=shell_env
        )
    provider = EditProvider(entries)
    state = AccessState(edits=edits)
    timers: list[tuple[float, Callable[[], None]]] = []
    moved = clock or FakeNow()

    def schedule(delay: float, work: Callable[[], None]) -> None:
        timers.append((delay, work))

    service = EditService(
        provider, state, clock=moved, scheduler=schedule, secret=b"s" * 32
    )
    app = FastAPI()
    errors.install(app)
    app.include_router(api_edit.build_always_router(provider, state, config, service))
    if edits == "on":
        app.include_router(api_edit.build_edits_router(state, provider, service))
    else:
        app.include_router(api_edit.build_off_router())
    with open_client(app) as client:
        yield Api(
            client=client,
            service=service,
            state=state,
            provider=provider,
            clock=moved,
            config=config,
            project=project,
            store_root=store_root,
            inputs=entries[PROJECT],
            timers=timers,
        )


def write_json(path: Path, text: str, mode: int = 0o644) -> Path:
    """Write a settings file the way a person would have, with a chosen mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)
    return path


def dump(data: object) -> str:
    """Return JSON text as a person would write it: two spaces, a final newline."""
    return json.dumps(data, indent=2) + "\n"


def git_available() -> bool:
    """True when a git executable is on the path."""
    return shutil.which("git") is not None


def init_repo(folder: Path, add: list[str]) -> None:
    """Make a git repo in ``folder`` and stage the named files, with a bare env."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(folder.parent),
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    for args in (["init", "-q"], ["add", "--", *add]):
        subprocess.run(  # noqa: S603 - fixed arguments, a throwaway folder
            ["git", *args],  # noqa: S607
            cwd=folder,
            env=env,
            check=True,
            capture_output=True,
            timeout=20,
        )
