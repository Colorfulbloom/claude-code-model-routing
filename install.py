#!/usr/bin/env python3
"""Installs the model-routing setup (agents, rules, hooks, skills, reference doc)
into the Claude Code config directory and registers six hook entries in settings.json.

Python 3.9+, standard library only. Run it through install.sh (a thin shim that
checks the Python version) or directly with python3.
"""
import collections
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

# ============================================================================
# Messages
# Every string a user reads lives in this section. Reword freely, but keep the
# %s placeholders in the same number and order. Logic starts below.
# ============================================================================

MSG_USAGE = """\
Usage: install.sh [--dry-run] [--uninstall] [--yes] [--agent NAME=MODEL[:EFFORT]]
                  [--reset] [--plain] [--help]

Installs the model-routing setup (agents, rules, hooks, skills and the
reference doc) into the Claude Code config directory, CLAUDE_CONFIG_DIR when
set and $HOME/.claude otherwise. Anything it replaces is backed up first
under <config dir>/backups/.

On a terminal it first asks which model and effort each agent should use. The
choices are saved in <config dir>/model-routing-choices.json and preselected
on the next run. Without a terminal (or with CI set) it behaves like --yes.

Options:
  --dry-run    Print the plan. Change nothing.
  --uninstall  Remove what a previous install added (it reads the manifest).
  -y, --yes    Skip the picker. Use saved choices, else the defaults.
  --agent NAME=MODEL[:EFFORT]
               Set one agent's model (haiku, sonnet, opus, fable or a model
               id) and optionally its effort (low, medium, high, xhigh, max).
               Repeat for more agents.
  --reset      Ignore saved choices and start from the defaults.
  --plain      Use numbered prompts instead of the full-screen picker.
  --help, -h   Show this text.

Exit codes: 0 ok, 1 failure, 2 usage error.
"""

MSG_UNKNOWN_FLAG = 'Unknown option: %s\n'
MSG_PYTHON_VERSION = 'python %s\n'
MSG_CLAUDE_VERSION = 'claude %s\n'
MSG_TARGET = 'Target: %s\n'
MSG_DRY_BANNER = 'Dry run. Nothing is created, written or deleted.\n'
MSG_FILES_HEADING = 'Files\n'
MSG_FILE_ADD = '  add        %s\n'
MSG_FILE_UNCHANGED = '  unchanged  %s\n'
MSG_FILE_REPLACE = '  replace    %s (old copy saved to %s)\n'
MSG_FILE_REMOVE = '  remove     %s\n'
MSG_FILE_MOVE = '  edited     %s (kept at %s)\n'
MSG_FILE_GONE = '  missing    %s (already gone)\n'
MSG_FILE_SAMENAME = '  warning    %s also declares name: %s. Claude Code will load only one of the two. Rename or remove that file.\n'
MSG_SETTINGS_HEADING = 'Settings (%s)\n'
MSG_SETTINGS_ADD = '  add        %s hook, matcher %s\n'
MSG_SETTINGS_SKIP = '  skip       %s hook, matcher %s (already there)\n'
MSG_SETTINGS_REMOVE = '  remove     %s hook, matcher %s\n'
MSG_SETTINGS_ABSENT = '  skip       %s hook, matcher %s (not there)\n'
MSG_SETTINGS_BACKUP = '  settings.json saved to %s\n'
MSG_SETTINGS_NOFILE = '  no settings.json found\n'
MSG_MANIFEST_HEADING = 'Manifest (%s)\n'
MSG_MANIFEST_WRITE = '  write      %s\n'
MSG_MANIFEST_UNCHANGED = '  unchanged  %s\n'
MSG_MANIFEST_REMOVE = '  remove     %s\n'
MSG_MANIFEST_MISSING = 'No manifest at %s. Only the hook entries can be removed.\n'
MSG_MANIFEST_LINE = '    %s\n'
MSG_SUMMARY_INSTALL = 'Summary: %s added, %s replaced, %s unchanged. Settings entries: %s added, %s skipped.\n'
MSG_SUMMARY_SAMENAME = 'Same-name agent files: %s found. Each one needs a rename or a removal, or Claude Code keeps only one of the pair.\n'
MSG_SUMMARY_UNINSTALL = 'Summary: %s removed, %s kept in backup, %s already gone. Settings entries: %s removed, %s skipped.\n'
MSG_SUMMARY_BACKUP = 'Backups: %s\n'
MSG_SUMMARY_NO_BACKUP = 'Backups: none needed\n'
MSG_NEXT_HEADING = 'Next steps\n'
MSG_NEXT_INSTALL_1 = '  1. Restart Claude Code so the hooks and agents load.\n'
MSG_NEXT_INSTALL_2 = '  2. Run /route-project inside each project that has its own agents.\n'
MSG_NEXT_INSTALL_3 = '  3. Optional. Run /setup-model-routing for the settings this installer leaves alone (main model, effortLevel, subagent catch-all model).\n'
MSG_NEXT_UNINSTALL_1 = '  1. Restart Claude Code so it stops loading the removed files.\n'

MSG_CHOICES_SOURCE = 'Agent models: %s\n'
MSG_CHOICES_BAD_ENTRY = 'Warning: the saved choice for %s in %s is not valid. Using the default for that agent.\n'
MSG_CHOICES_BAD_FILE = 'Warning: %s is not a usable choices file. Using the defaults.\n'
MSG_CANCELLED = 'Cancelled. Nothing was changed.\n'

MSG_ERR_OLD_PYTHON = 'Error: python3 is older than 3.9 (%s). Install a newer one and run this again.\n'
MSG_ERR_NO_CLAUDE = 'Error: claude is not on PATH. Install Claude Code first.\n'
MSG_ERR_BAD_TARGET = 'Error: the target path contains a double quote, dollar sign, backtick or backslash: %s\n'
MSG_ERR_NO_SOURCE = 'Error: nothing to install in %s\n'
MSG_ERR_BAD_MANIFEST_PATH = 'Error: the manifest lists an unsafe path, so nothing was changed: %s\n'
MSG_ERR_SETTINGS_PARSE = 'Error: %s is not valid JSON. Nothing was changed.\n'
MSG_ERR_SETTINGS_NOT_OBJECT = 'Error: %s is not a JSON object. Nothing was changed.\n'
MSG_ERR_SETTINGS_HOOKS = 'Error: "hooks" in %s is not an object. Nothing was changed.\n'
MSG_ERR_SETTINGS_EVENT = 'Error: hooks.%s in %s is not a list. Nothing was changed.\n'
MSG_ERR_SETTINGS_OTHER = 'Error: could not update %s: %s\n'
MSG_ERR_COPY = 'Error: could not write %s\n'
MSG_ERR_TARGET_NOT_DIR = 'Error: %s exists but is not a directory. Nothing was changed.\n'
MSG_ERR_NOT_WRITABLE = 'Error: %s is not writable. Nothing was changed.\n'
MSG_ERR_SETTINGS_DANGLING = 'Error: %s is a symlink whose target does not exist. Nothing was changed.\n'
MSG_ERR_AGENT_FRONTMATTER = 'Error: %s needs both a model: and an effort: line in its frontmatter.\n'
MSG_ERR_UNEXPECTED = 'Error: %s\n'

MSG_ERR_AGENT_MISSING = 'Error: --agent needs a value like NAME=MODEL[:EFFORT]\n'
MSG_ERR_AGENT_FORMAT = 'Error: --agent expects NAME=MODEL[:EFFORT], got: %s\n'
MSG_ERR_AGENT_UNKNOWN = 'Error: unknown agent %s. Known agents: %s\n'
MSG_ERR_AGENT_INHERIT = 'Error: the model for %s cannot be inherit. Pick a model.\n'
MSG_ERR_AGENT_MODEL = 'Error: %s is not a model alias (haiku, sonnet, opus, fable) or a valid model id.\n'
MSG_ERR_AGENT_EFFORT = 'Error: effort %s is not valid for model %s. Valid efforts: %s\n'
MSG_ERR_FLAG_UNINSTALL = 'Error: %s cannot be combined with --uninstall.\n'

# ============================================================================
# End of Messages
# ============================================================================

ALIASES = ["haiku", "sonnet", "opus", "fable"]
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
EFFORTS_BY_MODEL = {alias: EFFORTS for alias in ALIASES}
FABLE_NOTE = "may bill to usage credits"
DEFAULT_EFFORT = "medium"
CHOICES_NAME = "model-routing-choices.json"
HOOK_NAMES = ["require-agent-model.py", "check-agent-models.sh", "hivemind_lib.py",
              "hivemind-inject.py", "hivemind-capture.py", "hivemind-guard.py"]
SETTINGS_ENTRIES_FMT = [
    ("PreToolUse", "Agent", 'python3 "%s/hooks/require-agent-model.py"'),
    ("SessionStart", "startup", 'bash "%s/hooks/check-agent-models.sh"'),
    ("SubagentStart", "*", 'python3 "%s/hooks/hivemind-inject.py"'),
    ("SubagentStop", "*", 'python3 "%s/hooks/hivemind-capture.py"'),
    ("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit", 'python3 "%s/hooks/hivemind-guard.py"'),
    ("SessionStart", "", 'python3 "%s/hooks/hivemind_lib.py" status'),
]

# A plan entry: destination relative to the target, mode, rendered bytes, and the
# repo source path (for messages only).
Entry = collections.namedtuple("Entry", "rel mode data src")


class InstallError(Exception):
    """A failure that stops the run with exit code 1. The message is printed as is."""


class UsageError(Exception):
    """A bad command line: message and usage go to stderr, exit code 2."""


class Args(object):
    def __init__(self):
        self.dry = False
        self.uninstall = False
        self.yes = False
        self.reset = False
        self.plain = False
        self.help = False
        self.agent_flags = []  # list of (name, model, effort or None)


class Ctx(object):
    """State shared by the install and uninstall steps."""

    def __init__(self, target, settings_real, entries, dry, uninstall, stamp):
        self.target = target
        self.settings_real = settings_real
        self.entries = entries  # list of (event, matcher, command)
        self.dry = dry
        self.uninstall = uninstall
        self.stamp = stamp
        self.manifest = os.path.join(target, "model-routing-manifest.txt")
        self.backup_dir = ""
        self.need_backup = False
        self.set_added = 0
        self.set_skipped = 0
        self.set_removed = 0
        self.samename = 0


# ---- Output helpers ---------------------------------------------------------

def say(fmt, *args):
    sys.stdout.write(fmt % args if args else fmt)
    sys.stdout.flush()


def die_text(fmt, *args):
    return InstallError(fmt % args if args else fmt)


def read_bytes_text(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8", "surrogateescape")


def byte_key(text):
    return text.encode("utf-8", "surrogateescape")


# ---- Argument parsing -------------------------------------------------------

def validate_model(value):
    """True for an alias or a typed model id. `inherit` is never valid."""
    if value in ALIASES:
        return True
    if value == "inherit":
        return False
    return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@\[\]/-]{0,99}", value) is not None


def valid_effort(model, effort):
    return effort in EFFORTS_BY_MODEL.get(model, EFFORTS)


def parse_agent_flag(value):
    """NAME=MODEL[:EFFORT] -> (name, model, effort or None). Raises UsageError."""
    name, sep, rest = value.partition("=")
    if not sep or not name or not rest:
        raise UsageError(MSG_ERR_AGENT_FORMAT % value)
    model, _, effort = rest.partition(":")
    has_effort = ":" in rest
    if model == "inherit":
        raise UsageError(MSG_ERR_AGENT_INHERIT % name)
    if not validate_model(model):
        raise UsageError(MSG_ERR_AGENT_MODEL % model)
    if has_effort and not valid_effort(model, effort):
        raise UsageError(MSG_ERR_AGENT_EFFORT % (effort, model, " ".join(EFFORTS_BY_MODEL.get(model, EFFORTS))))
    return (name, model, effort if has_effort else None)


def parse_args(argv):
    """Processes argv in order. --help stops at the point it is seen (args.help)."""
    args = Args()
    i = 0
    n = len(argv)
    while i < n:
        arg = argv[i]
        i += 1
        if arg == "--dry-run":
            args.dry = True
        elif arg == "--uninstall":
            args.uninstall = True
        elif arg in ("--help", "-h"):
            args.help = True
            return args
        elif arg in ("--yes", "-y"):
            args.yes = True
        elif arg == "--reset":
            args.reset = True
        elif arg == "--plain":
            args.plain = True
        elif arg == "--agent" or arg.startswith("--agent="):
            if arg == "--agent":
                if i >= n:
                    raise UsageError(MSG_ERR_AGENT_MISSING)
                value = argv[i]
                i += 1
            else:
                value = arg[len("--agent="):]
                if value == "":
                    raise UsageError(MSG_ERR_AGENT_MISSING)
            args.agent_flags.append(parse_agent_flag(value))
        else:
            raise UsageError(MSG_UNKNOWN_FLAG % arg)
    if args.uninstall and args.agent_flags:
        raise UsageError(MSG_ERR_FLAG_UNINSTALL % "--agent")
    if args.uninstall and args.reset:
        raise UsageError(MSG_ERR_FLAG_UNINSTALL % "--reset")
    return args


def is_interactive(stdin, stdout, env):
    ci = env.get("CI", "")
    ci_set = ci != "" and ci.lower() not in ("0", "false", "no", "off")
    return bool(stdin.isatty() and stdout.isatty() and not ci_set)


# ---- Target -----------------------------------------------------------------

def resolve_target(env, cwd):
    """The config dir: CLAUDE_CONFIG_DIR else $HOME/.claude, made absolute and checked."""
    t = env.get("CLAUDE_CONFIG_DIR") or (env.get("HOME", "") + "/.claude")
    while len(t) > 1 and t.endswith("/"):
        t = t[:-1]
    if not t.startswith("/"):
        t = os.path.realpath(cwd) + "/" + t
    if any(c in t for c in '"$`\\'):
        raise die_text(MSG_ERR_BAD_TARGET, t)
    if (os.path.exists(t) or os.path.islink(t)) and not os.path.isdir(t):
        raise die_text(MSG_ERR_TARGET_NOT_DIR, t)
    return t


def hook_prefix(target, env):
    """The literal text $HOME/.claude when the target is the default location."""
    if target == env.get("HOME", "") + "/.claude":
        return "$HOME/.claude"
    return target


def hook_entries(prefix):
    """The settings.json entries as (event, matcher, command) tuples."""
    return [(event, matcher, fmt % prefix) for event, matcher, fmt in SETTINGS_ENTRIES_FMT]


def detect_claude_version():
    """First line of `claude --version`, or None when claude is not on PATH."""
    if shutil.which("claude") is None:
        return None
    try:
        proc = subprocess.run(["claude", "--version"], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        text = proc.stdout.decode("utf-8", "surrogateescape")
    except OSError:
        text = ""
    return text.split("\n")[0]


# ---- Frontmatter parse and render -------------------------------------------

LINE_RE = re.compile(r"[^\n]*\n|[^\n]+")


def split_line(line):
    """(content, ending) with ending one of \\r\\n, \\n or empty."""
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def frontmatter_span(lines):
    """Index range (1, end) of frontmatter lines, or None without frontmatter."""
    if not lines or split_line(lines[0])[0] != "---":
        return None
    for idx in range(1, len(lines)):
        if split_line(lines[idx])[0] == "---":
            return (1, idx)
    return None


def strip_quotes(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value.strip()


def find_field_lines(lines, span):
    found = {}
    for idx in range(span[0], span[1]):
        content = split_line(lines[idx])[0]
        for key in ("model", "effort"):
            if key not in found and content.startswith(key + ":"):
                found[key] = idx
    return found


def parse_agent_defaults(text, label):
    """(model, effort) from the frontmatter. Raises InstallError naming `label`."""
    lines = LINE_RE.findall(text)
    span = frontmatter_span(lines)
    found = find_field_lines(lines, span) if span else {}
    if "model" not in found or "effort" not in found:
        raise die_text(MSG_ERR_AGENT_FRONTMATTER, label)
    values = []
    for key in ("model", "effort"):
        content = split_line(lines[found[key]])[0]
        values.append(strip_quotes(content[len(key) + 1:]))
    return (values[0], values[1])


def render_agent(text, model, effort, label="agent file"):
    """Replaces only the first model: and effort: lines inside the frontmatter."""
    lines = LINE_RE.findall(text)
    span = frontmatter_span(lines)
    found = find_field_lines(lines, span) if span else {}
    if "model" not in found or "effort" not in found:
        raise die_text(MSG_ERR_AGENT_FRONTMATTER, label)
    for key, value in (("model", model), ("effort", effort)):
        ending = split_line(lines[found[key]])[1]
        lines[found[key]] = "%s: %s%s" % (key, value, ending)
    return "".join(lines)


# ---- Choices ----------------------------------------------------------------

def list_agents(repo_dir):
    """Sorted basenames of repo agents/*.md (regular files, no dotfiles)."""
    agents_dir = os.path.join(repo_dir, "agents")
    names = []
    if os.path.isdir(agents_dir):
        for fname in os.listdir(agents_dir):
            if fname.startswith(".") or not fname.endswith(".md"):
                continue
            if os.path.isfile(os.path.join(agents_dir, fname)):
                names.append(fname[:-3])
    return sorted(names, key=byte_key)


def load_agent_defaults(repo_dir, agents):
    defaults = {}
    for name in agents:
        path = os.path.join(repo_dir, "agents", name + ".md")
        defaults[name] = parse_agent_defaults(read_bytes_text(path), path)
    return defaults


def serialize_choices(choices):
    agents = {}
    for name in sorted(choices, key=byte_key):
        model, effort = choices[name]
        agents[name] = {"model": model, "effort": effort}
    return json.dumps({"format": 1, "agents": agents}, indent=2) + "\n"


def load_choices(path, agents, defaults):
    """Returns (choices, status, bad_names). status: missing, bad or ok.

    Unusable entries keep the agent's default and are listed in bad_names.
    """
    choices = dict(defaults)
    if not os.path.isfile(path):
        return choices, "missing", []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return choices, "bad", []
    fmt = data.get("format") if isinstance(data, dict) else None
    saved = data.get("agents") if isinstance(data, dict) else None
    if not (isinstance(fmt, int) and not isinstance(fmt, bool) and fmt == 1 and isinstance(saved, dict)):
        return choices, "bad", []
    bad = []
    for name in agents:
        if name not in saved:
            continue
        entry = saved[name]
        model = entry.get("model") if isinstance(entry, dict) else None
        effort = entry.get("effort") if isinstance(entry, dict) else None
        if isinstance(model, str) and isinstance(effort, str) and validate_model(model) and valid_effort(model, effort):
            choices[name] = (model, effort)
        else:
            bad.append(name)
    return choices, "ok", bad


def apply_agent_flags(choices, defaults, flags):
    """Applies --agent values in order. A missing effort keeps the current one when
    valid for the model, else the agent's default when valid, else medium."""
    result = dict(choices)
    for name, model, effort in flags:
        if effort is None:
            current = result[name][1]
            default = defaults[name][1]
            if valid_effort(model, current):
                effort = current
            elif valid_effort(model, default):
                effort = default
            else:
                effort = DEFAULT_EFFORT
        result[name] = (model, effort)
    return result


def choices_source(saved_path, saved, flagged, picked):
    if picked:
        return "picker"
    if saved and flagged:
        return "saved choices with --agent"
    if flagged:
        return "defaults with --agent"
    if saved:
        return "saved choices (%s)" % saved_path
    return "defaults"


# ---- Picker -----------------------------------------------------------------
# PickerState holds all the picker logic with no curses and no I/O. The two
# drivers (curses and numbered prompts) only translate keys or lines into actions
# and draw what render_screen returns.

UP = "up"
DOWN = "down"
ENTER = "enter"
BACK = "back"
QUIT = "quit"
RESET_ROW = "reset_row"
BACKSPACE = "backspace"

SCREEN_SUMMARY = "summary"
SCREEN_AGENTS = "agents"
SCREEN_MODEL = "model"
SCREEN_TYPED_ID = "typed_id"
SCREEN_EFFORT = "effort"
SCREEN_REVIEW = "review"

PICKER_TITLE = "Model routing installer"
PICKER_SAVED_NOTE = "(saved choices loaded)"
PICKER_INHERIT_NOTE = "inherit is not offered: the dispatch hook blocks it."
PICKER_TOO_SMALL = "Terminal too small. Enlarge it or press q."
PICKER_MIN_COLS = 60
PICKER_MIN_ROWS = 18
PICKER_ERR_MODEL = "Not a valid model id. Use letters, digits and . - _ @ [ ] / only, no spaces, quotes, colons or #."


def snap_effort(model, effort):
    """The effort itself when valid for the model, else the nearest valid level
    (the lower one on a tie)."""
    valid = EFFORTS_BY_MODEL.get(model, EFFORTS)
    if effort in valid or not valid:
        return effort
    pos = EFFORTS.index(effort) if effort in EFFORTS else EFFORTS.index(DEFAULT_EFFORT)
    return min(valid, key=lambda v: (abs(EFFORTS.index(v) - pos), EFFORTS.index(v)))


class PickerState(object):
    """Pure picker state. `choices` maps agent name -> (model, effort)."""

    def __init__(self, choices, defaults=None, saved=False):
        self.initial = dict(choices)
        self.choices = dict(choices)
        self.defaults = dict(defaults) if defaults is not None else dict(choices)
        self.agents = sorted(choices, key=byte_key)
        self.saved = saved
        self.stack = [SCREEN_SUMMARY]
        self.cursor = 0
        self.agent = None
        self.text = ""
        self.error = ""
        self.done = False
        self.cancelled = False
        self.result = None
        self.agents_cursor = 0
        self.visited_agents = False

    # -- queries
    @property
    def screen(self):
        return self.stack[-1]

    def differs_from_defaults(self):
        return any(self.choices[a] != self.defaults.get(a) for a in self.agents)

    def options(self):
        """The selectable rows of the current screen as (kind, argument)."""
        scr = self.screen
        if scr == SCREEN_SUMMARY:
            opts = [("install", None), ("change", None)]
            if self.differs_from_defaults():
                opts.append(("reset", None))
            opts.append(("cancel", None))
            return opts
        if scr == SCREEN_AGENTS:
            return [("agent", a) for a in self.agents] + [("done", None)]
        if scr == SCREEN_MODEL:
            return [("alias", a) for a in ALIASES] + [("other", None)]
        if scr == SCREEN_EFFORT:
            model = self.choices[self.agent][0]
            return [("effort", e) for e in EFFORTS_BY_MODEL.get(model, EFFORTS)]
        if scr == SCREEN_REVIEW:
            return [("install", None), ("back", None), ("cancel", None)]
        return []

    # -- helpers
    def _kinds(self):
        return [k for k, _ in self.options()]

    def _set_cursor(self):
        scr = self.screen
        opts = self.options()
        cur = 0
        if scr == SCREEN_SUMMARY:
            cur = 1 if self.visited_agents else 0
        elif scr == SCREEN_AGENTS:
            cur = min(self.agents_cursor, len(opts) - 1)
        elif scr == SCREEN_MODEL:
            model = self.choices[self.agent][0]
            cur = ALIASES.index(model) if model in ALIASES else len(ALIASES)
        elif scr == SCREEN_EFFORT:
            effort = self.choices[self.agent][1]
            vals = [a for _, a in opts]
            cur = vals.index(effort) if effort in vals else 0
        self.cursor = cur

    def _push(self, screen):
        self.stack.append(screen)
        self.error = ""
        self._set_cursor()

    def _return_to(self, screen):
        while len(self.stack) > 1 and self.stack[-1] != screen:
            self.stack.pop()
        self.error = ""
        self._set_cursor()

    def _finish(self, cancelled):
        self.done = True
        self.cancelled = cancelled
        self.result = None if cancelled else dict(self.choices)

    def _set_model(self, model):
        effort = snap_effort(model, self.choices[self.agent][1])
        self.choices[self.agent] = (model, effort)
        self._push(SCREEN_EFFORT)

    # -- actions
    def press(self, action):
        """Applies one action. ("char", c) inserts a character in typed_id."""
        if self.done:
            return
        if isinstance(action, tuple):
            if self.screen == SCREEN_TYPED_ID and len(action) == 2 and action[0] == "char":
                self.text += action[1]
                self.error = ""
            return
        scr = self.screen
        if action == QUIT:
            if scr != SCREEN_TYPED_ID:
                self._finish(True)
            return
        if scr == SCREEN_TYPED_ID:
            self._press_typed(action)
            return
        if action in (UP, DOWN):
            n = len(self.options())
            if action == UP:
                self.cursor = max(0, self.cursor - 1)
            else:
                self.cursor = min(n - 1, self.cursor + 1)
            if scr == SCREEN_AGENTS:
                self.agents_cursor = self.cursor
            return
        if action == BACK:
            self._back()
        elif action == RESET_ROW:
            if scr == SCREEN_AGENTS:
                kind, arg = self.options()[self.cursor]
                if kind == "agent" and arg in self.defaults:
                    self.choices[arg] = self.defaults[arg]
        elif action == ENTER:
            self._enter()

    def _press_typed(self, action):
        if action == BACKSPACE:
            self.text = self.text[:-1]
            self.error = ""
        elif action == BACK:
            self._back()
        elif action == ENTER:
            if not validate_model(self.text):
                self.error = PICKER_ERR_MODEL
                return
            self._set_model(self.text)

    def _back(self):
        scr = self.screen
        if scr == SCREEN_AGENTS:
            self.stack.pop()
            self._set_cursor()
        elif scr in (SCREEN_MODEL, SCREEN_REVIEW, SCREEN_EFFORT):
            self._return_to(SCREEN_AGENTS)
        elif scr == SCREEN_TYPED_ID:
            self._return_to(SCREEN_MODEL)

    def _enter(self):
        scr = self.screen
        kind, arg = self.options()[self.cursor]
        if scr == SCREEN_SUMMARY:
            if kind == "install":
                self._finish(False)
            elif kind == "change":
                self.visited_agents = True
                self._push(SCREEN_AGENTS)
            elif kind == "reset":
                self.choices = dict(self.defaults)
                self.cursor = min(self.cursor, len(self.options()) - 1)
            else:
                self._finish(True)
        elif scr == SCREEN_AGENTS:
            if kind == "agent":
                self.agent = arg
                self.agents_cursor = self.cursor
                self._push(SCREEN_MODEL)
            else:
                self._push(SCREEN_REVIEW)
        elif scr == SCREEN_MODEL:
            if kind == "alias":
                self._set_model(arg)
            else:
                current = self.choices[self.agent][0]
                self.text = "" if current in ALIASES else current
                self._push(SCREEN_TYPED_ID)
        elif scr == SCREEN_EFFORT:
            model = self.choices[self.agent][0]
            self.choices[self.agent] = (model, arg)
            self._return_to(SCREEN_AGENTS)
        elif scr == SCREEN_REVIEW:
            if kind == "install":
                self._finish(False)
            elif kind == "back":
                self._back()
            else:
                self._finish(True)


def file_plan_lines(entries, target):
    """Plan entries that would change something, as (word, rel). Compares each
    entry's bytes with the destination, like the install step does."""
    out = []
    for entry in entries:
        dest = (target + "/" + entry.rel) if target else None
        if dest is None or not os.path.exists(dest):
            out.append(("add", entry.rel))
        elif not same_bytes(dest, entry.data):
            out.append(("replace", entry.rel))
    return out


def _mark(value, default):
    return value + (" *" if value != default else "")


def build_screen(state, preview_fn, target=None):
    """(lines, option_line_indices, footer). Option rows start with "> " (the
    cursor row) or two spaces. Pure and ASCII."""
    lines = []
    opt_idx = []
    scr = state.screen

    def add_options(texts):
        for i, text in enumerate(texts):
            opt_idx.append(len(lines))
            lines.append(("> " if i == state.cursor else "  ") + text)

    def default_of(name):
        return state.defaults.get(name, state.choices[name])

    if scr == SCREEN_SUMMARY:
        lines.append(PICKER_TITLE)
        if state.saved:
            lines.append(PICKER_SAVED_NOTE)
        lines.append("")
        rows = []
        for a in state.agents:
            m, e = state.choices[a]
            dm, de = default_of(a)
            rows.append((a, _mark(m, dm), _mark(e, de)))
        wa = max([len("AGENT")] + [len(r[0]) for r in rows])
        wm = max([len("MODEL")] + [len(r[1]) for r in rows])
        lines.append("%-*s  %-*s  %s" % (wa, "AGENT", wm, "MODEL", "EFFORT"))
        for r in rows:
            lines.append(("%-*s  %-*s  %s" % (wa, r[0], wm, r[1], r[2])).rstrip())
        lines.append("")
        names = {"install": "Install with these settings", "change": "Change models and effort",
                 "reset": "Reset all to defaults", "cancel": "Cancel"}
        add_options([names[k] for k in state._kinds()])
        footer = "Up/Down move, Enter select, q cancel"
    elif scr == SCREEN_AGENTS:
        lines.append("Agents")
        lines.append("Pick an agent to change its model and effort.")
        lines.append("")
        wa = max(len(a) for a in state.agents)
        wm = max(len(state.choices[a][0]) for a in state.agents)
        we = max(len(state.choices[a][1]) for a in state.agents)
        texts = []
        for a in state.agents:
            m, e = state.choices[a]
            dm, de = default_of(a)
            hint = "default" if (m, e) == (dm, de) else "default: %s %s" % (dm, de)
            texts.append("%-*s  %-*s  %-*s  %s" % (wa, a, wm, m, we, e, hint))
        texts.append("Done, review")
        add_options(texts)
        footer = "Up/Down move, Enter change, r reset row, Esc back, q cancel"
    elif scr == SCREEN_MODEL:
        lines.append("%s: model" % state.agent)
        lines.append("")
        current, _ = state.choices[state.agent]
        dm = default_of(state.agent)[0]
        texts = []
        for a in ALIASES:
            text = "(%s) %s" % ("*" if a == current else " ", a)
            if a == dm:
                text += "  default"
            if a == "fable":
                text += "  (%s)" % FABLE_NOTE
            texts.append(text)
        texts.append("(%s) Other: type a model id" % ("*" if current not in ALIASES else " "))
        add_options(texts)
        lines.append("")
        lines.append(PICKER_INHERIT_NOTE)
        footer = "Up/Down move, Enter select, Esc back, q cancel"
    elif scr == SCREEN_TYPED_ID:
        lines.append("%s: model id" % state.agent)
        lines.append("")
        lines.append("Model id: %s_" % state.text)
        opt_idx_text = len(lines) - 1
        if state.error:
            lines.append("  " + state.error)
        lines.append("")
        lines.append(PICKER_INHERIT_NOTE)
        footer = "Type the id, Enter accept, Backspace delete, Esc back"
        return lines, [opt_idx_text], footer
    elif scr == SCREEN_EFFORT:
        model, current = state.choices[state.agent]
        lines.append("%s on %s: effort" % (state.agent, model))
        lines.append("")
        de = default_of(state.agent)[1]
        texts = []
        for e in EFFORTS_BY_MODEL.get(model, EFFORTS):
            text = "(%s) %s" % ("*" if e == current else " ", e)
            if e == de:
                text += "  default"
            texts.append(text)
        add_options(texts)
        footer = "Up/Down move, Enter select, Esc back, q cancel"
    else:
        lines.append("Review")
        lines.append("")
        changed = 0
        for a in state.agents:
            if state.choices[a] != state.initial[a]:
                changed += 1
                om, oe = state.initial[a]
                nm, ne = state.choices[a]
                lines.append("%s  %s %s  ->  %s %s" % (a, om, oe, nm, ne))
        lines.append("(%d agents unchanged)" % (len(state.agents) - changed))
        lines.append("")
        lines.append("Files")
        plan = file_plan_lines(preview_fn(state.choices), target)
        if plan:
            for word, rel in plan:
                lines.append("  %-9s  %s" % (word, rel))
        else:
            lines.append("  (no file changes)")
        lines.append("")
        names = {"install": "Install", "back": "Back", "cancel": "Cancel"}
        add_options([names[k] for k in state._kinds()])
        footer = "Up/Down move, Enter select, PgUp/PgDn scroll, Esc back, q cancel"
    return lines, opt_idx, footer


def render_screen(state, preview_fn, target=None):
    """(lines, selected line index, footer) for the current screen. The selected
    index is the cursor row's line (the text field's line on typed_id)."""
    lines, opt_idx, footer = build_screen(state, preview_fn, target)
    if state.screen == SCREEN_TYPED_ID:
        return lines, opt_idx[0], footer
    return lines, opt_idx[state.cursor] if opt_idx else None, footer


def key_to_action(key, screen):
    """Maps a curses key code to an action, ("char", c) or None."""
    if screen == SCREEN_TYPED_ID:
        if key in (10, 13, 343):
            return ENTER
        if key == 27:
            return BACK
        if key in (127, 8, 263):
            return BACKSPACE
        if 32 <= key <= 126:
            return ("char", chr(key))
        return None
    if key in (259, ord("k")):
        return UP
    if key in (258, ord("j")):
        return DOWN
    if key in (10, 13, 343):
        return ENTER
    if key in (27, ord("b"), 260, 263, 127, 8):
        return BACK
    if key == ord("q"):
        return QUIT
    if key == ord("r"):
        return RESET_ROW
    return None


def _memo_preview(preview_fn):
    cache = {}

    def preview(choices):
        key = tuple(sorted(choices.items()))
        if key not in cache:
            cache.clear()
            cache[key] = preview_fn(choices)
        return cache[key]
    return preview


def _curses_draw(curses, stdscr, state, preview, target, top):
    stdscr.erase()
    rows, cols = stdscr.getmaxyx()
    if rows < PICKER_MIN_ROWS or cols < PICKER_MIN_COLS:
        try:
            stdscr.addnstr(0, 0, PICKER_TOO_SMALL, max(cols - 1, 1))
        except curses.error:
            pass
        stdscr.refresh()
        return top, True
    lines, sel, footer = render_screen(state, preview, target)
    height = rows - 1
    if top is None:
        top = 0
    if sel is not None:
        if sel < top:
            top = sel
        if sel >= top + height:
            top = sel - height + 1
    top = max(0, min(top, max(0, len(lines) - height)))
    for i in range(height):
        idx = top + i
        if idx >= len(lines):
            break
        attr = curses.A_NORMAL
        if idx == sel and state.screen != SCREEN_TYPED_ID:
            attr = curses.A_REVERSE
        elif idx == 0 or (state.screen == SCREEN_SUMMARY and lines[idx].startswith("AGENT ")):
            attr = curses.A_BOLD
        try:
            stdscr.addnstr(i, 0, lines[idx], cols - 1, attr)
        except curses.error:
            pass
    try:
        stdscr.addnstr(rows - 1, 0, footer, cols - 1)
    except curses.error:
        pass
    stdscr.refresh()
    return top, False


def _curses_loop(stdscr, state, preview_fn, target):
    import curses
    preview = _memo_preview(preview_fn)
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    stdscr.keypad(True)
    top = 0
    while not state.done:
        top, small = _curses_draw(curses, stdscr, state, preview, target, top)
        key = stdscr.getch()
        if key == curses.KEY_RESIZE:
            continue
        if small:
            if key == ord("q"):
                state.press(QUIT)
            continue
        if key == curses.KEY_PPAGE:
            top = max(0, top - (stdscr.getmaxyx()[0] // 2))
            continue
        if key == curses.KEY_NPAGE:
            top += stdscr.getmaxyx()[0] // 2
            continue
        action = key_to_action(key, state.screen)
        if action is not None:
            state.press(action)
            top = 0 if state.screen != SCREEN_REVIEW else top


def run_plain_picker(state, preview_fn, target=None, inp=None, out=None):
    """Numbered prompts on the same PickerState. EOF cancels."""
    out = out or sys.stdout
    inp = inp or input
    preview = _memo_preview(preview_fn)

    def write(text):
        out.write(text + "\n")
        out.flush()

    while not state.done:
        lines, opt_idx, footer = build_screen(state, preview, target)
        write("")
        if state.screen == SCREEN_TYPED_ID:
            for line in lines:
                write(line)
            try:
                line = inp("Model id (Enter keeps the text above, b goes back, q cancels): ")
            except EOFError:
                state._finish(True)
                return
            line = line.strip()
            if line == "b":
                state.press(BACK)
            elif line == "q":
                state._finish(True)
            else:
                if line:
                    state.text = line
                state.press(ENTER)
            continue
        n = len(opt_idx)
        for i, li in enumerate(opt_idx):
            lines[li] = "%2d) %s" % (i + 1, lines[li][2:])
        for line in lines:
            write(line)
        try:
            line = inp("Choose 1-%d (Enter keeps the current one): " % n)
        except EOFError:
            state._finish(True)
            return
        line = line.strip()
        if line == "":
            state.press(ENTER)
        elif line == "q":
            state.press(QUIT)
        elif line == "b":
            state.press(BACK)
        elif line.isdigit() and 1 <= int(line) <= n:
            state.cursor = int(line) - 1
            if state.screen == SCREEN_AGENTS:
                state.agents_cursor = state.cursor
            state.press(ENTER)
        elif state.screen == SCREEN_AGENTS and re.fullmatch(r"r\s*\d+", line) and 1 <= int(line[1:]) <= len(state.agents):
            state.cursor = state.agents_cursor = int(line[1:]) - 1
            state.press(RESET_ROW)
        else:
            write("Enter a number from 1 to %d, b to go back or q to cancel." % n)


def run_picker(choices, plan_preview_fn, plain=False, defaults=None, target=None, saved=False):
    """The interactive picker. Returns the edited choices, or None when the user
    cancels. Never called without a terminal. `target` (the config dir) lets the
    review screen tell add from replace."""
    state = PickerState(choices, defaults, saved)
    use_plain = plain or os.environ.get("TERM", "") in ("", "dumb")
    if not use_plain:
        try:
            import curses
        except ImportError:
            use_plain = True
    if not use_plain:
        os.environ.setdefault("ESCDELAY", "25")
        try:
            curses.wrapper(_curses_loop, state, plan_preview_fn, target)
        except curses.error:
            use_plain = True  # wrapper has restored the terminal
    if use_plain and not state.done:
        run_plain_picker(state, plan_preview_fn, target)
    return None if state.cancelled else state.result


# ---- Plan -------------------------------------------------------------------

def build_plan(repo_dir, choices):
    """The ordered list of Entry objects, rendered in memory from `choices`
    (name -> (model, effort))."""
    plan = []

    def read(path):
        with open(path, "rb") as fh:
            return fh.read()

    agents_dir = os.path.join(repo_dir, "agents")
    for name in list_agents(repo_dir):
        src = os.path.join(agents_dir, name + ".md")
        model, effort = choices[name]
        text = read_bytes_text(src)
        data = render_agent(text, model, effort, src).encode("utf-8", "surrogateescape")
        plan.append(Entry("agents/%s.md" % name, 0o644, data, src))
    rules_dir = os.path.join(repo_dir, "rules")
    if os.path.isdir(rules_dir):
        rule_names = [f for f in os.listdir(rules_dir)
                      if not f.startswith(".") and f.endswith(".md")
                      and os.path.isfile(os.path.join(rules_dir, f))]
        for fname in sorted(rule_names, key=byte_key):
            src = os.path.join(rules_dir, fname)
            plan.append(Entry("rules/" + fname, 0o644, read(src), src))
    for name in HOOK_NAMES:
        src = os.path.join(repo_dir, "hooks", name)
        if os.path.isfile(src):
            plan.append(Entry("hooks/" + name, 0o755, read(src), src))
    skills_dir = os.path.join(repo_dir, "skills")
    if os.path.isdir(skills_dir) and not os.path.islink(skills_dir):
        found = []
        for dirpath, _dirnames, filenames in os.walk(skills_dir):
            for fname in filenames:
                full = os.path.join(dirpath, fname)
                if fname != ".DS_Store" and not os.path.islink(full) and os.path.isfile(full):
                    found.append(full)
        for full in sorted(found, key=byte_key):
            plan.append(Entry("skills/" + full[len(skills_dir) + 1:], 0o644, read(full), full))
    ref = os.path.join(repo_dir, "docs", "model-routing-reference.md")
    if os.path.isfile(ref):
        plan.append(Entry("model-routing-reference.md", 0o644, read(ref), ref))
    if not plan:
        raise die_text(MSG_ERR_NO_SOURCE, repo_dir)
    plan.append(Entry(CHOICES_NAME, 0o644,
                      serialize_choices(choices).encode("utf-8"),
                      os.path.join(repo_dir, "agents")))
    return plan


# ---- Backup dir and preflight -----------------------------------------------

def pick_backup_dir(target, stamp, uninstall):
    """The backup dir name (a numeric suffix when taken). Creates nothing."""
    kind = "model-routing-uninstall-" if uninstall else "model-routing-"
    base = "%s/backups/%s%s" % (target, kind, stamp)
    cand = base
    n = 1
    while os.path.exists(cand):
        n += 1
        cand = "%s-%d" % (base, n)
    return cand


def ensure_backup_dir(ctx):
    if not ctx.backup_dir:
        ctx.backup_dir = pick_backup_dir(ctx.target, ctx.stamp, ctx.uninstall)


def need_writable(path):
    """The path, or its nearest existing ancestor, must be a writable, enterable dir."""
    p = path
    while not os.path.exists(p) and not os.path.islink(p):
        p = os.path.dirname(p)
    if not os.path.isdir(p) or not os.access(p, os.W_OK) or not os.access(p, os.X_OK):
        raise die_text(MSG_ERR_NOT_WRITABLE, p)


def manifest_paths(text):
    """Paths listed in a manifest, each line kept raw (like `IFS= read -r`): only
    comment lines and lines of nothing but whitespace are dropped."""
    paths = []
    for raw in text.split("\n"):
        if raw.startswith("#") or raw.strip(" \t\n\r\v\f") == "":
            continue
        paths.append(raw)
    return paths


def unsafe_path(rel):
    return (rel.startswith("/") or rel == ".." or rel.startswith("../")
            or rel.endswith("/..") or "/../" in rel)


def preflight(ctx, plan):
    """Runs before anything is written, for a real run and a dry run alike."""
    t = ctx.target
    if ctx.uninstall and not os.path.exists(t):
        return
    need_writable(t)
    need_writable(os.path.dirname(ctx.settings_real))
    need_writable(t + "/backups")
    if not ctx.uninstall:
        for entry in plan:
            need_writable(os.path.dirname(t + "/" + entry.rel))
    elif os.path.isfile(ctx.manifest):
        for rel in manifest_paths(read_bytes_text(ctx.manifest)):
            if unsafe_path(rel):
                continue  # refused later with its own message
            if os.path.exists(t + "/" + rel):
                need_writable(os.path.dirname(t + "/" + rel))


# ---- Settings merge ---------------------------------------------------------

def merge_settings(mode, path, dry, backup_dir, tdir, entries):
    """Returns (lines, ok). Each line is a tuple:
    backup <path> | add/skip/remove/absent <event> <matcher> | nofile | error <code> [detail]
    """
    lines = []

    def out(*parts):
        lines.append(tuple(parts))

    existed = os.path.exists(path)
    if existed:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            out("error", "parse")
            return lines, False
        if not isinstance(data, dict):
            out("error", "notobject")
            return lines, False
    else:
        data = {}
        if mode == "uninstall":
            out("nofile")

    hooks = data.get("hooks")
    if "hooks" in data and not isinstance(hooks, dict):
        out("error", "hooks")
        return lines, False
    for event, _, _ in entries:
        if isinstance(hooks, dict) and event in hooks and not isinstance(hooks[event], list):
            out("error", "event", event)
            return lines, False

    def has_ours(group, matcher, command):
        if not isinstance(group, dict) or group.get("matcher") != matcher:
            return False
        hs = group.get("hooks")
        if not isinstance(hs, list):
            return False
        return any(isinstance(h, dict) and h.get("type") == "command" and h.get("command") == command for h in hs)

    changed = False
    if mode == "install":
        for event, matcher, command in entries:
            lst = hooks.get(event) if isinstance(hooks, dict) else None
            if isinstance(lst, list) and any(has_ours(g, matcher, command) for g in lst):
                out("skip", event, matcher)
                continue
            if not isinstance(hooks, dict):
                hooks = {}
                data["hooks"] = hooks
            if event not in hooks:
                hooks[event] = []
            hooks[event].append({"matcher": matcher, "hooks": [{"type": "command", "command": command, "timeout": 10}]})
            out("add", event, matcher)
            changed = True
    else:
        for event, matcher, command in entries:
            lst = hooks.get(event) if isinstance(hooks, dict) else None
            removed = False
            if isinstance(lst, list):
                keep = []
                for g in lst:
                    if has_ours(g, matcher, command):
                        before = g["hooks"]
                        after = [h for h in before
                                 if not (isinstance(h, dict) and h.get("type") == "command" and h.get("command") == command)]
                        if len(after) != len(before):
                            removed = True
                        if after:
                            g["hooks"] = after
                            keep.append(g)
                        # a group we emptied is dropped
                    else:
                        keep.append(g)
                if removed:
                    if keep:
                        hooks[event] = keep
                    else:
                        del hooks[event]
            if removed:
                out("remove", event, matcher)
                changed = True
            else:
                out("absent", event, matcher)
        if changed and isinstance(hooks, dict) and not hooks:
            del data["hooks"]

    if not changed:
        return lines, True

    if existed:
        out("backup", os.path.join(backup_dir, "settings.json"))
    if dry:
        return lines, True

    try:
        if existed:
            os.makedirs(backup_dir, exist_ok=True)
            shutil.copy2(path, os.path.join(backup_dir, "settings.json"))
        os.makedirs(tdir, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile("w", dir=tdir, delete=False, encoding="utf-8")
        try:
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp.write("\n")
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()
            os.chmod(tmp.name, (os.stat(path).st_mode & 0o7777) if existed else 0o644)
            os.replace(tmp.name, path)
        except Exception:
            try:
                tmp.close()
            except Exception:
                pass
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)
            raise
    except Exception as exc:
        out("error", "other", str(exc))
        return lines, False
    return lines, True


def do_settings(ctx, mode, dry, quiet):
    """Runs the merge and prints its lines. A quiet run only checks that the file
    can be merged (used before any file is copied)."""
    ensure_backup_dir(ctx)
    lines, ok = merge_settings(mode, ctx.settings_real, dry, ctx.backup_dir,
                               os.path.dirname(ctx.settings_real), ctx.entries)
    settings_path = ctx.target + "/settings.json"
    for line in lines:
        kind = line[0]
        a = line[1] if len(line) > 1 else ""
        b = line[2] if len(line) > 2 else ""
        if kind in ("add", "skip", "remove", "absent") and b == "":
            b = '""'  # an empty matcher prints readably
        if kind == "add" and not quiet:
            say(MSG_SETTINGS_ADD, a, b)
            ctx.set_added += 1
        elif kind == "skip" and not quiet:
            say(MSG_SETTINGS_SKIP, a, b)
            ctx.set_skipped += 1
        elif kind == "remove" and not quiet:
            say(MSG_SETTINGS_REMOVE, a, b)
            ctx.set_removed += 1
        elif kind == "absent" and not quiet:
            say(MSG_SETTINGS_ABSENT, a, b)
            ctx.set_skipped += 1
        elif kind == "nofile" and not quiet:
            say(MSG_SETTINGS_NOFILE)
        elif kind == "backup" and not quiet:
            say(MSG_SETTINGS_BACKUP, a)
            ctx.need_backup = True
        elif kind == "error":
            if a == "parse":
                raise die_text(MSG_ERR_SETTINGS_PARSE, settings_path)
            if a == "notobject":
                raise die_text(MSG_ERR_SETTINGS_NOT_OBJECT, settings_path)
            if a == "hooks":
                raise die_text(MSG_ERR_SETTINGS_HOOKS, settings_path)
            if a == "event":
                raise die_text(MSG_ERR_SETTINGS_EVENT, b, settings_path)
            raise die_text(MSG_ERR_SETTINGS_OTHER, settings_path, b)
    if not ok:
        raise InstallError("")


def print_backup_summary(ctx):
    if ctx.need_backup and ctx.backup_dir:
        say(MSG_SUMMARY_BACKUP, ctx.backup_dir)
    else:
        say(MSG_SUMMARY_NO_BACKUP)


# ---- Same-name agent scan ---------------------------------------------------

def frontmatter_name(path):
    """The value of the first name: line inside the frontmatter, or None."""
    try:
        text = read_bytes_text(path)
    except OSError:
        return None
    lines = text.split("\n")
    if lines[0] != "---":
        return None
    for line in lines[1:]:
        if line == "---":
            return None
        if line.startswith("name:"):
            value = line[len("name:"):].strip(" \t\n\r\v\f")
            if len(value) >= 3 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value
    return None


def find_agent_md_files(agents_dir):
    """Regular files and symlinks named *.md, anywhere under agents_dir, in the
    order `find` prints them: directory order, descending into a real directory
    right when it is met. Not sorted."""
    found = []
    try:
        entries = list(os.scandir(agents_dir))
    except OSError:
        return found
    for entry in entries:
        is_link = entry.is_symlink()
        if entry.name.endswith(".md") and (is_link or entry.is_file(follow_symlinks=False)):
            found.append(entry.path)
        if not is_link and entry.is_dir(follow_symlinks=False):
            found.extend(find_agent_md_files(entry.path))
    return found


def scan_samename(ctx, plan):
    """Read-only. Warns about files under <target>/agents/ that are not ours but
    whose frontmatter name equals one of our agent names."""
    t = ctx.target
    if not os.path.isdir(t + "/agents"):
        return
    names = []
    ours = set()
    for entry in plan:
        if entry.rel.startswith("agents/") and entry.rel.endswith(".md"):
            names.append(os.path.basename(entry.rel)[:-3])
            ours.add(t + "/" + entry.rel)
    for f in find_agent_md_files(t + "/agents"):
        if f in ours:
            continue
        nm = frontmatter_name(f)
        if not nm:
            continue
        for name in names:
            if name == nm:
                shown = f[len(t) + 1:] if f.startswith(t + "/") else f
                shown = "".join(c for c in shown if not (ord(c) < 32 or ord(c) == 127))
                say(MSG_FILE_SAMENAME, shown, name)
                ctx.samename += 1
                break


# ---- Install ----------------------------------------------------------------

def write_file(dest, data, mode):
    try:
        with open(dest, "wb") as fh:
            fh.write(data)
    except OSError:
        raise die_text(MSG_ERR_COPY, dest)
    os.chmod(dest, mode)


def same_bytes(dest, data):
    try:
        with open(dest, "rb") as fh:
            return fh.read() == data
    except OSError:
        return False


def manifest_body(plan):
    rels = sorted((e.rel for e in plan), key=byte_key)
    header = [
        "# model-routing manifest",
        "# Written by install.sh from claude-code-model-routing.",
        "# Paths below are relative to the Claude Code config directory.",
        "# install.sh --uninstall reads this list. Do not edit by hand.",
    ]
    return "\n".join(header + rels)


def do_install(ctx, plan):
    t = ctx.target
    added = replaced = unchanged = 0
    do_settings(ctx, "install", True, True)
    say(MSG_FILES_HEADING)
    for entry in plan:
        dest = t + "/" + entry.rel
        if not os.path.exists(dest):
            say(MSG_FILE_ADD, entry.rel)
            added += 1
            if not ctx.dry:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                write_file(dest, entry.data, entry.mode)
        elif same_bytes(dest, entry.data):
            say(MSG_FILE_UNCHANGED, entry.rel)
            unchanged += 1
        else:
            ensure_backup_dir(ctx)
            bk = ctx.backup_dir + "/" + entry.rel
            ctx.need_backup = True
            say(MSG_FILE_REPLACE, entry.rel, bk)
            replaced += 1
            if not ctx.dry:
                os.makedirs(os.path.dirname(bk), exist_ok=True)
                shutil.copy(dest, bk)
                write_file(dest, entry.data, entry.mode)

    scan_samename(ctx, plan)

    say(MSG_SETTINGS_HEADING, t + "/settings.json")
    do_settings(ctx, "install", ctx.dry, False)

    body = manifest_body(plan)
    say(MSG_MANIFEST_HEADING, ctx.manifest)
    if os.path.isfile(ctx.manifest) and read_bytes_text(ctx.manifest).rstrip("\n") == body:
        say(MSG_MANIFEST_UNCHANGED, ctx.manifest)
    else:
        say(MSG_MANIFEST_WRITE, ctx.manifest)
        if not ctx.dry:
            os.makedirs(t, exist_ok=True)
            with open(ctx.manifest, "w", encoding="utf-8", errors="surrogateescape") as fh:
                fh.write(body + "\n")
    if ctx.dry:
        for line in body.split("\n"):
            if not line.startswith("#"):
                say(MSG_MANIFEST_LINE, line)

    say(MSG_SUMMARY_INSTALL, added, replaced, unchanged, ctx.set_added, ctx.set_skipped)
    if ctx.samename > 0:
        say(MSG_SUMMARY_SAMENAME, ctx.samename)
    print_backup_summary(ctx)
    say(MSG_NEXT_HEADING)
    say(MSG_NEXT_INSTALL_1)
    say(MSG_NEXT_INSTALL_2)
    say(MSG_NEXT_INSTALL_3)


# ---- Uninstall --------------------------------------------------------------

def do_uninstall(ctx, plan):
    t = ctx.target
    removed = moved = gone = 0
    do_settings(ctx, "uninstall", True, True)
    if not os.path.isfile(ctx.manifest):
        say(MSG_MANIFEST_MISSING, ctx.manifest)
    else:
        paths = manifest_paths(read_bytes_text(ctx.manifest))
        # Refuse the whole run if any listed path could escape the target.
        for rel in paths:
            if unsafe_path(rel):
                raise die_text(MSG_ERR_BAD_MANIFEST_PATH, rel)
        say(MSG_FILES_HEADING)
        sources = {}
        for entry in plan:
            sources.setdefault(entry.rel, entry)
        for rel in paths:
            dest = t + "/" + rel
            if not os.path.exists(dest):
                say(MSG_FILE_GONE, rel)
                gone += 1
                continue
            entry = sources.get(rel)
            if entry is not None and same_bytes(dest, entry.data):
                say(MSG_FILE_REMOVE, rel)
                removed += 1
                if not ctx.dry:
                    try:
                        os.remove(dest)
                    except FileNotFoundError:
                        pass
            else:
                ensure_backup_dir(ctx)
                bk = ctx.backup_dir + "/" + rel
                ctx.need_backup = True
                say(MSG_FILE_MOVE, rel, bk)
                moved += 1
                if not ctx.dry:
                    os.makedirs(os.path.dirname(bk), exist_ok=True)
                    shutil.move(dest, bk)
        # Remove directories the install made, only when empty.
        if not ctx.dry:
            for rel in paths:
                d = os.path.dirname(rel)
                while d not in ("", ".", "/"):
                    try:
                        os.rmdir(t + "/" + d)
                    except OSError:
                        pass
                    d = os.path.dirname(d)

    say(MSG_SETTINGS_HEADING, t + "/settings.json")
    do_settings(ctx, "uninstall", ctx.dry, False)

    if os.path.isfile(ctx.manifest):
        say(MSG_MANIFEST_HEADING, ctx.manifest)
        say(MSG_MANIFEST_REMOVE, ctx.manifest)
        if not ctx.dry:
            try:
                os.remove(ctx.manifest)
            except FileNotFoundError:
                pass

    say(MSG_SUMMARY_UNINSTALL, removed, moved, gone, ctx.set_removed, ctx.set_skipped)
    print_backup_summary(ctx)
    say(MSG_NEXT_HEADING)
    say(MSG_NEXT_UNINSTALL_1)


# ---- Main -------------------------------------------------------------------

def resolve_choices(args, repo_dir, target, agents, defaults, interactive):
    """Defaults, then saved choices (unless --reset), then --agent, then the picker.
    Prints warnings and the source line. Returns the final choices or None when
    the picker was cancelled."""
    path = target + "/" + CHOICES_NAME
    choices = dict(defaults)
    saved = False
    if not args.reset:
        loaded, status, bad = load_choices(path, agents, defaults)
        if status == "bad":
            say(MSG_CHOICES_BAD_FILE, path)
        elif status == "ok":
            saved = True
            choices = loaded
            for name in bad:
                say(MSG_CHOICES_BAD_ENTRY, name, path)
    if args.agent_flags:
        choices = apply_agent_flags(choices, defaults, args.agent_flags)
    picked = False
    if interactive and not args.yes and not args.uninstall:
        def preview(candidate):
            return build_plan(repo_dir, candidate)
        result = run_picker(choices, preview, plain=args.plain, defaults=defaults,
                            target=target, saved=saved)
        if result is None:
            return None
        choices = result
        picked = True
    say(MSG_CHOICES_SOURCE, choices_source(path, saved, bool(args.agent_flags), picked))
    return choices


def run(args, env, repo_dir):
    say(MSG_PYTHON_VERSION, platform.python_version())
    if not args.uninstall:
        version = detect_claude_version()
        if version is None:
            raise die_text(MSG_ERR_NO_CLAUDE)
        say(MSG_CLAUDE_VERSION, version)

    target = resolve_target(env, os.getcwd())
    say(MSG_TARGET, target)
    prefix = hook_prefix(target, env)
    entries = hook_entries(prefix)
    if args.dry:
        say(MSG_DRY_BANNER)

    agents = list_agents(repo_dir)
    for name, _, _ in args.agent_flags:
        if name not in agents:
            raise UsageError(MSG_ERR_AGENT_UNKNOWN % (name, " ".join(agents)))
    defaults = load_agent_defaults(repo_dir, agents)
    plan = build_plan(repo_dir, defaults)

    settings_real = target + "/settings.json"
    if os.path.islink(settings_real):
        if not os.path.exists(settings_real):
            raise die_text(MSG_ERR_SETTINGS_DANGLING, target + "/settings.json")
        settings_real = os.path.realpath(settings_real)
    ctx = Ctx(target, settings_real, entries, args.dry, args.uninstall,
              time.strftime("%Y%m%d-%H%M%S"))

    if args.uninstall:
        saved, _status, _bad = load_choices(target + "/" + CHOICES_NAME, agents, defaults)
        plan = build_plan(repo_dir, saved)
    preflight(ctx, plan)

    if args.uninstall:
        do_uninstall(ctx, plan)
        return 0

    # Quiet settings.json check first, so a bad file exits before the picker shows.
    do_settings(ctx, "install", True, True)
    interactive = is_interactive(sys.stdin, sys.stdout, env)
    choices = resolve_choices(args, repo_dir, target, agents, defaults, interactive)
    if choices is None:
        say(MSG_CANCELLED)
        return 1
    plan = build_plan(repo_dir, choices)
    do_install(ctx, plan)
    return 0


def main(argv=None):
    if sys.version_info < (3, 9):
        sys.stderr.write(MSG_ERR_OLD_PYTHON % ("Python " + platform.python_version()))
        return 1
    argv = sys.argv[1:] if argv is None else argv
    repo_dir = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
    try:
        args = parse_args(argv)
        if args.help:
            sys.stdout.write(MSG_USAGE)
            sys.stdout.flush()
            return 0
        return run(args, os.environ, repo_dir)
    except UsageError as exc:
        sys.stdout.flush()
        sys.stderr.write(str(exc))
        sys.stderr.write(MSG_USAGE)
        return 2
    except InstallError as exc:
        sys.stdout.flush()
        if str(exc):
            sys.stderr.write(str(exc))
        return 1
    except KeyboardInterrupt:
        sys.stdout.flush()
        return 130
    except Exception as exc:  # one line, exit 1
        sys.stdout.flush()
        sys.stderr.write(MSG_ERR_UNEXPECTED % (str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__))
        return 1


if __name__ == "__main__":
    sys.exit(main())
