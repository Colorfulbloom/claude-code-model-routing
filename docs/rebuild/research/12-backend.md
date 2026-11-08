# Scout report: backend deep dive (2026-11-08)

Saved by the main session from the scout's reply (scout is read-only). Quotes are from WebFetch extraction.

## Summary
- Framework: FastAPI with Pydantic, on Starlette. SSE built in from 0.135.0. Alternative Litestar (built-in CSRF and allowed-hosts middleware). Django too heavy. Flask out.
- Host/Origin: Starlette has TrustedHostMiddleware but no CSRF; write Origin check and token dependency by hand. Litestar has CSRFConfig.
- Typed client: openapi-typescript from FastAPI OpenAPI output.
- Single-language TypeScript (Hono, Fastify) wins only if team is all TS and data work is light; YAML round-trip and JSONL analytics favor Python (inference).
- Data: SQLite for per-file cursors and state; DuckDB reads NDJSON but native file allows one read-write process at a time.
- File watching: watchfiles. Writes: ruamel.yaml round-trip, temp file plus os.replace.
- Tooling: uv, ruff, pyright (mypy alt), pytest + xdist, hypothesis.
- Packaging for a Claude Code plugin: PEP 723 script run by uv; PyInstaller for users without uv.

## 1. Python frameworks
FastAPI (recommended)
- SSE "Added in FastAPI 0.135.0", fastapi.sse, keepalive ping every 15 s suggested. https://fastapi.tiangolo.com/tutorial/server-sent-events/
- Starlette "doesn't provide automatic data validation, serialization or documentation"; FastAPI adds these "all based on Python type hints (using Pydantic)". https://fastapi.tiangolo.com/alternatives/
- Background tasks "run *after* returning a response"; heavy work may need Celery. https://fastapi.tiangolo.com/tutorial/background-tasks/
- "FastAPI Cloud is the primary sponsor and funding provider." MIT. https://github.com/fastapi/fastapi
- TestClient "is built on httpx2"; plain httpx "still supported but deprecated"; lifespan only as context manager. https://starlette.dev/testclient/ (check httpx2 package name)

Starlette: "lightweight ASGI framework/toolkit", "only requires anyio", BSD-3. https://starlette.dev/ TrustedHostMiddleware "Enforces that all incoming requests have a correctly set Host header"; no CSRF built in. https://www.starlette.dev/middleware/

Litestar (alternative): "Powerful dependency injection"; accepts msgspec, Pydantic, attrs, dataclasses. https://litestar.dev/ CSRFConfig and AllowedHostsMiddleware. https://docs.litestar.dev/latest/usage/middleware/builtin-middleware.html WebSockets https://docs.litestar.dev/latest/usage/websockets.html ; ServerSentEvent class exists, config UNVERIFIED https://docs.litestar.dev/latest/reference/response/sse.html. MIT, sponsor funded, ~8.5k stars. https://github.com/litestar-org/litestar ~13 direct deps (prior survey).

Django + Ninja: 6.1.3 mainstream to April 2027; 5.2 LTS to April 2028. https://www.djangoproject.com/download/ Ninja "Very high performance thanks to Pydantic and async support". https://github.com/vitalik/django-ninja Django Tasks "does not provide a worker mechanism". https://docs.djangoproject.com/en/6.1/topics/tasks/ CSRF checks Origin "against the current host and the CSRF_TRUSTED_ORIGINS setting". https://docs.djangoproject.com/en/6.1/ref/csrf/ Too heavy unless ORM/admin wanted.

Flask: "lightweight WSGI web application framework". https://flask.palletsprojects.com/en/stable/ Sync; SSE not checked. Skip.

openapi-typescript: "Convert OpenAPI 3.0/3.1 schemas to TypeScript types and create type-safe fetching." https://openapi-ts.dev/ hey-api UNVERIFIED.

Performance: no sourced benchmark; JSONL parsing is the bottleneck (inference).

## 2. Non-Python backends
- Hono: runs on Workers, Deno, Bun, Lambda, Node; "hono/tiny preset is under 14kB"; RPC client. https://hono.dev/docs/
- Fastify: JSON Schema validation; "speed up serialization by a factor of 2-3" (vendor). https://fastify.dev/docs/latest/Guides/Getting-Started/
- Axum 0.8.9: "designed to work with tokio and hyper"; SSE behind tokio feature, WS behind ws feature. https://docs.rs/axum/latest/axum/
- Tauri sidecar: "Common use cases are Python CLI applications or API servers bundled using pyinstaller." https://v2.tauri.app/develop/sidecar/
- Go not researched.

## 3. Data layer
- sqlite3 timeout default "five seconds"; check_same_thread True. https://docs.python.org/3/library/sqlite3.html
- WAL: "readers do not block writers and a writer does not block readers"; "only be one writer at a time"; WAL persistent. https://sqlite.org/wal.html
- SQLAlchemy 2.1.8 (Nov 4, 2026, Python >=3.11). https://pypi.org/project/SQLAlchemy/
- DuckDB 2.0.0 (Oct 21, 2026, Python >=3.11). https://pypi.org/project/duckdb/ read_ndjson alias, virtual filename column, glob (search snippets only). https://duckdb.org/docs/current/data/json/loading_json.html Concurrency "one read-write process at a time" (snippet; versions disagree). https://www.duckdb.org/docs/current/connect/concurrency
- Polars 2.1.0 (Oct 25, 2026, Python >=3.11). https://pypi.org/project/polars/
- Recommendation (inference): SQLite row per transcript file (path, inode, offset, size, mtime), parse only new bytes, reset on shrink or inode change; DuckDB optional read-side analytics.
- watchfiles 1.3.0 (Python >=3.10), "Notify rust library". https://pypi.org/project/watchfiles/ watchdog: inotify, FSEvents/kqueue; polling "slow and not recommended". https://github.com/gorakhargosh/watchdog

## 4. Validation, YAML, JSON, writes
- Pydantic v2.14.3: "core validation logic is written in Rust"; emits JSON Schema. https://pydantic.dev/docs/validation/latest/get-started/
- msgspec 0.22.0 (Python >=3.10). https://pypi.org/project/msgspec/
- python-frontmatter parses YAML front matter; dump formatting not described. https://python-frontmatter.readthedocs.io/en/latest/
- ruamel.yaml 0.19.1 (Jan 2, 2026, Python >=3.9): "roundtrip preservation of comments, seq/map flow style, and map key order". https://pypi.org/project/ruamel.yaml/
- PyYAML 6.0.3: YAML 1.1 parser, no round-trip. https://pypi.org/project/PyYAML/
- JSON round-trip library: UNVERIFIED; inference is to splice edited bytes into original text (the current json_edit.py approach).
- os.replace "atomic operation (this is a POSIX requirement)"; "may fail if src and dst are on different filesystems". https://docs.python.org/3/library/os.html

## 5. Tooling
- uv bundles CPython/PyPy downloads; uses system Python first. https://docs.astral.sh/uv/concepts/python-versions/ "uv lock --script will create a .lock file adjacent to the script." https://docs.astral.sh/uv/guides/scripts/
- ruff 0.17.4 (Nov 5, 2026). https://pypi.org/project/ruff/
- pyright https://github.com/microsoft/pyright ; mypy 2.4 (Oct 1, 2026) https://mypy-lang.org/
- pytest fixtures scopes. https://docs.pytest.org/en/stable/how-to/fixtures.html pytest-xdist "Order and amount of test must be consistent". https://pytest-xdist.readthedocs.io/en/latest/
- hypothesis 6.170.15 (Python >=3.11). https://pypi.org/project/hypothesis/

## 6. Packaging
- uvx "invokes a tool without installing it", temporary isolated envs. https://docs.astral.sh/uv/guides/tools/
- PEP 723 Final, "# /// TYPE" blocks. https://peps.python.org/pep-0723/
- pipx isolated envs, uses uv when available. https://pipx.pypa.io/stable/
- PyInstaller 6.22.3: bundles app and deps; "not a cross-compiler"; macOS signing noted. https://pyinstaller.org/en/stable/
- PyPI Trusted Publishing. https://docs.pypi.org/trusted-publishers/
- Briefcase UNVERIFIED.
- Launcher constraint: plugin launchers sit behind PreToolUse Bash guard hooks and are tested as subprocesses (project facts L-bd45, L-979a).

## Could not verify
Litestar SSE config; Django/Ninja SSE; DuckDB docs (snippets only); Briefcase; benchmarks; maintainer counts; attrs/cattrs, SQLModel, hey-api, JSON round-trip lib, Go.
