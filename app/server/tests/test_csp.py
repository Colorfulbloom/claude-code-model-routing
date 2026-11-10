"""Tests for the CSP, the security headers and the index rewrite."""

import os
import re
from pathlib import Path
from typing import Any

import pytest
from starlette.types import ASGIApp

import csp
import main
from access import AccessState

EXPECTED_CSP = (
    "default-src 'none'; script-src 'self' 'nonce-{n}'; style-src 'self' 'nonce-{n}'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'"
)


def _nonce_from_header(header: str) -> str:
    found = re.search(r"script-src 'self' 'nonce-([^']+)'", header)
    assert found is not None
    return found.group(1)


def _meta(html: str, name: str) -> str:
    found = re.search(rf'<meta name="{name}" content="([^"]*)">', html)
    assert found is not None
    return found.group(1)


def test_csp_string_equals_the_contract() -> None:
    assert csp.build_csp("abc") == EXPECTED_CSP.format(n="abc")


def test_index_source_rereads_after_a_rebuild(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    index.write_text(
        '<html><head><script src="/a-1.js"></script></head></html>', "utf-8"
    )
    source = csp.IndexSource(tmp_path)
    assert "a-1.js" in source.page.source
    # A rebuild writes new asset hashes, even at the same length and the same second.
    index.write_text(
        '<html><head><script src="/a-2.js"></script></head></html>', "utf-8"
    )
    os.utime(index, ns=(1, 1))
    assert "a-2.js" in source.page.source
    index.unlink()
    assert source.page.found is False
    index.write_text(
        '<html><head><script src="/a-3.js"></script></head></html>', "utf-8"
    )
    assert "a-3.js" in source.page.source
    assert source.page.found is True


def test_the_served_index_follows_a_rebuild(client: Any, dist_dir: Path) -> None:
    path = dist_dir / "index.html"
    path.write_text("<html><head><title>second</title></head></html>", "utf-8")
    os.utime(path, ns=(2, 2))
    assert "second" in client.get("/").text


def test_each_request_gets_a_fresh_nonce(client: Any) -> None:
    nonces = {
        _nonce_from_header(client.get("/").headers["content-security-policy"])
        for _ in range(5)
    }
    assert len(nonces) == 5


def test_nonce_in_header_meta_and_every_tag_agree(
    client: Any, state: AccessState
) -> None:
    response = client.get("/")
    nonce = _nonce_from_header(response.headers["content-security-policy"])
    html = response.text
    assert _meta(html, "csp-nonce") == nonce
    assert _meta(html, "bartab-instance") == state.instance
    assert _meta(html, "bartab-command") == "/bartab-preview"
    tags = re.findall(r"<(?:script|link)\b[^>]*>", html)
    assert len(tags) == 3
    for tag in tags:
        assert f'nonce="{nonce}"' in tag
    assert response.headers["content-security-policy"] == EXPECTED_CSP.format(n=nonce)


def test_index_carries_security_headers_and_no_store(client: Any) -> None:
    for path in ("/", "/index.html", "/somewhere/unknown"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "content-security-policy" in response.headers
        assert response.headers["content-type"].startswith("text/html")


def test_api_answers_carry_no_store_and_nosniff(
    client: Any, key_headers: dict[str, str]
) -> None:
    for response in (
        client.get("/api/app", headers=key_headers),
        client.get("/api/app"),
        client.get("/api/nothing", headers=key_headers),
    ):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"


def test_static_asset_gets_nosniff_and_referrer_policy(client: Any) -> None:
    response = client.get("/assets/app.js")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_head_on_index_works(client: Any) -> None:
    response = client.head("/")
    assert response.status_code == 200
    assert "content-security-policy" in response.headers


def test_index_has_no_secret(client: Any, state: AccessState) -> None:
    html = client.get("/").text
    assert state.read_key not in html
    assert state.mint_secret not in html


def test_existing_nonce_and_meta_are_replaced(tmp_path: Path) -> None:
    source = (
        '<html><head><meta name="csp-nonce" content="old">'
        '<script nonce="old" src="/a.js"></script></head><body></body></html>'
    )
    page = csp.IndexPage(source, found=True)
    html = page.render("NEW", "abcd1234").decode()
    assert "old" not in html
    assert html.count("nonce=") == 1
    assert html.count('name="csp-nonce"') == 1


def test_page_without_head_still_gets_the_metas() -> None:
    html = csp.IndexPage("<p>hi</p>", found=True).render("N", "abcd1234").decode()
    assert html.startswith('<meta name="csp-nonce" content="N">')


def test_missing_build_serves_a_notice(
    tmp_path: Path, state: AccessState, open_client: Any
) -> None:
    settings = main.Settings(
        port=47123,
        data_dir=tmp_path / "data",
        dist_dir=tmp_path / "nothing-here",
        access_state=state,
    )
    app = main.create_app(settings)
    with open_client(app) as client:
        response = client.get("/")
    assert response.status_code == 503
    assert "The build is missing" in response.text
    assert state.read_key not in response.text
    assert "script" not in response.text
    assert "content-security-policy" in response.headers


@pytest.mark.parametrize(
    "path",
    [
        "/assets/..%2f..%2foutside.txt",
        "/%2e%2e/outside.txt",
        "/assets/../../outside.txt",
        "/assets/link.txt",
        "/assets/%00",
    ],
)
def test_static_files_stay_inside_dist(client: Any, dist_dir: Path, path: str) -> None:
    (dist_dir.parent / "outside.txt").write_text("outside-secret", encoding="utf-8")
    (dist_dir / "assets" / "link.txt").symlink_to(dist_dir.parent / "outside.txt")
    response = client.get(path)
    assert "outside-secret" not in response.text


def test_unknown_api_path_needs_a_key_then_is_not_found(
    client: Any, key_headers: dict[str, str]
) -> None:
    assert client.get("/api/nothing").status_code == 401
    found = client.get("/api/nothing", headers=key_headers)
    assert found.status_code == 404
    assert found.json() == {"code": "not_found", "path": None}
    assert client.get("/api", headers=key_headers).status_code == 404


def test_create_app_returns_an_asgi_callable(app: ASGIApp) -> None:
    assert callable(app)
