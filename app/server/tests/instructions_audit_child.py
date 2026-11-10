"""Run the skills and instructions collectors under the read audit hook.

For ``test_instructions_audit.py``. The arguments are the config folder, the home
folder, the managed folder and the project folder (``-`` for an unlisted project), then
a folder outside ``<config>/plugins/`` that one hand-made plugin points at. The hook
(``read_audit_child.install``) logs every ``open``, ``os.listdir`` and ``os.scandir``
path to the file named by ``BARTAB_READ_AUDIT_LOG``. The script reads the project with
both collectors, asks for each signature, and prints one JSON line with the item counts.
A hand-made plugin handoff points one plugin at a folder outside ``<config>/plugins/``.
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
    config, home, managed, project, elsewhere = argv
    # Import everything the collectors need before the hook starts, so the log holds
    # reads of data files and project files only.
    import read_audit_child

    import collect_instructions
    import collect_skills
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
    plugins = {
        "skills": [{"plugin": "evil@market", "name": "evil", "path": elsewhere}],
        "commands": [],
    }
    skills = collect_skills.COLLECTOR.read(ctx, {"plugins": plugins})
    instructions = collect_instructions.COLLECTOR.read(ctx, {})
    collect_skills.COLLECTOR.signature(ctx, skills)
    collect_instructions.COLLECTOR.signature(ctx, instructions)
    counts = {
        part: len(items)
        for got in (skills, instructions)
        for part, items in got.items.items()
    }
    sys.stdout.write(json.dumps(counts) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
