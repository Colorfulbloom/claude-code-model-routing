"""Edit routes stay fast on big files and long histories (m6-build.md section 3.9).

The masker and the diff run over whole texts, so a settings file of several hundred
KB or a ledger with a few hundred rows must not turn one pass into many. Limits come
from ``timing_policy``: a strict local target, scaled under CI. The python 3.11 job
deselects the ``timing`` marker.
"""

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import timing_policy
from edit_api_helpers import OpenClient, open_api, write_json

import edit_store
import write_guard

PREVIEW_LOCAL_S = 1.0
HISTORY_LOCAL_S = 1.0
KEYS = 4_000
ROWS = 300


@pytest.fixture(autouse=True)
def _edits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(write_guard.STATE, "edits", True)


def big_settings() -> str:
    data: dict[str, object] = {
        f"key{i}": {"n": i, "text": "x" * 20} for i in range(KEYS)
    }
    data["effortLevel"] = "low"
    data["env"] = {"ANTHROPIC_API_KEY": "sk-ant-TIMINGSECRET"}
    return json.dumps(data, indent=2) + "\n"


@pytest.mark.timing
def test_a_preview_of_a_file_of_300_kb_stays_fast(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    text = big_settings()
    assert 200_000 < len(text) < 500_000
    write_json(edit_project / ".claude" / "settings.json", text)
    with open_api(open_client, edit_config, edit_project) as api:
        api.preview("high")  # warm the imports and the resolver
        started = time.perf_counter()
        response = api.preview("medium")
        took = time.perf_counter() - started
    assert response.status_code == 200
    body = response.json()
    assert body["refusal"] is None
    assert "sk-ant-TIMINGSECRET" not in response.text
    assert len(body["diff"]["lines"]) <= 8  # the edit and its context, not the file
    limit = timing_policy.limit(PREVIEW_LOCAL_S)
    assert took < limit, f"preview took {took:.2f} s, limit {limit:.2f} s"


@pytest.mark.timing
def test_history_over_a_few_hundred_rows_stays_fast(
    open_client: OpenClient, edit_config: Path, edit_project: Path
) -> None:
    write_json(
        edit_project / ".claude" / "settings.json",
        json.dumps({"effortLevel": "low"}, indent=2) + "\n",
    )
    with open_api(open_client, edit_config, edit_project) as api:
        assert api.save("high").status_code == 200
        folder = api.backups / edit_store.target_id_of(
            os.path.realpath(api.project_file())
        )
        ledger = json.loads((folder / "ledger.json").read_text())
        base = ledger["rows"][0]
        ledger["rows"] = [
            {
                **base,
                "id": f"{i:016x}",
                "time": f"2026-01-01T{i // 3600:02d}:{i // 60 % 60:02d}"
                f":{i % 60:02d}+00:00",
            }
            for i in range(1, ROWS)
        ] + [base]
        (folder / "ledger.json").write_text(json.dumps(ledger))
        api.history()  # warm
        started = time.perf_counter()
        response = api.history()
        took = time.perf_counter() - started
    assert response.status_code == 200
    body = response.json()
    assert len(body["rows"]) == 20
    assert body["older"]["count"] == ROWS - 20
    limit = timing_policy.limit(HISTORY_LOCAL_S)
    assert took < limit, f"history took {took:.2f} s, limit {limit:.2f} s"


@pytest.mark.timing
def test_the_git_check_gives_up_inside_its_timeout() -> None:
    import git_tracked

    assert timing_policy.wait_limit(2.0) >= git_tracked.TIMEOUT_SECONDS
