"""The one registry of every code the setup read side can emit (m4-build.md task 9).

The collectors, the answer builder and the problems feed name things with short codes:
a problem's code, an item's reason, a file that could not be read, a part, a scope, a
fix. The page turns each code into words, so a code with no entry here has no string.
This module is the single list task 12 writes strings against, and the closed-enum test
(``test_setup_codes.py``) fails when a collector emits a code that is missing from it.

Problem codes map to the group they appear in. Reasons that are not problems (an
item's ``reason.code``, the summary and usage codes) are plain sets.
"""

from typing import Final, get_args

from models import (
    SETUP_PARTS,
    SETUP_SCOPES,
    EmptyAction,
    EmptyReason,
    FixKind,
    ImportState,
    LoadsKind,
    ModelCheckStatus,
    PermissionKind,
    ProblemGroup,
    ReadOnlyCode,
    UnreadableReason,
)

# Problem codes by group. The first block is the plan's list (m4-build.md section 5);
# the others were added while building the collectors and are marked.
PROBLEM_CODES: Final[dict[str, ProblemGroup]] = {
    # Couldn't read. The first five are ``UnreadableFile.reason`` values that make a
    # row.
    "permission": "couldnt_read",
    "not_utf8": "couldnt_read",
    "too_large": "couldnt_read",
    "folder_unlistable": "couldnt_read",
    "transcript_unreadable": "couldnt_read",
    "vanished": "couldnt_read",  # beyond the plan
    # Won't load.
    "json_invalid": "wont_load",
    "not_object": "wont_load",
    "managed_invalid": "wont_load",
    "value_invalid": "wont_load",
    "frontmatter_invalid": "wont_load",
    "agent_no_name": "wont_load",
    "agent_no_description": "wont_load",
    "agent_not_md": "wont_load",
    "same_name_in_folder": "wont_load",
    "skill_no_md": "wont_load",
    "import_missing": "wont_load",
    "import_too_deep": "wont_load",
    "import_cycle": "wont_load",
    "hook_bad_event": "wont_load",
    "hook_bad_handler": "wont_load",
    "mcp_bad_entry": "wont_load",
    "plugin_not_installed": "wont_load",
    "plugin_manifest_invalid": "wont_load",
    "output_style_missing": "wont_load",
    "permission_rule_invalid": "wont_load",
    # Not as set.
    "ignored": "not_as_set",
    "lowered": "not_as_set",
    "plugin_field_ignored": "not_as_set",
    "hooks_disabled": "not_as_set",
    "agent_lowered": "not_as_set",  # beyond the plan
    # Can't tell.
    "unknown": "cant_tell",
    "import_out_of_scope": "cant_tell",
    "env_not_visible": "cant_tell",
    "plugin_format_unknown": "cant_tell",
    "walk_stopped": "cant_tell",
    "frontmatter_reader_gap": "cant_tell",  # beyond the plan
    "plugin_outside_plugins": "cant_tell",  # beyond the plan
    # Notices.
    "rows_no_usage": "notice",
}

# Files that could not be read, by reason. ``outside_scope`` and
# ``plugin_outside_plugins`` are "not read here", not failures, so they make no
# Couldn't read row.
UNREADABLE_REASONS: Final[tuple[UnreadableReason, ...]] = get_args(UnreadableReason)
NOT_READ_REASONS: Final[frozenset[str]] = frozenset(
    {"outside_scope", "plugin_outside_plugins"}
)
READ_FAILURE_REASONS: Final[tuple[str, ...]] = tuple(
    reason for reason in UNREADABLE_REASONS if reason not in NOT_READ_REASONS
)

# The seven statuses an item or a source carries.
STATUSES: Final[tuple[ModelCheckStatus, ...]] = get_args(ModelCheckStatus)

# ``ItemReason.code`` values. A status can be a reason by itself, so the seven status
# words are in the set.
ITEM_REASON_CODES: Final[frozenset[str]] = frozenset(
    {
        *STATUSES,
        "agent_loads",
        "agent_no_description",
        "agent_overrides",
        "env_not_visible",
        "frontmatter_invalid",
        "frontmatter_reader_gap",
        "hooks_disabled",
        "mcp_bad_entry",
        "mcp_not_approved",
        "plugin_loads",
        "plugin_manifest_invalid",
        "plugin_not_enabled",
        "plugin_not_installed",
        "plugin_outside_plugins",
        "same_name_in_folder",
    }
)

# The reason an Agents page row carries when the page cannot judge its model: a plugin
# or
# managed agent is read by the setup half, not by the resolver the Model check uses
# (``AgentRow.reason_code``, ``ModelCheckRow.reason_code``).
AGENT_CHECK_CODES: Final[frozenset[str]] = frozenset({"agent_source_unchecked"})

# Fix kinds, and why a row can't be fixed here (``ProblemFix.reason``).
FIX_KINDS: Final[tuple[FixKind, ...]] = get_args(FixKind)
CANT_FIX_REASONS: Final[frozenset[str]] = frozenset(
    {"managed", "plugin", "not_visible", "not_fixable", "walk_stopped"}
)

# The ``why`` param of the two problem codes that carry one. The page words each.
WHY_CODES: Final[dict[str, frozenset[str]]] = {
    "hook_bad_handler": frozenset(
        {
            "not_object",
            "no_type",
            "unknown_type",
            "no_command",
            "bad_args",
            "no_url",
            "no_tool",
            "no_prompt",
        }
    ),
    "mcp_bad_entry": frozenset(
        {
            "no_command_or_url",
            "url_without_type",
            "no_url",
            "no_command",
            "unknown_type",
            "bad_type",
            "bad_field",
            "not_object",
        }
    ),
}

READ_ONLY_CODES: Final[tuple[ReadOnlyCode, ...]] = get_args(ReadOnlyCode)
IMPORT_STATES: Final[tuple[ImportState, ...]] = get_args(ImportState)
LOADS_KINDS: Final[tuple[LoadsKind, ...]] = get_args(LoadsKind)
PERMISSION_KINDS: Final[tuple[PermissionKind, ...]] = get_args(PermissionKind)
EMPTY_REASONS: Final[tuple[EmptyReason, ...]] = get_args(EmptyReason)
EMPTY_ACTIONS: Final[tuple[EmptyAction, ...]] = get_args(EmptyAction)

# What the setup map says about a part (``SetupPartRow.summary.code``).
SUMMARY_CODES: Final[dict[str, str]] = {
    "settings": "model_effort",
    "agents": "agents",
    "instructions": "instructions",
    "rules": "rules",
    "skills": "skills",
    "hooks": "hooks",
    "permissions": "permissions",
    "mcp": "mcp",
    "plugins": "plugins",
    "output_style": "output_style",
}
# What one scope cell says (``SetupScopeCell.summary.code``).
CELL_CODES: Final[frozenset[str]] = frozenset({"count", "model_effort"})
# ``SetupItem.usage.code``.
USAGE_CODES: Final[frozenset[str]] = frozenset({"agent_runs", "runs_at_value"})
# ``SetupItem.group`` values that the answer builder sets (a collector sets its own).
AGENT_GROUPS: Final[tuple[str, ...]] = ("ran", "no_runs")
# ``SetupMap.notices[].code``.
NOTICE_CODES: Final[frozenset[str]] = frozenset({"project_not_listed", "rows_no_usage"})

PARTS: Final = SETUP_PARTS
SCOPES: Final = SETUP_SCOPES


def group_of(code: str) -> ProblemGroup | None:
    """Return the group a problem code belongs to, or None for an unregistered code."""
    return PROBLEM_CODES.get(code)
