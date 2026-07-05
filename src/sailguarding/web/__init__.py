"""The demo dashboard — a stdlib-only view over the real engine.

Per [`CLAUDE.md`](../../../CLAUDE.md), a task is not done until it is demonstrated. This package is
the standing demo surface: a zero-dependency web dashboard (``python -m sailguarding.web``) that
runs the actual classifier and scorer over a worked scenario, so shipped behaviour can be *seen*
and driven. New stories should extend it with a panel or interaction rather than a one-off script.

:mod:`.app` holds the framework-free router (testable without a socket); :mod:`.scenario` wires the
real engine; :mod:`.page` renders the self-contained HTML; :mod:`.server` is the thin
``http.server`` adapter.
"""

from sailguarding.web.app import App, Response
from sailguarding.web.server import make_server, serve

__all__ = ["App", "Response", "make_server", "serve"]
