#!/usr/bin/env python3
"""Round 3 of #39: usage-first information design in direction A's look. Revised October 30 for the 30 review findings.
Data: usage-stats.json (from usage_stats.py over usage-set/) and the round-1 resolver output.
Copy: deck strings via gen.S, round-2 strings via gen2.N, round-3 strings in strings-r3.json (tech-writer drafts).
"""
import json, os, sys, html, math, re, datetime as dt, collections
HERE = os.path.dirname(os.path.abspath(__file__)); R3 = os.path.dirname(HERE)
SCRATCH = os.path.dirname(R3)
sys.path.insert(0, os.path.join(SCRATCH, "directions", "tools")); sys.path.insert(0, os.path.join(SCRATCH, "directions-r2", "tools"))
import gen, gen2
# Round-3 demo set: the Tidewater fixture gained per-model caps (effort mix fix, October 30). The resolver was rerun on
# directions-r3/demo-set by tools/resolve_demo.py; round 1 and 2 keep their own copy under directions/demo-set.
_DS = os.path.join(R3, "demo-set")
if os.path.isdir(_DS):
    gen.RESOLVED = json.load(open(os.path.join(_DS, "_resolved.json")))
    gen.RULES = json.load(open(os.path.join(_DS, "rules-used.json")))
    gen2.ALL = json.load(open(os.path.join(_DS, "_resolved_all.json")))
esc = gen.esc; S = gen.S; N = gen2.N; STATUS = gen.STATUS
U = json.load(open(os.path.join(R3, "usage-stats.json")))
T = json.load(open(os.path.join(HERE, "strings-r3.json")))
DISPLAY = dict(gen.DISPLAY); DISPLAY.update(U["display"])
PRICE = U["price_table"]
CAT = {"claude-opus-5-5": "cat-1", "claude-sonnet-5-5": "cat-2", "claude-haiku-5-5": "cat-3", "claude-fable-5-1": "cat-4"}
KINDS = [("cache_read", T["k_cache_read"], "rk-1"), ("input", T["k_input"], "rk-2"), ("cache_write", T["k_cache_write"], "rk-3"), ("output", T["k_output"], "rk-4")]
RANGE_WORD = {"today": T["r_today"], "7d": T["r_7d"], "30d": T["r_30d"]}
PROJECT_NAME = {k: v["name"] for k, v in gen.PROJECTS.items()}; PROJECT_NAME["all"] = T["all_projects"]
STATUS_PLAIN = {"overridden": T["p_overridden"], "ignored": T["p_ignored"], "invalid": T["p_invalid"], "lowered": T["p_lowered"], "unknown": T["p_unknown"]}
SETTING_NAME = {"env": "CLAUDE_CODE_EFFORT_LEVEL", "project": "effortLevel", "user": "effortLevel", "local": "effortLevel", "managed": "effortLevel"}

# ------------------------------------------------------------------ formatting
def fmt_tokens(n):
    if n is None: return "0"
    if n >= 1e9: return "%.1fB" % (n / 1e9)
    if n >= 1e6: return "%.1fM" % (n / 1e6)
    if n >= 1e4: return "%dK" % round(n / 1e3)
    return "{:,}".format(int(n))
def fmt_cost(c, unpriced=0):
    if c is None or (c == 0 and unpriced): return T["not_priced"]
    return "$%s" % ("{:,.2f}".format(c))
def pct(x): return "%d%%" % round(100 * x) if x is not None else "0%"
def shares(values):
    """Largest-remainder rounding so shares sum to 100; '<1%' for a share under 0.5 that is not zero."""
    tot = sum(values) or 1
    raw = [100.0 * v / tot for v in values]; base = [int(math.floor(r)) for r in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - base[i], reverse=True)[:100 - sum(base)]: base[i] += 1
    return [("<1%" if 0 < r < 0.5 else "%d%%" % b) for r, b in zip(raw, base)]
def fmt_time(iso): d = dt.datetime.fromisoformat(iso); return d.strftime("%B %-d, %-I:%M %p")
def fmt_day(iso): return dt.date.fromisoformat(iso[:10]).strftime("%b %-d")
def model_name(m): return DISPLAY.get(m, m)
def vs_word(rng): return T["vs_yesterday"] if rng == "today" else T["vs_previous"].format(range=RANGE_WORD[rng].lower())
def delta_html(cur, prev, rng, points=False):
    """Relative percent, or percentage points for a rate. Zero is neutral, no arrow."""
    if prev is None or (not points and not prev): return '<span class="delta delta-none">%s</span>' % esc(T["no_previous"])
    if points:
        ch = (cur - prev) * 100; n = "%.1f" % abs(ch)
        if n == "0.0": return '<span class="delta delta-none">%s</span>' % esc(T["delta_none"])
        tmpl = T["delta_point"] if n == "1.0" else T["delta_points"]
        txt = tmpl.format(sign="+" if ch > 0 else "−", n=n, vs=vs_word(rng))
        num, rest = txt.split(" ", 1)
    else:
        ch = (cur - prev) / prev * 100
        if round(ch) == 0: return '<span class="delta delta-none">%s</span>' % esc(T["delta_none"])
        num = "%s%d%%" % ("+" if ch > 0 else "−", abs(round(ch))); rest = vs_word(rng)
    return '<span class="delta%s"><span class="delta-n">%s</span> %s</span>' % (" delta-down" if ch < 0 else "", esc(num), esc(rest))
def view(project, rng): return U["views"]["%s/%s" % (project, rng)]
def est_line(): return '<p class="est">%s</p>' % esc(T["est_short"])
def nice_ticks(mx, integer=False):
    """Top tick rounded up to a nice step; 3 or 4 steps, whichever wastes less. Returns (step, n_steps)."""
    if mx <= 0: return (1, 3)
    best = None
    for n in (3, 4):
        raw = mx / n; k = 10 ** math.floor(math.log10(raw)) if raw >= 1 else 1
        for m in (1, 2, 2.5, 4, 5, 10):
            step = m * k
            if integer: step = max(1, int(math.ceil(step)))
            if step * n >= mx:
                top = step * n
                if best is None or top < best[2] or (top == best[2] and n < best[1]): best = (step, n, top)
                break
    return best[0], best[1]

# ------------------------------------------------------------------ shell
def nav3(active, project):
    group1 = T["all_projects"] if project == "all" else N["nav_group_project"]
    groups = [(group1, [("overview", T["nav_overview"], "overview"), ("agents", T["nav_agents"], "agents"), ("models", T["nav_models"], "cpu"),
                        ("sessions", T["nav_sessions"], "session"), ("settings", T["nav_settings"], "sliders"), ("attention", T["nav_attention"], "issues")]),
              (N["nav_group_reference"], [("files", N["nav_files"], "files"), ("rules", N["nav_rules"], "rules")])]
    out = ['<nav class="sb-nav" aria-label="%s">' % esc(N["nav_label"])]
    for g, items in groups:
        out.append('<p class="sb-g">%s</p><ul>' % esc(g))
        for k, lbl, ic in items:
            a = k == active
            out.append('<li><a href="#%s" class="nv%s"%s>%s<span>%s</span></a></li>' % (k, " is-active" if a else "", ' aria-current="page"' if a else "", icon(ic), esc(lbl)))
        out.append('</ul>')
    out.append('</nav>'); return "".join(out)

def icon(name, cls="ic"):
    extra = {"cpu": '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
             "sliders": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
             "coins": '<circle cx="12" cy="12" r="9"/><path d="M12 6.5v11M14.6 9.3c-.3-1-1.3-1.6-2.6-1.6-1.5 0-2.6.8-2.6 1.9 0 2.6 5.3 1.3 5.3 4 0 1.1-1.1 1.9-2.7 1.9-1.4 0-2.4-.7-2.7-1.7"/>',
             "bars": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
             "cache": '<path d="M4 7a8 3 0 0 1 16 0v10a8 3 0 0 1-16 0z"/><path d="M4 12a8 3 0 0 0 16 0"/>',
             "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
             "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
             "pin": '<path d="M12 17v5M8 3h8l-1 6 3 3H6l3-3z"/>'}
    if name in extra:
        return ('<svg class="%s" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%s</svg>' % (cls, extra[name]))
    return _gen2_icon(name, cls)
_gen2_icon = gen2.icon
gen2.icon = icon  # cards built by gen2 can use the round-3 icons

def version_chip(state="several"):
    """Long and short text; CSS shows the short one under 720px. The accessible name stays the long one."""
    if state == "unreadable":
        return '<span class="vchip vchip-unk" aria-label="%s">%s<span class="vc-long">%s</span><span class="vc-short" aria-hidden="true">%s</span></span>' % (
            esc(N["chip_unknown"]), icon("version", "ic sm"), esc(N["chip_unknown"]), esc(T["chip_unknown_short"]))
    return '<span class="vchip">%s%s</span>' % (icon("version", "ic sm"), esc(N["chip_version"].format(version=gen.INSTALLED)))

def switcher3(current):
    opts = []
    for key, p in gen.PROJECTS.items():
        label = S["opt_missing"].format(name=p["name"]) if p.get("missing") else p["name"]
        opts.append('<option value="%s"%s>%s</option>' % (key, " selected" if key == current else "", esc(label)))
    opts.append('<option value="all"%s>%s</option>' % (" selected" if current == "all" else "", esc(T["all_projects"])))
    return '<div class="sw"><label for="project">%s</label><select id="project" name="project">%s</select></div>' % (esc(S["project_lbl"]), "".join(opts))

def range_control(active):
    return '<div class="segs segs-range" role="radiogroup" aria-label="%s">%s</div>' % (esc(T["range_label"]), "".join(
        '<button type="button" role="radio" aria-checked="%s" class="seg%s">%s</button>' % ("true" if k == active else "false", " is-active" if k == active else "", esc(RANGE_WORD[k])) for k in ("today", "7d", "30d")))

FLAG = re.compile(r'(?<![\w-])(--[a-z][a-z-]+)')
def shell(active, project, content, theme, banner_state="several"):
    content = FLAG.sub(r'<span class="nw">\1</span>', content)  # keep CLI flags such as --effort on one line
    side = '<aside class="sb"><div class="sb-brand">%s<span>%s</span></div>%s</aside>' % (icon("ring", "ic brand"), esc(S["h1"]), nav3(active, project))
    top = ('<header class="topbar"><button type="button" class="btn btn-icon menu" aria-label="%s">%s</button><div class="tb-title">%s</div>'
           '<div class="tb-right">%s%s</div></header>' % (esc(N["menu"]), icon("menu"), esc(S["h1"]), switcher3(project), version_chip(banner_state)))
    tab = S["tab_title"].format(project=PROJECT_NAME[project])
    css = "".join(open(p).read() for p in (os.path.join(SCRATCH, "directions", "tools", "base.css"), os.path.join(SCRATCH, "directions-r2", "tools", "base2.css"),
                                            os.path.join(SCRATCH, "directions-r2", "tools", "dir-a.css"), os.path.join(HERE, "base3.css")))
    script = ('addEventListener("load",function(){var d=document.documentElement;var h=Math.ceil(d.scrollHeight);var ox=d.scrollWidth>d.clientWidth?1:0;'
              'd.setAttribute("data-h",h);d.setAttribute("data-ox",ox);if(parent!==window){parent.postMessage({h:h,ox:ox},"*")}});')
    return ('<!doctype html><html lang="en" data-theme="%s"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>%s</title>'
            '<style>%s</style><style>%s</style></head><body><div class="app">%s<div class="main">%s<main class="content">%s</main></div></div><script>%s</script></body></html>'
            % (theme, esc(tab), open(gen.TOKENS).read(), css, side, top, content, script))

def page_head(title, intro=None, right="", crumbs=None):
    c = ('<p class="crumbs">%s</p>' % " ".join('<a href="#">%s</a> <span aria-hidden="true">/</span>' % esc(x) for x in crumbs)) if crumbs else ""
    return '<div class="ph">%s<div class="ph-row"><div><h1>%s</h1>%s</div>%s</div></div>' % (c, esc(title), ('<p class="intro">%s</p>' % esc(intro)) if intro else "", right)

def footer_line(): return '<p class="foot">%s</p>' % esc(T["footer"].format(config_dir=gen.CONFIG_DIR))

# ------------------------------------------------------------------ chart components
def kpi(label, value, sub, delta="", ic=None, cls=""):
    return ('<div class="kpi %s"><div class="kpi-top"><span class="tl-l">%s</span>%s</div><div class="kpi-v">%s</div>%s%s</div>'
            % (cls, esc(label), ('<span class="kpi-ic">%s</span>' % icon(ic, "ic sm")) if ic else "", esc(value), ('<div class="kpi-sub">%s</div>' % sub) if sub else "", delta))

def kpis(v, rng, with_runs=True, deltas=True):
    t, p = v["totals"], v["previous"]
    cost_sub = est_line()
    if t["unpriced_requests"]: cost_sub = '<p class="est">%s</p>' % esc(T["partly_priced"].format(n=t["unpriced_requests"]))
    d = (lambda *a, **k: delta_html(*a, **k)) if deltas else (lambda *a, **k: "")
    cards = [kpi(T["kpi_tokens"], fmt_tokens(t["tokens"]), "", d(t["tokens"], p["tokens"], rng), "bars"),
             kpi(T["kpi_cost"], fmt_cost(t["cost"], t["unpriced_requests"]), cost_sub, d(t["cost"], p["cost"], rng) if t["cost"] else "", "coins"),
             kpi(T["kpi_hit"], pct(t["hit_rate"]), '<span class="kpi-def">%s</span>' % esc(T["hit_def"]), d(t["hit_rate"] or 0, p["hit_rate"], rng, points=True), "cache")]
    if with_runs: cards.append(kpi(T["kpi_runs"], "{:,}".format(t["runs"]), "", d(t["runs"], p["runs"], rng), "agents"))
    return '<div class="kpis">%s</div>' % "".join(cards)

def hatch_defs(pid):
    return '<defs><pattern id="%s" patternUnits="userSpaceOnUse" width="5" height="5" patternTransform="rotate(45)"><rect width="5" height="5" class="pt-bg"/><rect width="2" height="5" class="pt-fg"/></pattern></defs>' % pid

def ring3(segments, centre, word, kind="r"):
    """segments: [(label, value, cls)]. Unlisted models get the hatched 'other' class. Centre text sized to the hole (14 units)."""
    total = sum(v for _l, v, _c in segments) or 1
    r, w, C, gap = 46, 13, 2 * math.pi * 46, 2.0
    out = ['<svg class="ring" viewBox="0 0 120 120" width="160" height="160" role="img" aria-label="%s %s">' % (esc(centre), esc(word)), hatch_defs("oth-" + kind)]
    out.append('<circle cx="60" cy="60" r="%d" class="ring-track" stroke-width="%d"/>' % (r, w))
    start = 0.0
    for lbl, val, cls in segments:
        if val <= 0: continue
        length = C * val / total; dash = max(length - gap, 0.6)
        fill = ' stroke="url(#oth-%s)"' % kind if cls == "cat-other" else ""
        out.append('<circle cx="60" cy="60" r="%d" class="rseg %s" stroke-width="%d" stroke-dasharray="%.2f %.2f" stroke-dashoffset="%.2f"%s><title>%s</title></circle>' % (r, cls, w, dash, C - dash, -start, fill, esc(lbl)))
        start += length
    out.append('<text x="60" y="58" class="ring-n" text-anchor="middle">%s</text><text x="60" y="73" class="ring-w" text-anchor="middle">%s</text></svg>' % (esc(centre), esc(word)))
    return "".join(out)

def legend_rows(rows, cols):
    th = "".join('<th>%s</th>' % esc(c) for c in cols)
    body = "".join('<tr><th scope="row"%s><span class="swatch %s" aria-hidden="true"></span>%s</th>%s</tr>' % (' class="wrap"' if sw == "cat-other" else "", sw, lbl, "".join('<td>%s</td>' % c for c in cells)) for sw, lbl, cells in rows)
    return '<table class="lg"><thead class="sr"><tr><th>%s</th>%s</tr></thead><tbody>%s</tbody></table>' % (esc(T["lg_name"]), th, body)

def cost_by_model_card(v, cls=""):
    items = sorted(v["by_model"].items(), key=lambda kv: -(kv[1]["cost"] or 0))
    total = sum(a["cost"] for _m, a in items)
    centre_total = v["totals"]["cost"] if abs(v["totals"]["cost"] - total) < 0.05 else total
    segs = [(model_name(m), a["cost"], CAT.get(m, "cat-other")) for m, a in items]
    sh = shares([a["cost"] for _m, a in items])
    rows = [(CAT.get(m, "cat-other"), esc(model_name(m)), [esc(fmt_cost(a["cost"], a["unpriced_requests"])), ('<span class="share">%s</span>' % s) if m in CAT else ""]) for (m, a), s in zip(items, sh)]
    body = '<div class="ring-row">%s%s</div>%s' % (ring3(segs, fmt_cost(centre_total), T["est_word"], "cost"), legend_rows(rows, [T["kpi_cost"], N["lg_share"]]), est_line())
    return gen2.card(T["c_cost_model"], body, "coins", sub=T["q_cost_model"], cls=cls)

def stacked_tokens(rows):
    mx = max((a["tokens"] for _l, a, _s in rows), default=1) or 1
    out = ['<div class="sbars">']
    for lbl, a, sub in rows:
        segs = "".join('<span class="sb-seg %s" style="width:%.2f%%"><span class="sr">%s %s</span></span>' % (cls, 100.0 * a[k] / mx, esc(name), esc(fmt_tokens(a[k]))) for k, name, cls in KINDS if a[k] > 0)
        out.append('<div class="sb-row"><div class="sb-l"><span class="sb-n">%s</span>%s</div><div class="sb-bar">%s</div><div class="sb-v">%s</div></div>' % (
            esc(lbl), ('<span class="sb-s">%s</span>' % sub) if sub else "", segs, esc(fmt_tokens(a["tokens"]))))
    out.append('</div>')
    return "".join(out)

def kinds_legend(a):
    """Always with totals (one anatomy on every page)."""
    return '<ul class="klg">%s</ul>' % "".join('<li><span class="swatch %s" aria-hidden="true"></span>%s <span class="muted">%s</span></li>' % (cls, esc(name), esc(fmt_tokens(a[k]))) for k, name, cls in KINDS)

def kind_costs(a, model):
    """Estimated cost per token kind at the model's list prices; None when the model has no price."""
    p = PRICE.get(model)
    if p is None: return None
    if model == "claude-haiku-5-5" and (a["input"] + a["cache_read"] + a["cache_write"]) > 100000 * a["requests"]: p = PRICE.get("claude-haiku-5-5:over100k", p)
    return {"cache_read": a["cache_read"] * p[3] / 1e6, "input": a["input"] * p[0] / 1e6, "cache_write": (a["cache_write_5m"] * p[1] + a["cache_write_1h"] * p[2]) / 1e6, "output": a["output"] * p[4] / 1e6}

def kinds_table(a, model):
    kc = kind_costs(a, model)
    rows = []
    for k, name, cls in KINDS:
        rows.append(['<span class="cw"><span class="swatch %s" aria-hidden="true"></span>%s</span>' % (cls, esc(name)), esc(fmt_tokens(a[k])), esc(fmt_cost(kc[k]) if kc else T["not_priced"])])
    return table3([T["k_kind"], T["kpi_tokens"], T["kpi_cost"]], rows, cls="dt-kinds")

def agents_sorted(by_agent):
    """One agent order everywhere: estimated cost, highest first."""
    return sorted(by_agent.items(), key=lambda kv: -(kv[1]["cost"] or 0))

def tokens_by_agent_card(v, cls=""):
    items = agents_sorted(v["by_agent"])
    rows = [(a["display"], a, '%s · %s' % (esc(model_name(a["ran_at"][0]["model"])), esc(a["ran_at"][0]["effort"] or ""))) for _k, a in items]
    return gen2.card(T["c_tokens_agent"], stacked_tokens(rows) + kinds_legend(v["totals"]), "agents", sub=T["q_where"], cls=cls)

def hbars(rows):
    """rows: [(label, value, text)] single series on the track."""
    mx = max((val for _l, val, _t in rows), default=1) or 1
    return '<div class="hbars">%s</div>' % "".join('<div class="hb-row"><span class="hb-l">%s</span><div class="hb-bar"><span style="width:%.2f%%"></span></div><span class="hb-v">%s</span></div>' % (
        esc(l), 100.0 * (val or 0) / mx, esc(t)) for l, val, t in rows)

def cost_by_agent_card(v, cls=""):
    items = agents_sorted(v["by_agent"])
    return gen2.card(T["c_cost_agent"], hbars([(a["display"], a["cost"] or 0, fmt_cost(a["cost"], a["unpriced_requests"])) for _k, a in items]) + est_line(), "coins", sub=T["q_agents"], cls=cls)

def mini_ring(p, label, sub=None):
    r, C = 26, 2 * math.pi * 26
    dash = C * (p or 0)
    return ('<div class="mini"><svg viewBox="0 0 64 64" width="72" height="72" role="img" aria-label="%s %s"><circle cx="32" cy="32" r="%d" class="ring-track" stroke-width="7"/>'
            '<circle cx="32" cy="32" r="%d" class="rseg mini-arc" stroke-width="7" stroke-dasharray="%.2f %.2f"/><text x="32" y="36" text-anchor="middle" class="mini-n">%s</text></svg>'
            '<span class="mini-l">%s</span>%s</div>' % (esc(label), esc(pct(p)), r, r, dash, C - dash, esc(pct(p)), esc(label), ('<span class="mini-s">%s</span>' % esc(sub)) if sub else ""))

def cache_card(v, cls=""):
    items = agents_sorted(v["by_agent"])
    body = '<div class="minis">%s</div><p class="ring-sum">%s</p>' % ("".join(mini_ring(a["hit_rate"], a["display"], fmt_tokens(a["cache_read"]) + " " + T["k_cache_read"].lower()) for _k, a in items), esc(T["hit_def"]))
    return gen2.card(T["c_cache_agent"], body, "cache", sub=T["q_cache"], cls=cls)

def daybars(per_day, dates, runs=False, height=150):
    """Columns per day. Bars in an SVG that stretches to the card; axis labels in HTML so they never scale.
    per_day: list of dicts with by_model, or list of ints when runs."""
    n = len(per_day); W = 600; H = height
    vals = [sum(d["by_model"].values()) for d in per_day] if not runs else list(per_day)
    mx = max(vals) if vals and max(vals) > 0 else 1
    step, nsteps = nice_ticks(mx, integer=runs); top = step * nsteps
    bw = W / n; gap = min(3, bw * 0.25)
    fmt = (lambda v: str(int(round(v)))) if runs else fmt_tokens
    ylab = "".join('<span>%s</span>' % esc(fmt(step * i)) for i in range(nsteps, 0, -1)) + '<span>0</span>'
    out = ['<div class="dchart"><div class="dy" aria-hidden="true">%s</div>' % ylab]
    out.append('<svg class="dbars" viewBox="0 0 %d %d" preserveAspectRatio="none" role="img" aria-label="%s">%s' % (W, H, esc(T["c_per_day"] if not runs else T["c_runs_time"]), hatch_defs("oth-day")))
    for i in range(1, nsteps + 1):
        y = H - H * i / nsteps
        out.append('<line x1="0" y1="%.1f" x2="%d" y2="%.1f" class="grid"/>' % (y, W, y))
    out.append('<line x1="0" y1="%d" x2="%d" y2="%d" class="base"/>' % (H, W, H))
    for i, d in enumerate(per_day):
        x = i * bw + gap / 2; w = bw - gap; y = H
        if runs:
            h = H * d / top
            if h > 0: out.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" class="col cat-acc"/>' % (x, y - h, w, h))
            continue
        for m in list(CAT) + [k for k in d["by_model"] if k not in CAT]:
            val = d["by_model"].get(m, 0)
            if val <= 0: continue
            h = H * val / top
            fill = ' fill="url(#oth-day)"' if m not in CAT else ""
            out.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" class="col %s"%s><title>%s %s %s</title></rect>' % (x, y - h, w, max(h - 1, 0.5), CAT.get(m, "cat-other"), fill, esc(fmt_day(d["date"])), esc(model_name(m)), esc(fmt_tokens(val))))
            y -= h
    out.append('</svg>')
    stepx = 7 if n > 10 else 1
    xl = "".join('<span style="left:%.2f%%">%s</span>' % (100.0 * (i + 0.5) / n, esc(fmt_day(dates[i]))) for i in range(0, n, stepx))
    out.append('<div class="dx" aria-hidden="true">%s</div></div>' % xl)
    return "".join(out)

def per_day_card(v, cls=""):
    models = [m for m in CAT if any(d["by_model"].get(m) for d in v["per_day"])]
    other = any(any(m not in CAT for m in d["by_model"]) for d in v["per_day"])
    leg = "".join('<li><span class="swatch %s" aria-hidden="true"></span>%s</li>' % (CAT[m], esc(model_name(m))) for m in models)
    if other: leg += '<li><span class="swatch cat-other" aria-hidden="true"></span>%s</li>' % esc(T["other_models"])
    body = daybars(v["per_day"], [d["date"] for d in v["per_day"]]) + '<ul class="klg">%s</ul>' % leg
    return gen2.card(T["c_per_day"], body, "calendar", sub=T["q_time"], cls=cls)

def effort_card(v, cls=""):
    items = sorted(v["by_effort"].items(), key=lambda kv: -kv[1]["tokens"])
    return gen2.card(T["c_effort"], hbars([(k, a["tokens"], fmt_tokens(a["tokens"])) for k, a in items]), "sliders", sub=T["q_effort"], cls=cls)

def table3(cols, rows, cls=""):
    th = "".join('<th scope="col">%s</th>' % esc(c) for c in cols)
    trs = "".join('<tr>%s</tr>' % "".join('<td data-l="%s">%s</td>' % (esc(c), cell) for c, cell in zip(cols, r)) for r in rows)
    return '<table class="dt %s"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (cls, th, trs)

def inline(count, words): return '<span class="cw">%s <span class="muted">%s</span></span>' % (count, esc(words))

# ------------------------------------------------------------------ pin check
def pin_info(project, agent, ran):
    """Owner decision (#9): "Pinned to" is the agent file's pin. The effective value comes from the resolver's winner.
    Returns dict: pinned (text), state (match|overridden|differs|unknown), sentence, note."""
    rows = gen2.ALL.get(project, [])
    if agent == "main":
        m = next((e for e in rows if e["key"] == "model" and e["scope"] == "main" and e["status"] in ("in_effect", "lowered", "default")), None)
        ef = next((e for e in rows if e["key"] == "effortLevel" and e["scope"] == "main" and e["status"] in ("in_effect", "lowered", "default", "unknown")), None)
        if m is None or ef is None: return {"pinned": T["pin_unknown"], "state": "unknown", "sentence": "", "note": ""}
        pin_model, pin_effort = m["value"], ef["value"] or STATUS["unknown"]
        effective = ef.get("becomes") or ef["value"]
        state = "match" if (ran["model"] == pin_model and ran["effort"] == effective) else "differs"
        sentence = gen.render_reason(project, ef["reason"]) if ef["status"] == "lowered" else ""
        return {"pinned": "%s, %s" % (model_name(pin_model), pin_effort), "state": state, "sentence": sentence, "note": T["pin_main_note"]}
    m = next((e for e in rows if e["key"] == "model" and e.get("agent") == agent and e["layer"] == "agent"), None)
    pf = next((e for e in rows if e["key"] == "effort" and e.get("agent") == agent and e["layer"] == "agent"), None)
    eff = next((e for e in rows if e["key"] == "effort" and e.get("agent") == agent and e["status"] in ("in_effect", "lowered")), None)
    if m is None or pf is None: return {"pinned": T["pin_unknown"], "state": "unknown", "sentence": "", "note": ""}
    pin_model, pin_effort = m["value"], pf["value"]
    effective = (eff.get("becomes") or eff["value"]) if eff else pin_effort
    if ran["model"] != pin_model:
        return {"pinned": "%s, %s" % (model_name(pin_model), pin_effort), "state": "differs", "note": "",
                "sentence": T["pin_model_differs_sentence"].format(ran_model=model_name(ran["model"]), pin_model=model_name(pin_model))}
    if ran["effort"] == pin_effort: return {"pinned": "%s, %s" % (model_name(pin_model), pin_effort), "state": "match", "sentence": "", "note": ""}
    if eff is not None and ran["effort"] == effective:
        if eff["status"] == "lowered": sentence = gen.render_reason(project, eff["reason"])
        else: sentence = T["pin_override_sentence"].format(setting=SETTING_NAME.get(eff["layer"], eff["key"]), file=gen.source_short(project, eff).split(", line")[0], effort=effective)
        return {"pinned": "%s, %s" % (model_name(pin_model), pin_effort), "state": "overridden", "sentence": sentence, "note": ""}
    return {"pinned": "%s, %s" % (model_name(pin_model), pin_effort), "state": "differs", "sentence": "", "note": ""}

def pin_pill(state):
    if state == "unknown": return gen.chip("unknown")
    cls, word = {"match": ("st-match", T["matches_pin"]), "overridden": ("st-overridden", T["pin_overridden"]), "differs": ("st-differs", T["differs_pin"])}[state]
    return '<span class="st %s"><i class="mk" aria-hidden="true"></i>%s</span>' % (cls, esc(word))

# ------------------------------------------------------------------ pages
def attention_rows(project, items, full=False):
    li = []
    for e in items:
        v = ('<span class="at-v">%s</span>' % esc(gen2.value_on_screen(e))) if gen2.value_on_screen(e) else ""
        if full:
            li.append('<li><a href="#trail"><span class="at-n">%s</span><span class="at-m">%s%s</span><span class="at-s">%s</span><span class="at-go">%s%s</span></a></li>' % (
                esc(gen2.row_name(e)), v, gen.chip(e["status"]), esc(gen.source_short(project, e)), esc(T["open_trail"]), icon("arrow", "ic sm")))
        else:
            li.append('<li><a href="#trail"><span class="at-n">%s</span><span class="at-m">%s%s</span><span class="at-p">%s</span></a></li>' % (esc(gen2.row_name(e)), v, gen.chip(e["status"]), esc(STATUS_PLAIN[e["status"]])))
    return "".join(li)

def overview(project, rng):
    v = view(project, rng)
    head = page_head(T["nav_overview"], T["intro_usage"].format(project=PROJECT_NAME[project], range=RANGE_WORD[rng].lower()), range_control(rng))
    att = gen2.attention(project)
    att_card = gen2.card(T["nav_attention"], '<ul class="at at-plain">%s</ul><p class="at-more"><a href="#attention">%s</a></p>' % (attention_rows(project, att[:3]), esc(T["see_all_attention"].format(n=len(att)))), "issues", sub=T["intro_attention"].split(".")[0])
    body = kpis(v, rng) + '<div class="g21">%s%s</div><div class="g2 g2-fill">%s<div class="stack">%s%s</div></div>%s' % (
        per_day_card(v), cost_by_model_card(v), tokens_by_agent_card(v), cache_card(v), effort_card(v), att_card) + footer_line()
    return head + body

def agents_page(project, rng):
    v = view(project, rng)
    head = page_head(T["nav_agents"], T["intro_agents"], range_control(rng))
    rows = []
    for k, a in agents_sorted(v["by_agent"]):
        ran = a["ran_at"][0]; pi = pin_info(project, k, ran)
        runs_cell = "{:,}".format(a["runs"]) if k != "main" else inline(a["sessions"], T["h_sessions"].lower())
        rows.append(['<a class="lnk" href="#agent-%s">%s</a>' % (esc(k), esc(a["display"])), runs_cell, esc(fmt_tokens(a["tokens"])), esc(fmt_cost(a["cost"], a["unpriced_requests"])),
                     esc(pct(a["hit_rate"])), esc("%s, %s" % (model_name(ran["model"]), ran["effort"] or "")), esc(pi["pinned"]) + (('<span class="cell-note">%s</span>' % esc(pi["note"])) if pi["note"] else ""), pin_pill(pi["state"])])
    cols = [T["h_agent"], T["h_runs"], T["kpi_tokens"], T["kpi_cost"], T["kpi_hit"], T["h_ran_at"], T["h_pinned"], T["h_pin_check"]]
    body = '<div class="g2">%s%s</div>' % (cost_by_agent_card(v), cache_card(v)) + gen2.card(T["c_agents_table"], table3(cols, rows) + est_line(), "agents") + footer_line()
    return head + body

def agent_detail(project, rng, agent):
    v = view(project, rng); a = v["by_agent"][agent]; ran = a["ran_at"][0]
    pi = pin_info(project, agent, ran)
    head = page_head(a["display"], None, range_control(rng), crumbs=[T["nav_agents"]])
    txt = T["pinned_to"].format(model=pi["pinned"].split(", ")[0], effort=pi["pinned"].split(", ")[-1]) + " " + T["ran_at_fmt"].format(model=model_name(ran["model"]), effort=ran["effort"] or "")
    sentence = ('<p class="en-rs">%s</p>' % esc(pi["sentence"])) if pi["sentence"] else ""
    pin_card = gen2.card(T["c_pin_check"], '<div class="pin"><div class="pin-top">%s<p>%s</p></div>%s<p class="pin-link"><a href="#settings">%s</a></p></div>' % (
        pin_pill(pi["state"]), esc(txt), sentence, esc(T["open_trail"])), "pin")
    tiles_html = '<div class="kpis">%s%s%s%s</div>' % (
        kpi(T["kpi_runs"], "{:,}".format(a["runs"]), "", "", "agents"), kpi(T["kpi_tokens"], fmt_tokens(a["tokens"]), "", "", "bars"),
        kpi(T["kpi_cost"], fmt_cost(a["cost"], a["unpriced_requests"]), est_line(), "", "coins"), kpi(T["kpi_hit"], pct(a["hit_rate"]), '<span class="kpi-def">%s</span>' % esc(T["hit_def"]), "", "cache"))
    dates = [d["date"] for d in v["per_day"]]
    runs_card = gen2.card(T["c_runs_time"], daybars(a["per_day_runs"], dates, runs=True, height=150) + '<p class="ring-sum">%s</p>' % esc(T["runs_axis"]), "calendar", sub=T["q_runs_time"])
    kinds_card = gen2.card(T["c_tokens_cost"], stacked_tokens([(a["display"], a, None)]) + kinds_table(a, ran["model"]) + '<p class="ring-sum">%s</p>' % esc(T["thinking_note"].format(n=fmt_tokens(a["thinking"]))) + est_line(), "bars", sub=T["q_tokens_kind"])
    cols = [T["h_started"], T["h_parent"], N["f_model"], N["f_effort"], T["kpi_tokens"], T["kpi_cost"]]
    rows = [[esc(fmt_time(r["started"])), '<a class="lnk" href="#session">%s</a>' % esc(T["session_from"].format(time=fmt_time(r["session_started"]))), esc(model_name(r["model"])), esc(r["effort"] or ""), esc(fmt_tokens(r["tokens"])), esc(fmt_cost(r["cost"]))] for r in a["recent_runs"][:6]]
    recent = gen2.card(T["c_recent_runs"], table3(cols, rows) + est_line(), "list")
    return head + '<div class="g21 g21-pin">%s%s</div>' % (tiles_html, pin_card) + '<div class="g2">%s%s</div>' % (runs_card, kinds_card) + recent + footer_line()

def models_page(project, rng):
    v = view(project, rng)
    head = page_head(T["nav_models"], T["intro_models"], range_control(rng))
    items = sorted(v["by_model"].items(), key=lambda kv: -(kv[1]["cost"] or 0))
    used_by = collections.defaultdict(list)
    for k, a in v["by_agent"].items():
        for r in a["ran_at"]: used_by[r["model"]].append(a["display"])
    rows = [['<span class="cw"><span class="swatch %s" aria-hidden="true"></span>%s</span> <span class="muted mono">%s</span>' % (CAT.get(m, "cat-other"), esc(model_name(m)), esc(m)), "{:,}".format(a["requests"]), esc(fmt_tokens(a["tokens"])),
             esc(fmt_cost(a["cost"], a["unpriced_requests"])), esc(pct(a["hit_rate"])), esc(", ".join(sorted(set(used_by[m]))))] for m, a in items]
    cols = [N["f_model"], T["h_requests"], T["kpi_tokens"], T["kpi_cost"], T["kpi_hit"], T["h_used_by"]]
    stacked = gen2.card(T["c_tokens_model"], stacked_tokens([(model_name(m), a, None) for m, a in items]) + kinds_legend(v["totals"]), "bars", sub=T["q_where"])
    note = ('<p class="est">%s</p>' % esc(T["not_priced_note"].format(model="claude-opus-6-preview"))) if any(a["unpriced_requests"] for _m, a in items) else ""
    return head + '<div class="g2">%s%s</div>' % (cost_by_model_card(v), stacked) + gen2.card(T["c_models_table"], table3(cols, rows) + est_line() + note, "cpu") + footer_line()

def sessions_page(project, rng):
    v = view(project, rng)
    head = page_head(T["nav_sessions"], T["intro_sessions"], range_control(rng))
    rows = []
    for s in v["sessions"][:10]:
        rows.append([esc(fmt_time(s["started"])), '<a class="lnk" href="#session">%s</a>' % esc(T["session_from"].format(time=fmt_time(s["started"]))), '<span class="mono">%s</span>' % esc(s["branch"] or ""),
                     inline(s["runs"], ", ".join(s["agents"])) if s["agents"] else '<span class="muted">%s</span>' % esc(T["none_spawned"]), esc(fmt_tokens(s["tokens"])), esc(fmt_cost(s["cost"], s["unpriced_requests"]))])
    cols = [T["h_started"], T["h_session"], T["h_branch"], T["h_agents_spawned"], T["kpi_tokens"], T["kpi_cost"]]
    more = '<p class="at-more">%s</p>' % esc(T["more_sessions"].format(n=len(v["sessions"]) - 10)) if len(v["sessions"]) > 10 else ""
    return head + gen2.card(T["c_sessions_table"], table3(cols, rows) + more + est_line(), "session") + footer_line()

def session_detail(project, rng):
    v = view(project, rng); s = v["sessions"][0]
    title = T["session_from"].format(time=fmt_time(s["started"]))
    head = page_head(title, T["intro_session"].format(branch=s["branch"], project=PROJECT_NAME[project]), "", crumbs=[T["nav_sessions"]])
    tiles_html = '<div class="kpis">%s%s%s%s</div>' % (
        kpi(T["kpi_tokens"], fmt_tokens(s["tokens"]), "", "", "bars"), kpi(T["kpi_cost"], fmt_cost(s["cost"], s["unpriced_requests"]), est_line(), "", "coins"),
        kpi(T["kpi_hit"], pct(s["hit_rate"]), '<span class="kpi-def">%s</span>' % esc(T["hit_def"]), "", "cache"), kpi(T["kpi_runs"], "{:,}".format(s["runs"]), "", "", "agents"))
    for k, a in s["by_agent"].items(): a["display"] = "Main session" if k == "main" else k
    by = agents_sorted(s["by_agent"])
    rows = [['<a class="lnk" href="#agent-%s">%s</a>' % (esc(k), esc(a["display"])), "{:,}".format(a["runs"]) if k != "main" else "1", esc(fmt_tokens(a["tokens"])), esc(fmt_cost(a["cost"], a["unpriced_requests"])), esc(pct(a["hit_rate"]))] for k, a in by]
    cols = [T["h_agent"], T["h_runs"], T["kpi_tokens"], T["kpi_cost"], T["kpi_hit"]]
    agents_card = gen2.card(T["c_agents_in_session"], table3(cols, rows) + est_line(), "agents", sub=T["q_agents_session"])
    stacked = gen2.card(T["c_tokens_by_agent_session"], stacked_tokens([(a["display"], a, None) for k, a in by]) + kinds_legend(s), "bars", sub=T["q_where"])
    return head + tiles_html + '<div class="g2">%s%s</div>' % (agents_card, stacked) + footer_line()

def settings_page(project):
    head = page_head(T["nav_settings"], T["intro_settings"])
    sm = gen2.summaries(project)
    others = gen.effort_entries(project)[1:] + gen.broken_files(project)  # the winner is not an "other value" (#11)
    lost = sum(1 for e in others if e["status"] in gen2.ATTENTION)
    sm["values"] = gen2.plural(len(others), "value") + (", %d didn't count" % lost if lost else "")
    trail = ('<div id="trail" class="trail-a"><h2 class="tr-title">%s</h2>%s%s%s%s%s</div>' % (
        esc(S["trail_h"]), gen2.meta_block(project),
        gen2.card(N["sec_winner"], '<div class="win">%s</div>' % gen.entry(project, gen.effort_entries(project)[0], "big"), "flag", summary=sm["winner"], open_=True, h="h3"),
        gen2.card(N["sec_values_other"], gen2.values_block(project, "a"), "list", summary=sm["values"], open_=True, h="h3"),
        gen2.card(S["rules_h"], gen2.rules_block(project), "rules", summary=sm["rules"], open_=False, h="h3"),
        gen2.card(N["sec_files"], gen2.files_block(project), "sources", summary=sm["files"], open_=False, h="h3")))
    return head + gen2.tiles(project) + trail

def attention_page(project):
    items = gen2.attention(project)
    head = page_head(T["nav_attention"], T["intro_attention"])
    groups = collections.OrderedDict()
    for e in items: groups.setdefault(e["status"], []).append(e)
    return head + "".join(gen2.card(STATUS[st], '<ul class="at at-full">%s</ul>' % attention_rows(project, es, full=True), None, sub=STATUS_PLAIN[st]) for st, es in groups.items())

def files_page():
    head = page_head(N["nav_files"], T["intro_files"])
    files = [("~/.claude/agents/reviewer.md", "match"), ("~/.claude/agents/scribe.md", "differs"), ("~/.claude/rules/model-routing.md", "match"), ("~/.claude/rules/writing-voice.md", "match"), ("~/.claude/agents/tech-writer.md", "missing")]
    word = {"match": T["f_matches"], "differs": T["f_differs"], "missing": T["f_missing"]}
    rows = [['<span class="mono">%s</span>' % esc(p), '<span class="st st-%s"><i class="mk" aria-hidden="true"></i>%s</span>' % (k, esc(word[k])), esc(T["f_action_" + k])] for p, k in files]
    return head + gen2.card(T["c_files_table"], table3([T["h_file"], T["h_state"], T["h_next"]], rows), "files") + '<p class="foot">%s</p>' % esc(T["files_foot"])

# P-3 strings. Drafts by the designer until tech-writer's words land in strings-r3.json (same keys).
P3 = {"rules_search_placeholder": "Search rule id or reason", "rules_search_label": "Search rules by id or reason",
      "rules_match_count": "{n} of {m} rules shown", "rules_no_match": "No rule matches \u201c{q}\u201d. Clear the search to see all {m} rules.",
      "rules_clear_search": "Clear search", "rules_sub": "Which rules does the dashboard apply, and what backs each one?"}
def P3S(k): return T.get(k, P3[k])
SEARCH_ICON = ('<svg class="ic" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.75" '
               'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg>')

def rules_card(query="", shown=None):
    """The Rules card. Header: title, count subtitle, then search and the confidence filter side by side (P-3 placement).
    shown=None renders the full list; shown=[] renders the no-match state for the states board."""
    counts = collections.Counter(r["confidence"] for r in gen.RULES.values()); m = len(gen.RULES)
    sub = P3S("rules_sub") if shown is None else P3S("rules_match_count").format(n=len(shown), m=m)
    search = ('<div class="search">%s<input type="search" value="%s" placeholder="%s" aria-label="%s" autocomplete="off" spellcheck="false"></div>'
              % (SEARCH_ICON, esc(query), esc(P3S("rules_search_placeholder")), esc(P3S("rules_search_label"))))
    filt = '<div class="segs segs-range" role="radiogroup" aria-label="%s">%s</div>' % (esc(T["rules_filter_label"]), "".join(
        '<button type="button" role="radio" aria-checked="%s" class="seg%s">%s <span class="muted">%s</span></button>' % ("true" if k == "all" else "false", " is-active" if k == "all" else "", esc(lbl), n)
        for k, lbl, n in (("all", T["rules_all"], m), ("tested", gen.CONF["tested"], counts["tested"]), ("documented", gen.CONF["documented"], counts["documented"]), ("assumed", gen.CONF["assumed"], counts["assumed"]))))
    actions = '<div class="cd-act rules-act">%s%s</div>' % (search, filt)
    if shown is None:
        body = '<ul class="rules">%s</ul>' % "".join(gen2.rule_item(rid) for rid in sorted(gen.RULES))
    elif shown:
        body = '<ul class="rules">%s</ul>' % "".join(gen2.rule_item(rid) for rid in shown)
    else:
        body = '<div class="es" role="status"><p class="es-h">%s</p><button type="button" class="btn">%s</button></div>' % (
            esc(P3S("rules_no_match").format(q=query, m=m)), esc(P3S("rules_clear_search")))
    return gen2.card(T["c_rules_list"], body, "rules", sub=sub, actions=actions, cls="cd-rules")

def rules_page():
    head = page_head(N["nav_rules"], T["intro_rules"])
    return head + rules_card()

def all_projects(rng):
    v = view("all", rng)
    head = page_head(T["all_projects"], T["intro_all"].format(range=RANGE_WORD[rng].lower()), range_control(rng))
    items = sorted(v["by_project"].items(), key=lambda kv: -kv[1]["tokens"])
    rows, notes = [], []
    for k, a in items:
        cost = esc(fmt_cost(a["cost"], a["unpriced_requests"]))
        if a["unpriced_requests"]:
            cost = '<span class="cw">%s<sup class="fn" aria-hidden="true">*</sup></span>' % cost
            notes.append((T["partly_priced_row_1"] if a["unpriced_requests"] == 1 else T["partly_priced_row"]).format(project=PROJECT_NAME[k], n=a["unpriced_requests"]))
        rows.append(['<a class="lnk" href="#%s">%s</a>' % (esc(k), esc(PROJECT_NAME[k])), "{:,}".format(a["sessions"]), "{:,}".format(a["runs"]), esc(fmt_tokens(a["tokens"])), cost, esc(pct(a["hit_rate"]))])
    cols = [T["h_project"], T["h_sessions"], T["kpi_runs"], T["kpi_tokens"], T["kpi_cost"], T["kpi_hit"]]
    note_html = "".join('<p class="est">%s %s</p>' % ('<span aria-hidden="true">*</span>', esc(n)) for n in notes)
    stacked = gen2.card(T["c_tokens_project"], stacked_tokens([(PROJECT_NAME[k], a, None) for k, a in items]) + kinds_legend(v["totals"]), "bars", sub=T["q_where"])
    return head + kpis(v, rng) + '<div class="g21">%s%s</div>' % (per_day_card(v), cost_by_model_card(v)) + '<div class="g2">%s%s</div>' % (stacked, gen2.card(T["c_projects_table"], table3(cols, rows) + note_html + est_line(), "overview")) + footer_line()

def states_page():
    """Each state labelled with its own demo project (#15). Saltmarsh is a fourth demo project with a .claude folder and no transcripts."""
    head = page_head(N["nav_overview"], None)
    d = view("driftwood", "today")
    blocks = [
        ("%s · Saltmarsh" % T["s_no_usage_h"], gen2.card(T["s_no_usage_h"], '<p class="es-t">%s</p>' % esc(T["s_no_usage_t"]), "bars")),
        ("%s · Harbor Light, %s" % (T["s_no_range_h"], T["r_today"]), gen2.card(T["c_per_day"], '<div class="es"><p class="es-h">%s</p><p class="es-t">%s</p>%s</div>' % (esc(T["s_no_range_h"]), esc(T["s_no_range_t"]), range_control("today")), "calendar", sub=T["q_time"])),
        ("%s · Lantern" % S["es_missing_h"], '<section class="cd cd-row">%s</section>' % gen.empty_state("missing", "lantern")),
        ("%s · Driftwood, %s" % (T["not_priced"], T["r_today"]), kpis(d, "today", with_runs=False)),
        ("%s · Tidewater" % P3S("rules_clear_search"), rules_card(query="cache ttl", shown=[])),
        ("%s · %s" % (N["chip_unknown"], T["all_projects"]), version_chip("unreadable")),
    ]
    return head + '<section class="board">%s</section>' % "".join('<div class="bd"><p class="bd-l">%s</p>%s</div>' % (esc(l), c) for l, c in blocks)

THEME = "light"
SCREENS = [
    ("01-overview", lambda: shell("overview", "tidewater", overview("tidewater", "30d"), THEME)),
    ("02-agents", lambda: shell("agents", "tidewater", agents_page("tidewater", "30d"), THEME)),
    ("03-agent-detail", lambda: shell("agents", "tidewater", agent_detail("tidewater", "30d", "builder"), THEME)),
    ("04-models", lambda: shell("models", "tidewater", models_page("tidewater", "30d"), THEME)),
    ("05-sessions", lambda: shell("sessions", "tidewater", sessions_page("tidewater", "7d"), THEME)),
    ("06-session-detail", lambda: shell("sessions", "tidewater", session_detail("tidewater", "7d"), THEME)),
    ("07-settings", lambda: shell("settings", "tidewater", settings_page("tidewater"), THEME)),
    ("08-needs-attention", lambda: shell("attention", "tidewater", attention_page("tidewater"), THEME)),
    ("09-installed-files", lambda: shell("files", "tidewater", files_page(), THEME)),
    ("10-rules-reference", lambda: shell("rules", "tidewater", rules_page(), THEME)),
    ("11-all-projects", lambda: shell("overview", "all", all_projects("30d"), THEME)),
    ("12-empty-and-states", lambda: shell("overview", "driftwood", states_page(), THEME, banner_state="unreadable")),
]

def main():
    global THEME
    folder = os.path.join(R3, "a-usage"); os.makedirs(folder, exist_ok=True)
    only = sys.argv[1:]
    for name, fn in SCREENS:
        if only and not any(name.startswith(o) for o in only): continue
        for THEME in ("light", "dark"):
            open(os.path.join(folder, "%s-%s.html" % (name, THEME)), "w").write(fn())
    print("ok")

if __name__ == "__main__":
    main()
