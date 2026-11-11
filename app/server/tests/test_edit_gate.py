"""Tests for the edit switch, the edit keys and the gate's write rules.

The matrix asserts "refused" (a 4xx), not exact codes, where the gate answers, as M0
did. A few named tests pin the two codes the page reacts to, ``edits_off`` and
``edit_key_unknown``. No test here writes a user file: preview, save and undo are
stubs that refuse until the writer lands.
"""

import json
import sys
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from starlette.types import ASGIApp

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from conftest import PORT, FakeClock

import gate
import main
from access import AccessState

PROJECT = "tidewater-reporting"
OTHER = "saltmarsh-api"
ORIGIN = f"http://127.0.0.1:{PORT}"
WRITE_PATHS = ("/api/edit/preview", "/api/edit/save", "/api/edit/undo")
PREVIEW_BODY = {
    "project": PROJECT,
    "op": "set",
    "scope": "user",
    "field": "model",
    "value": "claude-sonnet-5-5",
    "seq": 1,
}
Client = Any
OpenClient = Callable[..., AbstractContextManager[Any]]


def _is_refused(status: int) -> bool:
    return 400 <= status < 500


@pytest.fixture
def on_state(clock: FakeClock) -> AccessState:
    return AccessState(clock=clock, edits="on")


@pytest.fixture
def on_settings(settings: main.Settings, on_state: AccessState) -> main.Settings:
    return replace(settings, access_state=on_state, edits="on")


@pytest.fixture
def on_client(on_settings: main.Settings, open_client: OpenClient) -> Iterator[Client]:
    with open_client(main.create_app(on_settings)) as test:
        yield test


def swap(client: Client, state: AccessState, project: str | None) -> dict[str, Any]:
    """Mint a code for ``project`` and swap it, the way the page does."""
    code = state.mint_code(project)
    response = client.post("/api/access/swap", json={"code": code})
    assert response.status_code == 200
    return response.json()


def edit_headers(state: AccessState, key: str | None, **extra: str) -> dict[str, str]:
    headers = {
        "X-Bartab-Key": state.read_key,
        "Origin": ORIGIN,
        "Content-Type": "application/json",
        **extra,
    }
    if key is not None:
        headers["X-Bartab-Edit"] = key
    return headers


def post_edit(
    client: Client,
    path: str,
    body: object,
    headers: dict[str, str] | list[tuple[str, str]],
) -> Any:
    return client.post(path, content=json.dumps(body).encode(), headers=headers)


# ---------------------------------------------------------------- the swap and keys


def test_swap_hands_out_the_codes_project_key_with_edits_on(
    on_client: Client, on_state: AccessState
) -> None:
    answer = swap(on_client, on_state, PROJECT)
    assert set(answer["edit_keys"]) == {PROJECT}
    assert len(answer["edit_keys"][PROJECT]) >= 32


def test_one_key_per_project_per_run_and_another_for_another_project(
    on_client: Client, on_state: AccessState
) -> None:
    first = swap(on_client, on_state, PROJECT)["edit_keys"][PROJECT]
    again = swap(on_client, on_state, PROJECT)["edit_keys"][PROJECT]
    other = swap(on_client, on_state, OTHER)["edit_keys"][OTHER]
    assert first == again
    assert other != first


def test_a_code_with_no_project_gets_no_edit_key(
    on_client: Client, on_state: AccessState
) -> None:
    assert swap(on_client, on_state, None)["edit_keys"] == {}


def test_swap_hands_out_no_key_with_edits_off(
    client: Client, state: AccessState
) -> None:
    assert swap(client, state, PROJECT)["edit_keys"] == {}


def test_edit_keys_differ_between_server_runs(
    clock: FakeClock, open_client: OpenClient, settings: main.Settings
) -> None:
    keys: list[str] = []
    for _ in range(2):
        state = AccessState(clock=clock, edits="on")
        built = replace(settings, access_state=state, edits="on")
        with open_client(main.create_app(built)) as test:
            keys.append(swap(test, state, PROJECT)["edit_keys"][PROJECT])
    assert keys[0] != keys[1]


def test_the_edit_key_is_in_no_other_answer(
    on_client: Client, on_state: AccessState, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("DEBUG")
    key = swap(on_client, on_state, PROJECT)["edit_keys"][PROJECT]
    seen: list[str] = []
    for path in ("/api/app", "/api/projects", f"/api/edit/history?project={PROJECT}"):
        response = on_client.get(path, headers={"X-Bartab-Key": on_state.read_key})
        seen.append(response.text + str(dict(response.headers)))
    for bad in (key + "x", ""):
        response = post_edit(
            on_client, "/api/edit/preview", PREVIEW_BODY, edit_headers(on_state, bad)
        )
        seen.append(response.text + str(dict(response.headers)))
    good = post_edit(
        on_client, "/api/edit/preview", PREVIEW_BODY, edit_headers(on_state, key)
    )
    seen.append(good.text + str(dict(good.headers)))
    seen.append(caplog.text)
    assert all(key not in text for text in seen)


# ----------------------------------------------------- /api/app and /api/projects


def test_app_reports_edits_on_and_lists_editable_projects(
    on_client: Client, on_state: AccessState
) -> None:
    body = on_client.get("/api/app", headers={"X-Bartab-Key": on_state.read_key}).json()
    assert body["edits"] == {"state": "on", "instance": on_state.instance}
    assert body["instance"] == on_state.instance
    assert PROJECT in body["editable_projects"]


def test_app_reports_edits_off_with_no_editable_projects(
    client: Client, key_headers: dict[str, str], state: AccessState
) -> None:
    body = client.get("/api/app", headers=key_headers).json()
    assert body["edits"] == {"state": "off", "instance": state.instance}
    assert body["editable_projects"] == []


def test_app_reports_unavailable_with_no_editable_projects(
    clock: FakeClock, settings: main.Settings, open_client: OpenClient
) -> None:
    state = AccessState(clock=clock, edits="unavailable")
    built = replace(settings, access_state=state)
    with open_client(main.create_app(built)) as test:
        body = test.get("/api/app", headers={"X-Bartab-Key": state.read_key}).json()
    assert body["edits"]["state"] == "unavailable"
    assert body["editable_projects"] == []


def test_projects_carry_edit_block_only_for_a_missing_folder(
    on_client: Client, on_state: AccessState
) -> None:
    rows = on_client.get(
        "/api/projects", headers={"X-Bartab-Key": on_state.read_key}
    ).json()["projects"]
    assert rows
    for row in rows:
        expected = "folder_not_found" if row["state"] == "folder_not_found" else None
        assert row["edit_block"] == expected


def test_the_latch_turns_edits_off_for_good(
    on_client: Client, on_state: AccessState
) -> None:
    key = swap(on_client, on_state, PROJECT)["edit_keys"][PROJECT]
    assert on_state.disable_edits() is True
    assert on_state.edits == "unavailable"
    assert on_state.disable_edits() is False
    body = on_client.get("/api/app", headers={"X-Bartab-Key": on_state.read_key}).json()
    assert body["edits"]["state"] == "unavailable"
    assert body["editable_projects"] == []
    response = post_edit(
        on_client, "/api/edit/preview", PREVIEW_BODY, edit_headers(on_state, key)
    )
    assert _is_refused(response.status_code)
    assert response.json()["code"] == "edits_off"
    assert swap(on_client, on_state, PROJECT)["edit_keys"] == {}


# --------------------------------------------------------------- the gate matrix


@pytest.mark.parametrize("path", WRITE_PATHS)
def test_a_good_edit_write_passes_the_gate_and_the_stub_writes_nothing(
    on_client: Client, on_state: AccessState, path: str
) -> None:
    key = swap(on_client, on_state, PROJECT)["edit_keys"][PROJECT]
    body: dict[str, Any] = {**PREVIEW_BODY}
    if path == "/api/edit/save":
        body.update(version="v", request_id="req-12345678")
    if path == "/api/edit/undo":
        body = {"project": PROJECT, "row_id": "r1", "request_id": "req-12345678"}
    response = post_edit(on_client, path, body, edit_headers(on_state, key))
    # The gate let it through. The stub then refuses with not_editable.
    assert response.status_code == 422
    assert response.json()["code"] == "not_editable"


@pytest.mark.parametrize("path", WRITE_PATHS)
def test_edit_write_refusals(
    on_client: Client, on_state: AccessState, path: str
) -> None:
    key = swap(on_client, on_state, PROJECT)["edit_keys"][PROJECT]
    other = swap(on_client, on_state, OTHER)["edit_keys"][OTHER]
    good = edit_headers(on_state, key)
    no_origin = {k: v for k, v in good.items() if k != "Origin"}
    no_read_key = {k: v for k, v in good.items() if k != "X-Bartab-Key"}
    cases: dict[str, dict[str, str] | list[tuple[str, str]]] = {
        "no_origin": no_origin,
        "wrong_origin": {**good, "Origin": "http://evil.example"},
        "other_port_origin": {**good, "Origin": "http://127.0.0.1:1"},
        "null_origin": {**good, "Origin": "null"},
        "localhost_origin_on_a_127_host": {
            **good,
            "Origin": f"http://localhost:{PORT}",
        },
        "no_edit_header": edit_headers(on_state, None),
        "empty_edit_header": edit_headers(on_state, ""),
        "duplicate_edit_header": [
            ("X-Bartab-Key", on_state.read_key),
            ("Origin", ORIGIN),
            ("Content-Type", "application/json"),
            ("X-Bartab-Edit", key),
            ("X-Bartab-Edit", key),
        ],
        "key_for_another_project": edit_headers(on_state, other),
        "unknown_key": edit_headers(on_state, "not-a-key"),
        "key_with_a_suffix": edit_headers(on_state, key + "x"),
        "read_key_as_edit_key": edit_headers(on_state, on_state.read_key),
        "no_read_key": no_read_key,
        "cross_site": {**good, "Sec-Fetch-Site": "cross-site"},
    }
    for name, headers in cases.items():
        response = post_edit(on_client, path, PREVIEW_BODY, headers)
        assert _is_refused(response.status_code), name
        assert response.status_code != 422, name


def test_the_key_must_belong_to_the_projects_the_body_names(
    on_client: Client, on_state: AccessState
) -> None:
    key = swap(on_client, on_state, PROJECT)["edit_keys"][PROJECT]
    swap(on_client, on_state, OTHER)
    body = {**PREVIEW_BODY, "project": OTHER}
    response = post_edit(
        on_client, "/api/edit/preview", body, edit_headers(on_state, key)
    )
    assert _is_refused(response.status_code)
    assert response.json()["code"] == "edit_key_unknown"


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"not json",
        b"[]",
        b'{"seq": 1}',
        b'{"project": 5}',
        b'{"project": null}',
        # A repeated key, a BOM and another encoding are bodies two parsers could read
        # differently, so the gate refuses them whatever the key is.
        b'{"project": "tidewater-reporting", "project": "saltmarsh-api"}',
        b'\xef\xbb\xbf{"project": "tidewater-reporting"}',
        '{"project": "tidewater-reporting"}'.encode("utf-16"),
    ],
)
def test_a_body_that_names_no_project_is_refused(
    on_client: Client, on_state: AccessState, content: bytes
) -> None:
    key = swap(on_client, on_state, PROJECT)["edit_keys"][PROJECT]
    response = on_client.post(
        "/api/edit/preview", content=content, headers=edit_headers(on_state, key)
    )
    assert _is_refused(response.status_code)
    assert response.json()["code"] == "edit_key_unknown"


@pytest.mark.parametrize("path", WRITE_PATHS)
def test_a_body_over_the_cap_is_refused_as_too_large(
    on_client: Client, on_state: AccessState, path: str
) -> None:
    key = swap(on_client, on_state, PROJECT)["edit_keys"][PROJECT]
    body = {**PREVIEW_BODY, "value": "x" * (gate.BODY_CAP + 10)}
    response = post_edit(on_client, path, body, edit_headers(on_state, key))
    assert response.status_code == 413
    assert response.json()["code"] == "too_large"


def test_a_wrong_key_answers_edit_key_unknown(
    on_client: Client, on_state: AccessState
) -> None:
    swap(on_client, on_state, PROJECT)
    response = post_edit(
        on_client, "/api/edit/save", PREVIEW_BODY, edit_headers(on_state, "wrong")
    )
    assert _is_refused(response.status_code)
    assert response.json() == {"code": "edit_key_unknown", "path": None}


def test_the_edit_key_compare_runs_in_constant_time_for_unknown_projects(
    on_client: Client, on_state: AccessState, monkeypatch: pytest.MonkeyPatch
) -> None:
    import access

    calls: list[tuple[bytes, bytes]] = []
    real = access.hmac.compare_digest

    def spy(left: bytes, right: bytes) -> bool:
        calls.append((left, right))
        return real(left, right)

    monkeypatch.setattr(access.hmac, "compare_digest", spy)
    for project in (PROJECT, "no-such-project"):
        body = {**PREVIEW_BODY, "project": project}
        post_edit(on_client, "/api/edit/preview", body, edit_headers(on_state, "k"))
    # One compare per request, a stand-in when the project has no key.
    assert len(calls) >= 2


def test_no_cors_header_and_no_preflight(
    on_client: Client, on_state: AccessState
) -> None:
    key = swap(on_client, on_state, PROJECT)["edit_keys"][PROJECT]
    headers = {
        "Origin": "http://evil.example",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-bartab-edit,x-bartab-key",
    }
    preflight = on_client.options("/api/edit/save", headers=headers)
    assert _is_refused(preflight.status_code)
    responses = [
        preflight,
        post_edit(
            on_client, "/api/edit/save", PREVIEW_BODY, edit_headers(on_state, key)
        ),
        on_client.get("/api/app", headers={"X-Bartab-Key": on_state.read_key}),
    ]
    for response in responses:
        assert not [
            h for h in response.headers if h.lower().startswith("access-control")
        ]


# -------------------------------------------------------------------------- edits off


@pytest.mark.parametrize("path", WRITE_PATHS)
def test_edits_off_refuses_every_write_with_edits_off(
    client: Client, state: AccessState, path: str
) -> None:
    headers = edit_headers(state, "any-key")
    response = post_edit(client, path, PREVIEW_BODY, headers)
    assert _is_refused(response.status_code)
    assert response.json() == {"code": "edits_off", "path": None}


@pytest.mark.parametrize("path", WRITE_PATHS)
def test_edits_off_answers_even_without_the_edit_header(
    client: Client, state: AccessState, path: str
) -> None:
    response = post_edit(client, path, PREVIEW_BODY, edit_headers(state, None))
    assert _is_refused(response.status_code)
    assert response.json()["code"] == "edits_off"


def test_edits_off_still_needs_the_read_key_and_the_origin(
    client: Client, state: AccessState
) -> None:
    no_key = {"Origin": ORIGIN, "Content-Type": "application/json"}
    assert (
        post_edit(client, "/api/edit/preview", PREVIEW_BODY, no_key).status_code == 401
    )
    no_origin = {"X-Bartab-Key": state.read_key, "Content-Type": "application/json"}
    response = post_edit(client, "/api/edit/preview", PREVIEW_BODY, no_origin)
    assert _is_refused(response.status_code)
    assert response.json()["code"] != "edits_off"


def test_the_edits_off_router_answers_edits_off_too(
    settings: main.Settings, state: AccessState, open_client: OpenClient
) -> None:
    # Past the gate: a gate stand-in that forwards everything. The router must still
    # answer edits_off, not a bare 404.
    app: ASGIApp = main.build_app(settings)
    with open_client(app) as test:
        for path in WRITE_PATHS:
            response = test.post(path, json={})
            assert response.status_code == 403
            assert response.json()["code"] == "edits_off"


def test_unavailable_answers_edits_off(
    clock: FakeClock, settings: main.Settings, open_client: OpenClient
) -> None:
    state = AccessState(clock=clock, edits="unavailable")
    built = replace(settings, access_state=state)
    with open_client(main.create_app(built)) as test:
        response = post_edit(
            test, "/api/edit/preview", PREVIEW_BODY, edit_headers(state, "k")
        )
    assert response.json()["code"] == "edits_off"


# ---------------------------------------------------------------- always-mounted routes


@pytest.mark.parametrize("edits", ["on", "off"])
def test_history_open_and_seen_stay_mounted(
    clock: FakeClock, settings: main.Settings, open_client: OpenClient, edits: str
) -> None:
    state = AccessState(clock=clock, edits=edits)  # type: ignore[arg-type]
    built = replace(settings, access_state=state)
    read = {"X-Bartab-Key": state.read_key}
    with open_client(main.create_app(built)) as test:
        history = test.get(f"/api/edit/history?project={PROJECT}", headers=read)
        assert history.status_code == 200
        body = history.json()
        assert body["rows"] == []
        assert body["older"] == {"count": 0, "rows": []}
        assert body["edits"] == {"state": edits, "instance": state.instance}
        assert set(body["backup_folder"]) == {"display", "real"}
        opened = test.get(f"/api/edit/open?project={PROJECT}", headers=read)
        assert opened.status_code == 200
        assert opened.json()["row"] is None
        # "seen" needs the read key only: no Origin, no edit header. It reaches the
        # route, which knows no such row yet.
        seen = test.post(
            "/api/edit/rows/r1/seen",
            content=json.dumps({"project": PROJECT}).encode(),
            headers={**read, "Content-Type": "application/json"},
        )
        assert seen.status_code == 404
        assert seen.json()["code"] == "unknown_edit"
        row = test.get(f"/api/edit/rows/r1?project={PROJECT}", headers=read)
        assert row.status_code == 404
        drift = test.get(f"/api/edit/rows/r1/drift?project={PROJECT}", headers=read)
        assert drift.status_code == 404


def test_history_checks_the_project(on_client: Client, on_state: AccessState) -> None:
    read = {"X-Bartab-Key": on_state.read_key}
    unknown = on_client.get("/api/edit/history?project=no-such-project", headers=read)
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "unknown_project"
    assert on_client.get("/api/edit/history", headers=read).status_code == 400


def test_any_new_post_under_api_edit_is_an_edit_write(
    client: Client, state: AccessState
) -> None:
    # A route that does not exist yet still meets the edit rules first.
    headers = {"X-Bartab-Key": state.read_key, "Content-Type": "application/json"}
    response = client.post("/api/edit/whatever", content=b"{}", headers=headers)
    assert _is_refused(response.status_code)
    assert response.json()["code"] == "bad_origin"
