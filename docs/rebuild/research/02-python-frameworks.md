# Scout report 2: Python web frameworks and distribution (2026-11-08)

| Name | Version | Released | Min Python | Direct deps | Notes |
|---|---|---|---|---|---|
| FastAPI | 0.162.2 | Nov 7, 2026 | 3.10 | starlette, pydantic, typing-extensions, typing-inspection, annotated-doc, opentelemetry-api | Async. Built-in SSE since 0.135.0 (fastapi.sse, verified on docs). Uvicorn is an extra |
| Starlette | 1.10.0 | Oct 24, 2026 | 3.11 | anyio | StaticFiles html=True verified. SSE not confirmed |
| Litestar | 2.25.0 | Oct 18, 2026 | 3.8 | ~13 (anyio, click, httpx, msgspec, multidict, pyyaml, rich, ...) | Heavy footprint |
| Flask | 3.1.3 | Feb 19, 2026 | 3.9 | blinker, click, itsdangerous, jinja2, markupsafe, werkzeug | Sync. Only mainstream option still on 3.9 |
| Quart | 0.23.1 | Aug 29, 2026 | 3.13 | not fetched | Yank status UNVERIFIED (conflicting reads) |
| Django | 6.1.3 | Nov 3, 2026 | 3.12 | not fetched | LTS 5.2; 6.2 LTS due April 2027 |
| Django Ninja | 1.7.3 | Oct 29, 2026 | 3.7 | Django | |
| Bottle | 0.13.4 | Jun 15, 2025 | ~3.8 | single file | Last release ~17 months old |
| aiohttp | 3.14.5 | Oct 11, 2026 | 3.10 | not fetched | Own server, not ASGI |
| uvicorn | 0.54.0 | Sep 25, 2026 | 3.10 | click, h11 | [standard] adds compiled httptools, uvloop, websockets, watchfiles |

Python-driven UI: NiceGUI 4.0.0 (3.11, FastAPI + Vue/Quasar), Reflex 0.10.1 (3.11, compiles React), Streamlit 1.67.0 (3.11, reruns script), Panel 1.10.0 (3.12), Dash 4.5.0 (3.9, Plotly/React), Flet 1.1.2 (3.10, Flutter). Token-theming fit is the scout's inference, not sourced.

Distribution:
- uv (uvx, uv tool install): user needs only uv; uv downloads a managed Python on demand.
- pipx: needs Python and pipx.
- PEP 723 inline metadata: Final; needs a runner such as uv; plain python3 ignores it.
- zipapp: python3 only, deps bundled, compiled extensions cannot load from the archive.
- Vendored pure-Python wheels: python3 only, same limit. Not checked in a source.
- shiv: not checked.

Facts:
- Python 3.9 EOL Oct 31, 2025; 3.10 EOL Oct 1, 2026; 3.11 security until Oct 2027 (devguide, verified).
- http.server docs: "not recommended for production", "only implements basic security checks".
- JetBrains 2025 survey FastAPI 38%, Django 35%, Flask 34%: UNVERIFIED (403, from search snippet).

Sources: pypi.org pages for each package; fastapi.tiangolo.com/tutorial/server-sent-events/; starlette.dev/staticfiles/; docs.astral.sh/uv guides; peps.python.org/pep-0723/; docs.python.org/3/library/zipapp.html; pipx.pypa.io; devguide.python.org/versions/; docs.python.org/3/library/http.server.html.
