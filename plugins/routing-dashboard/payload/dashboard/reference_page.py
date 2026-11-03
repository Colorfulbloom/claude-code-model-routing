"""Generate docs/rules-reference.md from dashboard/rules.json. Standard library only.

    /usr/bin/python3 dashboard/reference_page.py          write docs/rules-reference.md
    /usr/bin/python3 dashboard/reference_page.py --check  write nothing; exit 1 if the page is missing or stale

The handwritten part lives in dashboard/reference_copy.md. Its one marker line,
<!-- rules -->, is replaced by the generated part. The only file this module
writes is docs/rules-reference.md.
"""
import json
import re
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RULES_PATH = os.path.join(HERE, "rules.json")
COPY_PATH = os.path.join(HERE, "reference_copy.md")
PAGE_PATH = os.path.join(REPO, "docs", "rules-reference.md")
MARKER = "<!-- rules -->"
COMMAND = "/usr/bin/python3 dashboard/reference_page.py"

# Every fixed label on the page, in one place so the copy can be reviewed.
LABELS = {
    "generated": "This page is generated from dashboard/rules.json and dashboard/reference_copy.md. Do not edit it by hand. Regenerate it with `" + COMMAND + "`.",
    "rules_heading": "Rules",
    "summary_heading": "Summary",
    "col_rule_id": "Rule",
    "col_key": "Key",
    "col_scope": "Scope",
    "col_confidence": "Confidence",
    "col_version": "Claude Code version checked",
    "key": "Key",
    "scope": "Scope",
    "combine": "Combine",
    "layer_order": "Layer order (highest first)",
    "reason": "Reason",
    "quotes": "Quotes",
    "experiment": "Experiment record",
    "confidence": "Confidence",
    "verified_on": "Verified on",
    "none": "none",
    "version": "Claude Code",
}


def _cell(text):
    """Escape a value for a table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def _quote_block(text):
    return "\n".join("> " + line if line else ">" for line in str(text).split("\n"))


def _confidence_word(rule):
    # Imported here so the module also works when rules_schema is not on the path.
    sys.path.insert(0, HERE)
    try:
        import rules_schema
    finally:
        sys.path.remove(HERE)
    c = rule.get("confidence")
    return rules_schema.CONFIDENCE_WORDS.get(c, str(c))


MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


def month_first(date):
    """Turn "2026-10-29" into "October 29, 2026". Anything else comes back as is."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", date) if isinstance(date, str) else None
    if not m or not 1 <= int(m.group(2)) <= 12:
        return date
    return "%s %d, %s" % (MONTHS[int(m.group(2)) - 1], int(m.group(3)), m.group(1))


def _verified(rule):
    v = rule.get("verified_on") or {}
    return v.get("claude_version", ""), month_first(v.get("date", ""))


def _summary(rules):
    L = LABELS
    lines = ["### " + L["summary_heading"], "",
             "| %s | %s | %s | %s | %s |" % (L["col_rule_id"], L["col_key"], L["col_scope"],
                                             L["col_confidence"], L["col_version"]),
             "| --- | --- | --- | --- | --- |"]
    for r in rules:
        lines.append("| %s | %s | %s | %s | %s |" % (
            _cell(r.get("rule_id", "")), _cell(r.get("key", "")), _cell(r.get("scope", "")),
            _cell(_confidence_word(r)), _cell(_verified(r)[0])))
    return "\n".join(lines)


def _section(rule):
    L = LABELS
    ver, date = _verified(rule)
    out = ["### " + str(rule.get("rule_id", "")), "",
           "- %s: %s" % (L["key"], rule.get("key", "")),
           "- %s: %s" % (L["scope"], rule.get("scope", "")),
           "- %s: %s" % (L["combine"], rule.get("combine", L["none"])),
           "- %s: %s" % (L["layer_order"], ", ".join(rule.get("layer_order") or []) or L["none"]),
           "", L["reason"] + ":", "",
           _quote_block(rule.get("reason", "")), "", L["quotes"] + ":", ""]
    quotes = rule.get("quotes") or []
    if quotes:
        for q in quotes:
            out.append("- [%s](%s)" % (q.get("doc_url", ""), q.get("doc_url", "")))
            out.append("")
            out.append(_quote_block(q.get("quote", "")))
            out.append("")
    else:
        out += [L["none"], ""]
    exp = rule.get("experiment")
    if exp:
        link = "../dashboard/" + exp
        exp_text = "[%s](%s)" % (link, link)
    else:
        exp_text = L["none"]
    out += ["- %s: %s" % (L["experiment"], exp_text),
            "- %s: %s" % (L["confidence"], _confidence_word(rule)),
            "- %s: %s %s, %s" % (L["verified_on"], L["version"], ver, date)]
    return "\n".join(out)


def generated_part(rules_data):
    rules = rules_data.get("rules", [])
    parts = ["## " + LABELS["rules_heading"], "", _summary(rules)]
    parts += [_section(r) for r in rules]
    return "\n\n".join(parts)


def render(rules_data, copy_text):
    """Return the page: the copy with the marker line replaced by the generated part."""
    if copy_text.count(MARKER) != 1:
        raise ValueError("the copy must hold the marker %s exactly once" % MARKER)
    body = copy_text.replace(MARKER, generated_part(rules_data))
    page = "> " + LABELS["generated"] + "\n\n" + body
    return page if page.endswith("\n") else page + "\n"


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def build():
    return render(json.loads(_read(RULES_PATH)), _read(COPY_PATH))


def main(argv):
    page = build()
    if "--check" in argv:
        try:
            current = _read(PAGE_PATH)
        except FileNotFoundError:
            print("docs/rules-reference.md is missing. Run %s" % COMMAND)
            return 1
        if current != page:
            print("docs/rules-reference.md is out of date. Run %s" % COMMAND)
            return 1
        return 0
    with open(PAGE_PATH, "w", encoding="utf-8") as f:
        f.write(page)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
