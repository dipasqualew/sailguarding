"""Pluggable storage for the append-only event log.

:class:`StorageStrategy` is the injectable contract; :class:`InMemoryStorage` is the
zero-infrastructure default for tests, and :class:`BranchStorage` persists the log to a
dedicated git branch. This package is the raw *event log* only — derived safeguard metrics
get their own sink later.
"""

from sailguarding.storage.base import StorageStrategy
from sailguarding.storage.branch import BranchStorage, BranchStorageConfig
from sailguarding.storage.git import (
    GitError,
    GitResult,
    GitRunner,
    SubprocessGitRunner,
)
from sailguarding.storage.memory import InMemoryStorage

__all__ = [
    "BranchStorage",
    "BranchStorageConfig",
    "GitError",
    "GitResult",
    "GitRunner",
    "InMemoryStorage",
    "StorageStrategy",
    "SubprocessGitRunner",
]
