# testing

### T-6bd7 SubagentHandback appeared only in auto mode on Claude Code 2.1.305
fact: On Claude Code 2.1.305, headless claude -p subagents got SubagentHandback only with --permission-mode auto; under acceptEdits they ended in plain text and SubagentStop carried last_assistant_message. The check shows capture reads both endings.
check: claude --version; grep -n -E "last_assistant_message|transcript_tool_input" hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py
fp: b7b34e576946
as_of: 9c7985a 2026-10-21
author: deep-reasoner
created: 2026-10-20
last_used: 2026-10-20
uses: 0
promote: no
retired: 2026-10-29 retired-by-lead

### T-91ac SessionStart source values on 2.1.306
fact: Headless claude -p on 2.1.306 sends SessionStart source startup (new session), resume (--resume and --continue), compact (/compact) and clear (/clear, new session_id); status shows Recent work only for startup, clear and compact.
check: grep -n "RECENT_SOURCES =" hooks/hivemind_lib.py
evidence: hooks/hivemind_lib.py
fp: b7b34e576946
as_of: 9c7985a 2026-10-21
author: deep-reasoner
created: 2026-10-21
last_used: 2026-10-21
uses: 1
retired: 2026-10-29 retired-by-lead

### T-735d install.py imports agent_md.py from its own folder
fact: The installer's frontmatter helpers live in agent_md.py at the repo root; install.py puts its folder on sys.path, and snapshot_source copies the module.
check: grep -n "agent_md" install.py tests/helpers.py
evidence: install.py, tests/helpers.py
fp: 00b6816b8d22
as_of: 84354c6 2026-10-29
author: deep-reasoner
created: 2026-10-29
last_used: 2026-10-29
uses: 0
retired: 2026-10-30 retired-by-lead
