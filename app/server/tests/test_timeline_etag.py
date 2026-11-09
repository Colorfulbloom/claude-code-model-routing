"""The timeline etag on a moving clock, polled through the route.

A running session's answer carries the clock T in the axis end and in the end of each
working run's open segment. The etag leaves those out, so a 1 s poll with no new
request gets the short ``unchanged`` reply even while T moves, and a real change (a
new request) still changes the etag.
"""

import sys
import time
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import ingest_helpers as h
from conftest import INDEX_HTML, PORT, _open  # pyright: ignore[reportPrivateUsage]

import main
from access import AccessState
from data_clock import DataClock

PROJECT = "app"
POLLS = 40
MOST = 0.9
RATE = 1.0


class Wall:
    """Epoch seconds the test moves by hand."""

    def __init__(self) -> None:
        self.at = 1_000_000.0

    def __call__(self) -> float:
        return self.at


class Rig:
    """A rate-clock server over one running session."""

    def __init__(self, client: Any, state: AccessState, wall: Wall, config: h.Config):
        self.client = client
        self.state = state
        self.wall = wall
        self.config = config
        self.path = config.main(h.S1)

    def poll(self, etag: str | None = None) -> Any:
        query = f"?project={PROJECT}" + (f"&etag={etag}" if etag else "")
        reply = self.client.get(
            f"/api/sessions/{h.S1}/timeline{query}",
            headers={
                "X-Bartab-Key": self.state.read_key,
                "Accept-Encoding": "identity",
            },
        )
        assert reply.status_code == 200, reply.text
        return reply.json()


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[Rig]:
    config = h.Config(tmp_path)
    config.write(config.main(h.S1), [h.assistant(10, "m1", req="r1", out=40)])
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    wall = Wall()
    state = AccessState()
    settings = main.Settings(
        port=PORT,
        data_dir=tmp_path / "data",
        dist_dir=dist,
        access_state=state,
        claude_dir=config.dir,
        store_dir=tmp_path / "store",
        data_clock=DataClock.rate(h.T0 + timedelta(seconds=15), RATE, wall=wall),
        price_fetch=False,
    )
    with _open(main.create_app(settings)) as client:
        made = Rig(client, state, wall, config)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            reply = client.get(
                f"/api/sessions/{h.S1}/timeline?project={PROJECT}",
                headers={"X-Bartab-Key": state.read_key},
            )
            if reply.status_code == 200:
                break
            time.sleep(0.05)
        else:
            pytest.fail("the session never reached the store")
        yield made


def test_most_one_second_polls_are_unchanged_and_a_new_request_changes_the_etag(
    rig: Rig,
) -> None:
    first = rig.poll()
    assert first["session"]["state"] == "working"
    ends = {first["axis"]["end"]}
    unchanged = 0
    etag = first["etag"]
    for _ in range(POLLS):
        rig.wall.at += 1.0 / RATE
        answer = rig.poll(etag)
        if answer["unchanged"]:
            unchanged += 1
            assert answer["etag"] == etag
        else:
            ends.add(answer["axis"]["end"])
            etag = answer["etag"]
    share = unchanged / POLLS
    print(f"unchanged share on the rate clock: {unchanged}/{POLLS} = {share:.0%}")  # noqa: T201
    assert share >= MOST
    # The clock really moved: a full answer at the end shows a later axis end.
    full = rig.poll()
    assert full["axis"]["end"] > first["axis"]["end"]
    assert full["etag"] == etag
    # A new request still changes the etag, once the writer has read it.
    stamp_sec = (full["server_time"] and 15 + POLLS) - 1
    rig.config.append(rig.path, [h.assistant(stamp_sec, "m2", req="r2", out=90)])
    deadline = time.monotonic() + 15
    changed = None
    while time.monotonic() < deadline:
        answer = rig.poll(etag)
        if not answer["unchanged"]:
            changed = answer
            break
        time.sleep(0.05)
    assert changed is not None, "the new request never changed the etag"
    assert changed["etag"] != etag
    assert changed["totals"]["requests"] == full["totals"]["requests"] + 1
