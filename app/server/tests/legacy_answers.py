"""Record what the M2 and M3 routes answer on the plain demo build.

``record`` asks a running demo server for the Agents answer of every project, the
Summary's Model check, and the Model check of every session's timeline. The result is
the pre-M4 snapshot in ``app/fixtures/oracle/m3-answers/answers.json``. Task 9 of M4
adds fields to those answers (``item_id``, ``plugin``), and the only change a recorded
answer may take is that addition, so the test strips the new fields from a fresh
answer and compares it with the snapshot (``test_legacy_answers.py``).

``volatile`` lists the fields that change between two runs by design.
"""

import json
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from conftest import INDEX_HTML, PORT, _open  # pyright: ignore[reportPrivateUsage]

import main
import serve
from access import AccessState
from data_clock import DataClock

VOLATILE = ("server_time", "etag")
RANGES = ("30d", "all")
SNAPSHOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "oracle"
    / "m3-answers"
    / "answers.json"
)


@contextmanager
def served_demo(build: Path, base: Path) -> Generator[tuple[Any, dict[str, str]]]:
    """Serve a demo build from a fresh store and wait for the ingest to finish."""
    dist = base / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    state = AccessState()
    settings = main.Settings(
        port=PORT,
        data_dir=base / "data",
        dist_dir=dist,
        access_state=state,
        claude_dir=build / "config",
        store_dir=base / "store",
        demo=True,
        data_clock=DataClock.fixed(serve.scenario_now(build)),
        price_fetch=False,
    )
    provider = main.make_provider(settings)
    app = main.create_app(replace(settings, provider=provider))
    with _open(app) as client:
        headers = {"X-Bartab-Key": state.read_key, "Accept-Encoding": "identity"}
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            info = client.get("/api/app", headers=headers).json()
            if info["ingest"]["state"] == "done":
                break
            time.sleep(0.05)
        else:
            msg = "the demo ingest never finished"
            raise RuntimeError(msg)
        yield client, headers


def _get(client: Any, headers: dict[str, str], path: str) -> dict[str, Any]:
    reply = client.get(path, headers=headers)
    if reply.status_code != 200:
        msg = f"{path} answered {reply.status_code}"
        raise RuntimeError(msg)
    body: dict[str, Any] = reply.json()
    return body


def record(client: Any, headers: dict[str, str]) -> dict[str, Any]:
    """Return the Agents, Summary Model check and timeline Model check answers."""
    out: dict[str, Any] = {}
    projects = _get(client, headers, "/api/projects")["projects"]
    for project in sorted(p["key"] for p in projects):
        for span in RANGES:
            base = f"project={project}&range={span}"
            agents = _get(client, headers, f"/api/agents?{base}")
            out[f"agents/{project}/{span}"] = _drop(agents)
        summary = _get(client, headers, f"/api/summary?project={project}&range=30d")
        out[f"summary-model-check/{project}"] = summary["model_check"]
        days = _get(client, headers, f"/api/sessions?project={project}&range=all")
        for day in days["days"]:
            for session in day["sessions"]:
                tl = _get(
                    client,
                    headers,
                    f"/api/sessions/{session['id']}/timeline?project={project}",
                )
                out[f"timeline-model-check/{project}/{session['id']}"] = tl[
                    "model_check"
                ]
    return out


def _drop(answer: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in answer.items() if k not in VOLATILE}


def dumps(answers: dict[str, Any]) -> str:
    """Render the snapshot the way it is stored."""
    return json.dumps(answers, indent=2, sort_keys=True) + "\n"
