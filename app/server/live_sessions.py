"""The running-session list behind Live's Session Select.

``build_live_sessions`` lists the sessions with a request in the 30 minutes before the
clock T, in every project, newest last request first (ties by id, descending). Each
one says whether it is working or idle and how many of its runs are working, by the
same run rules as the timeline. ``latest_ended`` is the newest session of one project
that is no longer running, for the nothing-running state.

A session belongs to the project its transcript folder maps to in ``folder_keys``, the
provider's folder-to-project map (the one ``/api/projects`` uses). A session in a folder
the map does not hold is left out, because the list cannot say which project it is in.
Requests after T are ignored, as in the timeline.
"""

import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime

import ingest
import timeline
from models import EndedSession, LiveSession, LiveSessions

_BEST = timeline.BEST_SQL
_SPAN_SQL = (
    "SELECT MIN(r.ts), MAX(r.ts), COUNT(*)"  # noqa: S608
    " FROM requests AS r JOIN files AS f ON f.id = r.file_id"
    f" WHERE f.session_id = ? AND r.ts <= ? AND {_BEST}"
)


def _span(
    conn: sqlite3.Connection, session_id: str, at: str
) -> tuple[datetime, datetime, int] | None:
    """Return the first request, the last request at or before ``at`` and the count."""
    row = conn.execute(_SPAN_SQL, (session_id, at)).fetchone()
    if row is None or row[0] is None:
        return None
    return timeline.parse_ts(str(row[0])), timeline.parse_ts(str(row[1])), int(row[2])


def build_live_sessions(
    conn: sqlite3.Connection,
    *,
    project_key: str,
    now: datetime,
    project_names: Mapping[str, str],
    folder_keys: Mapping[str, str],
) -> LiveSessions:
    """Build the session list at clock ``now``.

    Args:
        conn: A read connection to the store.
        project_key: The project whose newest ended session is wanted.
        now: The clock T, aware.
        project_names: The display name of each project key. A key with no name shows
            as itself.
        folder_keys: The project key of each transcript folder.

    Returns:
        The running sessions of every project and the newest ended one of
        ``project_key``.
    """
    t = now.astimezone(UTC)
    at = ingest.ts_text(t)
    cutoff = ingest.ts_text(t - timeline.RUNNING_WINDOW)
    running: list[tuple[datetime, str, LiveSession]] = []
    for session_id, folder, branch in conn.execute(
        "SELECT session_id, folder, branch FROM sessions"
        " WHERE last_ts > ? AND first_ts <= ?",
        (cutoff, at),
    ).fetchall():
        project = folder_keys.get(str(folder))
        if project is None:
            continue
        span = _span(conn, str(session_id), at)
        if span is None:
            continue
        first, last, count = span
        isrunning, active, state = timeline.session_state(last, t)
        if not isrunning:
            continue
        data = timeline.load_session(conn, str(session_id), t, project_key=None)
        if data is None:
            continue
        working = sum(1 for r in timeline.analyze_runs(data, t) if r.state == "working")
        running.append(
            (
                last,
                str(session_id),
                LiveSession(
                    id=str(session_id),
                    project=project,
                    project_name=project_names.get(project, project),
                    branch=None if branch is None else str(branch),
                    started=first,
                    last_request=last,
                    active=active,
                    state="working" if state == "working" else "idle",
                    runs_working=working,
                    requests=count,
                ),
            )
        )
    running.sort(key=lambda r: (r[0], r[1]), reverse=True)
    sessions = [r[2] for r in running]
    answer = LiveSessions(
        server_time=t,
        as_of=timeline.as_of(conn, t),
        etag="",
        unchanged=False,
        sessions=sessions,
        latest_ended=_latest_ended(conn, project_key, folder_keys, t, at),
    )
    body = answer.model_dump(mode="json", exclude={"server_time", "etag"})
    return answer.model_copy(update={"etag": timeline.digest(body)})


def _latest_ended(
    conn: sqlite3.Connection,
    project_key: str,
    folder_keys: Mapping[str, str],
    t: datetime,
    at: str,
) -> EndedSession | None:
    """Return the newest session of the project that has requests but is not running."""
    folders = sorted(f for f, key in folder_keys.items() if key == project_key)
    if not folders:
        return None
    marks = ",".join("?" * len(folders))
    candidates = conn.execute(
        "SELECT session_id, branch FROM sessions"  # noqa: S608
        f" WHERE folder IN ({marks}) AND first_ts <= ?"
        " ORDER BY last_ts DESC, session_id DESC",
        (*folders, at),
    ).fetchall()
    for session_id, branch in candidates:
        span = _span(conn, str(session_id), at)
        if span is None:
            continue
        first, last, count = span
        if timeline.session_state(last, t)[0]:
            continue
        return EndedSession(
            id=str(session_id),
            branch=None if branch is None else str(branch),
            started=first,
            last_request=last,
            requests=count,
        )
    return None
