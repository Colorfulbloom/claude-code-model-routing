#!/usr/bin/env python3
"""Record the old app's usage answers on the demo build as JSON oracle files.

Run from the repo root with the system Python:

    /usr/bin/python3 app/oracle/record.py

It builds the demo set into a temp folder outside the repo, builds a context with
dashboard/server.py fixture_context, and calls the old api_usage.usage and
api_usage.api_projects in process. No server starts and no port opens. The output
goes to app/fixtures/oracle/demo/. Python 3.9 standard library only. The old code
is imported and run, never changed.

Same inputs give the same bytes. The temp build folder is replaced by /work/demo in
every payload (also in the encoded folder names), keys are sorted and no timestamp
is written.
"""

import importlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "app" / "fixtures" / "oracle" / "demo"
BUILD_SCRIPT = REPO / "tests" / "fixtures" / "demo" / "build_demo.py"
NOW = "2026-10-30T18:00"
TZ = "America/New_York"
FAKE_ROOT = "/work/demo"
RANGES = ("today", "7d", "30d")
OLD_COMMIT_REF = "ad32428"
HTTP_OK = 200

DOC = (
    "Each entry is {path, reason, plan_ref}. path names a payload field, for "
    "example usage-30d-all.json:views.30d.totals.cost. reason says why the new "
    "answer may differ from the old one. plan_ref points to the plan section "
    "that allows it."
)


def _git(*args: str) -> str:
    """Run git in the repo and return its trimmed output."""
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


def _write(path: Path, text: str) -> None:
    """Write text as UTF-8 with LF line ends."""
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _dumps(payload: Any) -> str:  # noqa: ANN401
    """Return the stable JSON text of a payload."""
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    """Build the demo, ask the old app, write the files. Return the exit code."""
    sys.path.insert(0, str(REPO / "dashboard"))
    api_usage = importlib.import_module("api_usage")
    resolve = importlib.import_module("resolve")
    server = importlib.import_module("server")
    transcripts = importlib.import_module("transcripts")

    tmp = Path(tempfile.mkdtemp(prefix="oracle-")).resolve()
    try:
        folder = tmp / "demo"
        subprocess.run(  # noqa: S603
            [sys.executable, str(BUILD_SCRIPT), str(folder), "--now", NOW, "--tz", TZ],
            check=True,
            capture_output=True,
        )
        ctx = server.fixture_context(
            str(folder), None, None, resolve.load_rules(), resolve.load_agent_fields()
        )
        real = sorted({str(folder), str(folder.absolute())}, key=len, reverse=True)
        encoded = sorted(
            {transcripts.sanitize(item) for item in real}, key=len, reverse=True
        )
        fake_encoded = transcripts.sanitize(FAKE_ROOT)

        def clean(text: str) -> str:
            for item in real:
                text = text.replace(item, FAKE_ROOT)
            for item in encoded:
                text = text.replace(item, fake_encoded)
            return text

        status, listing = api_usage.api_projects(ctx, {})
        if status != HTTP_OK:
            msg = f"api_projects answered {status}"
            raise RuntimeError(msg)
        scopes = [row["key"] for row in listing["projects"]] + ["all"]

        files: dict[str, str] = {"projects.json": clean(_dumps(listing))}
        queries: list[dict[str, Any]] = [
            {"call": "api_projects", "file": "projects.json", "query": {}}
        ]
        for scope in scopes:
            query = {"project": [scope]}
            status, payload = api_usage.usage(ctx, query)
            if status != HTTP_OK:
                msg = f"usage answered {status} for {scope}"
                raise RuntimeError(msg)
            for rng in RANGES:
                part = dict(payload)
                part["views"] = {rng: payload["views"][rng]}
                name = f"usage-{rng}-{scope}.json"
                files[name] = clean(_dumps(part))
                queries.append(
                    {"call": "usage", "file": name, "query": query, "range": rng}
                )

        truth = json.loads((folder / "truth.json").read_text(encoding="utf-8"))
        files["truth.json"] = clean(_dumps(truth))

        OUT.mkdir(parents=True, exist_ok=True)
        allowed = OUT / "allowed-differences.json"
        if not allowed.is_file():
            _write(allowed, _dumps({"_doc": DOC, "differences": []}))
        keep = {*files, "allowed-differences.json", "manifest.json"}
        for old in OUT.glob("*.json"):
            if old.name not in keep:
                old.unlink()
        for name, text in files.items():
            _write(OUT / name, text)

        version = sys.version_info
        manifest = {
            "build_args": {
                "now": NOW,
                "script": "tests/fixtures/demo/build_demo.py",
                "tz": TZ,
            },
            "files": sorted(keep),
            "old_commit": _git(
                "log", "-1", "--format=%H", OLD_COMMIT_REF, "--", "dashboard"
            ),
            "python": f"{version[0]}.{version[1]}.{version[2]}",
            "queries": queries,
        }
        _write(OUT / "manifest.json", _dumps(manifest))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
