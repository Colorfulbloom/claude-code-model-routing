---
name: consolidate
description: Have deep-reasoner fold the waiting facts into this project's HiveMind store
disable-model-invocation: true
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/bin/hivemind" *)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/hivemind" --project "${CLAUDE_PROJECT_DIR}" consolidate $ARGUMENTS`

The HiveMind summary is above. Follow these rules in order.

1. If any line starts with "error:" or with "note: the HiveMind hooks aren't installed", relay it and stop. deep-reasoner needs the installed library to consolidate.
2. Find the line that starts with "consolidate:". If it says "nothing to do", tell the user nothing waits and stop. If it says "in progress", tell the user another consolidation holds an open prep snapshot in this store, so they should wait for it or let it expire (2 hours), and stop.
3. If it says "work waiting", state the dispatch plan in one line: deep-reasoner, Kind hivemind-consolidation, the reasons from that line, and the expected cost if the user's routing rules give one. If the user's own rules require a yes before this dispatch, ask and wait. Otherwise dispatch now.
4. If no deep-reasoner agent is available, say it comes with the model routing installer (./install.sh) and stop.
5. Dispatch the `deep-reasoner` agent through the Agent tool (subagent_type deep-reasoner, no model override), with this brief. Fill in <store> from the "HiveMind summary for <store>" line.

   Kind: hivemind-consolidation
   Run CONSOLIDATION only, with no feature work, on the store <store>. Pass that store path to every hivemind_lib.py call (prep <store>, apply <store>, check <store>). Steps: prep, decide each proposal by editing topics/*.md, apply, then check until it passes. Read every proposed check: command before accepting it. Never accept secrets or owner decisions. List facts worth promoting to .claude/rules/project-facts.md and leave them for the owner. This is a manual consolidation, so write no history entry and put `history none` in the CONSOLIDATION line. Leave every change uncommitted. End with the CONSOLIDATION line.

6. Relay deep-reasoner's summary and its CONSOLIDATION line.

Never run prep, apply, check or any HiveMind command yourself, and never edit the store. The plugin's guard hook blocks only this plugin's wrapper, so this rule is the guard.
