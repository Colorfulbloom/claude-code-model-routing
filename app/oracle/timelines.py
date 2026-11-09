#!/usr/bin/env python3
"""Write the new server's end-of-session timeline answer for each live_flow scenario.

Run from the repo root:

    app/scripts/uvw run --frozen --directory app python oracle/timelines.py

For each scenario (busy, many, unlinked, empty) it builds the ``live_flow`` fixture
with ``tests/fixtures/live_flow/build_flow.py`` into a temp folder, fills a temp store
through the server's own provider with a fixed data clock at the scenario's ``now``, and
asks the provider for the session's timeline. The answer goes to
``app/fixtures/oracle/live/<scenario>/new-end.json``.

The Vitest oracle (``src/lib/timeline-at.oracle.test.ts``) picks values at every T the
old app recorded from this one answer and compares them with the old answers. No server
starts and no port opens. Same inputs give the same bytes: keys are sorted and no
timestamp is written.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
REPO = APP.parent
sys.path.insert(0, str(APP / "server"))

import store_provider  # noqa: E402
from data_clock import DataClock  # noqa: E402
from models import Timeline  # noqa: E402

FLOW_SCRIPT = REPO / "tests" / "fixtures" / "live_flow" / "build_flow.py"
OUT = APP / "fixtures" / "oracle" / "live"
SCENARIOS = ("busy", "many", "unlinked", "empty")
PROJECT = "tidewater-reporting"
READY_SECONDS = 60


def _build(scenario: str, base: Path) -> Path:
    """Build one scenario and return its folder."""
    out = base / scenario
    subprocess.run(  # noqa: S603
        [sys.executable, "-B", str(FLOW_SCRIPT), str(out), scenario],
        check=True,
        timeout=180,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )
    return out


def _clock(built: Path) -> datetime:
    """Read the scenario clock, ``now`` in its ``session.json``."""
    text = json.loads((built / "session.json").read_text(encoding="utf-8"))["now"]
    at = datetime.fromisoformat(text)
    return at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)


def _answer(built: Path, base: Path) -> Timeline:
    """Ask the provider for the scenario's session at the scenario clock."""
    session = json.loads((built / "flow.json").read_text(encoding="utf-8"))["session"]
    provider = store_provider.create(
        claude_dir=built / "config",
        store_dir=base / f"store-{built.name}",
        demo=True,
        pace_ms=0,
        price_fetch=False,
        data_clock=DataClock.fixed(_clock(built)),
        mode="flow",
    )
    provider.start()
    try:
        deadline = time.monotonic() + READY_SECONDS
        while provider.app_info("oracle", None).ingest.state != "done":
            if time.monotonic() > deadline:
                msg = "the ingest never finished"
                raise TimeoutError(msg)
            time.sleep(0.05)
        answer = provider.timeline(PROJECT, session, None)
    finally:
        provider.stop()
    if not isinstance(answer, Timeline):
        msg = "the provider answered with the short form"
        raise TypeError(msg)
    return answer


def main() -> None:
    """Write ``new-end.json`` for every scenario."""
    base = Path(tempfile.mkdtemp(prefix="timelines-")).resolve()
    try:
        for scenario in SCENARIOS:
            answer = _answer(_build(scenario, base), base)
            target = OUT / scenario / "new-end.json"
            body = json.dumps(
                answer.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            target.write_text(body + "\n", encoding="utf-8", newline="\n")
            sys.stdout.write(f"{scenario}: {len(answer.runs)} runs, {target.name}\n")
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
