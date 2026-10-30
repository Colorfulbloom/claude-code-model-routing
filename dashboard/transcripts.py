"""Transcript reader for the usage page.

It finds Claude Code transcript files under <config_dir>/projects, turns each
assistant row into a Record from a fixed list of fields, and drops the row.
No message text, tool data or agent description is kept. A line is parsed in
memory for a moment, because its fields cannot be picked out before that.

The module only reads. Files open with open(path, "rb") and nothing is written
anywhere. The per-file cache lives on the Reader instance, in process memory.
"""
import collections
import datetime
import json
import os
import re
import stat
import threading

Record = collections.namedtuple(
    "Record",
    "message_id request_id ts_utc folder session_id run_id agent_type model_raw "
    "effort cwd git_branch is_sidechain input output cache_read cache_write_5m "
    "cache_write_1h thinking speed service_tier inference_geo",
)
ReadResult = collections.namedtuple("ReadResult", "records notes oldest_seen oldest_by_folder")

# One entry per file. offset is the end of the last complete line that was parsed.
_Entry = collections.namedtuple(
    "_Entry", "dev ino size mtime_ns offset records stats meta_sig agent_type"
)
# One transcript file found by the scan. kind is main, agent, orphaned or superseded.
_Found = collections.namedtuple("_Found", "path folder session_id run_id kind meta_path st")

MAIN, AGENT, ORPHANED, SUPERSEDED = "main", "agent", "orphaned", "superseded"

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_STAMP = r"[A-Za-z0-9._:+-]+"
_UUID_RE = re.compile(_UUID)
_MAIN_RE = re.compile(r"(" + _UUID + r")\.jsonl")
_ORPHANED_RE = re.compile(r"(" + _UUID + r")\.orphaned-" + _STAMP + r"-[A-Za-z0-9_]+\.jsonl")
_SUPERSEDED_RE = re.compile(r"(" + _UUID + r")\.jsonl\.superseded-" + _STAMP)
_AGENT_RE = re.compile(r"agent-([A-Za-z0-9_-]+)\.jsonl")
_AGENT_META_RE = re.compile(r"agent-[A-Za-z0-9_-]+\.meta\.json")
_TS_RE = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]{1,6}))?(Z|[+-][0-9]{2}:[0-9]{2})"
)

_UTC = datetime.timezone.utc
_PREFILTER = b'"assistant"'
_MAX_UNITS = 200


def _dashed(path):
    """Replace every character that is not a letter or digit with a dash.

    Claude Code runs path.replace(/[^a-zA-Z0-9]/g, "-") on UTF-16 code units, so
    a character above U+FFFF gives two dashes.
    """
    out = []
    for ch in path:
        if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9"):
            out.append(ch)
        elif ord(ch) > 0xFFFF:
            out.append("--")
        else:
            out.append("-")
    return "".join(out)


def sanitize(path):
    """Folder name Claude Code uses for a path, cut at 200 units (hash not added)."""
    return _dashed(path)[:_MAX_UNITS]


def folder_matches(project_path, folder, first_cwd=None):
    """True when folder is the transcript folder for project_path.

    Up to 200 units the names are equal. Above that, Claude Code adds "-" and a
    hash, so the folder must start with the 200-unit prefix plus "-" and the
    first row's cwd must be the real path.
    """
    real = os.path.realpath(project_path)
    full = _dashed(real)
    if len(full) <= _MAX_UNITS:
        return folder == full
    if first_cwd is None or first_cwd != real:
        return False
    return folder.startswith(full[:_MAX_UNITS] + "-")


def project_folders(projects, records):
    """Map each listed project key to its transcript folder name, or None.

    projects is a list of {"key", "name", "path"}. The first cwd seen in each
    folder (in record order) is the first_cwd that folder_matches needs for a
    long path. A folder with no record cannot match. When two folders match,
    the one seen first in records wins.
    """
    first_cwd = {}
    for rec in records:
        if rec.folder not in first_cwd:
            first_cwd[rec.folder] = rec.cwd
        elif first_cwd[rec.folder] is None and rec.cwd is not None:
            first_cwd[rec.folder] = rec.cwd
    out = {}
    for project in projects:
        found = None
        path = project.get("path")
        if isinstance(path, str) and path:
            for folder, cwd in first_cwd.items():
                if folder_matches(path, folder, cwd):
                    found = folder
                    break
        out[project["key"]] = found
    return out


def _parse_ts(value):
    """Aware UTC datetime from YYYY-MM-DDTHH:MM:SS[.f{1,6}](Z|+-HH:MM), else None."""
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
        return datetime.datetime(year, month, day, hour, minute, second, micro, tzinfo=tz).astimezone(_UTC)
    except (ValueError, OverflowError):
        return None


def _count(value):
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _text(value):
    return value if isinstance(value, str) else None


def _label(value):
    """None when missing, the string itself, else str(value) so pricing refuses it."""
    if value is None or isinstance(value, str):
        return value
    return str(value)


def _empty_stats():
    return {"malformed": 0, "synthetic": 0, "no_id": 0}


def _read_agent_type(meta_path):
    """The agentType string from a meta file, or None. Nothing else is kept."""
    if meta_path is None:
        return None
    try:
        with open(meta_path, "rb") as fh:
            data = json.loads(fh.read())
    except (OSError, ValueError, RecursionError):
        return None
    value = data.get("agentType") if isinstance(data, dict) else None
    del data
    return value if isinstance(value, str) else None


def _meta_sig(meta_path):
    """Identity of a meta file (None when missing or not a plain file)."""
    if meta_path is None:
        return None
    try:
        st = os.lstat(meta_path)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    return (st.st_ino, st.st_size, st.st_mtime_ns)


def _listdir(path):
    try:
        with os.scandir(path) as it:
            return list(it)
    except OSError:
        return []


def _is_dir(entry):
    return entry.is_dir(follow_symlinks=False)


def _is_file(entry):
    return entry.is_file(follow_symlinks=False)


def _make_record(row, found, agent_type, stats):
    """Whitelist copy of one parsed row. Returns None for rows that are dropped."""
    if not isinstance(row, dict) or row.get("type") != "assistant":
        return None
    message = row.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    model = message.get("model")
    if model == "<synthetic>":
        stats["synthetic"] += 1
        return None
    ts = _parse_ts(row.get("timestamp"))
    if ts is None:
        stats["malformed"] += 1
        return None
    message_id = _text(message.get("id"))
    request_id = _text(row.get("requestId"))
    if found.kind in (ORPHANED, SUPERSEDED) and not message_id and not request_id:
        stats["no_id"] += 1
        return None

    total = _count(usage.get("cache_creation_input_tokens"))
    split = usage.get("cache_creation")
    if isinstance(split, dict) and (
        "ephemeral_5m_input_tokens" in split or "ephemeral_1h_input_tokens" in split
    ):
        five = _count(split.get("ephemeral_5m_input_tokens"))
        one_hour = _count(split.get("ephemeral_1h_input_tokens"))
        if total - (five + one_hour) > 0:
            five += total - (five + one_hour)
    else:
        five, one_hour = total, 0

    details = usage.get("output_tokens_details")
    thinking = details.get("thinking_tokens") if isinstance(details, dict) else None
    if not (isinstance(thinking, int) and not isinstance(thinking, bool) and thinking >= 0):
        thinking = None

    sidechain = row.get("isSidechain")
    if not isinstance(sidechain, bool):
        sidechain = found.kind == AGENT

    return Record(
        message_id=message_id,
        request_id=request_id,
        ts_utc=ts,
        folder=found.folder,
        session_id=_text(row.get("sessionId")) or found.session_id,
        run_id=found.run_id,
        agent_type=agent_type,
        model_raw=_text(model),
        effort=_text(row.get("effort")),
        cwd=_text(row.get("cwd")),
        git_branch=_text(row.get("gitBranch")),
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


class Reader:
    def __init__(self, config_dir, horizon_days=61):
        self.config_dir = config_dir
        self.horizon_days = horizon_days
        self._cache = {}
        self._lock = threading.Lock()

    def read(self, now):
        with self._lock:
            return self._read(now)

    def _read(self, now):
        if now.tzinfo is None:
            now = now.replace(tzinfo=_UTC)
        cutoff = (now - datetime.timedelta(days=self.horizon_days)).timestamp()
        found, ignored = self._scan(os.path.join(self.config_dir, "projects"))

        notes = {
            "malformed_lines": 0,
            "synthetic_rows": 0,
            "no_id_rows": 0,
            "ignored_files": ignored,
            "skipped_old_files": 0,
        }
        records = []
        seen = set()
        oldest_skipped = None
        skipped_by_folder = {}
        for item in sorted(found, key=lambda f: f.path):
            if item.st.st_mtime < cutoff:
                notes["skipped_old_files"] += 1
                if oldest_skipped is None or item.st.st_mtime < oldest_skipped:
                    oldest_skipped = item.st.st_mtime
                low = skipped_by_folder.get(item.folder)
                if low is None or item.st.st_mtime < low:
                    skipped_by_folder[item.folder] = item.st.st_mtime
                continue
            entry = self._load(item)
            if entry is None:
                continue
            seen.add(item.path)
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
        by_folder = {}
        for rec in records:
            low = by_folder.get(rec.folder)
            if low is None or rec.ts_utc < low:
                by_folder[rec.folder] = rec.ts_utc
        for folder, mtime in skipped_by_folder.items():
            skipped_dt = datetime.datetime.fromtimestamp(mtime, _UTC)
            low = by_folder.get(folder)
            if low is None or skipped_dt < low:
                by_folder[folder] = skipped_dt
        return ReadResult(records, notes, oldest, by_folder)

    def _scan(self, root):
        """Transcript files under root plus a count of everything else.

        Symlinks are never followed. A directory that is not part of the layout
        counts once and is not walked.
        """
        files = []
        ignored = 0
        for top in _listdir(root):
            if top.is_symlink() or not _is_dir(top):
                ignored += 1
                continue
            folder = top.name
            for entry in _listdir(top.path):
                name = entry.name
                if entry.is_symlink():
                    ignored += 1
                elif _is_file(entry):
                    kind = None
                    for pattern, k in ((_MAIN_RE, MAIN), (_ORPHANED_RE, ORPHANED), (_SUPERSEDED_RE, SUPERSEDED)):
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
        return files, ignored

    def _scan_session(self, files, session_dir, folder):
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
                    meta = os.path.join(entry.path, "agent-" + m.group(1) + ".meta.json")
                    self._add(files, agent, folder, session_dir.name, m.group(1), AGENT, meta)
                elif _is_file(agent) and _AGENT_META_RE.fullmatch(agent.name):
                    continue
                else:
                    ignored += 1
        return ignored

    @staticmethod
    def _add(files, entry, folder, session_id, run_id, kind, meta_path):
        try:
            st = entry.stat(follow_symlinks=False)
        except OSError:
            return
        files.append(_Found(entry.path, folder, session_id, run_id, kind, meta_path, st))

    def _load(self, item):
        st = item.st
        old = self._cache.get(item.path)
        meta_sig = _meta_sig(item.meta_path)
        if old is not None and old.meta_sig == meta_sig:
            agent_type = old.agent_type
        else:
            agent_type = _read_agent_type(item.meta_path) if meta_sig is not None else None

        same_file = old is not None and old.dev == st.st_dev and old.ino == st.st_ino
        if same_file and old.size == st.st_size and old.mtime_ns == st.st_mtime_ns:
            records, stats, offset = old.records, old.stats, old.offset
        else:
            if same_file and st.st_size > old.size:
                # The file grew: keep what was parsed and read on from the stored offset.
                records, stats, offset = list(old.records), dict(old.stats), old.offset
            else:
                records, stats, offset = [], _empty_stats(), 0
            offset = self._parse(item, offset, records, stats, agent_type)
            if offset is None:
                self._cache.pop(item.path, None)
                return None
        if old is not None and records and old.agent_type != agent_type:
            records = [r._replace(agent_type=agent_type) for r in records]
        entry = _Entry(st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, offset, records, stats, meta_sig, agent_type)
        self._cache[item.path] = entry
        return entry

    @staticmethod
    def _parse(item, offset, records, stats, agent_type):
        """Append the records found from offset on. Returns the new offset, or None."""
        try:
            with open(item.path, "rb") as fh:
                fh.seek(offset)
                data = fh.read()
        except OSError:
            return None
        pos = 0
        while True:
            end = data.find(b"\n", pos)
            if end == -1:
                break  # no newline yet: the line is still being written
            line = data[pos:end]
            pos = end + 1
            if _PREFILTER not in line:
                continue
            try:
                row = json.loads(line)
            except (ValueError, RecursionError):
                stats["malformed"] += 1
                continue
            record = _make_record(row, item, agent_type, stats)
            del row
            if record is not None:
                records.append(record)
        return offset + pos
