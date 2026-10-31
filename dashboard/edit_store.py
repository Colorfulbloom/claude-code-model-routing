"""The only module that writes: one settings edit, backed up first, atomic.

A target is one of three settings files, derived from a project key and a layer
(user, project or local). No path ever arrives from a client. Every open,
write, rename, unlink and mkdir on a target or on the backup store goes through
a directory descriptor, so nothing can be swapped between a check and a use.
A symlink, a hard link, a FIFO, a file that is not ours, a file over 1 MiB and
anything at or under the managed settings folder is refused with a named code.

The backup store is <config_dir>/routing-dashboard/backups/<target-id>/. It
holds NNNNNN-<edit id>.bak files, ledger.json and .lock. Folders are 0700 and
files 0600. The ledger lists the edits (values stored masked). A save runs
these steps under a thread lock and an flock on .lock:

    1 read the file          5 write the temp file in the target's folder
    2 plan (caller's hook)   6 walk again, compare bytes, rename by descriptor
    3 write the backup       7 fsync the folder, read the file back, compare
    4 write the ledger       8 prune to the newest RETENTION rows

Whether a row can be undone is worked out from hashes when it is read, never
stored. Reads never write. A restore is a save whose bytes are a checked backup.

Standard library only, Python 3.9.
"""
import collections
import contextlib
import datetime
import errno
import hashlib
import json
import os
import re
import secrets
import stat
import threading
import time

try:
    import fcntl
except ImportError:  # a platform without fcntl can still import this module
    fcntl = None

import collect
import projects

LAYERS = ("user", "project", "local")
RETENTION = 20
MAX_FILE = 1024 * 1024
LOCK_WAIT = 5.0

STORE_DIR = "routing-dashboard"
BACKUPS_DIR = "backups"
LEDGER_FILE = "ledger.json"
LOCK_FILE = ".lock"
MANAGED_FILE = "managed-settings.json"
MAX_LEDGER = 4 * MAX_FILE
_BACKUP_RE = re.compile(r"^(\d{6})-[0-9a-f]{16}\.bak$")
_TEMP_RE = re.compile(r"^\.routing-dashboard-[0-9a-f]{16}\.tmp$")

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY
_SUBDIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_LEAF_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
_NEW_FLAGS = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW


# Errors

class StoreError(Exception):
    pass


class Refused(StoreError):
    """The target or the request is not allowed. .code names the reason."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class Stale(StoreError):
    """The file moved between the read and the rename. Nothing was written."""

    def __init__(self, changed="file"):
        super().__init__(changed)
        self.changed = changed


class WriteFailed(StoreError):
    """A step failed before the rename. The settings file is as it was."""


class Raced(StoreError):
    """Another writer got in after the rename, or the file differs from its backup."""

    def __init__(self, row, backup_path, matches_backup=None, restored_from_path=None):
        super().__init__("raced")
        self.row = row
        self.backup_path = backup_path
        self.matches_backup = matches_backup
        self.restored_from_path = restored_from_path


class Unverified(StoreError):
    """The rename happened but the read-back or the folder fsync failed."""

    def __init__(self, stage, row, backup_path):
        super().__init__(stage)
        self.stage = stage
        self.row = row
        self.backup_path = backup_path


class BackupDamaged(StoreError):
    def __init__(self, backup_path):
        super().__init__("backup_damaged")
        self.backup_path = backup_path


class ChangedSinceSave(StoreError):
    def __init__(self, backup_path):
        super().__init__("changed_since_save")
        self.backup_path = backup_path


class NotUndoable(StoreError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class UnknownEdit(StoreError):
    pass


Plan = collections.namedtuple("Plan", "new_raw key_path old_value new_value")
Restored = collections.namedtuple("Restored", "row matches_backup restored_from_path backup_path")
Snapshot = collections.namedtuple("Snapshot", "dir_fd raw mode dev ino")
_Job = collections.namedtuple(
    "_Job", "new_raw kind key_path layer old_value new_value restored_from restored_from_backup source")


# Targets

class Target:
    """One settings file: layer, base folder, rel folders under it and the file name."""

    __slots__ = ("layer", "base", "rel", "name", "path", "managed_real")

    def __init__(self, layer, base, rel, name, managed_real=None):
        self.layer = layer
        self.base = base
        self.rel = tuple(rel)
        self.name = name
        self.path = os.path.join(base, *self.rel, name)
        self.managed_real = managed_real


def target_for(ctx, project_key, layer):
    """Return the Target for a project key and a layer. Never takes a path."""
    if layer not in LAYERS:
        raise Refused("not_editable")
    project = projects.load(ctx).find(project_key)
    if project is None:
        raise Refused("unknown_project")
    if layer == "user":
        base, rel = ctx.config_dir, ()
    else:
        if project.unexpanded:
            raise Refused("file_missing")
        base, rel = project.path, (".claude",)
    name = "settings.local.json" if layer == "local" else "settings.json"
    managed = ctx.managed_dir
    managed_real = os.path.realpath(managed) if managed is not None else None
    target = Target(layer, base, rel, name, managed_real)
    _check_managed(target)
    return target


def _check_managed(target):
    """Refuse a file at or under the managed folder, or named managed-settings.json."""
    if target.name == MANAGED_FILE:
        raise Refused("managed")
    managed = target.managed_real
    prefix = managed.rstrip(os.sep) + os.sep if managed is not None else None
    paths = (os.path.realpath(target.path),
             os.path.join(os.path.realpath(target.base), *target.rel, target.name))
    for path in paths:
        if os.path.basename(path) == MANAGED_FILE:
            raise Refused("managed")
        if managed is not None and (path == managed or path.startswith(prefix)):
            raise Refused("managed")


def _target_id(target):
    real = os.path.join(os.path.realpath(target.base), *target.rel, target.name)
    return hashlib.sha256(os.fsencode(real)).hexdigest()[:16]


# The descriptor walk

def _refusal(exc, name, dir_fd):
    """Return the Refused for an open's OSError, or the OSError when it is not a known cause."""
    code = exc.errno
    if code == errno.ENOENT:
        return Refused("file_missing")
    if code in (errno.ENOTDIR, errno.ELOOP):
        if dir_fd is None:
            return Refused("not_regular")
        try:
            info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            return Refused("file_missing")
        except OSError:
            return Refused("not_regular")
        return Refused("symlink" if stat.S_ISLNK(info.st_mode) else "not_regular")
    if code in (errno.EACCES, errno.EPERM):
        return Refused("not_owner")
    if code in (errno.ENXIO, errno.EOPNOTSUPP, errno.ENODEV):
        return Refused("not_regular")
    return exc


def _open_step(name, flags, dir_fd):
    try:
        if dir_fd is None:
            return os.open(name, flags)
        return os.open(name, flags, dir_fd=dir_fd)
    except OSError as exc:
        raise _refusal(exc, name, dir_fd) from None


def _read_capped(fd, cap):
    """Read up to cap + 1 bytes from fd, in a loop."""
    chunks, total = [], 0
    while total <= cap:
        chunk = os.read(fd, cap + 1 - total)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


@contextlib.contextmanager
def _walk(target):
    """Open the target by descriptors and yield a Snapshot. Closes every descriptor."""
    _check_managed(target)
    fds = []
    try:
        dir_fd = _open_step(target.base, _DIR_FLAGS, None)
        fds.append(dir_fd)
        for part in target.rel:
            dir_fd = _open_step(part, _SUBDIR_FLAGS, dir_fd)
            fds.append(dir_fd)
        leaf = _open_step(target.name, _LEAF_FLAGS, dir_fd)
        fds.append(leaf)
        info = os.fstat(leaf)
        if not stat.S_ISREG(info.st_mode):
            raise Refused("not_regular")
        if info.st_nlink != 1:
            raise Refused("hard_link")
        if info.st_uid != os.geteuid():
            raise Refused("not_owner")
        if info.st_size > MAX_FILE:
            raise Refused("too_large")
        raw = _read_capped(leaf, MAX_FILE)
        if len(raw) > MAX_FILE:
            raise Refused("too_large")
        folder = os.fstat(dir_fd)
        yield Snapshot(dir_fd, raw, stat.S_IMODE(info.st_mode), folder.st_dev, folder.st_ino)
    finally:
        for fd in fds:
            try:
                os.close(fd)
            except OSError:
                pass


def read_target(target):
    """Return the target file's bytes through the walk, or raise Refused."""
    with _walk(target) as snap:
        return snap.raw


# Small file helpers, all relative to a directory descriptor

def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _fullfsync(fd):
    """F_FULLFSYNC where the platform has it and allows it, else fsync."""
    full = getattr(fcntl, "F_FULLFSYNC", None) if fcntl is not None else None
    if full is not None:
        try:
            fcntl.fcntl(fd, full)
            return
        except OSError:
            pass
    os.fsync(fd)


def _write_all(fd, data):
    view = memoryview(data)
    while len(view):
        written = os.write(fd, view)
        view = view[written:]


def _create_file(name, data, dir_fd, mode=0o600, final_mode=None):
    """Create name exclusively under dir_fd, write data, fsync fully, close."""
    fd = os.open(name, _NEW_FLAGS, mode, dir_fd=dir_fd)
    try:
        _write_all(fd, data)
        if final_mode is not None:
            os.fchmod(fd, final_mode)
        _fullfsync(fd)
    finally:
        os.close(fd)


def _read_file(name, dir_fd, cap):
    """Return the bytes of a regular file under dir_fd (not following a link).

    Raises FileNotFoundError when it is absent and OSError for anything else wrong.
    """
    fd = os.open(name, _LEAF_FLAGS, dir_fd=dir_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(errno.EINVAL, "not a regular file")
        return _read_capped(fd, cap)
    finally:
        os.close(fd)


def _unlink(name, dir_fd):
    try:
        os.unlink(name, dir_fd=dir_fd)
    except OSError:
        pass


def _backup_number(name):
    match = _BACKUP_RE.match(name) if isinstance(name, str) else None
    return int(match.group(1)) if match else None


def _valid_backup(name):
    return isinstance(name, str) and _BACKUP_RE.match(name) is not None


def _trim(rows, current_hash):
    """Drop trailing rows that never applied: before equals the file, after does not."""
    if current_hash is None:
        return list(rows)
    keep = list(rows)
    while keep:
        last = keep[-1]
        if last.get("before_sha256") == current_hash and last.get("after_sha256") != current_hash:
            keep.pop()
        else:
            break
    return keep


def _file_hash(target):
    """Hash of the target file, or None when it cannot be read."""
    try:
        return _sha(read_target(target))
    except (Refused, OSError):
        return None


# The store

class Store:
    """The backup store for one config folder, and the only place that writes."""

    def __init__(self, config_dir, fixed_now=None):
        self.config_dir = config_dir
        self.fixed_now = fixed_now
        self.seam = None  # callable(name), for tests
        self._lock = threading.Lock()

    # Public reads

    def target_id(self, target):
        return _target_id(target)

    def backup_path(self, target, name):
        """Full path of a backup, for display. None when the name is not a backup name."""
        if not _valid_backup(name):
            return None
        return os.path.join(self.config_dir, STORE_DIR, BACKUPS_DIR, _target_id(target), name)

    def rows(self, target):
        """The visible rows, oldest first. Reads only and creates nothing."""
        rows = self._read_rows(target, strict=False)
        return _trim(rows, _file_hash(target))

    def find(self, target, edit_id):
        for row in self.rows(target):
            if row.get("id") == edit_id:
                return row
        return None

    def undo_state(self, target, row):
        """None, "changed_since_save", "backup_pruned" or "backup_damaged". Reads only."""
        current = _file_hash(target)
        if current is None or current != row.get("after_sha256"):
            return "changed_since_save"
        name = row.get("backup")
        if not _valid_backup(name):
            return "backup_pruned"
        store_fd = self._open_store(target, create=False)
        if store_fd is None:
            return "backup_pruned"
        try:
            try:
                data = _read_file(name, store_fd, MAX_FILE)
            except FileNotFoundError:
                return "backup_pruned"
            except OSError:
                return "backup_damaged"
        finally:
            os.close(store_fd)
        if _sha(data) != row.get("before_sha256"):
            return "backup_damaged"
        return None

    # Public writes

    def save(self, target, plan_fn):
        """Apply plan_fn(raw) -> Plan to the target. Returns the new ledger row."""
        def produce(raw, rows, current, store_fd):
            plan = plan_fn(raw)
            return _Job(plan.new_raw, "edit", list(plan.key_path), target.layer,
                        plan.old_value, plan.new_value, None, None, None)
        return self._commit(target, produce)[0]

    def restore(self, target, edit_id, check=None):
        """Put a row's backup back as an undo row. Returns Restored."""
        def produce(raw, rows, current, store_fd):
            row = None
            for item in rows:
                if item.get("id") == edit_id:
                    row = item
                    break
            if row is None:
                raise UnknownEdit(edit_id)
            if check is not None:
                check(rows, row)
            name = row.get("backup")
            if current != row.get("after_sha256"):
                raise ChangedSinceSave(self.backup_path(target, name))
            if not _valid_backup(name):
                raise NotUndoable("backup_pruned")
            try:
                data = _read_file(name, store_fd, MAX_FILE)
            except FileNotFoundError:
                raise NotUndoable("backup_pruned") from None
            except OSError:
                raise BackupDamaged(self.backup_path(target, name)) from None
            if _sha(data) != row.get("before_sha256"):
                raise BackupDamaged(self.backup_path(target, name))
            return _Job(data, "undo", list(row.get("key_path") or []), row.get("layer"),
                        row.get("new_value"), row.get("old_value"), row.get("id"), name, name)
        row, matches = self._commit(target, produce)
        return Restored(row, matches, self.backup_path(target, row.get("restored_from_backup")),
                        self.backup_path(target, row.get("backup")))

    # Internals

    def _seam(self, name):
        if self.seam is not None:
            self.seam(name)

    def _now(self):
        moment = self.fixed_now if self.fixed_now is not None else \
            datetime.datetime.now(datetime.timezone.utc)
        return moment.isoformat()

    def _child_dir(self, parent, name, create):
        """Open a store folder under parent, or None when absent and not creating."""
        if create:
            try:
                os.mkdir(name, 0o700, dir_fd=parent)
            except FileExistsError:
                pass
            except OSError as exc:
                raise WriteFailed("cannot create the backup folder") from exc
        try:
            fd = os.open(name, _SUBDIR_FLAGS, dir_fd=parent)
        except FileNotFoundError:
            if create:
                raise WriteFailed("backup folder missing") from None
            return None
        except OSError as exc:
            raise WriteFailed("backup folder is a link or not a folder") from exc
        try:
            info = os.fstat(fd)
            if info.st_uid != os.geteuid():
                raise WriteFailed("backup folder is not ours")
            if create and stat.S_IMODE(info.st_mode) & 0o077:
                os.fchmod(fd, 0o700)
        except BaseException:
            os.close(fd)
            raise
        return fd

    def _open_store(self, target, create):
        """Return a descriptor for the target's store folder, or None when absent.

        The caller closes it. With create False nothing is created.
        """
        try:
            fd = os.open(self.config_dir, _DIR_FLAGS)
        except FileNotFoundError:
            if create:
                raise WriteFailed("config folder missing") from None
            return None
        except OSError as exc:
            raise WriteFailed("cannot open the config folder") from exc
        for name in (STORE_DIR, BACKUPS_DIR, _target_id(target)):
            try:
                child = self._child_dir(fd, name, create)
            except BaseException:
                os.close(fd)
                raise
            os.close(fd)
            if child is None:
                return None
            fd = child
        return fd

    def _read_ledger(self, store_fd):
        """Return the ledger's rows, [] when absent. Raises ValueError when damaged."""
        try:
            data = _read_file(LEDGER_FILE, store_fd, MAX_LEDGER)
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise ValueError("ledger unreadable") from exc
        if len(data) > MAX_LEDGER:
            raise ValueError("ledger too large")
        try:
            doc = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError) as exc:
            raise ValueError("ledger does not parse") from exc
        if not isinstance(doc, dict) or doc.get("version") != 1 \
                or not isinstance(doc.get("rows"), list) \
                or not all(isinstance(row, dict) for row in doc["rows"]):
            raise ValueError("ledger has the wrong shape")
        return doc["rows"]

    def _read_rows(self, target, strict):
        store_fd = self._open_store(target, create=False)
        if store_fd is None:
            return []
        try:
            return self._read_ledger(store_fd)
        except ValueError:
            if strict:
                raise WriteFailed("the ledger is damaged") from None
            return []
        finally:
            os.close(store_fd)

    def _write_ledger(self, store_fd, rows):
        """Write ledger.json by temp file, fsync and rename by descriptor."""
        data = json.dumps({"version": 1, "rows": rows}, indent=1).encode("utf-8")
        temp = ".ledger-%s.tmp" % secrets.token_hex(8)
        try:
            _create_file(temp, data, store_fd)
            os.rename(temp, LEDGER_FILE, src_dir_fd=store_fd, dst_dir_fd=store_fd)
        except OSError:
            _unlink(temp, store_fd)
            raise
        _fullfsync(store_fd)

    def _acquire_flock(self, store_fd):
        """Take the store's flock, retrying for LOCK_WAIT seconds. Returns the lock fd."""
        if fcntl is None:
            raise WriteFailed("no file locking on this platform")
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                         0o600, dir_fd=store_fd)
        except OSError as exc:
            raise WriteFailed("cannot open the lock file") from exc
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise WriteFailed("the lock file is not a file")
            deadline = time.monotonic() + LOCK_WAIT
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return fd
                except OSError as exc:
                    if exc.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                        raise WriteFailed("cannot lock the store") from exc
                if time.monotonic() >= deadline:
                    raise WriteFailed("the store is locked by another writer")
                time.sleep(0.02)
        except BaseException:
            os.close(fd)
            raise

    def _next_number(self, store_fd, rows):
        numbers = [_backup_number(row.get("backup")) for row in rows]
        numbers += [_backup_number(name) for name in os.listdir(store_fd)]
        top = max([n for n in numbers if n is not None] or [0])
        if top + 1 > 999999:
            raise WriteFailed("backup numbers are used up")
        return top + 1

    def _make_row(self, job, edit_id, backup, before_raw):
        name = job.key_path[-1] if job.key_path else None
        return {
            "id": edit_id,
            "time": self._now(),
            "kind": job.kind,
            "key_path": list(job.key_path),
            "layer": job.layer,
            "old_value": collect.mask(job.old_value, name),
            "new_value": collect.mask(job.new_value, name),
            "before_sha256": _sha(before_raw),
            "after_sha256": _sha(job.new_raw),
            "backup": backup,
            "restored_from": job.restored_from,
            "restored_from_backup": job.restored_from_backup,
        }

    def _commit(self, target, produce):
        """The save order, shared by save and restore. Returns (row, matches_backup)."""
        try:
            read_target(target)  # a refused target creates no store folder
            with self._lock:
                store_fd = self._open_store(target, create=True)
                try:
                    lock_fd = self._acquire_flock(store_fd)
                    try:
                        return self._commit_locked(target, produce, store_fd)
                    finally:
                        os.close(lock_fd)
                finally:
                    os.close(store_fd)
        except OSError as exc:
            raise WriteFailed(str(exc)) from exc

    def _commit_locked(self, target, produce, store_fd):
        try:
            with _walk(target) as s1:
                self._seam("after_read")
                raw = s1.raw
                current = _sha(raw)
                try:
                    all_rows = self._read_ledger(store_fd)
                except ValueError:
                    raise WriteFailed("the ledger is damaged") from None
                rows = _trim(all_rows, current)
                job = produce(raw, rows, current, store_fd)
                if job.new_raw == raw:
                    raise Refused("no_change")
                return self._apply(target, job, s1, store_fd, raw, all_rows, rows)
        except OSError as exc:
            raise WriteFailed(str(exc)) from exc

    def _apply(self, target, job, s1, store_fd, raw, all_rows, rows):
        """Steps 3 to 8. Cleans up and raises WriteFailed, Stale or Refused before the rename."""
        edit_id = secrets.token_hex(8)
        made = {"backup": None, "ledger": False, "temp": None}
        try:
            self._seam("before_backup")
            backup = "%06d-%s.bak" % (self._next_number(store_fd, all_rows), edit_id)
            made["backup"] = backup
            _create_file(backup, raw, store_fd)
            if _read_file(backup, store_fd, MAX_FILE) != raw:
                raise WriteFailed("the backup does not match what was read")
            self._seam("after_backup")

            row = self._make_row(job, edit_id, backup, raw)
            made["ledger"] = True
            self._write_ledger(store_fd, rows + [row])
            self._seam("after_ledger")

            for name in os.listdir(s1.dir_fd):
                if _TEMP_RE.match(name):
                    _unlink(name, s1.dir_fd)
            temp = ".routing-dashboard-%s.tmp" % secrets.token_hex(8)
            made["temp"] = temp
            _create_file(temp, job.new_raw, s1.dir_fd, final_mode=s1.mode)
            self._seam("after_temp")

            self._seam("before_recheck")
            with _walk(target) as s6:
                if (s6.dev, s6.ino) != (s1.dev, s1.ino) or s6.raw != raw:
                    raise Stale("file")
                self._seam("before_rename")
                os.rename(temp, target.name, src_dir_fd=s1.dir_fd, dst_dir_fd=s6.dir_fd)
            made["temp"] = None
        except (StoreError, OSError) as exc:
            self._cleanup(s1, store_fd, made, all_rows)
            if isinstance(exc, StoreError):
                raise
            raise WriteFailed(str(exc)) from exc
        self._seam("after_rename")

        matches = self._verify(target, job, s1, store_fd, row)
        self._prune(store_fd, rows + [row])
        return row, matches

    def _cleanup(self, s1, store_fd, made, old_rows):
        """Best effort: remove the temp file, roll the ledger back, remove the new backup."""
        if made["temp"] is not None:
            try:
                os.unlink(made["temp"], dir_fd=s1.dir_fd)
            except OSError:
                pass
        if made["ledger"]:
            try:
                self._write_ledger(store_fd, old_rows)
            except OSError:
                pass
        if made["backup"] is not None:
            try:
                os.unlink(made["backup"], dir_fd=store_fd)
            except OSError:
                pass

    def _verify(self, target, job, s1, store_fd, row):
        """Step 7. Returns matches_backup (None for a save). Raises Raced or Unverified."""
        backup_path = self.backup_path(target, row["backup"])
        source_path = self.backup_path(target, job.source) if job.source else None
        fsync_error = None
        try:
            self._seam("dir_fsync")
            _fullfsync(s1.dir_fd)
        except OSError as exc:
            fsync_error = exc
        try:
            self._seam("reread")
            with _walk(target) as s7:
                got = s7.raw
        except (OSError, Refused):
            raise Unverified("reread", row, backup_path) from None
        restoring = job.source is not None
        if got != job.new_raw:
            raise Raced(row, backup_path, False if restoring else None, source_path)
        if restoring:
            try:
                again = _read_file(job.source, store_fd, MAX_FILE)
            except OSError:
                again = None
            if again != got:
                raise Raced(row, backup_path, False, source_path)
        if fsync_error is not None:
            raise Unverified("fsync", row, backup_path)
        return True if restoring else None

    def _prune(self, store_fd, rows):
        """Keep the newest RETENTION rows and the backups they name. Never fails a save."""
        try:
            kept = rows[-RETENTION:]
            if len(kept) < len(rows):
                try:
                    self._write_ledger(store_fd, kept)
                except OSError:
                    kept = rows
            named = set(row.get("backup") for row in kept)
            for name in os.listdir(store_fd):
                if _BACKUP_RE.match(name) and name not in named:
                    _unlink(name, store_fd)
        except OSError:
            pass
