### F-ce69 Phase 1 data path: shared helpers, field lines, collectors, masking, resolver on collectors (#32-#36)
status: shipped
kind: code
dates: 2026-10-29 .. 2026-10-29
refs:
  commit: a54765ae4eeaecf0ac9fcdf9fb71cb6e1bb237ca (branch feature/phase1-data-path, merged into development)
summary: Issues #32 to #36 (epic #16). Installer frontmatter helpers moved to agent_md.py; the strict reader returns field lines; dashboard/collect.py reads settings, env, agents and rules files with path, line and masking; resolve() works only on collected data, carries lines, shows ~/ paths and display names, and adds settingsFile rows; harness raw_settings plus two records (invalid settings JSON, empty CLAUDE_CODE_EFFORT_LEVEL). Facts T-735d, T-6b2f; refreshed T-7629, D-1534.
decisions:
- agent_md.py sits at the repo root beside install.py, because the installer runs from the repo and the hooks keep their own code; the strict reader stays in dashboard/agent_frontmatter.py.
- The dashboard calls only agent_md.list_files_sorted; find_agent_md_files keeps find order and lists .md only, while the dashboard needs every file in a stable order.
- MissingFieldsError carries the label; install.py main() prints MSG_ERR_AGENT_FRONTMATTER so the message stays in install.py.
- A fixture gets its own managed folder at <fixture>/managed/ and its own shell from session.json; live use takes both as arguments from the server (#37).
- Collector where maps use tuple paths, because modelSettings names can hold dots.
- Unknown settings files mark winners Unknown by the row's order (rules a, b) and through env blocks only when the env.<VAR> row itself is unknown (rule c, fixed after the verifier).
- A broken user, project or local settings file is Ignored (harness record, owner confirmed); a broken managed file is Unknown (docs say Claude Code refuses to start); an unreadable managed file is Unknown per the October 29 record; unreadable user, project or local is Unknown with confidence assumed.
- An empty CLAUDE_CODE_EFFORT_LEVEL is ignored (record z1 to z6); only the literal unset sends no level, so _match_value no longer maps "" to "unset".
- Display names and six new reason texts are placeholders until #38 is approved.
rejected:
- Moving the strict reader into the shared module, because it is a strict YAML subset with its own field list and #33 edits it in place.
- Putting the module under dashboard/, because the installer would then depend on the dashboard folder.
- Marking every env-layer winner for any unknown file, because it contradicts env-block-order when a higher block set the variable.
files: agent_md.py, install.py, tests/helpers.py, tests/test_agent_md.py, dashboard/agent_frontmatter.py, tests/test_agent_frontmatter.py, dashboard/collect.py, tests/test_collect.py, dashboard/resolve.py, tests/test_resolve.py, tests/fixtures/resolution/, dashboard/rules.json, dashboard/rules_schema.py, tests/test_rules_schema.py, docs/rules-reference.md, dashboard/experiments/harness/runcase.py, dashboard/experiments/harness/README.md, tests/test_harness_guard.py, dashboard/experiments/2026-10-29-settings-invalid-json.json, dashboard/experiments/2026-10-29-effort-env-empty.json
gotchas:
- The raw_settings guard refuses any text holding "agent" (a forbidden key), so test texts avoid words like subagent.
- An unreadable user file always leaves default-layer winners Unknown under rule b.
- Fixture cli_settings is masked in load_fixture; the collector never sees --settings content.
follow-ups:
- Owner runs python3 dashboard/agent_frontmatter.py read over his own agent folders (#33 owner check).
- #38 replaces the display names and the placeholder reasons.
- Promotion candidate: project-facts T-7629 to 1152 tests in about 165 s.
