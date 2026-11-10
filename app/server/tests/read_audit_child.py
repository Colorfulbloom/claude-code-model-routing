"""Run ``serve.main`` with an audit hook that logs every read path.

``test_real_reads.py`` starts this script as a subprocess in place of ``serve.py``. The
hook appends one ``<event>\\t<absolute path>`` line to the file named by
``BARTAB_READ_AUDIT_LOG`` for every ``open``, ``os.listdir`` and ``os.scandir`` event,
then the script runs the server with the arguments it was given. The log is how the
test proves the server read nothing outside the allowed roots (m4-build.md section 7).

The log file descriptor is opened before the hook is installed and written with
``os.write``, so the hook never logs itself. Paths are made absolute against the
working folder, which is the server folder. A file descriptor argument has no path and
is skipped.
"""

import os
import sys
from pathlib import Path
from typing import cast

LOG_ENV = "BARTAB_READ_AUDIT_LOG"
EVENTS = frozenset({"open", "os.listdir", "os.scandir"})


def install(log_path: str) -> None:
    """Install the audit hook. It cannot be removed, so call it once."""
    fd = os.open(log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)

    def hook(event: str, args: tuple[object, ...]) -> None:
        if event not in EVENTS:
            return
        target = args[0] if args else None
        if target is None:
            target = "."
        if isinstance(target, int):
            return
        try:
            path = os.path.abspath(os.fsdecode(cast("str | bytes", target)))  # noqa: PTH100
        except (TypeError, ValueError):
            return
        os.write(fd, f"{event}\t{path}\n".encode(errors="replace"))

    sys.addaudithook(hook)


def main() -> int:
    """Install the hook, then run the server with this script's arguments."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    install(os.environ[LOG_ENV])
    import serve

    return serve.main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
