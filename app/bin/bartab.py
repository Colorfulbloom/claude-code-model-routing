#!/usr/bin/env python3
"""Start, find and stop the Bar Tab preview server for Claude Code sessions.

The bartab-preview and bartab-demo skills run this as
python3 "<checkout>/app/bin/bartab.py" [global options] [action] [args].
Python 3.9 standard library only, and no imports from the repo.

Global options come before the action: --data DIR (else env BARTAB_DATA, else
app/.data in the checkout), --default-project DIR (else the working folder),
--session ID, --demo (the server reads the demo build), --ingest-pace-ms N
(demo only, slows the first read so first run is watchable) and --real (the
server reads the owner's own Claude folder). Only start uses --demo and
--ingest-pace-ms. After the action only that action's own options are allowed,
so the skill's $ARGUMENTS can't override a global option.

--real refuses --demo, --ingest-pace-ms, --data and start --fixture, and ignores
BARTAB_DATA. It works out <config> the way store_paths.config_dir_default does
(CLAUDE_CONFIG_DIR, else $HOME/.claude), keeps its run state in
<config>/routing-dashboard/bartab/run/ and touches nothing else in <config>. It
starts the server as serve.py --real with no --data, --claude-dir or --store, and
passes the resolved <config> to it as CLAUDE_CONFIG_DIR so both agree. The server
writes its server.json into that same run folder. A demo server (state in the data
folder) and a real server can run side by side.

Actions
  start [--project DIR] [--no-open] [--port N] [--fixture NAME]   the default
  code [--project DIR] [--no-open]
  stop
  status        with --real, one more line holds the last pass times and the lag
  session-end   hidden, SessionEnd hook JSON on stdin
  guard         hidden, PreToolUse hook JSON on stdin

Run with --session (the skill path) the launcher always exits 0 and reports a
failure as one stdout line that starts "error: ", because a non-zero exit aborts
the skill. Run by hand it exits 1 for a failure and 2 for a usage error or a
missing uv, and writes the error to stderr.

One server serves every project. Run state lives in the data folder (in --real mode
the run folder), folder 0700 and files 0600: server.json (the server writes it,
this launcher adds and removes owners), port, launcher.lock and logs/server.log.
uv's cache, Python installs and the packages' environment live in <data>/uv/. With
--real they live in the checkout's app/.data/uv/ instead, because they hold code
only, and a sync lock there keeps a demo and a real launcher apart.

The server is started detached as <uv>/env/bin/python serve.py after
`uv sync --frozen`. Spike 3 showed `uv run` adds a second process and nothing else.
A one-time code is printed in the link, so the launcher never logs it.

The guard action is the PreToolUse hook's check, run as `python3 bartab.py guard`
with the hook JSON on stdin. It denies a Bash call that runs this launcher, runs
serve.py with --real, passes --real to either script (a line that names serve or
bartab and has --real counts, with $ expansions included, unless every command on
it only reads), runs a symlink to either script, names the real Claude folder or
.claude.json (paths under <home>/.claude/hooks/ are allowed), sets HOME or
CLAUDE_CONFIG_DIR beside either script, or runs text it can't read (a $(...) that
builds the command, a decoder piped into a shell). Allow is exit 0 with no output.
Deny is exit 2 with one reason line on stderr, the blocking form Claude Code
documents. It fails closed on any input it can't read, and it loads no heavy module
on that path.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import shlex
import sys

# --------------------------------------------------------------------------
# The PreToolUse guard
#
# It sits first in the file, with its own light imports, so `guard` starts without
# loading the launcher's heavy modules (http.client, webbrowser and the like). A
# hook runs on every Bash call, so the allow path has to stay fast. Python 3.9
# standard library only. A deny is exit 2 with one reason line on stderr, the form
# Claude Code documents as a blocking error. Any other exit code lets the call
# through, so every failure below ends in a deny.

GUARD_REASON = (
    "The Bar Tab launcher runs only from the user's /bartab-preview and "
    "/bartab-demo commands. Ask the user to run one of them instead."
)
GUARD_REAL_REASON = (
    "Agents never start Bar Tab on real data and never read or write the user's "
    "Claude folder or .claude.json. Ask the user to run /bartab-preview instead."
)
GUARD_OPAQUE_REASON = (
    "Agents don't run a command whose text is built or decoded at run time, "
    "because it could start Bar Tab on real data. Write the command out in full, "
    "or ask the user to run /bartab-preview instead."
)
GUARD_BLOCK_PREFIX = "Blocked by the Bar Tab guard. "
GUARD_BLOCK_EXIT = 2
GUARD_STDIN_LIMIT = 1024 * 1024
GUARD_HARD_SPLIT = re.compile(r"\n|;|&&|\|\||\||&")
GUARD_SOFT_SPLIT = re.compile(r"\$\(|`|\(|\)|\{|\}")
# Wrapper words the guard looks through, with the options that take a value.
GUARD_WRAPPERS: dict[str, tuple[str, ...]] = {
    "exec": (),
    "command": (),
    "nohup": (),
    "time": ("-f", "-o"),
    "nice": ("-n",),
    "sudo": ("-u", "-g", "-C", "-h", "-p", "-r", "-t", "-U", "-D"),
}
GUARD_ENV_VALUE_OPTIONS = ("-u", "-C", "--unset", "--chdir")
GUARD_ENV_STRING_OPTIONS = ("-S", "--split-string")
GUARD_SHELLS = ("bash", "sh", "zsh", "dash", "ksh")
GUARD_PYTHON = re.compile(r"python[0-9.]*")
GUARD_PYTHON_VALUE_OPTIONS = ("-W", "-X")
# uv and uvw options that take a separate value, for `uv [options] run [options]`.
GUARD_UV_VALUE_OPTIONS = (
    "--project",
    "--directory",
    "--config-file",
    "--cache-dir",
    "--python",
    "-p",
    "--with",
    "--with-editable",
    "--with-requirements",
    "--group",
    "--extra",
    "--package",
    "--env-file",
    "--index",
    "--default-index",
    "--index-url",
    "-i",
    "--find-links",
    "-f",
    "--exclude-newer",
    "--refresh-package",
    "--reinstall-package",
    "--upgrade-package",
    "-P",
)
GUARD_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
GUARD_SHELL_WORD = re.compile(r"\b(?:ba|z|da|k)?sh\b|\beval\b")
GUARD_PUNCTUATION = frozenset(";&|()<>")
GUARD_MARK = "bin/bartab.py"
GUARD_NAME = "bartab.py"
GUARD_MAX_DEPTH = 4
# Real-data rules. The scripts that take --real, the module names they run as, and
# commands that only read, which may carry --real as a search pattern.
GUARD_LAUNCHER_MODULE = re.compile(r"-m\s*bartab(?!\w)")
GUARD_SCRIPTS = ("serve.py", "bartab.py")
GUARD_MODULES = ("serve", "bartab")
# --real as a word, or as the default in ${X:---real} or ${X---real}.
GUARD_REAL_FLAG = re.compile(
    r"(?<![\w-])--real(?![\w-])|(?:(?<=:-)|(?<=:=)|(?<=\w-))--real(?![\w-])"
)
GUARD_SCRIPT_TEXT = re.compile(r"(?<![\w.-])(?:serve|bartab)\.py(?!\w)")
# A line names a target as serve.py or bartab.py, as -m serve, or as a bare module
# word (import serve). A path part such as .../model-routing-bartab/ doesn't count.
GUARD_TARGET_NAME = re.compile(
    r"(?<![\w.-])(?:serve|bartab)\.py(?!\w)"
    r"|-m\s*(?:serve|bartab)(?![\w-])"
    r"|(?<![\w./-])(?:serve|bartab)(?![\w/-])"
)
GUARD_SET_ENV = re.compile(r"(?<!\w)(?:CLAUDE_CONFIG_DIR|HOME)=")
GUARD_READ_ONLY = frozenset(
    {
        "grep",
        "egrep",
        "fgrep",
        "rg",
        "ag",
        "cat",
        "head",
        "tail",
        "less",
        "more",
        "wc",
        "ls",
        "nl",
        "diff",
        "cmp",
        "stat",
        "file",
    }
)
# Commands that can't run anything the guard has to see: the read-only set, plus
# echo and a few that print a path or filter text. sed and git are judged apart.
GUARD_INERT = GUARD_READ_ONLY | frozenset(
    {
        "echo",
        "true",
        "pwd",
        "which",
        "dirname",
        "basename",
        "realpath",
        "readlink",
        "sort",
        "uniq",
        "cut",
        "tr",
    }
)
GUARD_GIT_INERT = frozenset(
    {
        "diff",
        "log",
        "show",
        "status",
        "grep",
        "blame",
        "ls-files",
        "rev-parse",
        "add",
        "commit",
    }
)
GUARD_GIT_EXEC_OPTIONS = ("--ext-diff", "--textconv", "-O", "--open-files-in-pager")
GUARD_SED_PRINT = re.compile(r"(?:\d+|\$|/[^/]*/)(?:,(?:\+?\d+|\$|/[^/]*/))?p")
# Programs that run text they are given. A decoder beside one of them is a payload
# the guard can't read.
GUARD_SINKS = frozenset(
    {*GUARD_SHELLS, "eval", "xargs", "perl", "ruby", "node", "php", "uv", "uvw"}
)
GUARD_DECODER = re.compile(
    r"base64\s+(?:-[dD]|--decode)|b64decode|b32decode|a85decode|decodebytes"
    r"|fromhex|xxd\s+-\w*r|openssl\s+\w+[^|;&]*-d\b|\\x[0-9a-fA-F]{2}|\\[0-7]{3}"
    r"|\\u[0-9a-fA-F]{4}|\bchr\("
)
GUARD_DYNAMIC_CODE = re.compile(
    r"\b(?:exec|eval|compile|__import__|import_module|importlib|runpy|run_path"
    r"|run_module|subprocess|system|popen|Popen|spawn\w*|execv\w*)\b"
)
# Programs that can spell a flag or a path from pieces, inside a $(...).
GUARD_BUILDERS = frozenset(
    {
        "printf",
        "rev",
        "tr",
        "sed",
        "awk",
        "cut",
        "base64",
        "xxd",
        "perl",
        "python",
        "python3",
    }
)
GUARD_PURE_EXPANSION = re.compile(r"\$(?:\w+|\{[^}]*\})?")
GUARD_XARGS_VALUE_OPTIONS = (
    "-n",
    "-P",
    "-L",
    "-s",
    "-d",
    "-E",
    "-a",
    "--max-args",
    "--max-procs",
    "--max-lines",
    "--max-chars",
    "--delimiter",
    "--arg-file",
    "--eof",
)
GUARD_HOME_FORMS = ("~", "$HOME", "${HOME}")
GUARD_CONFIG_VARS = ("$CLAUDE_CONFIG_DIR", "${CLAUDE_CONFIG_DIR")
GUARD_PATH_TAIL = re.compile(r"[^\s;|&<>()]*")
GUARD_DOTCLAUDE_WORD = re.compile(r"(?:\./)?\.claude(?![\w-])(?P<rest>.*)")
# Python code that builds the real folder from the home folder, as Path.home() /
# ".claude" or os.path.join(os.environ["HOME"], ".claude"), after quotes are gone.
GUARD_PY_HOME = (
    r"(?:\bhome\(\)|environ\[HOME\]|(?:getenv|environ\.get)\(HOME(?:,[^)]*)?\)"
    r"|expanduser\((?:~)?\)|Path\(~\)(?:\.expanduser\(\))?)"
)
GUARD_PY_CLAUDE = re.compile(
    GUARD_PY_HOME
    + r"[)\]]*\s*(?:[,/+]+|\.joinpath\(|\.__truediv__\()\s*/?\.claude(?![\w-])"
)

GUARD_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # noqa: PTH100,PTH120
GUARD_OWN_SCRIPTS = (
    posixpath.join(GUARD_APP, "server", "serve.py"),
    posixpath.join(GUARD_APP, "bin", "bartab.py"),
)


def base_name(word: str) -> str:
    """The last part of a path, like Path(word).name, without importing pathlib."""
    return posixpath.basename(word.rstrip("/"))


def names_launcher(word: str) -> bool:
    """True when a word is the launcher script, by path or by bare file name."""
    return base_name(word) == GUARD_NAME or GUARD_MARK in word


def module_runs(arg: str, after: list[str]) -> bool:
    """True when python -m runs the launcher.

    arg is -m or -mMODULE and after holds the words past it. The launcher runs as
    bartab itself, or as runpy given the launcher's path.
    """
    if arg != "-m":
        return arg[2:] == "bartab"
    module = after[0] if after else ""
    if module == "bartab":
        return True
    return module == "runpy" and any(names_launcher(a) for a in after[1:])


def python_runs(args: list[str]) -> bool:
    """True when python run with args executes the launcher.

    Interpreter options are skipped. -m bartab counts. Any other -m and a plain read
    of the file (pytest, ruff and the like run through -m) don't. -c counts when its
    code names the launcher, and so does a script word or a < redirect that names it.
    """
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            i += 1
            break
        if not arg.startswith("-") or arg == "-":
            break
        if arg.startswith("-c"):
            code = arg[2:] or (args[i + 1] if i + 1 < len(args) else "")
            return GUARD_NAME in code
        if arg.startswith("-m"):
            return module_runs(arg, args[i + 1 :])
        i += 2 if arg in GUARD_PYTHON_VALUE_OPTIONS else 1
    if i < len(args) and names_launcher(args[i]):
        return True
    for k, arg in enumerate(args):
        if not arg.startswith("<"):
            continue
        target = arg.lstrip("<") or (args[k + 1] if k + 1 < len(args) else "")
        if names_launcher(target):
            return True
    return False


def shell_string(args: list[str]) -> str | None:
    """The command string of `sh -c STRING`, or None when args hold no -c."""
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-o", "+o"):
            i += 2
            continue
        if arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:]:
            return args[i + 1] if i + 1 < len(args) else None
        if arg.startswith(("-", "+")):
            i += 1
            continue
        return None
    return None


def uv_runs(args: list[str], depth: int) -> bool:
    """True when `uv [options] run [options] COMMAND` runs the launcher."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in GUARD_UV_VALUE_OPTIONS else 1
    if i >= len(args) or args[i] != "run":
        return False
    j = i + 1
    while j < len(args) and args[j].startswith("-"):
        if args[j] == "--script":
            return j + 1 < len(args) and names_launcher(args[j + 1])
        j += 2 if args[j] in GUARD_UV_VALUE_OPTIONS else 1
    if words_run(args[j:], depth):
        return True
    # An option this list doesn't know may have hidden the command word.
    return any(
        GUARD_PYTHON.fullmatch(base_name(word)) and python_runs(args[k + 1 :])
        for k, word in enumerate(args[i + 1 :], start=i + 1)
    )


def strip_wrappers(words: list[str]) -> tuple[list[str], str | None]:
    """Drop leading NAME=value words and wrapper words (GUARD_WRAPPERS, env).

    Returns the words left and, for `env -S STRING`, that string.
    """
    i = 0
    while i < len(words):
        name = base_name(words[i])
        if GUARD_ASSIGN.match(words[i]):
            i += 1
        elif name == "env":
            i += 1
            while i < len(words) and (
                words[i].startswith("-") or GUARD_ASSIGN.match(words[i])
            ):
                word = words[i]
                if word in GUARD_ENV_STRING_OPTIONS:
                    return [], " ".join(words[i + 1 :])
                if word.startswith("--split-string="):
                    return [], " ".join([word.partition("=")[2], *words[i + 1 :]])
                if word.startswith("-S"):
                    return [], " ".join([word[2:], *words[i + 1 :]])
                i += 2 if word in GUARD_ENV_VALUE_OPTIONS else 1
        elif name in GUARD_WRAPPERS:
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 2 if words[i] in GUARD_WRAPPERS[name] else 1
        else:
            break
    return words[i:], None


def words_run(words: list[str], depth: int) -> bool:
    """True when one simple command, already split into words, runs the launcher.

    Wrapper words and uv run are looked through. The command word left is the
    launcher itself, python (python3, python3.12, any path to one), a shell with
    -c, eval or uv.
    """
    rest, string = strip_wrappers(words)
    if string is not None:
        return command_runs(string, depth + 1)
    if not rest:
        return False
    exe, args = base_name(rest[0]), rest[1:]
    if exe == GUARD_NAME:
        return True
    if GUARD_PYTHON.fullmatch(exe):
        return python_runs(args)
    if exe in GUARD_SHELLS or exe == "eval":
        text = " ".join(args) if exe == "eval" else shell_string(args)
        return text is not None and command_runs(text, depth + 1)
    return exe in ("uv", "uvw") and uv_runs(args, depth)


def split_words(segment: str) -> list[str]:
    """Split a command segment into words with shell quoting.

    A segment that shlex can't read (a quote cut by the split) falls back to a
    plain split with the quote marks stripped.
    """
    try:
        return shlex.split(segment)
    except ValueError:
        return [w.strip("'\"") for w in segment.split()]


def squash(text: str) -> str:
    """Drop quote marks and backslashes, so ser""ve.py reads as serve.py."""
    return text.replace("'", "").replace('"', "").replace("\\", "")


def token_groups(command: str) -> list[list[str]] | None:
    """The simple commands of a line, split with shell quoting, as word lists.

    A quoted string that holds ; or | stays one word. Returns None when the line
    can't be tokenised, such as an unterminated quote.
    """
    lex = shlex.shlex(command.replace("`", ";"), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        tokens = list(lex)
    except ValueError:
        return None
    groups: list[list[str]] = [[]]
    for token in tokens:
        if set(token) <= GUARD_PUNCTUATION:
            groups.append([])
        else:
            groups[-1].append(token)
    return groups


def walk_command(
    command: str,
    depth: int,
    relevant: Callable[[str], bool],
    check: Callable[[list[str], int], bool],
) -> bool:
    """True when check holds for any simple command in a Bash command line.

    relevant is a cheap test on the line with its quotes dropped, so a line that
    can't matter is skipped. The line is split into command segments on newlines,
    ; && || | and &. Each segment is checked whole, and again after a split on
    $( ` ( ) { }, so a call inside a substitution or subshell is its own segment
    while a path built with $(...) or ${...} still counts for the segment around
    it. That split ignores quotes, so the line is also tokenised with shell quoting
    and each simple command checked again. A relevant line that is too deep, or has
    a shell word and can't be tokenised, counts as a hit.
    """
    if not relevant(squash(command)):
        return False
    if depth > GUARD_MAX_DEPTH:
        return True
    for hard in GUARD_HARD_SPLIT.split(command):
        for segment in [hard, *GUARD_SOFT_SPLIT.split(hard)]:
            if check(split_words(segment), depth):
                return True
    groups = token_groups(command)
    if groups is None:
        return GUARD_SHELL_WORD.search(command) is not None
    return any(check(group, depth) for group in groups)


def launcher_relevant(text: str) -> bool:
    """True when a line names the launcher, as bartab.py or as python -m bartab."""
    return GUARD_NAME in text or GUARD_LAUNCHER_MODULE.search(text) is not None


def command_runs(command: str, depth: int = 0) -> bool:
    """True when a Bash command line runs this launcher.

    The string after sh -c, bash -c, zsh -c or eval is checked as a command line
    of its own, up to GUARD_MAX_DEPTH levels deep.
    """
    return walk_command(command, depth, launcher_relevant, words_run)


def is_real_flag(word: str) -> bool:
    """True for the word --real, or --real=VALUE."""
    return word == "--real" or word.startswith("--real=")


def names_script(word: str) -> bool:
    """True when a word is serve.py or bartab.py, by path or by bare file name."""
    return base_name(word) in GUARD_SCRIPTS


def runs_module(words: list[str]) -> bool:
    """True when the words hold python -m serve (or -m bartab, or -mserve)."""
    for i, word in enumerate(words):
        if word == "-m" and i + 1 < len(words) and words[i + 1] in GUARD_MODULES:
            return True
        if word.startswith("-m") and word[2:] in GUARD_MODULES:
            return True
    return False


def code_words(words: list[str]) -> list[str]:
    """The code strings after -c (or glued as -cCODE), such as python -c CODE."""
    found: list[str] = []
    for i, word in enumerate(words):
        if word == "-c" and i + 1 < len(words):
            found.append(words[i + 1])
        elif word.startswith("-c") and len(word) > 2:  # noqa: PLR2004
            found.append(word[2:])
    return found


def words_real(words: list[str], depth: int) -> bool:
    """True when one simple command passes --real to serve.py or bartab.py.

    Wrappers, shells with -c, eval and uv run are looked through. After that any
    command that has the word --real and a word naming a script (or python -m
    serve, or -c code that names one) counts. Commands that only read, such as
    grep, may carry --real as a search pattern and don't.
    """
    rest, string = strip_wrappers(words)
    if string is not None:
        return command_real(string, depth + 1)
    if not rest:
        return False
    exe = base_name(rest[0])
    if exe in GUARD_SHELLS or exe == "eval":
        text = " ".join(rest[1:]) if exe == "eval" else shell_string(rest[1:])
        if text is not None:
            return command_real(text, depth + 1)
    if exe in GUARD_READ_ONLY:
        return False
    flag = any(is_real_flag(w) for w in rest[1:])
    if any(
        GUARD_SCRIPT_TEXT.search(code)
        and (flag or GUARD_REAL_FLAG.search(code) is not None)
        for code in code_words(rest[1:])
    ):
        return True
    return flag and (any(names_script(w) for w in rest) or runs_module(rest))


def command_real(command: str, depth: int = 0) -> bool:
    """True when a Bash command line passes --real to serve.py or bartab.py."""
    return walk_command(
        command,
        depth,
        lambda text: (
            GUARD_REAL_FLAG.search(text) is not None
            and any(name in text for name in (*GUARD_SCRIPTS, *GUARD_MODULES))
        ),
        words_real,
    )


# --------------------------------------------------------------------------
# The whole-line rules. The checks above look at one simple command at a time. A
# symlink, a variable or a $(...) can split a call across commands, so these look
# at the line as a whole.


class Simple:
    """One simple command of a Bash line, as the guard reads it."""

    __slots__ = ("piped", "tainted", "targets", "words")

    def __init__(self, piped: bool) -> None:
        """Start an empty command. piped is True when a | feeds it."""
        self.words: list[str] = []
        # Redirect targets and here-string words, kept apart from the command words.
        self.targets: list[str] = []
        self.piped = piped
        # True when a command substitution or process substitution sits in it.
        self.tainted = False


def split_lines(command: str) -> str:
    """Turn each newline outside quotes into ;, so each line is its own command."""
    out: list[str] = []
    quote = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and quote != "'" and i + 1 < len(command):
            out.append(command[i : i + 2])
            i += 2
            continue
        if quote:
            if ch == quote:
                quote = ""
            out.append(ch)
        elif ch in "'\"":
            quote = ch
            out.append(ch)
        else:
            out.append(" ; " if ch == "\n" else ch)
        i += 1
    return "".join(out)


def simple_commands(command: str) -> list[Simple] | None:
    """The simple commands of a line, read with shell quoting.

    A $(...) or <(...) stays inside the command that holds it, with its words
    joined in and the command marked tainted, so a path or flag built in a
    substitution still counts for the command around it. A backtick does the same.
    A plain ( ) subshell starts a new command. Redirect targets are kept apart.
    Returns None when the line can't be tokenised, such as an unterminated quote.
    """
    lex = shlex.shlex(split_lines(command), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        tokens = list(lex)
    except ValueError:
        return None
    cmds = [Simple(piped=False)]
    stack: list[bool] = []  # True for a substitution, False for a subshell
    skip = False
    for token in tokens:
        cur = cmds[-1]
        if skip:
            cur.targets.append(token)
            skip = False
        elif not token or not set(token) <= GUARD_PUNCTUATION:
            cur.words.append(token)
            if "$(" in token or "`" in token:
                cur.tainted = True
        else:
            skip = read_punctuation(token, cmds, stack)
    return [c for c in cmds if c.words or c.targets]


def read_punctuation(token: str, cmds: list[Simple], stack: list[bool]) -> bool:
    """Apply one run of ; & | ( ) < > to the command list. True skips the next word."""
    process = "<(" in token or ">(" in token
    redirect = ("<" in token or ">" in token) and not process
    for i, ch in enumerate(token):
        if ch == "(":
            cur = cmds[-1]
            via_process = process and token[i - 1 : i] in ("<", ">")
            sub = via_process or (
                i == 0 and bool(cur.words) and cur.words[-1].endswith("$")
            )
            stack.append(sub)
            if sub:
                cur.tainted = True
                if via_process:
                    cur.words.append("<(")  # a script that bash <(...) reads
            else:
                cmds.append(Simple(piped=False))
        elif ch == ")" and stack and not stack.pop():
            cmds.append(Simple(piped=False))
    if not redirect and not any(stack) and any(c in token for c in ";&|"):
        cmds.append(Simple(piped=token in ("|", "|&")))
    return redirect


def sed_inert(args: list[str]) -> bool:
    """True for sed -n SCRIPT FILE with a print script, which only reads."""
    options = [a for a in args if a.startswith("-")]
    script = [a for a in args if not a.startswith("-")]
    quiet = any(a in ("-n", "--quiet", "--silent") for a in options)
    plain = all(a in ("-n", "--quiet", "--silent", "-E", "-r") for a in options)
    return (
        quiet
        and plain
        and bool(script)
        and GUARD_SED_PRINT.fullmatch(script[0]) is not None
    )


def git_inert(args: list[str]) -> bool:
    """True for a git call that only reads or records, with no -c or pager hook."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if args[i].startswith(("-c", "--config-env", "--exec-path", "--upload-pack")):
            return False
        i += 2 if args[i] == "-C" else 1
    if i >= len(args) or args[i] not in GUARD_GIT_INERT:
        return False
    return not any(a.startswith(GUARD_GIT_EXEC_OPTIONS) for a in args[i + 1 :])


def cmd_inert(cmd: Simple, depth: int) -> bool:  # noqa: PLR0911
    """True when a simple command can't run anything but a read or an echo."""
    if cmd.tainted:
        return False
    words, string = strip_wrappers(cmd.words)
    if string is not None:
        return text_inert(string, depth + 1)
    if not words:
        return True
    exe, args = base_name(words[0]), words[1:]
    if exe in GUARD_SHELLS:
        text = shell_string(args)
        return text is not None and text_inert(text, depth + 1)
    if exe == "eval":
        return text_inert(" ".join(args), depth + 1)
    if exe == "git":
        return git_inert(args)
    if exe == "sed":
        return sed_inert(args)
    if exe == "rg":
        return not any(a.startswith("--pre") for a in args)
    return exe in GUARD_INERT


def text_inert(text: str, depth: int) -> bool:
    """True when every command in a command string is inert."""
    cmds = simple_commands(text)
    if cmds is None or depth > GUARD_MAX_DEPTH:
        return False
    return all(cmd_inert(c, depth) for c in cmds)


def is_cmdsub(word: str) -> bool:
    """True for a word that is, or starts, a command substitution."""
    return "$(" in word or "`" in word or word.endswith("$") or "<(" in word


def pure_expansion(word: str) -> bool:
    """True for a word that is only an expansion, such as $S, ${S} or $(...)."""
    return GUARD_PURE_EXPANSION.fullmatch(word) is not None or is_cmdsub(word)


def strip_uv(words: list[str]) -> list[str]:
    """The words after `uv [options] run [options]`, or the words unchanged."""
    if not words or base_name(words[0]) not in ("uv", "uvw"):
        return words
    i = 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in GUARD_UV_VALUE_OPTIONS else 1
    if i >= len(words) or words[i] != "run":
        return words
    j = i + 1
    while j < len(words) and words[j].startswith("-"):
        j += 2 if words[j] in GUARD_UV_VALUE_OPTIONS else 1
    return words[j:]


def effective_words(cmd: Simple) -> tuple[list[str], str | None]:
    """The command word and arguments with wrappers and uv run looked through."""
    words, string = strip_wrappers(cmd.words)
    return strip_uv(words), string


def script_words(words: list[str]) -> list[str]:
    """The command word, and for python or a shell the script word that follows."""
    if not words:
        return []
    out = [words[0]]
    exe = base_name(words[0])
    if not (GUARD_PYTHON.fullmatch(exe) or exe in GUARD_SHELLS):
        return out
    i = 1
    while i < len(words):
        word = words[i]
        if word.startswith(("-c", "-m")):
            break
        if word.startswith("-") and word != "-":
            i += 2 if word in (*GUARD_PYTHON_VALUE_OPTIONS, "-o", "+o") else 1
            continue
        out.append(word)
        break
    return out


def script_kind(word: str, cwd: str) -> str | None:
    """Name serve or bartab when word is a path that ends at one of the two scripts.

    A symlink counts, and so does a hard link to this checkout's own copy. Words
    with a variable or a glob, and words that don't exist, are None.
    """
    if not word or word.startswith("-") or any(ch in word for ch in "$`*?[{"):
        return None
    path = word if posixpath.isabs(word) else posixpath.join(cwd, word)
    try:
        if not os.path.lexists(path):
            return None
        name = base_name(os.path.realpath(path))
        if name in GUARD_SCRIPTS:
            return name[:-3]
        for own in GUARD_OWN_SCRIPTS:
            if os.path.exists(own) and os.path.samefile(path, own):  # noqa: PTH110,PTH121
                return base_name(own)[:-3]
    except (OSError, ValueError):
        return None
    return None


def script_kinds(cmds: list[Simple], cwd: str) -> set[str]:
    """The scripts (serve, bartab) that the command and script words end at."""
    kinds: set[str] = set()
    for cmd in cmds:
        for word in script_words(effective_words(cmd)[0]):
            kind = script_kind(word, cwd)
            if kind is not None:
                kinds.add(kind)
    return kinds


def dynamic_python(cmd: Simple) -> bool:
    """True for python code that can run text it builds, like exec or runpy."""
    words, _ = effective_words(cmd)
    if not words or not GUARD_PYTHON.fullmatch(base_name(words[0])):
        return False
    return any(GUARD_DYNAMIC_CODE.search(w) for w in words[1:])


def is_sink(cmd: Simple) -> bool:
    """True when a command runs the text it is given: a shell, eval, python, xargs."""
    words, _ = effective_words(cmd)
    if not words:
        return False
    exe = base_name(words[0])
    return exe in GUARD_SINKS or GUARD_PYTHON.fullmatch(exe) is not None


def xargs_opaque(args: list[str], depth: int) -> bool:
    """True when `xargs ARGS` runs a shell, eval or python on text it can't see."""
    i = 0
    repl = "{}"
    while i < len(args) and args[i].startswith("-"):
        arg = args[i]
        if arg in ("-I", "-J") and i + 1 < len(args):
            repl = args[i + 1]
            i += 2
            continue
        if arg.startswith(("-I", "-J")) and len(arg) > 2:  # noqa: PLR2004
            repl = arg[2:]
        elif arg.startswith("--replace="):
            repl = arg.partition("=")[2]
        i += 2 if arg in GUARD_XARGS_VALUE_OPTIONS else 1
    target = args[i:]
    if not target:
        return False
    exe = base_name(target[0])
    critical = [target[0], *script_words(target)[1:], *code_words(target[1:])]
    if exe in GUARD_SHELLS:
        critical.append(shell_string(target[1:]) or "")
    if any(repl in w for w in critical):
        return True
    return opaque_cmd(Simple(piped=False), depth + 1, target)


def opaque_text(text: str, depth: int) -> bool:
    """True when a nested command string runs something the guard can't read."""
    cmds = simple_commands(text)
    if cmds is None:
        return GUARD_REAL_FLAG.search(squash(text)) is not None or (
            GUARD_TARGET_NAME.search(squash(text)) is not None
        )
    return any(opaque_cmd(c, depth) for c in cmds)


def opaque_cmd(  # noqa: PLR0911, PLR0912
    cmd: Simple, depth: int, override: list[str] | None = None
) -> bool:
    """True when a command runs text that is built or fed in at run time.

    That is a command word that is a $(...) result, a shell or python with no
    script that a pipe feeds, a shell -c string or eval text built by a
    substitution, and xargs running a shell with the text in a placeholder.
    """
    if depth > GUARD_MAX_DEPTH:
        return True
    if override is None:
        words, string = effective_words(cmd)
        if string is not None:
            return opaque_text(string, depth + 1)
    else:
        words = strip_uv(strip_wrappers(override)[0])
    if not words:
        return False
    if is_cmdsub(words[0]):
        return True
    exe, args = base_name(words[0]), words[1:]
    if exe == "xargs":
        return xargs_opaque(args, depth)
    if exe == "eval":
        text = " ".join(args)
        return "$" in text or "`" in text or opaque_text(text, depth + 1)
    if exe in GUARD_SHELLS or exe in ("source", "."):
        string = shell_string(args)
        if string is not None:
            return is_cmdsub(string) or opaque_text(string, depth + 1)
        scripts = args[:1] if exe in ("source", ".") else script_words(words)[1:]
        return cmd.piped or any(is_cmdsub(w) for w in scripts)
    if GUARD_PYTHON.fullmatch(exe):
        code = code_words(args)
        if any(is_cmdsub(c) for c in code):
            return True
        script = [w for w in script_words(words)[1:] if w != "-"]
        module = any(w.startswith("-m") for w in args)
        if not code and not script and not module:
            return cmd.piped
        return any(is_cmdsub(w) for w in script)
    return False


def unknown_target(cmd: Simple) -> bool:
    """True when the command word or script word is only an expansion ($S, $(...))."""
    words, _ = effective_words(cmd)
    return any(pure_expansion(w) for w in script_words(words))


def assignment_text(cmds: list[Simple]) -> str:
    """The NAME=value words of a line, which may hold a path or a flag for later."""
    return " ".join(
        w for c in cmds for w in c.words if GUARD_ASSIGN.match(w) is not None
    )


def is_xargs(cmd: Simple) -> bool:
    """True when the command word is xargs, whose arguments come from a pipe."""
    words, _ = effective_words(cmd)
    return bool(words) and base_name(words[0]) == "xargs"


def builds_text(cmd: Simple) -> bool:
    """True when a command spells an option or path from pieces.

    That is an option word with an expansion in it (--$X), or a substitution that
    builds text with printf, tr, sed and the like.
    """
    if any(w.startswith("-") and ("$" in w or "`" in w) for w in cmd.words):
        return True
    return cmd.tainted and any(base_name(w) in GUARD_BUILDERS for w in cmd.words)


def line_reason(command: str, cwd: str) -> str | None:  # noqa: PLR0911
    r"""The deny reason from the whole-line rules, or None.

    The line is split into simple commands, and the ones that can only read or echo
    (grep, cat, git diff, sed -n 1,40p, echo) are set aside. If any command is left,
    the line is denied when
    - it has --real and names serve or bartab, or has a command or script word that
      is only an expansion, or runs python code that can run built text;
    - it names serve or bartab and gives an option word an expansion (--$X);
    - a command word, script word, or sh -c string is built by a $(...) or fed by a
      pipe, or a decoder (base64 -d, printf '\\x..') sits beside a program that runs
      text;
    - a command word or script word is a symlink to bartab.py (the launcher).
    A line that can't be read is denied when it has --real or names a script beside
    a shell word.
    """
    cmds = simple_commands(command)
    flag_text = squash(command)
    if cmds is None:
        shellish = GUARD_SHELL_WORD.search(command) is not None
        flag = GUARD_REAL_FLAG.search(flag_text) is not None
        names = GUARD_TARGET_NAME.search(flag_text) is not None
        if (flag and (names or shellish or "$" in command)) or (names and shellish):
            return GUARD_REAL_REASON
        return None
    live = [c for c in cmds if not cmd_inert(c, 0)]
    if not live:
        return None
    # A pipe, xargs or a file written by a redirect can carry the flag in from a
    # command that only echoes it.
    fed = any(c.piped or is_xargs(c) for c in live) or any(c.targets for c in cmds)
    source = cmds if fed else live
    text = squash(
        " ".join(
            [
                *(w for c in source for w in (*c.words, *c.targets)),
                assignment_text(cmds),
            ]
        )
    )
    flag = GUARD_REAL_FLAG.search(text) is not None
    names = GUARD_TARGET_NAME.search(text) is not None
    kinds = script_kinds(live, cwd)
    if flag and (
        names or kinds or any(unknown_target(c) or dynamic_python(c) for c in live)
    ):
        return GUARD_REAL_REASON
    if (names or kinds) and any(builds_text(c) for c in live):
        return GUARD_REAL_REASON
    if any(opaque_cmd(c, 0) for c in live):
        return GUARD_OPAQUE_REASON
    if GUARD_DECODER.search(command) and any(is_sink(c) for c in live):
        return GUARD_OPAQUE_REASON
    if "bartab" in kinds:
        return GUARD_REASON
    return None


def real_path_forms() -> list[tuple[str, bool]]:
    """The spellings of the real Claude folder, as (text, hooks may sit below it).

    ~, $HOME and ${HOME} plus the literal HOME from the environment, each with
    /.claude, then CLAUDE_CONFIG_DIR as a value and as a variable. Only the home
    forms (and a CLAUDE_CONFIG_DIR that is <home>/.claude) may have hooks/ below.
    """
    home = os.environ.get("HOME", "").rstrip("/")
    forms = [(f"{prefix}/.claude", True) for prefix in GUARD_HOME_FORMS]
    default = f"{home}/.claude" if home else ""
    if default:
        forms.append((default, True))
    value = os.environ.get("CLAUDE_CONFIG_DIR", "").rstrip("/")
    if value:
        forms.append((value, posixpath.normpath(value) == posixpath.normpath(default)))
    forms.extend((var, False) for var in GUARD_CONFIG_VARS)
    return forms


def clean_hooks_tail(below: str) -> bool:
    """True when the text below the Claude folder is hooks/ and stays inside it."""
    return (
        re.match(r"/hooks(?:/|$)", below) is not None
        and ".." not in below.split("/")
        and not any(ch in below for ch in "$`")
    )


def names_real_path(command: str) -> bool:
    """True when a command line names the real Claude folder or .claude.json.

    Paths under <home>/.claude/hooks/ are the one exemption, unless the same line
    passes --real, names any other real path, or reaches out of hooks/ with ..,
    a variable or a command substitution. A path that follows a - (as in
    ${CLAUDE_CONFIG_DIR:-$HOME/.claude}) counts. So does Python code that builds
    the folder from the home folder, as Path.home() / ".claude" does.
    """
    text = squash(command)
    flag = GUARD_REAL_FLAG.search(text) is not None
    if GUARD_PY_CLAUDE.search(text) is not None:
        return True
    for form, hooks_ok in real_path_forms():
        end = r"(?![A-Za-z0-9_])" if form in GUARD_CONFIG_VARS else r"(?![A-Za-z0-9_-])"
        pattern = r"(?<![\w.~/])" + re.escape(form) + end
        for match in re.finditer(pattern, text):
            tail = GUARD_PATH_TAIL.match(text, match.end())
            below = tail.group(0) if tail else ""
            if not (hooks_ok and clean_hooks_tail(below) and not flag):
                return True
    return False


def home_forms() -> set[str]:
    """The ways a command can say the home folder, without a trailing slash."""
    home = os.environ.get("HOME", "").rstrip("/")
    return {"~", "$HOME", "${HOME}", *([home] if home else [])}


def dotclaude_word(word: str) -> bool:
    """True for a relative .claude or .claude.json word, hooks/ below it aside."""
    match = GUARD_DOTCLAUDE_WORD.fullmatch(word)
    if match is None:
        return False
    return not clean_hooks_tail(match.group("rest"))


def cd_home_claude(cmds: list[Simple], cwd: str) -> bool:
    """True when a command in the home folder names a relative .claude path.

    The home folder is where the call starts (its cwd) or where cd, cd ~ or
    cd $HOME goes. A later cd elsewhere clears it.
    """
    home = os.environ.get("HOME", "").rstrip("/")
    at_home = bool(home) and os.path.realpath(cwd) == os.path.realpath(home)
    for cmd in cmds:
        words, _ = strip_wrappers(cmd.words)
        if words and base_name(words[0]) in ("cd", "pushd"):
            args = [w for w in words[1:] if not w.startswith("-") or w == "-"]
            at_home = not args or args[0].rstrip("/") in home_forms()
        elif at_home and any(dotclaude_word(w) for w in (*words, *cmd.targets)):
            return True
    return False


def sets_home_beside_script(command: str) -> bool:
    """True when a line sets HOME or CLAUDE_CONFIG_DIR and names a script."""
    text = squash(command)
    return (
        GUARD_SET_ENV.search(text) is not None
        and GUARD_SCRIPT_TEXT.search(text) is not None
    )


def guard_cwd(data: dict[str, object]) -> str:
    """The folder the call runs in, from the payload's cwd, else this process's."""
    cwd = data.get("cwd")
    if isinstance(cwd, str) and posixpath.isabs(cwd):
        return cwd
    try:
        return os.getcwd()  # noqa: PTH109
    except OSError:
        return "/"


def guard_reason(raw: str) -> str | None:  # noqa: PLR0911
    """The deny reason for the PreToolUse input text raw, or None to allow it.

    The input is the JSON object Claude Code sends on stdin. It needs a text
    tool_name and an object tool_input. A call to a tool other than Bash is
    allowed. A Bash call needs a text command, and is denied when it runs this
    launcher, passes --real to a script, names the real Claude folder or
    .claude.json, sets HOME or CLAUDE_CONFIG_DIR beside a script, or runs text the
    guard can't read. Anything that is not such an object is denied too, so the
    guard fails closed.
    """
    loaded = json.loads(raw)
    if not isinstance(loaded, dict):
        return GUARD_REASON
    # json.loads gives Any, and typing's cast would cost an import on the hot path.
    data: dict[str, object] = loaded  # pyright: ignore[reportUnknownVariableType]
    name = data.get("tool_name")
    loaded_input = data.get("tool_input")
    if not isinstance(name, str) or not isinstance(loaded_input, dict):
        return GUARD_REASON
    if name != "Bash":
        return None
    tool_input: dict[str, object] = loaded_input  # pyright: ignore[reportUnknownVariableType]
    command = tool_input.get("command")
    if not isinstance(command, str):
        return GUARD_REASON
    command = command.replace("\\\n", " ")  # a backslash-newline joins the line
    cwd = guard_cwd(data)
    if command_runs(command):
        return GUARD_REASON
    cmds = simple_commands(command)
    if (
        command_real(command)
        or names_real_path(command)
        or sets_home_beside_script(command)
        or (cmds is not None and cd_home_claude(cmds, cwd))
    ):
        return GUARD_REAL_REASON
    return line_reason(command, cwd)


def guard() -> int:
    """The PreToolUse hook action. Exit 0 with no output to allow the call.

    A denied call is exit 2 with one reason line on stderr, which Claude Code feeds
    back to the model. Every other outcome must also be a deny, because any other
    exit code lets the call through: input that can't be read, and any error
    inside the guard.
    """
    try:
        raw = sys.stdin.buffer.read(GUARD_STDIN_LIMIT + 1)
        if len(raw) > GUARD_STDIN_LIMIT:
            reason: str | None = GUARD_REASON
        else:
            reason = guard_reason(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        reason = GUARD_REASON
    if reason is None:
        return 0
    try:  # noqa: SIM105
        os.write(2, (GUARD_BLOCK_PREFIX + reason + "\n").encode())
    except OSError:
        pass  # no contextlib here, it costs start time; a closed stderr still blocks
    return GUARD_BLOCK_EXIT


if __name__ == "__main__" and sys.argv[1:] == ["guard"]:
    sys.exit(guard())


import contextlib  # noqa: E402
import errno  # noqa: E402
import fcntl  # noqa: E402
import http.client  # noqa: E402
import select  # noqa: E402
import shutil  # noqa: E402
import signal  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
import webbrowser  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import TYPE_CHECKING, NamedTuple, NoReturn, TypedDict, cast  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

sys.dont_write_bytecode = True

APP = Path(__file__).resolve().parent.parent
SERVER_DIR = APP / "server"
SERVE = SERVER_DIR / "serve.py"
NEVER_PORT = 8377
BUSY_MARKS = ("in use", "errno 48", "errno 98", "could not bind")
PORT_LOW = 47000
PORT_HIGH = 47999
IDLE_EXIT_MINUTES = 30
LOCK_WAIT = 300
END_LOCK_WAIT = 60
LAUNCH_WAIT = 30
STOP_WAIT = 5
SYNC_TIMEOUT = 900
SYNC_LOCK_WAIT = SYNC_TIMEOUT + 60
LOG_LIMIT = 1024 * 1024
LOG_KEEP = 256 * 1024
HTTP_TIMEOUT = 5
MAX_PORT = 65535
LAUNCH_LINE_MAX = 4096
SESSION_RE = re.compile(r"[A-Za-z0-9_-]{0,128}")
FIXTURE_RE = re.compile(r"[a-z0-9_]{1,40}")
PACE_RE = re.compile(r"[0-9]{1,5}")
HEALTH_TIME_RE = re.compile(r"[0-9][0-9T:.+Z-]{0,39}")
CODE_RE = re.compile(r"[A-Za-z0-9_.~-]{1,300}")
UV_URL = "https://docs.astral.sh/uv/getting-started/installation/"
USAGE = (
    "usage: bartab.py [--data DIR] [--default-project DIR] [--session ID] "
    "[--demo] [--ingest-pace-ms N] [--real] "
    "[start [--project DIR] [--no-open] [--port N] [--fixture NAME] | "
    "code [--project DIR] [--no-open] | stop | status]"
)
CONNECT_HINT = "Connect to the internet and run the command again."
SANDBOX_MESSAGE = "Claude Code's sandbox blocked the Bar Tab launcher."

GLOBAL_OPTIONS = ("--data", "--default-project", "--session", "--ingest-pace-ms")
GLOBAL_FLAGS = ("--demo", "--real")
# What --real refuses. start --fixture is refused where start reads its options.
REAL_REFUSES = ("--demo", "--ingest-pace-ms", "--data")
# action -> (options as {name: takes a value}, number of positional words)
ACTIONS: dict[str, tuple[dict[str, bool], int]] = {
    "start": (
        {"--project": True, "--no-open": False, "--port": True, "--fixture": True},
        0,
    ),
    "code": ({"--project": True, "--no-open": False}, 0),
    "stop": ({}, 0),
    "status": ({}, 0),
    "session-end": ({}, 0),
    "guard": ({}, 0),
    "_end": (
        {"--session": True, "--claude-pid": True, "--claude-started": True},
        0,
    ),
}
QUIET_ACTIONS = ("session-end", "guard", "_end")


class Usage(Exception):  # noqa: N818
    """A bad command line. The text is ours and holds no code or secret."""


class Fail(Exception):  # noqa: N818
    """A failure to report. The text is ours and holds no code or secret."""

    def __init__(self, message: str, code: int = 1) -> None:
        """Keep the message and the exit code a hand run uses."""
        super().__init__(message)
        self.code = code


def fail(message: str, code: int = 1) -> NoReturn:
    """Raise Fail with message."""
    raise Fail(message, code)


def usage(message: str) -> NoReturn:
    """Raise Usage with message."""
    raise Usage(message)


class Owner(TypedDict):
    """One Claude Code session that uses the server."""

    session: str
    claude_pid: int | None
    claude_started: str | None


@dataclass
class Record:
    """What server.json says, plus every key the launcher doesn't know."""

    port: int
    pid: int
    instance: str
    mint_secret: str
    owners: list[Owner]
    raw: dict[str, object]


@dataclass
class Launch:
    """The server's one JSON line on the launch fd."""

    port: int
    pid: int
    instance: str
    code: str
    project: str | None


class Ctx:
    """What one run knows, where the data is, who is calling, which folder it means."""

    def __init__(
        self,
        data: Path,
        session: str | None,
        default_project: Path,
        uv_root: Path | None = None,
    ) -> None:
        """Set the run state folder, the calling session (None by hand), the project.

        uv_root is where the uv folder lives. It defaults to the data folder, and
        --real moves it to the checkout's app/.data, so run state and uv are apart.
        """
        self.data = data
        self.session = session
        self.default_project = default_project
        self.skill = session is not None
        self.owner: Owner | None = None
        self.demo = False
        self.real = False
        self.config: Path | None = None
        self.pace_ms: str | None = None
        self.uv_root = uv_root if uv_root is not None else data

    @property
    def label(self) -> str:
        """What the messages call the server this run means."""
        return "Bar Tab preview (real data)" if self.real else "Bar Tab preview"

    @property
    def server_json(self) -> Path:
        """The shared server record."""
        return self.data / "server.json"

    @property
    def port_file(self) -> Path:
        """The port this data folder used last."""
        return self.data / "port"

    @property
    def log_file(self) -> Path:
        """The server's stdout and stderr."""
        return self.data / "logs" / "server.log"

    @property
    def uv_dir(self) -> Path:
        """Everything uv keeps: its cache, Python installs and the packages' env."""
        return self.uv_root / "uv"

    @property
    def python_bin(self) -> Path:
        """The packages' environment's Python."""
        return self.uv_dir / "env" / "bin" / "python"


def say(line: str) -> None:
    """Print one line."""
    sys.stdout.write(line + "\n")


def clean(text: object, limit: int = 80) -> str:
    """Make text one printable line of at most limit characters."""
    out = "".join(ch if ch.isprintable() else "?" for ch in str(text))
    return out if len(out) <= limit else out[:limit] + "..."


def as_dict(raw: object) -> dict[str, object] | None:
    """Return raw as a dict with str keys, or None."""
    if not isinstance(raw, dict):
        return None
    return cast("dict[str, object]", raw)


def is_int(value: object) -> bool:
    """True for an int that is not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def int_field(data: dict[str, object], key: str, high: int | None = None) -> int | None:
    """Return data[key] when it is an int from 1 up to high, else None."""
    value = data.get(key)
    if not isinstance(value, int) or not is_int(value) or value < 1:
        return None
    return value if high is None or value <= high else None


def str_field(data: dict[str, object], key: str) -> str | None:
    """Return data[key] when it is a non-empty string, else None."""
    value = data.get(key)
    return value if isinstance(value, str) and value else None


# --------------------------------------------------------------------------
# Command line


def parse_globals(
    argv: list[str], state: dict[str, bool]
) -> tuple[dict[str, str], list[str]]:
    """Read the global options. Returns (globals, the words left)."""
    glob: dict[str, str] = {}
    i = 0
    while i < len(argv) and (argv[i] in GLOBAL_OPTIONS or argv[i] in GLOBAL_FLAGS):
        name = argv[i]
        if name == "--session":
            state["skill"] = True
        if name in glob:
            usage(f"{name} was given twice")
        if name in GLOBAL_FLAGS:
            glob[name] = "1"
            i += 1
            continue
        if i + 1 >= len(argv):
            usage(f"{name} needs a value")
        glob[name] = argv[i + 1]
        i += 2
    return glob, argv[i:]


def parse_options(action: str, words: list[str]) -> dict[str, str | bool]:
    """Read the action's own options. Any other word is a usage error."""
    spec = ACTIONS[action][0]
    opts: dict[str, str | bool] = {}
    j = 0
    while j < len(words):
        word = words[j]
        if word not in spec:
            if word.startswith("--"):
                usage(f"{clean(word)} is not an option of {action}")
            usage(f"{action} takes no word after it, got {clean(word)}")
        if word in opts:
            usage(f"{word} was given twice")
        if spec[word]:
            if j + 1 >= len(words):
                usage(f"{word} needs a value")
            opts[word] = words[j + 1]
            j += 2
        else:
            opts[word] = True
            j += 1
    return opts


def parse_args(
    argv: list[str], state: dict[str, bool]
) -> tuple[dict[str, str], str, dict[str, str | bool]]:
    """Return (globals, action, options). Global options come first."""
    glob, rest = parse_globals(argv, state)
    action = "start"
    if rest and not rest[0].startswith("--"):
        action, rest = rest[0], rest[1:]
    if action not in ACTIONS:
        usage(f"unknown action {clean(action)}")
    if action in QUIET_ACTIONS:
        if state["skill"]:
            usage(f"{action} is not an action the skill can run")
        state["quiet"] = True
    return glob, action, parse_options(action, rest)


def parse_port(opts: dict[str, str | bool]) -> int | None:
    """Return --port as an int, or None when it was not given."""
    text = opts.get("--port")
    if text is None:
        return None
    if (
        not isinstance(text, str)
        or not re.fullmatch(r"[0-9]{1,5}", text)
        or not 1 <= int(text) <= MAX_PORT
    ):
        usage(f"--port needs a number from 1 to {MAX_PORT}")
    return int(text)


def config_dir() -> Path:
    """Return CLAUDE_CONFIG_DIR, else $HOME/.claude, absolute.

    The same rule as store_paths.config_dir_default, made absolute because the
    server runs from another working folder.
    """
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return Path.cwd() / env
    home = Path(os.environ.get("HOME", "~")).expanduser()
    return Path.cwd() / home / ".claude"


def real_run_dir(config: Path) -> Path:
    """The real server's run state folder inside the shared config folder."""
    return config / "routing-dashboard" / "bartab" / "run"


def data_folder(glob: dict[str, str]) -> Path:
    """Resolve the run state folder.

    --real gives <config>/routing-dashboard/bartab/run and ignores BARTAB_DATA.
    Otherwise it is --data, else BARTAB_DATA, else app/.data.
    """
    if "--real" in glob:
        return real_run_dir(config_dir())
    text = glob.get("--data") or os.environ.get("BARTAB_DATA") or ""
    return Path(text).resolve() if text else APP / ".data"


def uv_root_for(glob: dict[str, str]) -> Path | None:
    """Where the uv folder lives, or None for the data folder (the default)."""
    return APP / ".data" if "--real" in glob else None


def build_ctx(glob: dict[str, str]) -> Ctx:
    """Make the run's context from the global options."""
    session = glob.get("--session")
    if session is not None and not SESSION_RE.fullmatch(session):
        usage("--session takes letters, digits, - and _ (up to 128)")
    default = Path(glob.get("--default-project") or Path.cwd()).resolve()
    for name in REAL_REFUSES:
        if "--real" in glob and name in glob:
            usage(f"--real can't be used with {name}")
    ctx = Ctx(data_folder(glob), session, default, uv_root_for(glob))
    ctx.real = "--real" in glob
    if ctx.real:
        ctx.config = config_dir()
    ctx.demo = "--demo" in glob
    pace = glob.get("--ingest-pace-ms")
    if pace is not None:
        if not PACE_RE.fullmatch(pace):
            usage("--ingest-pace-ms takes a number of milliseconds, up to 99999")
        if not ctx.demo:
            usage("--ingest-pace-ms is for the demo build only, add --demo")
        ctx.pace_ms = pace
    return ctx


# --------------------------------------------------------------------------
# Processes


def run_ps(*args: str) -> str:
    """Run ps and return its stdout, or "" when it finds nothing."""
    try:
        proc = subprocess.run(  # noqa: S603
            ("ps", "-ww", *args),  # noqa: S607
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            text=True,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def ps_command(pid: int) -> str:
    """The command line of pid, or ""."""
    return run_ps("-o", "command=", "-p", str(pid))


def proc_info(pid: int) -> tuple[str, str] | None:
    """Return (stat, lstart) for a pid, or None when ps doesn't know it."""
    parts = run_ps("-o", "stat=", "-o", "lstart=", "-p", str(pid)).split(None, 1)
    if len(parts) <= 1:
        return None
    return parts[0], parts[1].strip()


def parent_of(pid: int) -> int:
    """The parent pid of pid, or 0."""
    text = run_ps("-o", "ppid=", "-p", str(pid))
    return int(text) if text.isdigit() else 0


def pid_exists(pid: int) -> bool:
    """True when a process with this pid exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def claude_identity() -> tuple[int | None, str | None]:
    """Return (claude_pid, claude_started) from env CLAUDE_PID, or (None, None).

    CLAUDE_PID is undocumented, so it counts only when it names one of this
    process's ancestors, up to 8 levels above the parent.
    """
    raw = os.environ.get("CLAUDE_PID", "")
    if not re.fullmatch(r"[0-9]{1,10}", raw) or int(raw) <= 0:
        return None, None
    pid = int(raw)
    cur = os.getppid()
    for _ in range(8):
        if cur == pid:
            info = proc_info(pid)
            return pid, (info[1] if info else None)
        if cur <= 1:
            break
        cur = parent_of(cur)
    return None, None


def owner_alive(owner: Owner) -> bool:
    """False only when the owner's Claude Code process is known to be gone."""
    pid = owner["claude_pid"]
    if pid is None:
        return True
    if not pid_exists(pid):
        return False
    info = proc_info(pid)
    if info is None or info[0].startswith("Z"):
        return False
    started = owner["claude_started"]
    return started is None or info[1] == started


def argv_has(command: str, *words: str) -> bool:
    """True when the words appear in command as whole, consecutive arguments.

    ps gives one joined line, so an argument counts when whitespace or the line
    edge sits on both sides of it. A path that merely contains another is no match.
    """
    needle = r"\s+".join(re.escape(word) for word in words)
    return re.search(rf"(?:^|\s){needle}(?=\s|$)", command) is not None


def process_ours(ctx: Ctx, rec: Record) -> bool:
    """True when rec's pid is alive and runs this checkout's serve.py on this data.

    The command line must hold the resolved path of SERVE as one argument and
    --data followed by this run's resolved data folder. A real-mode server has no
    --data, so it must hold --real instead, and a demo server must not. A process
    that only mentions serve.py, or serves another data folder, is not ours.
    """
    if not pid_exists(rec.pid):
        return False
    command = ps_command(rec.pid)
    if not argv_has(command, str(SERVE.resolve())):
        return False
    if ctx.real:
        return argv_has(command, "--real")
    return argv_has(command, "--data", str(ctx.data.resolve()))


def wait_gone(pid: int, seconds: float) -> bool:
    """Wait up to seconds for pid to end. A zombie counts as ended."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not pid_exists(pid):
            return True
        time.sleep(0.05)
    if not pid_exists(pid):
        return True
    info = proc_info(pid)
    return info is None or info[0].startswith("Z")


def stop_process(ctx: Ctx, rec: Record) -> bool:
    """SIGTERM, wait, SIGKILL. Signals only a pid that runs our serve.py.

    Returns True when a process was signalled.
    """
    if not process_ours(ctx, rec):
        return False
    try:
        os.kill(rec.pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    if not wait_gone(rec.pid, STOP_WAIT) and process_ours(ctx, rec):
        with contextlib.suppress(ProcessLookupError):
            os.kill(rec.pid, signal.SIGKILL)
        wait_gone(rec.pid, 3)
    return True


class Request(NamedTuple):
    """One request for http_call."""

    method: str
    path: str
    headers: dict[str, str]
    body: bytes | None


def http_call(
    port: int, request: Request, timeout: float = 2
) -> tuple[int, bytes] | None:
    """Send request to 127.0.0.1:port. Returns (status, body), or None on an error."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.putrequest(
            request.method, request.path, skip_host=True, skip_accept_encoding=True
        )
        conn.putheader("Host", f"127.0.0.1:{port}")
        for name, value in request.headers.items():
            conn.putheader(name, value)
        if request.body is not None:
            conn.putheader("Content-Length", str(len(request.body)))
        conn.endheaders(request.body)
        resp = conn.getresponse()
        return resp.status, resp.read(1024 * 1024)
    except (OSError, http.client.HTTPException):
        return None
    finally:
        conn.close()


def probe_http(port: int, timeout: float = 2) -> bool:
    """True when GET / on 127.0.0.1:port answers with any HTTP response."""
    return http_call(port, Request("GET", "/", {}, None), timeout) is not None


# --------------------------------------------------------------------------
# State under the data folder


def ensure_data(data: Path) -> None:
    """Make the data folder and its logs folder, mode 0700."""
    try:
        data.mkdir(mode=0o700, parents=True, exist_ok=True)
        data.chmod(0o700)
        logs = data / "logs"
        logs.mkdir(mode=0o700, exist_ok=True)
        logs.chmod(0o700)
    except (FileExistsError, NotADirectoryError):
        fail(f"the data path is not a folder: {clean(data, 200)}")


def ensure_real_run(config: Path, run: Path) -> None:
    """Make the real run folder and its logs folder, mode 0700.

    The config folder must already exist and is never created or changed. Each
    folder between it and the run folder is made only when missing, mode 0700, and
    an existing one keeps its mode. Nothing else in the config folder is touched.
    """
    if not config.is_dir():
        fail(f"there is no Claude folder to read at {clean(config, 200)}")
    try:
        missing: list[Path] = []
        folder = run
        while folder != config:
            if not folder.exists():
                missing.append(folder)
            folder = folder.parent
        for folder in reversed(missing):
            folder.mkdir(mode=0o700)
            folder.chmod(0o700)
        run.chmod(0o700)
        logs = run / "logs"
        logs.mkdir(mode=0o700, exist_ok=True)
        logs.chmod(0o700)
    except (FileExistsError, NotADirectoryError):
        fail(f"the run state path is not a folder: {clean(run, 200)}")


class Lock:
    """An exclusive flock on launcher.lock, polled every 50 ms."""

    def __init__(self, folder: Path, wait: float, name: str = "launcher.lock") -> None:
        """Take the lock file name in folder, or raise Fail after wait seconds."""
        self.fd = os.open(folder / name, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if not isinstance(exc, BlockingIOError) and exc.errno != errno.EACCES:
                    os.close(self.fd)
                    raise
            else:
                return
            if time.monotonic() >= deadline:
                os.close(self.fd)
                fail("another launcher is busy, try again")
            time.sleep(0.05)

    def release(self) -> None:
        """Drop the lock."""
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)


def write_private(path: Path, data: bytes) -> None:
    """Write bytes to a new 0600 file next to path, fsync, then rename it over path."""
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def valid_owners(raw: object) -> list[Owner]:
    """Keep the entries of raw that are owners."""
    owners: list[Owner] = []
    if not isinstance(raw, list):
        return owners
    for item in cast("list[object]", raw):
        entry = as_dict(item)
        if entry is None:
            continue
        pid = entry.get("claude_pid")
        started = entry.get("claude_started")
        session = entry.get("session")
        if pid is not None and not is_int(pid):
            continue
        owners.append(
            {
                "session": session if isinstance(session, str) else "",
                "claude_pid": cast("int | None", pid),
                "claude_started": started if isinstance(started, str) else None,
            }
        )
    return owners


def valid_record(raw: object) -> Record | None:
    """Return a Record when raw holds every field the launcher needs, else None."""
    data = as_dict(raw)
    if data is None:
        return None
    port = int_field(data, "port", MAX_PORT)
    pid = int_field(data, "pid")
    instance = str_field(data, "instance")
    secret = str_field(data, "mint_secret")
    if port is None or pid is None or instance is None or secret is None:
        return None
    return Record(port, pid, instance, secret, valid_owners(data.get("owners")), data)


def load_record(ctx: Ctx) -> Record | None:
    """Return the server record. A file that isn't one is deleted."""
    try:
        text = ctx.server_json.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        rec = valid_record(json.loads(text))
    except ValueError:
        rec = None
    if rec is None:
        forget(ctx)
        say("cleaned up an unreadable server record")
    return rec


def save_record(ctx: Ctx, rec: Record) -> None:
    """Write the record back with its current owners, keeping the keys it came with."""
    out = dict(rec.raw)
    out["owners"] = list(rec.owners)
    text = json.dumps(out, indent=2, sort_keys=True) + "\n"
    write_private(ctx.server_json, text.encode("utf-8"))


def forget(ctx: Ctx) -> None:
    """Delete server.json."""
    ctx.server_json.unlink(missing_ok=True)


def add_owner(rec: Record, owner: Owner) -> None:
    """Add owner unless the same process, or the same session with no pid, is in."""
    for have in rec.owners:
        if owner["claude_pid"] is not None:
            if (
                have["claude_pid"] == owner["claude_pid"]
                and have["claude_started"] == owner["claude_started"]
            ):
                return
        elif have["claude_pid"] is None and have["session"] == owner["session"]:
            return
    rec.owners.append(owner)


def caller_owner(ctx: Ctx) -> Owner:
    """The calling session as an owner. A run by hand has no session id."""
    if ctx.owner is None:
        pid, started = (None, None) if not ctx.skill else claude_identity()
        ctx.owner = {
            "session": ctx.session or "",
            "claude_pid": pid,
            "claude_started": started,
        }
    return ctx.owner


def live_server(ctx: Ctx) -> Record | None:
    """Return the running server's record, or None. A stale record is deleted.

    Owners whose Claude Code process is gone are dropped first. A server left
    with none is stopped. A server whose process is ours but whose port doesn't
    answer twice is stopped too.
    """
    rec = load_record(ctx)
    if rec is None:
        return None
    if not process_ours(ctx, rec):
        forget(ctx)
        return None
    keep = [o for o in rec.owners if owner_alive(o)]
    if len(keep) != len(rec.owners):
        rec.owners = keep
        if not keep:
            stop_process(ctx, rec)
            forget(ctx)
            say("stopped the server: every session that used it has ended")
            return None
        save_record(ctx, rec)
    if probe_http(rec.port) or probe_http(rec.port, timeout=HTTP_TIMEOUT):
        return rec
    stop_process(ctx, rec)
    forget(ctx)
    say("stopped a server that stopped answering")
    return None


# --------------------------------------------------------------------------
# uv and the packages


def find_uv() -> str:
    """Find uv in the contract's order, and fail with exit code 2 when there is none."""
    candidates: list[str | None] = [
        os.environ.get("BARTAB_UV"),
        str(APP.parent / ".tools" / "uv" / "uv"),
        shutil.which("uv"),
        str(Path.home() / ".local" / "bin" / "uv"),
        str(Path.home() / ".cargo" / "bin" / "uv"),
    ]
    for item in candidates:
        if item and Path(item).is_file() and os.access(item, os.X_OK):
            return item
    fail(
        f"uv not found. Install it from {UV_URL} or set BARTAB_UV to its path.",
        2,
    )


def uv_env(ctx: Ctx) -> dict[str, str]:
    """The environment for uv and the server, every uv folder under <data>/uv."""
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    uv = ctx.uv_dir
    env.update(
        {
            "UV_CACHE_DIR": str(uv / "cache"),
            "UV_PYTHON_INSTALL_DIR": str(uv / "python"),
            "UV_PROJECT_ENVIRONMENT": str(uv / "env"),
            "UV_PYTHON_BIN_DIR": str(uv / "bin"),
            "UV_PYTHON_INSTALL_BIN": "0",
            "UV_TOOL_DIR": str(uv / "tools"),
            "UV_PYTHON_PREFERENCE": "only-managed",
            "UV_NO_MODIFY_PATH": "1",
            "PYTHONPATH": str(SERVER_DIR),
        }
    )
    return env


def server_env(ctx: Ctx) -> dict[str, str]:
    """The server's environment.

    Real mode pins CLAUDE_CONFIG_DIR to the folder the launcher worked out, so both
    name the same one from any working folder.
    """
    env = uv_env(ctx)
    if ctx.real and ctx.config is not None:
        env["CLAUDE_CONFIG_DIR"] = str(ctx.config)
    return env


def last_line(text: str) -> str:
    """The last non-empty line of text, cleaned."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return clean(lines[-1], 200) if lines else ""


def python_step_failed(text: str) -> bool:
    """True when uv's output says the Python download or lookup failed."""
    low = text.lower()
    if "no interpreter found" in low:
        return True
    return "failed to download" in low and (
        "cpython" in low or "python-build-standalone" in low
    )


def network_failed(text: str) -> bool:
    """True when uv's output looks like a connection problem."""
    low = text.lower()
    marks = ("failed to download", "failed to fetch", "dns error", "error sending")
    return python_step_failed(text) or any(m in low for m in marks)


def run_sync(ctx: Ctx, uv: str) -> tuple[int, str]:
    """Run uv sync --frozen --no-dev for the checkout. Returns (exit code, output)."""
    argv = [uv, "sync", "--frozen", "--project", str(APP), "--no-dev"]
    try:
        proc = subprocess.run(  # noqa: S603
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=uv_env(ctx),
            timeout=SYNC_TIMEOUT,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        fail(f"uv sync took longer than {SYNC_TIMEOUT} seconds. {CONNECT_HINT}")
    except OSError as exc:
        fail(f"couldn't run uv ({clean(exc.strerror or type(exc).__name__)})")
    return proc.returncode, proc.stdout


def ensure_packages(ctx: Ctx, uv: str) -> None:
    """Run uv sync --frozen under the uv folder's own lock.

    A demo launcher and a real launcher that share the folder never sync at once.
    """
    ctx.uv_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = Lock(ctx.uv_dir, SYNC_LOCK_WAIT, "sync.lock")
    try:
        sync_packages(ctx, uv)
    finally:
        lock.release()


def sync_packages(ctx: Ctx, uv: str) -> None:
    """Run uv sync --frozen. The first run prints its two step lines."""
    marker = ctx.uv_dir / "synced"
    first = not marker.is_file()
    code, out = run_sync(ctx, uv)
    if code == 0:
        if not ctx.python_bin.exists():
            fail("uv finished but the Python environment is missing")
        if first:
            say("Download Python: done")
            say("Install the dashboard's packages: done")
            ctx.uv_dir.mkdir(parents=True, exist_ok=True)
            marker.write_text("ok\n", encoding="utf-8")
        return
    detail = last_line(out)
    if python_step_failed(out):
        say("Download Python: failed")
        fail(f"couldn't download Python ({detail}). {CONNECT_HINT}")
    if first:
        say("Download Python: done")
        say("Install the dashboard's packages: failed")
    hint = f" {CONNECT_HINT}" if network_failed(out) else ""
    fail(f"couldn't install the dashboard's packages ({detail}).{hint}")


# --------------------------------------------------------------------------
# Ports


def port_free(port: int) -> bool:
    """True when nothing listens on 127.0.0.1:port and the port can be bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # The server binds with SO_REUSEADDR, so a port in TIME_WAIT after a stop
        # counts as free. A port with a listener still fails to bind.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def saved_port(ctx: Ctx) -> int | None:
    """The port in <data>/port, when it is in range."""
    try:
        text = ctx.port_file.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if re.fullmatch(r"[0-9]{1,5}", text) and PORT_LOW <= int(text) <= PORT_HIGH:
        return int(text)
    return None


def pick_port(
    ctx: Ctx, asked: int | None, taken: tuple[int, ...] = ()
) -> tuple[int, str]:
    """Choose the port. Returns (port, note). Never 8377, even when asked.

    asked is --port. A busy asked port is an error. Otherwise the saved port is
    tried first, then the first free one from PORT_LOW to PORT_HIGH. taken lists
    ports that just failed.
    """
    note = ""
    if asked == NEVER_PORT:
        note = f"port {NEVER_PORT} is the old dashboard's, so another port was chosen"
        asked = None
    if asked is not None:
        if asked in taken or not port_free(asked):
            fail(f"port {asked} is in use")
        return asked, note
    first = saved_port(ctx)
    order = ([first] if first is not None else []) + list(
        range(PORT_LOW, PORT_HIGH + 1)
    )
    for port in order:
        if port != NEVER_PORT and port not in taken and port_free(port):
            return port, note
    fail(f"no free port from {PORT_LOW} to {PORT_HIGH}")


# --------------------------------------------------------------------------
# Browser


def browser_blocked() -> str | None:
    """Return None when a browser may open, else the line to say ("" for none)."""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return "Not opening a browser over SSH."
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        return "No display found, so no browser opened."
    return None


@contextlib.contextmanager
def quiet_output() -> Generator[None, None, None]:
    """Point stdout and stderr at /dev/null, so a browser can't keep our pipe open."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        saved = (os.dup(1), os.dup(2))
        null = os.open(os.devnull, os.O_RDWR)
    except OSError:
        yield
        return
    try:
        os.dup2(null, 1)
        os.dup2(null, 2)
        yield
    finally:
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        for fd in (null, *saved):
            os.close(fd)


def open_browser(url: str, no_open: bool) -> tuple[str, str]:
    """Return (state, line), state is opened, skipped or failed. line may be empty."""
    if no_open:
        return "skipped", ""
    reason = browser_blocked()
    if reason is not None:
        return "skipped", reason
    try:
        with quiet_output():
            # get().open, not webbrowser.open. The latter goes on to the next
            # browser when the first fails, which would open a second tab.
            ok = webbrowser.get().open(url, new=2)
    except Exception:  # noqa: BLE001
        ok = False
    if ok:
        return "opened", ""
    return "failed", "Couldn't open a browser."


def announce(port: int, code: str, no_open: bool) -> None:
    """Print the link and open it."""
    url = f"http://127.0.0.1:{port}/#/?code={code}"
    say(f"Bar Tab preview: {url}")
    state, line = open_browser(url, no_open)
    if state == "opened":
        say("Opened in your browser.")
    elif line:
        say(line)


# --------------------------------------------------------------------------
# Starting the server


def open_log(ctx: Ctx) -> int:
    """Open the server log for append. Over 1 MB it first keeps only its last 256 KB."""
    path = ctx.log_file
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        size = 0
    if size > LOG_LIMIT:
        with path.open("rb") as fh:
            fh.seek(size - LOG_KEEP)
            tail = fh.read()
        write_private(path, tail)
    return os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)


def last_log_line(ctx: Ctx) -> str:
    """The last line of the server log, cleaned."""
    try:
        with ctx.log_file.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 4096))
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return ""
    return last_line(text)


def kill_child(proc: subprocess.Popen[bytes]) -> None:
    """Kill a server that failed to start and reap it."""
    with contextlib.suppress(OSError):
        proc.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(5)


def parse_launch(line: str) -> Launch | None:
    """Parse the launch line, or None when it isn't the contract's shape."""
    try:
        data = as_dict(json.loads(line))
    except ValueError:
        return None
    if data is None:
        return None
    port = int_field(data, "port", MAX_PORT)
    pid = int_field(data, "pid")
    instance = str_field(data, "instance")
    code = str_field(data, "code")
    if port is None or pid is None or instance is None or code is None:
        return None
    if not CODE_RE.fullmatch(code):
        return None
    return Launch(port, pid, instance, code, str_field(data, "project"))


def read_launch_line(ctx: Ctx, fd: int, proc: subprocess.Popen[bytes]) -> Launch | None:
    """Read the server's one line from the pipe.

    Returns None when the server stopped before it was ready. The code in the
    line is handed back to the caller and kept out of every message.
    """
    buf = b""
    deadline = time.monotonic() + LAUNCH_WAIT
    while b"\n" not in buf and len(buf) < LAUNCH_LINE_MAX:
        left = deadline - time.monotonic()
        if left <= 0:
            kill_child(proc)
            fail(
                f"the server didn't report its address in {LAUNCH_WAIT} seconds; "
                f"see the log at {clean(ctx.log_file, 300)}"
            )
        ready, _, _ = select.select([fd], [], [], left)
        if not ready:
            continue
        chunk = os.read(fd, LAUNCH_LINE_MAX)
        if not chunk:
            break
        buf += chunk
    if b"\n" not in buf:
        kill_child(proc)
        return None
    launch = parse_launch(buf.split(b"\n", 1)[0].decode("ascii", "replace"))
    if launch is None:
        kill_child(proc)
        fail(
            "the server sent a reply the launcher doesn't know; "
            f"see the log at {clean(ctx.log_file, 300)}"
        )
    return launch


def spawn_once(
    ctx: Ctx,
    port: int,
    project: Path,
    fixture: str | None,
    extra: tuple[str, ...] = (),
) -> Launch | None:
    """Start one server on port. Returns None when it stopped before it was ready."""
    argv = [str(ctx.python_bin), "-B", str(SERVE)]
    # A real-mode server works out its own folders, so it gets no path to type.
    argv += ["--real"] if ctx.real else ["--data", str(ctx.data)]
    argv += [
        "--port",
        str(port),
        "--project-dir",
        str(project),
        "--idle-exit-minutes",
        str(IDLE_EXIT_MINUTES),
    ]
    if fixture:
        argv += ["--fixture", fixture]
    argv += extra
    r, w = os.pipe()
    try:
        argv += ["--launch-fd", str(w)]
        log_fd = open_log(ctx)
        try:
            proc = subprocess.Popen(  # noqa: S603
                argv,
                stdin=subprocess.DEVNULL,
                stdout=log_fd,
                stderr=log_fd,
                cwd=SERVER_DIR,
                env=server_env(ctx),
                start_new_session=True,
                pass_fds=(w,),
            )
        finally:
            os.close(log_fd)
    except BaseException:
        os.close(r)
        raise
    finally:
        os.close(w)
    try:
        return read_launch_line(ctx, r, proc)
    finally:
        os.close(r)


def bring_up(
    ctx: Ctx,
    project: Path,
    asked: int | None,
    fixture: str | None,
    extra: tuple[str, ...] = (),
) -> tuple[Launch, str]:
    """Start the server, trying up to 3 ports. Returns (launch, note)."""
    taken: tuple[int, ...] = ()
    note = ""
    for attempt in range(3):
        port, pick_note = pick_port(ctx, asked, taken)
        note = note or pick_note
        launch = spawn_once(ctx, port, project, fixture, extra)
        if launch is not None:
            return launch, note
        detail = last_log_line(ctx)
        busy = any(m in detail.lower() for m in BUSY_MARKS)
        if asked is not None or not busy or attempt == 2:  # noqa: PLR2004
            fail(
                "the server stopped before it was ready"
                + (f": {detail}" if detail else "")
            )
        taken += (port,)
    fail("no free port found")


def adopt_record(ctx: Ctx, launch: Launch, project: Path) -> Record:
    """Read the server's server.json, check it is this server's, add the caller.

    The launch line's project key is kept beside the folder it came from, because
    the mint call takes a project key and only the server knows how to make one.
    """
    deadline = time.monotonic() + 3
    rec = None
    while time.monotonic() < deadline:
        with contextlib.suppress(FileNotFoundError, ValueError):
            rec = valid_record(json.loads(ctx.server_json.read_text(encoding="utf-8")))
        if rec is not None:
            break
        time.sleep(0.05)
    if rec is None or rec.pid != launch.pid or rec.instance != launch.instance:
        with contextlib.suppress(OSError):
            os.kill(launch.pid, signal.SIGTERM)
        fail(
            "the server didn't write server.json; "
            f"see the log at {clean(ctx.log_file, 300)}"
        )
    rec.raw["launcher_project_dir"] = str(project)
    rec.raw["launcher_project"] = launch.project
    add_owner(rec, caller_owner(ctx))
    save_record(ctx, rec)
    return rec


def mint_code(rec: Record, project: Path) -> str:
    """Ask the running server for a fresh single-use code.

    The code names the project key the server gave this folder when it started.
    Any other folder gets a code with no project.
    """
    key = None
    if rec.raw.get("launcher_project_dir") == str(project):
        key = str_field(rec.raw, "launcher_project")
    body = json.dumps({"project": key}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Bartab-Mint": rec.mint_secret,
    }
    request = Request("POST", "/api/access/mint", headers, body)
    result = http_call(rec.port, request, timeout=HTTP_TIMEOUT)
    if result is None:
        fail("the server didn't answer the request for a new link")
    status, payload = result
    if status != 200:  # noqa: PLR2004
        fail(f"the server refused the request for a new link (status {status})")
    try:
        data = as_dict(json.loads(payload.decode("utf-8")))
    except (ValueError, UnicodeDecodeError):
        data = None
    code = data.get("code") if data else None
    if not isinstance(code, str) or not CODE_RE.fullmatch(code):
        fail("the server sent a new link the launcher doesn't know")
    return code


# --------------------------------------------------------------------------
# Actions


def resolve_project(ctx: Ctx, opts: dict[str, str | bool]) -> Path:
    """The project folder, --project (relative to the default) or the default."""
    word = opts.get("--project")
    if isinstance(word, str):
        path = Path(word)
        if not path.is_absolute():
            path = ctx.default_project / path
    else:
        path = ctx.default_project
    path = path.resolve()
    if not path.is_dir():
        fail(f"not a folder: {clean(word if isinstance(word, str) else path, 200)}")
    return path


def do_start(ctx: Ctx, opts: dict[str, str | bool]) -> None:
    """Start the server, or add this session to the one that is running."""
    project = resolve_project(ctx, opts)
    asked = parse_port(opts)
    fixture = opts.get("--fixture")
    if fixture is not None and (
        not isinstance(fixture, str) or not FIXTURE_RE.fullmatch(fixture)
    ):
        usage("--fixture takes lowercase letters, digits and _")
    extra: tuple[str, ...] = ("--demo",) if ctx.demo else ()
    if ctx.pace_ms is not None:
        extra += ("--ingest-pace-ms", ctx.pace_ms)
    no_open = "--no-open" in opts
    rec = live_server(ctx)
    if rec is not None:
        add_owner(rec, caller_owner(ctx))
        save_record(ctx, rec)
        code = mint_code(rec, project)
        announce(rec.port, code, no_open)
        if (asked and asked != rec.port) or fixture:
            say("already running; run stop first to change the port or fixture")
        return
    uv = find_uv()
    ensure_packages(ctx, uv)
    launch, note = bring_up(
        ctx, project, asked, fixture if isinstance(fixture, str) else None, extra
    )
    adopt_record(ctx, launch, project)
    with contextlib.suppress(OSError):
        write_private(ctx.port_file, f"{launch.port}\n".encode("ascii"))
    if note:
        say(note)
    announce(launch.port, launch.code, no_open)


def do_code(ctx: Ctx, opts: dict[str, str | bool]) -> None:
    """Mint a fresh code for the running server and show the link."""
    project = resolve_project(ctx, opts)
    rec = live_server(ctx)
    if rec is None:
        fail(f"no {ctx.label} is running; run start")
    add_owner(rec, caller_owner(ctx))
    save_record(ctx, rec)
    announce(rec.port, mint_code(rec, project), "--no-open" in opts)


def do_stop(ctx: Ctx) -> None:
    """Stop the server whatever its owners."""
    rec = load_record(ctx)
    if rec is not None and stop_process(ctx, rec):
        say(f"Stopped Bar Tab (port {rec.port}).")
    else:
        say(f"No {ctx.label} is running.")
    forget(ctx)


def do_status(ctx: Ctx) -> None:
    """Say whether the server runs, where, and for how many sessions."""
    rec = live_server(ctx)
    if rec is None:
        say(f"No {ctx.label} is running.")
        return
    started = rec.raw.get("started")
    say(
        f"Bar Tab preview  http://127.0.0.1:{rec.port}/  "
        f"started {started if isinstance(started, str) else 'unknown'}  "
        f"sessions {len(rec.owners)}" + ("  real data" if ctx.real else "")
    )
    if ctx.real:
        say(health_line(ctx))


def health_number(raw: dict[str, object], key: str) -> str:
    """Return one health number as text: a whole number of milliseconds, else "none"."""
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return "none"
    return f"{value} ms"


def health_line(ctx: Ctx) -> str:
    """The status line for the server's last health report, numbers only.

    The server writes health.json in the run folder after a pass, at most every 30
    seconds. The line holds the report's time and three numbers, never a path, so the
    owner can paste it into a chat.
    """
    try:
        text = (ctx.data / "health.json").read_text(encoding="utf-8")
        raw = as_dict(json.loads(text))
    except (OSError, ValueError):
        raw = None
    if raw is None:
        return "Health  no report yet"
    at = raw.get("at")
    stamp = at if isinstance(at, str) and HEALTH_TIME_RE.fullmatch(at) else "unknown"
    return (
        f"Health  at {stamp}  "
        f"hot pass {health_number(raw, 'hot_pass_ms')}  "
        f"cold pass {health_number(raw, 'cold_pass_ms')}  "
        f"lag {health_number(raw, 'lag_ms')}"
    )


def run_locked(ctx: Ctx, work: str, opts: dict[str, str | bool]) -> None:
    """Run one action under the launcher lock."""
    if ctx.real and ctx.config is not None:
        ensure_real_run(ctx.config, ctx.data)
    else:
        ensure_data(ctx.data)
    lock = Lock(ctx.data, LOCK_WAIT)
    try:
        if work == "start":
            do_start(ctx, opts)
        elif work == "code":
            do_code(ctx, opts)
        elif work == "stop":
            do_stop(ctx)
        else:
            do_status(ctx)
    finally:
        lock.release()


# --------------------------------------------------------------------------
# The SessionEnd hook


def read_stdin_capped() -> bytes:
    """Read up to 64 KB from stdin, giving up after 0.3 s."""
    try:
        fd = sys.stdin.fileno()
    except (OSError, ValueError, AttributeError):
        return b""
    buf = b""
    deadline = time.monotonic() + 0.3
    while len(buf) < 65536:  # noqa: PLR2004
        left = deadline - time.monotonic()
        if left <= 0:
            break
        try:
            ready, _, _ = select.select([fd], [], [], left)
            if not ready:
                break
            chunk = os.read(fd, 65536 - len(buf))
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
    return buf


def session_end(glob: dict[str, str]) -> None:
    """Hand the cleanup to a detached worker and return at once. Never prints."""
    try:
        data = as_dict(json.loads(read_stdin_capped().decode("utf-8")))
    except (ValueError, UnicodeDecodeError):
        return
    if data is None:
        return
    session = data.get("session_id")
    if not isinstance(session, str) or not session or not SESSION_RE.fullmatch(session):
        return
    if data.get("reason") in ("clear", "resume"):
        return
    folder = data_folder(glob)
    if not (folder / "server.json").is_file():
        return
    pid, started = claude_identity()
    # The worker is told the same way this run was, so --real never gets --data.
    where = ["--real"] if "--real" in glob else ["--data", str(folder)]
    subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-B",
            str(Path(__file__).resolve()),
            *where,
            "_end",
            "--session",
            session,
            "--claude-pid",
            str(pid) if pid else "",
            "--claude-started",
            started or "",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def end_session(glob: dict[str, str], opts: dict[str, str | bool]) -> None:
    """The detached worker. Drop this session's owners, stop a server left with none."""
    session = opts.get("--session")
    if not isinstance(session, str) or not SESSION_RE.fullmatch(session):
        return
    ctx = Ctx(data_folder(glob), None, Path.cwd(), uv_root_for(glob))
    ctx.real = "--real" in glob
    if not ctx.data.is_dir():
        return
    raw_pid = opts.get("--claude-pid")
    claude_pid = (
        int(raw_pid) if isinstance(raw_pid, str) and raw_pid.isdigit() else None
    )
    started = opts.get("--claude-started")
    claude_started = started if isinstance(started, str) and started else None
    lock = Lock(ctx.data, END_LOCK_WAIT)
    try:
        rec = load_record(ctx)
        if rec is None:
            return
        if not process_ours(ctx, rec):
            forget(ctx)
            return
        keep: list[Owner] = []
        for owner in rec.owners:
            mine = (
                claude_pid is not None
                and owner["claude_pid"] == claude_pid
                and owner["claude_started"] == claude_started
            ) or (
                bool(session)
                and owner["claude_pid"] is None
                and owner["session"] == session
            )
            if not mine and owner_alive(owner):
                keep.append(owner)
        if len(keep) == len(rec.owners):
            return
        rec.owners = keep
        if keep:
            save_record(ctx, rec)
            return
        stop_process(ctx, rec)
        forget(ctx)
    finally:
        lock.release()


# --------------------------------------------------------------------------
# Entry point


def report(state: dict[str, bool], message: str, code: int) -> int:
    """Print an error. The skill path prints to stdout and exits 0."""
    if state["quiet"]:
        return 0
    if state["skill"]:
        say("error: " + message)
        return 0
    sys.stderr.write("error: " + message + "\n")
    return code


def run(argv: list[str], state: dict[str, bool]) -> int:
    """Parse the command line and run the action."""
    if any(word in ("-h", "--help") for word in argv):
        say(USAGE)
        return 0
    glob, action, opts = parse_args(argv, state)
    if action == "guard":
        return guard()
    if action == "session-end":
        session_end(glob)
        return 0
    if action == "_end":
        end_session(glob, opts)
        return 0
    ctx = build_ctx(glob)
    if ctx.real and "--fixture" in opts:
        usage("--real can't be used with --fixture")
    run_locked(ctx, action, opts)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the launcher and turn every failure into one error line."""
    args = list(sys.argv[1:] if argv is None else argv)
    state = {"skill": False, "quiet": False}
    try:
        return run(args, state)
    except Usage as exc:
        return report(state, f"{exc}. {USAGE}", 2)
    except Fail as exc:
        return report(state, str(exc), exc.code)
    except PermissionError:
        return report(state, SANDBOX_MESSAGE, 1)
    except KeyboardInterrupt:
        return report(state, "interrupted", 1)
    except Exception as exc:  # noqa: BLE001
        return report(state, "unexpected " + type(exc).__name__, 1)
    finally:
        with contextlib.suppress(OSError, ValueError):
            sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
