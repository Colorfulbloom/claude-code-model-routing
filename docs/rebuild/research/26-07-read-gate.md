# Read gate: does the rebuilt dashboard need a read token?

Measured November 8, 2026 on FastAPI 0.162.2, Starlette 1.10.0, Pydantic 2.14.3, Uvicorn 0.54.0 (`--http h11 --no-proxy-headers`, 127.0.0.1, ports 41871-41873). Spike: `/private/tmp/claude-501/-Volumes-Warehouse-Projects-claude-code-model-routing/0dd9a1d1-64b9-4152-b377-78cd2a79f3ad/scratchpad/spikes/round3/7-readgate/` (`app.py`, `gate.py`, `mask.py`, `probe.py`, `mask_test.py`, `logs/`).

## Recommendation

- Yes, add a read token. The gate (Host, Origin, Sec-Fetch-Site) already stops cross-site and rebinding reads (below), but a token also covers other OS users and any local process, and the cost is one header. Treat it as defense in depth, not the only control (inference).
- It travels the way the write token does today: printed once in the launch URL fragment (`http://127.0.0.1:PORT/#t=...`), read by page JS into memory, then sent as `X-Dashboard-Token` on every `fetch`. Never in a query string or path, because Uvicorn's access log records both (test 4).
- Keep the gate on GET as well as POST, mask on the server before serializing, and ship the 422/500/docs/log settings below. Masking is the last line: the current `collect.py:35-97` leaves gaps (test 5).

## Results: gate on GET (test 1)

Gate: `gate.py`, pure ASGI, all methods. It mirrors `dashboard/server.py:385-411`: Host must be `127.0.0.1:P` or `localhost:P`; Origin, when present, must be `http://` plus one of those; Sec-Fetch-Site, when present, must be `same-origin` or `none`. The old server applies all three to GET (`server.py:455`) and adds a top-level `/` exception (`server.py:394-413`), which I left out because the spike has no `/` page. Evidence for every row: `logs/default.out`.

| request | expected | actual | evidence |
|---|---|---|---|
| GET, Host ok, no Origin, no Sec-Fetch-Site (curl) | allow | 200 | default.out 1a, 1h |
| Sec-Fetch-Site: cross-site | refuse | 403 | 1b |
| Sec-Fetch-Site: same-site | refuse | 403 | 1c |
| Sec-Fetch-Site: none (typed URL) | allow | 200 | 1d |
| Host: evil.example:P | refuse | 403 | 1e |
| Host evil, no Origin, no Sec-Fetch-Site | refuse | 403 | 1f |
| Origin http://127.0.0.1:P+1 (other localhost port) | refuse | 403 | 1g |
| Origin same, Host localhost:P | allow | 200 | 1i, 1j |
| Host 127.0.0.1 without port | refuse | 403 | 1k |

What a browser sends. Sec-Fetch-Site is a forbidden request header (Sec- prefix), so page script cannot forge it, and its values are same-origin, same-site, cross-site, none (MDN, https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-Fetch-Site). A cross-origin GET with `fetch` is a simple request and is not preflighted, but the browser withholds the response unless CORS headers allow it (MDN, https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS). The request still reaches the server, so a no-cors GET with side effects still runs. The dashboard's GETs have none, but the gate blocks it anyway. Another localhost port is a different origin, so it sends `Origin: http://127.0.0.1:OTHER` and `cross-site`/`same-site` (inference from the same MDN pages; no real browser run here). The app sends no CORS headers, so those pages cannot read replies.

DNS rebinding: the attacker page loads from `evil.example`, then the name resolves to 127.0.0.1. The browser treats later requests as same-origin to the attacker, so it sends no Origin on a GET and Sec-Fetch-Site is `same-origin`. Only the Host header (`evil.example:P`) betrays it, which is why the Host check carries the weight (inference; MDN's CORS page does not discuss rebinding, so this is UNVERIFIED against a browser). A token in a header stops it too, since the attacker page never saw the fragment.

## What 127.0.0.1 binding does

- It stops other machines on the network from connecting (inference).
- It does not stop other OS users or other processes on this Mac, which can open `127.0.0.1:P` freely. Only a token separates them (inference; not tested with a second user).
- It does not stop a browser on this Mac from being used as a proxy, which is the CSRF and rebinding case the gate handles.

## Results: error bodies, docs, logs (tests 2 to 4)

| request | expected | actual | evidence |
|---|---|---|---|
| POST /api/edit/preview, body `{"key":"sk-ant-FAKE-secret","value":"not-an-int"}`, default app | 422 | 422, `input` echoes the bad field value (`"not-an-int"`) | default.out 2a |
| Same, malformed JSON, default app | 422 | 422 with `"input":{}` and `"ctx":{"error":...}` | default.out 2b |
| Same two, custom handler | 422 without input/ctx | 422 with only type, loc, msg | hard.out 2a, 2b |
| GET /boom (RuntimeError holding a fake key), default | 500 | 500, body `Internal Server Error`, no traceback | default.out 2c |
| Same, custom Exception handler | 500 | 500 `{"error":"internal"}` | hard.out 2c |
| /docs, /redoc, /openapi.json, default | served | 200 all four (incl. /docs/oauth2-redirect) | default.out part 3 |
| Same with the three URLs set to None | 404 | 404 all four | hard.out part 3 |
| Access log: `?project=/work/p&token=SECRETTOKEN123` | logs the query | logged in full | default.server.log |
| Access log: `/api/files/PATHSECRET456` | logs the path | logged in full | default.server.log |
| Request line with `#frag-SECRETFRAG` sent by hand | server never gets it | Uvicorn logged it, because my raw socket sent an illegal request line | hardlog.server.log |
| `--no-access-log` | no request lines | 0 request lines, secret count 0 | hard.server.log |

Notes.
- The 422 default body echoes `input` (the field's own value; the first test sent a wrong-typed `value`, so the leaked string was the offending value, not `key`). A secret typed into a wrong field would be returned to the caller. The caller is already past the gate, so the risk is logs and proxies, not strangers (inference).
- Fragment: browsers do not send the fragment in a request (RFC 3986 section 3.5 and RFC 9110 section 7.1; not re-fetched here). My hand-built socket request is not what a browser sends, so do not read that log line as a Uvicorn bug.
- The 500 handler hides the body but Starlette re-raises, so the traceback with the exception text (`RuntimeError: boom sk-ant-FAKE-in-traceback`) still reaches the server log (all three server logs). Do not put secrets in exception messages, and log to a file only the owner can read.
- Offline schema: `app.openapi()` can write the schema at build time for `openapi-typescript`, so the live endpoint is not needed. Not run here (UNVERIFIED).

Exact settings.
- `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`
- `@app.exception_handler(RequestValidationError)` returning `[{k: e[k] for k in ("type","loc","msg") if k in e} for e in exc.errors()]` with status 422.
- `@app.exception_handler(Exception)` returning `{"error":"internal"}` with status 500. Leave `debug` off (the default).
- `uvicorn app:app --host 127.0.0.1 --http h11 --no-proxy-headers --no-access-log`. If access logs are wanted, use a log config whose formatter logs method and path only (no query string).

## Masking (test 5)

Test: `mask_test.py`, output `logs/mask_test.txt`. Old = `dashboard/collect.py:31-97` (name parts KEY, TOKEN, SECRET, PASSWORD, CREDENTIAL, AUTH; prefixes `sk-` and `Bearer `). New = `mask.py` in the spike.

New rules.
- Name hides the whole value: KEY, TOKEN, SECRET, PASSWORD, PASSWD, CREDENTIAL, AUTH, COOKIE, BEARER, case-insensitive, `-` read as `_`. MAX_THINKING_TOKENS is exempt.
- Value prefix hides: `sk-`, `Bearer `, `Basic `, `ghp_`/`gho_`/`ghu_`/`ghs_`/`github_pat_`, `xox[abprs]-`, `AKIA` plus 12 or more characters, JWT shape `eyJ...` with two dots.
- URL userinfo: `scheme://user:pass@host` becomes `user:hidden@host`; a user-only form such as `https://ghp_x@host` hides the user. Host is kept.
- Under a key called `args`, a flag whose name holds a secret word hides the next item (`--api-key abc`) or the part after `=` (`--token=abc`). Other items still go through the value rules.

Result: old 8 of 18 pass, new 18 of 18. Old gaps: `ghp_`, `xoxb-`, `AKIA`, JWT values under a non-secret name; URL userinfo (`https://user:pass@...` returned unchanged); the Cookie header (COOKIE is not a name part); MCP args (`--api-key abc`, `--token=abc`, userinfo URLs in args). The fake MCP payload under the new rules: `"args":["--api-key","hidden","--token=hidden"]`, `"url":"https://user:hidden@example.invalid/mcp"` (hard.out part 5).

Remaining gaps even in the new rules (inference): a secret under an unrelated name and prefix (a bare hex key); secrets split across args (`-H "Authorization: x"` is caught only by the value rule if it starts with a known prefix); a flag name without a secret word (`--pat abc`); secrets inside free text such as a shell command in a hook. Prefer an allowlist for fields shown verbatim where the schema is known.

## UNVERIFIED

- Real-browser behavior (Sec-Fetch-Site values for a localhost-to-localhost cross-port fetch, no Origin on same-origin GET under rebinding). I tested header shapes with raw sockets, not Chrome.
- DNS rebinding as described is reasoning, not a measured attack.
- Other-OS-user access to loopback was not tested (single user machine).
- Fragment never reaching the server rests on the RFCs, which I did not re-read.
- `app.openapi()` offline export was not run.
- The new mask function covers my 18 cases only; it has not been run against real settings (forbidden by the round rules).
