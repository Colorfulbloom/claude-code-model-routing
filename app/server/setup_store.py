"""What the store tells the setup answers: run counts and unreadable transcripts.

``usage_of`` counts the last 30 days of runs for the project's transcript folders, with
the same scan Review's Agents page uses, so "runs" means one thing everywhere. It keeps
two things: runs per agent type, and the main session's runs per (model, effort) pair.
``transcripts_of`` lists the transcripts the ingest could not open
(``files.read_errors``
above zero) and counts the files that hold rows without usage. Both read through the
connection they are given and write nothing.
"""

import sqlite3
from collections.abc import Collection, Iterator, Sequence
from datetime import datetime

import problems
import review_query
import review_windows
import setup_answers
from prices import PricesDoc

_MAIN = "@main"
_CHUNK = 500


def usage_of(
    conn: sqlite3.Connection,
    doc: PricesDoc,
    folders: Collection[str],
    *,
    now: datetime,
    tz: str,
) -> setup_answers.SetupUsage:
    """Count runs over the last ``USAGE_DAYS`` days for the given transcript folders.

    Args:
        conn: A read connection to the store.
        doc: The prices document. The scan needs one to price; the counts ignore it.
        folders: The project's transcript folders.
        now: T, aware.
        tz: The zone Review counts local days in.

    Returns:
        The counts. A project with no folders has none.
    """
    window = review_windows.review_window("30d", now, tz, None)
    found = review_query.scan(
        conn,
        doc,
        folders=frozenset(folders),
        start=window.start,
        end=window.end,
        tz=tz,
        now=now,
    )
    agent_runs = {key: len(runs) for key, runs in found.runs.items() if key != _MAIN}
    pairs: dict[tuple[str | None, str | None], int] = {}
    for run in found.runs.get(_MAIN, []):
        pair = (run.get("model"), run.get("effort"))
        pairs[pair] = pairs.get(pair, 0) + 1
    return setup_answers.SetupUsage(
        days=setup_answers.USAGE_DAYS, agent_runs=agent_runs, main_pairs=pairs
    )


def _chunks(items: Sequence[str]) -> Iterator[Sequence[str]]:
    for at in range(0, len(items), _CHUNK):
        yield items[at : at + _CHUNK]


def transcripts_of(
    conn: sqlite3.Connection, folders: Collection[str]
) -> problems.Transcripts:
    """List the project's unreadable transcripts and count its no-usage files.

    Args:
        conn: A read connection to the store.
        folders: The project's transcript folders.

    Returns:
        The absolute paths of files the ingest could not open, sorted, and the number
        of files with rows that carry no usage.
    """
    paths: list[str] = []
    no_usage = 0
    for chunk in _chunks(sorted(folders)):
        marks = ",".join("?" * len(chunk))
        paths.extend(
            str(row[0])
            for row in conn.execute(
                f"SELECT path FROM files WHERE read_errors > 0 AND folder IN ({marks})",  # noqa: S608
                tuple(chunk),
            )
        )
        row = conn.execute(
            f"SELECT COALESCE(SUM(no_usage), 0) FROM files WHERE folder IN ({marks})",  # noqa: S608
            tuple(chunk),
        ).fetchone()
        no_usage += int(row[0])
    return problems.Transcripts(unreadable=tuple(sorted(paths)), no_usage_rows=no_usage)
