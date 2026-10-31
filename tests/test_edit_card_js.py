"""Runs the browser-free checks of the Change effort card in tests/js/edit_card_checks.mjs with Node.

A first step builds real answers of the edit routes in temp folders, with the World class of
tests/test_api_edit.py: the targets, the previews, the save, the undo and the history, plus the settings
payloads they come with. They go into a temp folder named by MR_PAYLOADS, one JSON file per scenario, so the
checks run on the shapes the server really sends. Bodies a real run can't reach, such as unverified, are
written by hand in the checks. No browser starts, no socket opens, and every folder and value is made up.
The test skips when node is not installed, and it tries the --experimental-default-type=module flag like
tests/test_shell_js.py does.

Two more tests read the card's source. One fails if edit_card.js holds a call that parses text as markup.
The other fails if a class the card uses is missing from app.css.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import helpers

import test_api_edit as tae

TESTS = Path(__file__).resolve().parent
STATIC = Path(helpers.REPO) / "dashboard" / "static"
CARD = STATIC / "js" / "edit_card.js"
CSS = STATIC / "app.css"
CHECKS = TESTS / "js" / "edit_card_checks.mjs"
NODE = shutil.which("node")
FLAG = "--experimental-default-type=module"
SONNET = tae.SONNET


def node_flags():
    probe = subprocess.run([NODE, FLAG, "-e", "0"], capture_output=True, text=True, timeout=60)
    return [FLAG] if probe.returncode == 0 else []


def settings_of(world):
    listing = tae.projects.load(world.ctx)
    return tae.api_settings.answer(world.ctx, listing, listing.find(world.key))


def target(world, layer):
    return tae.target_of(world.targets(), layer)["target"]


def preview(world, tgt, value):
    status, body = world.preview(tgt, value)
    assert status == 200, (status, body)
    return body


def state_of(world):
    """The three things the page holds for a project, as the routes answer them now."""
    return {"settings": settings_of(world), "targets": world.targets(), "history": world.history()}


def write_json(folder, name, data):
    with open(os.path.join(folder, name + ".json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def build_all(case, folder):
    """Builds the payload files. World needs a TestCase for its cleanup, so the test passes itself in."""
    for step in (base, levels_cases, warnings, undo_cases, ledger, stale):
        step(case, folder)


# A project at low, a known model: every level but the current one is reachable.
def base(case, folder):
    world = tae.World(case, user={"model": SONNET}, project={"effortLevel": "low"})
    tgt = target(world, "project")
    out = {"start": state_of(world), "target": tgt,
           "previews": {level: preview(world, tgt, level) for level in ("low", "medium", "high", "xhigh")}}
    status, saved = world.save(out["previews"]["high"], tgt, "high")
    assert status == 200, saved
    out["save"] = saved
    out["after_save"] = state_of(world)
    status, undone = world.undo(saved["edit"]["id"])
    assert status == 200, undone
    out["undo"] = undone
    out["after_undo"] = state_of(world)
    write_json(folder, "base", out)


def levels_cases(case, folder):
    cases = {
        "nomodel_cap": dict(user={"maxEffortLevel": "low"}, project={"effortLevel": "low"}),
        "managed_cap": dict(user={"model": SONNET}, project={"effortLevel": "low"},
                            managed={"maxEffortLevel": "medium"}),
        "shell": dict(user={"model": SONNET}, project={"effortLevel": "low"},
                      shell_env={"CLAUDE_CODE_EFFORT_LEVEL": "high"}),
        "model_limit": dict(user={"model": "claude-opus-4-6"}, project={"effortLevel": "low"}),
        "haiku": dict(user={"model": "claude-haiku-4-5"}, project={"effortLevel": "low"}),
        "user_unknown": dict(user={"effortLevel": "low"}),
        "nomodel_project": dict(project={"effortLevel": "low"}),
    }
    for name, kwargs in cases.items():
        world = tae.World(case, **kwargs)
        out = state_of(world)
        out["previews"] = {}
        if out["targets"]["levels_state"] == "no_effort_support":
            # A preview here answers 400 not_editable, and the page never asks.
            status, body = world.preview(out["targets"]["targets"][0]["target"], "high")
            assert (status, body["error"]) == (400, "not_editable"), (status, body)
            write_json(folder, name, out)
            continue
        for row in out["targets"]["targets"]:
            if row["layer"] in ("project", "user"):
                out["previews"][row["layer"]] = {level: preview(world, row["target"], level)
                                                 for level in ("medium", "high", "xhigh")}
        write_json(folder, name, out)


def warnings(case, folder):
    # A cap below the level, found by the resolver: Lowered, and the effort that runs moves.
    world = tae.World(case, user={"model": SONNET, "maxEffortLevel": "medium"},
                      project={"effortLevel": "low", "maxEffortLevel": "high"})
    tgt = target(world, "project")
    out = state_of(world)
    out["target"] = tgt
    out["previews"] = {level: preview(world, tgt, level) for level in ("medium", "xhigh")}
    write_json(folder, "lowered", out)
    # A line a higher layer overrides: the file changes and what runs doesn't.
    world = tae.World(case, user={"model": SONNET}, project={"effortLevel": "low"}, local={"effortLevel": "medium"})
    out = state_of(world)
    proj = target(world, "project")
    out["project_target"] = proj
    out["local_target"] = target(world, "local")
    out["previews"] = {"project": {level: preview(world, proj, level) for level in ("high", "xhigh")},
                       "local": {level: preview(world, out["local_target"], level) for level in ("high", "low")}}
    write_json(folder, "overridden", out)
    # The same value as the file already holds.
    world = tae.World(case, user={"model": SONNET}, project={"effortLevel": "low"})
    out = state_of(world)
    out["preview_same"] = preview(world, target(world, "project"), "low")
    write_json(folder, "no_change", out)


def undo_cases(case, folder):
    # The file changed after the save: Undo answers 409 changed_since_save.
    world = tae.World(case, user={"model": SONNET}, project={"effortLevel": "low"})
    tgt = target(world, "project")
    saved = world.edit(tgt, "high")
    world.write("project", world.read("project").replace(b'"high"', b'"high", "x": 1'))
    status, body = world.undo(saved["edit"]["id"])
    assert status == 409 and body["error"] == "changed_since_save", body
    write_json(folder, "changed_since_save", {"save": saved, "undo_answer": body, "history": world.history(),
                                              "settings": settings_of(world), "targets": world.targets()})
    # The backup was cut short: Undo answers 409 backup_damaged, and the row says so at rest.
    world = tae.World(case, user={"model": SONNET}, project={"effortLevel": "low"})
    tgt = target(world, "project")
    saved = world.edit(tgt, "high")
    with open(world.real(saved["edit"]["backup_display"]), "r+b") as fh:
        fh.truncate(3)
    status, body = world.undo(saved["edit"]["id"])
    assert status == 409 and body["error"] == "backup_damaged", body
    write_json(folder, "backup_damaged", {"save": saved, "undo_answer": body, "history": world.history(),
                                          "settings": settings_of(world), "targets": world.targets()})
    # A save, a second save, then the first row: not the newest row.
    world = tae.World(case, user={"model": SONNET}, project={"effortLevel": "low"})
    tgt = target(world, "project")
    first = world.edit(tgt, "medium")
    second = world.edit(tgt, "high")
    status, body = world.undo(first["edit"]["id"])
    assert status == 409 and body["error"] == "not_undoable", body
    write_json(folder, "not_undoable", {"first": first, "second": second, "undo_answer": body,
                                        "history": world.history(), "settings": settings_of(world),
                                        "targets": world.targets()})
    # The newest row is gone from the folder: backup_pruned at rest.
    world = tae.World(case, user={"model": SONNET}, project={"effortLevel": "low"})
    tgt = target(world, "project")
    saved = world.edit(tgt, "high")
    os.remove(world.real(saved["edit"]["backup_display"]))
    write_json(folder, "backup_pruned", {"save": saved, "history": world.history(), "settings": settings_of(world),
                                         "targets": world.targets()})


def ledger(case, folder):
    # The local file's record of saves is damaged. The project file's is not.
    world = tae.World(case, user={"model": SONNET}, project={"effortLevel": "low"}, local={"effortLevel": "low"})
    local = target(world, "local")
    proj = target(world, "project")
    world.edit(local, "medium")
    damaged = [os.path.join(d, f) for d, _x, files in os.walk(world.cfg) for f in files if f == "ledger.json"][0]
    with open(damaged, "w") as fh:
        fh.write("{not json")
    out = state_of(world)
    out["local_target"] = local
    out["project_target"] = proj
    out["previews"] = {"local": {level: preview(world, local, level) for level in ("high", "xhigh")},
                       "project": {level: preview(world, proj, level) for level in ("high",)}}
    status, body = world.save(out["previews"]["local"]["xhigh"], local, "xhigh")
    assert status == 500 and body["error"] == "ledger_damaged", body
    out["save_answer"] = body
    write_json(folder, "ledger", out)


def stale(case, folder):
    world = tae.World(case, user={"model": SONNET}, project={"effortLevel": "low"})
    tgt = target(world, "project")
    pv = preview(world, tgt, "high")
    world.write("project", world.read("project").replace(b'"low"', b'"low", "x": 1'))
    status, body = world.save(pv, tgt, "high")
    assert status == 409 and body["changed"] == "file", (status, body)
    out = {"target": tgt, "stale_file": body}
    world = tae.World(case, user={"model": SONNET}, project={"effortLevel": "low"})
    tgt = target(world, "project")
    pv = preview(world, tgt, "high")
    world.write("user", {"model": SONNET, "alwaysThinkingEnabled": True})
    status, body = world.save(pv, tgt, "high")
    assert status == 409 and body["changed"] == "trail", (status, body)
    out["stale_trail"] = body
    write_json(folder, "stale", out)


class CardScripts(unittest.TestCase):
    @unittest.skipUnless(NODE, "node is not installed")
    def test_checks_pass(self):
        folder = os.path.realpath(tempfile.mkdtemp(prefix="edit-card-js-", dir=helpers._tmp_base()))
        self.addCleanup(helpers.rmtree_force, folder)
        build_all(self, folder)
        env = dict(os.environ, MR_PAYLOADS=folder)
        run = subprocess.run([NODE] + node_flags() + [str(CHECKS)], capture_output=True, text=True,
                             timeout=300, env=env)
        report = run.stdout + run.stderr
        if run.returncode != 0:
            sys.stderr.write(report)
        self.assertEqual(run.returncode, 0, report)
        self.assertIn("checks passed", run.stdout)
        self.assertNotIn("FAIL", run.stdout)


def strip_comments(source):
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", source)


class CardSource(unittest.TestCase):
    def test_no_call_that_parses_markup(self):
        source = CARD.read_text(encoding="utf-8")
        for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "createContextualFragment",
                       "DOMParser", "eval(", "new Function"):
            self.assertNotIn(banned, source, banned)
        self.assertNotRegex(strip_comments(source), r"\.style\b|\bstyle\s*:", "the page's policy forbids a style attribute")

    def test_every_class_the_card_uses_is_in_app_css(self):
        source = strip_comments(CARD.read_text(encoding="utf-8"))
        used = set()
        for match in re.finditer(r"\bclass:\s*(\[[^\]]*\]|\"[^\"]*\"|'[^']*')", source):
            for literal in re.findall(r"\"([^\"]*)\"|'([^']*)'", match.group(1)):
                used.update((literal[0] or literal[1]).split())
        # Maps of class text, such as NT_CLASS and STRIP_CLASS, are literals outside an attribute.
        for match in re.finditer(r"(?m)^const (?:NT|STRIP)_CLASS = \{(.*?)\};", source, flags=re.S):
            for literal in re.findall(r"\"([^\"]*)\"", match.group(1)):
                used.update(literal.split())
        self.assertIn("p2-segs", used)
        self.assertIn("p2-nt-warn", used)
        css = strip_comments(CSS.read_text(encoding="utf-8"))
        defined = set(re.findall(r"\.(-?[_a-zA-Z][_a-zA-Z0-9-]*)", css))
        self.assertEqual(sorted(used - defined), [], "classes the card uses that app.css lacks")


if __name__ == "__main__":
    unittest.main()
