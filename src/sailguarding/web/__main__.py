"""Launch the demo dashboard.

The front door is ``sg serve`` (the one command on PATH). This module is the same server behind it,
runnable directly as ``python -m sailguarding.web [--host HOST] [--port PORT]`` for tests or when
the operator CLI isn't installed.
"""

from __future__ import annotations

import argparse

from sailguarding.web.server import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sailguarding.web", description="Demo dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
