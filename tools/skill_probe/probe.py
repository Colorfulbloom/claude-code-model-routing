#!/usr/bin/env python3
"""Probe how a skill's disallowed-tools rule reaches the main session, subagents and
background agents in Claude Code.

Run it from the repo root, after a Claude Code upgrade:

    python3 tools/skill_probe/probe.py

It starts `claude -p --input-format stream-json` three times per variant (three user turns in one
process) against scriptapi.py, a scripted fake API on 127.0.0.1, in a throwaway HOME,
CLAUDE_CONFIG_DIR and project. No real API call is made. It prints a pass or fail table for six
checks, once for the bare `disallowed-tools: Bash` and once for the narrowed
`Bash(python3 *bin/routing-dashboard*)` pattern that the routing-dashboard skill ships. The exit
code is 0 when the narrowed pattern behaves as recorded, 1 when it does not, and 2 when the
probe could not run or refused to.

Options:
    --root DIR     work under DIR (it must not exist or must be empty) and keep it
    --keep         keep the throwaway root of a passing run too
    --variant V    bare, narrow or both (default both)
    -v             print what each command did, not only the table
"""
import argparse
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

BARE_DENY = "Bash"
NARROW_DENY = "Bash(python3 *bin/routing-dashboard*)"
ALLOW = 'Bash(python3 "${CLAUDE_PLUGIN_ROOT}/bin/routing-dashboard" *)'
BANG = ('python3 "${CLAUDE_PLUGIN_ROOT}/bin/routing-dashboard" --data "${CLAUDE_PLUGIN_DATA}" '
        '--default-project "${CLAUDE_PROJECT_DIR}" --session "${CLAUDE_SESSION_ID}" $ARGUMENTS')
USER_SETTINGS = {"permissions": {"allow": ["Bash(echo *)"]}}

# The three turns. Turn 1 starts a background agent (bgb) before the skill. Turn 2 invokes the
# skill: the main session runs echo and the launcher, a foreground agent does the same, and a
# background agent (bgin) is started inside the turn. The two holds keep the turn open for 8
# seconds each, so the background agents' calls land inside it. Turn 3 is the next user message.
TURN1 = "TAG=t1 PLAN=bash,bgagent:bgb:wk~bash+wk~L.edits.bgduring+ws~L.status.bgafter+wt3~bash+text,text"
SKILL_PLAN = ("hold,L.edits.model,L.status.model,agent:fgsame:bash+L.stop.sub+text,"
              "bgagent:bgin:bash+L.edits.bgin+text,hold,text")
TURN3 = "TAG=t3 PLAN=bash,L.status.t3,text"
INVOKE = "/pp:dash edits"
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

# The six checks, in table order: (name, commands it reads).
CHECKS = [
    ("the ! line runs", []),
    ("main session later in the turn", ["main_echo", "main_edits", "main_status"]),
    ("foreground subagent in the turn", ["fg_echo", "fg_stop"]),
    ("background agent in the turn", ["bgin_echo", "bgin_edits"]),
    ("background agent started before the skill", ["bgb_echo", "bgb_edits", "bgb_after", "bgb_echo3"]),
    ("the next turn", ["next_echo", "next_launch"]),
]

# What each command does, per variant, as a tuple of accepted outcomes.
#   ran          the command ran.
#   denied       the skill's deny rule refused it.
#   unavailable  the subagent was not given the Bash tool at all.
#   approval     no rule refused it, but -p mode has no one to approve it (the launcher has no
#                allow rule outside the skill's turn), so it did not run either.
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
    },
}
VARIANT_DENY = {"bare": BARE_DENY, "narrow": NARROW_DENY}


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


def build_tree(root, deny):
    """Lay out one throwaway run: home, config, project and a plugin with one skill."""
    home, cfg, proj, plug = (os.path.join(root, d) for d in ("home", "cfg", "proj", "plug"))
    os.makedirs(home)
    write(os.path.join(cfg, "settings.json"), json.dumps(USER_SETTINGS))
    os.makedirs(proj)
    write(os.path.join(plug, ".claude-plugin", "plugin.json"),
          json.dumps({"name": "pp", "version": "0.0.1", "description": "probe"}))
    write(os.path.join(plug, "bin", "routing-dashboard"),
          "import sys\nprint('LAUNCH ' + ' '.join(sys.argv[1:]))\n")
    write(os.path.join(plug, "skills", "dash", "SKILL.md"),
          "---\nname: dash\ndescription: probe dashboard\ndisable-model-invocation: true\n"
          "model: haiku\ndisallowed-tools: %s\nallowed-tools: %s\n---\n!`%s`\n\n"
          "SKILLMARK TAG=t2 PLAN=%s\n" % (deny, ALLOW, BANG, SKILL_PLAN))
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


def run_variant(harness, claude, name, root):
    """Run the three turns for one variant and return the fake API's log rows."""
    home, cfg, proj, plug = build_tree(root, VARIANT_DENY[name])
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
        p = subprocess.Popen([claude, "-p", "--input-format", "stream-json", "--output-format", "stream-json",
                              "--verbose", "--plugin-dir", plug], cwd=proj, env=env, stdin=subprocess.PIPE,
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
    return read_log(log)


def classify(row):
    text = str(row.get("content") or "")
    if not row.get("is_error"):
        return "ran"
    if "requires approval" in text:
        return "approval"
    if "No such tool available" in text:
        return "unavailable"
    if "denied" in text or "Permission to use" in text:
        return "denied"
    return "error"


def observe(rows):
    """Reduce the log to {key: outcome}, plus "launch": whether the ! line's output reached the model."""
    ended = [r["t"] for r in rows if r.get("ev") == "skill_turn_end"]
    turn_end = max(ended) if ended else None
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
    try:
        with open(SHIPPED_SKILL) as fh:
            head = fh.read().split("---")[1]
    except (OSError, IndexError):
        return "shipped skill: not found, so the narrowed pattern was not compared with it"
    rule = [l.split(":", 1)[1].strip() for l in head.splitlines() if l.startswith("disallowed-tools:")]
    if rule == [NARROW_DENY]:
        return "shipped skill: its disallowed-tools matches the narrowed pattern"
    return "shipped skill: its disallowed-tools is %s, not the narrowed pattern probed here" % (rule or "missing")


def print_table(variants, verdicts, verbose, seens):
    width = max(len(name) for name, _ in CHECKS)
    print(("%-*s  %s" % (width, "check", "  ".join("%-6s" % v for v in variants))).rstrip())
    for i, (name, _) in enumerate(CHECKS):
        cells = ["%-6s" % ("PASS" if verdicts[v][i][1] else "FAIL") for v in variants]
        print(("%-*s  %s" % (width, name, "  ".join(cells))).rstrip())
    for v in variants:
        for name, passed, diff in verdicts[v]:
            for key, want, got in diff:
                print("  %s / %s: %s expected %s, saw %s" % (v, name, key, want, got))
        if verbose:
            print("  %s saw: %s" % (v, json.dumps(seens[v], sort_keys=True)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Probe a skill's disallowed-tools rule against a fake API.")
    ap.add_argument("--root", help="work under this folder (new or empty) and keep it")
    ap.add_argument("--keep", action="store_true", help="keep the throwaway root of a passing run")
    ap.add_argument("--variant", choices=("bare", "narrow", "both"), default="both")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    try:
        return run(args)
    except Refused as exc:
        sys.stderr.write("skill probe: %s\n" % exc)
        return 2


def run(args):
    harness = load_harness()
    check_caller_env(harness)
    if args.root:
        check_root(args.root)
    claude = shutil.which("claude")
    if not claude:
        raise Refused("claude is not on PATH")
    variants = ["bare", "narrow"] if args.variant == "both" else [args.variant]
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
            seens[v] = observe(run_variant(harness, claude, v, run_root))
            verdicts[v] = judge(v, seens[v])
    except BaseException:
        sys.stderr.write("skill probe: files kept in %s\n" % root)
        raise
    print("claude %s" % version)
    print_table(variants, verdicts, args.verbose, seens)
    print(shipped_note())
    narrow_ok = "narrow" not in verdicts or all(p for _, p, _ in verdicts["narrow"])
    bare_ok = "bare" not in verdicts or all(p for _, p, _ in verdicts["bare"])
    if not bare_ok:
        print("note: the bare form no longer behaves as recorded. That is informational.")
    keep = args.keep or not own or not narrow_ok
    if keep:
        print("files: %s" % root)
    else:
        shutil.rmtree(root, True)
    if not narrow_ok:
        print("FAIL: the narrowed pattern no longer behaves as recorded")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
