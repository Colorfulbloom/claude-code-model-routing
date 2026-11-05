### F-e323 hivemind plugin, phase 1: seven commands in the model-routing marketplace
status: shipped
kind: code
dates: 2026-11-03 .. 2026-11-04
refs:
  commit: 61b3faf43a08a05ad4da2eecad47857bec0e67b7 (branch feature/hivemind-plugin, merged into development)
summary: New hivemind plugin 0.1.0 with /hivemind:status, check, link, related, inbox, init and consolidate, a wrapper over its own payload copy of hivemind_lib.py, and read-only summary and preview library actions
decisions:
- The plugin imports its own payload copy of hooks/hivemind_lib.py (owner answer), so no LIB_API or version action; BUILD.json and the drift test keep it in step; status notes when the installed hook library is missing or differs
- routing-dashboard bumped to 0.1.3 because its payload also carries hivemind_lib.py; the build checks routing-dashboard first, so a hivemind-only bump is refused
- /hivemind:inbox calls a new read-only preview action, never prep, because prep pins apply's fold set for 2 hours since #144 (F-2650 follow-up)
- summary always prints and ends with consolidate: nothing to do | work waiting (...) | in progress (...); work is inbox files, NEW records, expired items or topics/*.md over limit except token-tallies.md; an open prep snapshot means in progress and consolidate stops
- Wrapper always exits 0 with error:, warning: and note: lines on stdout (L-bd45), passes an explicit store to every library call (D-168e), sets child-process guards for the VCS, and honors an inherited CLAUDE_PROJECT_DIR when --project is not a directory
- Skills use disallowed-tools Bash(python3 *bin/hivemind*), never a bare Bash (#151); six relay skills on haiku, consolidate on the session model
- consolidate dispatches deep-reasoner through the Agent tool with a brief that names the store, asks for history none and no commit; it stops when the hooks are not installed; the never-run-apply rule is an instruction only, because the deny rule covers only the wrapper
- link warns only when an existing local or origin development ref lacks the commit; init refuses an existing store (owner answer); check's exit 1 with listed problems adds no error line
- Verifier pair on the plan, same brief, independent: Opus 152,520 tokens, Fable 138,416 tokens; neither found a blocker; both caught the files-callable build bug, the history slot in the CONSOLIDATION line and the one-plugin root README
rejected:
- Finding the installed library in the config dir with a LIB_API check (source plan): the owner chose a bundled payload copy
- context: fork with agent deep-reasoner for consolidate: the guard is proven only on the Agent-tool path
- A wider deny rule covering hivemind_lib.py: it would also block deep-reasoner's own consolidation calls in that turn
- Bumping routing-dashboard again to 0.1.4 for a same-branch rebuild: restored the released payload/BUILD.json from development and rebuilt under 0.1.3
files: hooks/hivemind_lib.py, tools/build_plugins.py, .claude-plugin/marketplace.json, plugins/hivemind/bin/hivemind, plugins/hivemind/skills, plugins/hivemind/README.md, plugins/hivemind/.claude-plugin/plugin.json, plugins/routing-dashboard/.claude-plugin/plugin.json, tests/test_hivemind.py, tests/test_plugin_build.py, tests/test_plugin_hivemind.py, tests/test_plugin_hivemind_e2e.py, README.md, docs/model-routing-reference.md
gotchas:
- A change to hooks/hivemind_lib.py needs version bumps in both plugin.json files, then python3 tools/build_plugins.py
- Rebuilding twice on one unmerged branch trips the version guard; restore the released payload/BUILD.json from development, then build
- The worktree guard refuses commands that set HOME and heredocs that mention the VCS, so run the wrapper through tests/test_plugin_hivemind.py and pass drafts as files
follow-ups:
- Owner E2E: MR_E2E=1 /usr/bin/python3 -m unittest discover -s tests -p "test_plugin_hivemind_e2e.py" (add MR_PLUGIN_SOURCE=Colorfulbloom/claude-code-model-routing#feature/hivemind-plugin for the pushed branch)
- Owner: rerun install.sh after merge so the installed hivemind_lib.py matches the plugin copy, or status notes the difference
- Phase 2 (plugin-owned hooks) stays an option
- Harness check whether context: fork with agent deep-reasoner passes the guard
