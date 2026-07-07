"""sg — the sailguarding operator CLI.

A thin Click front-end for the tasks a developer does *around* the engine rather than inside it.
Its first job is plugin lifecycle: register the in-repo local marketplace and install / enable /
disable the Claude Code sensor plugin through Claude Code's own plugin flow.

This is a separate package from ``sailguarding`` on purpose. The engine holds a hard
zero-runtime-dependency invariant (``dependencies = []``); this CLI is allowed to depend on Click,
so it lives beside the engine as its own workspace member instead of polluting the core.
"""
