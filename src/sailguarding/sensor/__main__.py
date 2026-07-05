"""``python -m sailguarding.sensor`` — the engine entrypoint the plugin hook shells into."""

from __future__ import annotations

from sailguarding.sensor.cli import main

raise SystemExit(main())
