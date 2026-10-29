"""Run one settings case in a throwaway HOME, CLAUDE_CONFIG_DIR and project.

Usage: runcase.py <case.json> <port>

case.json: {"name": ..., "user": {...}, "project": {...}, "local": {...},
            "cli_settings": {...}, "env": {...}, "args": [...],
            "agents": {"<name>": "<agent file text>"}, "agent_input": {...},
            "prompt": "say hi", "text_reply": false}

prompt is optional and must be exactly one of PROMPT_ALLOWLIST ("say hi", the
default, or "/effort status"); it is the -p argument. text_reply is optional and
must be a bool. When true, fakeapi.py answers every request it does not serve as
the Agent tool call with a 200 text reply instead of a 400, so the session
finishes a turn. TEXT_REPLY goes into fakeapi.py's environment only, never
Claude Code's.

Claude Code only ever talks to fakeapi.py on 127.0.0.1, with a fake key. The
script refuses to run when the caller's shell sets ANTHROPIC_API_KEY,
ANTHROPIC_AUTH_TOKEN or ANTHROPIC_BASE_URL. A case may set only the env names on
ENV_ALLOWLIST, and no settings file may set hooks, statusLine, apiKeyHelper, the
AWS and OTEL helper keys, forceLoginMethod or any key with "mcp" in its name. Every
refusal happens before a folder is made or any process starts. Claude Code and
fakeapi.py get only PATH, TMPDIR and LANG from the caller's environment.
Prints one JSON line: the init model and what the fake API got ("sent"), plus
"transcript" and "result". "transcript" lists [who, kind, effort, perTurnEffort]
rows read from every *.jsonl under the config dir's projects/ folder before the
throwaway root is removed: kind "assistant" rows carry the row's effort and
perTurnEffort, kind "api-request" rows carry params.output_config.effort and None.
who is "subagent" when the file path contains "/subagents/", else "main". Rows are
deduplicated in first-seen order. "result" lists the text of the stream-json
"result" rows, each cut to 200 characters.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

FAKE_KEY = "sk-ant-fake-000"
HOST = "127.0.0.1"
ARG_ALLOWLIST = ("--model", "--effort", "--autocompact")
# The only prompts a case may send. Both are harmless: no tool runs, no network.
PROMPT_ALLOWLIST = ("say hi", "/effort status")
DEFAULT_PROMPT = "say hi"
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
# Keys no settings file may set, compared in lower case. Every layer in FILE_LAYERS is
# checked, the user file and the --settings file included.
SETTINGS_FORBIDDEN_KEYS = ("hooks", "statusLine", "apiKeyHelper", "awsAuthRefresh",
                           "awsCredentialExport", "otelHeadersHelper", "forceLoginMethod",
                           "fileSuggestion", "subagentStatusLine", "gcpAuthRefresh",
                           "extraKnownMarketplaces", "enabledPlugins", "agent")
FORBIDDEN_KEYS_LOWER = frozenset(k.lower() for k in SETTINGS_FORBIDDEN_KEYS)
FILE_LAYERS = ("user", "project", "local", "cli_settings")
# Agent frontmatter keys a case may not set, compared in lower case. initialPrompt
# would get around the prompt allowlist.
AGENT_FORBIDDEN_KEYS = ("hooks", "mcpservers", "initialprompt")
# The only keys of agent_input, each with a string value. fakeapi.py sends it as the
# Agent tool call, so anything else (isolation, run_in_background) would change what runs.
AGENT_INPUT_KEYS = ("description", "prompt", "subagent_type", "model")
# The only effort values read_transcript keeps.
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
CLAUDE_TIMEOUT = 90


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
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    out = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        out.append(line)
    return "\n".join(out)


_KEY_AT_LINE_START = re.compile(r"^\s*(?:-\s+)?[{,\s]*[\"']?([^\s\"':,{}]+)[\"']?\s*:")
_KEY_IN_FLOW = re.compile(r"[{,]\s*[\"']?([^\s\"':,{}]+)[\"']?\s*:")


def frontmatter_keys(head):
    """Return the mapping keys named anywhere in the frontmatter text.

    Reads a key at the start of a line, plain or quoted, with any indent and any
    space before the colon, plus keys inside a one-line flow mapping. It over-reports
    (a nested key counts) so the guard only ever refuses more.
    """
    keys = set()
    for line in head.splitlines():
        m = _KEY_AT_LINE_START.match(line)
        if m:
            keys.add(m.group(1))
        keys.update(_KEY_IN_FLOW.findall(line))
    return keys


def check_case(case):
    if not isinstance(case, dict):
        refuse("case is not an object")
    check_env("case env", case.get("env"))
    prompt = case.get("prompt", DEFAULT_PROMPT)
    if not isinstance(prompt, str) or prompt not in PROMPT_ALLOWLIST:
        refuse("case prompt is not on the prompt allowlist")
    if "text_reply" in case and not isinstance(case["text_reply"], bool):
        refuse("case text_reply is not a bool")
    for layer in FILE_LAYERS:
        data = case.get(layer)
        if data is None:
            continue
        if not isinstance(data, dict):
            refuse("%s settings are not an object" % layer)
        for key in data:
            if str(key).lower() in FORBIDDEN_KEYS_LOWER or "mcp" in str(key).lower():
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
        if not isinstance(text, str):
            refuse("agent %s text is not a string" % name)
        for key in sorted(frontmatter_keys(frontmatter(text))):
            if key.lower() in AGENT_FORBIDDEN_KEYS:
                refuse("agent %s frontmatter sets %s" % (name, key))
    agent_input = case.get("agent_input")
    if agent_input is not None:
        if not isinstance(agent_input, dict):
            refuse("case agent_input is not an object")
        for key, value in agent_input.items():
            if key not in AGENT_INPUT_KEYS:
                refuse("agent_input sets %s, which is not on the agent_input allowlist" % key)
            if not isinstance(value, str):
                refuse("agent_input sets %s to a value that is not a string" % key)


def clean_effort(value):
    """Keep an effort value only if it is None or one of EFFORT_LEVELS; else None."""
    if value is None or (isinstance(value, str) and value in EFFORT_LEVELS):
        return value
    return None


def read_transcript(cfg):
    """Return the deduplicated [who, kind, effort, perTurnEffort] rows from the config dir."""
    rows = []
    projects = os.path.join(cfg, "projects")
    for dirpath, _dirs, files in sorted(os.walk(projects)):
        for fname in sorted(files):
            if not fname.endswith(".jsonl"):
                continue
            path = os.path.join(dirpath, fname)
            who = "subagent" if "/subagents/" in path.replace(os.sep, "/") else "main"
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    lines = fh.read().splitlines()
            except OSError:
                continue
            for line in lines:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict):
                    continue
                if row.get("type") == "assistant":
                    item = [who, "assistant", clean_effort(row.get("effort")),
                            clean_effort(row.get("perTurnEffort"))]
                elif row.get("type") == "api-request":
                    params = row.get("params")
                    out = params.get("output_config") if isinstance(params, dict) else None
                    effort = out.get("effort") if isinstance(out, dict) else None
                    item = [who, "api-request", clean_effort(effort), None]
                else:
                    continue
                if item not in rows:
                    rows.append(item)
    return rows


def pass_through():
    return {k: os.environ[k] for k in CALLER_PASSTHROUGH if k in os.environ}


def main():
    for name in CALLER_FORBIDDEN:
        if os.environ.get(name):
            refuse("%s is set in your shell; unset it first" % name)
    with open(sys.argv[1]) as fh:
        case = json.load(fh)
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
    args = ["claude", "-p", case.get("prompt", DEFAULT_PROMPT), "--output-format", "stream-json", "--verbose"]
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
    if case.get("text_reply"):
        senv["TEXT_REPLY"] = "1"
    here = os.path.dirname(os.path.abspath(__file__))
    srv = subprocess.Popen([sys.executable, os.path.join(here, "fakeapi.py"), str(port), log], env=senv)
    time.sleep(0.5)
    try:
        r = subprocess.run(args, cwd=proj, env=env, capture_output=True, text=True,
                           timeout=CLAUDE_TIMEOUT, stdin=subprocess.DEVNULL)
    except BaseException:
        # A timeout, or any other failure, still removes the throwaway root.
        shutil.rmtree(root, True)
        raise
    finally:
        srv.terminate()
        srv.wait()

    init = None
    results = []
    for line in r.stdout.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if not isinstance(o, dict):
            continue
        if o.get("type") == "system" and o.get("subtype") == "init":
            init = o
        elif o.get("type") == "result":
            if isinstance(o.get("result"), str):
                results.append(o["result"][:200])
    reqs = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    msgs = [q for q in reqs if "/messages" in (q["path"] or "") and "count_tokens" not in q["path"]]
    seen = []
    for q in msgs:
        k = (q["who"], q["model"], q["effort"], tuple(q["cache_ttls"]))
        if k not in seen:
            seen.append(k)
    print(json.dumps({"case": case.get("name"), "init_model": init and init.get("model"),
                      "sent": [list(k) for k in seen], "stderr": r.stderr[-200:].strip(),
                      "transcript": read_transcript(cfg), "result": results}))
    shutil.rmtree(root, True)


if __name__ == "__main__":
    main()
