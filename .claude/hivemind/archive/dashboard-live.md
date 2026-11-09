# dashboard-live

### V-e534 Live rules go in live.css with an lv- prefix
fact: test_static_shell.py LiveCss covers only live.css (lv- classes, tokens only, motion under no-preference), so a new Live sheet needs its own asserts. A live.css rule on an app class (sb-row, swatch, dy) needs that name in the shared set.
check: /usr/bin/python3 -m unittest discover -s tests -p test_static_shell.py -k every_class_starts_lv
evidence: tests/test_static_shell.py, dashboard/static/live.css, dashboard/static/index.html
fp: de3a178e456d
as_of: abaaff3 2026-11-04
author: deep-reasoner
created: 2026-11-04
last_used: 2026-11-04
uses: 0
retired: 2026-11-09 retired-by-lead
