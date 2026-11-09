"""Tests for the read key, mint secret and single-use codes."""

import threading
import time
from typing import Any

import pytest

import access
from access import AccessState, SwapError


def test_new_state_makes_distinct_secrets() -> None:
    first, second = AccessState(), AccessState()
    assert len(first.instance) == 8
    assert int(first.instance, 16) >= 0
    assert first.read_key != second.read_key
    assert first.mint_secret != first.read_key
    assert len(first.read_key) >= 43


def test_code_is_instance_dot_random(state: AccessState) -> None:
    code = state.mint_code(None)
    prefix, dot, rest = code.partition(".")
    assert prefix == state.instance
    assert dot == "."
    assert len(rest) >= 20


def test_code_works_once(state: AccessState) -> None:
    code = state.mint_code("saltmarsh")
    result = state.swap(code)
    assert result.read_key == state.read_key
    assert result.instance == state.instance
    assert result.project == "saltmarsh"
    with pytest.raises(SwapError) as again:
        state.swap(code)
    assert again.value.reason == "code_used"


def test_code_without_project_returns_none(state: AccessState) -> None:
    assert state.swap(state.mint_code(None)).project is None


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [(0, None), (119.9, None), (120, "code_expired"), (500, "code_expired")],
)
def test_code_expires_at_120_seconds(
    state: AccessState, clock: Any, elapsed: float, expected: str | None
) -> None:
    code = state.mint_code(None)
    clock.advance(elapsed)
    if expected is None:
        state.swap(code)
        return
    with pytest.raises(SwapError) as err:
        state.swap(code)
    assert err.value.reason == expected


class _SlowFloat(float):
    """An expiry time whose comparison pauses, to open the gap between check and set."""

    def __le__(self, other: float) -> bool:
        time.sleep(0.01)
        return super().__le__(other)


def test_simultaneous_swaps_of_one_code_let_exactly_one_win(
    state: AccessState,
) -> None:
    """D2: the route is a plain def, so swaps run in threads and must not race."""
    threads = 16
    code = state.mint_code("saltmarsh")
    for entry in state._codes.values():  # pyright: ignore[reportPrivateUsage]
        entry.expires = _SlowFloat(entry.expires)
    barrier = threading.Barrier(threads)
    outcomes: list[str] = []

    def swap() -> None:
        barrier.wait()
        try:
            state.swap(code)
        except SwapError as err:
            outcomes.append(err.reason)
        else:
            outcomes.append("ok")

    workers = [threading.Thread(target=swap) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
    assert sorted(outcomes) == ["code_used"] * (threads - 1) + ["ok"]


def test_simultaneous_mints_each_give_a_working_code(state: AccessState) -> None:
    threads = 16
    barrier = threading.Barrier(threads)
    codes: list[str] = []

    def mint() -> None:
        barrier.wait()
        codes.append(state.mint_code(None))

    workers = [threading.Thread(target=mint) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
    assert len(set(codes)) == threads
    for code in codes:
        assert state.swap(code).read_key == state.read_key


def test_lifetime_constant_is_120_seconds() -> None:
    assert access.CODE_LIFETIME_SECONDS == 120


def test_old_entries_are_forgotten(state: AccessState, clock: Any) -> None:
    code = state.mint_code(None)
    clock.advance(4 * 3600)
    with pytest.raises(SwapError) as err:
        state.swap(code)
    assert err.value.reason == "code_unknown"


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("deadbeef.abcdefghijk", "server_restarted"),
        ("00000000.zzzz", "server_restarted"),
        ("", "code_unknown"),
        ("nodot", "code_unknown"),
        (".only-random", "code_unknown"),
        ("short.abc", "code_unknown"),
        ("DEADBEEF.abc", "code_unknown"),
        ("a.b.c", "code_unknown"),
    ],
)
def test_other_codes_are_refused(state: AccessState, code: str, reason: str) -> None:
    if code.startswith(state.instance):
        pytest.skip("instance collided with the sample")
    with pytest.raises(SwapError) as err:
        state.swap(code)
    assert err.value.reason == reason


def test_unknown_code_with_this_instance_is_unknown(state: AccessState) -> None:
    with pytest.raises(SwapError) as err:
        state.swap(f"{state.instance}.never-minted")
    assert err.value.reason == "code_unknown"


def test_swap_over_http_gives_a_working_read_key(
    client: Any, state: AccessState
) -> None:
    code = state.mint_code("tidewater-reporting")
    response = client.post("/api/access/swap", json={"code": code})
    assert response.status_code == 200
    body = response.json()
    assert body["instance"] == state.instance
    assert body["project"] == "tidewater-reporting"
    assert body["edit_keys"] == {}
    app_response = client.get("/api/app", headers={"X-Bartab-Key": body["read_key"]})
    assert app_response.status_code == 200
    again = client.post("/api/access/swap", json={"code": code})
    assert again.status_code == 403
    assert again.json() == {"code": "code_used", "path": None}


@pytest.mark.parametrize(
    ("code", "reason"),
    [("deadbeef.abcdefghijk", "server_restarted"), ("junk", "code_unknown")],
)
def test_swap_over_http_names_the_refusal(
    client: Any, code: str, reason: str, state: AccessState
) -> None:
    if code.startswith(state.instance):
        pytest.skip("instance collided with the sample")
    response = client.post("/api/access/swap", json={"code": code})
    assert response.status_code == 403
    assert response.json() == {"code": reason, "path": None}


def test_expired_code_over_http(client: Any, state: AccessState, clock: Any) -> None:
    code = state.mint_code(None)
    clock.advance(121)
    response = client.post("/api/access/swap", json={"code": code})
    assert response.status_code == 403
    assert response.json()["code"] == "code_expired"


def test_mint_over_http_makes_a_swappable_code(client: Any, state: AccessState) -> None:
    minted = client.post(
        "/api/access/mint",
        json={"project": "saltmarsh"},
        headers={"X-Bartab-Mint": state.mint_secret},
    )
    assert minted.status_code == 200
    swapped = client.post("/api/access/swap", json={"code": minted.json()["code"]})
    assert swapped.json()["project"] == "saltmarsh"


@pytest.mark.parametrize(
    "body",
    [
        {"project": "../etc"},
        {"project": "UPPER"},
        {"project": "x" * 100},
        {"project": 5},
        {"project": None, "extra": 1},
    ],
)
def test_mint_rejects_bad_projects(
    client: Any, state: AccessState, body: dict[str, object]
) -> None:
    response = client.post(
        "/api/access/mint",
        json=body,
        headers={"X-Bartab-Mint": state.mint_secret},
    )
    assert response.status_code == 422
