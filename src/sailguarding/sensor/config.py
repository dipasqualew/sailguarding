"""Sensor configuration, resolved from environment *and* the operator config file.

The plugin's hook shells into the engine with nothing but the stdin payload and the process
environment, so every setting has to be reachable from there. Two sources feed one resolved
:class:`SensorConfig`, in precedence order:

1. an **environment variable** — highest, so a one-off override always wins;
2. the operator **config file** (:mod:`sailguarding.sensor.pluginconfig`), managed by ``sg config``
   — where durable choices like *which data store* live;
3. a built-in **default** — so with no configuration at all the sensor still works.

With nothing set, the sensor commits to the ``sailguarding/events`` branch of the repo the tool
call ran in, redacting obvious secrets. Teams tune it — a different branch, the filesystem store, a
shared directory, extra secret keys, ambient labels — without editing code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from sailguarding.sensor.pluginconfig import VALID_STORES, ConfigError, PluginConfig
from sailguarding.sensor.redaction import DEFAULT_SECRET_KEY_PATTERNS
from sailguarding.sensor.spool import SpoolStorage
from sailguarding.storage import (
    BranchStorage,
    BranchStorageConfig,
    FilesystemStorage,
    StorageStrategy,
)
from sailguarding.storage.git import GitRunner

# Environment variables the sensor reads. Prefixed to stay clear of the harness's own vars.
ENV_STORE = "SAILGUARDING_STORE"
ENV_STORE_PATH = "SAILGUARDING_STORE_PATH"
ENV_BRANCH = "SAILGUARDING_BRANCH"
ENV_TEAM = "SAILGUARDING_TEAM"
ENV_ENVIRONMENT = "SAILGUARDING_ENVIRONMENT"
ENV_REDACT_KEYS = "SAILGUARDING_REDACT_KEYS"

DEFAULT_STORE = "branch"
DEFAULT_BRANCH = "sailguarding/events"


@dataclass(frozen=True)
class SensorConfig:
    """Resolved sensor settings for one invocation.

    :param repo_path: Repository whose branch (or filesystem tree) holds the event log.
    :param store: Which data store the commit sink writes to (``branch`` or ``filesystem``).
    :param branch: Dedicated events branch the log is committed to, for the ``branch`` store.
    :param team: Ambient team label to stamp on context, if configured.
    :param environment: Ambient environment label to stamp on context, if configured.
    :param redact_keys: Secret-bearing key patterns the redactor masks.
    :param spool_root: Local directory events are staged in before the deferred commit.
        Resolved from git at invocation time; ``None`` until then.
    :param store_path: Directory the ``filesystem`` store writes under. Resolved at invocation
        time (an explicit path, else a default under the git dir); ``None`` until then.
    """

    repo_path: Path
    store: str = DEFAULT_STORE
    branch: str = DEFAULT_BRANCH
    team: str | None = None
    environment: str | None = None
    redact_keys: tuple[str, ...] = field(default=DEFAULT_SECRET_KEY_PATTERNS)
    spool_root: Path | None = None
    store_path: Path | None = None

    @classmethod
    def resolve(
        cls,
        repo_path: Path,
        env: Mapping[str, str],
        file_config: PluginConfig,
    ) -> SensorConfig:
        """Resolve config for ``repo_path`` with ``env`` over ``file_config`` over defaults."""
        store = env.get(ENV_STORE) or file_config.store or DEFAULT_STORE
        if store not in VALID_STORES:
            raise ConfigError(f"unknown store {store!r}; valid stores: {', '.join(VALID_STORES)}")
        branch = env.get(ENV_BRANCH) or file_config.branch or DEFAULT_BRANCH
        raw_store_path = env.get(ENV_STORE_PATH) or file_config.store_path
        store_path = Path(raw_store_path).expanduser() if raw_store_path else None
        # Extend the built-in patterns rather than replace them: a team adds its own secret keys
        # (from either source) without losing the safe default set.
        extra = _split_keys(env.get(ENV_REDACT_KEYS)) + tuple(file_config.redact_keys)
        return cls(
            repo_path=repo_path,
            store=store,
            branch=branch,
            team=env.get(ENV_TEAM) or file_config.team or None,
            environment=env.get(ENV_ENVIRONMENT) or file_config.environment or None,
            redact_keys=DEFAULT_SECRET_KEY_PATTERNS + extra,
            store_path=store_path,
        )


def build_spool_storage(config: SensorConfig) -> SpoolStorage:
    """The per-tool-call sink: stage events locally, to be committed on Stop / SessionEnd."""
    if config.spool_root is None:
        raise ValueError("SensorConfig.spool_root must be resolved before building the spool")
    return SpoolStorage(config.spool_root)


def build_commit_storage(config: SensorConfig) -> StorageStrategy:
    """The commit sink the flush drains into, chosen by ``config.store``.

    ``branch`` targets the configured git branch (task 02); ``filesystem`` writes JSONL under the
    resolved ``store_path``. The flush command writes a whole session's staged events through this
    in one batch.
    """
    if config.store == "filesystem":
        if config.store_path is None:
            raise ValueError("filesystem store requires a resolved SensorConfig.store_path")
        return FilesystemStorage(config.store_path)
    return BranchStorage(BranchStorageConfig(repo_path=config.repo_path, branch=config.branch))


def resolve_store_root(
    git: GitRunner,
    repo_path: Path,
    configured: Path | None,
) -> Path:
    """Where the filesystem store writes: an explicit path, else a default under the git dir.

    An absolute ``configured`` path is honoured as-is (e.g. a shared mount); a relative one is
    taken against ``repo_path``. With nothing configured, events land under the repo's git dir so
    they stay out of the working tree, falling back to a dotdir when there is no git repo.
    """
    if configured is not None:
        return configured if configured.is_absolute() else repo_path / configured
    result = git(["rev-parse", "--absolute-git-dir"])
    if result.ok:
        git_dir = result.stdout.decode(errors="replace").strip()
        if git_dir:
            return Path(git_dir) / "sailguarding" / "events"
    return repo_path / ".sailguarding" / "events"


def _split_keys(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())
