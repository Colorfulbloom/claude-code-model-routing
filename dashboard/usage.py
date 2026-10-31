"""Usage views for the dashboard page. Standard library only, pure.

build_views turns transcript records into the numbers the usage page shows,
for three ranges (today, 7d, 30d). It takes everything as arguments. It reads
no clock, no environment and no file, and it never calls realpath. A listed
project's folder is worked out outside, by transcripts.project_folders.

    build_views(records, scope, now, tz, prices, catalog, oldest_seen,
                projects=(), reader_notes=None, tz_fixed=False, pin_fn=None)
        -> {"today": View, "7d": View, "30d": View}

    dedupe(records) -> (records, no_id_rows)

records are transcripts.Record rows. scope is a project key or "all". now is an
aware datetime. tz is a tzinfo (a zoneinfo zone in the server). prices and
catalog are the prices.json document and the rules.json models list.
oldest_seen is a dict {folder name: aware datetime}, the oldest moment the
reader could see in each folder (its oldest record or its oldest skipped old
file), from ReadResult.oldest_by_folder. A folder with nothing seen has no key.
The effective oldest moment is the smallest value over the scope's folders (all
values for "all"). A project with no folder, or no key, has none, so its
previous is None. projects is a list of {"key", "name", "folder"}, where
folder is a transcript folder name or None. reader_notes is the reader's notes
dict (malformed_lines, synthetic_rows, no_id_rows, skipped_old_files).

pin_fn is None or a callable (agent_key, ran_with, runs) -> dict or None. It
fills AgentAgg.pin. agent_key is the agent name, "@unnamed" or "@main". runs
lists every in-range run of that agent as {run_id, model, effort, requests}.
For the Main session a run is one session, and run_id holds the session id.
It is called for a single project scope only, never for "all".

All numbers are raw. Nothing is rounded here, so the KPI, the ring and every
table use the same sums. The page formats them.

Choices the ticket left open:
  - Main session: agent None, route_key "@main". A subagent with no agent type
    is "@unnamed". Main means run_id is None. Agg.runs counts subagent runs only,
    so the Main row has runs 0 and the page shows its sessions.
  - A run is (session_id, run_id). For Main a run is one session. A run's model
    and effort are its most-used pair by request, ties to the first seen in
    time. Model is the catalog id, else the raw name ("unknown" when missing).
  - Bucket runs_by_agent is keyed by route_key. Main counts sessions there.
  - by_effort uses the effort string as written. A request with no effort is the
    row whose effort is None (the page says "Not recorded").
  - ModelAgg for a model that is not in the catalog has cost None.
  - Shares are of estimated cost. They are all 0 when no cost is priced.
  - by_project lists folders with at least one in-range request, sorted like agents.
  - Session branch is the branch on the session's first main row.

Shapes (the ticket's View shape, plus the additions named here):

    View = {range, start, end, previous_start, previous_end, totals, previous,
            deltas, by_model, by_effort, by_agent, bucket_unit, buckets, axis,
            sessions, by_project, notes}
    deltas = {tokens_pct, cost_pct, runs_pct, hit_rate_pts}  (additive key)
      The relative ones are None when previous is None or the baseline is 0. A zero
      change is 0. Hit rate is in percentage points and is None when previous is
      None or either hit rate is None. A previous hit rate of 0.0 gives a number.
    Agg = {tokens, input, output, cache_read, cache_write, cache_write_5m,
           cache_write_1h, thinking, cost, cost_by_kind, unpriced_requests,
           unpriced_tokens, hit_rate, requests, runs, sessions}
    ModelAgg = Agg + {model, display_name, cat, share_pct, share_lt1, agents}
    AgentAgg = Agg + {agent, route_key, display, ran_with, pin, recent_runs,
                      runs_per_day, runs_ticks}
      runs_ticks are integer ticks from 0 for this agent's runs_per_day alone
      (axis.runs_ticks is scaled for the whole view)
    ProjectAgg = Agg + {key, name, listed, folder}
    SessionAgg = Agg + {session_id, project, branch, started, agents, by_agent}
"""
import bisect
import collections
import datetime
import os
import re
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import prices as price_list  # noqa: E402
import resolve  # noqa: E402

# "every_folder" counts every transcript folder in All projects. "listed" counts
# only folders that belong to a listed project.
ALL_PROJECTS_SCOPE = "every_folder"
# Thinking tokens sit inside output_tokens and are priced as output. The page
# shows them in one "Includes n thinking tokens" line. No number here changes.
THINKING_IN_OUTPUT = True

ALL = "all"
MAIN_KEY = "@main"
UNNAMED_KEY = "@unnamed"
MAIN_DISPLAY = "Main session"
UNNAMED_DISPLAY = "Unnamed agent"
UNKNOWN_MODEL = "unknown"
UNKNOWN_MODEL_DISPLAY = "Unknown model"

# Chart colour slot per catalog model (the page's cat-1 to cat-4). Others are "other".
CAT_SLOTS = {
    "claude-opus-5-5": 1,
    "claude-sonnet-5-5": 2,
    "claude-haiku-5-5": 3,
    "claude-fable-5-1": 4,
}
EFFORT_LEVELS = ("low", "medium", "high", "xhigh")
EFFORT_MAX = "max"
RANGES = (("today", 1), ("7d", 7), ("30d", 30))
RECENT_RUNS = 8

_UTC = datetime.timezone.utc
_MIDNIGHT = datetime.time(0)
_ONE_HOUR = datetime.timedelta(hours=1)
_PATH_SPLIT = re.compile(r"[\\/]")


# ---------------------------------------------------------------- dedupe

def dedupe(records):
    """Keep one record per message id. Returns (records, no_id_rows).

    A record with no message id falls back to its request id. Among records that
    share an id, the largest output wins. A tie goes to the later timestamp,
    then to the later position in the list (a later file). A record with neither
    id is kept and counted. The winner takes the place of the id's first record,
    so the rest of the input order is kept.
    """
    out = []
    slot = {}
    no_id = 0
    for rec in records:
        if rec.message_id:
            key = (0, rec.message_id)
        elif rec.request_id:
            key = (1, rec.request_id)
        else:
            out.append(rec)
            no_id += 1
            continue
        at = slot.get(key)
        if at is None:
            slot[key] = len(out)
            out.append(rec)
        else:
            old = out[at]
            if (rec.output, rec.ts_utc) >= (old.output, old.ts_utc):
                out[at] = rec
    return out, no_id


# ---------------------------------------------------------------- windows

def _aware(value):
    return value if value.tzinfo is not None else value.replace(tzinfo=_UTC)


def _wall(tz, day, clock):
    """The local moment for a date and a wall clock time, as an aware datetime in tz.

    Built from the fields, so a clock change between two days does not move the
    hours. A time that does not exist (spring forward) lands just after the gap.
    """
    naive = datetime.datetime.combine(day, clock)
    return naive.replace(tzinfo=tz).astimezone(_UTC).astimezone(tz)


def _window(tz, now_local, days):
    """(start, previous_start, previous_end) for a range of `days` local days."""
    today = now_local.date()
    one = datetime.timedelta
    start = _wall(tz, today - one(days=days - 1), _MIDNIGHT)
    prev_start = _wall(tz, today - one(days=2 * days - 1), _MIDNIGHT)
    prev_end = _wall(tz, today - one(days=days), now_local.time())
    return start, prev_start, prev_end


# ---------------------------------------------------------------- axis

def nice_max(value):
    """Round value up to 1, 2, 2.5 or 5 times a power of 10 (at least 1)."""
    value = int(-(-value // 1)) if value > 0 else 0
    if value <= 1:
        return 1
    base = 10 ** (len(str(value)) - 1)
    for mult in (Fraction(1), Fraction(2), Fraction(5, 2), Fraction(5), Fraction(10)):
        top = mult * base
        if top >= value:
            return int(top) if top.denominator == 1 else float(top)
    return 10 * base


def token_ticks(max_tokens):
    """(nice maximum, ticks): 4 steps from 0 to the nice maximum."""
    top = nice_max(max_tokens)
    frac = Fraction(top)
    ticks = []
    for i in range(5):
        step = frac * i / 4
        ticks.append(int(step) if step.denominator == 1 else float(step))
    return top, ticks


def run_ticks(max_runs):
    """Integer ticks from 0, in 3 or 4 steps, whichever tops out lower."""
    if max_runs <= 0:
        return [0, 1, 2, 3]
    best = None
    for n in (3, 4):
        raw = max_runs / float(n)
        k = 10 ** (len(str(int(raw))) - 1) if raw >= 1 else 1
        for mult in (1, 2, 2.5, 4, 5, 10):
            step = max(1, int(-(-(mult * k) // 1)))
            if step * n >= max_runs:
                top = step * n
                if best is None or top < best[2]:
                    best = (step, n, top)
                break
    step, n, _top = best
    return [step * i for i in range(n + 1)]


# ---------------------------------------------------------------- sums

class _Acc(object):
    """Running sums for one group of requests."""

    __slots__ = ("requests", "input", "output", "cache_read", "cw5", "cw1",
                 "thinking", "cost", "k_in", "k_out", "k_cr", "k_cw",
                 "unpriced_requests", "unpriced_tokens", "runs", "sessions")

    def __init__(self):
        self.requests = self.input = self.output = self.cache_read = 0
        self.cw5 = self.cw1 = 0
        self.thinking = None
        self.cost = 0.0
        self.k_in = self.k_out = self.k_cr = self.k_cw = 0.0
        self.unpriced_requests = self.unpriced_tokens = 0
        self.runs = set()
        self.sessions = set()

    def add(self, req):
        rec = req.rec
        self.requests += 1
        self.input += rec.input
        self.output += rec.output
        self.cache_read += rec.cache_read
        self.cw5 += rec.cache_write_5m
        self.cw1 += rec.cache_write_1h
        if rec.thinking is not None:
            self.thinking = rec.thinking if self.thinking is None else self.thinking + rec.thinking
        parts = req.parts
        if parts is None:
            self.unpriced_requests += 1
            self.unpriced_tokens += req.tokens
        else:
            self.cost += req.cost
            self.k_in += parts["input"]
            self.k_out += parts["output"]
            self.k_cr += parts["cache_read"]
            self.k_cw += parts["cache_write"]
        self.sessions.add(rec.session_id)
        if rec.run_id is not None:
            self.runs.add((rec.session_id, rec.run_id))

    def total_tokens(self):
        return self.input + self.output + self.cache_read + self.cw5 + self.cw1

    def finish(self):
        cw = self.cw5 + self.cw1
        denom = self.cache_read + cw + self.input
        return {
            "tokens": self.input + self.output + self.cache_read + cw,
            "input": self.input,
            "output": self.output,
            "cache_read": self.cache_read,
            "cache_write": cw,
            "cache_write_5m": self.cw5,
            "cache_write_1h": self.cw1,
            "thinking": self.thinking,
            "cost": self.cost,
            "cost_by_kind": {"input": self.k_in, "output": self.k_out,
                             "cache_read": self.k_cr, "cache_write": self.k_cw},
            "unpriced_requests": self.unpriced_requests,
            "unpriced_tokens": self.unpriced_tokens,
            "hit_rate": (self.cache_read / float(denom)) if denom else None,
            "requests": self.requests,
            "runs": len(self.runs),
            "sessions": len(self.sessions),
        }


class _Req(object):
    """One record with the values every group needs, worked out once."""

    __slots__ = ("rec", "ts", "model", "parts", "cost", "tokens", "agent",
                 "route_key", "display", "local")


class _Run(object):
    __slots__ = ("session_id", "run_id", "folder", "first", "acc", "pairs")

    def __init__(self, req):
        self.session_id = req.rec.session_id
        self.run_id = req.rec.run_id
        self.folder = req.rec.folder
        self.first = req.ts
        self.acc = _Acc()
        self.pairs = {}

    def pair(self):
        """The (model, effort) pair with the most requests; ties go to the first seen."""
        best = None
        best_n = 0
        for pair, n in self.pairs.items():
            if n > best_n:
                best, best_n = pair, n
        return best


class _Agent(object):
    __slots__ = ("agent", "route_key", "display", "acc", "pairs", "runs")

    def __init__(self, req):
        self.agent = req.agent
        self.route_key = req.route_key
        self.display = req.display
        self.acc = _Acc()
        self.pairs = {}
        self.runs = {}


class _Session(object):
    __slots__ = ("acc", "agents", "by_agent")

    def __init__(self):
        self.acc = _Acc()
        self.agents = set()
        self.by_agent = {}


class _SessionInfo(object):
    """Facts about a session taken from every record, in range or not."""

    __slots__ = ("main_ts", "main_folder", "main_branch", "any_ts", "any_folder",
                 "any_branch", "branch_ts", "branch")

    def __init__(self):
        self.main_ts = self.any_ts = self.branch_ts = None
        self.main_folder = self.any_folder = None
        self.main_branch = self.any_branch = self.branch = None

    def add(self, rec):
        ts = rec.ts_utc
        if self.any_ts is None or ts < self.any_ts:
            self.any_ts, self.any_folder, self.any_branch = ts, rec.folder, rec.git_branch
        if rec.run_id is None and (self.main_ts is None or ts < self.main_ts):
            self.main_ts, self.main_folder, self.main_branch = ts, rec.folder, rec.git_branch
        if rec.git_branch is not None and (self.branch_ts is None or ts < self.branch_ts):
            self.branch_ts, self.branch = ts, rec.git_branch

    @property
    def start(self):
        return self.main_ts if self.main_ts is not None else self.any_ts

    @property
    def folder(self):
        return self.main_folder if self.main_ts is not None else self.any_folder

    @property
    def start_branch(self):
        value = self.main_branch if self.main_ts is not None else self.any_branch
        return value if value is not None else self.branch


# ---------------------------------------------------------------- helpers

def _agent_of(rec):
    """(agent, route_key, display). Main means run_id is None, not agent_type None."""
    if rec.run_id is None:
        return None, MAIN_KEY, MAIN_DISPLAY
    if not rec.agent_type:
        return UNNAMED_KEY, UNNAMED_KEY, UNNAMED_DISPLAY
    return rec.agent_type, rec.agent_type, rec.agent_type


def _order_key(agg, tie):
    """One agent order everywhere: estimated cost highest first, then tokens."""
    return (-agg["cost"], -agg["tokens"], tie)


def _shares(values):
    """Largest-remainder shares of values that sum to 100, and a '<1%' flag each."""
    total = float(sum(values))
    if total <= 0:
        return [(0, False) for _ in values]
    raw = [round(100.0 * v / total, 9) for v in values]
    base = [int(r // 1) for r in raw]
    deficit = 100 - sum(base)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[:max(deficit, 0)]:
        base[i] += 1
    return [(base[i], 0 < raw[i] < 0.5) for i in range(len(raw))]


def _rel_pct(cur, prev):
    if prev is None or not prev:
        return None
    return (cur - prev) / float(prev) * 100.0


def _deltas(totals, previous):
    if previous is None:
        return {"tokens_pct": None, "cost_pct": None, "runs_pct": None, "hit_rate_pts": None}
    prev_rate = previous["hit_rate"]
    cur_rate = totals["hit_rate"]
    points = None
    if prev_rate is not None and cur_rate is not None:
        points = (cur_rate - prev_rate) * 100.0
    return {
        "tokens_pct": _rel_pct(totals["tokens"], previous["tokens"]),
        "cost_pct": _rel_pct(totals["cost"], previous["cost"]),
        "runs_pct": _rel_pct(totals["runs"], previous["runs"]),
        "hit_rate_pts": points,
    }


class _Context(object):
    """Everything shared by the three ranges."""

    def __init__(self):
        self.tz = None
        self.now_utc = None
        self.now_local = None
        self.reqs = []
        self.req_ts = []
        self.scope = ALL
        self.single = False
        self.pin_fn = None
        self.sessions = {}
        self.folder_names = {}
        self.listed = {}
        self.catalog_order = {}
        self.catalog_names = {}
        self.eff_oldest = None
        self.base_notes = {}
        self.no_id_rows = 0

    def iso(self, value):
        return value.astimezone(self.tz).isoformat()

    def project_name(self, folder):
        return self.folder_names.get(folder, folder)


# ---------------------------------------------------------------- build

def build_views(records, scope, now, tz, prices, catalog, oldest_seen,
                projects=(), reader_notes=None, tz_fixed=False, pin_fn=None):
    """Return {"today": View, "7d": View, "30d": View}. See the module docstring."""
    now = _aware(now)
    records, no_id = dedupe(records)
    ctx = _Context()
    ctx.tz = tz
    ctx.now_utc = now.astimezone(_UTC)
    ctx.now_local = now.astimezone(tz)
    ctx.scope = scope
    ctx.single = scope != ALL
    ctx.pin_fn = pin_fn
    ctx.no_id_rows = no_id
    notes = dict(reader_notes or {})
    ctx.base_notes = {
        "malformed_lines": notes.get("malformed_lines", 0),
        "synthetic_rows": notes.get("synthetic_rows", 0),
        "no_id_rows": notes.get("no_id_rows", 0) + no_id,
        "skipped_old_files": notes.get("skipped_old_files", 0),
        "tz_fixed": bool(tz_fixed),
    }
    for i, model in enumerate(catalog):
        ctx.catalog_order[model["id"]] = i
        ctx.catalog_names[model["id"]] = model.get("display_name") or model["id"]

    listed_by_folder = {}
    by_key = {}
    for project in projects:
        by_key.setdefault(project["key"], project)
        folder = project.get("folder")
        if folder is not None:
            listed_by_folder.setdefault(folder, project)
    ctx.listed = listed_by_folder

    # One pass over every record: session facts and folder names.
    cwd_counts = {}
    for rec in records:
        info = ctx.sessions.get(rec.session_id)
        if info is None:
            info = ctx.sessions[rec.session_id] = _SessionInfo()
        info.add(rec)
        if rec.cwd and rec.folder not in listed_by_folder:
            counts = cwd_counts.get(rec.folder)
            if counts is None:
                counts = cwd_counts[rec.folder] = collections.Counter()
            counts[rec.cwd] += 1
    for folder, project in listed_by_folder.items():
        ctx.folder_names[folder] = project.get("name") or folder
    for folder, counts in cwd_counts.items():
        ctx.folder_names[folder] = _name_from_cwd(counts.most_common(1)[0][0], folder)

    # Scope.
    if scope == ALL:
        if ALL_PROJECTS_SCOPE == "listed":
            scoped = [r for r in records if r.folder in listed_by_folder]
        else:
            scoped = records
    else:
        project = by_key.get(scope)
        folder = project.get("folder") if project else None
        scoped = [r for r in records if r.folder == folder] if folder is not None else []

    seen = oldest_seen or {}
    if scope == ALL:
        values = list(seen.values())
    else:
        values = [seen[folder]] if folder is not None and folder in seen else []
    ctx.eff_oldest = min(_aware(v) for v in values) if values else None

    windows = {}
    low = None
    for name, days in RANGES:
        windows[name] = _window(tz, ctx.now_local, days)
        if low is None or windows[name][1] < low:
            low = windows[name][1]
    low_utc = low.astimezone(_UTC)

    # Price only the records any window can use, then sort them by time.
    model_cache = {}
    reqs = []
    for rec in scoped:
        if rec.ts_utc < low_utc or rec.ts_utc > ctx.now_utc:
            continue
        req = _Req()
        req.rec = rec
        req.ts = rec.ts_utc
        raw = rec.model_raw
        label = model_cache.get(raw)
        if label is None:
            known, _form = resolve.normalize_model(raw, catalog)
            label = model_cache[raw] = known or raw or UNKNOWN_MODEL
        req.model = label
        req.tokens = rec.input + rec.output + rec.cache_read + rec.cache_write_5m + rec.cache_write_1h
        parts = price_list.price_parts(rec, prices, catalog)
        req.parts = parts
        req.cost = sum(parts.values()) if parts is not None else None
        req.agent, req.route_key, req.display = _agent_of(rec)
        req.local = None
        reqs.append(req)
    reqs.sort(key=lambda r: r.ts)
    ctx.reqs = reqs
    ctx.req_ts = [r.ts for r in reqs]

    views = {}
    for name, days in RANGES:
        views[name] = _build_view(ctx, name, days, windows[name], by_key)
    return views


def _name_from_cwd(cwd, folder):
    parts = [p for p in _PATH_SPLIT.split(cwd.rstrip("/\\")) if p]
    return parts[-1] if parts else folder


def _slice(ctx, start, end):
    lo = bisect.bisect_left(ctx.req_ts, start.astimezone(_UTC))
    hi = bisect.bisect_right(ctx.req_ts, end.astimezone(_UTC))
    return ctx.reqs[lo:hi]


def _build_view(ctx, name, days, window, by_key):
    tz = ctx.tz
    start, prev_start, prev_end = window
    end = ctx.now_local
    cur = _slice(ctx, start, end)

    previous = None
    if ctx.eff_oldest is not None and prev_start >= ctx.eff_oldest:
        acc = _Acc()
        for req in _slice(ctx, prev_start, prev_end):
            acc.add(req)
        previous = acc.finish()

    hourly = name == "today"
    if hourly:
        buckets, index = _hour_buckets(ctx, start)
    else:
        buckets, index = _day_buckets(ctx, start.date(), days)
    bucket_models = [collections.defaultdict(int) for _ in buckets]
    bucket_runs = [collections.defaultdict(set) for _ in buckets]
    bucket_tokens = [0] * len(buckets)

    totals = _Acc()
    models = {}
    model_agents = {}
    efforts = {}
    agents = {}
    sessions = {}
    projects = {} if not ctx.single else None
    unpriced = {}

    for req in cur:
        rec = req.rec
        totals.add(req)

        acc = models.get(req.model)
        if acc is None:
            acc = models[req.model] = _Acc()
            model_agents[req.model] = set()
        acc.add(req)
        model_agents[req.model].add(req.display)

        acc = efforts.get(rec.effort)
        if acc is None:
            acc = efforts[rec.effort] = _Acc()
        acc.add(req)

        grp = agents.get(req.route_key)
        if grp is None:
            grp = agents[req.route_key] = _Agent(req)
        grp.acc.add(req)
        pair = (req.model, rec.effort)
        grp.pairs[pair] = grp.pairs.get(pair, 0) + 1
        # A subagent run is (session, run id). For Main a run is the session.
        run_key = (rec.session_id, rec.run_id)
        run = grp.runs.get(run_key)
        if run is None:
            run = grp.runs[run_key] = _Run(req)
        run.acc.add(req)
        run.pairs[pair] = run.pairs.get(pair, 0) + 1

        sess = sessions.get(rec.session_id)
        if sess is None:
            sess = sessions[rec.session_id] = _Session()
        sess.acc.add(req)
        if rec.run_id is not None:
            sess.agents.add(req.display)
        entry = sess.by_agent.get(req.route_key)
        if entry is None:
            entry = sess.by_agent[req.route_key] = (req.agent, _Acc())
        entry[1].add(req)

        if projects is not None:
            acc = projects.get(rec.folder)
            if acc is None:
                acc = projects[rec.folder] = _Acc()
            acc.add(req)

        if req.parts is None:
            row = unpriced.get(req.model)
            if row is None:
                row = unpriced[req.model] = [0, 0]
            row[0] += 1
            row[1] += req.tokens

        local = req.local
        if local is None:
            local = req.local = req.ts.astimezone(tz)
        bi = index.get((local.hour, local.fold) if hourly else local.date())
        if bi is not None:
            bucket_tokens[bi] += req.tokens
            bucket_models[bi][req.model] += req.tokens
            bucket_runs[bi][req.route_key].add(run_key)

    total_agg = totals.finish()

    # Buckets and axis.
    out_buckets = []
    for i, bucket in enumerate(buckets):
        bucket = dict(bucket)
        bucket["tokens"] = bucket_tokens[i]
        bucket["by_model"] = dict(bucket_models[i])
        bucket["runs_by_agent"] = {k: len(v) for k, v in bucket_runs[i].items()}
        out_buckets.append(bucket)
    nice, ticks = token_ticks(max(bucket_tokens) if bucket_tokens else 0)
    max_runs = max((sum(b["runs_by_agent"].values()) for b in out_buckets), default=0)
    axis = {"tokens_max_nice": nice, "tokens_ticks": ticks, "runs_ticks": run_ticks(max_runs)}

    view = {
        "range": name,
        "start": ctx.iso(start),
        "end": ctx.iso(end),
        "previous_start": ctx.iso(prev_start),
        "previous_end": ctx.iso(prev_end),
        "totals": total_agg,
        "previous": previous,
        "deltas": _deltas(total_agg, previous),
        "by_model": _model_rows(ctx, models, model_agents),
        "by_effort": _effort_rows(efforts),
        "by_agent": _agent_rows(ctx, agents, bucket_runs),
        "bucket_unit": "hour" if hourly else "day",
        "buckets": out_buckets,
        "axis": axis,
        "sessions": _session_rows(ctx, sessions),
        "by_project": _project_rows(ctx, projects) if projects is not None else None,
    }
    notes = dict(ctx.base_notes)
    notes["unpriced"] = [
        {"model": m, "requests": v[0], "tokens": v[1]}
        for m, v in sorted(unpriced.items(), key=lambda kv: (-kv[1][1], kv[0]))
    ]
    view["notes"] = notes
    return view


# ---------------------------------------------------------------- buckets

def _hour_buckets(ctx, start):
    """Every local hour of the start's day. 23, 24 or 25 of them."""
    tz = ctx.tz
    day = start.date()
    buckets = []
    index = {}
    t = start.astimezone(_UTC)
    for _ in range(26):
        local = t.astimezone(tz)
        if local.date() != day:
            break
        index[(local.hour, local.fold)] = len(buckets)
        buckets.append({"start": local.isoformat(), "date": day.isoformat(), "hour": local.hour})
        t += _ONE_HOUR
    return buckets, index


def _day_buckets(ctx, first_day, days):
    buckets = []
    index = {}
    for i in range(days):
        day = first_day + datetime.timedelta(days=i)
        index[day] = len(buckets)
        buckets.append({"start": _wall(ctx.tz, day, _MIDNIGHT).isoformat(),
                        "date": day.isoformat(), "hour": None})
    return buckets, index


# ---------------------------------------------------------------- rows

def _model_rows(ctx, models, model_agents):
    ids = list(models)
    known = sorted((m for m in ids if m in ctx.catalog_order), key=lambda m: ctx.catalog_order[m])
    unknown = sorted((m for m in ids if m not in ctx.catalog_order),
                     key=lambda m: (-models[m].total_tokens(), m))
    rows = []
    for m in known + unknown:
        agg = models[m].finish()
        if m in ctx.catalog_order:
            agg["model"] = m
            agg["display_name"] = ctx.catalog_names[m]
            agg["cat"] = CAT_SLOTS.get(m, "other")
        else:
            agg["model"] = m
            agg["display_name"] = UNKNOWN_MODEL_DISPLAY if m == UNKNOWN_MODEL else m
            agg["cat"] = "other"
            agg["cost"] = None
        agg["agents"] = sorted(model_agents[m])
        rows.append(agg)
    shares = _shares([r["cost"] or 0.0 for r in rows])
    for row, (pct, lt1) in zip(rows, shares):
        row["share_pct"] = pct
        row["share_lt1"] = lt1
    return rows


def _effort_rows(efforts):
    order = list(EFFORT_LEVELS)
    if EFFORT_MAX in efforts:
        order.append(EFFORT_MAX)
    others = sorted(e for e in efforts if e is not None and e not in EFFORT_LEVELS and e != EFFORT_MAX)
    order.extend(others)
    if None in efforts:
        order.append(None)
    rows = []
    for effort in order:
        acc = efforts.get(effort)
        agg = (acc or _Acc()).finish()
        agg["effort"] = effort
        rows.append(agg)
    return rows


def _agent_rows(ctx, agents, bucket_runs):
    rows = []
    for key, grp in agents.items():
        agg = grp.acc.finish()
        runs = list(grp.runs.values())
        reps = [(run, run.pair()) for run in runs]
        run_counts = collections.Counter(pair for _run, pair in reps)
        ran_with = []
        for pair, n in grp.pairs.items():
            ran_with.append({"model": pair[0], "effort": pair[1], "requests": n,
                             "runs": run_counts.get(pair, 0)})
        ran_with.sort(key=lambda row: (-row["requests"], -row["runs"]))
        agg.update({
            "agent": grp.agent,
            "route_key": grp.route_key,
            "display": grp.display,
            "ran_with": ran_with,
            "pin": None,
            "recent_runs": _recent_runs(ctx, runs),
            "runs_per_day": [len(b.get(key, ())) for b in bucket_runs],
        })
        # axis.runs_ticks is scaled for the whole view, so one agent's chart gets its own.
        agg["runs_ticks"] = run_ticks(max(agg["runs_per_day"], default=0))
        if ctx.single and ctx.pin_fn is not None:
            run_list = [{"run_id": run.run_id if run.run_id is not None else run.session_id,
                         "model": pair[0], "effort": pair[1], "requests": run.acc.requests}
                        for run, pair in reps]
            agg["pin"] = ctx.pin_fn(key, ran_with, run_list)
        rows.append(agg)
    rows.sort(key=lambda a: _order_key(a, a["route_key"]))
    return rows


def _recent_runs(ctx, runs):
    newest = sorted(runs, key=lambda r: (r.first, r.session_id, r.run_id or ""), reverse=True)
    out = []
    for run in newest[:RECENT_RUNS]:
        agg = run.acc.finish()
        model, effort = run.pair()
        info = ctx.sessions.get(run.session_id)
        out.append({
            "run_id": run.run_id,
            "started": ctx.iso(run.first),
            "session_id": run.session_id,
            "session_started": ctx.iso(info.start if info is not None else run.first),
            "project": ctx.project_name(run.folder),
            "model": model,
            "effort": effort,
            "tokens": agg["tokens"],
            "cost": agg["cost"],
            "hit_rate": agg["hit_rate"],
            "requests": agg["requests"],
        })
    return out


def _session_rows(ctx, sessions):
    rows = []
    for sid, sess in sessions.items():
        info = ctx.sessions[sid]
        agg = sess.acc.finish()
        by_agent = []
        for _key, (agent, acc) in sess.by_agent.items():
            row = acc.finish()
            row["agent"] = agent
            by_agent.append((_key, row))
        by_agent.sort(key=lambda kv: _order_key(kv[1], kv[0]))
        agg.update({
            "session_id": sid,
            "project": ctx.project_name(info.folder),
            "branch": info.start_branch,
            "started": ctx.iso(info.start),
            "agents": sorted(sess.agents),
            "by_agent": [row for _key, row in by_agent],
        })
        rows.append((info.start, sid, agg))
    rows.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [agg for _start, _sid, agg in rows]


def _project_rows(ctx, projects):
    rows = []
    for folder, acc in projects.items():
        agg = acc.finish()
        listed = ctx.listed.get(folder)
        agg.update({
            "key": listed["key"] if listed is not None else None,
            "name": ctx.project_name(folder),
            "listed": listed is not None,
            "folder": folder,
        })
        rows.append(agg)
    rows.sort(key=lambda a: _order_key(a, a["name"]))
    return rows
