"""The only module that touches ``http.server`` — a thin socket adapter over :class:`App`.

The handler does nothing but parse the request line, delegate to :meth:`App.handle`, and write the
:class:`Response` back. All routing and logic live in :mod:`.app`, which is why the app is testable
without ever binding a socket.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from sailguarding.web.app import App


def make_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    """Build (but do not start) the demo HTTP server bound to ``host:port``."""
    app = App()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parts = urlsplit(self.path)
            response = app.handle("GET", parts.path, parts.query)
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
    print(f"sailguarding demo dashboard → http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
