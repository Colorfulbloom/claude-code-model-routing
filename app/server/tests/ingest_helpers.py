"""Builders and checks shared by the ingest and writer tests.

A test file imports this module by name after putting this folder on ``sys.path``,
as the ported tests do with ``port_helpers``. All names and paths are made up.
"""

import json
import os
import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import ingest
import store
import transcripts
import usage
from store_paths import StoreLayout

FOLDER = "-work-demo-app"
S1 = "11111111-1111-4111-8111-111111111111"
S2 = "22222222-2222-4222-8222-222222222222"
S3 = "33333333-3333-4333-8333-333333333333"
T0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
FAR = datetime(2026, 12, 1, tzinfo=UTC)


def iso(moment: datetime) -> str:
    """Return the transcript timestamp text for a moment, to the millisecond."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + (
        f"{moment.microsecond // 1000:03d}Z"
    )


def stamp(seconds: float) -> str:
    """Return a transcript timestamp ``seconds`` after T0."""
    return iso(T0 + timedelta(seconds=seconds))


def assistant(  # noqa: PLR0913 - a row has this many fields
    sec: float,
    msg: str | None,
    *,
    out: int = 10,
    sid: str = S1,
    req: str | None = None,
    model: str | None = "claude-sonnet-5-5",
    inp: int = 3,
    cache_read: int = 5,
    cache_write: int = 7,
    usage_obj: bool = True,
    tools: Sequence[str] | None = None,
    stop: str | None = None,
    cwd: str | None = "/work/demo/app",
    branch: str | None = "main",
) -> bytes:
    """Return one assistant row as a JSON line without its newline."""
    message: dict[str, object] = {"role": "assistant"}
    if msg is not None:
        message["id"] = msg
    if model is not None:
        message["model"] = model
    if usage_obj:
        message["usage"] = {
            "input_tokens": inp,
            "output_tokens": out,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_write,
            "cache_creation": {
                "ephemeral_5m_input_tokens": cache_write // 2,
                "ephemeral_1h_input_tokens": cache_write - cache_write // 2,
            },
        }
    message["content"] = [{"type": "tool_use", "name": n} for n in tools or ()]
    if stop is not None:
        message["stop_reason"] = stop
    row: dict[str, object] = {
        "type": "assistant",
        "timestamp": stamp(sec),
        "sessionId": sid,
        "message": message,
    }
    if req is not None:
        row["requestId"] = req
    if cwd is not None:
        row["cwd"] = cwd
    if branch is not None:
        row["gitBranch"] = branch
    return json.dumps(row).encode()


def link_row(sec: float, child: str, sid: str = S1) -> bytes:
    """Return a user row whose tool result launched agent ``child``."""
    return json.dumps(
        {
            "type": "user",
            "timestamp": stamp(sec),
            "sessionId": sid,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "content": "x"}],
            },
            "toolUseResult": {"agentId": child},
        }
    ).encode()


def brief_row(sec: float, kind: str = "coordinator", sid: str = S1) -> bytes:
    """Return a real user row with an origin, which briefs an agent."""
    return json.dumps(
        {
            "type": "user",
            "timestamp": stamp(sec),
            "sessionId": sid,
            "origin": {"kind": kind},
            "message": {"role": "user", "content": "do the next thing"},
        }
    ).encode()


class Config:
    """A fake Claude config folder under a base path."""

    def __init__(self, base: Path) -> None:
        """Create ``<base>/config/projects``."""
        self.dir = base / "config"
        self.projects = self.dir / "projects"
        self.projects.mkdir(parents=True)

    def main(self, sid: str = S1, folder: str = FOLDER) -> Path:
        """Path of a main transcript."""
        return self.projects / folder / f"{sid}.jsonl"

    def agent(self, run: str, sid: str = S1, folder: str = FOLDER) -> Path:
        """Path of an agent transcript."""
        return self.projects / folder / sid / "subagents" / f"agent-{run}.jsonl"

    def write(self, path: Path, lines: Sequence[bytes], *, end: bytes = b"\n") -> Path:
        """Write lines, each ended by a newline, and ``end`` after the last."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\n".join(lines) + (end if lines else b""))
        return path

    def append(self, path: Path, lines: Sequence[bytes], *, end: bytes = b"\n") -> None:
        """Append lines to a file."""
        with path.open("ab") as fh:
            fh.write(b"\n".join(lines) + end)

    def meta(
        self, run: str, agent_type: str, sid: str = S1, folder: str = FOLDER
    ) -> None:
        """Write the meta file of an agent."""
        path = self.agent(run, sid, folder).with_suffix(".meta.json")
        path.write_text(json.dumps({"agentType": agent_type}), encoding="utf-8")


class Store:
    """A migrated store and an ingestor over a config folder."""

    def __init__(
        self,
        base: Path,
        config: Config,
        *,
        clock: datetime = FAR,
        batch_rows: int = ingest.BATCH_ROWS,
        tier: ingest.TierPolicy | None = None,
    ) -> None:
        """Open the store at ``<base>/bartab`` and build the ingestor."""
        self.layout = StoreLayout(base / "bartab")
        self.conn = store.open_writer(self.layout)
        store.migrate(self.conn)
        self.now = clock
        self.progress = ingest.ProgressSink()
        self.ingestor = ingest.Ingestor(
            self.conn,
            config.dir,
            clock=lambda: self.now,
            tier_policy=tier,
            progress=self.progress,
            batch_rows=batch_rows,
        )

    def run(self, kind: ingest.PassKind = "cold") -> ingest.PassResult:
        """Run a pass over every folder."""
        return self.ingestor.run_pass(ingest.PassScope(kind))

    def close(self) -> None:
        """Close the connection."""
        self.conn.close()

    def one(self, sql: str, *args: object) -> object:
        """Return the first column of the first row."""
        row = self.conn.execute(sql, args).fetchone()
        return None if row is None else row[0]

    def rows(self, sql: str, *args: object) -> list[tuple[object, ...]]:
        """Return all rows as tuples."""
        return [tuple(r) for r in self.conn.execute(sql, args)]

    def file_row(self, path: Path) -> dict[str, object]:
        """Return the ``files`` row of a path as a dict."""
        cursor = self.conn.execute("SELECT * FROM files WHERE path = ?", (str(path),))
        row = cursor.fetchone()
        assert row is not None, path
        return {d[0]: v for d, v in zip(cursor.description, row, strict=True)}


Totals = dict[tuple[str, str], tuple[int, int, int, int, int, int]]


def store_totals(conn: sqlite3.Connection) -> Totals:
    """Sum the winners per (session, model): input, output, reads, writes, count."""
    out: Totals = {}
    cursor = conn.execute(
        "SELECT session_id, model, SUM(input), SUM(output), SUM(cache_read),"
        " SUM(cache_write_5m), SUM(cache_write_1h), COUNT(*)"
        " FROM best_winners GROUP BY session_id, model"
    )
    for r in cursor:
        out[(str(r[0]), str(r[1]))] = (r[2], r[3], r[4], r[5], r[6], r[7])
    return out


def totals_of(
    records: Sequence[transcripts.Record], session_of: dict[int, str]
) -> Totals:
    """Sum records per (session, model) the way ``store_totals`` does.

    ``session_of`` maps ``id(record)`` to the session of the file the record is in.
    """
    acc: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    for rec in records:
        cell = acc[(session_of[id(rec)], rec.model_raw or "")]
        for i, value in enumerate(
            (
                rec.input,
                rec.output,
                rec.cache_read,
                rec.cache_write_5m,
                rec.cache_write_1h,
                1,
            )
        ):
            cell[i] += value
    return {k: (v[0], v[1], v[2], v[3], v[4], v[5]) for k, v in acc.items()}


def oracle_totals(config_dir: Path) -> Totals:
    """Re-read every file with the old Reader, dedupe and sum per (session, model)."""
    result = transcripts.Reader(str(config_dir), horizon_days=100000).read(FAR)
    kept, _ = usage.dedupe(result.records)
    return totals_of(kept, {id(r): r.session_id for r in kept})


def expected_minutes(
    conn: sqlite3.Connection, tier: ingest.TierPolicy
) -> dict[tuple[object, ...], tuple[int, ...]]:
    """Rebuild ``minute_usage`` from ``best_winners`` in Python."""
    out: dict[tuple[object, ...], list[int]] = defaultdict(lambda: [0] * 7)
    cursor = conn.execute(
        "SELECT session_id, run_id, ts, model, effort, speed, service_tier,"
        " inference_geo, input, output, cache_read, cache_write_5m, cache_write_1h,"
        " thinking FROM best_winners"
    )
    for r in cursor:
        prompt = r[8] + r[10] + r[11] + r[12]
        cell = (
            r[0], r[1] or "main", r[2][:16], r[3], r[4] or "", r[5] or "", r[6] or "",
            r[7] or "", str(tier.tier_for(r[3], prompt)),
        )  # fmt: skip
        acc = out[cell]
        for i, value in enumerate((r[8], r[9], r[10], r[11], r[12], r[13], 1)):
            acc[i] += value
    return {k: tuple(v) for k, v in out.items()}


def actual_minutes(
    conn: sqlite3.Connection,
) -> dict[tuple[object, ...], tuple[int, ...]]:
    """Read ``minute_usage`` as the same shape ``expected_minutes`` returns."""
    out: dict[tuple[object, ...], tuple[int, ...]] = {}
    for r in conn.execute("SELECT * FROM minute_usage"):
        out[tuple(r[:9])] = tuple(r[9:])
    return out


def copy_tree(src: Path, dst: Path) -> None:
    """Copy a folder tree with file contents and mtimes."""
    import shutil

    shutil.copytree(src, dst, copy_function=shutil.copy2)


def set_old(path: Path, days: int = 100) -> None:
    """Move a file's mtime back, as a stale transcript."""
    then = (FAR - timedelta(days=days)).timestamp()
    os.utime(path, (then, then))
