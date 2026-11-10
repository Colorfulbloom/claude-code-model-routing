"""Build the problem rows a setup collector reports (m4-build.md section 5).

A collector gives each diagnostic as a ``ProblemRow``. The id is
``<code>:<item id or file>`` with ``:<line>`` added when there is one, so it stays the
same across refetches. Read failures are not built here: they are ``UnreadableFile``
entries, and the problems feed makes their rows.
"""

from collections.abc import Mapping

from models import (
    Confidence,
    ConfidenceLevel,
    ProblemFix,
    ProblemGroup,
    ProblemKind,
    ProblemRow,
    SetupPart,
)

_KINDS: dict[ProblemGroup, ProblemKind] = {
    "couldnt_read": "read_failure",
    "wont_load": "problem",
    "not_as_set": "problem",
    "cant_tell": "cant_tell",
    "notice": "notice",
}


def confidence(level: ConfidenceLevel, tested_on: str | None = None) -> Confidence:
    """Return a ``Confidence``. ``tested_on`` belongs to the ``tested`` level only."""
    return Confidence(level=level, tested_on=tested_on)


def problem_id(code: str, anchor: str, line: int | None) -> str:
    """Return the stable id of a problem row."""
    parts = [code, anchor]
    if line is not None:
        parts.append(str(line))
    return ":".join(parts)


def default_fix(item_id: str | None, full_path: str | None) -> ProblemFix:
    """Return the fix a row offers when the collector names none.

    A row about an item opens the item. A row about a file only copies its path.
    """
    if item_id is not None:
        return ProblemFix(kind="open_item", target=item_id, reason=None)
    if full_path is not None:
        return ProblemFix(kind="copy_path", target=full_path, reason=None)
    return ProblemFix(kind="cant_fix_here", target=None, reason="not_visible")


def make_row(  # noqa: PLR0913 - one keyword per field of the row
    *,
    code: str,
    group: ProblemGroup,
    thing: str,
    part: SetupPart,
    item_id: str | None,
    file: str | None,
    full_path: str | None,
    line: int | None,
    level: ConfidenceLevel,
    tested_on: str | None = None,
    params: Mapping[str, str] | None = None,
    fix: ProblemFix | None = None,
) -> ProblemRow:
    """Build one problem row.

    Args:
        code: The problem code (m4-build.md section 5 lists them).
        group: The row's group. ``kind`` follows from it.
        thing: The display name the title names (an item name, or a file name).
        part: The part the row belongs to.
        item_id: The item the row is about, or None for a file with no item.
        file: The display path of the file, or None.
        full_path: The absolute path of the file, or None.
        line: The line, or None.
        level: How sure the dashboard is.
        tested_on: The Claude Code version a test ran on, for ``tested``.
        params: String parameters for the page's words.
        fix: The one action the row offers, or None for ``default_fix``.

    Returns:
        The row, with a stable id.
    """
    anchor = item_id or file or thing
    return ProblemRow(
        id=problem_id(code, anchor, line),
        kind=_KINDS[group],
        group=group,
        code=code,
        thing=thing,
        part=part,
        item_id=item_id,
        file=file,
        full_path=full_path,
        line=line,
        params=dict(params or {}),
        confidence=confidence(level, tested_on),
        fix=fix if fix is not None else default_fix(item_id, full_path),
    )
