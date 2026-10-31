"""Run one settings case in a throwaway HOME, CLAUDE_CONFIG_DIR and project.

Usage: runcase.py <case.json> <port>

case.json: {"name": ..., "user": {...}, "project": {...}, "local": {...},
            "cli_settings": {...}, "raw_settings": {"user": "text"}, "env": {...}, "args": [...],
            "agents": {"<name>": "<agent file text>"}, "agent_input": {...},
            "agent_files": [{"where": "user", "path": "a.md", "text": "..."}],
            "cwd": "project", "git_init": false,
            "prompt": "say hi", "text_reply": false}

prompt is optional and must be exactly one of PROMPT_ALLOWLIST ("say hi", the
default, "/effort status", or "/autocompact" with no argument); it is the -p
argument. "/autocompact" prints the window and its source and makes no API call.
text_reply is optional and
must be a bool. When true, fakeapi.py answers every request it does not serve as
the Agent tool call with a 200 text reply instead of a 400, so the session
finishes a turn. TEXT_REPLY goes into fakeapi.py's environment only, never
Claude Code's.

agent_files is optional: a list of at most 8 objects with exactly the keys "where",
"path" and "text". where is "user" (written under <config>/agents/), "project" (under
<project>/.claude/agents/) or "nested" (under <project>/sub/.claude/agents/). path is
one or two segments joined by "/", each matching SEGMENT_RE, and the last one ends in
".md" or ".md.bak". text is a string whose frontmatter gets the same check as "agents".
No two items may resolve to the same file, and none may collide with a file from "agents". cwd is optional: "project" (default) or "nested", which runs
claude in <project>/sub. git_init is optional and must be a bool. When true, `git init
-q` runs in <project> first, with only the pass-through variables, HOME set to the
throwaway home, GIT_CONFIG_NOSYSTEM=1 and GIT_CONFIG_GLOBAL=/dev/null. Claude Code gets
the same two GIT_CONFIG variables.

Agent text ("agents" values and agent_files text) goes through check_frontmatter.
It refuses any of NUL, \\v, \\f, \\r, the other C0 controls except \\n and \\t, DEL,
U+0085, U+2028 and U+2029 anywhere in the text, then splits on "\\n" only. Between the
fences, every top-level line must be blank, a comment, indented, or a plain `key:`
matching [A-Za-z][A-Za-z0-9_-]* with no quote, tag, anchor or escape. The first line
that is not blank or a comment must be a key. Braces and backslashes are refused in the
frontmatter, as is a line with a colon after an unclosed [. hooks, mcpServers and
initialPrompt are refused in any case. A text with no closing fence is not loaded by
Claude Code, so only forbidden keys and lookalike closing fences are refused in it.

raw_settings is optional: an object whose keys are a subset of "user", "project" and
"local". Each value is a string written byte for byte, with no json.dump, to the path that
layer uses, so a case can test a settings file that is not a JSON object. A layer may not
be in both raw_settings and its normal field. A value is 1 to RAW_SETTINGS_MAX characters of
printable ASCII plus "\\n", with no backslash. It may not hold, in any case, a forbidden
settings key, "mcp", "env", "helper", "plugin" or "otel" as a substring, and it may not
parse as a JSON object (use the normal field for that).

Claude Code only ever talks to fakeapi.py on 127.0.0.1, with a fake key. The
script refuses to run when the caller's shell sets ANTHROPIC_API_KEY,
ANTHROPIC_AUTH_TOKEN or ANTHROPIC_BASE_URL. A case may set only the env names on
ENV_ALLOWLIST, and no settings file may set hooks, statusLine, apiKeyHelper, the
AWS and OTEL helper keys, forceLoginMethod or any key with "mcp" in its name. Every
refusal happens before a folder is made or any process starts. Claude Code and
fakeapi.py get only PATH, TMPDIR and LANG from the caller's environment.
Prints one JSON line: the init model, "init_agents", "init_version" and what the fake API
got ("sent"), plus "transcript" and "result". "init_agents" is the "agents" list of the
stream-json init row, keeping only strings, each cut to 100 characters, or null when there
is no init row or no list. "init_version" is the init row's claude_code_version, or null
when there is no init row. "transcript" lists [who, kind, effort, perTurnEffort]
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
# The only prompts a case may send. All are harmless: no tool runs, no network.
# "/autocompact" without an argument only prints the window and its source.
PROMPT_ALLOWLIST = ("say hi", "/effort status", "/autocompact")
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
# raw_settings: the layers it may name, where each goes (relative to the throwaway root),
# its length limit, the characters a value may hold and the substrings it may not hold.
RAW_LAYERS = {"user": ("config", "settings.json"),
              "project": ("project", ".claude", "settings.json"),
              "local": ("project", ".claude", "settings.local.json")}
RAW_SETTINGS_MAX = 512
RAW_OK_CHARS = re.compile("[\x20-\x7e\n]*")
RAW_FORBIDDEN_SUBSTRINGS = tuple(sorted(FORBIDDEN_KEYS_LOWER)) + ("mcp", "env", "helper",
                                                                  "plugin", "otel")
# Agent frontmatter keys a case may not set, compared in lower case. initialPrompt
# would get around the prompt allowlist.
AGENT_FORBIDDEN_KEYS = ("hooks", "mcpservers", "initialprompt")
# The only keys of agent_input, each with a string value. fakeapi.py sends it as the
# Agent tool call, so anything else (isolation, run_in_background) would change what runs.
AGENT_INPUT_KEYS = ("description", "prompt", "subagent_type", "model")
# The only effort values read_transcript keeps.
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
# agent_files: where each file goes, relative to the throwaway root.
AGENT_FILE_WHERE = {"user": ("config", "agents"),
                    "project": ("project", ".claude", "agents"),
                    "nested": ("project", "sub", ".claude", "agents")}
AGENT_FILE_KEYS = ("where", "path", "text")
AGENT_FILE_MAX = 8
AGENT_FILE_SUFFIXES = (".md", ".md.bak")
SEGMENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
CWD_CHOICES = ("project", "nested")
INIT_AGENT_MAX = 100
CLAUDE_TIMEOUT = 90
GIT_TIMEOUT = 20


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


# Characters an agent text may not hold. \n and \t are allowed. The other C0 controls
# (NUL, \v, \f, \r and the like), DEL, U+0085, U+2028 and U+2029 are refused because
# readers disagree on whether they end a line, and so on where the frontmatter ends.
AGENT_TEXT_BAD_CHARS = re.compile("[\x00-\x08\x0b-\x1f\x7f\x85\u2028\u2029]")
# A top-level frontmatter line is blank, a comment, indented, or exactly this.
PLAIN_KEY_LINE = re.compile(r"([A-Za-z][A-Za-z0-9_-]*):(?:[ \t].*)?")
# What an indented line may not start with, after any "- " markers.
INDENTED_BAD_START = "?!&*{,:\\"


def split_frontmatter(text):
    """Return (head, closed) for an agent text, or None when it has no opening fence.

    head holds the lines after the opening fence, up to the closing fence or, when
    there is none, to the end. Splits on "\\n" only. check_frontmatter refuses every
    other line break first.
    """
    lines = text.lstrip("\ufeff").split("\n")
    if lines[0].rstrip(" \t") != "---":
        return None
    out = []
    for line in lines[1:]:
        if line.rstrip(" \t") == "---":
            return "\n".join(out), True
        out.append(line)
    return "\n".join(out), False


def frontmatter(text):
    """Return the frontmatter text of an agent text, or "" when it has none."""
    split = split_frontmatter(text)
    return split[0] if split else ""


_KEY_AT_LINE_START = re.compile(r"^\s*(?:-\s+)?[{,\s]*[\"']?([^\s\"':,{}]+)[\"']?\s*:")
_KEY_IN_FLOW = re.compile(r"[{,]\s*[\"']?([^\s\"':,{}]+)[\"']?\s*:")


def frontmatter_keys(head):
    """Return the mapping keys named anywhere in the frontmatter text.

    Reads a key at the start of a line, plain or quoted, with any indent and any
    space before the colon, plus keys inside a one-line flow mapping. It over-reports
    (a nested key counts) so the guard only ever refuses more.
    """
    keys = set()
    for line in head.split("\n"):
        m = _KEY_AT_LINE_START.match(line)
        if m:
            keys.add(m.group(1))
        keys.update(_KEY_IN_FLOW.findall(line))
    return keys


def flow_depth(text, depth=0):
    """Return how many [ are still open after text, ignoring quoted parts. One line at a time."""
    quote = None
    for ch in text:
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]" and depth > 0:
            depth -= 1
    return depth


def frontmatter_shape_problem(head):
    """Return why the frontmatter lines are not plainly shaped, or None when they are.

    An allowlist, not a hunt for tricks. Every top-level line must be blank, a
    comment, an indented line, or a plain `key:` (no quote, tag, anchor or escape)
    with a space or the end of the line after the colon. The first line that is
    not blank or a comment must be a key line, so an indented block can never be
    the top-level mapping. Braces and backslashes are refused anywhere, so no flow
    map or escaped key can name a key some other way. A line with a colon that
    follows an unclosed [ is refused.
    """
    seen_key = False
    depth = 0
    for line in head.split("\n"):
        if depth > 0 and ":" in line:
            return "a key line sits inside an unclosed flow list"
        if "{" in line or "}" in line:
            return "it holds a brace"
        if "\\" in line:
            return "it holds a backslash"
        if line.strip(" \t") == "" or line.startswith("#"):
            continue
        if line[0] in " \t":
            if not seen_key:
                return "an indented line comes before the first key"
            body = line.lstrip(" \t")
            while body == "-" or body.startswith("- "):
                body = body[1:].lstrip(" \t")
            if body and body[0] in INDENTED_BAD_START:
                return "an indented line starts with %r" % body[0]
            if depth > 0:
                depth = flow_depth(line, depth)
            continue
        m = PLAIN_KEY_LINE.fullmatch(line)
        if not m:
            return "a top-level line is not a plain key"
        seen_key = True
        value = line[m.end(1) + 1:].strip(" \t")
        depth = flow_depth(value) if value.startswith("[") else 0
    return None


def check_frontmatter(label, text):
    """Refuse an agent text whose frontmatter names a forbidden key or is not plainly shaped."""
    bad = AGENT_TEXT_BAD_CHARS.search(text)
    if bad:
        refuse("%s holds the character U+%04X, which is not allowed" % (label, ord(bad.group())))
    lines = text.lstrip("\ufeff").split("\n")
    first = next((i for i, line in enumerate(lines) if line.strip(" \t")), None)
    if first is not None and lines[first].strip().startswith("---") \
            and (first != 0 or lines[0].rstrip(" \t") != "---"):
        refuse("%s has a first line that might be a fence but is not exactly ---" % label)
    split = split_frontmatter(text)
    if split is None:
        return
    head, closed = split
    for key in sorted(frontmatter_keys(head)):
        if key.lower() in AGENT_FORBIDDEN_KEYS:
            refuse("%s frontmatter sets %s" % (label, key))
    if not closed:
        # Claude Code does not load a file with no closing fence (case f1), so the rest
        # is body text. Only a line that might be a closing fence in disguise is refused.
        for line in head.split("\n"):
            if line.strip().startswith("---"):
                refuse("%s has a line that might be a closing fence but is not exactly ---" % label)
        return
    problem = frontmatter_shape_problem(head)
    if problem:
        refuse("%s frontmatter is not plainly shaped: %s" % (label, problem))


def agent_file_segments(path):
    """Return the segments of an agent_files path, or None when the path is not allowed."""
    if not isinstance(path, str):
        return None
    segments = path.split("/")
    if not 1 <= len(segments) <= 2:
        return None
    for seg in segments:
        if seg in (".", "..") or not SEGMENT_RE.fullmatch(seg):
            return None
    if not segments[-1].endswith(AGENT_FILE_SUFFIXES):
        return None
    return segments


def check_agent_files(items, agents):
    """Refuse an agent_files value that is not allowed; return [(where, segments, text)]."""
    if not isinstance(items, list):
        refuse("case agent_files are not a list")
    if len(items) > AGENT_FILE_MAX:
        refuse("case agent_files has more than %d items" % AGENT_FILE_MAX)
    out = []
    # Lower case, because the throwaway folder may sit on a case-insensitive disk.
    taken = {("user", name.lower() + ".md") for name in agents}
    for item in items:
        if not isinstance(item, dict):
            refuse("agent_files item is not an object")
        if sorted(item) != sorted(AGENT_FILE_KEYS):
            refuse("agent_files item must have exactly the keys %s" % ", ".join(AGENT_FILE_KEYS))
        where, path, text = item["where"], item["path"], item["text"]
        if not isinstance(where, str) or where not in AGENT_FILE_WHERE:
            refuse("agent_files where %r is not user, project or nested" % (where,))
        segments = agent_file_segments(path)
        if segments is None:
            refuse("agent_files path %r is not allowed" % (path,))
        if not isinstance(text, str):
            refuse("agent_files %s text is not a string" % path)
        check_frontmatter("agent_files %s" % path, text)
        full = "/".join(segments).lower()
        for other_where, other in taken:
            # The same file, or one is a folder the other needs as a file.
            if other_where == where and (other == full or other.startswith(full + "/")
                                         or full.startswith(other + "/")):
                refuse("agent_files path %s resolves to the same file as another item" % path)
        taken.add((where, full))
        out.append((where, segments, text))
    return out


def check_raw_settings(case):
    """Refuse a raw_settings value that is not allowed. Raw text gets substring checks."""
    if "raw_settings" not in case:
        return
    raw = case["raw_settings"]
    if not isinstance(raw, dict):
        refuse("case raw_settings is not an object")
    for layer, text in raw.items():
        if layer not in RAW_LAYERS:
            refuse("raw_settings names %r, which is not user, project or local" % (layer,))
        if case.get(layer) is not None:
            refuse("raw_settings %s is also set as a normal %s field" % (layer, layer))
        if not isinstance(text, str):
            refuse("raw_settings %s is not a string" % layer)
        if not text:
            refuse("raw_settings %s is empty" % layer)
        if len(text) > RAW_SETTINGS_MAX:
            refuse("raw_settings %s is longer than %d characters" % (layer, RAW_SETTINGS_MAX))
        if not RAW_OK_CHARS.fullmatch(text):
            refuse("raw_settings %s holds a character outside printable ASCII and newline" % layer)
        if "\\" in text:
            refuse("raw_settings %s holds a backslash" % layer)
        low = text.lower()
        for word in RAW_FORBIDDEN_SUBSTRINGS:
            if word in low:
                refuse("raw_settings %s holds %s" % (layer, word))
        try:
            parsed = json.loads(text)
        except (ValueError, RecursionError):
            continue
        if isinstance(parsed, dict):
            refuse("raw_settings %s is a JSON object; use the normal %s field" % (layer, layer))


def init_agents(init):
    """Return the init row's agents list as strings cut to INIT_AGENT_MAX, or None."""
    agents = init.get("agents") if isinstance(init, dict) else None
    if not isinstance(agents, list):
        return None
    return [a[:INIT_AGENT_MAX] for a in agents if isinstance(a, str)]


def check_case(case):
    if not isinstance(case, dict):
        refuse("case is not an object")
    check_env("case env", case.get("env"))
    prompt = case.get("prompt", DEFAULT_PROMPT)
    if not isinstance(prompt, str) or prompt not in PROMPT_ALLOWLIST:
        refuse("case prompt is not on the prompt allowlist")
    if "text_reply" in case and not isinstance(case["text_reply"], bool):
        refuse("case text_reply is not a bool")
    if "git_init" in case and not isinstance(case["git_init"], bool):
        refuse("case git_init is not a bool")
    if "cwd" in case and (not isinstance(case["cwd"], str) or case["cwd"] not in CWD_CHOICES):
        refuse("case cwd is not project or nested")
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
    check_raw_settings(case)
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
        check_frontmatter("agent %s" % name, text)
    if "agent_files" in case:
        check_agent_files(case["agent_files"], agents)
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
    agent_files = check_agent_files(case["agent_files"], case.get("agents") or {}) \
        if "agent_files" in case else []

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
    bases = {"config": cfg, "project": proj}
    for layer, text in (case.get("raw_settings") or {}).items():
        parts = RAW_LAYERS[layer]
        # newline="" so the text lands byte for byte.
        with open(os.path.join(bases[parts[0]], *parts[1:]), "w", newline="") as fh:
            fh.write(text)
    for name, text in (case.get("agents") or {}).items():
        os.makedirs(os.path.join(cfg, "agents"), exist_ok=True)
        with open(os.path.join(cfg, "agents", name + ".md"), "w") as fh:
            fh.write(text)
    for where, segments, text in agent_files:
        parts = AGENT_FILE_WHERE[where]
        target = os.path.join(bases[parts[0]], *parts[1:], *segments)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as fh:
            fh.write(text)
    workdir = proj
    if case.get("cwd") == "nested":
        workdir = os.path.join(proj, "sub")
        os.makedirs(workdir, exist_ok=True)
    if case.get("git_init"):
        genv = pass_through()
        genv.update({"HOME": home, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"})
        try:
            g = subprocess.run(["git", "init", "-q"], cwd=proj, env=genv, capture_output=True,
                               text=True, timeout=GIT_TIMEOUT, stdin=subprocess.DEVNULL)
            failed = None if g.returncode == 0 else "exit %d: %s" % (g.returncode, g.stderr.strip()[-200:])
        except (OSError, subprocess.SubprocessError) as exc:
            failed = "%s: %s" % (type(exc).__name__, exc)
        if failed:
            shutil.rmtree(root, True)
            sys.stderr.write("runcase failed: git init in the project did not finish (%s)\n" % failed)
            sys.exit(1)
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
                "DISABLE_AUTOUPDATER": "1",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"})

    senv = pass_through()
    if case.get("agent_input"):
        senv["AGENT_INPUT"] = json.dumps(case["agent_input"])
    if case.get("text_reply"):
        senv["TEXT_REPLY"] = "1"
    here = os.path.dirname(os.path.abspath(__file__))
    srv = subprocess.Popen([sys.executable, os.path.join(here, "fakeapi.py"), str(port), log], env=senv)
    time.sleep(0.5)
    try:
        r = subprocess.run(args, cwd=workdir, env=env, capture_output=True, text=True,
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
                      "init_agents": init_agents(init),
                      "init_version": init and init.get("claude_code_version"),
                      "sent": [list(k) for k in seen], "stderr": r.stderr[-200:].strip(),
                      "transcript": read_transcript(cfg), "result": results}))
    shutil.rmtree(root, True)


if __name__ == "__main__":
    main()
