"""Pin check for the usage page. Standard library only, pure.

It joins what the resolver says should win with what the runs did, so the page
can answer "Did it run as pinned?" It reads no clock, no environment and no
file. It returns data only, and the page renders the words.

    checker(entries, catalog) -> pin_fn
    check_agent(entries, agent_key, ran_with, runs, catalog) -> PinCheck or None

pin_fn has the signature usage.build_views calls: pin_fn(agent_key, ran_with,
runs). agent_key is an agent name, "@unnamed" or "@main". runs is every
in-range run as {run_id, model, effort, requests}. A run's model is a catalog
id, else the raw string. entries is the list resolve.resolve returns for one
listed project.

PinCheck = {state, pinned, source, mismatched_runs, total_runs, model, effort}
  state            one of STATES, or None when there is nothing to check
  pinned           "both", "model_only", "effort_only" or "none"
  source           "agent_file" or "settings" (the Main session)
  mismatched_runs  n, runs that differ from the pin on a setting whose state is
                   differs or mixed. A run that equals the pin never counts.
  total_runs       m, all runs
  model, effort    a Setting, or None when the file does not pin that setting

Setting = {state, pinned, expected, cap, ran, runs_match_pin}
  pinned    {value, file, line, status, id}; id is the pin's catalog id for a
            model alias or dated name, else the value as written
  runs_match_pin  True when the pin lost (state overridden) or won and is
            Lowered (state matches) and every run still equals the pin;
            False otherwise
  expected  {value, status, becomes, key, file, line, layer, via, reason,
            rule_id}
  cap       {key, value, model, file, line} when expected is Lowered, else None.
            file and line are None when no maxEffortLevel entry won for that
            model in the entries.
  ran       distinct values the runs showed, most common first
  state is cannot_check only when the expected value is Unknown. When the
  expected value is known but no run recorded a value, state is None and the
  setting adds nothing to the agent's state, like a setting with no pin.

Agent with no file in the folders read, and "@unnamed": the result is None. An
agent file that pins neither setting gives a PinCheck whose state is None and
whose pinned is "none".
"""
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import resolve  # noqa: E402

MATCHES = "matches"
MATCHES_LOWERED = "matches_lowered"
OVERRIDDEN = "overridden"
DIFFERS = "differs"
MIXED = "mixed"
CANNOT_CHECK = "cannot_check"

# Worst first. A confirmed mismatch beats not knowing, and not knowing beats a
# clean match.
STATES = (DIFFERS, MIXED, OVERRIDDEN, CANNOT_CHECK, MATCHES_LOWERED, MATCHES)

UNNAMED = "@unnamed"
MAIN = "@main"

_WON = ("in_effect", "default", "lowered")
_WINNER = _WON + ("unknown",)
_MAIN_KEYS = {"model": "model", "effort": "effortLevel"}
_ENTRY_FIELDS = ("value", "status", "becomes", "key", "file", "line", "layer",
                 "via", "reason", "rule_id")


def worst(states):
    """The worst of some states, ignoring None. None when none are left."""
    found = [s for s in states if s is not None]
    if not found:
        return None
    return min(found, key=STATES.index)


def checker(entries, catalog):
    """Return the pin_fn that usage.build_views calls for a single project."""
    def pin_fn(agent_key, ran_with, runs):
        return check_agent(entries, agent_key, ran_with, runs, catalog)
    return pin_fn


def check_agent(entries, agent_key, ran_with, runs, catalog):
    """Return the PinCheck for one agent key, or None when there is no pin."""
    if agent_key == UNNAMED:
        return None
    runs = list(runs or ())
    if agent_key == MAIN:
        rows = {kind: _main_row(entries, key) for kind, key in _MAIN_KEYS.items()}
        source = "settings"
    else:
        rows = _agent_rows(entries, agent_key)
        source = "agent_file"
        if rows is None:
            return None
    return _build(entries, rows, runs, catalog, source, agent_key == MAIN)


# ---------------------------------------------------------------- entries

def _winner(rows):
    for entry in rows:
        if entry.get("status") in _WINNER:
            return entry
    return None


def _main_row(entries, key):
    """(pin, winner) for a Main session row, or None when the row has no winner."""
    rows = [e for e in entries if e.get("scope") == "main" and e.get("key") == key]
    win = _winner(rows)
    if win is None:
        return None
    return win, win


def _agent_rows(entries, name):
    """{"model": (pin, winner) or None, "effort": ...} or None for no file."""
    mine = [e for e in entries if e.get("scope") == "agent" and e.get("agent") == name]
    has_file = any(e.get("key") == "agentFile" for e in mine)
    out = {}
    for kind in ("model", "effort"):
        rows = [e for e in mine if e.get("key") == kind]
        pins = [e for e in rows if e.get("layer") == "agent"]
        if pins:
            win = _winner(rows)
            pin = win if win is not None and win.get("layer") == "agent" else pins[0]
            out[kind] = (pin, win)
        else:
            out[kind] = None
    if not has_file and out["model"] is None and out["effort"] is None:
        return None
    return out


# ---------------------------------------------------------------- one setting

def _model_key(value, catalog):
    """The catalog id of a model name, else the name itself."""
    found = resolve.normalize_model(value, catalog)[0] if isinstance(value, str) else None
    return found if found is not None else value


def _expected_value(win):
    if win is None:
        return None
    if win.get("status") == "unknown":
        return None
    if win.get("status") == "lowered":
        return win.get("becomes")
    return win.get("value")


def _cap(entries, win):
    model = win.get("model")
    value = win.get("becomes")
    file = line = None
    for entry in entries:
        if (entry.get("key") == "maxEffortLevel" and entry.get("scope") == "main"
                and entry.get("status") == "in_effect" and entry.get("model") == model):
            file, line = entry.get("file"), entry.get("line")
            break
    return {"key": "maxEffortLevel", "value": value, "model": model, "file": file, "line": line}


def _ranked(values):
    """Distinct values, most common first, ties in first-seen order."""
    counts = collections.Counter(values)
    seen = list(dict.fromkeys(values))
    return sorted(seen, key=lambda v: -counts[v])


def _setting(entries, row, kind, runs, catalog):
    """Work out one setting. Returns (Setting, run values keyed for comparison, expected key)."""
    pin, win = row
    norm = (lambda v: _model_key(v, catalog)) if kind == "model" else (lambda v: v)
    raw_values = [r.get(kind) for r in runs]
    values = [norm(v) for v in raw_values if v is not None]
    expected = _expected_value(win)
    expected_key = norm(expected) if expected is not None else None
    pin_key = norm(pin.get("value"))
    at_pin = all(v == pin_key for v in values)
    setting = {
        "state": None,
        "pinned": {"value": pin.get("value"), "file": pin.get("file"),
                   "line": pin.get("line"), "status": pin.get("status"), "id": pin_key},
        "expected": ({f: win.get(f) for f in _ENTRY_FIELDS} if win is not None
                     else {f: None for f in _ENTRY_FIELDS}),
        "cap": _cap(entries, win) if win is not None and win.get("status") == "lowered" else None,
        "ran": _ranked([v for v in raw_values if v is not None]),
        "runs_match_pin": False,
    }
    if not runs:
        return setting, values, expected_key
    if expected_key is None:
        setting["state"] = CANNOT_CHECK
    elif not values:
        pass  # a known expected value and no recorded run value: nothing to check
    elif pin is not win and at_pin:
        setting["state"] = OVERRIDDEN
        setting["runs_match_pin"] = True
    elif pin is win and win.get("status") == "lowered" and at_pin:
        setting["state"] = MATCHES
        setting["runs_match_pin"] = True
    elif all(v == expected_key for v in values):
        if pin is win:
            setting["state"] = MATCHES_LOWERED if win.get("status") == "lowered" else MATCHES
        else:
            setting["state"] = OVERRIDDEN
    elif len(set(values)) > 1:
        setting["state"] = MIXED
    else:
        setting["state"] = DIFFERS
    return setting, values, expected_key


# ---------------------------------------------------------------- one agent

def _build(entries, rows, runs, catalog, source, is_main):
    present = [k for k in ("model", "effort") if rows[k] is not None]
    pinned = {("model", "effort"): "both", ("model",): "model_only",
              ("effort",): "effort_only", (): "none"}[tuple(present)]
    out = {"state": None, "pinned": pinned, "source": source,
           "mismatched_runs": 0, "total_runs": len(runs), "model": None, "effort": None}
    mismatched = [False] * len(runs)
    for kind in present:
        setting, _values, _expected_key = _setting(entries, rows[kind], kind, runs, catalog)
        out[kind] = setting
        if setting["state"] not in (DIFFERS, MIXED):
            continue
        norm = (lambda v: _model_key(v, catalog)) if kind == "model" else (lambda v: v)
        pin_key = setting["pinned"]["id"]
        for i, run in enumerate(runs):
            value = run.get(kind)
            if value is not None and norm(value) != pin_key:
                mismatched[i] = True
    out["mismatched_runs"] = sum(mismatched)
    out["state"] = worst(out[k]["state"] for k in present)
    return out
