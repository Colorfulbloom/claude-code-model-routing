"""Transcript reader for the usage views.

It finds Claude Code transcript files under ``<config_dir>/projects``, turns each
assistant row into a ``Record`` from a fixed list of fields, and drops the row.
No message text, tool data or agent description is kept. A line is parsed in
memory for a moment, because its fields cannot be picked out before that.

Two things are also kept from the rows around the assistant rows, per file, as
``Links``: the agent ids a file launched (from a user row's
``toolUseResult.agentId``, with the row's time), the times the agent was resumed
(the kind of a user row's origin, and for a peer the sender's agent id), and the
times the agent stopped or woke. Ids and resume kinds from user rows are kept,
never text, tool input or output, or the message body: ``origin.body`` is only
tested for the hand-back prefix, and an id is kept only when it is letters,
digits, dash and underscore.

The module only reads. Files open with ``open(path, "rb")`` and nothing is
written anywhere. The per-file cache lives on the ``Reader`` instance, in process
memory. ``Reader.read`` scans every file, ``Reader.read_folder`` reads one project
folder, and both parse only the bytes after the stored offset of a file that grew.
"""

# ruff: noqa: PTH112, PTH114, PTH116, PTH118, PTH123 - the port keeps os.path string handling,
# so every path joins and tests exactly as the old reader did.
import datetime
import json
import os
import re
import stat
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import NamedTuple, cast

JsonObject = dict[str, object]


class Record(NamedTuple):
    """One assistant row reduced to a whitelist of fields."""

    message_id: str | None
    request_id: str | None
    ts_utc: datetime.datetime
    folder: str
    session_id: str
    run_id: str | None
    agent_type: str | None
    model_raw: str | None
    effort: str | None
    cwd: str | None
    git_branch: str | None
    is_sidechain: bool
    input: int
    output: int
    cache_read: int
    cache_write_5m: int
    cache_write_1h: int
    thinking: int | None
    speed: str | None
    service_tier: str | None
    inference_geo: str | None


class ReadResult(NamedTuple):
    """What ``Reader.read`` returns.

    ``signature`` is a hash over the files a read used (path, size, mtime and meta
    file identity, or the path alone for a file skipped as old). It changes when any
    of them does, so a caller can tell a read that found nothing new.
    ``unreadable`` is the set of project folder names the read could not use: a
    folder it could not list, or one whose files all failed to open.
    ``top_unreadable`` is True when the projects folder itself could not be listed.
    """

    records: list[Record]
    notes: dict[str, int]
    oldest_seen: datetime.datetime | None
    oldest_by_folder: dict[str, datetime.datetime]
    signature: int | None = None
    unreadable: frozenset[str] = frozenset()
    top_unreadable: bool = False


class Links(NamedTuple):
    """What one file says about who it launched and when it stopped or woke.

    All three are tuples.

    ``launched``: (child agent id, ts_utc), the first link row per child, in file
    order.
    ``rounds``: (ts_utc, by_kind, by_id) for each brief that came after the agent
    stopped, agent files only. ``by_kind`` is coordinator, human or peer; ``by_id``
    is the peer's agent id, else None.
    ``stops``: (ts_utc, finished) each time finished changed. ``finished`` is True
    from an assistant row that called SubagentHandback, or ended its turn with no
    tool call, until the agent is woken: a later assistant row that does not finish,
    a brief, or the first user row after the stop that is not only tool results.
    """

    launched: tuple[tuple[str, datetime.datetime], ...]
    rounds: tuple[tuple[datetime.datetime, object, str | None], ...]
    stops: tuple[tuple[datetime.datetime, bool], ...]


class FolderResult(NamedTuple):
    """What ``Reader.read_folder`` returns.

    The records of one project folder, a hash over the files it used (as
    ``ReadResult.signature``) and whether the folder could not be used. ``links`` is
    ``{(session_id, run_id or None): Links}`` for the files it read, or None when the
    read did not look (a linked folder). Files skipped as old give no links, and an
    orphaned or superseded main file merges into the ``(session_id, None)`` key, in
    file order.
    """

    records: list[Record]
    signature: int
    unreadable: bool
    links: dict[tuple[str, str | None], Links] | None = None


MAIN, AGENT, ORPHANED, SUPERSEDED = "main", "agent", "orphaned", "superseded"

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_STAMP = r"[A-Za-z0-9._:+-]+"
_UUID_RE = re.compile(_UUID)
_MAIN_RE = re.compile(r"(" + _UUID + r")\.jsonl")
_ORPHANED_RE = re.compile(
    r"(" + _UUID + r")\.orphaned-" + _STAMP + r"-[A-Za-z0-9_]+\.jsonl"
)
_SUPERSEDED_RE = re.compile(r"(" + _UUID + r")\.jsonl\.superseded-" + _STAMP)
_AGENT_RE = re.compile(r"agent-([A-Za-z0-9_-]+)\.jsonl")
_AGENT_META_RE = re.compile(r"agent-[A-Za-z0-9_-]+\.meta\.json")
_TS_RE = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]{1,6}))?(Z|[+-][0-9]{2}:[0-9]{2})"
)

_UTC = datetime.UTC
_PREFILTER = b'"assistant"'
_ORIGIN = b'"origin"'
# The key with its colon, so a string value "toolUseResult" does not match (V-e876).
_TOOL_RESULT_KEY = b'"toolUseResult":'
_AGENT_ID_KEY = b'"agentId"'
_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_HANDBACK_PREFIX = "[Subagent hand-back]"
_MAX_UNITS = 200
_ASCII_LETTER_DIGIT_HIGH = 0xFFFF


class _Found(NamedTuple):
    """One transcript file found by the scan.

    ``kind`` is main, agent, orphaned or superseded.
    """

    path: str
    folder: str
    session_id: str
    run_id: str | None
    kind: str
    meta_path: str | None
    st: os.stat_result


def _obj(value: object) -> JsonObject | None:
    """Narrow a parsed JSON value to an object, else None."""
    if isinstance(value, dict):
        return cast("JsonObject", value)
    return None


def _dashed(path: str) -> str:
    """Replace every character that is not a letter or digit with a dash.

    Claude Code runs ``path.replace(/[^a-zA-Z0-9]/g, "-")`` on UTF-16 code units, so
    a character above U+FFFF gives two dashes.

    Args:
        path: The path to turn into a folder name.

    Returns:
        The dashed name.
    """
    out: list[str] = []
    for ch in path:
        if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9"):
            out.append(ch)
        elif ord(ch) > _ASCII_LETTER_DIGIT_HIGH:
            out.append("--")
        else:
            out.append("-")
    return "".join(out)


def sanitize(path: str) -> str:
    """Return the folder name Claude Code uses for a path, cut at 200 units.

    Args:
        path: The project path.

    Returns:
        The dashed name, without the hash Claude Code adds above 200 units.
    """
    return _dashed(path)[:_MAX_UNITS]


def folder_matches(
    project_path: str, folder: str, first_cwd: str | None = None
) -> bool:
    """Say whether ``folder`` is the transcript folder for ``project_path``.

    Up to 200 units the names are equal. Above that, Claude Code adds "-" and a
    hash, so the folder must start with the 200-unit prefix plus "-" and the first
    row's cwd must be the real path.

    Args:
        project_path: The project path.
        folder: A folder name under ``projects/``.
        first_cwd: The cwd of the first row in the folder, if known.

    Returns:
        True when the folder belongs to the project.
    """
    real = os.path.realpath(project_path)
    full = _dashed(real)
    if len(full) <= _MAX_UNITS:
        return folder == full
    if first_cwd is None or first_cwd != real:
        return False
    return folder.startswith(full[:_MAX_UNITS] + "-")


def unreadable_folder(project_path: str, folders: Iterable[str]) -> str | None:
    """Return the folder in ``folders`` that ``project_path`` names, or None.

    A folder that failed has no rows, so there is no first cwd to confirm a path
    over 200 units. Such a path matches on the 200-unit prefix and the dash.

    Args:
        project_path: The project path.
        folders: Folder names that could not be read.

    Returns:
        The matching folder name, or None.
    """
    full = _dashed(os.path.realpath(project_path))
    for folder in sorted(folders):
        if folder == full or (
            len(full) > _MAX_UNITS and folder.startswith(full[:_MAX_UNITS] + "-")
        ):
            return folder
    return None


def folder_for_path(
    project_path: str,
    projects_dir: str,
    first_cwd_of: Callable[[str], str | None] | None = None,
) -> str | None:
    """Return the transcript folder name for ``project_path``, or None.

    It decides the way ``folder_matches`` does. Up to 200 units it is the dashed
    real path, whether or not the folder exists. Above that, it is the first folder
    in ``projects_dir`` (sorted) that starts with the 200-unit prefix plus "-" and
    whose first cwd, from ``first_cwd_of(folder)``, is the real path. With no
    ``first_cwd_of``, a long path gives None.

    Args:
        project_path: The project path.
        projects_dir: The ``projects/`` folder.
        first_cwd_of: Looks up the first cwd of a folder.

    Returns:
        The folder name, or None.
    """
    real = os.path.realpath(project_path)
    full = _dashed(real)
    if len(full) <= _MAX_UNITS:
        return full
    if first_cwd_of is None:
        return None
    prefix = full[:_MAX_UNITS] + "-"
    names = sorted(
        e.name
        for e in _listdir(projects_dir)
        if e.name.startswith(prefix) and _is_dir(e)
    )
    for name in names:
        if first_cwd_of(name) == real:
            return name
    return None


def project_folders(
    projects: Sequence[Mapping[str, object]], records: Iterable[Record]
) -> dict[str, str | None]:
    """Map each listed project key to its transcript folder name, or None.

    ``projects`` is a list of ``{"key", "name", "path"}``. The first cwd seen in
    each folder (in record order) is the first_cwd that ``folder_matches`` needs for
    a long path. A folder with no record cannot match. When two folders match, the
    one seen first in records wins.

    Args:
        projects: The listed projects.
        records: Records in read order.

    Returns:
        A map of project key to folder name or None.
    """
    first_cwd: dict[str, str | None] = {}
    for rec in records:
        if rec.folder not in first_cwd or (
            first_cwd[rec.folder] is None and rec.cwd is not None
        ):
            first_cwd[rec.folder] = rec.cwd
    out: dict[str, str | None] = {}
    for project in projects:
        found: str | None = None
        path = project.get("path")
        if isinstance(path, str) and path:
            for folder, cwd in first_cwd.items():
                if folder_matches(path, folder, cwd):
                    found = folder
                    break
        out[str(project["key"])] = found
    return out


def _parse_ts(value: object) -> datetime.datetime | None:
    """Return an aware UTC datetime from ``YYYY-MM-DDTHH:MM:SS[.f{1,6}](Z|+-HH:MM)``.

    Anything else gives None.
    """
    if not isinstance(value, str):
        return None
    m = _TS_RE.fullmatch(value)
    if not m:
        return None
    year, month, day, hour, minute, second = (int(m.group(i)) for i in range(1, 7))
    micro = int((m.group(7) or "0").ljust(6, "0"))
    zone = m.group(8)
    try:
        if zone == "Z":
            tz = _UTC
        else:
            sign = -1 if zone[0] == "-" else 1
            delta = datetime.timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6]))
            tz = datetime.timezone(sign * delta)
        return datetime.datetime(
            year, month, day, hour, minute, second, micro, tzinfo=tz
        ).astimezone(_UTC)
    except (ValueError, OverflowError):
        return None


def _count(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _label(value: object) -> str | None:
    """Return None when missing, the string itself, else ``str(value)``.

    The stringified value makes pricing refuse it.
    """
    if value is None or isinstance(value, str):
        return value
    return str(value)


def _empty_stats() -> dict[str, int]:
    return {"malformed": 0, "synthetic": 0, "no_id": 0}


def _read_agent_type(meta_path: str | None) -> str | None:
    """Return the agentType string from a meta file, or None. Nothing else is kept."""
    if meta_path is None:
        return None
    try:
        with open(meta_path, "rb") as fh:
            data = json.loads(fh.read())
    except (OSError, ValueError, RecursionError):
        return None
    obj = _obj(data)
    value = obj.get("agentType") if obj is not None else None
    del data
    return value if isinstance(value, str) else None


def _meta_sig(meta_path: str | None) -> tuple[int, int, int] | None:
    """Return the identity of a meta file (None when missing or not a plain file)."""
    if meta_path is None:
        return None
    try:
        st = os.lstat(meta_path)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    return (st.st_ino, st.st_size, st.st_mtime_ns)


def _listdir(path: str) -> list[os.DirEntry[str]]:
    try:
        with os.scandir(path) as it:
            return list(it)
    except OSError:
        return []


def _listdir_checked(path: str) -> list[os.DirEntry[str]] | None:
    """Return the entries of ``path``, or None when it cannot be listed."""
    try:
        with os.scandir(path) as it:
            return list(it)
    except OSError:
        return None


def _is_dir(entry: os.DirEntry[str]) -> bool:
    return entry.is_dir(follow_symlinks=False)


def _is_file(entry: os.DirEntry[str]) -> bool:
    return entry.is_file(follow_symlinks=False)


def _cache_writes(usage: JsonObject) -> tuple[int, int]:
    """Return the 5 minute and 1 hour cache write counts of a usage object."""
    total = _count(usage.get("cache_creation_input_tokens"))
    split = _obj(usage.get("cache_creation"))
    if split is not None and (
        "ephemeral_5m_input_tokens" in split or "ephemeral_1h_input_tokens" in split
    ):
        five = _count(split.get("ephemeral_5m_input_tokens"))
        one_hour = _count(split.get("ephemeral_1h_input_tokens"))
        if total - (five + one_hour) > 0:
            five += total - (five + one_hour)
        return five, one_hour
    return total, 0


def _make_record(
    row: object, found: _Found, agent_type: str | None, stats: dict[str, int]
) -> Record | None:
    """Return a whitelist copy of one parsed row, or None for rows that are dropped."""
    row_obj = _obj(row)
    if row_obj is None or row_obj.get("type") != "assistant":
        return None
    message = _obj(row_obj.get("message"))
    usage = _obj(message.get("usage")) if message is not None else None
    if message is None or usage is None:
        # Only a stats dict made by parse_file has the key, so Reader's stay as were.
        if "no_usage" in stats:
            stats["no_usage"] += 1
        return None
    model = message.get("model")
    if model == "<synthetic>":
        stats["synthetic"] += 1
        return None
    ts = _parse_ts(row_obj.get("timestamp"))
    if ts is None:
        stats["malformed"] += 1
        return None
    message_id = _text(message.get("id"))
    request_id = _text(row_obj.get("requestId"))
    if found.kind in (ORPHANED, SUPERSEDED) and not message_id and not request_id:
        stats["no_id"] += 1
        return None

    five, one_hour = _cache_writes(usage)

    details = _obj(usage.get("output_tokens_details"))
    raw_thinking = details.get("thinking_tokens") if details is not None else None
    thinking: int | None = None
    if (
        isinstance(raw_thinking, int)
        and not isinstance(raw_thinking, bool)
        and raw_thinking >= 0
    ):
        thinking = raw_thinking

    sidechain = row_obj.get("isSidechain")
    if not isinstance(sidechain, bool):
        sidechain = found.kind == AGENT

    return Record(
        message_id=message_id,
        request_id=request_id,
        ts_utc=ts,
        folder=found.folder,
        session_id=_text(row_obj.get("sessionId")) or found.session_id,
        run_id=found.run_id,
        agent_type=agent_type,
        model_raw=_text(model),
        effort=_text(row_obj.get("effort")),
        cwd=_text(row_obj.get("cwd")),
        git_branch=_text(row_obj.get("gitBranch")),
        is_sidechain=sidechain,
        input=_count(usage.get("input_tokens")),
        output=_count(usage.get("output_tokens")),
        cache_read=_count(usage.get("cache_read_input_tokens")),
        cache_write_5m=five,
        cache_write_1h=one_hour,
        thinking=thinking,
        speed=_label(usage.get("speed")),
        service_tier=_label(usage.get("service_tier")),
        inference_geo=_label(usage.get("inference_geo")),
    )


class _LinkState:
    """The parse state behind one file's Links.

    The idea is the hivemind round rule (hooks/hivemind_lib.py brief_starts),
    copied, because the dashboard does not import hooks/.

    ``stopped``: the last assistant row made no tool call or called
    SubagentHandback. ``finished``: the stop was final (see Links). Only ids, kinds
    and times are kept.
    """

    __slots__ = ("finished", "launched", "rounds", "seen", "stopped", "stops")

    def __init__(self) -> None:
        self.launched: list[tuple[str, datetime.datetime]] = []
        self.seen: set[str] = set()
        self.rounds: list[tuple[datetime.datetime, object, str | None]] = []
        self.stops: list[tuple[datetime.datetime, bool]] = []
        self.stopped = False
        self.finished = False

    def copy(self) -> "_LinkState":
        out = _LinkState()
        out.launched = list(self.launched)
        out.seen = set(self.seen)
        out.rounds = list(self.rounds)
        out.stops = list(self.stops)
        out.stopped = self.stopped
        out.finished = self.finished
        return out

    def links(self) -> Links:
        return Links(tuple(self.launched), tuple(self.rounds), tuple(self.stops))

    def export_state(self) -> dict[str, object]:
        """Return what a later parse needs to go on from an offset.

        Ids and two flags, never text. ``launched``, ``rounds`` and ``stops`` are
        results, not state, so they are not part of it.
        """
        return {
            "seen": sorted(self.seen),
            "stopped": self.stopped,
            "finished": self.finished,
        }

    @classmethod
    def from_state(cls, data: Mapping[str, object]) -> "_LinkState":
        """Build a state that goes on from ``export_state``. Bad input gives defaults.

        The new state has empty ``launched``, ``rounds`` and ``stops``, so after a
        parse they hold only what the new bytes added.
        """
        out = cls()
        seen = data.get("seen")
        if isinstance(seen, list):
            out.seen = {
                item
                for item in cast("list[object]", seen)
                if isinstance(item, str) and _ID_RE.fullmatch(item)
            }
        out.stopped = data.get("stopped") is True
        out.finished = data.get("finished") is True
        return out

    def _finish(self, ts: datetime.datetime, finished: bool) -> None:
        if finished != self.finished:
            self.finished = finished
            self.stops.append((ts, finished))

    def assistant(self, row: JsonObject, ts: datetime.datetime) -> None:
        message = _obj(row.get("message"))
        if message is None:
            return
        content = message.get("content")
        names: list[object] = []
        if isinstance(content, list):
            for block in cast("list[object]", content):
                item = _obj(block)
                if item is not None and item.get("type") == "tool_use":
                    names.append(item.get("name"))
        handback = "SubagentHandback" in names
        self.stopped = handback or not names
        self._finish(
            ts, handback or (not names and message.get("stop_reason") == "end_turn")
        )

    def user(  # noqa: PLR0912 - ported unchanged
        self, row: JsonObject, ts: datetime.datetime, is_agent: bool
    ) -> None:
        message = _obj(row.get("message"))
        content = message.get("content") if message is not None else None
        if isinstance(content, str):
            real = True
        elif isinstance(content, list):
            real = False
            for block in cast("list[object]", content):
                item = _obj(block)
                if item is not None and item.get("type") != "tool_result":
                    real = True
                    break
        else:
            real = False
        result = _obj(row.get("toolUseResult"))
        if result is not None:
            child = result.get("agentId")
            if (
                isinstance(child, str)
                and _ID_RE.fullmatch(child)
                and child not in self.seen
            ):
                self.seen.add(child)
                self.launched.append((child, ts))
        if not real:
            return
        origin = _obj(row.get("origin"))
        if is_agent and origin is not None:
            kind = origin.get("kind")
            by: str | None = None
            brief = kind in ("coordinator", "human")
            if kind == "peer":
                sender = origin.get("from")
                if isinstance(sender, str) and _ID_RE.fullmatch(sender):
                    by = sender
                body = origin.get("body")
                brief = by not in self.seen and not (
                    isinstance(body, str) and body.startswith(_HANDBACK_PREFIX)
                )
                if not brief:
                    by = None
            if brief and self.stopped:
                self.rounds.append((ts, kind, by))
                self.stopped = False
        if self.finished:
            self._finish(ts, False)


class _Entry(NamedTuple):
    """One cache entry per file.

    ``offset`` is the end of the last complete line that was parsed. ``links`` is the
    file's Links and ``lstate`` the parse state behind it, so a file that grew goes on
    from the offset.
    """

    dev: int
    ino: int
    size: int
    mtime_ns: int
    offset: int
    records: list[Record]
    stats: dict[str, int]
    meta_sig: tuple[int, int, int] | None
    agent_type: str | None
    links: Links
    lstate: _LinkState


class Reader:
    """Reads transcript files under a config folder and caches each parsed file."""

    def __init__(self, config_dir: str, horizon_days: int = 61) -> None:
        """Set up a reader.

        Args:
            config_dir: The Claude config folder. Transcripts are under ``projects/``.
            horizon_days: Files older than this many days are skipped.
        """
        self.config_dir = config_dir
        self.horizon_days = horizon_days
        self._cache: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        # How many transcript files the last scan found. Set while a read runs, and
        # read by other threads without the lock. None until the first scan ends.
        self.files_found: int | None = None
        # How many of those files the current scan has gone through: skipped as old,
        # loaded, or failed to open. Zero when a scan starts, then counts up to
        # files_found. Read by other threads without the lock. None until the first
        # scan starts.
        self.files_read: int | None = None

    def read(self, now: datetime.datetime) -> ReadResult:
        """Read every transcript file under the config folder.

        Args:
            now: The current time, which sets the horizon.

        Returns:
            The records, notes, oldest times and a signature.
        """
        with self._lock:
            return self._read(now)

    def read_folder(self, folder: str, now: datetime.datetime) -> FolderResult:
        """Read one project folder.

        It shares the per-file cache and the lock with ``read``, applies the same
        horizon, and parses only the new bytes of a file that grew. It drops cache
        entries only for files inside this folder that it no longer finds. It never
        changes ``files_found`` or ``files_read``. A folder that does not exist gives
        no records and is not unreadable. ``unreadable`` is True when the folder
        exists but could not be listed, or all its files failed to open.

        Args:
            folder: The folder name under ``projects/``.
            now: The current time, which sets the horizon.

        Returns:
            The records, a signature, the unreadable flag and the links.
        """
        with self._lock:
            return self._read_folder(folder, now)

    def _read_folder(self, folder: str, now: datetime.datetime) -> FolderResult:
        if now.tzinfo is None:
            now = now.replace(tzinfo=_UTC)
        cutoff = (now - datetime.timedelta(days=self.horizon_days)).timestamp()
        path = os.path.join(self.config_dir, "projects", folder)
        if os.path.islink(path):  # read never follows a linked folder either
            return FolderResult([], hash(()), False)
        inside = _listdir_checked(path)
        found: list[_Found] = []
        listed = inside is not None
        if inside is not None:
            self._scan_folder(found, inside, folder)
        records: list[Record] = []
        links: dict[tuple[str, str | None], Links] = {}
        seen: set[str] = set()
        signature: list[tuple[object, ...]] = []
        opened = failed = 0
        for item in sorted(found, key=lambda f: f.path):
            if item.st.st_mtime < cutoff:
                signature.append((item.path,))
                opened += 1
                continue
            entry = self._load(item)
            if entry is None:
                failed += 1
                continue
            opened += 1
            seen.add(item.path)
            signature.append((item.path, entry.size, entry.mtime_ns, entry.meta_sig))
            records.extend(entry.records)
            key = (item.session_id, item.run_id)
            kept = links.get(key)
            if kept is None:
                links[key] = entry.links
            else:  # an orphaned or superseded file of the same session: file order
                links[key] = Links(
                    kept.launched + entry.links.launched,
                    kept.rounds + entry.links.rounds,
                    kept.stops + entry.links.stops,
                )
        prefix = path + os.sep
        for cached in [
            p for p in self._cache if p.startswith(prefix) and p not in seen
        ]:
            del self._cache[cached]
        unreadable = failed > 0 and opened == 0 if listed else os.path.isdir(path)
        return FolderResult(records, hash(tuple(signature)), unreadable, links)

    def _read(  # noqa: PLR0912, PLR0915 - ported unchanged
        self, now: datetime.datetime
    ) -> ReadResult:
        if now.tzinfo is None:
            now = now.replace(tzinfo=_UTC)
        cutoff = (now - datetime.timedelta(days=self.horizon_days)).timestamp()
        self.files_read = 0
        found, ignored, unlisted, top_unreadable = self._scan(
            os.path.join(self.config_dir, "projects")
        )
        self.files_found = len(found)

        notes = {
            "malformed_lines": 0,
            "synthetic_rows": 0,
            "no_id_rows": 0,
            "ignored_files": ignored,
            "skipped_old_files": 0,
        }
        records: list[Record] = []
        seen: set[str] = set()
        oldest_skipped: float | None = None
        skipped_by_folder: dict[str, float] = {}
        opened: set[str] = set()
        failed: set[str] = set()
        signature: list[tuple[object, ...]] = []
        for item in sorted(found, key=lambda f: f.path):
            # files_read counts a file once it is done with, so the page never says a
            # file was read while it is still being parsed. Old files count as read
            # too: they are part of the total.
            if item.st.st_mtime < cutoff:
                self.files_read += 1
                signature.append((item.path,))
                notes["skipped_old_files"] += 1
                opened.add(item.folder)
                if oldest_skipped is None or item.st.st_mtime < oldest_skipped:
                    oldest_skipped = item.st.st_mtime
                low = skipped_by_folder.get(item.folder)
                if low is None or item.st.st_mtime < low:
                    skipped_by_folder[item.folder] = item.st.st_mtime
                continue
            entry = self._load(item)
            self.files_read += 1
            if entry is None:
                failed.add(item.folder)
                continue
            opened.add(item.folder)
            seen.add(item.path)
            signature.append((item.path, entry.size, entry.mtime_ns, entry.meta_sig))
            records.extend(entry.records)
            notes["malformed_lines"] += entry.stats["malformed"]
            notes["synthetic_rows"] += entry.stats["synthetic"]
            notes["no_id_rows"] += entry.stats["no_id"]
        for path in [p for p in self._cache if p not in seen]:
            del self._cache[path]

        oldest = min((r.ts_utc for r in records), default=None)
        if oldest_skipped is not None:
            skipped_dt = datetime.datetime.fromtimestamp(oldest_skipped, _UTC)
            if oldest is None or skipped_dt < oldest:
                oldest = skipped_dt
        # Per folder: the earlier of its oldest record and its oldest skipped file.
        by_folder: dict[str, datetime.datetime] = {}
        for rec in records:
            low_ts = by_folder.get(rec.folder)
            if low_ts is None or rec.ts_utc < low_ts:
                by_folder[rec.folder] = rec.ts_utc
        for folder, mtime in skipped_by_folder.items():
            skipped_dt = datetime.datetime.fromtimestamp(mtime, _UTC)
            low_ts = by_folder.get(folder)
            if low_ts is None or skipped_dt < low_ts:
                by_folder[folder] = skipped_dt
        # A folder is unreadable when its listing failed, or when it had files and
        # none of them opened.
        unreadable = frozenset(unlisted | (failed - opened))
        return ReadResult(
            records,
            notes,
            oldest,
            by_folder,
            hash(tuple(signature)),
            unreadable,
            top_unreadable,
        )

    def _scan(self, root: str) -> tuple[list[_Found], int, set[str], bool]:
        """Scan ``root`` for transcript files.

        Returns the files, a count of everything else, the project folders that could
        not be listed, and whether root itself could not. Symlinks are never followed.
        A directory that is not part of the layout counts once and is not walked.
        """
        files: list[_Found] = []
        ignored = 0
        unlisted: set[str] = set()
        tops = _listdir_checked(root)
        if tops is None:
            return files, ignored, unlisted, True
        for top in tops:
            if top.is_symlink() or not _is_dir(top):
                ignored += 1
                continue
            folder = top.name
            inside = _listdir_checked(top.path)
            if inside is None:
                unlisted.add(folder)
                continue
            ignored += self._scan_folder(files, inside, folder)
        return files, ignored, unlisted, False

    def _scan_folder(
        self, files: list[_Found], inside: list[os.DirEntry[str]], folder: str
    ) -> int:
        """Add the transcript files among the entries of one project folder to files.

        Returns how many entries were ignored.
        """
        ignored = 0
        for entry in inside:
            name = entry.name
            if entry.is_symlink():
                ignored += 1
            elif _is_file(entry):
                kind: str | None = None
                sid = ""
                for pattern, k in (
                    (_MAIN_RE, MAIN),
                    (_ORPHANED_RE, ORPHANED),
                    (_SUPERSEDED_RE, SUPERSEDED),
                ):
                    m = pattern.fullmatch(name)
                    if m:
                        kind, sid = k, m.group(1)
                        break
                if kind is None:
                    ignored += 1
                else:
                    self._add(files, entry, folder, sid, None, kind, None)
            elif _is_dir(entry) and _UUID_RE.fullmatch(name):
                ignored += self._scan_session(files, entry, folder)
            else:
                ignored += 1
        return ignored

    def _scan_session(
        self, files: list[_Found], session_dir: os.DirEntry[str], folder: str
    ) -> int:
        ignored = 0
        for entry in _listdir(session_dir.path):
            if entry.is_symlink() or entry.name != "subagents" or not _is_dir(entry):
                ignored += 1
                continue
            for agent in _listdir(entry.path):
                m = _AGENT_RE.fullmatch(agent.name)
                if agent.is_symlink():
                    ignored += 1
                elif _is_file(agent) and m:
                    meta = os.path.join(
                        entry.path, "agent-" + m.group(1) + ".meta.json"
                    )
                    self._add(
                        files, agent, folder, session_dir.name, m.group(1), AGENT, meta
                    )
                elif _is_file(agent) and _AGENT_META_RE.fullmatch(agent.name):
                    continue
                else:
                    ignored += 1
        return ignored

    @staticmethod
    def _add(  # noqa: PLR0913, PLR0917 - ported unchanged
        files: list[_Found],
        entry: os.DirEntry[str],
        folder: str,
        session_id: str,
        run_id: str | None,
        kind: str,
        meta_path: str | None,
    ) -> None:
        try:
            st = entry.stat(follow_symlinks=False)
        except OSError:
            return
        files.append(
            _Found(entry.path, folder, session_id, run_id, kind, meta_path, st)
        )

    def _load(self, item: _Found) -> _Entry | None:
        st = item.st
        old = self._cache.get(item.path)
        meta_sig = _meta_sig(item.meta_path)
        if old is not None and old.meta_sig == meta_sig:
            agent_type = old.agent_type
        else:
            agent_type = (
                _read_agent_type(item.meta_path) if meta_sig is not None else None
            )

        same_file = old is not None and old.dev == st.st_dev and old.ino == st.st_ino
        if (
            old is not None
            and same_file
            and old.size == st.st_size
            and old.mtime_ns == st.st_mtime_ns
        ):
            records, stats, offset, links, lstate = (
                old.records,
                old.stats,
                old.offset,
                old.links,
                old.lstate,
            )
        else:
            if old is not None and same_file and st.st_size > old.size:
                # The file grew: keep what was parsed, read on from the offset.
                records, stats, offset = list(old.records), dict(old.stats), old.offset
                lstate = old.lstate.copy()
            else:
                records, stats, offset = [], _empty_stats(), 0
                lstate = _LinkState()
            new_offset = self._parse(item, offset, records, stats, agent_type, lstate)
            if new_offset is None:
                self._cache.pop(item.path, None)
                return None
            offset = new_offset
            links = lstate.links()
        if old is not None and records and old.agent_type != agent_type:
            records = [r._replace(agent_type=agent_type) for r in records]
        entry = _Entry(
            st.st_dev,
            st.st_ino,
            st.st_size,
            st.st_mtime_ns,
            offset,
            records,
            stats,
            meta_sig,
            agent_type,
            links,
            lstate,
        )
        self._cache[item.path] = entry
        return entry

    @staticmethod
    def _parse(  # noqa: PLR0912, PLR0913, PLR0917 - ported unchanged
        item: _Found,
        offset: int,
        records: list[Record],
        stats: dict[str, int],
        agent_type: str | None,
        lstate: _LinkState,
        offsets: list[int] | None = None,
    ) -> int | None:
        """Append the records found from offset on and update lstate.

        When ``offsets`` is a list, the byte offset of each appended record's line is
        appended to it, in step with ``records``.

        Returns the new offset, or None. Each line is parsed at most once, and only
        when it can matter: an assistant row (records and stop tracking), a user row
        whose toolUseResult holds an agentId (a launch), a user row in an agent file
        with an origin (a brief), or the user rows after a finishing stop until one
        that is not only tool results wakes the agent. A line with a toolUseResult key
        counts as a user row.
        """
        try:
            with open(item.path, "rb") as fh:
                fh.seek(offset)
                data = fh.read()
        except OSError:
            return None
        is_agent = item.kind == AGENT
        find = (
            data.find
        )  # searches the buffer in place, so a line is copied only when parsed
        pos = 0
        while True:
            end = find(b"\n", pos)
            if end == -1:
                break  # no newline yet: the line is still being written
            start = pos
            pos = end + 1
            at = find(_TOOL_RESULT_KEY, start, end)
            if at >= 0:
                # A row with a toolUseResult is a user row, so it needs no assistant or
                # origin check, and only a launch (an agentId after the key) matters.
                # Scanning a big tool result row once instead of three times keeps a
                # cold read within a few percent of what it was. The needle carries the
                # colon, so a string value such as a Grep pattern does not count. One
                # case is left: an object key "toolUseResult" inside a tool input with
                # no "agentId" after it.
                assistant = False
                if find(_AGENT_ID_KEY, at, end) < 0:
                    continue
            else:
                assistant = find(_PREFILTER, start, end) >= 0
                if not assistant and not (
                    lstate.finished or (is_agent and find(_ORIGIN, start, end) >= 0)
                ):
                    continue
            line = data[start:end]
            try:
                row = json.loads(line)
            except (ValueError, RecursionError):
                if assistant:
                    stats["malformed"] += 1
                continue
            row_obj = _obj(row)
            kind = row_obj.get("type") if row_obj is not None else None
            if row_obj is not None and kind == "assistant":
                record = _make_record(row_obj, item, agent_type, stats)
                ts = (
                    record.ts_utc
                    if record is not None
                    else _parse_ts(row_obj.get("timestamp"))
                )
                if ts is not None:
                    lstate.assistant(row_obj, ts)
                if record is not None:
                    records.append(record)
                    if offsets is not None:
                        offsets.append(offset + start)
            elif row_obj is not None and kind == "user":
                ts = _parse_ts(row_obj.get("timestamp"))
                if ts is not None:
                    lstate.user(row_obj, ts, is_agent)
            del row
        return offset + pos


# ---------------------------------------------------------------- public parts
#
# What the SQLite ingest uses. The Reader above stays the oracle, and these call the
# same scan, regexes and ``_parse`` it does.

LinkState = _LinkState
FoundFile = _Found


class FileParse(NamedTuple):
    """What ``parse_file`` returns.

    ``records`` and ``line_offsets`` go in step: the byte offset of each record's
    line, which keys a row that has no message id and no request id. ``end_offset`` is
    the end of the last complete line, or None when the file could not be opened.
    ``stats`` has malformed, synthetic and no_id like the Reader's, plus ``no_usage``,
    the assistant rows that carry no usage object. ``link_state`` holds only what the
    new bytes added in its ``launched``, ``rounds`` and ``stops``.
    """

    records: list[Record]
    end_offset: int | None
    stats: dict[str, int]
    link_state: LinkState
    line_offsets: list[int]


def parse_file(  # noqa: PLR0913 - one file's identity, keyword-only
    path: str,
    kind: str,
    offset: int,
    link_state: LinkState | None,
    agent_type: str | None,
    *,
    folder: str = "",
    session_id: str = "",
    run_id: str | None = None,
) -> FileParse:
    """Parse one transcript file from ``offset`` and return what it holds.

    It reads only the bytes after ``offset`` and stops at the last complete line, so
    a half-written last line waits for the next call. ``link_state`` is the state a
    previous call returned (or ``LinkState.from_state`` of the stored dict), or None
    to start fresh. The state passed in is not changed. Nothing is written.

    Args:
        path: The transcript file.
        kind: main, agent, orphaned or superseded.
        offset: Where to start, a line start.
        link_state: The parse state at ``offset``, or None.
        agent_type: The agent type from the meta file, or None.
        folder: The project folder name, for the records.
        session_id: The session the file belongs to, for the records.
        run_id: The agent id for an agent file, else None.

    Returns:
        The records, the end offset, the stats and the link state.
    """
    state = link_state.copy() if link_state is not None else LinkState()
    if link_state is not None:
        state.launched, state.rounds, state.stops = [], [], []
    stats = {**_empty_stats(), "no_usage": 0}
    records: list[Record] = []
    offsets: list[int] = []
    try:
        st = os.stat(path)
    except OSError:
        return FileParse(records, None, stats, state, offsets)
    item = _Found(path, folder, session_id, run_id, kind, None, st)
    parse = Reader._parse  # pyright: ignore[reportPrivateUsage]
    end = parse(item, offset, records, stats, agent_type, state, offsets)
    return FileParse(records, end, stats, state, offsets)


def scan_folder(path: str, folder: str) -> list[FoundFile] | None:
    """List the transcript files of one project folder, the way the Reader does.

    Main, orphaned and superseded files, and agent files under
    ``<session>/subagents/`` with the path of their meta file. Symlinks and other
    entries are skipped. Returns None when the folder cannot be listed.

    Args:
        path: The project folder path.
        folder: Its name under ``projects/``.

    Returns:
        The files in listing order, or None.
    """
    inside = _listdir_checked(path)
    if inside is None:
        return None
    files: list[FoundFile] = []
    Reader("")._scan_folder(files, inside, folder)  # pyright: ignore[reportPrivateUsage]
    return files


def read_agent_type(meta_path: str | None) -> str | None:
    """Return the agentType string from an agent meta file, or None."""
    return _read_agent_type(meta_path)
