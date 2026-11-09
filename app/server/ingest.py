"""Transcript ingest into the Bar Tab store, one pass at a time.

``Ingestor.run_pass`` lists the project folders, decides from ``os.stat`` alone which
files changed, reads only the new bytes of those, and writes the rows to SQLite. The
parser, the file kinds and the dedupe rule are the old ones (``transcripts`` and
``usage``). Only the storage and the incremental read are new, as research 26-05
describes.

Everything is written through the one connection it is given, which must be the
writer's (``isolation_level=None``) and must have no open transaction when a pass
starts. A batch is ``BEGIN IMMEDIATE`` and ``COMMIT``. Offsets, ``requests`` rows,
sessions, runs, links, ``run_events``, ``file_state`` and the ``minute_usage`` cells
the batch touched commit together, so a crash never leaves an offset ahead of its
rows.

Rules that keep history safe:

- A row is upserted per ``(file_id, key)``. The larger output wins, then the later
  ``ts``, so a rescan never loses a better snapshot. The winner across files is the
  ``best_winners`` view.
- Nothing is deleted. A file that is gone gets ``missing = 1`` and keeps its rows. A
  file that shrinks, changes inode or fails the head and tail hash is parsed again
  from byte 0 and upserted, and rows whose keys do not come back stay.
- A file that cannot be opened counts in ``files.read_errors`` and is tried again on
  every cold pass. Assistant rows with no usage object count in ``files.no_usage``.
- ``file_state.state`` holds ids, two flags and counters only, never row text.
- ``run_events.by_run`` of a launch row holds the child agent id.

``minute_usage`` is rebuilt cell by cell. A batch collects the message keys it
touched, takes the old winners of those keys before the upsert and the new winners
after it, and marks their ``(session_id, minute)`` cells dirty. Each dirty cell is
deleted and rebuilt from the winners. Keys cross sessions (a resumed session copies
message ids), so a cell is never assumed to hold one session's keys only.
"""

import hashlib
import json
import logging
import os
import sqlite3
import stat
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Literal, NamedTuple, cast

import history
import model_catalog
import prices
import transcripts
from transcripts import FoundFile, LinkState, Record

logger = logging.getLogger(__name__)

PassKind = Literal["full", "cold", "hot"]
IngestCode = Literal["config_dir_missing", "config_dir_unreadable"]

HASH_BYTES = 64
BATCH_ROWS = 50_000
BATCH_READ_BYTES = 64 * 1024 * 1024
KEY_CHUNK = 400
RUNNING_WINDOW = timedelta(minutes=30)
KEEP_PASSES = 1000
KEY_TIER_HASH = "tier_hash"

_UPSERT_REQUEST = (
    "INSERT INTO requests (file_id, key, ts, input, output, cache_read,"
    " cache_write_5m, cache_write_1h, thinking, model, request_id, effort, speed,"
    " service_tier, inference_geo)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    " ON CONFLICT (file_id, key) DO UPDATE SET"
    " ts = excluded.ts, input = excluded.input, output = excluded.output,"
    " cache_read = excluded.cache_read, cache_write_5m = excluded.cache_write_5m,"
    " cache_write_1h = excluded.cache_write_1h, thinking = excluded.thinking,"
    " model = excluded.model, request_id = excluded.request_id,"
    " effort = excluded.effort, speed = excluded.speed,"
    " service_tier = excluded.service_tier, inference_geo = excluded.inference_geo"
    " WHERE (excluded.output, excluded.ts) >= (requests.output, requests.ts)"
)
_WINNER_COLUMNS = (
    "key, session_id, run_id, ts, model, effort, speed, service_tier, inference_geo,"
    " input, output, cache_read, cache_write_5m, cache_write_1h, thinking"
)


class IngestError(Exception):
    """A whole-pass failure about the transcript folder, with a first-run code."""

    def __init__(self, code: IngestCode, file: str | None = None) -> None:
        """Keep the code and the folder path."""
        super().__init__(code if file is None else f"{code}: {file}")
        self.code: IngestCode = code
        self.file = file


class ProgressSink:
    """Receives a pass's progress. The base class ignores everything."""

    def listing(self) -> None:
        """A pass began listing folders. Totals are not known yet."""

    def totals(self, files: int, bytes_: int) -> None:
        """The work of the pass is fixed: files and bytes still to read."""

    def done(self, files: int, bytes_: int) -> None:
        """Files and bytes finished so far in this pass."""

    def has_work(self) -> None:
        """The pass found something to read. Called once, after ``totals``."""


@dataclass(frozen=True)
class TierPolicy:
    """Which price tier a request falls in, and a hash of the thresholds behind it.

    ``tier_for(model, prompt_tokens)`` returns 0 for the base rates and 1 or more
    once the prompt passes a tier's ``prompt_tokens_over``. ``hash`` changes when any
    threshold does, and ``minute_usage`` is rebuilt then.
    """

    tier_for: Callable[[str, int], int]
    hash: str


def _dict(value: object) -> dict[str, object] | None:
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def _thresholds(doc: prices.PricesDoc) -> dict[str, tuple[float, ...]]:
    """Return ``{model id: sorted prompt_tokens_over values}`` for models with tiers."""
    out: dict[str, tuple[float, ...]] = {}
    for model_id, raw_entry in (_dict(doc.get("models")) or {}).items():
        entry = _dict(raw_entry) or {}
        raw_tiers = entry.get("tiers")
        overs: list[float] = []
        for raw_tier in (
            cast("list[object]", raw_tiers) if isinstance(raw_tiers, list) else []
        ):
            over = (_dict(raw_tier) or {}).get("prompt_tokens_over")
            if isinstance(over, int | float) and not isinstance(over, bool):
                overs.append(float(over))
        if overs:
            out[model_id] = tuple(sorted(overs))
    return out


def tier_policy_from_prices(
    doc: prices.PricesDoc, catalog: model_catalog.Catalog
) -> TierPolicy:
    """Build the policy from a prices document, as ``prices.price_parts`` reads it.

    A request is in tier N when its prompt tokens (input, cache read and both cache
    writes) pass N of the model's ``prompt_tokens_over`` thresholds.
    """
    thresholds = _thresholds(doc)
    digest = hashlib.sha256(
        json.dumps(thresholds, sort_keys=True).encode("utf-8")
    ).hexdigest()

    @cache
    def overs_for(model: str) -> tuple[float, ...]:
        model_id, _form = model_catalog.normalize_model(model, catalog)
        return thresholds.get(model_id or "", ())

    def tier_for(model: str, prompt_tokens: int) -> int:
        return sum(1 for over in overs_for(model) if prompt_tokens > over)

    return TierPolicy(tier_for, digest)


def default_tier_policy() -> TierPolicy:
    """Return the policy of ``data/prices-old.json`` and the bundled catalog."""
    return tier_policy_from_prices(prices.load_prices(), model_catalog.load_catalog())


@dataclass(frozen=True)
class PassScope:
    """What one pass covers. ``folders`` None means every project folder."""

    kind: PassKind
    folders: frozenset[str] | None = None

    @property
    def retry_unreadable(self) -> bool:
        """Hot passes leave unreadable files for the next cold pass."""
        return self.kind != "hot"


@dataclass
class PassResult:
    """What a pass did. ``changed`` is True when it wrote any store data."""

    kind: PassKind
    files_seen: int = 0
    files_read: int = 0
    bytes_read: int = 0
    rows_added: int = 0
    rescans: int = 0
    changed: bool = False
    cancelled: bool = False


class _Row(NamedTuple):
    """The columns of a ``files`` row a pass decides from."""

    id: int
    path: str
    folder: str
    dev: int
    inode: int
    size: int
    mtime_ns: int
    offset: int
    head_hash: str | None
    last_line_hash: str | None
    missing: int
    read_errors: int
    agent_type: str | None


@dataclass
class _Work:
    """One file to parse."""

    found: FoundFile
    row: _Row | None
    rescan: bool
    shrink: bool
    start: int
    todo: int


@dataclass
class _Plan:
    """What the listing and the stat-only decision found."""

    work: list[_Work] = field(default_factory=list[_Work])
    touch: list[tuple[FoundFile, _Row]] = field(
        default_factory=list[tuple[FoundFile, _Row]]
    )
    restore: list[int] = field(default_factory=list[int])
    missing: list[int] = field(default_factory=list[int])
    agent_types: list[tuple[int, str]] = field(default_factory=list[tuple[int, str]])
    files_seen: int = 0


@dataclass
class _Batch:
    """The state of the open transaction."""

    touched: set[str] = field(default_factory=set[str])
    cells: set[tuple[str, str]] = field(default_factory=set[tuple[str, str]])
    rows: int = 0
    read_bytes: int = 0


class _Winner(NamedTuple):
    key: str
    session_id: str
    run_id: str | None
    ts: str
    model: str
    effort: str | None
    speed: str | None
    service_tier: str | None
    inference_geo: str | None
    input: int
    output: int
    cache_read: int
    cache_write_5m: int
    cache_write_1h: int
    thinking: int


class _Event(NamedTuple):
    at: str
    kind: str
    finished: int
    by_kind: str | None
    by_run: str | None


def ts_text(moment: datetime) -> str:
    """Return the fixed-width UTC text the store keeps, to the microsecond."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def request_key(record: Record, line_offset: int, file_id: int) -> str:
    """Return the dedupe key of a record.

    The key is the message id, else the request id. A record with neither is kept as
    it is, as the old reader keeps it, so its key holds the file id and the line
    offset: two files can hold id-less records at the same offset, and both count.
    """
    if record.message_id:
        return record.message_id
    if record.request_id:
        return "r|" + record.request_id
    return f"n|{file_id}|{line_offset}"


def _digest(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=16).hexdigest()


def _hashes(path: str, offset: int) -> tuple[str | None, str | None]:
    """Hash the first bytes and the bytes just before ``offset``, or Nones."""
    if offset <= 0:
        return None, None
    size = min(HASH_BYTES, offset)
    try:
        with open(path, "rb") as fh:  # noqa: PTH123 - the parser opens by string path
            head = fh.read(size)
            fh.seek(offset - size)
            tail = fh.read(size)
    except OSError:
        return None, None
    return _digest(head), _digest(tail)


def _chunks(items: Sequence[str], size: int = KEY_CHUNK) -> Iterable[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _marks(count: int) -> str:
    return ",".join("?" * count)


class Ingestor:
    """Runs ingest passes over one Claude config folder into one store connection."""

    def __init__(  # noqa: PLR0913 - one pass's collaborators, keyword-only
        self,
        conn: sqlite3.Connection,
        claude_dir: Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        tier_policy: TierPolicy | None = None,
        progress: ProgressSink | None = None,
        pace: Callable[[], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        batch_rows: int = BATCH_ROWS,
    ) -> None:
        """Keep the connection and the collaborators.

        Args:
            conn: The writer connection, in autocommit mode.
            claude_dir: The Claude config folder. Transcripts are under ``projects/``.
            clock: Returns the current aware time.
            tier_policy: Price tiers for ``minute_usage``. Defaults to the old table.
            progress: Receives listing, totals and done counts.
            pace: Called after each file. The demo sleeps in it.
            cancel: Checked between files. True ends the pass after the open batch.
            batch_rows: Commit once a batch holds this many rows.
        """
        self.conn = conn
        self.claude_dir = claude_dir
        self.clock = clock
        self.tier = tier_policy if tier_policy is not None else default_tier_policy()
        self.progress = progress if progress is not None else ProgressSink()
        self.pace = pace
        self.cancel = cancel
        self.batch_rows = batch_rows

    @property
    def projects_dir(self) -> Path:
        """The folder the project folders sit in."""
        return self.claude_dir / "projects"

    # ------------------------------------------------------------ public

    def running_folders(self, now: datetime) -> frozenset[str]:
        """Return the folders of sessions with a request in the last 30 minutes."""
        cutoff = ts_text(now - RUNNING_WINDOW)
        rows = self.conn.execute(
            "SELECT DISTINCT folder FROM sessions WHERE last_ts >= ?", (cutoff,)
        ).fetchall()
        return frozenset(str(r[0]) for r in rows)

    def run_pass(self, scope: PassScope) -> PassResult:
        """Run one pass and return what it did.

        Raises:
            IngestError: The projects folder is missing or cannot be read.
            sqlite3.Error: A store write failed. The open batch is rolled back.
        """
        if self.conn.in_transaction:
            msg = "run_pass needs a connection with no open transaction"
            raise ValueError(msg)
        result = PassResult(scope.kind)
        started = history.utc_text(self.clock())
        self.progress.listing()
        self._check_tier_hash(result)
        plan = self._plan(scope)
        result.files_seen = plan.files_seen
        files_total = len(plan.work)
        bytes_total = sum(w.todo for w in plan.work)
        self.progress.totals(files_total, bytes_total)
        if plan.work:
            self.progress.has_work()
        self._housekeeping(plan, result)
        self._read_all(plan, result)
        if result.changed:
            self._checkpoint()
        if scope.kind == "full" or result.files_read or result.rescans:
            self._record_pass(result, started)
        return result

    # ------------------------------------------------------------ tier table

    def _check_tier_hash(self, result: PassResult) -> None:
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = ?", (KEY_TIER_HASH,)
        ).fetchone()
        if row is not None and row[0] == self.tier.hash:
            return
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute("DELETE FROM minute_usage")
            cells = {
                (str(r[0]), str(r[1]))
                for r in self.conn.execute(
                    "SELECT DISTINCT f.session_id, substr(r.ts, 1, 16)"
                    " FROM requests AS r JOIN files AS f ON f.id = r.file_id"
                    " WHERE f.session_id IS NOT NULL"
                )
            }
            self._rebuild_cells(cells)
            self.conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?)"
                " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (KEY_TIER_HASH, self.tier.hash),
            )
        except BaseException:
            self._rollback()
            raise
        self.conn.execute("COMMIT")
        result.changed = result.changed or bool(row is not None)

    # ------------------------------------------------------------ listing

    def _top_folders(self, scope: PassScope) -> tuple[list[str], bool]:
        """Return the folder names to scan, and whether this is the full listing."""
        projects = self.projects_dir
        try:
            mode = os.stat(projects).st_mode  # noqa: PTH116
        except PermissionError as exc:
            raise IngestError("config_dir_unreadable", str(projects)) from exc
        except OSError as exc:
            raise IngestError("config_dir_missing", str(projects)) from exc
        if not stat.S_ISDIR(mode):
            raise IngestError("config_dir_missing", str(projects))
        if scope.folders is not None:
            return sorted(scope.folders), False
        try:
            with os.scandir(projects) as it:
                entries = list(it)
        except PermissionError as exc:
            raise IngestError("config_dir_unreadable", str(projects)) from exc
        except OSError as exc:
            raise IngestError("config_dir_missing", str(projects)) from exc
        names = sorted(
            e.name
            for e in entries
            if not e.is_symlink() and e.is_dir(follow_symlinks=False)
        )
        return names, True

    def _load_rows(self, folders: Sequence[str] | None) -> dict[str, _Row]:
        sql = (
            "SELECT f.id, f.path, f.folder, f.dev, f.inode, f.size, f.mtime_ns,"
            ' f."offset", f.head_hash, f.last_line_hash, f.missing, f.read_errors,'
            " r.agent_type FROM files AS f"
            " LEFT JOIN runs AS r ON r.file_id = f.id"
        )
        rows: dict[str, _Row] = {}
        if folders is None:
            cursor = self.conn.execute(sql)
            for r in cursor:
                rows[str(r[1])] = _Row(*r)
            return rows
        for chunk in _chunks(list(folders), 500):
            cursor = self.conn.execute(
                f"{sql} WHERE f.folder IN ({_marks(len(chunk))})",
                tuple(chunk),
            )
            for r in cursor:
                rows[str(r[1])] = _Row(*r)
        return rows

    def _plan(self, scope: PassScope) -> _Plan:
        """List and stat the folders and decide, per file, what to do."""
        names, full_listing = self._top_folders(scope)
        rows = self._load_rows(None if full_listing else names)
        plan = _Plan()
        found_paths: set[str] = set()
        listed: set[str] = set()
        unlisted: set[str] = set()
        for name in names:
            files = transcripts.scan_folder(str(self.projects_dir / name), name)
            if files is None:
                unlisted.add(name)
                continue
            listed.add(name)
            for item in sorted(files, key=lambda f: f.path):
                found_paths.add(item.path)
                plan.files_seen += 1
                self._decide(item, rows.get(item.path), scope, plan)
        top_names = set(names)
        for path, row in rows.items():
            if row.missing or path in found_paths:
                continue
            if row.folder in listed or (
                full_listing
                and row.folder not in top_names
                and row.folder not in unlisted
            ):
                plan.missing.append(row.id)
        return plan

    def _decide(
        self, item: FoundFile, row: _Row | None, scope: PassScope, plan: _Plan
    ) -> None:
        st = item.st
        if row is None:
            plan.work.append(
                _Work(item, None, rescan=False, shrink=False, start=0, todo=st.st_size)
            )
            return
        same_identity = (
            row.dev == st.st_dev
            and row.inode == st.st_ino
            and row.size == st.st_size
            and row.mtime_ns == st.st_mtime_ns
        )
        retry = row.read_errors > 0 and scope.retry_unreadable
        if same_identity and not retry:
            if row.missing:
                plan.restore.append(row.id)
            if (
                item.kind == transcripts.AGENT
                and row.agent_type is None
                and scope.retry_unreadable
            ):
                found_type = transcripts.read_agent_type(item.meta_path)
                if found_type is not None:
                    plan.agent_types.append((row.id, found_type))
            return
        shrink = st.st_size < row.size
        rescan = (
            row.dev != st.st_dev
            or row.inode != st.st_ino
            or st.st_size < row.offset
            or not self._hashes_match(item.path, row)
        )
        start = 0 if rescan else row.offset
        todo = st.st_size - start
        if not rescan and todo <= 0 and row.read_errors == 0:
            plan.touch.append((item, row))
            return
        plan.work.append(_Work(item, row, rescan, shrink, start, max(todo, 0)))

    @staticmethod
    def _hashes_match(path: str, row: _Row) -> bool:
        if row.offset <= 0 or row.head_hash is None:
            return True
        head, tail = _hashes(path, row.offset)
        return head == row.head_hash and tail == row.last_line_hash

    # ------------------------------------------------------------ small writes

    def _housekeeping(self, plan: _Plan, result: PassResult) -> None:
        """Write the flags and stat updates that need no parse, in one transaction."""
        if not (plan.missing or plan.restore or plan.touch or plan.agent_types):
            return
        now = history.utc_text(self.clock())
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.executemany(
                "UPDATE files SET missing = 1 WHERE id = ?",
                [(i,) for i in plan.missing],
            )
            self.conn.executemany(
                "UPDATE files SET missing = 0, last_seen = ? WHERE id = ?",
                [(now, i) for i in plan.restore],
            )
            self.conn.executemany(
                "UPDATE files SET dev = ?, inode = ?, size = ?, mtime_ns = ?,"
                " missing = 0, last_seen = ? WHERE id = ?",
                [
                    (
                        f.st.st_dev,
                        f.st.st_ino,
                        f.st.st_size,
                        f.st.st_mtime_ns,
                        now,
                        r.id,
                    )
                    for f, r in plan.touch
                ],
            )
            self.conn.executemany(
                "UPDATE runs SET agent_type = ? WHERE file_id = ?",
                [(t, i) for i, t in plan.agent_types],
            )
        except BaseException:
            self._rollback()
            raise
        self.conn.execute("COMMIT")
        result.changed = True

    # ------------------------------------------------------------ reading

    def _read_all(self, plan: _Plan, result: PassResult) -> None:
        batch: _Batch | None = None
        done_files = done_bytes = 0
        try:
            for work in plan.work:
                if self.cancel is not None and self.cancel():
                    result.cancelled = True
                    break
                if batch is None:
                    self.conn.execute("BEGIN IMMEDIATE")
                    batch = _Batch()
                self._read_file(work, batch, result)
                result.files_read += 1
                done_files += 1
                done_bytes += work.todo
                self.progress.done(done_files, done_bytes)
                if self.pace is not None:
                    self.pace()
                if (
                    batch.rows >= self.batch_rows
                    or batch.read_bytes >= BATCH_READ_BYTES
                ):
                    self._finish_batch(batch)
                    batch = None
            if batch is not None:
                self._finish_batch(batch)
                batch = None
        except BaseException:
            self._rollback()
            raise
        result.bytes_read = done_bytes

    def _finish_batch(self, batch: _Batch) -> None:
        keys = sorted(batch.touched)
        for chunk in _chunks(keys):
            for winner in self._winners(chunk):
                batch.cells.add((winner.session_id, winner.ts[:16]))
        self._rebuild_cells(batch.cells)
        self.conn.execute("COMMIT")

    def _rollback(self) -> None:
        if self.conn.in_transaction:
            self.conn.execute("ROLLBACK")

    def _read_file(self, work: _Work, batch: _Batch, result: PassResult) -> None:
        item, row = work.found, work.row
        now = history.utc_text(self.clock())
        agent_type: str | None = row.agent_type if row is not None else None
        if item.kind == transcripts.AGENT and agent_type is None:
            agent_type = transcripts.read_agent_type(item.meta_path)
        resume: LinkState | None = None
        if row is not None and not work.rescan and work.start > 0:
            resume = self._stored_state(row.id)
            if resume is None:  # no usable state for this offset: start over
                work.rescan, work.start = True, 0
        parsed = transcripts.parse_file(
            item.path,
            item.kind,
            work.start,
            resume,
            agent_type,
            folder=item.folder,
            session_id=item.session_id,
            run_id=item.run_id,
        )
        if parsed.end_offset is None:
            self._note_read_error(work, now)
            result.changed = True
            return
        if work.rescan:
            result.rescans += 1
        file_id = self._file_id(work, now)
        keys = [
            request_key(r, o, file_id)
            for r, o in zip(parsed.records, parsed.line_offsets, strict=True)
        ]
        self._remember_old_winners(keys, batch)
        before = self.conn.total_changes
        self.conn.executemany(
            _UPSERT_REQUEST,
            [
                self._request_row(file_id, k, r)
                for k, r in zip(keys, parsed.records, strict=True)
            ],
        )
        changed_rows = self.conn.total_changes - before
        batch.touched.update(keys)
        batch.rows += len(keys)
        batch.read_bytes += max(parsed.end_offset - work.start, 0)
        result.rows_added += changed_rows
        self._write_session(item, parsed.records)
        if item.kind == transcripts.AGENT and item.run_id is not None:
            self._write_run(file_id, item, agent_type)
        self._write_links(file_id, item, parsed.link_state)
        self._write_events(file_id, item, parsed.link_state, rescan=work.rescan)
        self._write_file_row(work, file_id, parsed, now)
        result.changed = True

    def _stored_state(self, file_id: int) -> LinkState | None:
        """Return the stored link state of a file, or None when it is missing or bad."""
        row = self.conn.execute(
            "SELECT state FROM file_state WHERE file_id = ?", (file_id,)
        ).fetchone()
        if row is None:
            return None
        try:
            data = _dict(json.loads(str(row[0])))
        except ValueError:
            return None
        return None if data is None else LinkState.from_state(data)

    def _note_read_error(self, work: _Work, now: str) -> None:
        item, row = work.found, work.row
        if row is None:
            st = item.st
            self.conn.execute(
                "INSERT INTO files (path, kind, folder, session_id, run_id, dev, inode,"
                " size, mtime_ns, read_errors, first_seen, last_seen)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (
                    item.path, item.kind, item.folder, item.session_id, item.run_id,
                    st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, now, now,
                ),
            )  # fmt: skip
            return
        self.conn.execute(
            "UPDATE files SET read_errors = read_errors + 1, last_seen = ?"
            " WHERE id = ?",
            (now, row.id),
        )

    def _file_id(self, work: _Work, now: str) -> int:
        item, row = work.found, work.row
        if row is not None:
            return row.id
        st = item.st
        cursor = self.conn.execute(
            "INSERT INTO files (path, kind, folder, session_id, run_id, dev, inode,"
            " size, mtime_ns, first_seen, last_seen)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.path, item.kind, item.folder, item.session_id, item.run_id,
                st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, now, now,
            ),
        )  # fmt: skip
        return int(cursor.lastrowid or 0)

    @staticmethod
    def _request_row(file_id: int, key: str, rec: Record) -> tuple[object, ...]:
        return (
            file_id, key, ts_text(rec.ts_utc), rec.input, rec.output, rec.cache_read,
            rec.cache_write_5m, rec.cache_write_1h, rec.thinking or 0,
            rec.model_raw or "", rec.request_id, rec.effort, rec.speed,
            rec.service_tier, rec.inference_geo,
        )  # fmt: skip

    def _write_session(self, item: FoundFile, records: list[Record]) -> None:
        first = min(records, key=lambda r: r.ts_utc, default=None)
        last = max(records, key=lambda r: r.ts_utc, default=None)
        first_ts = ts_text(first.ts_utc) if first is not None else None
        last_ts = ts_text(last.ts_utc) if last is not None else None
        cwd = next(
            (r.cwd for r in sorted(records, key=lambda r: r.ts_utc) if r.cwd), None
        )
        branch = next(
            (
                r.git_branch
                for r in sorted(records, key=lambda r: r.ts_utc)
                if r.git_branch
            ),
            None,
        )
        self.conn.execute(
            "INSERT INTO sessions (session_id, folder, first_ts, last_ts, cwd, branch)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (session_id) DO UPDATE SET"
            " first_ts = CASE WHEN excluded.first_ts IS NOT NULL AND"
            "   (sessions.first_ts IS NULL OR excluded.first_ts < sessions.first_ts)"
            "   THEN excluded.first_ts ELSE sessions.first_ts END,"
            " last_ts = CASE WHEN excluded.last_ts IS NOT NULL AND"
            "   (sessions.last_ts IS NULL OR excluded.last_ts > sessions.last_ts)"
            "   THEN excluded.last_ts ELSE sessions.last_ts END,"
            " cwd = CASE WHEN excluded.cwd IS NOT NULL AND (sessions.cwd IS NULL OR"
            "   excluded.first_ts < sessions.first_ts)"
            "   THEN excluded.cwd ELSE sessions.cwd END,"
            " branch = CASE WHEN excluded.branch IS NOT NULL AND"
            "   (sessions.branch IS NULL OR excluded.first_ts < sessions.first_ts)"
            "   THEN excluded.branch ELSE sessions.branch END",
            (item.session_id, item.folder, first_ts, last_ts, cwd, branch),
        )

    def _write_run(self, file_id: int, item: FoundFile, agent_type: str | None) -> None:
        self.conn.execute(
            "INSERT INTO runs (session_id, run_id, file_id, agent_type)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT (session_id, run_id) DO UPDATE SET"
            " file_id = excluded.file_id,"
            " agent_type = COALESCE(excluded.agent_type, runs.agent_type)",
            (item.session_id, item.run_id, file_id, agent_type),
        )
        self.conn.execute(
            "UPDATE links SET resolved = 1"
            " WHERE session_id = ? AND child_id = ? AND resolved = 0",
            (item.session_id, item.run_id),
        )

    def _write_links(self, file_id: int, item: FoundFile, state: LinkState) -> None:
        self.conn.executemany(
            "INSERT OR IGNORE INTO links (parent_file_id, child_id, session_id, ts,"
            " resolved) VALUES (?, ?, ?, ?, EXISTS (SELECT 1 FROM runs"
            " WHERE session_id = ? AND run_id = ?))",
            [
                (file_id, child, item.session_id, ts_text(at), item.session_id, child)
                for child, at in state.launched
            ],
        )

    def _write_events(
        self, file_id: int, item: FoundFile, state: LinkState, *, rescan: bool
    ) -> None:
        run_key = (
            item.run_id if item.kind == transcripts.AGENT and item.run_id else "main"
        )
        events = [
            _Event(ts_text(at), "launch", 0, None, child)
            for child, at in state.launched
        ]
        events += [
            _Event(ts_text(at), "brief", 0, str(kind), by)
            for at, kind, by in state.rounds
        ]
        events += [
            _Event(ts_text(at), "stop", 1 if finished else 0, None, None)
            for at, finished in state.stops
        ]
        if not events:
            return
        events.sort(key=lambda e: e.at)
        if rescan:
            known = {
                _Event(str(r[0]), str(r[1]), int(r[2]), r[3], r[4])
                for r in self.conn.execute(
                    "SELECT at, kind, finished, by_kind, by_run FROM run_events"
                    " WHERE file_id = ?",
                    (file_id,),
                )
            }
            events = [e for e in events if e not in known]
        row = self.conn.execute(
            "SELECT COALESCE(MAX(seq), -1) FROM run_events WHERE file_id = ?",
            (file_id,),
        ).fetchone()
        seq = int(row[0]) + 1
        self.conn.executemany(
            "INSERT INTO run_events (file_id, seq, session_id, run_key, kind, at,"
            " finished, by_kind, by_run) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (file_id, seq + i, item.session_id, run_key, e.kind, e.at, e.finished,
                 e.by_kind, e.by_run)
                for i, e in enumerate(events)
            ],
        )  # fmt: skip

    def _write_file_row(
        self, work: _Work, file_id: int, parsed: transcripts.FileParse, now: str
    ) -> None:
        st = work.found.st
        end = parsed.end_offset or 0
        head, tail = _hashes(work.found.path, end)
        stats = parsed.stats
        replace = work.rescan or work.row is None
        row = work.row
        base = {"malformed": 0, "synthetic": 0, "no_id": 0, "no_usage": 0}
        if not replace and row is not None:
            old = self.conn.execute(
                "SELECT malformed, synthetic, no_id, no_usage FROM files WHERE id = ?",
                (file_id,),
            ).fetchone()
            base = dict(zip(base, (int(v) for v in old), strict=True))
        self.conn.execute(
            "UPDATE files SET dev = ?, inode = ?, size = ?, mtime_ns = ?,"
            ' "offset" = ?, head_hash = ?, last_line_hash = ?, malformed = ?,'
            " synthetic = ?, no_id = ?, no_usage = ?, missing = 0, read_errors = 0,"
            " scans = scans + ?, shrinks = shrinks + ?, last_seen = ? WHERE id = ?",
            (
                st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, end, head, tail,
                base["malformed"] + stats["malformed"],
                base["synthetic"] + stats["synthetic"],
                base["no_id"] + stats["no_id"],
                base["no_usage"] + stats["no_usage"],
                1 if replace else 0, 1 if work.shrink else 0, now, file_id,
            ),
        )  # fmt: skip
        self.conn.execute(
            'INSERT INTO file_state (file_id, "offset", state) VALUES (?, ?, ?)'
            ' ON CONFLICT (file_id) DO UPDATE SET "offset" = excluded."offset",'
            " state = excluded.state",
            (
                file_id,
                end,
                json.dumps(parsed.link_state.export_state(), separators=(",", ":")),
            ),
        )

    # ------------------------------------------------------------ minute_usage

    def _winners(self, keys: Sequence[str]) -> list[_Winner]:
        if not keys:
            return []
        cursor = self.conn.execute(
            f"SELECT {_WINNER_COLUMNS} FROM best_winners"  # noqa: S608
            f" WHERE key IN ({_marks(len(keys))})",
            tuple(keys),
        )
        return [_Winner(*r) for r in cursor]

    def _remember_old_winners(self, keys: Sequence[str], batch: _Batch) -> None:
        fresh = [k for k in dict.fromkeys(keys) if k not in batch.touched]
        for chunk in _chunks(fresh):
            for winner in self._winners(chunk):
                batch.cells.add((winner.session_id, winner.ts[:16]))

    def _session_files(self, sessions: list[str]) -> dict[str, list[int]]:
        """Return the file ids of each session, from one scan of ``files``."""
        out: dict[str, list[int]] = {}
        for chunk in _chunks(sessions, 500):
            cursor = self.conn.execute(
                f"SELECT session_id, id FROM files"  # noqa: S608
                f" WHERE session_id IN ({_marks(len(chunk))})",
                tuple(chunk),
            )
            for session_id, file_id in cursor:
                out.setdefault(str(session_id), []).append(int(file_id))
        return out

    def _candidate_keys(self, file_ids: list[int], low: str, high: str) -> list[str]:
        """Return the keys of rows in the files whose minute is between two minutes."""
        keys: dict[str, None] = {}
        for start in range(0, len(file_ids), 500):
            chunk = file_ids[start : start + 500]
            cursor = self.conn.execute(
                f"SELECT DISTINCT key FROM requests"  # noqa: S608
                f" WHERE file_id IN ({_marks(len(chunk))})"
                " AND substr(ts, 1, 16) BETWEEN ? AND ?",
                (*chunk, low, high),
            )
            keys.update((str(r[0]), None) for r in cursor)
        return list(keys)

    def _rebuild_cells(self, cells: set[tuple[str, str]]) -> None:
        """Delete each dirty cell and rebuild it from the winners of its keys."""
        if not cells:
            return
        by_session: dict[str, set[str]] = {}
        for session_id, minute in cells:
            by_session.setdefault(session_id, set()).add(minute)
        files_of = self._session_files(list(by_session))
        for session_id, minutes in by_session.items():
            self.conn.executemany(
                "DELETE FROM minute_usage WHERE session_id = ? AND minute = ?",
                [(session_id, m) for m in minutes],
            )
            candidates = self._candidate_keys(
                files_of.get(session_id, []), min(minutes), max(minutes)
            )
            sums: dict[tuple[str, ...], list[int]] = {}
            for chunk in _chunks(candidates):
                for w in self._winners(chunk):
                    minute = w.ts[:16]
                    if w.session_id != session_id or minute not in minutes:
                        continue
                    prompt = (
                        w.input + w.cache_read + w.cache_write_5m + w.cache_write_1h
                    )
                    cell = (
                        session_id, w.run_id or "main", minute, w.model,
                        w.effort or "", w.speed or "", w.service_tier or "",
                        w.inference_geo or "", str(self.tier.tier_for(w.model, prompt)),
                    )  # fmt: skip
                    acc = sums.setdefault(cell, [0, 0, 0, 0, 0, 0, 0])
                    for i, value in enumerate(
                        (w.input, w.output, w.cache_read, w.cache_write_5m,
                         w.cache_write_1h, w.thinking, 1)
                    ):  # fmt: skip
                        acc[i] += value
            self.conn.executemany(
                "INSERT INTO minute_usage (session_id, run_key, minute, model, effort,"
                " speed, service_tier, inference_geo, tier, input, output, cache_read,"
                " cache_write_5m, cache_write_1h, thinking, requests)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(*cell, *acc) for cell, acc in sums.items()],
            )

    # ------------------------------------------------------------ bookkeeping

    def _checkpoint(self) -> None:
        try:
            self.conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchall()
        except sqlite3.Error:
            logger.warning("wal checkpoint failed")

    def _record_pass(self, result: PassResult, started: str) -> None:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute(
                "INSERT INTO passes (kind, started, finished, files_seen, files_read,"
                " bytes_read, rows_added, rescans, error_code)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    result.kind, started, history.utc_text(self.clock()),
                    result.files_seen, result.files_read, result.bytes_read,
                    result.rows_added, result.rescans,
                ),
            )  # fmt: skip
            self.conn.execute(
                "DELETE FROM passes WHERE id <= (SELECT MAX(id) FROM passes) - ?",
                (KEEP_PASSES,),
            )
        except BaseException:
            self._rollback()
            raise
        self.conn.execute("COMMIT")
