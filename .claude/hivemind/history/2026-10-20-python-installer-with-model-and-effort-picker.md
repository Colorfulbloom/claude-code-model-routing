### F-ee9e Python installer with model and effort picker
status: shipped
kind: code
dates: 2026-10-20 .. 2026-10-20
refs:
  commit: 6e0d51499c41ae7e2d26ec68b1bd211c1f5ade3e (feature/python_installer, merged into development by fast-forward; branch deleted)
summary: install.py replaced the bash install.sh, which is now a short shim that checks for Python 3.9 and runs install.py. A full-screen curses picker sets each of the six agents' model and effort, with defaults read from agents/*.md and choices saved to model-routing-choices.json so a rerun preselects them. Flags --yes, --agent NAME=MODEL[:EFFORT], --reset and --plain; no TTY or CI skips the picker.
decisions:
- Python over bash: the dispatch hook already required python3, so it added no dependency, and the picker and install logic could share code and tests.
- Kept install.sh as a shim so existing instructions and links keep working; the owner plans to remove it later.
- Picker scope is the six agents only; the installer never writes model, effortLevel or env in settings.json (setup-model-routing owns those).
- Rules, agent descriptions, skills, hook message, README and reference doc reworded to name no tier, since tiers became user-chosen; tiers live only in frontmatter. The startup hook prints each agent's model and effort instead.
- Typed full model ids allowed with a strict character check; all five effort levels for every model (max confirmed valid in agent frontmatter by the docs).
rejected:
- dialog and whiptail (not on macOS), gum (extra install), pure bash menus (fragile arrow keys on bash 3.2).
- PyInstaller binary to avoid Python (per-platform builds, size, Gatekeeper on unsigned downloads).
- A bare install command on PATH (collides with /usr/bin/install).
- Filling chosen tier names into the prose with anchors (more moving parts than rewording).
files: README.md, agents/deep-reasoner.md, agents/designer.md, agents/fast-worker.md, agents/judge.md, agents/scout.md, agents/verifier.md, docs/model-routing-reference.md, hooks/check-agent-models.sh, hooks/require-agent-model.py, install.py, install.sh, rules/model-routing.md, skills/route-project/SKILL.md, skills/setup-model-routing/SKILL.md, tests/fixtures/check-agent-models_old.sh, tests/fixtures/install_old.sh, tests/helpers.py, tests/test_features.py, tests/test_hook_roster.py, tests/test_parity.py, tests/test_picker.py
gotchas:
- Parity with the old bash script needed deliberate tests for symlinked destinations, broken links, glob order, whitespace trimming in manifest reads, and byte-identical hook command strings (any change duplicates hook entries on rerun).
- The verifier found manifest lines were trimmed (a trailing space would delete the wrong file), typed ids accepted shell characters, and CI=false counted as CI. All fixed before commit.
- Tests run old and new installers side by side in throwaway HOME and CLAUDE_CONFIG_DIR folders; never against the real config.
follow-ups:
- Remove install.sh (owner's plan): update README, two shim tests, and the missing-Python message.
- Linux untested; terminal-too-small screen untested.
