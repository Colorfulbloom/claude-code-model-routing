"""The edit routes: what each effort level would do, a preview and a save (set a level or remove a line), an undo and the history.

A read route is a function (ctx, query) -> (status, payload), like the routes in
api_settings. A write route is (ctx, body), where body is the parsed JSON
object the server's gate already checked. ctx.edit is an EditState when the
server started with --allow-edits, else None.

A preview or save body holds the opaque target and an action, "set" (the default, with a value)
or "remove" (no value, a line target only). No path or key name ever comes from a request.

Nothing here writes. Every write goes through edit_store.Store. The answers come
from the real resolver run over overlays (api_settings.resolved), never from a
second copy of the precedence rules. The server keeps no preview: a save
recomputes everything under the store's lock and compares it with the HMACs the
preview handed out.

Standard library only, Python 3.9.
"""
import hashlib
import hmac
import json
import os
import re

import api_settings
import collect
import edit_store
import git_check
import json_edit
import projects
import resolve
import rules_schema

MAIN_AGENT = api_settings.MAIN_AGENT
SETTING = "effortLevel"
LEVELS = ("low", "medium", "high", "xhigh")  # tests tie this to rule effort-level-settings-values
RANKS = rules_schema.EFFORT_LEVELS  # low to max, for comparing levels and caps
REPLACED_RULE = "max-effort-level-replaced-in-file"
LAYER_REASONS = {"managed": "managed", "flag": "flag", "cli": "cli", "default": "default"}
LAYER_ORDER = {"local": 0, "project": 1, "user": 2}  # the order other targets are tried in
# What a preview hashes as base_file when the settings file is not there (a create).
NO_FILE = b"\0no-file"
EFFECT_RANK = ("applies", "lowered", "unknown", "wont_apply")  # best first
_SEQ_RE = re.compile(r"^(\d{6})-")


class EditState:
    """What one --allow-edits launch holds: the token, the launch id and the store."""

    def __init__(self, token, launch_id, store):
        self.token = token
        self.launch_id = launch_id
        self.store = store

    def __repr__(self):
        return "EditState(launch_id=%r)" % (self.launch_id,)


class _Answer(Exception):
    """A finished answer, raised from deep inside a route."""

    def __init__(self, status, body):
        super().__init__(status)
        self.status = status
        self.body = body


class _StaleSignal(Exception):
    """A save found the file or the trail moved. Carries the fresh preview."""

    def __init__(self, changed, files, preview):
        super().__init__(changed)
        self.changed = changed
        self.files = files
        self.preview = preview


def edit_info(ctx, query):
    """GET /api/edit: whether edits are on, and this launch's id (None when off)."""
    state = ctx.edit
    return 200, {"enabled": state is not None,
                 "launch_id": state.launch_id if state is not None else None}


# ---------------------------------------------------------------- small helpers

def ref_of(entry):
    """Return the match key of a trail entry: agent, setting, layer, file and path, no line.

    static/js/edit_ref.js builds the same string, and tests/fixtures/edit_ref_table.json
    runs under both.
    """
    return json.dumps([entry.get("agent") or MAIN_AGENT, entry["key"], entry["layer"], entry.get("file"),
                       entry.get("path") or entry["key"]], ensure_ascii=False, separators=(",", ":"))


def _target_id(layer, key_path):
    """Return the opaque id of a layer and key path. It is compared, never decoded."""
    text = json.dumps([layer, list(key_path)])
    return "t-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _hmac(ctx, data):
    """Return the hex HMAC-SHA256 of bytes, keyed by the launch token."""
    return hmac.new(ctx.edit.token.encode("utf-8"), data, hashlib.sha256).hexdigest()


def _display(ctx, path):
    return resolve.display_path(path, home=ctx.home, root=ctx.root)


def _display_or_none(ctx, path):
    return None if path is None else _display(ctx, path)


def _key_allowed(key_path):
    """The editable table: effortLevel and modelSettings.<name>.effortLevel, nothing else."""
    key_path = tuple(key_path)
    if key_path == (SETTING,):
        return True
    return (len(key_path) == 3 and key_path[0] == "modelSettings"
            and isinstance(key_path[1], str) and key_path[2] == SETTING)


def _masked(value, name=SETTING):
    return collect.mask(value, name)


def _effort_row(entries):
    return [e for e in entries
            if e["key"] == SETTING and e.get("scope") == "main" and not e.get("agent")]


def _winner(row):
    for entry in row:
        if entry["status"] in resolve.WINNING:
            return entry
    return None


def _caps_below(entries, level):
    """Return the main maxEffortLevel entries that cap a level, lowest cap first, then entry order.

    Left out are a value that is not a level, "max" (no cap), an invalid cap, and a
    top-level cap that a same-file per-model cap replaced.
    """
    if level not in RANKS:
        return []
    rank = RANKS.index(level)
    caps = []
    for entry in entries:
        value = entry.get("value")
        if entry["key"] != "maxEffortLevel" or entry.get("scope") != "main" or entry.get("agent"):
            continue
        if not isinstance(value, str) or value not in RANKS or value == "max":
            continue
        if RANKS.index(value) >= rank or entry["status"] == "invalid":
            continue
        if REPLACED_RULE in (entry.get("rule_ids") or []):
            continue
        caps.append(entry)
    return sorted(caps, key=lambda e: RANKS.index(e["value"]))


def _runs_as(view, entries):
    """Return the level the main effort row runs at, or None when it is unknown.

    The resolver sets no "becomes" for a winner it did not lower: with no model it
    applies no cap, and a modelSettings line (key effortLevel) never gets one under a
    cap (resolve.py, _computed_becomes). So a level above a top-level cap is lowered
    here, whenever the winner has no "becomes". This is the only place that does.
    """
    winner = _winner(_effort_row(entries))
    if winner is None or winner["status"] == "unknown":
        return None
    value = winner.get("becomes", winner["value"])
    if "becomes" not in winner and isinstance(value, str) and value in LEVELS:
        caps = _caps_below(entries, value)
        if caps:
            value = caps[0]["value"]
    return value


# ---------------------------------------------------------------- one reading of a project

class _Target:
    """One value that can be edited: a line on the main effort trail, or an add (entry None).

    An add is a key the file doesn't hold yet (op insert), one that holds null (op replace), or a
    whole file that isn't there (op create, raw None).
    Its ref is built from the display path of its file, so it matches the trail entry the
    resolver shows once the line is there.
    """

    __slots__ = ("id", "ref", "layer", "key_path", "store_target", "raw", "entry", "op", "file_display")

    def __init__(self, layer, key_path, store_target, raw, entry, op="replace", file_display=None):
        self.id = _target_id(layer, key_path)
        self.layer = layer
        self.key_path = tuple(key_path)
        self.store_target = store_target
        self.raw = raw
        self.entry = entry
        self.op = op
        if entry is not None:
            self.file_display = entry.get("file")
            self.ref = ref_of(entry)
        else:
            self.file_display = file_display
            self.ref = ref_of({"key": SETTING, "layer": layer, "file": file_display,
                               "path": None if len(self.key_path) == 1 else ".".join(self.key_path)})

    @property
    def path(self):
        return self.store_target.path

    @property
    def line(self):
        return None if self.entry is None else self.entry.get("line")

    @property
    def old_value(self):
        return None if self.entry is None else self.entry.get("value")


class _View:
    """One reading of a project: its entries, the main effort row, and the targets and blocked rows."""

    def __init__(self, ctx, listing, project, overlay):
        self.ctx = ctx
        self.listing = listing
        self.project = project
        self.overlay = overlay
        self.missing = False
        self.repo_locked = False
        self.entries = []
        self.collected = None
        self.effort = []
        self.model = None
        self.offered = []
        self.levels_state = "model_unknown"
        self.runs_as = None
        self.targets = []
        self.adds = []
        self.files = []
        self.refused = {}  # (target id, level) -> the json_edit code of a simulation it refused
        self.blocked = []
        self.blocked_refs = {}
        self.blocked_ids = {}
        self.sims = {}

    def find(self, target_id):
        """Return the target or add with this id, or raise 422 (it is blocked now) or 400 not_editable."""
        for target in self.targets + self.adds:
            if target.id == target_id:
                return target
        reason = self.blocked_ids.get(target_id)
        if reason is not None:
            raise _Answer(422, {"error": reason})
        raise _Answer(400, {"error": "not_editable"})


def _layer_reason(entry):
    """Return the blocked reason of a layer that is not user, project or local, else None."""
    layer = entry["layer"]
    if layer == "env":
        return "env_file" if entry.get("line") is not None else "env_shell"
    return LAYER_REASONS.get(layer)


def _block(view, entry, reason, key_path=None):
    ref = ref_of(entry)
    if ref not in view.blocked_refs:
        view.blocked_refs[ref] = reason
        view.blocked.append({"ref": ref, "layer": entry["layer"], "file_display": entry.get("file"),
                             "line": entry.get("line"), "value": _masked(entry.get("value")),
                             "reason": reason})
    if key_path is not None:
        view.blocked_ids[_target_id(entry["layer"], key_path)] = reason


def _classify(view, entry):
    """Make the entry one target or one blocked row."""
    ctx = view.ctx
    layer = entry["layer"]
    if layer not in edit_store.LAYERS:
        _block(view, entry, _layer_reason(entry) or "not_editable")
        return
    key_path = None if entry.get("path") else (SETTING,)
    try:
        target = edit_store.target_for(ctx, view.project.key, layer)
        if view.overlay is not None and target.path in view.overlay:
            raw = view.overlay[target.path]
        else:
            raw = edit_store.read_target(target)
    except edit_store.Refused as exc:
        # The entry came from a file that has just gone, so the file is not parsed any more.
        _block(view, entry, "unparsed" if exc.code == "file_missing" else exc.code, key_path)
        return
    except OSError:
        _block(view, entry, "unparsed", key_path)
        return
    try:
        _text, data = json_edit.parse_strict(raw)
    except json_edit.Refused:
        _block(view, entry, "unparsed", key_path)
        return
    if entry.get("path"):
        key_path = None
        table = data.get("modelSettings")
        if isinstance(table, dict):
            for name in table:  # never split the path, a model id can hold dots
                if "modelSettings.%s.%s" % (name, SETTING) == entry["path"]:
                    key_path = ("modelSettings", name, SETTING)
                    break
        if key_path is None:
            _block(view, entry, "unparsed")
            return
    if not _key_allowed(key_path) or _display(ctx, target.path) != entry.get("file"):
        _block(view, entry, "unparsed", key_path)
        return
    if view.repo_locked:
        _block(view, entry, "not_repo_root", key_path)
        return
    view.targets.append(_Target(layer, key_path, target, raw, entry))


def _repo_locked(project):
    """True when the project is a repo subfolder, a worktree or a submodule: every write locks.

    Claude Code reads settings.local.json at the repo root, so a root file the dashboard
    can't see could beat any line written here. An unexpanded path is not walked.
    """
    if project.unexpanded:
        return False
    return git_check.repo_place(project.path) in ("subfolder", "linked")


def _view(ctx, listing, project, overlay=None):
    """Return the _View of one project. overlay is {path: bytes}, as for collect."""
    view = _View(ctx, listing, project, overlay)
    if project.state == projects.STATE_MISSING and not project.implicit:
        view.missing = True
        return view
    view.repo_locked = _repo_locked(project)
    view.entries, view.collected = api_settings.resolved(ctx, project, overlay=overlay, listing=listing)
    view.effort = _effort_row(view.entries)
    for entry in view.effort:
        if entry.get("model"):
            view.model = entry["model"]
            break
    for model in ctx.rules.get("models", []):
        if model["id"] == view.model:
            view.offered = list(model.get("effort_levels") or [])
    if view.model is None:
        view.levels_state = "model_unknown"
    elif not view.offered:
        view.levels_state = "no_effort_support"
    else:
        view.levels_state = "ok"
    view.runs_as = _runs_as(view, view.entries)
    for entry in view.effort:
        _classify(view, entry)
    view.files = _file_states(view)
    if ctx.edit is not None:
        view.adds = _make_adds(view)
    return view


# ---------------------------------------------------------------- limits

def _lock_reason(view, entry):
    """Return why a winner or cap can't be changed here."""
    layer = entry["layer"]
    if layer == "default":
        if view.levels_state == "no_effort_support":
            return "no_effort_support"
        return "no_key_in_file" if entry.get("value") is not None else "unknown"
    if layer not in edit_store.LAYERS:
        return _layer_reason(entry) or "unknown"
    reason = view.blocked_refs.get(ref_of(entry))
    if reason is not None:
        return reason
    return "unknown"  # a file value that came back unknown


def _limit(kind, value, layer, file_display, line, lock_reason):
    return {"kind": kind, "value": value, "layer": layer, "file_display": file_display, "line": line,
            "editable": False, "target": None, "lock_reason": lock_reason}


def _cap_limit(view, entry):
    layer = entry["layer"]
    reason = "cap_later" if layer in edit_store.LAYERS else (_layer_reason(entry) or "unknown")
    return _limit("cap", _masked(entry.get("value")), layer, entry.get("file"), entry.get("line"), reason)


def _model_limit(view, level):
    below = [lv for lv in view.offered if RANKS.index(lv) <= RANKS.index(level)]
    return _limit("model", below[-1] if below else None, None, None, None, "model")


def _model_unknown_limit():
    return _limit("model_unknown", None, None, None, None, "model_unknown")


def _winner_limit(view, entry):
    return _limit("winner", _masked(entry.get("value")), entry["layer"], entry.get("file"),
                  entry.get("line"), _lock_reason(view, entry))


def limits_for(view, level, entries):
    """Return everything in the way of a level, for the entries of a simulation or a preview.

    view is the view before the edit, so lock reasons don't change with the value.
    """
    out = [_cap_limit(view, entry) for entry in _caps_below(entries, level)]
    if view.model is not None and level not in view.offered:
        out.append(_model_limit(view, level))
    if out:
        return out
    winner = _winner(_effort_row(entries))
    if winner is not None and winner["status"] == "in_effect" and winner["value"] == level:
        return []
    if view.model is None and (winner is None or winner["status"] == "unknown"):
        return [_model_unknown_limit()]
    return [_winner_limit(view, winner)] if winner is not None else []


# ---------------------------------------------------------------- levels

def _new_raw(target, value):
    """Return the bytes of the target's file with the value set: a new file, an insert for a new key, else a replace."""
    if target.op == "create":
        return json_edit.new_file(target.key_path, value)
    if target.op == "insert":
        return json_edit.insert_value(target.raw, target.key_path, value)
    return json_edit.replace_value(target.raw, target.key_path, value)


def _removed_raw(target):
    """Return the bytes of the target's file with its line cut out. Only a line target can be removed."""
    return json_edit.remove_key(target.raw, target.key_path)


def _simulation(view, target, key, make_raw):
    """Return the entries after make_raw(target), or None when json_edit refuses it. Kept in view.sims under key."""
    if key not in view.sims:
        try:
            new_raw = make_raw()
        except json_edit.Refused as exc:
            view.refused[key] = exc.code
            view.sims[key] = None
        else:
            overlay = dict(view.overlay or {})
            overlay[target.path] = new_raw
            entries, _collected = api_settings.resolved(
                view.ctx, view.project, overlay=overlay, listing=view.listing, reuse=view.collected)
            view.sims[key] = entries
    return view.sims[key]


def _simulate(view, target, level):
    """Return the entries with the target set to level, or None when the edit is refused."""
    return _simulation(view, target, (target.id, level), lambda: _new_raw(target, level))


def _simulate_remove(view, target):
    """Return the entries with the target's line removed, or None when the removal is refused."""
    return _simulation(view, target, (target.id, "remove"), lambda: _removed_raw(target))


def _order(view, winner):
    """Targets in the order they are tried: the row's winner, then local, project, user."""
    first = [t for t in view.targets if winner is not None and t.ref == ref_of(winner)]
    rest = [t for t in view.targets if t not in first]
    rest.sort(key=lambda t: (LAYER_ORDER.get(t.layer, 3), 0 if len(t.key_path) == 3 else 1))
    return first + rest


def _file_row(layer, file_display, state, line=None, value=None, status=None, target=None, lock_reason=None):
    return {"layer": layer, "file_display": file_display, "state": state, "line": line, "value": value,
            "status": status, "target": target, "shared": layer == "project",
            "lock_reason": lock_reason}


def _modelsettings_locked(view, data):
    """True when modelSettings, or the table entry of the running model, is not an object."""
    if "modelSettings" not in data:
        return False
    table = data["modelSettings"]
    if not isinstance(table, dict):
        return True
    if view.model is None:
        return False
    catalog = view.ctx.rules.get("models", [])
    for name, item in table.items():
        if resolve.normalize_model(name, catalog)[0] == view.model and not isinstance(item, dict):
            return True
    return False


def _empty_file_row(view, layer):
    """Return the file row of a layer that has no entry on the main effort trail."""
    ctx = view.ctx
    try:
        target = edit_store.target_for(ctx, view.project.key, layer)
    except edit_store.Refused as exc:
        return _file_row(layer, None, "locked", lock_reason=exc.code)
    display = _display(ctx, target.path)
    try:
        raw = edit_store.read_target(target)
    except edit_store.Refused as exc:
        if exc.code != "file_missing":
            return _file_row(layer, display, "locked", lock_reason=exc.code)
        if not os.path.lexists(target.base):
            return _file_row(layer, display, "locked", lock_reason="file_missing")
        return _file_row(layer, display, "absent")
    except OSError:
        return _file_row(layer, display, "locked", lock_reason="unparsed")
    try:
        _text, data = json_edit.parse_strict(raw)  # for the lock reason only, never for a value
    except json_edit.Refused:
        return _file_row(layer, display, "locked", lock_reason="unparsed")
    if _modelsettings_locked(view, data):
        return _file_row(layer, display, "locked", lock_reason="parent_not_object")
    return _file_row(layer, display, "no_line")


def _file_states(view):
    """Return one row per layer (local, project, user) for the files the page can draw. Empty for a missing folder.

    A row says whether the file holds an effort line (has_line), holds none (no_line), is not
    there yet (absent) or can't be edited (locked). A value comes only from the trail, which is
    masked, never from the file itself.
    """
    if view.missing:
        return []
    by_ref = {t.ref: t for t in view.targets}
    rows = []
    for layer in sorted(edit_store.LAYERS, key=LAYER_ORDER.get):
        entries = [e for e in view.effort if e["layer"] == layer]
        found = next((e for e in entries if ref_of(e) in by_ref), None)
        if found is not None:
            rows.append(_file_row(layer, found.get("file"), "has_line", found.get("line"),
                                  _masked(found.get("value")), found["status"], by_ref[ref_of(found)].id))
        elif entries:
            first = entries[0]
            rows.append(_file_row(layer, first.get("file"), "locked", first.get("line"),
                                  _masked(first.get("value")), first["status"],
                                  lock_reason=view.blocked_refs.get(ref_of(first), "unparsed")))
        else:
            rows.append(_empty_file_row(view, layer))
    if view.repo_locked:
        for row in rows:
            row["lock_reason"] = "not_repo_root"
            row["target"] = None
    return rows


def _add_op(data, key_path):
    """Return "replace" when the key is in the parsed file (as null), else "insert".

    A parent that is not an object reads as insert: the simulation reports it.
    """
    node = data
    for step in key_path[:-1]:
        node = node.get(step) if isinstance(node, dict) else None
    return "replace" if isinstance(node, dict) and key_path[-1] in node else "insert"


def _model_name(view, data):
    """Return the modelSettings name an add uses: an existing name of the model, else the catalog id.

    With several names for the model, the best form wins (rules_schema.NAME_FORMS order).
    """
    table = data.get("modelSettings")
    if isinstance(table, dict):
        catalog = view.ctx.rules.get("models", [])
        found = []
        for name in table:
            model, form = resolve.normalize_model(name, catalog)
            if model == view.model:
                found.append((rules_schema.NAME_FORMS.index(form), name))
        if found:
            return min(found, key=lambda item: item[0])[1]
    return view.model


def _make_adds(view):
    """Return the adds: a line to put in a file that holds none, tried at the top level, then under the model.

    The file is read again from the overlay or the disk. An absent file (raw None) gives creates.
    Nothing is added to a locked row or in a repo subfolder, and a file that no longer parses gives none.
    """
    if view.repo_locked or view.missing:
        return []
    ctx = view.ctx
    out = []
    for row in view.files:
        if row["state"] not in ("no_line", "has_line", "absent") or row["lock_reason"]:
            continue
        layer = row["layer"]
        try:
            target = edit_store.target_for(ctx, view.project.key, layer)
            if view.overlay is not None and target.path in view.overlay:
                raw = view.overlay[target.path]
            else:
                raw = edit_store.read_or_none(target)
            data = {} if raw is None else json_edit.parse_strict(raw)[1]
        except (edit_store.Refused, json_edit.Refused, OSError):
            continue
        have = {t.key_path for t in view.targets if t.layer == layer}
        display = _display(ctx, target.path)
        wanted = []
        if (SETTING,) not in have:
            wanted.append((SETTING,))
        if view.model is not None and not any(len(path) == 3 for path in have):
            wanted.append(("modelSettings", _model_name(view, data), SETTING))
        for key_path in wanted:
            op = "create" if raw is None else _add_op(data, key_path)
            out.append(_Target(layer, key_path, target, raw, None, op=op, file_display=display))
    out.sort(key=lambda t: (LAYER_ORDER.get(t.layer, 3), 0 if len(t.key_path) == 1 else 1))
    return out


def _effect(view, target, level):
    """Return (effect, runs_as, lock_reason, line) of setting one target to a level, from the real resolver run.

    effect is applies, lowered, unknown or wont_apply, and None when the edit is refused or an add
    would land where the trail can't see it (not_on_trail). line is the line the trail gives the
    target after the edit.
    """
    entries = _simulate(view, target, level)
    if entries is None:
        code = view.refused.get((target.id, level))
        return None, None, ("parent_not_object" if code == "parent_not_object" else "not_editable"), None
    row = _effort_row(entries)
    mine = next((e for e in row if ref_of(e) == target.ref), None)
    if mine is None and target.entry is None:
        return None, None, "not_on_trail", None
    winner = _winner(row)
    runs = _runs_as(view, entries)
    if mine is None:
        effect = "wont_apply"
    elif mine["status"] == "unknown":
        effect = "unknown"
    elif winner is None or ref_of(winner) != target.ref:
        effect = "wont_apply"
    elif (winner["status"] == "in_effect" and winner["value"] == level
          and not limits_for(view, level, entries)):
        effect = "applies"
    else:
        effect = "lowered"
    if effect != "unknown" and runs == view.runs_as:
        effect = "wont_apply"  # a file change that leaves the level where it is today
    return effect, _masked(runs), None, None if mine is None else mine.get("line")


def _level_file(view, file_row, level, order):
    """Return the row of one file under one level.

    Every item of the order on this layer is a candidate, a line or an add. The best effect wins,
    the first on a tie, so a working replace beats an add and a top add beats a model add.
    """
    layer = file_row["layer"]
    out = {"layer": layer, "target": None, "op": None, "line": file_row["line"], "runs_as": None,
           "effect": None, "lock_reason": file_row["lock_reason"], "pickable": False}
    candidates = [target for target in order if target.layer == layer]
    if not candidates:
        if out["lock_reason"] is None:
            out["lock_reason"] = "not_editable"  # a file with no line and nothing to add
        return out
    best = None
    hidden = False
    for target in candidates:
        effect, runs, lock, line = _effect(view, target, level)
        hidden = hidden or lock == "not_on_trail"
        rank = EFFECT_RANK.index(effect) if effect is not None else len(EFFECT_RANK)
        if best is None or rank < best[0]:
            best = (rank, target, effect, runs, lock, line)
        if rank == 0:
            break
    _rank, target, effect, runs, lock, line = best
    if target.entry is not None:
        line = target.line
    out.update(target=target.id, op=target.op, line=line, runs_as=runs, effect=effect,
               lock_reason=lock, pickable=lock is None and effect in EFFECT_RANK[:3])
    if effect == "wont_apply" and file_row["line"] is None:
        # A file with no line, whose candidates can't be written (a parent that is not an object) or can't
        # be seen on the trail, says why it can't take the level, whatever the best working candidate shows.
        # A file that holds a line keeps its own label, Won't change what runs.
        if any(view.refused.get((t.id, level)) == "parent_not_object" for t in candidates):
            out.update(lock_reason="parent_not_object", pickable=False)
        elif hidden:
            out.update(lock_reason="not_on_trail", pickable=False)
    return out


def _level_row(level, result, runs_as, certain, limits, files=None, preselect=None):
    files = files or []
    return {"level": level, "result": result, "runs_as": runs_as, "certain": certain, "limits": limits,
            "files": files, "preselect": preselect, "saveable": any(row["pickable"] for row in files)}


def _preselect(files):
    """Return the local file's target when it would apply the level, else None. Never a shared file."""
    for row in files:
        if row["layer"] == "local" and row["effect"] == "applies" and row["pickable"]:
            return row["target"]
    return None


def _levels(view, file_rows):
    if view.missing or view.levels_state == "no_effort_support":
        return []
    certain = view.model is not None
    today = view.runs_as
    order = _order(view, _winner(view.effort)) + view.adds
    out = []
    for level in LEVELS:
        if level == today:
            out.append(_level_row(level, "now", level, certain, []))
            continue
        best = None
        first = None
        reached = None
        for target in order:
            entries = _simulate(view, target, level)
            if entries is None:
                continue
            if first is None:
                first = entries
            winner = _winner(_effort_row(entries))
            ours = winner is not None and ref_of(winner) == target.ref
            if ours and best is None:
                best = _runs_as(view, entries)
            if (ours and winner["status"] == "in_effect" and winner["value"] == level
                    and not limits_for(view, level, entries)):
                reached = target
                break
        files = [_level_file(view, row, level, order) for row in file_rows]
        if reached is not None:
            out.append(_level_row(level, "reachable", level, certain, [], files, _preselect(files)))
        else:
            entries = first if first is not None else view.entries
            out.append(_level_row(level, "stopped", best if best is not None else today,
                                  certain, limits_for(view, level, entries), files, _preselect(files)))
    return out


# ---------------------------------------------------------------- preview

class _Preview:
    """A preview payload, the bytes it would write and the layer of each other file."""

    def __init__(self, payload, new_raw, layers):
        self.payload = payload
        self.new_raw = new_raw
        self.layers = layers


def _others(ctx, project, edited):
    """Return ({display path: hash or marker}, {display path: layer}) for every other settings file."""
    found = []
    for layer in edit_store.LAYERS:
        if layer == edited.layer:
            continue
        try:
            found.append((layer, edit_store.target_for(ctx, project.key, layer).path))
        except edit_store.Refused:
            continue
    if ctx.managed_dir is not None:
        for path in collect._managed_paths(ctx.managed_dir)[0]:
            found.append(("managed", path))
    hashes, layers = {}, {}
    for layer, path in found:
        display = _display(ctx, path)
        raw, status = collect._read_bytes(path)
        hashes[display] = _hmac(ctx, raw) if status == "ok" else status
        layers[display] = layer
    return hashes, layers


def _first_entries(payload):
    """Return {(agent, setting): first entry of the row}, in row order."""
    return {(row["agent"], row["setting"]): payload["entries"][row["entries"][0]]
            for row in payload["rows"]}


def _side(view, key, entry, entries):
    if entry is None:
        return None
    if key == (MAIN_AGENT, SETTING):
        runs_as = _runs_as(view, entries)
    elif entry["status"] == "unknown":
        runs_as = None
    else:
        runs_as = entry.get("becomes", entry["value"])
    return {"value": _masked(entry["value"], entry["key"]), "status": entry["status"],
            "layer": entry["layer"], "file": entry.get("file"), "line": entry.get("line"),
            "runs_as": _masked(runs_as, entry["key"])}


def _changes(view, before, after):
    """Return every row where the winner, the status, the file or the run-as value moved."""
    old = _first_entries(before)
    new = _first_entries(after)
    out = []
    for key in list(old) + [k for k in new if k not in old]:
        was = _side(view, key, old.get(key), before["entries"])
        now = _side(view, key, new.get(key), after["entries"])
        if was is not None and now is not None:
            same = (all(was[f] == now[f] for f in ("layer", "value", "status", "runs_as"))
                    and old[key].get("file") == new[key].get("file")
                    and old[key].get("path") == new[key].get("path"))
            if same:
                continue
        out.append({"agent": key[0], "setting": key[1], "before": was, "after": now})
    return out


def _warning(view, edited, value, before, after):
    """Return the warning for the edited entry in the after entries, or None."""
    entries = after["entries"]
    entry = None
    for item in _effort_row(entries):
        if ref_of(item) == edited.ref:
            entry = item
            break
    if entry is None:
        if edited.entry is None:  # an add that lands where the trail can't see it
            raise _Answer(422, {"error": "not_on_trail"})
        raise _Answer(400, {"error": "not_editable"})
    limits = limits_for(view, value, entries)
    status = entry["status"]
    if status == "in_effect":
        if not limits:
            return None
    elif status == "lowered":
        limits = [limit for limit in limits if limit["kind"] in ("cap", "model")]
    else:
        winner = _winner(_effort_row(entries))
        if view.model is None and (winner is None or winner["status"] == "unknown"):
            limits = [_model_unknown_limit()]
        elif winner is None:
            limits = []
        else:
            limit = _winner_limit(view, winner)
            for target in view.targets:
                if target.ref == ref_of(winner):
                    # A file value on the table, so this one can be edited. lock_reason is null then.
                    limit.update(target=target.id, editable=True, lock_reason=None)
            limits = [limit]
    return {"status": status, "reason": entry.get("reason"), "rule_ids": list(entry.get("rule_ids") or []),
            "in_effect_changes": _runs_as(view, before["entries"]) != _runs_as(view, entries),
            "model_known": view.model is not None,
            "limits": limits}


def _base_file(ctx, raw):
    """Return the HMAC that stands for a file's bytes, or for no file when raw is None."""
    return _hmac(ctx, NO_FILE if raw is None else raw)


def _folder_missing(target):
    """True when the file's .claude folder isn't there. A refused or failed walk counts as no."""
    try:
        return edit_store.folder_missing(target)
    except (edit_store.Refused, OSError):
        return False


def _require_pickable(view, edited, value):
    """Raise unless this target at this level is a pickable file row.

    The page only sends the target of a pickable row, one whose effect is applies, lowered or unknown
    and that has no lock. A forged preview or save for a change that wouldn't apply, or for a file the
    trail can't see or the dashboard can't write into, is refused with 400 not_editable, or 422 with
    the lock (not_on_trail, parent_not_object). A value the file already holds is left to no_change,
    which writes nothing.
    """
    if _new_raw(edited, value) == edited.raw:
        return
    effect, _runs, lock, _line = _effect(view, edited, value)
    if lock in ("not_on_trail", "parent_not_object"):
        raise _Answer(422, {"error": lock})
    if lock is not None or effect not in EFFECT_RANK[:3]:
        raise _Answer(400, {"error": "not_editable"})


def _preview(ctx, view, edited, value, action="set"):
    """Return the _Preview of setting the target to value, or of removing its line. Reads, writes nothing.

    A remove has no value and no warning. no_effect says the level would not move, and last_line says
    the file would be left with nothing in it.
    """
    remove = action == "remove"
    if remove and edited.entry is None:
        raise _Answer(400, {"error": "not_editable"})
    new_raw = _removed_raw(edited) if remove else _new_raw(edited, value)
    no_change = new_raw == edited.raw  # a create has no raw, so it is never no change
    before = api_settings.answer(ctx, view.listing, view.project, overlay=view.overlay,
                                 reuse=view.collected)
    overlay = dict(view.overlay or {})
    overlay[edited.path] = new_raw
    after = api_settings.answer(ctx, view.listing, view.project, overlay=overlay, reuse=view.collected)
    warning = None if remove else _warning(view, edited, value, before, after)
    runs_before = _masked(_runs_as(view, before["entries"]))
    runs_after = _masked(_runs_as(view, after["entries"]))
    diff = json_edit.structured_diff(None if edited.raw is None else edited.raw.decode("utf-8"),
                                     new_raw.decode("utf-8"), edited.file_display)
    line = edited.line
    if line is None:  # an add: the line the trail gives it after the edit
        line = next((item.get("line") for item in _effort_row(after["entries"])
                     if ref_of(item) == edited.ref), None)
    trail = json.dumps({"before": before["entries"], "after": after["entries"]}, sort_keys=True)
    others, layers = _others(ctx, view.project, edited)
    payload = {
        "target": edited.id,
        "old_value": _masked(edited.old_value),
        "new_value": None if remove else value,
        "no_change": no_change,
        "no_effect": remove and runs_before is not None and runs_after == runs_before,
        "last_line": remove and json_edit.parse_strict(new_raw)[1] == {},
        "before": before,
        "after": after,
        "changes": _changes(view, before, after),
        "warning": warning,
        "diff": diff,
        "base_file": _base_file(ctx, edited.raw),
        "base_trail": _hmac(ctx, trail.encode("utf-8")),
        "base_others": others,
        "op": "remove" if remove else edited.op,
        "layer": edited.layer,
        "shared": edited.layer == "project",
        "line": line,
        "ref": edited.ref,
        "git_ignore": None,  # filled by _with_git, outside the store's lock
        "new_file": edited.op == "create",
        "creates_dir": edited.op == "create" and _folder_missing(edited.store_target),
        "ledger_damaged": _ledger_damaged(ctx.edit.store, edited.store_target),
        "runs_before": runs_before,
        "runs_after": runs_after,
    }
    return _Preview(payload, new_raw, layers)


# ---------------------------------------------------------------- answers

def _targets_out(view):
    winner = _winner(view.effort)
    rows = []
    for target in view.targets:
        entry = target.entry
        rows.append({
            "target": target.id,
            "ref": target.ref,
            "layer": target.layer,
            "file_display": entry.get("file"),
            "line": entry.get("line"),
            "current_value": _masked(entry.get("value")),
            "status": entry["status"],
            "shared": target.layer == "project",
            "in_effect": (winner is not None and target.ref == ref_of(winner)
                          and entry["status"] in ("in_effect", "lowered")),
            "remove": _remove_out(view, target),
        })
    return rows


def _remove_out(view, target):
    """Return what removing a target's line would do: the level it runs at after, and why it can't be removed."""
    entries = _simulate_remove(view, target)
    if entries is None:
        code = view.refused.get((target.id, "remove"))
        return {"runs_as": None, "no_effect": False,
                "lock_reason": "repeated_key" if code == "repeated_key" else "not_editable"}
    runs = _runs_as(view, entries)
    # With no level known either side, the dashboard can't say the line does nothing.
    return {"runs_as": _masked(runs), "no_effect": runs is not None and runs == view.runs_as, "lock_reason": None}


def _adds_out(view):
    """Return the adds for the page: the lines it could put in a file that holds none."""
    return [{"target": add.id, "ref": add.ref, "layer": add.layer, "file_display": add.file_display,
             "op": add.op, "shared": add.layer == "project"} for add in view.adds]


def _seq(name):
    match = _SEQ_RE.match(name) if isinstance(name, str) else None
    return int(match.group(1)) if match else 0


def _safe_rows(store, target):
    """Return the visible ledger rows of a target, or [] when the store folder can't be read."""
    try:
        return store.rows(target)
    except edit_store.StoreError:
        return []


def _ledger_damaged(store, target):
    """True when the target's ledger is damaged. A store folder that can't be read counts as no ledger."""
    try:
        return store.ledger_damaged(target)
    except edit_store.StoreError:
        return False


def _row_out(ctx, target, rows, row):
    """Return one history row: what the page shows for an edit and whether it can be undone."""
    store = ctx.edit.store
    key_path = list(row.get("key_path") or [])
    name = key_path[-1] if key_path else None
    if row.get("kind") == "undo":
        reason = "undo_row"
    elif not rows or rows[-1].get("id") != row.get("id"):
        reason = "not_newest"
    else:
        try:
            reason = store.undo_state(target, row)
        except edit_store.StoreError:
            reason = "backup_damaged"
    out = {
        "id": row.get("id"),
        "kind": row.get("kind"),
        "time": row.get("time"),
        "layer": target.layer,
        "file_display": _display(ctx, target.path),
        "op": row.get("op", "replace"),
        "key_path": key_path,
        "backup_display": _display_or_none(ctx, store.backup_path(target, row.get("backup"))),
    }
    for field in ("old_value", "new_value"):  # a null value is left out, so it never reaches the page
        if row.get(field) is not None:
            out[field] = _masked(row[field], name)
    if row.get("kind") == "undo":
        out["restored_from_display"] = _display_or_none(
            ctx, store.backup_path(target, row.get("restored_from_backup")))
    out["undoable"] = reason is None
    out["not_undoable_reason"] = reason
    return out


def _edit_out(ctx, target, row):
    """Return the history row for a row the store just returned, read with the rows as they are now."""
    rows = _safe_rows(ctx.edit.store, target)
    if not any(item.get("id") == row.get("id") for item in rows):
        rows = rows + [row]
    return _row_out(ctx, target, rows, row)


class _Request:
    """What an answer for a store exception needs to know about its request."""

    def __init__(self, ctx, listing, project, target=None, value=None, undo=False, action="set"):
        self.ctx = ctx
        self.listing = listing
        self.project = project
        self.target = target  # the first view's _Target for a save, the store Target for an undo
        self.value = value
        self.undo = undo
        self.action = action


def _store_target(req):
    """Return the edit_store Target of the request: a save holds a _Target, an undo the Target itself."""
    return req.target.store_target if isinstance(req.target, _Target) else req.target


def _with_git(ctx, project, payload):
    """Add the git-ignore result to a preview of the local file, and return it.

    It starts a child process, so a route calls it, never _preview: _preview also runs inside
    save's plan, under the store's lock. It stays out of the base hashes, because it is advice.
    """
    if payload is not None and payload.get("layer") == "local":
        payload["git_ignore"] = git_check.ignore_state(project.path, ctx.path_env, ctx.home,
                                                       ctx.shell_env.get("XDG_CONFIG_HOME"))
    return payload


def _fresh_preview(req):
    """Return the preview of the request from a new view, or None when the target is gone."""
    remove = req.action == "remove"
    if req.undo or (req.value is None and not remove):
        return None
    try:
        view = _view(req.ctx, req.listing, req.project)
        found = view.find(req.target.id)
        if remove and found.entry is None:
            return None  # the line went, so there is nothing left to remove
        return _with_git(req.ctx, req.project, _preview(req.ctx, view, found, req.value, req.action).payload)
    except (_Answer, json_edit.Refused, edit_store.StoreError):
        return None


def _store_answer(req, exc):
    """Return (status, payload) for an exception from the store, json_edit or a signal."""
    ctx = req.ctx
    if isinstance(exc, _StaleSignal):
        return 409, {"error": "stale", "changed": exc.changed, "changed_files": exc.files,
                     "preview": _with_git(ctx, req.project, exc.preview)}
    if isinstance(exc, json_edit.Refused):
        if exc.code == "oracle_failed":
            return 500, {"error": "write_failed", "file_unchanged": True}
        return 422, {"error": exc.code}
    if isinstance(exc, edit_store.Refused):
        status = {"not_editable": 400, "unknown_project": 404, "no_change": 400}.get(exc.code, 422)
        return status, {"error": exc.code}
    if isinstance(exc, edit_store.Stale):
        store_target = _store_target(req)
        files = [{"layer": store_target.layer, "file_display": _display(ctx, store_target.path)}]
        return 409, {"error": "stale", "changed": exc.changed, "changed_files": files,
                     "preview": _fresh_preview(req)}
    if isinstance(exc, edit_store.Unverified):
        return 500, {"error": "unverified", "stage": exc.stage, "file_unchanged": False,
                     "edit": _edit_out(ctx, _store_target(req), exc.row),
                     "backup_display": _display_or_none(ctx, exc.backup_path)}
    if isinstance(exc, edit_store.Raced):
        store_target = _store_target(req)
        body = {"error": "raced", "edit": _edit_out(ctx, store_target, exc.row),
                "backup_display": _display_or_none(ctx, exc.backup_path),
                "settings": api_settings.answer(ctx, req.listing, req.project)}
        if req.undo:
            body["matches_backup"] = False
            body["restored_from_display"] = _display_or_none(ctx, exc.restored_from_path)
        return 409, body
    if isinstance(exc, edit_store.ChangedSinceSave):
        return 409, {"error": "changed_since_save",
                     "backup_display": _display_or_none(ctx, exc.backup_path)}
    if isinstance(exc, edit_store.BackupDamaged):
        return 409, {"error": "backup_damaged", "backup_display": _display_or_none(ctx, exc.backup_path)}
    if isinstance(exc, edit_store.NotUndoable):
        return 409, {"error": "not_undoable", "reason": exc.reason}
    if isinstance(exc, edit_store.UnknownEdit):
        return 404, {"error": "unknown_edit"}
    if isinstance(exc, edit_store.ConfigDirMissing):
        return 500, {"error": "config_dir_missing", "file_unchanged": True,
                     "config_dir_display": _display_or_none(ctx, exc.path)}
    if isinstance(exc, edit_store.LedgerDamaged):
        return 500, {"error": "ledger_damaged", "file_unchanged": True,
                     "ledger_display": _display_or_none(ctx, exc.path)}
    body = {"error": "write_failed", "file_unchanged": True}  # WriteFailed, or a store error with no name
    if exc.dir_left:
        body["dir_left"] = True  # a save made .claude and could not take it away again
    return 500, body


_CAUGHT = (_Answer, _StaleSignal, json_edit.Refused, edit_store.StoreError)


# ---------------------------------------------------------------- request parts

def _pick(ctx, asked):
    """Return (listing, project) for the project values asked, a list of 0 or 1 str."""
    if len(asked) > 1 or not all(isinstance(value, str) for value in asked):
        raise _Answer(400, {"error": "bad_request"})
    listing = projects.load(ctx)
    if asked and asked[0] == projects.ALL_KEY:
        raise _Answer(400, {"error": "bad_request"})
    project = listing.find(asked[0] if asked else listing.current)
    if project is None:
        raise _Answer(404, {"error": "unknown_project"})
    return listing, project


def _pick_body(ctx, body):
    if not isinstance(body, dict):
        raise _Answer(400, {"error": "bad_request"})
    return _pick(ctx, [body["project"]] if "project" in body else [])


def _body_value(body):
    value = body.get("value")
    if not isinstance(value, str) or value not in LEVELS:
        raise _Answer(400, {"error": "bad_value"})
    return value


def _body_action(body):
    """Return "set" or "remove". A missing action is set, anything else is a bad request."""
    action = body.get("action", "set") if "action" in body else "set"
    if not isinstance(action, str) or action not in ("set", "remove"):
        raise _Answer(400, {"error": "bad_request"})
    return action


def _body_edit(body):
    """Return (action, value) of a preview or save body. A remove carries no value, a set needs a level."""
    action = _body_action(body)
    if action == "remove":
        if "value" in body:
            raise _Answer(400, {"error": "bad_request"})
        return action, None
    return action, _body_value(body)


def _body_target(body):
    target = body.get("target")
    if not isinstance(target, str):
        raise _Answer(400, {"error": "bad_request"})
    return target


def _editable_view(ctx, listing, project, target_id):
    """Return (view, target) for a preview or a save, or raise the answer."""
    view = _view(ctx, listing, project)
    if view.missing:
        raise _Answer(422, {"error": "file_missing"})
    if view.levels_state == "no_effort_support":
        raise _Answer(400, {"error": "not_editable"})
    try:
        return view, view.find(target_id)
    except _Answer as answer:
        # A base folder that went since the page loaded (a config folder, say) leaves no target at all.
        if answer.status == 400 and any(row["lock_reason"] == "file_missing" for row in view.files):
            raise _Answer(422, {"error": "file_missing"}) from None
        raise


# ---------------------------------------------------------------- routes

def _project_lock(view):
    return "not_repo_root" if view.repo_locked else None


def _read_only(view, project, file_rows):
    """Return the targets answer when edits are off: what runs today and which levels exist, nothing to write.

    It holds no target ids, no per-level simulation and no save flags. The only resolver pass is the one _view ran.
    """
    levels = []
    if not (view.missing or view.levels_state == "no_effort_support"):
        levels = [{"level": level, "result": "now" if level == view.runs_as else "offered"} for level in LEVELS]
    files = [{key: value for key, value in row.items() if key != "target"} for row in file_rows]
    return {"enabled": False, "project": project.key, "state": project.state,
            "agent": MAIN_AGENT, "setting": SETTING, "runs_as": view.runs_as,
            "model": view.model, "levels_state": view.levels_state,
            "project_lock": _project_lock(view), "files": files, "levels": levels}


def targets(ctx, query):
    """GET /api/edit/targets: the main effort row, what can be edited and what each level would do.

    With edits off it answers the read-only form from _read_only, for the same project checks.
    """
    try:
        listing, project = _pick(ctx, query.get("project") or [])
        view = _view(ctx, listing, project)
        files = view.files
        if ctx.edit is None:
            return 200, _read_only(view, project, files)
        levels = _levels(view, files)
        return 200, {"enabled": True, "project": project.key, "state": project.state,
                     "agent": MAIN_AGENT, "setting": SETTING, "runs_as": view.runs_as,
                     "model": view.model, "levels_state": view.levels_state,
                     "project_lock": _project_lock(view),
                     "targets": _targets_out(view), "adds": _adds_out(view),
                     "blocked": view.blocked, "files": files,
                     "levels": levels, "saveable": any(row["saveable"] for row in levels)}
    except _Answer as answer:
        return answer.status, answer.body


def preview(ctx, body):
    """POST /api/edit/preview: what setting a target to a level, or removing its line, would change. Writes nothing."""
    if ctx.edit is None:
        return 400, {"error": "not_editable"}
    try:
        listing, project = _pick_body(ctx, body)
        action, value = _body_edit(body)
        target_id = _body_target(body)
        view, edited = _editable_view(ctx, listing, project, target_id)
        if action == "set":
            _require_pickable(view, edited, value)
        return 200, _with_git(ctx, project, _preview(ctx, view, edited, value, action).payload)
    except _CAUGHT as exc:
        if isinstance(exc, _Answer):
            return exc.status, exc.body
        return _store_answer(_Request(ctx, None, None), exc)


def _stale_files(fresh, client, layers):
    """Return the files whose hash differs, or that only the fresh side holds."""
    return [{"layer": layers[display], "file_display": display}
            for display in fresh if client.get(display) != fresh[display]]


def save(ctx, body):
    """POST /api/edit/save: set a target to a level, or remove its line, backed up first. Recomputes under the lock."""
    if ctx.edit is None:
        return 400, {"error": "not_editable"}
    req = _Request(ctx, None, None)
    try:
        listing, project = _pick_body(ctx, body)
        action, value = _body_edit(body)
        target_id = _body_target(body)
        base_file, base_trail, base_others = (body.get("base_file"), body.get("base_trail"),
                                              body.get("base_others"))
        if (not isinstance(base_file, str) or not isinstance(base_trail, str)
                or not isinstance(base_others, dict)):
            raise _Answer(400, {"error": "bad_request"})
        view, edited = _editable_view(ctx, listing, project, target_id)
        if action == "remove" and edited.entry is None:
            raise _Answer(400, {"error": "not_editable"})  # an add has no line to remove
        req = _Request(ctx, listing, project, edited, value, action=action)

        def plan(raw):
            # An absent file has no bytes to overlay, so its path is left out and reads as absent.
            fresh_view = _view(ctx, listing, project, overlay={} if raw is None else {edited.path: raw})
            try:
                fresh = fresh_view.find(target_id)
            except _Answer:
                if raw is None and base_file != _base_file(ctx, None):
                    # The file went, and the target it held (an alias name, say) is not offered for a create.
                    raise _StaleSignal("file_removed", [{"layer": edited.layer, "file_display": _display(
                        ctx, edited.store_target.path)}], None) from None
                raise
            if action == "remove" and fresh.entry is None:
                # The line went since the preview: the file changed, or it is not there at all.
                raise _StaleSignal("file_removed" if raw is None else "file",
                                   [{"layer": edited.layer,
                                     "file_display": _display(ctx, edited.store_target.path)}], None)
            if action == "set":
                _require_pickable(fresh_view, fresh, value)  # the row, as the file is now, must take the level
            made = _preview(ctx, fresh_view, fresh, value, action)
            payload = made.payload
            if payload["base_file"] != base_file:
                if base_file == _base_file(ctx, None):
                    changed = "file_appeared"
                else:
                    changed = "file_removed" if raw is None else "file"
                files = [{"layer": fresh.layer, "file_display": _display(ctx, fresh.store_target.path)}]
            elif payload["base_trail"] != base_trail or payload["base_others"] != base_others:
                changed, files = "trail", _stale_files(payload["base_others"], base_others, made.layers)
            else:
                changed = None
            if changed is not None:
                raise _StaleSignal(changed, files, payload)
            if payload["no_change"]:
                raise edit_store.Refused("no_change")
            if action == "remove":
                return edit_store.Plan(made.new_raw, fresh.key_path, fresh.old_value, None, op="remove")
            return edit_store.Plan(made.new_raw, fresh.key_path, fresh.old_value, value, op=fresh.op)

        row = ctx.edit.store.save(edited.store_target, plan, allow_absent=True)
        return 200, {"edit": _edit_out(ctx, edited.store_target, row),
                     "settings": api_settings.answer(ctx, listing, project)}
    except _CAUGHT as exc:
        if isinstance(exc, _Answer):
            return exc.status, exc.body
        return _store_answer(req, exc)


def undo(ctx, body):
    """POST /api/edit/undo: put an edit's backup back, only for the newest edit row of its file."""
    if ctx.edit is None:
        return 400, {"error": "not_editable"}
    req = _Request(ctx, None, None, undo=True)
    try:
        listing, project = _pick_body(ctx, body)
        edit_id = body.get("edit")
        if not isinstance(edit_id, str):
            raise _Answer(400, {"error": "bad_request"})
        store = ctx.edit.store
        found = None
        damaged = None
        for layer in edit_store.LAYERS:
            try:
                target = edit_store.target_for(ctx, project.key, layer)
                if store.find(target, edit_id) is not None:
                    found = target
                    break
                if _ledger_damaged(store, target):
                    damaged = target
            except edit_store.StoreError:
                continue
        if found is None and damaged is not None:
            raise edit_store.LedgerDamaged(store.ledger_path(damaged))  # its rows can't be searched
        if found is None:
            raise _Answer(404, {"error": "unknown_edit"})
        req = _Request(ctx, listing, project, found, undo=True)

        def check(rows, row):
            if row.get("kind") == "undo":
                raise edit_store.NotUndoable("undo_row")
            if rows[-1].get("id") != row.get("id"):
                raise edit_store.NotUndoable("not_newest")

        restored = store.restore(found, edit_id, check)
        return 200, {"edit": _edit_out(ctx, found, restored.row),
                     "settings": api_settings.answer(ctx, listing, project),
                     "matches_backup": restored.matches_backup,
                     "restored_from_display": _display_or_none(ctx, restored.restored_from_path),
                     "removed_file": restored.removed_file, "removed_dir": restored.removed_dir}
    except _CAUGHT as exc:
        if isinstance(exc, _Answer):
            return exc.status, exc.body
        return _store_answer(req, exc)


def history(ctx, query):
    """GET /api/edit/history: the ledgers of the project's three files, newest first."""
    if ctx.edit is None:
        return 200, {"enabled": False}
    try:
        _listing, project = _pick(ctx, query.get("project") or [])
    except _Answer as answer:
        return answer.status, answer.body
    store = ctx.edit.store
    found = []
    damaged = []
    for layer in edit_store.LAYERS:
        try:
            target = edit_store.target_for(ctx, project.key, layer)
        except edit_store.Refused:
            continue
        if _ledger_damaged(store, target):
            damaged.append({"layer": layer, "file_display": _display(ctx, target.path),
                            "ledger_display": _display(ctx, store.ledger_path(target))})
        rows = _safe_rows(store, target)
        for row in rows:
            found.append((row.get("time") or "", _seq(row.get("backup")), _row_out(ctx, target, rows, row)))
    found.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return 200, {"enabled": True, "project": project.key, "rows": [item[2] for item in found],
                 "damaged_ledgers": damaged}
