"""The demo dashboard — the standing view over the real engine.

Per [`CLAUDE.md`](../../../CLAUDE.md), a task is not done until it is demonstrated. This package is
the standing demo surface: a web dashboard (``sg serve`` / ``python -m sailguarding.web``) that runs
the actual aggregates over a worked scenario, so shipped behaviour can be *seen* and driven. New
stories should extend it with a panel or interaction rather than a one-off script.

The front-end is a React SPA under [`frontend/`](../../../frontend); its build lands in ``static/``
and the server serves it. :mod:`.app` holds the framework-free router and JSON API (testable
without a socket); :mod:`.scenario` wires the real engine; :mod:`.server` is the thin
``http.server`` adapter.
"""

from sailguarding.web.app import App, Response
from sailguarding.web.server import make_server, serve

__all__ = ["App", "Response", "make_server", "serve"]
