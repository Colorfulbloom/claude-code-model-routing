"""Every word the edit server can emit is in a closed set the page types against.

The page's TypeScript reads these as string unions (``schema.d.ts``), so a code the
server invents that the models do not list would reach the page as an unknown word.
This test reads the server's own source with ``ast`` and collects each literal code it
passes to a refusal, a row status or a warning, then checks each against its
``Literal`` in ``models.py``. A new code in the writer fails here until the models
list it.
"""

import ast
import typing
from pathlib import Path

import models

SERVER = Path(__file__).resolve().parents[1]
SOURCES = (
    "api_edit.py",
    "edit_diff.py",
    "edit_history.py",
    "edit_preview.py",
    "edit_seen.py",
    "edit_service.py",
    "edit_store.py",
    "gate.py",
    "json_edit.py",
)


def literal_args(name: str, position: int) -> dict[str, list[str]]:
    """Map each source file to the string constants at ``position`` in ``name(...)``."""
    found: dict[str, list[str]] = {}
    for source in SOURCES:
        tree = ast.parse((SERVER / source).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            called = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else ""
            )
            if called != name or len(node.args) <= position:
                continue
            arg = node.args[position]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.setdefault(source, []).append(arg.value)
    return found


def allowed(literal: object) -> set[str]:
    return {str(item) for item in typing.get_args(literal)}


def test_every_refusal_code_in_the_source_is_in_the_models_literal() -> None:
    codes = allowed(models.EditRefusalCode)
    seen = literal_args("Refused", 0)
    assert seen["edit_store.py"], (
        "the scan found no refusals, so it reads the wrong calls"
    )
    for source, words in seen.items():
        for word in words:
            assert word in codes, (source, word)


def test_the_writers_own_code_table_is_inside_the_models_literal() -> None:
    import edit_store

    assert set(edit_store._CODES) <= allowed(models.EditRefusalCode)  # pyright: ignore[reportPrivateUsage]


def test_every_not_undoable_reason_is_in_the_closed_set() -> None:
    reasons = allowed(models.NotUndoableReason)
    from_params: set[str] = set()
    for source in SOURCES:
        tree = ast.parse((SERVER / source).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Refused"
                and len(node.args) > 1
                and isinstance(node.args[1], ast.Dict)
            ):
                for key, value in zip(
                    node.args[1].keys, node.args[1].values, strict=True
                ):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "reason"
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and node.args[0].value == "not_undoable"  # type: ignore[attr-defined]
                    ):
                        from_params.add(value.value)
    assert from_params <= reasons
    status_words = {
        word for words in literal_args("RowStatus", 1).values() for word in words
    }
    # "changed_since_save" is the 409 code's word, not a not-undoable reason
    assert status_words - {"changed_since_save"} <= reasons
    assert "backup_damaged" in reasons  # backup_state returns it through a variable


def test_every_warning_and_recheck_word_is_in_its_literal() -> None:
    warnings = set(_keyword_values("edit_preview.py", "EditWarning", "code"))
    assert warnings == allowed(models.EditWarningCode)
    states = {
        word for words in literal_args("_recheck_result", 0).values() for word in words
    }
    assert states == {"confirmed", "overwritten"}
    assert states | {"checking"} == allowed(models.RecheckState)


def test_every_row_undo_state_the_writer_gives_is_in_the_literal() -> None:
    states = {word for words in literal_args("RowStatus", 0).values() for word in words}
    assert states <= allowed(models.UndoState)
    # "undone" is chosen by a conditional expression, which the scan can't read
    assert states | {"undone"} == allowed(models.UndoState)


def test_the_read_only_and_applies_words_are_in_their_literals() -> None:
    import edit_preview
    from edit_store import _CODES  # pyright: ignore[reportPrivateUsage]

    reasons = allowed(models.EditReadOnlyCode)
    for code in (*_CODES, "managed", "link_outside", "not_editable"):
        assert edit_preview.read_only_reason(code) in reasons
    assert edit_preview.APPLIES in allowed(models.EditApplies)


def _keyword_values(source: str, call: str, keyword: str) -> list[str]:
    """Return the string constants passed as ``keyword=`` to ``call(...)``."""
    tree = ast.parse((SERVER / source).read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else ""
        )
        if name != call:
            continue
        for item in node.keywords:
            if (
                item.arg == keyword
                and isinstance(item.value, ast.Constant)
                and isinstance(item.value.value, str)
            ):
                out.append(item.value.value)
    return out
