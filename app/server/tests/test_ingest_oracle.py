"""The ingest oracle, a seeded hypothesis state machine.

It appends rows, writes half lines and finishes them, adds link rows and agent files
in both orders, truncates, swaps inodes, deletes files and plants message ids that
another session already holds. After a pass the store must equal the old reader:

- the winners' totals per session and model equal ``usage.dedupe`` over what the old
  ``transcripts.Reader`` reads from each file, plus the rows the store keeps for a
  file that was cut or deleted (the model remembers every row of a file by its best
  snapshot, as the store's upsert does);
- ``minute_usage`` equals a rebuild from ``best_winners``;
- the launches, rounds and stops in ``run_events`` equal the old ``Links`` of a file
  that was never cut, deleted or replaced, and contain them for the others.
"""

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, rule

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import ingest_helpers as h
from ingest_helpers import Config, Store

import transcripts
import usage

SESSIONS = (h.S1, h.S2, h.S3)
RUNS = ("a1", "a2")
FileId = tuple[str, str | None]

ROW = st.tuples(
    st.integers(0, 7),
    st.integers(0, 80),
    st.integers(0, 150),
    st.sampled_from(["use", "use", "use", "no_usage", "request_id"]),
)
AGENT_ROW = st.sampled_from(["stop", "tool", "handback", "brief", "human"])


class IngestMachine(RuleBasedStateMachine):
    """Mutates a fake config folder and checks the store against the old reader."""

    def __init__(self) -> None:
        super().__init__()
        self.base = Path(tempfile.mkdtemp(prefix="ingest-oracle-"))
        self.config = Config(self.base)
        self.store = Store(self.base, self.config)
        self.t = 0.0
        self.serial = 0
        self.pending: dict[FileId, bytes] = {}
        self.history: set[FileId] = set()  # files cut, replaced, deleted or re-made
        self.kept: dict[FileId, dict[str, transcripts.Record]] = {}
        self.floor = (0, 0)

    # ------------------------------------------------------------ helpers

    def path(self, fid: FileId) -> Path:
        sid, run = fid
        return self.config.main(sid) if run is None else self.config.agent(run, sid)

    def ensure(self, fid: FileId) -> Path:
        path = self.path(fid)
        if not path.exists():
            self.config.write(path, [])
            if self.path(fid) in {self.path(f) for f in self.kept}:
                self.history.add(fid)
        return path

    def settle(self, fid: FileId) -> None:
        """Finish a half-written line before anything else is appended."""
        rest = self.pending.pop(fid, None)
        if rest is not None and self.path(fid).exists():
            with self.path(fid).open("ab") as fh:
                fh.write(rest + b"\n")

    def row(self, spec: tuple[int, int, int, str], sid: str) -> bytes:
        idx, out, dt, kind = spec
        self.t += dt
        if kind == "no_usage":
            return h.assistant(self.t, f"m{idx}", sid=sid, usage_obj=False)
        if kind == "request_id":
            return h.assistant(self.t, None, sid=sid, req=f"r{idx}", out=out)
        return h.assistant(self.t, f"m{idx}", sid=sid, out=out, inp=idx + 1)

    def agent_row(self, kind: str, sid: str) -> bytes:
        self.t += 5
        self.serial += 1
        mid = f"ev{self.serial}"
        if kind == "stop":
            return h.assistant(self.t, mid, sid=sid, stop="end_turn")
        if kind == "tool":
            return h.assistant(self.t, mid, sid=sid, tools=["Read"])
        if kind == "handback":
            return h.assistant(self.t, mid, sid=sid, tools=["SubagentHandback"])
        return h.brief_row(self.t, "human" if kind == "human" else "coordinator", sid)

    def maybe_sync(self, sync: bool) -> None:
        if sync:
            self.sync()

    # ------------------------------------------------------------ rules

    @initialize()
    def start(self) -> None:
        self.config.write(self.config.main(h.S1), [h.assistant(0, "m0", sid=h.S1)])

    @rule(
        sid=st.sampled_from(SESSIONS),
        rows=st.lists(ROW, min_size=1, max_size=4),
        sync=st.booleans(),
    )
    def append_rows(
        self, sid: str, rows: list[tuple[int, int, int, str]], sync: bool
    ) -> None:
        fid = (sid, None)
        path = self.ensure(fid)
        self.settle(fid)
        self.config.append(path, [self.row(r, sid) for r in rows])
        self.maybe_sync(sync)

    @rule(
        sid=st.sampled_from(SESSIONS),
        spec=ROW,
        cut=st.integers(5, 60),
        sync=st.booleans(),
    )
    def half_line(
        self, sid: str, spec: tuple[int, int, int, str], cut: int, sync: bool
    ) -> None:
        fid = (sid, None)
        path = self.ensure(fid)
        self.settle(fid)
        line = self.row(spec, sid)
        self.config.append(path, [line[:cut]], end=b"")
        self.pending[fid] = line[cut:]
        self.maybe_sync(sync)

    @rule(sid=st.sampled_from(SESSIONS), sync=st.booleans())
    def finish_line(self, sid: str, sync: bool) -> None:
        self.settle((sid, None))
        self.maybe_sync(sync)

    @rule(sid=st.sampled_from(SESSIONS), run=st.sampled_from(RUNS), sync=st.booleans())
    def link_row(self, sid: str, run: str, sync: bool) -> None:
        fid = (sid, None)
        path = self.ensure(fid)
        self.settle(fid)
        self.t += 3
        self.config.append(path, [h.link_row(self.t, run, sid)])
        self.maybe_sync(sync)

    @rule(
        sid=st.sampled_from(SESSIONS),
        run=st.sampled_from(RUNS),
        rows=st.lists(ROW, min_size=1, max_size=3),
        typed=st.booleans(),
        sync=st.booleans(),
    )
    def agent_file(
        self,
        sid: str,
        run: str,
        rows: list[tuple[int, int, int, str]],
        typed: bool,
        sync: bool,
    ) -> None:
        fid = (sid, run)
        path = self.ensure(fid)
        self.settle(fid)
        self.config.append(path, [self.row(r, sid) for r in rows])
        if typed:
            self.config.meta(run, f"type-{run}", sid)
        self.maybe_sync(sync)

    @rule(
        sid=st.sampled_from(SESSIONS),
        run=st.sampled_from(RUNS),
        kinds=st.lists(AGENT_ROW, min_size=1, max_size=4),
        sync=st.booleans(),
    )
    def agent_events(self, sid: str, run: str, kinds: list[str], sync: bool) -> None:
        fid = (sid, run)
        path = self.ensure(fid)
        self.settle(fid)
        self.config.append(path, [self.agent_row(k, sid) for k in kinds])
        self.maybe_sync(sync)

    @rule(
        sid=st.sampled_from(SESSIONS),
        run=st.sampled_from((None, *RUNS)),
        keep=st.floats(0, 1),
        sync=st.booleans(),
    )
    def truncate(self, sid: str, run: str | None, keep: float, sync: bool) -> None:
        fid = (sid, run)
        path = self.path(fid)
        if not path.exists():
            return
        self.pending.pop(fid, None)
        lines = [x for x in path.read_bytes().split(b"\n")[:-1]]
        size = sum(len(x) + 1 for x in lines[: int(len(lines) * keep)])
        with path.open("r+b") as fh:
            fh.truncate(size)
        self.history.add(fid)
        self.maybe_sync(sync)

    @rule(
        sid=st.sampled_from(SESSIONS),
        run=st.sampled_from((None, *RUNS)),
        keep=st.floats(0, 1),
        rows=st.lists(ROW, max_size=3),
        sync=st.booleans(),
    )
    def replace_inode(
        self,
        sid: str,
        run: str | None,
        keep: float,
        rows: list[tuple[int, int, int, str]],
        sync: bool,
    ) -> None:
        fid = (sid, run)
        path = self.path(fid)
        if not path.exists():
            return
        self.pending.pop(fid, None)
        lines = path.read_bytes().split(b"\n")[:-1]
        fresh = lines[: int(len(lines) * keep)] + [self.row(r, sid) for r in rows]
        tmp = path.with_name("swap.tmp")
        self.config.write(tmp, fresh)
        tmp.replace(path)
        self.history.add(fid)
        self.maybe_sync(sync)

    @rule(
        sid=st.sampled_from(SESSIONS),
        run=st.sampled_from((None, *RUNS)),
        sync=st.booleans(),
    )
    def delete(self, sid: str, run: str | None, sync: bool) -> None:
        fid = (sid, run)
        path = self.path(fid)
        if path.exists():
            path.unlink()
            self.pending.pop(fid, None)
            self.history.add(fid)
        self.maybe_sync(sync)

    @rule(
        src=st.sampled_from(SESSIONS),
        dst=st.sampled_from(SESSIONS),
        better=st.booleans(),
        sync=st.booleans(),
    )
    def plant_copy(self, src: str, dst: str, better: bool, sync: bool) -> None:
        """Copy a message id another session holds, as a resumed session does."""
        held = [
            key
            for fid, rows in self.kept.items()
            if fid[0] == src
            for key in rows
            if not key.startswith("r|")
        ]
        if not held:
            return
        key = sorted(held)[0]
        fid = (dst, None)
        path = self.ensure(fid)
        self.settle(fid)
        self.t += 1
        out = 500 if better else 1
        self.config.append(path, [h.assistant(self.t, key, sid=dst, out=out)])
        self.maybe_sync(sync)

    @rule()
    def ingest_now(self) -> None:
        self.sync()

    # ------------------------------------------------------------ the oracle

    def absorb(self) -> None:
        """Remember each file's best snapshots, as the store's upsert does."""
        result = transcripts.Reader(str(self.config.dir), horizon_days=100000).read(
            h.FAR
        )
        for rec in result.records:
            fid = (rec.session_id, rec.run_id)
            key = rec.message_id or f"r|{rec.request_id}"
            rows = self.kept.setdefault(fid, {})
            old = rows.get(key)
            if old is None or (rec.output, rec.ts_utc) >= (old.output, old.ts_utc):
                rows[key] = rec

    def expected_totals(self) -> h.Totals:
        ordered = sorted(self.kept, key=lambda f: str(self.path(f)))
        records: list[transcripts.Record] = []
        session_of: dict[int, str] = {}
        for fid in ordered:
            for rec in self.kept[fid].values():
                records.append(rec)
                session_of[id(rec)] = fid[0]
        winners, _ = usage.dedupe(records)
        return h.totals_of(winners, session_of)

    def sync(self) -> None:
        self.store.run()
        self.absorb()
        conn = self.store.conn
        assert h.store_totals(conn) == self.expected_totals()
        assert h.actual_minutes(conn) == h.expected_minutes(
            conn, self.store.ingestor.tier
        )
        self.check_events(conn)
        counts = (
            int(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]),
            int(conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]),
        )
        assert counts[0] >= self.floor[0], "a row was deleted"
        assert counts[1] >= self.floor[1], "a file row was deleted"
        self.floor = counts
        # nothing left to read: a second pass is a no-op
        assert not self.store.run().changed

    def check_events(self, conn: sqlite3.Connection) -> None:
        reader = transcripts.Reader(str(self.config.dir), horizon_days=100000)
        links = reader.read_folder(h.FOLDER, h.FAR).links or {}
        for (sid, run), old in links.items():
            run_key = run or "main"
            rows = conn.execute(
                "SELECT kind, at, finished, by_kind, by_run FROM run_events"
                " WHERE session_id = ? AND run_key = ?",
                (sid, run_key),
            ).fetchall()
            stored = (
                {(r[4], r[1]) for r in rows if r[0] == "launch"},
                {(r[1], r[3], r[4]) for r in rows if r[0] == "brief"},
                {(r[1], bool(r[2])) for r in rows if r[0] == "stop"},
            )
            want = (
                {(c, h_ts(t)) for c, t in old.launched},
                {(h_ts(t), k, b) for t, k, b in old.rounds},
                {(h_ts(t), f) for t, f in old.stops},
            )
            if (sid, run) in self.history:
                assert want[0] <= stored[0]
                assert want[1] <= stored[1]
                assert want[2] <= stored[2]
            else:
                assert want == stored, (sid, run)
            launched = {
                r[0]
                for r in conn.execute(
                    "SELECT child_id FROM links JOIN files ON files.id = parent_file_id"
                    " WHERE files.path = ?",
                    (str(self.path((sid, run))),),
                )
            }
            if (sid, run) in self.history:
                assert {c for c, _t in old.launched} <= launched
            else:
                assert {c for c, _t in old.launched} == launched
        bad = conn.execute(
            "SELECT COUNT(*) FROM links AS l WHERE l.resolved != EXISTS ("
            " SELECT 1 FROM runs AS r WHERE r.session_id = l.session_id"
            " AND r.run_id = l.child_id)"
        ).fetchone()[0]
        assert bad == 0, "a link is resolved or unresolved against its agent file"

    def teardown(self) -> None:
        try:
            self.sync()
        finally:
            self.store.close()
            shutil.rmtree(self.base, ignore_errors=True)


def h_ts(moment: object) -> str:
    import ingest

    return ingest.ts_text(moment)  # pyright: ignore[reportArgumentType]


IngestMachine.TestCase.settings = settings(
    derandomize=True,
    max_examples=20,
    stateful_step_count=18,
    deadline=None,
    suppress_health_check=list(HealthCheck),  # pyright: ignore[reportArgumentType]
)
TestIngestOracle = IngestMachine.TestCase
