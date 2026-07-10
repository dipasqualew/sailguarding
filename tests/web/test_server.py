"""A socket-level smoke test that the http.server adapter serves the app end to end."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection

import pytest

from sailguarding.model import InMemoryWorkspaceStore
from sailguarding.web.app import App
from sailguarding.web.server import make_server


@pytest.fixture
def base_url() -> Iterator[str]:
    # Inject an in-memory-backed app so the smoke test never writes a workspace file into the repo.
    server = make_server("127.0.0.1", 0, App(InMemoryWorkspaceStore()))  # port 0 → free port
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


def _post(base_url: str, path: str, body: dict[str, object]) -> tuple[int, bytes]:
    conn = HTTPConnection(base_url, timeout=5)
    try:
        payload = json.dumps(body).encode("utf-8")
        conn.request("POST", path, body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def test_serves_the_dashboard(base_url: str) -> None:
    status, content_type, body = _get(base_url, "/")
    assert status == 200
    assert content_type.startswith("text/html")
    # Build-agnostic: the built SPA's <title> and the not-built help page both name the app, so this
    # holds whether or not `npm run build` has run.
    assert b"sailguarding" in body


def test_serves_the_model_api(base_url: str) -> None:
    status, content_type, body = _get(base_url, "/api/model")
    assert status == 200
    assert content_type.startswith("application/json")
    view = json.loads(body)
    assert {"activities", "risks", "safeguards"} <= set(view)


def test_serves_a_post_mutation(base_url: str) -> None:
    status, body = _post(base_url, "/api/activity/add", {"parent_id": None, "label": "Smoke test"})
    assert status == 200
    data = json.loads(body)
    assert isinstance(data["created_id"], str)
    assert any(a["label"] == "Smoke test" for a in data["model"]["activities"])


def test_app_boots_from_a_fresh_in_memory_store() -> None:
    # The default App seeds and serves without touching any durable store.
    assert App().handle("GET", "/api/model").status == 200
