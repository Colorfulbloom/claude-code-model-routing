"""Run the settings collector under the read audit hook, for ``test_settings_audit.py``.

The arguments are the config folder, the home folder, the managed folder and the
project folder (``-`` for an unlisted project). The hook (``read_audit_child.install``)
logs every ``open``, ``os.listdir`` and ``os.scandir`` path to the file named by
``BARTAB_READ_AUDIT_LOG``. The script then reads the project once, asks for the
signature, and prints one JSON line with the item counts.
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
    config, home, managed, project = argv
    # Import everything the collector needs before the hook starts, so the log holds
    # reads of data files and project files only.
    import read_audit_child

    import collect_settings
    from setup_contract import SetupContext

    read_audit_child.install(os.environ[read_audit_child.LOG_ENV])
    ctx = SetupContext(
        project_key="proj",
        config_dir=Path(config),
        home=Path(home),
        project_dir=None if project == "-" else Path(project),
        managed_dir=Path(managed),
        real_mode=True,
    )
    got = collect_settings.COLLECTOR.read(ctx, {})
    collect_settings.COLLECTOR.signature(ctx, got)
    collect_settings.ManagedPricing(Path(config), Path(managed))()
    counts = {part: len(items) for part, items in got.items.items()}
    sys.stdout.write(json.dumps(counts) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
