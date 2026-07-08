"""Pluggable storage for the append-only event log.

:class:`StorageStrategy` is the injectable contract; :class:`InMemoryStorage` is the
zero-infrastructure default for tests, :class:`BranchStorage` persists the log to a dedicated
git branch, and :class:`FilesystemStorage` persists it as plain JSONL under a directory. This
package is the raw *event log* only — derived safeguard metrics get their own sink later.
"""

from sailguarding.storage.base import StorageStrategy
from sailguarding.storage.branch import BranchStorage, BranchStorageConfig
from sailguarding.storage.filesystem import FilesystemStorage
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
    "FilesystemStorage",
    "GitError",
    "GitResult",
    "GitRunner",
    "InMemoryStorage",
    "StorageStrategy",
    "SubprocessGitRunner",
]
