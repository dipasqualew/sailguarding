"""Sensor configuration, resolved from the environment.

The plugin's hook shells into the engine with nothing but the stdin payload and the process
environment, so configuration is read from environment variables here. Everything has a sane
default: with no configuration at all the sensor writes to the ``sailguarding/events`` branch
of the repo the tool call ran in, redacting obvious secrets. Teams tune it — a different
branch, extra secret keys, ambient team/environment labels — without editing code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from sailguarding.sensor.redaction import DEFAULT_SECRET_KEY_PATTERNS
from sailguarding.sensor.spool import SpoolStorage
from sailguarding.storage import BranchStorage, BranchStorageConfig, StorageStrategy

# Environment variables the sensor reads. Prefixed to stay clear of the harness's own vars.
ENV_BRANCH = "SAILGUARDING_BRANCH"
ENV_TEAM = "SAILGUARDING_TEAM"
ENV_ENVIRONMENT = "SAILGUARDING_ENVIRONMENT"
ENV_REDACT_KEYS = "SAILGUARDING_REDACT_KEYS"


@dataclass(frozen=True)
class SensorConfig:
    """Resolved sensor settings for one invocation.

    :param repo_path: Repository whose branch holds the event log.
    :param branch: Dedicated events branch the log is committed to.
    :param team: Ambient team label to stamp on context, if configured.
    :param environment: Ambient environment label to stamp on context, if configured.
    :param redact_keys: Secret-bearing key patterns the redactor masks.
    :param spool_root: Local directory events are staged in before the deferred branch commit.
        Resolved from git at invocation time; ``None`` until then.
    """

    repo_path: Path
    branch: str = "sailguarding/events"
    team: str | None = None
    environment: str | None = None
    redact_keys: tuple[str, ...] = field(default=DEFAULT_SECRET_KEY_PATTERNS)
    spool_root: Path | None = None

    @classmethod
    def from_env(cls, repo_path: Path, env: Mapping[str, str]) -> SensorConfig:
        """Build config for ``repo_path`` from environment variables, applying defaults."""
        branch = env.get(ENV_BRANCH) or "sailguarding/events"
        extra = _split_keys(env.get(ENV_REDACT_KEYS))
        # Extend the built-in patterns rather than replace them: a team adds its own secret
        # keys without losing the safe default set.
        redact_keys = DEFAULT_SECRET_KEY_PATTERNS + extra
        return cls(
            repo_path=repo_path,
            branch=branch,
            team=env.get(ENV_TEAM) or None,
            environment=env.get(ENV_ENVIRONMENT) or None,
            redact_keys=redact_keys,
        )


def build_spool_storage(config: SensorConfig) -> SpoolStorage:
    """The per-tool-call sink: stage events locally, to be committed on Stop / SessionEnd."""
    if config.spool_root is None:
        raise ValueError("SensorConfig.spool_root must be resolved before building the spool")
    return SpoolStorage(config.spool_root)


def build_branch_storage(config: SensorConfig) -> StorageStrategy:
    """The commit sink: the branch sink from task 02, targeting the configured branch.

    The flush command writes a whole session's staged events through this in one commit.
    """
    return BranchStorage(BranchStorageConfig(repo_path=config.repo_path, branch=config.branch))


def _split_keys(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())
