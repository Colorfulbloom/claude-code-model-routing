"""How long a new request takes to reach the timeline.

The real store writer runs on a temp tree. The test appends a request to a running
session's transcript 20 times and polls the provider's timeline until the new request
shows. The median lag must stay under 1.5 s and the worst under 2.0 s (the exit of
M2, plan section 6). The numbers are printed. The page's own 1 s poll comes on top and
is measured in the browser.
"""

import json
import statistics
import sys
import time
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import ingest_helpers as h

import store_provider
from models import Timeline

APPENDS = 20
MEDIAN_LIMIT_S = 1.5
WORST_LIMIT_S = 2.0
FOLDER = "-work-latency-app"
PROJECT = "latency-app"


def request_row(index: int) -> bytes:
    """One assistant request, stamped now, with its own output size."""
    now = datetime.now(UTC)
    row = json.loads(
        h.assistant(0, f"msg_{index}", out=100 + index, cwd="/work/latency-app")
    )
    row["timestamp"] = h.iso(now)
    return json.dumps(row).encode() + b"\n"


@pytest.fixture
def provider(tmp_path: Path) -> Generator[store_provider.StoreProvider]:
    config = h.Config(tmp_path)
    transcript = config.main(h.S1, FOLDER)
    config.write(transcript, [request_row(0)])
    made = store_provider.create(
        claude_dir=config.dir,
        store_dir=tmp_path / "store",
        demo=True,
        pace_ms=0,
        price_fetch=False,
    )
    made.start()
    try:
        yield made
    finally:
        made.stop()


def timeline_of(provider: store_provider.StoreProvider) -> Timeline | None:
    try:
        answer = provider.timeline(PROJECT, h.S1, None)
    except Exception:  # noqa: BLE001 - the session is not known until the first pass
        return None
    return answer if isinstance(answer, Timeline) else None


def wait_for_output(
    provider: store_provider.StoreProvider, output: int, seconds: float
) -> None:
    """Poll the timeline every 10 ms until its newest request shows ``output`` tokens.

    The row's own tokens are the mark, not a request count. The reader has no snapshot
    across the timeline's queries, so a count can run one ahead of the request list
    for a single answer.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        answer = timeline_of(provider)
        if (
            answer is not None
            and answer.requests
            and (answer.requests[0].output == output)
        ):
            return
        time.sleep(0.01)
    pytest.fail(f"the timeline never showed the request with {output} output tokens")


@pytest.mark.slow
def test_a_new_request_reaches_the_timeline_within_two_seconds(
    tmp_path: Path, provider: store_provider.StoreProvider
) -> None:
    transcript = tmp_path / "config" / "projects" / FOLDER / f"{h.S1}.jsonl"
    wait_for_output(provider, 100, 30.0)  # the first run has read the first request
    lags: list[float] = []
    for index in range(1, APPENDS + 1):
        time.sleep(0.05 + (index * 0.037) % 0.31)  # spread the appends over the loop
        with transcript.open("ab") as handle:
            handle.write(request_row(index))
        began = time.monotonic()
        wait_for_output(provider, 100 + index, 10.0)
        lags.append(time.monotonic() - began)
    median = statistics.median(lags)
    print(  # noqa: T201
        f"live latency over {APPENDS} appends: median {median * 1000:.0f} ms, "
        f"worst {max(lags) * 1000:.0f} ms, best {min(lags) * 1000:.0f} ms"
    )
    assert median < MEDIAN_LIMIT_S
    assert max(lags) < WORST_LIMIT_S
