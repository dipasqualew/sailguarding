"""Persistence for the :class:`~sailguarding.model.model.ActivityModel`.

The same minimal contract the rest of the engine uses for its aggregates — save one, load it back —
expressed as a :class:`Protocol` so a durable backend can stand in for the in-memory default without
the caller caring which is behind it.

Two implementations ship here:

- :class:`InMemoryActivityModelStore` — the injectable unit-test default. It round-trips the model
  through its serialised form on save, so a test exercises the real encode/decode path with no I/O,
  and nothing is shared between instances.
- :class:`FileActivityModelStore` — one canonical JSON file, written **atomically** (to a temp file
  in the same directory, then :func:`os.replace`), so a crash mid-write can never leave a truncated
  model on disk. ``load()`` returns ``None`` when the file does not exist yet.

Both are stdlib-only; there are no third-party dependencies.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

from sailguarding.model.model import ActivityModel


@runtime_checkable
class ActivityModelStore(Protocol):
    """Persist and reload a single :class:`ActivityModel`."""

    def save(self, model: ActivityModel) -> None:
        """Persist ``model``, replacing any previously saved one."""
        ...

    def load(self) -> ActivityModel | None:
        """The saved model, or ``None`` if nothing has been saved yet."""
        ...


class InMemoryActivityModelStore:
    """An :class:`ActivityModelStore` holding the model in memory.

    The injectable default: nothing shared between instances, and the model is round-tripped through
    its serialised form on save so a test exercises the real encode/decode path with no I/O.
    """

    def __init__(self) -> None:
        self._payload: str | None = None

    def save(self, model: ActivityModel) -> None:
        self._payload = model.to_json()

    def load(self) -> ActivityModel | None:
        if self._payload is None:
            return None
        return ActivityModel.from_json(self._payload)


class FileActivityModelStore:
    """An :class:`ActivityModelStore` persisting to one canonical JSON file, written atomically.

    :param path: The file the model is stored in. Its parent directory must exist.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)

    def save(self, model: ActivityModel) -> None:
        """Write ``model`` atomically: to a temp file in the same dir, then :func:`os.replace`.

        The temp-then-replace dance means a reader never sees a half-written file, and a crash
        mid-write leaves the previous good file untouched.
        """
        directory = self._path.parent
        fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=self._path.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(model.to_json())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self._path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise

    def load(self) -> ActivityModel | None:
        """The saved model, or ``None`` if the file does not exist."""
        if not self._path.exists():
            return None
        return ActivityModel.from_json(self._path.read_text(encoding="utf-8"))
