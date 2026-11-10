"""Run the hooks, MCP and masked-reader collectors under the read audit hook.

Used by ``test_hooks_mcp_audit.py``. The arguments are the config folder, the home
folder, the managed folder, the project folder (``-`` for an unlisted project) and two
decoy paths outside the plugins folder, a hooks file and an MCP file. The hook
(``read_audit_child.install``) logs every ``open``, ``os.listdir`` and ``os.scandir``
path to the file named by ``BARTAB_READ_AUDIT_LOG``. The script runs the chain, then
runs the hooks and MCP collectors once more with plugin input that names the decoys,
asks for each signature, and prints one JSON line with the item counts.
"""

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))


def main(argv: list[str]) -> int:
    """Install the hook, read the project, print the item counts."""
    sys.dont_write_bytecode = True
    config, home, managed, project, decoy_hooks, decoy_mcp = argv
    # Import everything the collectors need before the hook starts, so the log holds
    # reads of data files and project files only.
    import read_audit_child

    import claude_json
    import collect_agents
    import collect_hooks
    import collect_mcp
    import collect_plugins
    import collect_settings
    from setup_contract import Collected, SetupContext

    read_audit_child.install(os.environ[read_audit_child.LOG_ENV])
    ctx = SetupContext(
        project_key="proj",
        config_dir=Path(config),
        home=Path(home),
        project_dir=None if project == "-" else Path(project),
        managed_dir=Path(managed),
        real_mode=True,
    )
    handoff: dict[str, object] = {}
    answers: dict[str, Collected] = {}
    chain = (
        collect_settings.COLLECTOR,
        collect_plugins.COLLECTOR,
        collect_agents.COLLECTOR,
        claude_json.COLLECTOR,
        collect_hooks.COLLECTOR,
        collect_mcp.COLLECTOR,
    )
    for collector in chain:
        got = collector.read(ctx, handoff)
        answers[collector.name] = got
        handoff.update(got.handoff)
        collector.signature(ctx, got)
        collector.signature(ctx, None)
    decoys = {
        "plugins": {
            "hooks": [{"plugin": "x@y", "name": "x", "path": decoy_hooks}],
            "mcp": [{"plugin": "x@y", "name": "x", "path": decoy_mcp}],
        }
    }
    extra_hooks = collect_hooks.COLLECTOR.read(ctx, decoys)
    extra_mcp = collect_mcp.COLLECTOR.read(ctx, decoys)
    counts = {
        "hooks": len(answers["hooks"].items.get("hooks", [])),
        "mcp": len(answers["mcp"].items.get("mcp", [])),
        "decoy_unreadable": len(extra_hooks.unreadable) + len(extra_mcp.unreadable),
    }
    sys.stdout.write(json.dumps(counts) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
