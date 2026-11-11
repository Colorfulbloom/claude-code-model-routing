"""Build time and size of the timeline for a long session.

An eight-hour session with 200 runs goes into a temp store. The timeline must build in
under 100 ms (the median of 20 builds after a warm-up, so one slow build on a busy
runner does not fail it), and its gzip body must stay under 200 KB (the exit of M2,
plan section 6). Both numbers are printed, with the 95th percentile and the slowest
build. Under CI, which GitHub sets, the time budget is the CI limit from
``timing_policy`` (ten times looser) because the runners have two shared vCPUs. The size
limit stays the same. The test carries the ``timing`` marker, so the python 3.11
coverage job deselects it and the python 3.14 job runs it.
"""

import gzip
import json
import os
import statistics
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import timeline_helpers as t
import timing_policy

import model_check
import timeline
from models import ModelCheck, Timeline, TimelineRun

RUNS = 200
SESSION_SECONDS = 8 * 3600
REQUESTS_PER_RUN = 6
BUILDS = 20
MEDIAN_LIMIT_MS = 100.0
GZIP_LIMIT_BYTES = 200 * 1024
AGENTS = ("scout", "worker", "reviewer", "builder", "scribe", "planner", "tester")


def long_session(base: Path) -> t.World:
    """Eight hours of work: a main session that launches 200 agent runs."""
    w = t.World(base, now=SESSION_SECONDS + 600.0)
    for k in range(SESSION_SECONDS // 90):
        w.add(SESSION_SECONDS + 500.0 - k * 90.0, f"m{k}", 200, 40 + k % 7)
    spacing = (SESSION_SECONDS - 600.0) / RUNS
    for i in range(RUNS):
        run = f"run{i:03d}"
        start = SESSION_SECONDS + 400.0 - i * spacing
        w.link(start, run)
        for j in range(REQUESTS_PER_RUN):
            w.add(
                start - 5.0 - j * 40.0,
                f"{run}-{j}",
                60 + j,
                8 + j,
                cache_read=4000 + 10 * j,
                cache_write=300,
                model=t.OPUS if i % 3 else t.SONNET,
                effort="high" if i % 2 else "medium",
                run=run,
                agent=AGENTS[i % len(AGENTS)],
                stop="handback" if j == REQUESTS_PER_RUN - 1 else None,
            )
    return w


def percentile(values: list[float], share: float) -> float:
    """The value at ``share`` (0 to 1) of the sorted values, nearest rank."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(share * (len(ordered) - 1)))]


def measure(base: str) -> dict[str, float]:
    """Build the long session in ``base`` and time ``BUILDS`` timeline builds.

    Returns the build times in milliseconds and the sizes of the answer. The test
    runs this in a child process, so a coverage tracer in the test process can't
    slow the builds it times.
    """
    w = long_session(Path(base))
    conn = w.conn()  # one ingest pass
    entries = model_check.resolve_entries(
        claude_dir=w.config.dir, project_dir=None, managed_dir=None, shell_env={}
    )

    def check(_key: str, runs: Sequence[TimelineRun]) -> ModelCheck:
        return model_check.build_model_check(
            entries=entries, runs=runs, catalog=t.CATALOG
        )

    def build() -> Timeline | None:
        return timeline.build_timeline(
            conn,
            session_id=t.S1,
            project_key=t.PROJECT,
            folder_keys=w.projects,
            now=w.moment(),
            pricer=w.pricer,
            catalog=t.CATALOG,
            model_check_fn=check,
            prices=timeline.bundled_prices(w.moment().date()),
        )

    build()  # warm the caches, as a server that has answered before would
    millis: list[float] = []
    answer = None
    for _ in range(BUILDS):
        began = time.perf_counter()
        answer = build()
        millis.append((time.perf_counter() - began) * 1000)
    assert answer is not None
    body = json.dumps(answer.model_dump(mode="json"), separators=(",", ":")).encode()
    return {
        "p95_ms": percentile(millis, 0.95),
        "median_ms": statistics.median(millis),
        "max_ms": max(millis),
        "runs": len(answer.runs),
        "bucket_seconds": answer.axis.bucket_seconds,
        "body_bytes": len(body),
        "gzip_bytes": len(gzip.compress(body, compresslevel=9)),
    }


CHILD = (
    "import json, sys; sys.path[:0] = [{server!r}, {tests!r}]; "
    "import test_timeline_size as m; print(json.dumps(m.measure(sys.argv[1])))"
)


@pytest.mark.slow
@pytest.mark.timing
def test_an_eight_hour_session_with_200_runs_builds_fast_and_stays_small(
    tmp_path: Path,
) -> None:
    here = Path(__file__).resolve().parent
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("COV_CORE", "COVERAGE"))  # no tracer in the child
    }
    done = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-B",
            "-c",
            CHILD.format(server=str(here.parent), tests=str(here)),
            str(tmp_path),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )
    result = json.loads(done.stdout.strip().splitlines()[-1])
    print(  # noqa: T201
        f"timeline size: p95 {result['p95_ms']:.1f} ms, "
        f"median {result['median_ms']:.1f} ms, max {result['max_ms']:.1f} ms over "
        f"{BUILDS} builds; {result['runs']:.0f} runs, "
        f"{result['bucket_seconds']:.0f} s buckets; "
        f"body {result['body_bytes'] / 1024:.1f} KB, "
        f"gzip {result['gzip_bytes'] / 1024:.1f} KB"
    )
    assert result["runs"] >= RUNS
    limit = timing_policy.limit(MEDIAN_LIMIT_MS)
    assert result["median_ms"] < limit, f"median {result['median_ms']:.0f} ms, {limit=}"
    assert result["gzip_bytes"] < GZIP_LIMIT_BYTES
