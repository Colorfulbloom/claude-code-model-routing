# testing-hivemind

### H-1324 History rollup leaves the current quarter alone
fact: hivemind_lib.py history rollup rolls only quarters before the current one, so a quarter with more entries than history_index_max_lines keeps check failing until it ends. This store sets that cap to 60 in config.json.
check: grep -n "if q >= current" hooks/hivemind_lib.py; grep -n "history_index_max_lines" .claude/hivemind/config.json
evidence: hooks/hivemind_lib.py, .claude/hivemind/config.json
fp: 79d5c01d166b
as_of: abaaff3 2026-11-04
author: deep-reasoner
created: 2026-11-04
last_used: 2026-11-04
uses: 0

### H-0fa6 summary's last line and prep's Snapshot line
fact: hivemind_lib.py summary ends with exactly one of "consolidate: nothing to do", "consolidate: work waiting (...)" or "consolidate: in progress (prep snapshot from ...)". Work is inbox files, NEW records, expired items or topics over their limit, token-tallies.md excepted. A prep report written after prep opened a snapshot has a "Snapshot (...)" line that preview lacks, so compare the two without it.
check: /usr/bin/python3 -m unittest discover -s tests -p test_hivemind.py -k SummaryPreview
evidence: hooks/hivemind_lib.py, tests/test_hivemind.py
fp: 583ee765cf12
as_of: abaaff3 2026-11-04
author: verifier
created: 2026-11-04
last_used: 2026-11-04
uses: 0

### H-65be hivemind wrapper: exit 0, explicit store, sealed tests
fact: plugins/hivemind/bin/hivemind always exits 0, prints every message on stdout and calls lib.main in process with an explicit store, so it resolves root and store first. tests/test_plugin_hivemind.py sets GIT_CEILING_DIRECTORIES to its temp base so the no-project case finds no repo above it, and calls install_lib when the summary must be the first line, because the library-differs note prints first.
check: /usr/bin/python3 -m unittest discover -s tests -p test_plugin_hivemind.py
evidence: plugins/hivemind/bin/hivemind, tests/test_plugin_hivemind.py
fp: ea5994c4d82d
as_of: abaaff3 2026-11-04
author: fast-worker
created: 2026-11-04
last_used: 2026-11-04
uses: 0

### H-da08 Tally rows expire by their own active-day window
fact: token-tallies.md is generated from tallies.json, one row per (kind, agent, model, effort) key at about 110 bytes; tally_samples_max caps samples per row, not rows. Only apply removes rows: a row expires when more than tally_expiry_active_days active days follow its last_date (this store sets 14; without the key it follows expiry_active_days, so the key stays out of DEFAULT_CONFIG). Active days are active-days.txt plus git commit dates, not calendar days. An expired row's line goes to archive/token-tallies.md and its raw samples to archive/tallies.json, appended on a repeat expiry.
check: grep -n "def tally_expiry_days\|def archive_tally_samples\|def active_days" hooks/hivemind_lib.py; /usr/bin/python3 -m unittest discover -s tests -p test_hivemind.py -k tally_expiry
evidence: hooks/hivemind_lib.py, .claude/hivemind/config.json, tests/test_hivemind.py
fp: 74da995a45ec
as_of: c7af027 2026-11-06
author: fast-worker
created: 2026-11-06
last_used: 2026-11-06
uses: 0

### H-f1f0 HiveMind skills: only the writers carry a Bash deny
fact: Of plugins/hivemind/skills, only link, init and consolidate set disallowed-tools (HiveMindSkillTest.WRITERS in tests/test_plugin_build.py). The test's stated reason: the deny lasts until the next user message and a slash command counts as one, so check, inbox, related and status must not carry it. Every skill but consolidate pins model haiku.
check: /usr/bin/python3 -m unittest discover -s tests -p test_plugin_build.py -k HiveMindSkill
evidence: tests/test_plugin_build.py, plugins/hivemind/skills/link/SKILL.md
fp: 1a95f2f37ed6
as_of: c7af027 2026-11-06
author: fast-worker
created: 2026-11-06
last_used: 2026-11-06
uses: 0
