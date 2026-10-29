### F-af78 Routing Dashboard rules schema, bug template, Design section
status: shipped
kind: code
dates: 2026-10-29 .. 2026-10-29
refs:
  commit: 1d0786c4c91a96b8ce14a42661c4b41d7804150d (branch feature/routing-dashboard, merged into development)
  url: https://github.com/Colorfulbloom/claude-code-model-routing/issues/4
summary: dashboard/rules.json plus a stdlib schema check and 53 tests (#4), a bug issue template (#2), and a project CLAUDE.md Design section with a starter token sheet (#3).
decisions:
- The schema is a Python module (dashboard/rules_schema.py), not a JSON Schema file, because the owner chose standard library only and stdlib has no JSON Schema validator.
- Data names are snake_case ids (in_effect, documented); STATUS_WORDS and CONFIDENCE_WORDS in the module map each to its screen word, as #4's notes ask.
- One reason per rule, so one rule per distinct outcome; conditions are first-match, narrow ones first.
- Documented and Tested rules need a source; Assumed rules are exempt (owner decision, October 29, overriding a literal reading of #4). Documented needs doc_url and quote; Tested needs an experiment record at a relative path inside dashboard/ (dashboard/experiments/ by convention, not enforced).
- Seeded one Documented rule (effortLevel in User settings ignored on Opus 5.5) with the verbatim settings-reference quote, so the real-file test checks a real entry.
- Bug template copied from the owner-approved draft in #2; the one later change, "Begin with how you started", is the owner's.
- Build-after-the-pick line routes the build as a separate feature for the main session's lead, because designer.md never dispatches a lead.
rejected:
- Status map as data inside rules.json, because the seven words are fixed by the owner and belong to code.
- rules.json under rules/, because install.py copies rules/*.md into ~/.claude.
- A scout diff review, to stay inside the 250K budget. The lead read the code, tests and rules.json in full but only the header and motion lines of tokens.css; a verifier reviewed it afterwards.
files: dashboard/rules.json, dashboard/rules_schema.py, dashboard/experiments/.gitkeep, dashboard/static/tokens.css, tests/test_rules_schema.py, .github/ISSUE_TEMPLATE/bug.md, CLAUDE.md
gotchas:
- Lowered conditions require becomes; non-string confidence or status values give error lines, not TypeError (verifier findings, fixed).
- unittest collects any TestCase method whose name starts with "test", helpers named tested() included.
- The seed rule's layer_order is the general settings order, not yet checked per key; P0-5 settles it.
facts: T-7629
follow-ups:
- Subagent usage.output_tokens values of 3 to 16 were seen on assistant rows in this session's transcripts, so context_final_plus_out may undercount output in tallies; not yet traced to a cause.
- The #2 default-branch and New-issue criteria are checkable only after merge to main.
