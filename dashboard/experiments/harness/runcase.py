"""Run one settings case in a throwaway HOME, CLAUDE_CONFIG_DIR and project.

Usage: runcase.py <case.json> <port>

case.json: {"name": ..., "user": {...}, "project": {...}, "local": {...},
            "cli_settings": {...}, "env": {...}, "args": [...],
            "agents": {"<name>": "<agent file text>"}, "agent_input": {...}}

Claude Code only ever talks to fakeapi.py on 127.0.0.1, with a fake key. The
script refuses to run when the caller's shell sets ANTHROPIC_API_KEY,
ANTHROPIC_AUTH_TOKEN or ANTHROPIC_BASE_URL. A case may set only the env names on
ENV_ALLOWLIST, and no settings file may set hooks, statusLine, apiKeyHelper, the
AWS and OTEL helper keys, forceLoginMethod or any key with "mcp" in its name. Every
refusal happens before a folder is made or any process starts. Claude Code and
fakeapi.py get only PATH, TMPDIR and LANG from the caller's environment.
Prints one JSON line: the init model and what the fake API got.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

FAKE_KEY = "sk-ant-fake-000"
HOST = "127.0.0.1"
ARG_ALLOWLIST = ("--model", "--effort", "--autocompact")
CALLER_FORBIDDEN = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")
# The only env names a case, or a settings file's env block, may set.
ENV_ALLOWLIST = frozenset((
    "ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_MODEL", "CLAUDE_CODE_EFFORT_LEVEL",
    "CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE",
    "CLAUDE_CODE_PROMPT_CACHE_TTL", "CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL",
    "ENABLE_PROMPT_CACHING_1H", "FORCE_PROMPT_CACHING_5M", "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
))
# The only variables passed on from the caller's environment.
CALLER_PASSTHROUGH = ("PATH", "TMPDIR", "LANG")
SETTINGS_FORBIDDEN_KEYS = ("hooks", "statusLine", "apiKeyHelper", "awsAuthRefresh",
                           "awsCredentialExport", "otelHeadersHelper", "forceLoginMethod")
FILE_LAYERS = ("user", "project", "local", "cli_settings")


def refuse(msg):
    sys.stderr.write("runcase refused: %s\n" % msg)
    sys.exit(2)


def check_env(where, env):
    if env is None:
        return
    if not isinstance(env, dict):
        refuse("%s env is not an object" % where)
    for name, value in env.items():
        if name not in ENV_ALLOWLIST:
            refuse("%s sets %s, which is not on the env allowlist" % (where, name))
        if not isinstance(value, str):
            refuse("%s sets %s to a value that is not a string" % (where, name))


def frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    out = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        out.append(line)
    return "\n".join(out)


def check_case(case):
    if not isinstance(case, dict):
        refuse("case is not an object")
    check_env("case env", case.get("env"))
    for layer in FILE_LAYERS:
        data = case.get(layer)
        if data is None:
            continue
        if not isinstance(data, dict):
            refuse("%s settings are not an object" % layer)
        for key in data:
            if key in SETTINGS_FORBIDDEN_KEYS or "mcp" in str(key).lower():
                refuse("%s settings set %s" % (layer, key))
        check_env("%s settings env block" % layer, data.get("env"))
    args = case.get("args") or []
    if not isinstance(args, list):
        refuse("case args are not a list")
    for arg in args:
        low = str(arg).lower()
        if "http" in low:
            refuse("case args contain a URL")
        if "mcp" in low:
            refuse("case args contain mcp (%s)" % arg)
    # Allowlist: only these session flags, each with one value. The harness adds
    # -p, --output-format, --verbose and its own --settings file itself.
    if len(args) % 2:
        refuse("case args must be flag and value pairs")
    for flag, value in zip(args[0::2], args[1::2]):
        if flag not in ARG_ALLOWLIST:
            refuse("case args use %s, which is not on the args allowlist" % flag)
        if not isinstance(value, str) or value.startswith("-"):
            refuse("case args give %s no value" % flag)
    agents = case.get("agents") or {}
    if not isinstance(agents, dict):
        refuse("case agents are not an object")
    for name, text in agents.items():
        if not name or "/" in name or "\\" in name or name.startswith("."):
            refuse("agent name %r is not a plain file name" % name)
        head = frontmatter(str(text))
        for bad in ("hooks:", "mcpServers"):
            if bad in head:
                refuse("agent %s frontmatter contains %s" % (name, bad))


def pass_through():
    return {k: os.environ[k] for k in CALLER_PASSTHROUGH if k in os.environ}


def main():
    for name in CALLER_FORBIDDEN:
        if os.environ.get(name):
            refuse("%s is set in your shell; unset it first" % name)
    case = json.load(open(sys.argv[1]))
    port = int(sys.argv[2])
    check_case(case)

    root = tempfile.mkdtemp(prefix="mr-exp-", dir=os.environ.get("TMPDIR"))
    home, cfg, proj = (os.path.join(root, d) for d in ("home", "config", "project"))
    for d in (home, cfg, os.path.join(proj, ".claude")):
        os.makedirs(d)

    def put(path, data):
        if data is not None:
            with open(path, "w") as fh:
                json.dump(data, fh)

    put(os.path.join(cfg, "settings.json"), case.get("user"))
    put(os.path.join(proj, ".claude", "settings.json"), case.get("project"))
    put(os.path.join(proj, ".claude", "settings.local.json"), case.get("local"))
    for name, text in (case.get("agents") or {}).items():
        os.makedirs(os.path.join(cfg, "agents"), exist_ok=True)
        with open(os.path.join(cfg, "agents", name + ".md"), "w") as fh:
            fh.write(text)
    args = ["claude", "-p", "say hi", "--output-format", "stream-json", "--verbose"]
    if case.get("cli_settings") is not None:
        path = os.path.join(root, "cli-settings.json")
        put(path, case["cli_settings"])
        args += ["--settings", path]
    args += case.get("args", [])

    log = os.path.join(root, "api.log")
    env = pass_through()
    env.update(case.get("env") or {})
    # Set last, so nothing above can replace them.
    env.update({"HOME": home, "CLAUDE_CONFIG_DIR": cfg, "ANTHROPIC_API_KEY": FAKE_KEY,
                "ANTHROPIC_BASE_URL": "http://%s:%d" % (HOST, port),
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL": "1",
                "DISABLE_AUTOUPDATER": "1"})

    senv = pass_through()
    if case.get("agent_input"):
        senv["AGENT_INPUT"] = json.dumps(case["agent_input"])
    here = os.path.dirname(os.path.abspath(__file__))
    srv = subprocess.Popen([sys.executable, os.path.join(here, "fakeapi.py"), str(port), log], env=senv)
    time.sleep(0.5)
    try:
        r = subprocess.run(args, cwd=proj, env=env, capture_output=True, text=True,
                           timeout=90, stdin=subprocess.DEVNULL)
    finally:
        srv.terminate()
        srv.wait()

    init = None
    for line in r.stdout.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") == "system" and o.get("subtype") == "init":
            init = o
    reqs = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    msgs = [q for q in reqs if "/messages" in (q["path"] or "") and "count_tokens" not in q["path"]]
    seen = []
    for q in msgs:
        k = (q["who"], q["model"], q["effort"], tuple(q["cache_ttls"]))
        if k not in seen:
            seen.append(k)
    print(json.dumps({"case": case.get("name"), "init_model": init and init.get("model"),
                      "sent": [list(k) for k in seen], "stderr": r.stderr[-200:].strip()}))
    shutil.rmtree(root, True)


if __name__ == "__main__":
    main()
