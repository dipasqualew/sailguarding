"""The only module that touches ``http.server`` — a thin socket adapter over :class:`App`.

The handler does nothing but parse the request line (reading the body on a ``POST``), delegate to
:meth:`App.handle`, and write the :class:`Response` back. All routing and logic live in :mod:`.app`,
which is why the app is testable without ever binding a socket.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from sailguarding.web.app import App, Response, store_backed_workspace_store


def make_server(
    host: str = "127.0.0.1", port: int = 8000, app: App | None = None
) -> ThreadingHTTPServer:
    """Build (but do not start) the demo HTTP server bound to ``host:port``.

    :param app: The :class:`App` to serve. Injectable for tests (pass one on an in-memory store to
        keep a smoke test hermetic); the default wires a durable file store under the
        operator-configured root so edits survive a restart, falling back to in-memory when there is
        no writable store (a non-git dir, a permissions error) so the server always boots.
    """
    served = app or App(store_backed_workspace_store())

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parts = urlsplit(self.path)
            self._respond(served.handle("GET", parts.path, parts.query))

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length > 0 else b""
            parts = urlsplit(self.path)
            self._respond(served.handle("POST", parts.path, parts.query, body))

        def _respond(self, response: Response) -> None:
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, format: str, *args: object) -> None:
            # Quiet by default — the demo server should not spam the terminal it runs in.
            pass

    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Serve the dashboard until interrupted."""
    server = make_server(host, port)
    print(f"sailguarding activity-model editor → http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
