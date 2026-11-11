"""The settings field registry for Bar Tab edits.

The plan is ``docs/rebuild/planning/m6-build.md`` section 2, "Field registry".

Pure data and small helpers, with no file access. The writer, the preview builder and
the routes read this table and nothing else to learn which settings a save can change.

The rule for where a value goes: the writer edits the key path the resolver reports for
the file, else it inserts the top-level key. The resolver reports one of three paths for
a file that sets the field. They are the top-level key, an ``env`` twin such as
``env.CLAUDE_CODE_EFFORT_LEVEL``, or a ``modelSettings.<model>.<field>`` entry. A file
that sets the field in none of them gets the top-level key.

Where each row comes from:

- Top-level key. ``resolve.SETTINGS_KEYS`` (``app/server/resolve.py``), the entries
  whose scope is ``main``.
- Env twins. The ``variables`` list in ``app/server/data/rules.json``, the rows whose
  scope is ``main`` (``ANTHROPIC_MODEL``, ``CLAUDE_CODE_EFFORT_LEVEL`` and
  ``CLAUDE_CODE_AUTO_COMPACT_WINDOW``). ``CLAUDE_CODE_SUBAGENT_MODEL`` feeds an agent
  row only, so it is not a twin of the main ``model`` row. The effort cap has no
  variable.
- ``modelSettings`` fields. ``resolve.MODEL_SETTINGS_FIELDS``. The model row has none.
- Value rules. Effort level in a file: rule ``effort-level-settings-values``. Effort
  cap: rule ``max-effort-level-values``. Window: rules
  ``auto-compact-window-values`` and
  ``model-settings-auto-compact-window``, with the old app's bounds
  (``dashboard/api_edit.py``, ``_compact_ok``). Model: any printable name, because the
  catalog is open-ended.
- Item ids. ``setup_items.make_item`` names a Settings item ``settings:<key>``.

Four Settings items wait for M7. They keep a read-only reason, ``field_until_m7``.
"""

from dataclasses import dataclass
from typing import Literal

from models import EditReadOnlyCode, SettingsEditField

ValueKind = Literal["effort", "effort_cap", "model", "window"]

# What a settings file may hold for ``effortLevel`` (rule effort-level-settings-values).
EFFORT_FILE_LEVELS: tuple[str, ...] = ("low", "medium", "high", "xhigh")
# What ``maxEffortLevel`` may hold (rule max-effort-level-values), lowest first.
EFFORT_CAP_LEVELS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")

# ``autoCompactWindow``: a whole number of tokens in this range, or "auto" on a
# ``modelSettings`` path only (the window tuned for the model).
WINDOW_MIN = 100000
WINDOW_MAX = 1000000
WINDOW_AUTO = "auto"

MODEL_MAX_LENGTH = 200


@dataclass(frozen=True)
class EditField:
    """One settings field a save can change.

    ``env_twins`` are the process variables that feed the same main row.
    ``model_settings_fields`` are the names inside ``modelSettings.<model>`` that feed
    it. ``item_id`` is the id of the Settings item the inspector shows for the row.
    """

    name: SettingsEditField
    top_key: str
    env_twins: tuple[str, ...]
    model_settings_fields: tuple[str, ...]
    value_kind: ValueKind
    item_id: str


FIELDS: dict[SettingsEditField, EditField] = {
    "model": EditField(
        name="model",
        top_key="model",
        env_twins=("ANTHROPIC_MODEL",),
        model_settings_fields=(),
        value_kind="model",
        item_id="settings:model",
    ),
    "effortLevel": EditField(
        name="effortLevel",
        top_key="effortLevel",
        env_twins=("CLAUDE_CODE_EFFORT_LEVEL",),
        model_settings_fields=("effortLevel", "effort"),
        value_kind="effort",
        item_id="settings:effortLevel",
    ),
    "maxEffortLevel": EditField(
        name="maxEffortLevel",
        top_key="maxEffortLevel",
        env_twins=(),
        model_settings_fields=("maxEffortLevel",),
        value_kind="effort_cap",
        item_id="settings:maxEffortLevel",
    ),
    "autoCompactWindow": EditField(
        name="autoCompactWindow",
        top_key="autoCompactWindow",
        env_twins=("CLAUDE_CODE_AUTO_COMPACT_WINDOW",),
        model_settings_fields=("autoCompactWindow",),
        value_kind="window",
        item_id="settings:autoCompactWindow",
    ),
}

# Settings items that wait for M7: thinking, cache lifetime, allowed models and
# fallback models. They show as read-only with the reason ``field_until_m7``.
FIELD_UNTIL_M7_ITEMS: frozenset[str] = frozenset(
    {
        "settings:alwaysThinkingEnabled",
        "settings:promptCacheTtl",
        "settings:availableModels",
        "settings:fallbackModel",
    }
)

_BY_ITEM: dict[str, SettingsEditField] = {
    field.item_id: name for name, field in FIELDS.items()
}


def field_for_item(item_id: str) -> SettingsEditField | None:
    """Return the field a Settings item edits, or None when it has no edit here."""
    return _BY_ITEM.get(item_id)


def read_only_code_for_item(item_id: str) -> EditReadOnlyCode | None:
    """Return ``field_until_m7`` for an item that waits for M7, else None.

    None does not mean the item is writable. A managed value, a plugin file and a
    path that can't be written get their own codes from the writer.
    """
    return "field_until_m7" if item_id in FIELD_UNTIL_M7_ITEMS else None


def accepts(field: SettingsEditField, value: object, *, nested: bool = False) -> bool:
    """Return True when ``value`` fits the field's rule, so a save can write it.

    Args:
        field: The field being edited.
        value: The value from the request. A bool never fits.
        nested: True when the key path is under ``modelSettings``, where the window
            also takes "auto".

    Returns:
        False for a value the save refuses with ``bad_value``.
    """
    if isinstance(value, bool):
        return False
    kind = FIELDS[field].value_kind
    if kind == "effort":
        return isinstance(value, str) and value in EFFORT_FILE_LEVELS
    if kind == "effort_cap":
        return isinstance(value, str) and value in EFFORT_CAP_LEVELS
    if kind == "window":
        if isinstance(value, int):
            return WINDOW_MIN <= value <= WINDOW_MAX
        return nested and value == WINDOW_AUTO
    return (
        isinstance(value, str)
        and value.strip() != ""
        and len(value) <= MODEL_MAX_LENGTH
        and value.isprintable()
    )


def options(field: SettingsEditField) -> tuple[str, ...] | None:
    """Return an enum field's fixed values, lowest first, or None for an open field."""
    kind = FIELDS[field].value_kind
    if kind == "effort":
        return EFFORT_FILE_LEVELS
    if kind == "effort_cap":
        return EFFORT_CAP_LEVELS
    return None
