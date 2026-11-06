#!/usr/bin/env python3
"""Probe how the routing-dashboard plugin keeps a model from running its launcher, in Claude Code.

Run it from the repo root, after a Claude Code upgrade:

    python3 tools/skill_probe/probe.py

It starts `claude -p --input-format stream-json` three times (once per variant), five user turns in
one process each, against scriptapi.py, a scripted fake API on 127.0.0.1, in a throwaway HOME,
CLAUDE_CONFIG_DIR and project. No real API call is made. It prints a pass or fail table for seven
checks, for three variants of the plugin:

    bare     the old skill with `disallowed-tools: Bash` (informational)
    narrow   the old skill with `disallowed-tools: Bash(python3 *bin/routing-dashboard*)`
             (informational)
    shipped  what the plugin ships now: no disallowed-tools, and a PreToolUse hook that runs the
             launcher's hidden guard action. The probe plugin's hooks/hooks.json holds the
             PreToolUse list of plugins/routing-dashboard/hooks/hooks.json, copied verbatim at run
             time, and its fake launcher hands the call `guard` to the shipped launcher, so the
             real guard and the real hook entry are under test.

The seventh check runs two slash commands back to back (a second skill, seq, with the same front
matter and ! line as the first). The fake launcher appends each call's arguments to launch.log,
and the check reads that file. The old deny rules let the first command run and refuse the second;
the shipped form runs both.

The exit code is 0 when every check of the shipped variant passes (or it was not run), 1 when one
fails, and 2 when the probe could not run or refused to. A changed bare or narrow column prints a
note only.

A refusal counts as "hook" only when its error text holds the shipped launcher's GUARD_REASON
(read from plugins/routing-dashboard/bin/routing-dashboard). Any other PreToolUse error is
"hook-error", a hook that crashed or printed something else, and it fails the shipped column.

Options:
    --root DIR     work under DIR (it must not exist or must be empty) and keep it
    --keep         keep the throwaway root of a passing run too
    --variant V    bare, narrow, shipped or all (default all)
    --bypass       start claude with `--permission-mode bypassPermissions`. Only with
                   `--variant shipped` (exit 2 otherwise). The shipped expectations stay the same,
                   so a pass shows the hook still refuses the launcher when no permission prompt
                   or allow rule is in play
    -v             print what each command did, not only the table
"""
import argparse
import importlib.machinery
import importlib.util
import json
import os
import pwd
import shutil
import socket
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True  # importing runcase.py must not leave a __pycache__ in the harness folder

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HARNESS = os.path.join(REPO, "dashboard", "experiments", "harness", "runcase.py")
SHIPPED_SKILL = os.path.join(REPO, "plugins", "routing-dashboard", "skills", "dashboard", "SKILL.md")
SHIPPED_HOOKS = os.path.join(REPO, "plugins", "routing-dashboard", "hooks", "hooks.json")
SHIPPED_LAUNCHER = os.path.join(REPO, "plugins", "routing-dashboard", "bin", "routing-dashboard")

BARE_DENY = "Bash"
NARROW_DENY = "Bash(python3 *bin/routing-dashboard*)"
SHIPPED_RULE = "Bash(python3 *bin/routing-dashboard*)"
VARIANTS = ("bare", "narrow", "shipped")
ALLOW = 'Bash(python3 "${CLAUDE_PLUGIN_ROOT}/bin/routing-dashboard" *)'
BANG = ('python3 "${CLAUDE_PLUGIN_ROOT}/bin/routing-dashboard" --data "${CLAUDE_PLUGIN_DATA}" '
        '--default-project "${CLAUDE_PROJECT_DIR}" --session "${CLAUDE_SESSION_ID}" $ARGUMENTS')
USER_SETTINGS = {"permissions": {"allow": ["Bash(echo *)"]}}

# The five turns. Turn 1 starts a background agent (bgb) before the skill. Turn 2 invokes the
# skill: the main session runs echo and the launcher, a foreground agent does the same, and a
# background agent (bgin) is started inside the turn. The two holds keep the turn open for 8
# seconds each, so the background agents' calls land inside it. Turn 3 is the next user message.
# Turns 4 and 5 are two more slash commands, each of a second skill (seq), back to back.
TURN1 = "TAG=t1 PLAN=bash,bgagent:bgb:wk~bash+wk~L.edits.bgduring+ws~L.status.bgafter+wt3~bash+text,text"
SKILL_PLAN = ("hold,L.edits.model,L.status.model,agent:fgsame:bash+L.stop.sub+text,"
              "bgagent:bgin:bash+L.edits.bgin+text,hold,text")
TURN3 = "TAG=t3 PLAN=bash,L.status.t3,text"
INVOKE = "/pp:dash edits"
SEQ_PLAN = "text"
SEQ_FIRST = "reload"
SEQ_SECOND = "stop"
TURN4 = "/pp:seq " + SEQ_FIRST
TURN5 = "/pp:seq " + SEQ_SECOND
# Commands the fake API logs a result for before turn 3 is sent.
WAIT_BEFORE_T3 = ["echo bgb-0", "edits bgduring", "echo bgin-0", "edits bgin", "status bgafter"]
WAIT_AFTER_T3 = ["echo bgb-3"]

# Where each command runs. in_turn commands must have finished before the skill turn ended,
# or the result says nothing about the turn.
COMMANDS = {
    "main_echo": ("echo t2-0", True),
    "main_edits": ("edits model", True),
    "main_status": ("status model", True),
    "fg_echo": ("echo fgsame-0", True),
    "fg_stop": ("stop sub", True),
    "bgin_echo": ("echo bgin-0", True),
    "bgin_edits": ("edits bgin", True),
    "bgb_echo": ("echo bgb-0", True),
    "bgb_edits": ("edits bgduring", True),
    "bgb_after": ("status bgafter", False),
    "bgb_echo3": ("echo bgb-3", False),
    "next_echo": ("echo t3-0", False),
    "next_launch": ("status t3", False),
}

# The two outcomes of the back-to-back check, read from launch.log: the last word of a launcher
# call that reached the fake launcher.
SEQ_KEYS = {"seq_first": SEQ_FIRST, "seq_second": SEQ_SECOND}

# The seven checks, in table order: (name, commands it reads).
CHECKS = [
    ("the ! line runs", []),
    ("main session later in the turn", ["main_echo", "main_edits", "main_status"]),
    ("foreground subagent in the turn", ["fg_echo", "fg_stop"]),
    ("background agent in the turn", ["bgin_echo", "bgin_edits"]),
    ("background agent started before the skill", ["bgb_echo", "bgb_edits", "bgb_after", "bgb_echo3"]),
    ("the next turn", ["next_echo", "next_launch"]),
    ("back-to-back slash commands", ["seq_first", "seq_second"]),
]

# What each command does, per variant, as a tuple of accepted outcomes.
#   ran          the command ran.
#   denied       the skill's deny rule refused it.
#   unavailable  the subagent was not given the Bash tool at all.
#   approval     no rule refused it, but -p mode has no one to approve it (the launcher has no
#                allow rule outside the skill's turn), so it did not run either.
#   hook         the plugin's PreToolUse guard hook refused it, with the launcher's GUARD_REASON.
#   hook-error   a PreToolUse hook failed in some other way (never expected, so it fails a check).
# For the seq keys, "ran" means the launcher call reached the fake launcher, and "denied" that it did not.
# Recorded on Claude Code 2.1.302. After the skill's turn, "denied" and "approval" both mean the
# launcher did not run. When the skill also starts a background agent, a background agent started
# before the skill is still denied after the turn ends, until the next user message (three runs
# out of three). Without that second agent the same call got "approval". The probe accepts both.
NOT_RUN = ("denied", "approval")
EXPECTED = {
    "narrow": {
        "launch": ("yes",),
        "main_echo": ("ran",), "main_edits": ("denied",), "main_status": ("denied",),
        "fg_echo": ("ran",), "fg_stop": ("denied",),
        "bgin_echo": ("ran",), "bgin_edits": ("denied",),
        "bgb_echo": ("ran",), "bgb_edits": ("denied",), "bgb_after": NOT_RUN, "bgb_echo3": ("ran",),
        "next_echo": ("ran",), "next_launch": ("approval",),
        "seq_first": ("ran",), "seq_second": ("denied",),
    },
    # The bare form, kept for comparison. It blocks all Bash in the turn, takes the Bash tool away
    # from subagents, and blocks the earlier background agent after the turn too.
    "bare": {
        "launch": ("yes",),
        "main_echo": ("denied",), "main_edits": ("denied",), "main_status": ("denied",),
        "fg_echo": ("unavailable",), "fg_stop": ("unavailable",),
        "bgin_echo": ("unavailable",), "bgin_edits": ("unavailable",),
        "bgb_echo": ("denied",), "bgb_edits": ("denied",), "bgb_after": ("denied",), "bgb_echo3": ("ran",),
        "next_echo": ("ran",), "next_launch": ("approval",),
        "seq_first": ("ran",), "seq_second": ("denied",),
    },
    # What the plugin ships: no deny rule on the skill, and a PreToolUse hook that denies a model's
    # launcher call. Observed on Claude Code 2.1.302. The hook never fires for a skill's ! line, so
    # every launch works, and it fires for every model, subagent and background-agent call.
    "shipped": {
        "launch": ("yes",),
        "main_echo": ("ran",), "main_edits": ("hook",), "main_status": ("hook",),
        "fg_echo": ("ran",), "fg_stop": ("hook",),
        "bgin_echo": ("ran",), "bgin_edits": ("hook",),
        "bgb_echo": ("ran",), "bgb_edits": ("hook",), "bgb_after": ("hook",), "bgb_echo3": ("ran",),
        "next_echo": ("ran",), "next_launch": ("hook",),
        "seq_first": ("ran",), "seq_second": ("ran",),
    },
}
VARIANT_DENY = {"bare": BARE_DENY, "narrow": NARROW_DENY, "shipped": None}


class Refused(Exception):
    """The probe will not run, or could not run. main() prints it and exits 2."""


def load_harness():
    """The settings harness's runcase.py, for its fixed values and its caller-environment rules."""
    spec = importlib.util.spec_from_file_location("runcase_for_skill_probe", HARNESS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def real_path(path):
    return os.path.realpath(os.path.expanduser(path))


def real_homes(env=None):
    """Every folder that could be the real home: the account's, $HOME and ~."""
    env = os.environ if env is None else env
    found = set()
    try:
        found.add(real_path(pwd.getpwuid(os.getuid()).pw_dir))
    except (KeyError, OSError):
        pass
    for path in (env.get("HOME"), "~"):
        if path:
            found.add(real_path(path))
    return found


def real_config_dirs(env=None):
    """Every folder that could be the real Claude config: ~/.claude of each real home, and the
    caller's CLAUDE_CONFIG_DIR."""
    env = os.environ if env is None else env
    found = {os.path.join(h, ".claude") for h in real_homes(env)}
    if env.get("CLAUDE_CONFIG_DIR"):
        found.add(real_path(env["CLAUDE_CONFIG_DIR"]))
    return found


def is_inside(path, folder):
    """True when path is folder or lies under it."""
    path, folder = real_path(path), real_path(folder)
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def check_isolated(home, cfg, env=None):
    """Refuse when HOME or CLAUDE_CONFIG_DIR would be, or sit inside, the real ones. A throwaway
    home may sit inside the real home's folder tree (a --root under ~), but never be it, and
    nothing may sit inside a real ~/.claude."""
    homes, cfgs = real_homes(env), real_config_dirs(env)
    if real_path(home) in homes:
        raise Refused("HOME would be the real home (%s)" % real_path(home))
    if real_path(cfg) in homes:
        raise Refused("CLAUDE_CONFIG_DIR would be the real home (%s)" % real_path(cfg))
    for label, path in (("HOME", home), ("CLAUDE_CONFIG_DIR", cfg)):
        for real in cfgs:
            if is_inside(path, real) or is_inside(real, path):
                raise Refused("%s would be or overlap the real Claude config (%s)" % (label, real))


def check_caller_env(harness, env=None):
    env = os.environ if env is None else env
    for name in harness.CALLER_FORBIDDEN:
        if env.get(name):
            raise Refused("%s is set in your shell; unset it first" % name)


def check_root(root, env=None):
    """The root must be new or empty, and neither a real home nor inside a real ~/.claude."""
    if real_path(root) in real_homes(env):
        raise Refused("--root is the real home")
    for real in real_config_dirs(env):
        if is_inside(root, real):
            raise Refused("--root is inside the real Claude config (%s)" % real)
    if os.path.exists(root) and (not os.path.isdir(root) or os.listdir(root)):
        raise Refused("--root %s exists and is not an empty folder" % root)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


def launch_log(root):
    """Where the fake launcher of the run under root records its calls."""
    return os.path.join(root, "launch.log")


def fake_launcher(log_path):
    """The probe plugin's bin/routing-dashboard. A call appends its arguments to log_path as one JSON
    line and prints LAUNCH. The call `guard` is handed to the shipped launcher, so the shipped guard
    and the shipped hooks.json entry are what the shipped variant tests."""
    return ("import json, os, sys\n"
            "if sys.argv[1:] == ['guard']:\n"
            "    os.execv(sys.executable, [sys.executable, %r, 'guard'])\n"
            "with open(%r, 'a') as fh:\n"
            "    fh.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "print('LAUNCH ' + ' '.join(sys.argv[1:]))\n" % (SHIPPED_LAUNCHER, log_path))


def skill_text(name, description, deny, body):
    """A skill like the shipped one: the same grant and ! line, and a deny rule only when deny is set."""
    rule = "disallowed-tools: %s\n" % deny if deny else ""
    return ("---\nname: %s\ndescription: %s\ndisable-model-invocation: true\nmodel: haiku\n%s"
            "allowed-tools: %s\n---\n!`%s`\n\n%s\n" % (name, description, rule, ALLOW, BANG, body))


def shipped_pretooluse():
    """The PreToolUse list of the shipped hooks.json, read now."""
    try:
        with open(SHIPPED_HOOKS) as fh:
            groups = json.load(fh)["hooks"]["PreToolUse"]
    except (OSError, ValueError, KeyError, TypeError):
        raise Refused("%s has no readable hooks.PreToolUse list" % SHIPPED_HOOKS)
    if not isinstance(groups, list) or not groups:
        raise Refused("%s has no readable hooks.PreToolUse list" % SHIPPED_HOOKS)
    return groups


def build_tree(root, variant):
    """Lay out one throwaway run: home, config, project and a plugin with two skills (dash and seq).

    The shipped variant has no deny rule and a hooks/hooks.json that carries the shipped PreToolUse list."""
    deny = VARIANT_DENY[variant]
    home, cfg, proj, plug = (os.path.join(root, d) for d in ("home", "cfg", "proj", "plug"))
    os.makedirs(home)
    write(os.path.join(cfg, "settings.json"), json.dumps(USER_SETTINGS))
    os.makedirs(proj)
    write(os.path.join(plug, ".claude-plugin", "plugin.json"),
          json.dumps({"name": "pp", "version": "0.0.1", "description": "probe"}))
    write(os.path.join(plug, "bin", "routing-dashboard"), fake_launcher(launch_log(root)))
    write(os.path.join(plug, "skills", "dash", "SKILL.md"),
          skill_text("dash", "probe dashboard", deny, "SKILLMARK TAG=t2 PLAN=%s" % SKILL_PLAN))
    write(os.path.join(plug, "skills", "seq", "SKILL.md"),
          skill_text("seq", "probe sequence", deny, "SEQMARK TAG=t4 PLAN=%s" % SEQ_PLAN))
    if variant == "shipped":
        write(os.path.join(plug, "hooks", "hooks.json"),
              json.dumps({"hooks": {"PreToolUse": shipped_pretooluse()}}, indent=2) + "\n")
    return home, cfg, proj, plug


def child_env(harness, home, cfg, port):
    env = harness.pass_through()
    env.update({"HOME": home, "CLAUDE_CONFIG_DIR": cfg, "ANTHROPIC_API_KEY": harness.FAKE_KEY,
                "ANTHROPIC_BASE_URL": "http://%s:%d" % (harness.HOST, port),
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL": "1",
                "DISABLE_AUTOUPDATER": "1",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"})
    return env


def claude_version(harness, claude, root):
    """`claude --version`, run in the same closed environment as the probe. It sends no request."""
    home, cfg = os.path.join(root, "version-home"), os.path.join(root, "version-cfg")
    os.makedirs(home)
    os.makedirs(cfg)
    env = child_env(harness, home, cfg, 9)
    check_isolated(env["HOME"], env["CLAUDE_CONFIG_DIR"])
    try:
        done = subprocess.run([claude, "--version"], cwd=home, env=env, capture_output=True, text=True,
                              timeout=30, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return "(version unknown)"
    return done.stdout.strip() or "(version unknown)"


def read_log(path):
    rows = []
    if os.path.exists(path):
        with open(path) as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    return rows


def read_launches(path):
    """The argument lists the fake launcher recorded, one per call, oldest first."""
    found = []
    if os.path.exists(path):
        with open(path) as fh:
            for line in fh:
                try:
                    argv = json.loads(line)
                except ValueError:
                    continue
                if isinstance(argv, list):
                    found.append([str(a) for a in argv])
    return found


def claude_command(claude, plug, bypass=False):
    """The argument list that starts one probe session. bypass adds --permission-mode bypassPermissions."""
    cmd = [claude, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--plugin-dir", plug]
    if bypass:
        cmd += ["--permission-mode", "bypassPermissions"]
    return cmd


def run_variant(harness, claude, name, root, bypass=False):
    """Run the five turns for one variant and return (the fake API's log rows, the fake launcher's calls)."""
    home, cfg, proj, plug = build_tree(root, name)
    port = free_port()
    # The guard runs on the final values, right before anything starts.
    env = child_env(harness, home, cfg, port)
    check_isolated(env["HOME"], env["CLAUDE_CONFIG_DIR"])
    log = os.path.join(root, "api.log")
    srv_env = dict(harness.pass_through(), PLUGROOT=plug)
    srv = subprocess.Popen([sys.executable, os.path.join(HERE, "scriptapi.py"), str(port), log], env=srv_env)
    err = open(os.path.join(root, "stderr.txt"), "w")
    out = open(os.path.join(root, "stdout.jsonl"), "w")
    p = None
    try:
        time.sleep(0.5)
        p = subprocess.Popen(claude_command(claude, plug, bypass), cwd=proj, env=env, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=err, text=True, bufsize=1)

        def send(text):
            p.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n")
            p.stdin.flush()

        def until_result(label):
            deadline = time.time() + 90
            while time.time() < deadline:
                line = p.stdout.readline()
                if not line:
                    break
                out.write(line)
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("type") == "result":
                    return
            raise Refused("%s: %s did not finish (see %s)" % (name, label, root))

        def logged(cmds, secs):
            deadline = time.time() + secs
            while time.time() < deadline:
                seen = {r["cmd"] for r in read_log(log) if r.get("ev") == "result"}
                if all(any(s.endswith(c) for s in seen) for c in cmds):
                    return
                time.sleep(0.5)
            raise Refused("%s: the agents did not make their calls %s (see %s)" % (name, cmds, root))

        send(TURN1)
        until_result("turn 1")
        send(INVOKE)
        until_result("turn 2 (the skill)")
        logged(WAIT_BEFORE_T3, 45)
        send(TURN3)
        until_result("turn 3")
        logged(WAIT_AFTER_T3, 45)
        send(TURN4)
        until_result("turn 4 (the first seq command)")
        send(TURN5)
        until_result("turn 5 (the second seq command)")
        time.sleep(1)
    finally:
        if p is not None:
            try:
                p.stdin.close()
                p.wait(20)
            except Exception:
                p.kill()
        srv.terminate()
        srv.wait()
        out.close()
        err.close()
    return read_log(log), read_launches(launch_log(root))


_GUARD_REASON = []


def guard_reason():
    """GUARD_REASON of the shipped launcher, read from its source. Nothing in it runs but its definitions."""
    if not _GUARD_REASON:
        try:
            loader = importlib.machinery.SourceFileLoader("shipped_launcher_for_probe", SHIPPED_LAUNCHER)
            spec = importlib.util.spec_from_loader(loader.name, loader)
            mod = importlib.util.module_from_spec(spec)
            loader.exec_module(mod)
            reason = mod.GUARD_REASON
        except (OSError, SyntaxError, AttributeError, ImportError):
            raise Refused("%s has no readable GUARD_REASON" % SHIPPED_LAUNCHER)
        if not isinstance(reason, str) or not reason:
            raise Refused("%s has no readable GUARD_REASON" % SHIPPED_LAUNCHER)
        _GUARD_REASON.append(reason)
    return _GUARD_REASON[0]


def classify(row):
    text = str(row.get("content") or "")
    if not row.get("is_error"):
        return "ran"
    if "PreToolUse" in text:
        return "hook" if guard_reason() in text else "hook-error"
    if "requires approval" in text:
        return "approval"
    if "No such tool available" in text:
        return "unavailable"
    if "denied" in text or "Permission to use" in text:
        return "denied"
    return "error"


def observe(rows, launches=()):
    """Reduce the log to {key: outcome}, plus "launch": whether the ! line's output reached the model.

    launches is the fake launcher's calls (read_launches). seq_first and seq_second are "ran" when a call
    ended with that command's word, else "denied". An in-turn command is judged against the first end of
    the skill's turn, so the later turns do not loosen it."""
    ended = [r["t"] for r in rows if r.get("ev") == "skill_turn_end"]
    turn_end = min(ended) if ended else None
    launched = any(r.get("ev") == "req" and r.get("skill") and r.get("launch") for r in rows)
    seen = {"launch": "yes" if launched else "no"}
    results = [r for r in rows if r.get("ev") == "result"]
    for key, (suffix, in_turn) in COMMANDS.items():
        hits = [r for r in results if r["cmd"].endswith(suffix)]
        if not hits:
            seen[key] = "missing"
        elif in_turn and (turn_end is None or hits[0]["t"] > turn_end):
            seen[key] = "late"
        else:
            seen[key] = classify(hits[0])
    for key, word in SEQ_KEYS.items():
        seen[key] = "ran" if any(argv and argv[-1] == word for argv in launches) else "denied"
    return seen


def judge(variant, seen):
    """Per check: (name, passed, [(key, expected, seen) that differ])."""
    want = EXPECTED[variant]
    table = []
    for name, keys in CHECKS:
        keys = keys or ["launch"]
        diff = [(k, "/".join(want[k]), seen[k]) for k in keys if seen[k] not in want[k]]
        table.append((name, not diff, diff))
    return table


def shipped_note():
    """Whether the shipped skill has no disallowed-tools line and the shipped hook's `if` is the probed rule."""
    try:
        with open(SHIPPED_SKILL) as fh:
            head = fh.read().split("---")[1]
    except (OSError, IndexError):
        return "shipped skill: not found, so the shipped variant was not compared with it"
    rules = [l.split(":", 1)[1].strip() for l in head.splitlines() if l.startswith("disallowed-tools:")]
    skill = ("shipped skill: no disallowed-tools line" if not rules
             else "shipped skill: still has disallowed-tools %s, which the shipped variant does not probe" % rules)
    try:
        ifs = [h.get("if") for g in shipped_pretooluse() for h in g.get("hooks", [])]
    except (Refused, AttributeError):
        return skill + "\nshipped hooks.json: no readable PreToolUse hook"
    if ifs == [SHIPPED_RULE]:
        hook = "shipped hooks.json: its PreToolUse `if` is the probed rule"
    else:
        hook = "shipped hooks.json: its PreToolUse `if` is %s, not the probed rule" % (ifs or "missing")
    return skill + "\n" + hook


def print_table(variants, verdicts, verbose, seens):
    width = max(len(name) for name, _ in CHECKS)
    print(("%-*s  %s" % (width, "check", "  ".join("%-7s" % v for v in variants))).rstrip())
    for i, (name, _) in enumerate(CHECKS):
        cells = ["%-7s" % ("PASS" if verdicts[v][i][1] else "FAIL") for v in variants]
        print(("%-*s  %s" % (width, name, "  ".join(cells))).rstrip())
    for v in variants:
        for name, passed, diff in verdicts[v]:
            for key, want, got in diff:
                print("  %s / %s: %s expected %s, saw %s" % (v, name, key, want, got))
        if verbose:
            print("  %s saw: %s" % (v, json.dumps(seens[v], sort_keys=True)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Probe how the routing-dashboard plugin guards its launcher, "
                                             "against a fake API.")
    ap.add_argument("--root", help="work under this folder (new or empty) and keep it")
    ap.add_argument("--keep", action="store_true", help="keep the throwaway root of a passing run")
    ap.add_argument("--variant", choices=VARIANTS + ("all",), default="all")
    ap.add_argument("--bypass", action="store_true",
                    help="start claude with --permission-mode bypassPermissions (only with --variant shipped)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    try:
        return run(args)
    except Refused as exc:
        sys.stderr.write("skill probe: %s\n" % exc)
        return 2


def run(args):
    if args.bypass and args.variant != "shipped":
        raise Refused("--bypass works only with --variant shipped (give --variant shipped with it)")
    harness = load_harness()
    check_caller_env(harness)
    if args.root:
        check_root(args.root)
    claude = shutil.which("claude")
    if not claude:
        raise Refused("claude is not on PATH")
    variants = list(VARIANTS) if args.variant == "all" else [args.variant]
    if args.root:
        root, own = os.path.abspath(args.root), False
    else:
        root, own = tempfile.mkdtemp(prefix="skill-probe-", dir=os.environ.get("TMPDIR")), True
    verdicts, seens = {}, {}
    try:
        version = claude_version(harness, claude, root)
        for v in variants:
            run_root = os.path.join(root, v)
            os.makedirs(run_root)
            rows, launches = run_variant(harness, claude, v, run_root, bypass=args.bypass)
            seens[v] = observe(rows, launches)
            verdicts[v] = judge(v, seens[v])
    except BaseException:
        sys.stderr.write("skill probe: files kept in %s\n" % root)
        raise
    print("claude %s" % version + (" (permission mode bypassPermissions)" if args.bypass else ""))
    print_table(variants, verdicts, args.verbose, seens)
    print(shipped_note())
    shipped_ok = "shipped" not in verdicts or all(p for _, p, _ in verdicts["shipped"])
    for v in ("bare", "narrow"):
        if v in verdicts and not all(p for _, p, _ in verdicts[v]):
            print("note: the %s form no longer behaves as recorded. That is informational." % v)
    keep = args.keep or not own or not shipped_ok
    if keep:
        print("files: %s" % root)
    else:
        shutil.rmtree(root, True)
    if not shipped_ok:
        print("FAIL: the shipped guard hook no longer behaves as recorded")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
