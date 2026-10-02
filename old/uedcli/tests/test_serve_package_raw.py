"""GET /api/package/{package_name}/raw -- gui-inspector-props-payload-redesign spec §0."""
from __future__ import annotations

import gzip
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from uedcli.serve import app as serve_app
from uedcli.serve.package_raw import PackageRawError, find_u_file


def _write_pkg(tmp_path: Path, name: str, ext: str, content: bytes) -> Path:
    d = tmp_path / "base"
    d.mkdir(exist_ok=True)
    p = d / f"{name}{ext}"
    p.write_bytes(content)
    return p


def test_find_u_file_matches_case_insensitively(tmp_path):
    p = _write_pkg(tmp_path, "DeusEx", ".u", b"fake-u-bytes")
    search_files = [(str(p), "base")]
    assert find_u_file(search_files, "deusex") == str(p)


def test_find_u_file_404s_for_a_name_not_on_the_search_path(tmp_path):
    search_files: list[tuple[str, str]] = []
    try:
        find_u_file(search_files, "NoSuchPackage")
        assert False, "expected PackageRawError"
    except PackageRawError as e:
        assert "NoSuchPackage" in e.message


def test_find_u_file_404s_for_a_wrong_kind_match(tmp_path):
    p = _write_pkg(tmp_path, "SomeTextures", ".utx", b"fake-utx-bytes")
    search_files = [(str(p), "base")]
    try:
        find_u_file(search_files, "SomeTextures")
        assert False, "expected PackageRawError"
    except PackageRawError as e:
        assert "SomeTextures" in e.message


def test_package_raw_route_serves_bytes_with_a_real_content_etag(tmp_path):
    # Fixture >= 500 bytes so GZipMiddleware's compression path is exercised
    content = b"fake-u-bytes-for-etag-test" * 30
    p = _write_pkg(tmp_path, "DeusEx", ".u", content)
    project = SimpleNamespace(root=str(tmp_path), maps=None)

    def fake_search_files(_project, _user_config):
        return [(str(p), "base")]

    import uedcli.serve.app as serve_app_module
    orig = serve_app_module.config.composed_search_files
    serve_app_module.config.composed_search_files = fake_search_files
    try:
        app = serve_app.create_app(project)
        c = TestClient(app, raise_server_exceptions=False)
        r = c.get("/api/package/DeusEx/raw")
        assert r.status_code == 200
        assert r.content == content
        assert r.headers["content-type"] == "application/octet-stream"
        assert r.headers["cache-control"] == "no-cache"
        assert r.headers["vary"] == "Accept-Encoding"
        import hashlib
        expected = hashlib.sha1(content).hexdigest()
        assert r.headers["etag"] == f'"{expected}"'

        # Second request with a matching If-None-Match -> 304, no body. GZipMiddleware never adds
        # Vary here (no body to process), so the route must set it itself -- regression for a 304
        # that had no Vary at all.
        r2 = c.get("/api/package/DeusEx/raw", headers={"If-None-Match": f'"{expected}"'})
        assert r2.status_code == 304
        assert r2.content == b""
        assert r2.headers["vary"] == "Accept-Encoding"
    finally:
        serve_app_module.config.composed_search_files = orig


def test_package_raw_route_gzip_large_fixture_no_duplicate_vary(tmp_path):
    # Fixture >= 500 bytes so GZipMiddleware's Vary-adding path is exercised.
    # Main regression test: verify Vary header is exactly "Accept-Encoding" (not doubled).
    content = b"fake-u-bytes-for-gzip-test" * 30
    p = _write_pkg(tmp_path, "Engine", ".u", content)
    project = SimpleNamespace(root=str(tmp_path), maps=None)

    def fake_search_files(_project, _user_config):
        return [(str(p), "base")]

    import uedcli.serve.app as serve_app_module
    orig = serve_app_module.config.composed_search_files
    serve_app_module.config.composed_search_files = fake_search_files
    try:
        app = serve_app.create_app(project)
        c = TestClient(app, raise_server_exceptions=False)
        r = c.get("/api/package/Engine/raw")
        assert r.status_code == 200
        # Fixture is >= 500 bytes, so middleware adds Vary header. Regression: verify it's
        # exactly "Accept-Encoding", not "Accept-Encoding, Accept-Encoding" (no duplicate).
        assert r.headers["vary"] == "Accept-Encoding"
        assert r.headers["cache-control"] == "no-cache"
    finally:
        serve_app_module.config.composed_search_files = orig


def test_package_raw_route_404s_for_unknown_and_wrong_kind_names(tmp_path):
    utx = _write_pkg(tmp_path, "SomeTextures", ".utx", b"fake-utx")
    project = SimpleNamespace(root=str(tmp_path), maps=None)
    import uedcli.serve.app as serve_app_module

    def fake_search_files(_project, _user_config):
        return [(str(utx), "base")]

    orig = serve_app_module.config.composed_search_files
    serve_app_module.config.composed_search_files = fake_search_files
    try:
        app = serve_app.create_app(project)
        c = TestClient(app, raise_server_exceptions=False)
        assert c.get("/api/package/NoSuchPackage/raw").status_code == 404
        assert c.get("/api/package/SomeTextures/raw").status_code == 404
    finally:
        serve_app_module.config.composed_search_files = orig


def test_package_raw_route_gzip_compresses_when_requested(tmp_path):
    # Repetitive, highly-compressible fixture large enough to trigger compression (>= 500 bytes).
    content = b"fake-u-bytes-for-compression" * 100
    p = _write_pkg(tmp_path, "Core", ".u", content)
    project = SimpleNamespace(root=str(tmp_path), maps=None)

    def fake_search_files(_project, _user_config):
        return [(str(p), "base")]

    import uedcli.serve.app as serve_app_module
    orig = serve_app_module.config.composed_search_files
    serve_app_module.config.composed_search_files = fake_search_files
    try:
        app = serve_app.create_app(project)
        c = TestClient(app, raise_server_exceptions=False)
        r = c.get("/api/package/Core/raw", headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200
        assert r.headers["content-encoding"] == "gzip"
        # TestClient/httpx may auto-decompress transparently or return raw compressed bytes.
        # Check which one we got and assert accordingly.
        try:
            # If r.content is already decompressed by httpx, gzip.decompress will fail.
            decompressed = gzip.decompress(r.content)
            # Content was raw compressed bytes; verify decompression recovers original.
            assert decompressed == content
        except gzip.BadGzipFile:
            # httpx auto-decompressed; r.content is already original bytes.
            assert r.content == content
        # Regression test: verify Vary header is not duplicated even on gzip path.
        assert r.headers["vary"] == "Accept-Encoding"
    finally:
        serve_app_module.config.composed_search_files = orig
