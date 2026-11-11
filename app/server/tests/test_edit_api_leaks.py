"""Masking and leaks (m6-build.md section 3.9).

Masking is span-aware: both sides of a diff are masked as whole texts before any line is
compared, so a secret on a context line, a secret across lines and a line that
holds part of a secret never show. The leak test runs every edit flow through the real
gate on a throwaway machine with planted secrets, then searches every response, every
captured log line and every ledger for the read key, the edit keys, the mint
secret, the access code
and the planted values. Backups keep raw bytes by design (undo needs them), so only
their names are searched.
"""

# ruff: noqa: S105 - the secrets here are planted fakes, the point of the test

import json
import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from conftest import PORT, FakeClock
from edit_api_helpers import (
    PROJECT,
    EditProvider,
    OpenClient,
    dump,
    inputs_for,
    open_api,
    write_json,
)

import edit_diff
import edit_store
import errors
import main
import write_guard
from access import AccessState
from edit_service import EditService

CONTEXT_SECRET = "sk-ant-CONTEXTSECRET"
MULTILINE_SECRET = "plain-multiline-secret"
LIST_SECRETS = ("listsecret-one", "listsecret-two")
LATE_SECRET = "sk-ant-LATESECRET"
PLANTED = (CONTEXT_SECRET, MULTILINE_SECRET, *LIST_SECRETS, LATE_SECRET)

# The edit is at line 6. The list above it and the objects below it are all context.
SECRET_FILE = """{
  "apiKeyList": [
    "listsecret-one",
    "listsecret-two"
  ],
  "effortLevel": "low",
  "credentialStore": {
    "user": "alice",
    "value": "plain-multiline-secret"
  },
  "env": {
    "ANTHROPIC_API_KEY": "sk-ant-CONTEXTSECRET"
  },
  "other": 1
}
"""


@pytest.fixture(autouse=True)
def _edits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(write_guard.STATE, "edits", True)


# ---------------------------------------------------------------- the masker


def lines_of(before: str | None, after: str | None) -> list[Any]:
    return edit_diff.diff_lines(
        None if before is None else before.encode(),
        None if after is None else after.encode(),
    )


def shown(lines: list[Any]) -> str:
    return "\n".join(line.text for line in lines)


def test_a_secret_on_a_context_line_is_masked() -> None:
    after = SECRET_FILE.replace('"low"', '"high"')
    text = shown(lines_of(SECRET_FILE, after))
    assert CONTEXT_SECRET not in text
    assert '"hidden"' in text


def test_a_secret_across_lines_is_masked_and_the_line_numbers_stay_true() -> None:
    after = SECRET_FILE.replace('"low"', '"high"')
    lines = lines_of(SECRET_FILE, after)
    text = shown(lines)
    for secret in (MULTILINE_SECRET, *LIST_SECRETS):
        assert secret not in text
    removed = next(line for line in lines if line.kind == "del")
    added = next(line for line in lines if line.kind == "add")
    assert (removed.old_n, added.new_n) == (6, 6)  # the real line of the edit
    context = [line for line in lines if line.kind == "ctx"]
    assert [line.old_n for line in context] == [line.new_n for line in context]
    assert [line.old_n for line in context] == [3, 4, 5, 7, 8, 9]


def test_a_value_on_a_line_with_part_of_a_secret_is_masked() -> None:
    before = '{\n  "token": "abc",\n  "a": 1\n}\n'
    after = '{\n  "token": "abc",\n  "a": 2\n}\n'
    text = shown(lines_of(before, after))
    assert "abc" not in text


def test_a_secret_prefix_under_an_innocent_name_is_masked() -> None:
    before = '{\n  "note": "sk-abcdefghij",\n  "a": 1\n}\n'
    after = '{\n  "note": "sk-abcdefghij",\n  "a": 2\n}\n'
    assert "sk-abcdefghij" not in shown(lines_of(before, after))


def test_a_new_file_diff_masks_its_added_lines() -> None:
    lines = lines_of(None, SECRET_FILE)
    assert {line.kind for line in lines} == {"add"}
    assert CONTEXT_SECRET not in shown(lines)


def test_a_secret_that_changed_shows_as_no_change_at_all() -> None:
    before = '{\n  "apiKey": "one",\n  "a": 1\n}\n'
    after = '{\n  "apiKey": "two",\n  "a": 1\n}\n'
    assert lines_of(before, after) == []


def test_text_the_parser_rejects_is_masked_by_line() -> None:
    before = (
        '{ // note\n  "a": 1,\n  "apiKey": {\n    "inner": "x"\n  },\n'
        '  "n": "sk-zzzzzzzz"\n}\n'
    )
    after = before.replace('"a": 1', '"a": 2')
    text = shown(lines_of(before, after))
    assert '"inner": "x"' not in text
    assert "sk-zzzzzzzz" not in text
    assert '"a": 2' in text


def test_a_byte_order_mark_file_takes_the_loose_mask() -> None:
    raw = ("﻿" + SECRET_FILE).encode("utf-8")
    text = shown(edit_diff.diff_lines(raw, raw + b" "))
    for secret in PLANTED:
        assert secret not in text


def test_a_long_file_costs_one_pass_and_keeps_its_line_numbers() -> None:
    body = ",\n".join(f'  "k{i}": {i}' for i in range(20000))
    before = "{\n" + body + "\n}\n"
    after = before.replace('"k10000": 10000', '"k10000": -1')
    lines = lines_of(before, after)
    removed = [line for line in lines if line.kind == "del"]
    assert [line.old_n for line in removed] == [10002]
    assert len(lines) <= 8


def test_changed_keys_list_names_never_values() -> None:
    before = b'{"a": 1, "env": {"X": "sk-aaaaaaaa"}, "gone": 1}'
    after = b'{"a": 2, "env": {"X": "sk-bbbbbbbb"}, "new": 1}'
    assert edit_diff.changed_keys(before, after) == ["a", "env.X", "gone", "new"]
    assert edit_diff.changed_keys(b"{broken", after) == []
    assert edit_diff.touches(["env.X"], ["env", "X"])
    assert edit_diff.touches(["env"], ["env", "X"])
    assert not edit_diff.touches(["other"], ["env", "X"])


# ---------------------------------------------------------------- the leak test


@dataclass
class Gate:
    client: Any
    state: AccessState
    code: str
    edit_key: str
    seen: list[str]

    def headers(self, *, write: bool) -> dict[str, str]:
        base = {"X-Bartab-Key": self.state.read_key}
        if write:
            base.update(
                {
                    "Origin": f"http://127.0.0.1:{PORT}",
                    "Content-Type": "application/json",
                    "X-Bartab-Edit": self.edit_key,
                }
            )
        return base

    def get(self, path: str) -> Any:
        response = self.client.get(path, headers=self.headers(write=False))
        self.seen.append(response.text + json.dumps(dict(response.headers)))
        return response

    def post(self, path: str, body: dict[str, Any], *, write: bool = True) -> Any:
        headers = self.headers(write=write)
        headers["Content-Type"] = "application/json"
        response = self.client.post(
            path, content=json.dumps(body).encode(), headers=headers
        )
        self.seen.append(response.text + json.dumps(dict(response.headers)))
        return response


def test_no_answer_log_or_ledger_carries_a_key_or_a_secret(  # noqa: PLR0913, PLR0917
    open_client: OpenClient,
    edit_config: Path,
    edit_project: Path,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timers: list[Callable[[], None]] = []

    def keep(_delay: float, work: Callable[[], None]) -> None:
        timers.append(work)

    monkeypatch.setattr(edit_store, "_thread_timer", keep)
    caplog.set_level(logging.DEBUG)
    write_json(edit_config / "settings.json", dump({"model": "sonnet"}))
    project_file = edit_project / ".claude" / "settings.json"
    write_json(project_file, SECRET_FILE)
    store_root = edit_config.parent / "bartab-store"
    store_root.mkdir()
    (edit_config / "routing-dashboard" / "bartab").mkdir(parents=True)
    provider = EditProvider(
        {PROJECT: inputs_for(PROJECT, edit_config, edit_project, store_root)}
    )
    state = AccessState(clock=FakeClock(), edits="on")
    settings = main.Settings(
        port=PORT,
        data_dir=tmp_path / "data",
        dist_dir=tmp_path / "dist",
        provider=provider,
        access_state=state,
        edits="on",
        clock=state.clock,
    )
    code = state.mint_code(PROJECT)
    with open_client(main.create_app(settings)) as client:
        swapped = client.post("/api/access/swap", json={"code": code}).json()
        gate = Gate(client, state, code, swapped["edit_keys"][PROJECT], [])
        body = {
            "project": PROJECT,
            "op": "set",
            "scope": "project",
            "field": "effortLevel",
            "value": "high",
            "seq": 1,
        }
        shown_ = gate.post("/api/edit/preview", body)
        assert shown_.status_code == 200
        assert "hidden" in json.dumps(shown_.json()["diff"])
        version = shown_.json()["version"]
        saved = gate.post(
            "/api/edit/save",
            {**body, "seq": 2, "version": version, "request_id": "leak-save-0001"},
        )
        assert saved.status_code == 200
        row_id = saved.json()["row_id"]
        gate.get(f"/api/edit/history?project={PROJECT}")
        gate.get(f"/api/edit/rows/{row_id}?project={PROJECT}")
        for work in timers:
            work()
        gate.get(f"/api/edit/rows/{row_id}?project={PROJECT}")
        # another program overwrites the file and plants one more secret on a line next
        # to the edit
        project_file.write_text(
            SECRET_FILE.replace('"high"', '"high"')
            .replace('"effortLevel": "low"', '"effortLevel": "high"')
            .replace(
                '"other": 1', f'"other": 2,\n  "extra": {{"auth": "{LATE_SECRET}"}}'
            ),
            encoding="utf-8",
        )
        drift = gate.get(f"/api/edit/rows/{row_id}/drift?project={PROJECT}")
        assert drift.status_code == 200
        assert drift.json()["lines"]
        gate.get(f"/api/edit/open?project={PROJECT}&item=settings:effortLevel")
        # a stale preview: a 409 with a fresh preview and changed keys
        stale = gate.post(
            "/api/edit/save",
            {
                **body,
                "value": "medium",
                "seq": 3,
                "version": version,
                "request_id": "leak-save-0002",
            },
        )
        assert stale.status_code == 409
        # an undo of a changed file: the undo diff of two files that both hold secrets
        conflict = gate.post(
            "/api/edit/undo",
            {"project": PROJECT, "row_id": row_id, "request_id": "leak-undo-0001"},
        )
        assert conflict.status_code == 409
        undo_version = conflict.json()["undo_preview"]["version"]
        gate.post(
            "/api/edit/undo",
            {
                "project": PROJECT,
                "row_id": row_id,
                "request_id": "leak-undo-0002",
                "anyway": True,
                "version": undo_version,
            },
        )
        gate.post(f"/api/edit/rows/{row_id}/seen", {"project": PROJECT}, write=False)
        gate.get(f"/api/edit/history?project={PROJECT}")
        gate.post(
            "/api/edit/save",
            {**body, "version": "junk", "request_id": "leak-save-0003"},
        )
    forbidden = [
        state.read_key,
        gate.edit_key,
        state.mint_secret,
        code,
        *PLANTED,
    ]
    haystacks = {
        "answers": "\n".join(gate.seen),
        "log": caplog.text,
        "ledgers": "\n".join(
            path.read_text(encoding="utf-8")
            for path in (edit_config / "routing-dashboard" / "backups").rglob(
                "ledger.json"
            )
        ),
        "backup names": "\n".join(
            path.name
            for path in (edit_config / "routing-dashboard" / "backups").rglob("*")
        ),
        "seen marks": "\n".join(
            path.read_text(encoding="utf-8") for path in store_root.glob("*.json")
        ),
    }
    for where, text in haystacks.items():
        assert text, where
        for secret in forbidden:
            assert secret not in text, (where, secret[:12])
    assert re.search(r"\.bak", haystacks["backup names"])


def test_an_edit_key_is_never_in_a_refusal_body(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(edit_project / ".claude" / "settings.json", dump({"effortLevel": "low"}))
    with open_api(open_client, edit_config, edit_project) as api:
        responses = [
            api.preview("turbo"),
            api.save("high", version="junk"),
            api.undo("0123456789abcdef"),
            api.row("0123456789abcdef"),
        ]
    for response in responses:
        assert "X-Bartab" not in response.text
        assert set(response.json()) <= {
            "server_time",
            "code",
            "params",
            "path",
            "seq",
            "choice_key",
            "target",
            "effect",
            "options",
            "scopes",
            "reaches",
            "warnings",
            "diff",
            "summary",
            "read_at",
            "version",
            "refusal",
        }


def test_the_routers_work_without_the_gate_or_a_service(
    edit_config: Path, edit_project: Path, open_client: OpenClient
) -> None:
    # A router built with no service makes its own, so the schema export and a bare
    # test app keep working.
    provider = EditProvider(
        {PROJECT: inputs_for(PROJECT, edit_config, edit_project, edit_config.parent)}
    )
    state = AccessState(edits="on")
    app = FastAPI()
    errors.install(app)
    shared = EditService(provider, state)
    import api_edit

    app.include_router(api_edit.build_always_router(provider, state, edit_config))
    app.include_router(api_edit.build_edits_router(state, provider, shared))
    with open_client(app) as client:
        assert client.get(f"/api/edit/history?project={PROJECT}").status_code == 200
