"""The /api/live route: what one running session of one project is doing now.

A route is a function (ctx, query) -> (status, payload). ctx is the server's
Context and query is the parsed query string. The server turns the payload into
JSON.

The page polls this route every second, so the work per request stays
small. The route reads only the transcript folder of the asked project
(transcripts.Reader.read_folder), which re-parses only the bytes a file gained.
The deduped records of that folder are grouped by session and kept on the
usage Cache (live, under live_lock), keyed by the folder signature, together
with the session's links (transcripts.Links per file: which agents it launched,
when it was resumed, when it stopped), so they are rebuilt only when a file
changes. A request then touches one session's records.
The route takes cache.lock only to create the reader or load the prices, and
never while it reads, so a slow All projects build on /api/usage does not hold
it.

Query. project=<key> is required and takes one value. session=<id> picks a
session and etag=<tag> is the tag of the answer the page already has. A missing
project or a repeated parameter gets 400 bad_request, project=all gets 400
pick_project, and a key that is not listed gets 404 unknown_project. When etag
equals the tag of the answer the server would send, the answer is only
{project, server_time, etag, unchanged: true}.

Sessions. running lists the sessions of the project with a request in the last
RUNNING_MINUTES, newest request first. session is the asked one when it is in
running, else the first of running (session_gone is then true if one was asked),
or null when nothing runs. active is True when the last request is less than
ACTIVE_SECONDS old. A session counts every record of its id in the project
folder with a time up to now, so records after now (a fixture clock) are
ignored. usage.dedupe runs first, so the largest row per message id wins and a
total never steps back when a row grows.

Chart numbers. In minutes[], tokens and by_model count new tokens only, which
are input, cache writes (5 minute and 1 hour) and output, and tokens is the sum
of by_model. A model with no new tokens in a minute is left out of by_model.
cache_read is that minute's cache read tokens, so tokens plus cache_read is the
minute's total. axis is drawn over the tallest new-token minute, and the
session by_model legend sums new tokens over the 30 minutes. Each request in
requests[] keeps tokens as its total of all kinds and adds its cache_read.

Runs. session.runs lists the main session and every agent run of the session
with a request up to now, in dispatch order (main first), for the dispatch
canvas. A run has its parent (the earliest link row up to now that names it, with
a link to itself or to an ancestor dropped; "@main" with parent_known false when
no usable link exists), its rounds (round 1 from its first request, later ones
from briefs that came after the agent stopped), a state of working, idle or done,
and the totals the agents card counts. A foreground agent is linked only when it
finishes, so it reads as not linked until then. Links, briefs and stops after now
are ignored.

Times are ISO strings in the page zone (api_usage._zone). The etag is the first
16 hex digits of a sha256 over the JSON of every field except server_time and
etag. It does not depend on the clock except through the values listed there:
the minute buckets, last_minute and active, and runs[].state, which is working
or idle by the age of the run's last activity.

No response holds message text, tool data, a cwd or an agent description: the
reader keeps none, and this module adds only counts, ids hashed from message
ids, model and agent names, and git branch names. Run ids in runs[] are hashed
from agent ids (the first 12 hex digits of a sha256), so no raw agent id leaves
the server, and the rounds say only who briefed a run (the main session, another
run, or nobody). The one path in an answer is the display path in unreadable.

Standard library only, Python 3.9. Nothing here writes a file.
"""
import bisect
import datetime
import hashlib
import json
import os

import api_usage
import prices as price_list
import projects
import resolve
import transcripts
import usage as usage_views

RUNNING_MINUTES = 30
ACTIVE_SECONDS = 60
BUCKETS = 30
LATEST = 8

_UTC = datetime.timezone.utc
_MINUTE = datetime.timedelta(minutes=1)


class _Sess(object):
    """The deduped records of one session, oldest first, with their times and
    (built on first use) the priced requests that usage.build_views would make."""

    __slots__ = ("records", "ts", "reqs", "links")

    def __init__(self, records, links=None):
        self.records = records
        self.ts = [r.ts_utc for r in records]
        self.reqs = None
        # {run id, or None for the main session: transcripts.Links} over the session's files.
        self.links = links or {}


def _index(records, links=None):
    """{session id: _Sess} over the deduped records of one folder.

    links is FolderResult.links, {(session id, run id or None): Links}, or None.
    """
    kept, _no_id = usage_views.dedupe(records)
    grouped = {}
    for rec in kept:
        grouped.setdefault(rec.session_id, []).append(rec)
    by_session = {}
    for (sid, run), item in (links or {}).items():
        by_session.setdefault(sid, {})[run] = item
    out = {}
    for sid, recs in grouped.items():
        recs.sort(key=lambda r: r.ts_utc)  # stable: equal times keep file order
        out[sid] = _Sess(recs, by_session.get(sid))
    return out


def _requests(sess, prices, catalog):
    """The priced requests of a session (all its records), built once."""
    if sess.reqs is None:
        labels = {}
        reqs = []
        for rec in sess.records:
            req = usage_views._Req()
            req.rec = rec
            req.ts = rec.ts_utc
            raw = rec.model_raw
            label = labels.get(raw)
            if label is None:
                known, _form = resolve.normalize_model(raw, catalog)
                label = labels[raw] = known or raw or usage_views.UNKNOWN_MODEL
            req.model = label
            req.tokens = (rec.input + rec.output + rec.cache_read
                          + rec.cache_write_5m + rec.cache_write_1h)
            req.parts = price_list.price_parts(rec, prices, catalog)
            req.cost = sum(req.parts.values()) if req.parts is not None else None
            req.agent, req.route_key, req.display = usage_views._agent_of(rec)
            req.local = None
            reqs.append(req)
        sess.reqs = reqs
    return sess.reqs


def _request_id(rec):
    """First 12 hex of a sha256 over the dedupe key. The same row gives the same id on every poll."""
    if rec.message_id:
        key = [0, rec.message_id]
    elif rec.request_id:
        key = [1, rec.request_id]
    else:
        key = [2, rec.ts_utc.isoformat(), rec.session_id, rec.run_id]
    return hashlib.sha256(json.dumps(key).encode("utf-8")).hexdigest()[:12]


def _unreadable(ctx, folder, folder_failed, has_records):
    """The display path of what could not be read, or None (see api_usage._unreadable).

    The projects folder when it cannot be listed (checked only when the project
    folder gave nothing, since a failed project folder is the common case there),
    else the project's own folder when it could not be used.
    """
    top = os.path.join(ctx.config_dir, "projects")
    if not has_records and transcripts._listdir_checked(top) is None and os.path.isdir(top):
        return resolve.display_path(top, home=ctx.home, root=ctx.root)
    if folder_failed and folder is not None:
        return resolve.display_path(os.path.join(top, folder), home=ctx.home, root=ctx.root)
    return None


def _model_display(label, names):
    if label in names:
        return names[label]
    if label == usage_views.UNKNOWN_MODEL:
        return usage_views.UNKNOWN_MODEL_DISPLAY
    return label


def _pair(pairs):
    """The (model, effort) with the most requests; ties go to the first seen."""
    best, best_n = None, 0
    for pair, n in pairs.items():
        if n > best_n:
            best, best_n = pair, n
    return best


def _summary(acc, keys):
    done = acc.finish()
    out = {}
    for key in keys:
        out[key] = done[key]
    return out


MAIN_RUN = usage_views.MAIN_KEY
_TOGETHER = datetime.timedelta(seconds=5)


def _run_id(agent_id):
    """First 12 hex of a sha256 over an agent id, so the raw id never leaves the server."""
    return hashlib.sha256(agent_id.encode("utf-8")).hexdigest()[:12]


def _parents(sess, now_utc):
    """{child agent id: (dispatcher run key, link time)} from the links up to now.

    The dispatcher key is None for the main session. The earliest link wins. A link
    from a run to itself, or to one of its own ancestors, is dropped, so there is no cycle.
    """
    found = []
    for dispatcher, item in sess.links.items():
        for child, ts in item.launched:
            if ts <= now_utc:
                found.append((ts, dispatcher or "", dispatcher, child))
    found.sort(key=lambda f: f[:2] + (f[3],))
    parent_of = {}
    for ts, _tie, dispatcher, child in found:
        if child in parent_of or child == dispatcher:
            continue
        up, cycle = dispatcher, False
        while up is not None:
            if up == child:
                cycle = True
                break
            up = parent_of[up][0] if up in parent_of else None
        if not cycle:
            parent_of[child] = (dispatcher, ts)
    return parent_of


def _group_runs(reqs):
    """{run key: group} over the requests, oldest first. The key is None for the main session."""
    groups = {}
    for req in reqs:
        key = req.rec.run_id
        group = groups.get(key)
        if group is None:
            group = groups[key] = {"acc": usage_views._Acc(), "pairs": {}, "ts": [],
                                   "route_key": req.route_key, "agent": req.agent}
        group["acc"].add(req)
        pair = (req.model, req.rec.effort)
        group["pairs"][pair] = group["pairs"].get(pair, 0) + 1
        group["ts"].append(req.ts)
    return groups


def _run_rounds(key, group, sess, now_utc, tz, ids, parent):
    """The rounds of one run: round 1 from its first request, the rest from briefs up to now.

    Each round is a dict plus "_at", its start as a datetime (the caller drops it).
    """
    ts = group["ts"]
    starts = [(ts[0], parent)]
    item = sess.links.get(key)
    if key is not None and item is not None:
        briefs = sorted((r for r in item.rounds if r[0] <= now_utc), key=lambda r: r[0])
        for at, kind, sender in briefs:
            if kind == "coordinator":
                by = MAIN_RUN
            elif kind == "peer" and sender is not None and sender != key and sender in ids:
                by = ids[sender]
            else:
                by = None
            starts.append((at, by))
    out = []
    for i, (at, by) in enumerate(starts):
        lo = bisect.bisect_left(ts, at)
        hi = bisect.bisect_left(ts, starts[i + 1][0]) if i + 1 < len(starts) else len(ts)
        last = ts[hi - 1] if hi > lo else at
        out.append({"n": i + 1, "started": at.astimezone(tz).isoformat(),
                    "last_request": last.astimezone(tz).isoformat(), "by": by, "_at": at})
    return out


def _runs(sess, reqs, now_utc, tz, names):
    """session.runs: the main session and each agent run with a request up to now.

    See the module docstring. reqs are the session's priced requests up to now.
    """
    groups = _group_runs(reqs)
    ids = {key: (MAIN_RUN if key is None else _run_id(key)) for key in groups}
    parent_of = _parents(sess, now_utc)

    # The parent as drawn: the dispatcher when it is a run of this session, else the main session.
    pkey, known, linked = {}, {}, {}
    for key in groups:
        if key is None:
            continue
        found = parent_of.get(key)
        if found is not None and (found[0] is None or found[0] in groups):
            pkey[key], known[key], linked[key] = found[0], True, found[1]
        else:
            pkey[key], known[key], linked[key] = None, False, None
    order = sorted((key for key in groups if key is not None),
                   key=lambda key: (groups[key]["ts"][0], ids[key]))
    if None in groups:
        order.insert(0, None)

    # label_n: the rank among runs of one route key, in dispatch order.
    rank, total = {}, {}
    for key in order:
        route = groups[key]["route_key"]
        total[route] = total.get(route, 0) + 1
        rank[key] = total[route]

    # together: siblings drawn under one parent, each launched within 5 s of the one before.
    together = {}
    siblings = {}
    for key in order:
        if key is not None:
            siblings.setdefault(pkey[key], []).append(key)
    for members in siblings.values():
        launch = {}
        for key in members:
            first = groups[key]["ts"][0]
            launch[key] = min(linked[key], first) if linked[key] is not None else first
        members.sort(key=lambda k: (launch[k], ids[k]))
        chains = []
        for key in members:
            if chains and launch[key] - launch[chains[-1][-1]] <= _TOGETHER:
                chains[-1].append(key)
            else:
                chains.append([key])
        for chain in chains:
            if len(chain) > 1:
                for key in chain:
                    together[key] = {"key": ids[chain[0]], "n": len(chain)}

    rounds = {}
    for key in groups:
        rounds[key] = _run_rounds(key, groups[key], sess, now_utc, tz, ids,
                                  None if key is None else MAIN_RUN if pkey[key] is None else ids[pkey[key]])

    # done: the last stop up to now is a finished one, no round started after it, and every
    # child run is done. Deepest runs first, so the children are known.
    children = {}
    for key, up in pkey.items():
        children.setdefault(up, []).append(key)
    depth = {}

    def depth_of(key):
        steps = 0
        while key is not None and steps <= len(groups):
            key = pkey.get(key)
            steps += 1
        return steps

    for key in groups:
        depth[key] = depth_of(key)
    done = {}
    for key in sorted(groups, key=lambda k: -depth[k]):
        stop = None
        item = sess.links.get(key)
        if key is not None and item is not None:
            for at, finished in reversed(item.stops):
                if at <= now_utc:
                    stop = (at, finished)
                    break
        done[key] = bool(stop is not None and stop[1] and rounds[key][-1]["_at"] <= stop[0]
                         and all(done[c] for c in children.get(key, ())))

    result = []
    first = 0 if None in groups else 1  # dispatch_order 0 is the main session; agents start at 1
    for place, key in enumerate(order):
        group = groups[key]
        model, effort = _pair(group["pairs"])
        acc = group["acc"]
        ts = group["ts"]
        active_at = max(ts[-1], rounds[key][-1]["_at"])
        if done[key]:
            state = "done"
        elif now_utc - active_at < datetime.timedelta(seconds=ACTIVE_SECONDS):
            state = "working"
        else:
            state = "idle"
        route = group["route_key"]
        named = route not in (usage_views.MAIN_KEY, usage_views.UNNAMED_KEY)
        result.append({
            "run_id": ids[key],
            "route_key": route,
            "agent": group["agent"] if named else None,
            "label_n": rank[key] if key is not None and total[route] > 1 else None,
            "model": model,
            "model_display": _model_display(model, names),
            "effort": effort,
            "parent": None if key is None else MAIN_RUN if pkey[key] is None else ids[pkey[key]],
            "parent_known": True if key is None else known[key],
            "dispatch_order": place + first,
            "together": together.get(key),
            "started": ts[0].astimezone(tz).isoformat(),
            "last_request": ts[-1].astimezone(tz).isoformat(),
            "active_at": active_at.astimezone(tz).isoformat(),
            "state": state,
            "rounds": [{k: v for k, v in r.items() if k != "_at"} for r in rounds[key]],
            "tokens": acc.total_tokens(),
            "cost": acc.cost if acc.requests > acc.unpriced_requests else None,
        })
    return result


def _session_answer(ctx, sid, sess, count, now, tz, prices, catalog):
    """The session object for the first `count` records of sess (those up to now)."""
    names = {m["id"]: m.get("display_name") or m["id"] for m in catalog}
    order = {m["id"]: i for i, m in enumerate(catalog)}
    reqs = _requests(sess, prices, catalog)[:count]
    now_utc = now.astimezone(_UTC)
    active_after = now_utc - datetime.timedelta(seconds=ACTIVE_SECONDS)

    info = usage_views._SessionInfo()
    for req in reqs:
        info.add(req.rec)
    last = reqs[-1].ts

    total = usage_views._Acc()
    for req in reqs:
        total.add(req)
    minute = usage_views._Acc()
    for req in reqs[bisect.bisect_right(sess.ts, active_after, 0, count):]:
        minute.add(req)

    # Thirty minute-aligned buckets in the page zone; the last holds now.
    floor_utc = now.replace(second=0, microsecond=0).astimezone(_UTC)
    first = floor_utc - _MINUTE * (BUCKETS - 1)
    buckets = [{} for _ in range(BUCKETS)]
    reads = [0] * BUCKETS
    low = bisect.bisect_left(sess.ts, first, 0, count)
    for req in reqs[low:]:
        at = int((req.ts - first) // _MINUTE)
        at = min(max(at, 0), BUCKETS - 1)
        rec = req.rec
        reads[at] += rec.cache_read
        fresh = rec.input + rec.output + rec.cache_write_5m + rec.cache_write_1h
        if fresh > 0:
            slot = buckets[at]
            slot[req.model] = slot.get(req.model, 0) + fresh
    sums = [sum(b.values()) for b in buckets]
    top, ticks = usage_views.token_ticks(max(sums))
    minutes = []
    for i in range(BUCKETS):
        minutes.append({
            "start": (first + _MINUTE * i).astimezone(tz).isoformat(),
            "tokens": sums[i],
            "by_model": dict(buckets[i]),
            "cache_read": reads[i],
        })
    per_model = {}
    for slot in buckets:
        for model, tokens in slot.items():
            per_model[model] = per_model.get(model, 0) + tokens
    models = sorted((m for m, t in per_model.items() if t > 0),
                    key=lambda m: (order.get(m, len(order)), m))
    by_model = [{"model": m, "display_name": _model_display(m, names), "tokens": per_model[m]}
                for m in models]

    # One row per agent over the whole session.
    groups = {}
    for req in reqs:
        group = groups.get(req.route_key)
        if group is None:
            group = groups[req.route_key] = {"acc": usage_views._Acc(), "pairs": {},
                                             "last": req.ts, "agent": None}
            if req.route_key not in (usage_views.MAIN_KEY, usage_views.UNNAMED_KEY):
                group["agent"] = req.agent
        group["acc"].add(req)
        pair = (req.model, req.rec.effort)
        group["pairs"][pair] = group["pairs"].get(pair, 0) + 1
        if req.ts > group["last"]:
            group["last"] = req.ts
    rows = []
    for route_key, group in groups.items():
        model, effort = _pair(group["pairs"])
        acc = group["acc"]
        rows.append({
            "route_key": route_key,
            "agent": group["agent"],
            "model": model,
            "model_display": _model_display(model, names),
            "effort": effort,
            "tokens": acc.total_tokens(),
            "cost": acc.cost,
            "requests": acc.requests,
            "last_request": group["last"].astimezone(tz).isoformat(),
            "active": group["last"] > active_after,
        })
    rows.sort(key=lambda r: usage_views._order_key(r, r["route_key"]))

    latest = []
    for req in reversed(reqs[-LATEST:]):
        rec = req.rec
        latest.append({
            "id": _request_id(rec),
            "ts": req.ts.astimezone(tz).isoformat(),
            "route_key": req.route_key,
            "agent": (req.agent if req.route_key not in (usage_views.MAIN_KEY, usage_views.UNNAMED_KEY)
                      else None),
            "model": req.model,
            "model_display": _model_display(req.model, names),
            "effort": rec.effort,
            "tokens": req.tokens,
            "cache_read": rec.cache_read,
            "output": rec.output,
            "cost": req.cost,
        })

    return {
        "session_id": sid,
        "started": info.start.astimezone(tz).isoformat(),
        "branch": info.start_branch,
        "last_request": last.astimezone(tz).isoformat(),
        "active": last > active_after,
        "totals": _summary(total, ("tokens", "input", "output", "cache_read", "cache_write", "cost",
                                   "unpriced_requests", "hit_rate", "requests")),
        "last_minute": _summary(minute, ("tokens", "cost", "unpriced_requests", "hit_rate", "requests")),
        "minutes": minutes,
        "axis": {"top": top, "ticks": ticks},
        "by_model": by_model,
        "agents": rows,
        "runs": _runs(sess, reqs, now_utc, tz, names),
        "requests": latest,
    }


def live(ctx, query):
    """Return (200, payload) as the module docstring describes, or (400/404, {"error": ...})."""
    for values in query.values():
        if len(values) > 1:
            return 400, {"error": "bad_request"}
    asked = query.get("project") or []
    if len(asked) != 1 or not asked[0]:
        return 400, {"error": "bad_request"}
    key = asked[0]
    if key == usage_views.ALL:
        return 400, {"error": "pick_project"}
    listing = projects.load(ctx)
    project = listing.find(key)
    if project is None:
        return 404, {"error": "unknown_project"}
    want_session = (query.get("session") or [""])[0] or None
    want_etag = (query.get("etag") or [""])[0] or None

    catalog = ctx.rules["models"]
    tz = api_usage._zone(ctx)[0]
    now = api_usage._now(ctx, tz)
    now_utc = now.astimezone(_UTC)
    cache = ctx.usage_cache
    reader, prices = cache.reader, cache.prices
    if reader is None or prices is None:
        with cache.lock:  # only to create what is missing; never held while reading
            if cache.reader is None:
                cache.reader = transcripts.Reader(ctx.config_dir)
            if cache.prices is None:
                cache.prices = price_list.load_prices()
            reader, prices = cache.reader, cache.prices

    def first_cwd(name):
        for rec in reader.read_folder(name, now).records:
            if rec.cwd:
                return rec.cwd
        return None

    top = os.path.join(ctx.config_dir, "projects")
    folder = transcripts.folder_for_path(project.path, top, first_cwd)
    if folder is None:
        result = transcripts.FolderResult([], hash(()), False)
    else:
        result = reader.read_folder(folder, now)
    with cache.live_lock:
        kept = cache.live.get(folder)
    if folder is not None and kept is not None and kept[0] == result.signature:
        index = kept[1]
    else:
        index = _index(result.records, result.links)
        if folder is not None:
            with cache.live_lock:
                cache.live[folder] = (result.signature, index)

    # Sessions with a request in the last RUNNING_MINUTES, newest first.
    edge = now_utc - datetime.timedelta(minutes=RUNNING_MINUTES)
    found = []
    for sid, sess in index.items():
        count = bisect.bisect_right(sess.ts, now_utc)
        if count == 0 or sess.ts[count - 1] <= edge:
            continue
        info = usage_views._SessionInfo()
        for rec in sess.records[:count]:
            info.add(rec)
        found.append((sess.ts[count - 1], sid, sess, count, info))
    found.sort(key=lambda f: (f[0], f[1]), reverse=True)
    running = [{
        "session_id": sid,
        "started": info.start.astimezone(tz).isoformat(),
        "branch": info.start_branch,
        "last_request": last.astimezone(tz).isoformat(),
        "requests": count,
    } for last, sid, _sess, count, info in found]

    chosen = None
    for item in found:
        if item[1] == want_session:
            chosen = item
            break
    session_gone = want_session is not None and chosen is None
    if chosen is None and found:
        chosen = found[0]
    session = None
    if chosen is not None:
        session = _session_answer(ctx, chosen[1], chosen[2], chosen[3], now, tz, prices, catalog)

    payload = {
        "project": key,
        "unchanged": False,
        "unreadable": _unreadable(ctx, folder, result.unreadable, bool(result.records)),
        "running": running,
        "session_gone": session_gone,
        "session": session,
    }
    etag = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    if want_etag is not None and want_etag == etag:
        return 200, {"project": key, "server_time": now.isoformat(), "etag": etag, "unchanged": True}
    payload["server_time"] = now.isoformat()
    payload["etag"] = etag
    return 200, payload
