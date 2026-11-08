# Platforms: macOS, Linux, Windows (2026-11-08)

## Recommendation

Ship macOS first, but build every OS call behind one small platform module so Linux is a short follow-up. Treat Windows as a separate project that waits for an owner yes.

- Linux shares the POSIX model the launcher and edit store rely on (flock, signals, `pass_fds`, dir-fd walk, 0600 modes). Its one real gap is the browser opener, which puts the URL with its key fragment into `xdg-open`'s argv. Effort S to M (inference).
- Windows breaks five load-bearing pieces at once: file lock, graceful stop, fd passing, the dir-fd safe-write walk, and 0600 privacy. Claude Code there also runs hooks under Git Bash or PowerShell, and `python3` is unreliable. Effort L (inference).
- So "all platforms" is feasible for Linux now and for Windows only with a second write path and a second launcher path. My recommendation is macOS first, Linux soon after, and Windows behind a decision.

Two changes make the key safe on every OS, so I recommend them for macOS now.

1. Pin Python below 3.15: `requires-python = ">=3.11,<3.15"` in the pyproject, plus a `.python-version` (for example 3.13) beside it, with `UV_PYTHON_PREFERENCE=only-managed` as spike 2 used. uv uses "The first Python version that is compatible with the requirement ... unless a version is otherwise requested, e.g., via a .python-version file" (https://docs.astral.sh/uv/concepts/python-versions/).
2. Stop putting the edit key in the opened URL. Open the page with a short-lived, single-use code, and let the page swap it for the key with one POST. Then argv exposure on any OS (3.15 `open`, Linux `xdg-open`, the browser's own command line on Windows) leaks only a spent code (inference; this is a design option, not spiked).

## Facts per concern

### Launcher

- `fcntl` is "Availability: Unix, not WASI" (https://docs.python.org/3/library/fcntl.html). Windows has `msvcrt.locking`, a byte-range lock that retries 10 times with `LK_LOCK` (https://docs.python.org/3/library/msvcrt.html).
- `os.kill` on Windows: any signal other than the console events "will cause the process to be unconditionally killed by the TerminateProcess API" (https://docs.python.org/3/library/os.html#os.kill). So SIGTERM is a hard kill there, and the launcher's 5-second graceful stop is gone. `CTRL_BREAK_EVENT` works only for children started with `CREATE_NEW_PROCESS_GROUP` (https://docs.python.org/3/library/subprocess.html).
- `start_new_session` and `pass_fds` are POSIX only. Windows passes handles through `STARTUPINFO.lpAttributeList` `handle_list` (subprocess docs). The `--launch-fd` pipe needs a Windows variant.
- uv: "uv ignores Ctrl-C events, deferring handling to the child process" on Windows; on Unix it forwards most signals (https://docs.astral.sh/uv/concepts/projects/run/). On Windows the server must handle its own shutdown.
- The launcher matches pids with `ps` (19-launcher.md). Linux can use `ps` or `/proc`. Windows needs `tasklist` or psutil (not verified).

### Browser opener and key exposure

| OS and Python | How the URL reaches the browser | URL in an argv? | Source |
|---|---|---|---|
| macOS, 3.11 to 3.14 | `os.popen("/usr/bin/osascript", "w")`, script on stdin | No | https://raw.githubusercontent.com/python/cpython/3.14/Lib/webbrowser.py |
| macOS, 3.15 | `['/usr/bin/open', url]` | Yes, fragment included | https://github.com/python/cpython/pull/146439 (merged into main May 6, 2026, per the PR page) |
| Linux | `xdg-open` through `BackgroundBrowser`, URL substituted into the command line | Yes | https://raw.githubusercontent.com/python/cpython/main/Lib/webbrowser.py |
| Windows | `os.startfile(url)` | Not in Python's argv; the browser's own command line likely holds it (inference) | same file |

The current launcher already uses `webbrowser.get().open(url)` (project fact I-14ae) and skips opening over SSH or with no display (19-launcher.md).

### Claude Code paths

- "On Windows, ~/.claude means %USERPROFILE%\.claude", and `CLAUDE_CONFIG_DIR` moves it; the same holds for `.claude.json` (https://code.claude.com/docs/en/settings.md, https://code.claude.com/docs/en/claude-directory.md).
- Managed settings: macOS `/Library/Application Support/ClaudeCode/managed-settings.json`; Linux and WSL `/etc/claude-code/managed-settings.json`; Windows `C:\Program Files\ClaudeCode\managed-settings.json` and registry `HKLM\SOFTWARE\Policies\ClaudeCode`. Source https://code.claude.com/docs/en/managed-settings, read through a search summary only. [NEEDS CONFIRMATION: exact Linux and Windows paths and the registry value name]
- The project folder rule ("every character other than letters and digits replaced by -") is documented for the scratchpad; the same rule for `projects/` on Windows, with a drive letter and backslashes, is inference (claude-directory.md).

### Files

- `os.replace`: "If successful, the renaming will be an atomic operation (this is a POSIX requirement)" (https://docs.python.org/3/library/os.html). On Windows it can fail with access denied while another process holds the target open without share-delete (2021 tracker report, https://www.python.org/pipermail/new-bugs-announce/2021-December/044766.html). Needs a retry loop there.
- `os.chmod` on Windows: "you can only set the file's read-only flag with it ... All other bits are ignored" (os docs). The 0600 backups, ledger and link file give no privacy on Windows without ACL work.
- "Currently dir_fd parameters only work on Unix platforms; none of them work on Windows" (os docs). edit_store's safe walk (O_NOFOLLOW per segment, dev/ino recheck; edit_store.py:88-89, 996-1008) has no direct Windows port.
- Symlinks on Windows need Developer Mode or privilege (os docs). Paths there are case-insensitive, so target ids from `realpath` need case folding (inference).

### Storage

- SQLite WAL: "All processes using a database must be on the same host computer; WAL does not work over a network filesystem" (https://www.sqlite.org/wal.html). Fine on local disks on all three OSes; a database under a WSL-mounted Windows drive or a network home folder is a risk (inference).

### Running inside Claude Code on Windows

- Hook commands run under "sh -c on macOS and Linux, Git Bash on Windows, or PowerShell when Git Bash isn't installed" (https://code.claude.com/docs/en/hooks.md). Without Git for Windows, Claude Code "uses PowerShell as the shell tool" (https://code.claude.com/docs/en/setup.md).
- Python's Windows docs say the `python3` command "is not meant to be widely used or recommended" (https://docs.python.org/3/using/windows.html). The plugin's `python3 bin/routing-dashboard` line and the PreToolUse guard (`if: "Bash(python3 *bin/<script>*)"`, project fact L-bd45) would need a Windows form.

## Effort table (inference)

| Concern | macOS | Linux | Windows |
|---|---|---|---|
| File lock | works | works | M, `msvcrt.locking` |
| Graceful stop | works | works | M, process group plus CTRL_BREAK, or an HTTP shutdown call |
| Detach and pass the URL pipe | works | works | M, creation flags and handle list |
| Browser opener | S, pin below 3.15 or use a one-time code | S, one-time code | S |
| Pid matching | works | works | M |
| 0600 privacy | works | works | L, ACLs |
| Atomic replace | works | works | M, retries |
| Safe-write walk | works | works | L, new design |
| Shell and python3 in the plugin | works | works | L |
| uv signals | works | works | M |

## UNVERIFIED

- Whether other local users can read another user's process argv on macOS 27.
- Whether Python 3.15 has shipped with the `open` change; the PR merge date is from the GitHub page.
- Linux and Windows managed-settings paths, read only through a search summary.
- `tasklist` or psutil as a pid matcher; Windows uv install and `--frozen` behaviour.
- The environment variable name `UV_PYTHON_PREFERENCE` (spike 2 used it; the uv page read here names the setting only).
- The one-time code design was not spiked.
