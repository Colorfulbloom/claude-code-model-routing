# Form factor research: rebuilt Routing Dashboard

Date of research: 2026-11-08 (from `date`, not guessed).
Method: WebFetch on official pages. Quotes are as WebFetch returned them, not checked against raw HTML. Pages that failed are listed under "Could not determine." Nothing under ~/.claude was read. Nothing was installed.

Lean, stated as inference: the local web server is the lowest-risk form factor for this app because it already exists. A Claude Code mod is a real new surface, but it lives inside Claude Code, so it can't be the whole dashboard. A desktop wrapper adds signing and notarization work for little gain on a single-user local tool.

## 1. Local web app (server on 127.0.0.1 plus browser)

Sources
- Jupyter Server security, https://jupyter-server.readthedocs.io/en/latest/operators/security.html. Quotes: "uses a token-based authentication that is **on by default**." "This token is logged to the terminal, so that you can copy/paste the URL into your browser." The page does not mention Origin checks, Host header checks or DNS rebinding.
- MCP transports, Security Warning, https://modelcontextprotocol.io/specification/2025-06-18/basic/transports. Quotes: "Servers **MUST** validate the `Origin` header on all incoming connections to prevent DNS rebinding attacks." "When running locally, servers **SHOULD** bind only to localhost (127.0.0.1) rather than all network interfaces (0.0.0.0)." This is MCP spec text, not OWASP. Use it as the closest vendor guidance on local servers.
- OWASP CSRF Prevention Cheat Sheet, https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html. Quotes: "If the Origin header is present, verify that its value matches the target origin." "If the Origin header is not present, verify that the hostname in the Referer header matches the target origin." "Sec-Fetch-Site is the most useful Fetch Metadata header for blocking CSRF-like cross-origin requests." "A user-friendly defense that is particularly well suited for AJAX or API endpoints is the use of a custom request header."
- OWASP DNS Rebinding page: redirected to community.owasp.org and not fetched. Its content is UNVERIFIED here.
- Langfuse self-hosting, https://langfuse.com/self-hosting (page labeled "Version: v4", no date shown). Quotes: "Docker Compose: For local use and testing." Required components listed: PostgreSQL, ClickHouse, Redis/Valkey, S3/Blob storage. "Single VM without high availability, scaling, or backups."
- Helicone self-host Docker, https://docs.helicone.ai/getting-started/self-host/docker (no date shown). Quotes: "To run all services in a single Docker container, you can use the `helicone-all-in-one` image." Dashboard at "http://localhost:3000". Postgres (5432) and ClickHouse (8123) listed as "Internal (can be restricted)".

Findings
- The browser UI pattern on localhost is common (Jupyter, Langfuse, Helicone). Jupyter's token is the auth model. Its docs do not describe Origin or Host checks, so this app should not copy Jupyter's model alone.
- Protections a local server needs, from the sources above: Origin check on every request (MCP spec, OWASP), bind to 127.0.0.1 only (MCP spec), a custom request header or Sec-Fetch-Site check for state-changing calls (OWASP). The existing app's edit path needs these most, since the server can write Claude Code settings files.

Form factor facts
- Pros: exists today. Reads local files with no extra runtime. Browser gives charts and live views through normal web code. Edits go through the same server.
- Cons: a user has to start a server and open a browser tab. Server must defend against DNS rebinding, CSRF and other local processes (MCP spec, OWASP).
- Install for end user: today's plugin path, then start the server. Inference: the plugin can start it, but see section 4 for limits.
- Offline: works. Source above does not claim network needs; the app reads local files only (inference from the brief).
- Read local files: yes. Server runs as the user.
- Effort: low, because the server exists (inference).
- Fit: high.

Heavier self-hosted stacks (Langfuse, Helicone) need Docker and several databases. That is far more than a single-user local tool needs (inference from the pages above).

## 2. Desktop app wrappers

### Tauri 2 (current docs at v2.tauri.app)
- Version and date: GitHub releases page, https://github.com/tauri-apps/tauri/releases, shows "tauri v3.0.0-alpha.6" marked "Latest" with a "06 Nov" date (year not shown). The same page lists tauri v2.12.5 released "21 Oct". Tauri 2 is still the documented stable line on v2.tauri.app. Check this before any decision, because a Tauri 3 alpha is now tagged on GitHub.
- Size: https://v2.tauri.app/start/ (page "Last updated: Nov 5, 2026"). Quote: "This means that a minimal Tauri app can be less than 600KB in size." Quote: "Tauri apps take advantage of the web view already available on every user's system." Size of this app's bundle: UNVERIFIED.
- Python sidecar: https://v2.tauri.app/distribute/sidecar/ (page "Last updated: Jun 15, 2026"). Quotes: "you can add the `externalBin` property to the `bundle` object." "Common use cases are Python CLI applications or API servers bundled using `pyinstaller`." The page has no Python code example. Spawning uses "shell().sidecar()" from Rust, or "Command.sidecar" from JavaScript.
- Signing: https://v2.tauri.app/distribute/ (page date not shown). Quote: "Both methods require code signing, and distributing outside the App Store also requires notarization." Windows: "Code signing Windows installers" (link card only).
- Auto-update: https://v2.tauri.app/plugin/updater/ (page "Last updated: Nov 28, 2025"). Quotes: "Automatically update your Tauri app with an update server or a static JSON." "Tauri's updater needs a signature to verify that the update is from a trusted source. This cannot be disabled." "This plugin requires a Rust version of at least 1.90." Platform table levels were lost in extraction, so per-OS support: UNVERIFIED.
- OS support: the sidecar and distribute pages do not state a full OS list. The updater page's table lists windows, linux, macos, android, ios (levels not extracted).
- Fit: Python backend runs as a sidecar. Needs Rust toolchain, per-platform binary with a target triple suffix (sidecar page: "a binary with the same name and a `-$TARGET_TRIPLE` suffix must exist"), signing and notarization, and a signed updater key. Effort: high (inference).

### Electron
- Version and date: https://github.com/electron/electron/releases shows v45.2.3 marked "Latest", published "04 Nov" (year inferred as 2026 from the asset timestamps; UNVERIFIED year). v46.0.0-alpha.7 shows "06 Nov".
- Process model: https://www.electronjs.org/docs/latest/tutorial/process-model. Quotes: "Each Electron app has a single main process, which acts as the application's entry point." "Each Electron app spawns a separate renderer process for each open BrowserWindow (and each web embed)." "Electron inherits its multi-process architecture from Chromium." Electron bundles Chromium and Node, so the app is large. Bundle size: UNVERIFIED.
- Signing: https://www.electronjs.org/docs/latest/tutorial/code-signing. Quotes: "Both Windows and macOS prevent users from running unsigned applications." "`Squirrel.Mac` requires the app to be signed for automatic updates to work at all." Windows: "Microsoft requires software to be signed with an 'extended validation' certificate."
- Python backend: not native. Would need a sidecar process (inference). Not verified in Electron docs.
- Fit: works, but heavier than Tauri and needs a Node layer for a Python app (inference).

### Wails
- https://wails.io/docs/introduction returned HTTP 403. Nothing verified: Go backend, webview per OS, version, size, signing all UNVERIFIED.

### pywebview
- https://pywebview.flowrl.com/ (no date). Quotes: "_pywebview_ is a lightweight BSD-licensed cross-platform wrapper around a webview component." "Compatible with Windows, macOS, Linux, and Android." "Current Version: 6.2.1". Backend per OS (Cocoa/WebKit, Qt, GTK, Edge WebView2): not on the page, UNVERIFIED.
- Python-native: the UI and server share one Python process. Signing and bundle size: UNVERIFIED for this tool. Packaging would likely pair with PyInstaller (inference).

### Flet
- https://flet.dev/docs/ (footer "Copyright © 2026 Appveyor Systems Inc." is the only date). Quotes: "a Python framework for building web, desktop, and mobile apps without prior experience in frontend development." "package it for Windows, macOS, Linux, iOS, or Android, or publish it to the web." Flutter rendering: not on the page, UNVERIFIED. Version: not on the page, UNVERIFIED. Charts: UNVERIFIED.
- Fit: means rebuilding the UI in Flet controls, not HTML. Inference: the existing HTML and JavaScript would not carry over.

### Briefcase (BeeWare)
- Redirected to https://briefcase.beeware.org/en/stable/. Quotes: "Briefcase is a tool for converting a Python project into a standalone native application." Platforms: "macOS, as a standalone .app", "Windows, as an MSI installer", "Linux, as a native system package". macOS signing and notarization: not on the page, UNVERIFIED. Version: UNVERIFIED.

### PyInstaller
- https://pyinstaller.org/en/stable/. Quotes: "PyInstaller bundles a Python application and all its dependencies into a single package." "PyInstaller is tested against Windows, macOS, and Linux." Version "6.22.3", changelog "6.22.3 (2026-09-12)".
- Signing and notarization: not on this page. Apple's notarization page (https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution) returned only its title to WebFetch, so the notarization wording is UNVERIFIED here.
- Fit: the packager, not a window. Pairs with pywebview, Tauri sidecar or Briefcase.

## 3. Terminal UI

- Textual: https://textual.textualize.io/. Quote: "Textual is a _Rapid Application Development_ framework for Python, built by Textualize.io." Latest version 8.2.8, "Jun 30, 2026", MIT (https://pypi.org/project/textual/). Charts or live widgets: the homepage does not list chart widgets, so charts are UNVERIFIED.
- textual-serve: https://github.com/Textualize/textual-serve. Quote: "With 3 lines of code, any Textual app can run in the browser." Quote: "There is no way for a malicious user to do anything the app-author didn't intend." The README has no Origin or Host caveat for localhost. Release date: not shown.
- Rich: https://github.com/Textualize/rich. Quote: "Rich is a Python library for rich text and beautiful formatting in the terminal." Quote: "Rich can render multiple flicker-free progress bars to track long-running tasks." Charts: not mentioned on the page, UNVERIFIED.
- Comparable: Claude-Code-Usage-Monitor, https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor, describes itself as "Real-time Claude Code usage monitor with predictions and warnings." Stack: Python 3.9+ with a terminal UI built on Rich. Install: "uv tool install claude-monitor".
- Fit: terminal can show tables and a live refresh. Charts and rich interaction are weaker. The owner's dashboard needs charts (per brief), so this is a fit only for a companion view (inference).

## 4. Claude Code integration surfaces

Plugins
- https://code.claude.com/docs/en/plugins (plugins overview). Quote: "A Claude Code plugin is a directory of skills, agents, hooks, MCP servers, or other components that Claude Code installs and loads as one unit."
- Components named on the page: skills, agents, hooks, a "hooks module", MCP servers. Monitors and LSP servers appear on the security page (below).
- Security: https://code.claude.com/docs/en/plugins/security. Quote: "A Claude Code plugin you install can execute arbitrary code on your machine with your user privileges." Monitors "run as background shell commands that Claude Code starts on its own when the session starts, when you reload plugins, or the first time a named skill runs."
- bin/ directory: Claude Code adds each enabled plugin's `bin/` directory to the PATH of the Bash tool's shell (security page).

Mods (new surface, in-process)
- https://code.claude.com/docs/en/plugins/mods/overview. Quote: "A mod is a [plugin] that changes how Claude Code looks and behaves." Quote: "Draw an interface you can use: a pane beside the transcript or a band above the prompt, with tabs, buttons, and text fields." Quote: "Mods aren't sandboxed."
- Mods API, https://code.claude.com/docs/en/plugins/mods/api. Quotes: "`$.fs`: `read(path)`, `write(path, text)`, `exists(path)`, `stat(path)`, and `list(path)` work on files and directories." "`$.process`: `run(['git', 'status'])` starts a command". "`$.http`: `fetch(url, init)` over `http` or `https`." "`$.settings`: `read()` resolves to all settings, merged into one object." `$.session.messages()` returns the transcript. A mod's calls run "with the same permissions as the user running Claude Code."
- Where mods draw (table on the overview page): terminal yes; Desktop Code tab yes except WSL; VS Code chat panel yes from extension 2.1.299; "claude -p" and Agent SDK hooks run but do not draw; cloud sessions do not draw; WSL sessions get no plugins.
- Version: terminal needs Claude Code v2.1.287 or later (overview page).
- Trust: "A mod is code that runs with your permissions." (overview page).
- Fit: a mod can read settings and the transcript, and draw a pane in Claude Code. It is not a standalone app. It runs only while Claude Code runs, and it can't draw a full browser dashboard. Inference: a mod pane could host a small live view or a link to the local server.

Hooks
- https://code.claude.com/docs/en/hooks. Quote: "user-defined shell commands, HTTP endpoints, MCP tool calls, LLM prompts, or subagents that execute automatically at specific points in Claude Code's lifecycle." HTTP hook: "send the event's JSON input as an HTTP POST request to a URL." Surfacing text: "return [`systemMessage`](#json-output) in JSON output." The hooks page does not say hooks run with user permissions; the security page says command hooks "run with your full user permissions".

Status line
- https://code.claude.com/docs/en/statusline. Quote: "The status line is a customizable bar at the bottom of Claude Code that runs any shell script you configure. It receives JSON session data on stdin and displays whatever your script prints." Fit: a one-line indicator only, not charts (inference).

Slash commands
- Mods can add commands: "`$.command.register`" (mods API). Plugins can ship skills that run as commands (plugins overview).

VS Code extension
- https://code.claude.com/docs/en/vs-code. Quote: "The VS Code extension provides a native graphical interface for Claude Code, integrated directly into your IDE." The page places the chat panel in the secondary sidebar, primary sidebar or editor area. The page does not describe an API for third-party extensions to add a webview. The only custom UI it covers is plugin mods, from extension 2.1.299. The page does not use the word "webview."

Can a plugin ship or launch a web UI? The plugin docs say plugins can ship MCP servers and background monitors (security page), and that these run with user permissions. The docs I read do not say a plugin can open a browser tab or host a web UI in a panel. UNVERIFIED for "open browser tab" and "host web UI in a panel". A plugin that starts the existing local server through a monitor is possible by the docs' own wording, but I did not find a doc page that states it.

## 5. Hosted or remote option (brief)

- Data would leave the machine: transcripts and settings are local files, so a hosted service would upload them (inference from the brief).
- Langfuse Cloud is "Fully managed by the Langfuse team." (https://langfuse.com/self-hosting). That is the hosted choice for that tool.
- Claude Code cloud sessions do not load local plugins: "A cloud session, including one in the browser at claude.ai/code, doesn't load the plugins in your local settings." (https://code.claude.com/docs/en/plugins).
- Effort: moderate to high for auth, multi-user data, and retention. Not researched further (out of scope for a local tool).

## 6. Comparable tools

| Tool | Form factor and stack | Source |
| --- | --- | --- |
| ccusage | Terminal CLI. "Analyze coding (agent) CLI token usage and costs from local data." Run with `npx ccusage@latest`. Has a "Claude Code status line for hooks (Beta)". Runtime not named on the page. | https://github.com/ryoppippi/ccusage |
| Claude-Code-Usage-Monitor | Python 3.9+, terminal UI on Rich. "Real-time Claude Code usage monitor with predictions and warnings." | https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor |
| Langfuse (self-host) | Web app in Docker. Needs Postgres, ClickHouse, Redis/Valkey and S3. Compose is "for local use and testing." | https://langfuse.com/self-hosting |
| Helicone (self-host) | Web dashboard on localhost:3000 in one Docker image. Postgres and ClickHouse inside. | https://docs.helicone.ai/getting-started/self-host/docker |

Not fetched: Jupyter, MLflow UI, Prefect UI, Datasette. The Datasette security page returned 404. Their form factors are UNVERIFIED here. Repo URLs for Langfuse and Helicone were not fetched; the URLs are the docs pages above.

## Comparison (inference, scout judgment)

| Form factor | Install for end user | Offline | Reads local files | Effort | Fit |
| --- | --- | --- | --- | --- | --- |
| Local web app (current) | Plugin plus start a server | Yes | Yes | Low | High |
| Tauri 2 plus Python sidecar | Signed installer, per-OS builds | Yes | Yes, via sidecar | High | Medium |
| Electron | Signed installer, large | Yes | Yes, via main process | High | Medium |
| pywebview or PyInstaller | Signed bundle per OS | Yes | Yes | Medium | Medium |
| Flet | Rebuild UI in Flet | Yes | Yes | High | Low |
| Textual or Rich (terminal) | pip or uv install | Yes | Yes | Medium | Low to medium (no proven charts) |
| Claude Code mod | Plugin install, inside Claude Code | Needs Claude Code | Yes (`$.fs`, `$.settings`) | Medium | Medium for a pane, low as a whole app |
| Hosted | Sign-in, web | No | No, data uploads | High | Low for this brief |

## Could not determine

- Wails: docs returned 403. Everything about Wails is UNVERIFIED.
- Datasette security page: 404.
- OWASP DNS Rebinding page: redirected, not fetched.
- Apple notarization page: only the title came back. Notarization wording is UNVERIFIED.
- Bundle sizes for Electron, pywebview, PyInstaller and Python sidecars.
- Flet's rendering engine, version and date.
- Briefcase signing and version.
- Textual chart widgets.
- Per-OS support for Tauri (updater table levels lost in extraction).
- Whether Tauri 3 alpha on GitHub changes the stable line. The v2 docs were current as of their dates above.
- Whether Claude Code plugins can open a browser tab or host a web view. Not found on the pages read.
- Electron and Tauri release dates in the year 2026 for the GitHub entries (the year is not shown on the page).
