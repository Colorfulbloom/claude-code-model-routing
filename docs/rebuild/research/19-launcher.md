# Scout report: launcher lifecycle (2026-11-08), condensed by main session

Recommendation: one server per Claude Code data folder serving every project (one SQLite writer, one port, one ingest task); launcher stays the only entry point; keep edit key out of logs/argv; keep PreToolUse guard and SessionEnd hook.

Current (plugins/routing-dashboard/bin/routing-dashboard): actions 67-79; data folder via --data (188); state servers/<id>.json, servers/.lock, logs/<id>.log, links/<id>.url, 0700/0600 (22-26, 424-445); project id sha1(realpath)[:12] (364); fcntl.flock lock polled 50 ms, waits 45 s / 30 s (396-420); port preferred > env > 8377, then 0 (557-561, 793-811); Popen start_new_session with --launch-fd pipe, 15 s wait (757-779); stop SIGTERM, 5 s, SIGKILL, only pids whose ps matches server path (282-323); stale/hung detection by Server header probe (326-361); status flags old plugin version (915-944); browser webbrowser.get().open(url, new=2), skipped over SSH or no display (583-632); log rotation 1 MB keep 256 KB (654-666). Edit key secrets.token_urlsafe(32) in URL fragment via launch-fd, or links/<id>.url 0600 for --key-file. SessionEnd spawns detached _end worker, stops server when no owners and not manual (1051-1111). Guard prints JSON deny (1173-1189).

Web:
- SessionEnd default budget 1.5 s; plugin hook timeouts don't raise it; no decision control; -p kills async hooks, so detach. https://code.claude.com/docs/en/hooks.md
- CLAUDE_PLUGIN_ROOT changes on update; CLAUDE_PLUGIN_DATA persists across updates, deleted on uninstall; bin/ on Bash PATH; vars absent from Bash env. https://code.claude.com/docs/en/plugins/reference
- Running session keeps old version paths; old dirs removed 14 days later. https://code.claude.com/docs/en/plugins/loading.md
- SQLite WAL one writer. https://www.sqlite.org/wal.html ; Datasette, MLflow, Jupyter serve many from one server.
- uvicorn.run without workers; --timeout-graceful-shutdown; SIGINT/SIGTERM handled. https://raw.githubusercontent.com/encode/uvicorn/master/docs/settings.md ; lifespan https://fastapi.tiangolo.com/advanced/events/
- launchd overkill (inference).

Design notes: server writes its own pid/port after bind (uv may sit between launcher and Python; SIGTERM forwarding unverified); short graceful shutdown (~3 s); extend PreToolUse guard to the server entry point / uv run line; front end strips the fragment with history.replaceState; check opener argv doesn't expose key.
Owner decision: one edit link across all projects, or per project.
Unverified: interactive SessionEnd teardown vs detached child; uv SIGTERM forwarding; webbrowser argv; SessionEnd 1.5 s vs python3 start time.
