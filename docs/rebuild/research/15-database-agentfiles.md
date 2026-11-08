# Scout report: database and agent-file editing (2026-11-08), saved by main session. Quotes via WebFetch summaries; recheck wording before docs.

## Database
- Pick: SQLite (stdlib sqlite3, WAL, JSON functions; FTS5 only if text search; check FTS5 in the bundled sqlite). Plain SQL in a repository module; numbered .sql migrations with PRAGMA user_version (UNVERIFIED). Alternative: DuckDB as an optional rebuildable analytics file.
- WAL: readers and writer don't block; one writer; same host only. https://www.sqlite.org/wal.html
- JSON built in since 3.38.0. https://www.sqlite.org/json1.html ; FTS5 https://www.sqlite.org/fts5.html
- sqlite3 timeout 5 s, check_same_thread True. https://docs.python.org/3/library/sqlite3.html
- DuckDB 2.0: one process read-write; files with storage v69 "cannot be opened by DuckDB versions prior to v2.0.0"; forward compat "best effort". https://duckdb.org/docs/2.0/connect/concurrency.html https://duckdb.org/docs/2.0/internals/storage.html ; read_ndjson https://duckdb.org/docs/2.0/data/json/loading_json.html
- SQLAlchemy Core/ORM https://docs.sqlalchemy.org/en/20/tutorial/index.html ; SQLModel status unknown https://sqlmodel.tiangolo.com/ ; Alembic https://alembic.sqlalchemy.org/en/latest/tutorial.html
- Location: ${CLAUDE_PLUGIN_DATA} = ~/.claude/plugins/data/<id>/, kept across updates, DELETED on uninstall; variables NOT present in Bash-tool environments, so the skill body or a hook must pass the path. https://code.claude.com/docs/en/plugins-reference
- Apple Caches for regenerable data, Application Support for user data. https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/MacOSXDirectories/MacOSXDirectories.html
- Only transcript-derived rows are safe to delete; edit history, backups and preferences are not (backups live at <config_dir>/routing-dashboard/backups/, edit_store.py:1-37).

## Agent files
- Scopes by priority: managed, --agents, .claude/agents/, ~/.claude/agents/, plugin agents/. Fields: name (required, no ":"), description (required), tools, disallowedTools, model, permissionMode, maxTurns, skills, mcpServers, hooks, memory, background, effort, isolation, color, initialPrompt. Plugin agents ignore hooks, mcpServers, permissionMode (initialPrompt conflict on page). https://code.claude.com/docs/en/sub-agents
- ruamel.yaml round-trip keeps comments, flow style, key order; "individual indentation of lines is not preserved"; width bugs in history; preserve_quotes API UNVERIFIED. https://pypi.org/project/ruamel.yaml/ https://yaml.dev/doc/ruamel.yaml/overview
- python-frontmatter dump re-emits via yaml.dump SafeDumper: loses comments and quotes. Do not use for writes. https://raw.githubusercontent.com/eyeseast/python-frontmatter/main/frontmatter/default_handlers.py
- Approach: split at fences, round-trip YAML only, copy body bytes untouched, verify. Possibly extend json_edit.py-style byte splicing to YAML for simple scalar fields (inference).
- Reuse edit_store.py write pattern: lock + flock, backup, ledger, temp in same folder, byte compare (stale check by hash, :529, Stale :108), rename, F_FULLFSYNC (:431), read back, retention 20 (:70); refuses symlinks, hard links, FIFOs, >1 MiB (:71, :391); undo when hash matches after-hash (:588).
- json_edit.py byte splicing: replace_value :212, insert_value :281, remove_key :369.
