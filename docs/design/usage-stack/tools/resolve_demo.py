#!/usr/bin/env python3
"""Run the repo's real resolver (read-only) over demo-set/<project> (beside tools/) and write
_resolved.json (main scope, as round 1), _resolved_all.json (every row, as round 2) and rules-used.json
(the rule records the three projects cite, same six fields as round 1). Nothing in the repo is touched."""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.join(os.path.dirname(HERE), "demo-set")
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))  # tools/ -> usage-stack/ -> design/ -> docs/ -> repo root
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "dashboard"))
os.chdir(REPO)
from dashboard import resolve
rules = resolve.load_rules(); fields = resolve.load_agent_fields()
rule_by_id = {r["rule_id"]: r for r in rules["rules"]}
main_out, all_out, used = {}, {}, set()
for name in ("tidewater", "driftwood", "harbor-light"):
    inputs, _ = resolve.load_fixture(os.path.join(BASE, name), rules)
    entries = resolve.resolve(inputs, rules, fields)
    all_out[name] = entries
    main_out[name] = [e for e in entries if e.get("scope") == "main"]
    for e in main_out[name]:  # main scope only, as round 1 did (12 rules), so the Rules reference page keeps its list
        for rid in e.get("rule_ids") or []: used.add(rid)
json.dump(main_out, open(os.path.join(BASE, "_resolved.json"), "w"), indent=1)
json.dump(all_out, open(os.path.join(BASE, "_resolved_all.json"), "w"), indent=1)
KEEP = ("rule_id", "confidence", "verified_on", "reason", "quotes", "experiment")
json.dump({rid: {k: rule_by_id[rid].get(k) for k in KEEP} for rid in sorted(used)}, open(os.path.join(BASE, "rules-used.json"), "w"), indent=1)
for e in all_out["tidewater"]:
    if e["key"] in ("effort", "effortLevel", "maxEffortLevel", "modelSettings.maxEffortLevel"):
        print({k: e.get(k) for k in ("key", "scope", "agent", "layer", "value", "status", "becomes", "file")}); print("   ", e.get("reason"))
print("rules used", len(used), sorted(used))
