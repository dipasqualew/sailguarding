"""A socket-level smoke test that the http.server adapter serves the app end to end."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection

import pytest

from sailguarding.web.server import make_server


@pytest.fixture
def base_url() -> Iterator[str]:
    server = make_server("127.0.0.1", 0)  # port 0 → an ephemeral free port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _get(base_url: str, path: str) -> tuple[int, str, bytes]:
    conn = HTTPConnection(base_url, timeout=5)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.getheader("Content-Type", ""), resp.read()
    finally:
        conn.close()


def test_serves_the_dashboard(base_url: str) -> None:
    status, content_type, body = _get(base_url, "/")
    assert status == 200
    assert content_type.startswith("text/html")
    assert b"delegation scoring" in body


def test_serves_the_score_api(base_url: str) -> None:
    status, content_type, body = _get(base_url, "/api/score?impact=100&flakiness=0&budget=1")
    assert status == 200
    assert content_type.startswith("application/json")
    assert json.loads(body)["score"] == 0.0
