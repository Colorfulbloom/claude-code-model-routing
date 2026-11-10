"""The hooks and MCP inputs a plugin hands to the later collectors (m4-build.md task 8).

``collect_plugins`` hands ``handoff["plugins"]`` on in one of two shapes, as
``collect_skills.plugin_paths`` reads for skills.

- A mapping ``{"skills", "commands", "hooks", "mcp"}``, each a list of
  ``{plugin, name, path}``, where ``plugin`` is ``<name>@<marketplace>``. A hooks or MCP
  object written in the manifest is one more row whose ``path`` is the manifest and
  whose ``inline`` is that object.
- A list of ``PluginComponents``, one per enabled plugin.

``rows`` turns either into the same small rows. Anything else is no plugin input.
"""

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from collect_plugins import HANDOFF_PLUGINS, PluginComponents

Kind = Literal["hooks", "mcp"]


@dataclass(frozen=True)
class PluginInput:
    """One hooks or MCP input of a plugin.

    Attributes:
        plugin_id: ``<name>@<marketplace>``.
        name: The plugin's name.
        path: A hooks or MCP file, or the manifest when ``inline`` is set.
        inline: The object written in the manifest, or None for a file.
    """

    plugin_id: str
    name: str
    path: str
    inline: object | None


def _from_row(raw: object) -> PluginInput | None:
    if not isinstance(raw, Mapping):
        return None
    row = cast("Mapping[str, object]", raw)
    plugin_id, path = row.get("plugin"), row.get("path")
    if not isinstance(plugin_id, str) or not isinstance(path, str):
        return None
    name = row.get("name")
    return PluginInput(
        plugin_id,
        name if isinstance(name, str) else plugin_id.split("@")[0],
        path,
        row.get("inline"),
    )


def _from_component(comp: PluginComponents, kind: Kind) -> list[PluginInput]:
    manifest = os.path.join(comp.root, ".claude-plugin", "plugin.json")  # noqa: PTH118
    files = comp.hooks_files if kind == "hooks" else comp.mcp_files
    inline = comp.hooks_inline if kind == "hooks" else comp.mcp_inline
    found = [PluginInput(comp.plugin_id, comp.name, path, None) for path in files]
    if inline is not None:
        found.append(PluginInput(comp.plugin_id, comp.name, manifest, inline))
    return found


def rows(handoff: Mapping[str, object], kind: Kind) -> list[PluginInput]:
    """Return the hooks (or MCP) inputs of every enabled plugin, in handoff order."""
    raw = handoff.get(HANDOFF_PLUGINS)
    found: list[PluginInput] = []
    if isinstance(raw, Mapping):
        listed = cast("Mapping[str, object]", raw).get(kind)
        if isinstance(listed, list):
            for one in cast("list[object]", listed):
                made = _from_row(one)
                if made is not None:
                    found.append(made)
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for comp in cast("Sequence[object]", raw):
            if isinstance(comp, PluginComponents):
                found += _from_component(comp, kind)
    return found
