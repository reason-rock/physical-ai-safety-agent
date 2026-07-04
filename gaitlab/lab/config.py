"""Configuration for the Physical AI Safety Agent live lab adapter.

Reads the same ``.env`` file as :class:`gaitlab.config.GaitLabConfig` but
exposes the subset of fields that the live adapter needs, plus an explicit
``require_enabled`` gate that every adapter agent calls before doing any
network or filesystem work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gaitlab.config import (
    GaitLabConfig,
    ROOT,
    _mask_host,
    _mask_host_list,
    _mask_path,
)


class LiveLabNotEnabledError(RuntimeError):
    """Raised when live lab mode is requested but the safe defaults forbid it."""


def _read_lab_env_extras() -> dict[str, str]:
    """Read ``GAITLAB_LAB_*`` extras directly from ``.env``.

    The base :class:`gaitlab.config.GaitLabConfig` only parses a fixed set
    of fields. The lab adapter needs a few extras (notably
    ``GAITLAB_LAB_REMOTE_REPO_PATH``) that are not in the base parser, so
    we re-read the same file using the same minimal key=value logic.
    """

    env_path = ROOT / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key.startswith("GAITLAB_LAB_"):
            values[key] = value
    return values


@dataclass(frozen=True)
class LiveLabConfig:
    """Resolved live lab configuration derived from ``.env``.

    Mirrors the safe-summary pattern of :class:`gaitlab.config.GaitLabConfig`:
    secret values are never stored as raw strings here. The ``ssh_key_path``
    is exposed only as a boolean ``ssh_key_configured`` flag.
    """

    mode: str
    enable_ssh: bool
    allow_real_robot: bool
    lab_repo_path: Path
    gpu0_host: str
    gpu1_host: str
    research_pc_host: str
    robot_host: str
    train_host_primary: str
    train_host_fallbacks: list[str]
    robot_fallbacks: list[str]
    ssh_user: str
    ssh_key_configured: bool
    operator_approval_required: bool
    estop_dry_run_required: bool
    workspace_path: Path
    live_demo_mock: bool = False
    pipeline_dir: Path = field(default_factory=Path)
    # Linux path on the training servers and robot. Required when the lab
    # adapter is enabled, but defaulted here so that direct LiveLabConfig
    # construction (e.g. in tests with only a local lab_repo_path) keeps
    # working without naming every field. ``LiveLabConfig.load()`` always
    # fills this in.
    remote_repo_path: str = ""

    @classmethod
    def load(cls, base: GaitLabConfig | None = None) -> "LiveLabConfig":
        base = base or GaitLabConfig.load()
        lab_repo = Path(base.lab_repo_path) if base.lab_repo_path else Path()
        pipeline_dir = lab_repo / "scripts" / "pipeline" if lab_repo else Path()
        # The remote repo path is the Linux path on the training servers and
        # robot. It is usually different from the local lab_repo_path (which
        # is a Windows path on the dev PC). Allow .env override; default to
        # the canonical layout used in the lab's _common.sh.
        env_values = _read_lab_env_extras()
        remote_repo_path = (
            env_values.get("GAITLAB_LAB_REMOTE_REPO_PATH")
            or f"/home/{base.ssh_user or 'operator'}/physical-ai-lab"
        )
        return cls(
            mode=base.mode,
            enable_ssh=base.enable_ssh,
            allow_real_robot=base.allow_real_robot,
            lab_repo_path=lab_repo,
            gpu0_host=base.gpu0_host,
            gpu1_host=base.gpu1_host,
            research_pc_host=base.research_pc_host,
            robot_host=base.robot_host,
            train_host_primary=base.train_host_primary,
            train_host_fallbacks=list(base.train_host_fallbacks),
            robot_fallbacks=list(base.robot_fallbacks),
            ssh_user=base.ssh_user,
            ssh_key_configured=bool(base.ssh_key_path),
            operator_approval_required=base.operator_approval_required,
            estop_dry_run_required=base.estop_dry_run_required,
            live_demo_mock=base.live_demo_mock,
            workspace_path=Path(base.workspace_path),
            pipeline_dir=pipeline_dir,
            remote_repo_path=remote_repo_path,
        )

    @property
    def enabled(self) -> bool:
        """True only when every precondition for live lab work is satisfied."""

        return (
            self.live_demo_mock
            or
            self.enable_ssh
            and bool(self.lab_repo_path)
            and self.lab_repo_path.exists()
            and self.pipeline_dir.exists()
        )

    def require_enabled(self, action: str = "live lab work") -> None:
        """Raise :class:`LiveLabNotEnabledError` unless ``self.enabled`` is True.

        The error message lists the first missing precondition so the user
        knows exactly which ``.env`` flag to flip. This is the single gate
        every adapter agent calls before touching the network or the lab
        repository.
        """

        if self.enabled:
            return
        missing: list[str] = []
        if not self.enable_ssh:
            missing.append("GAITLAB_ENABLE_SSH=true")
        if not self.lab_repo_path:
            missing.append("GAITLAB_LAB_REPO_PATH=<path to physical-ai-lab>")
        elif not self.lab_repo_path.exists():
            missing.append(f"GAITLAB_LAB_REPO_PATH does not exist: {self.lab_repo_path}")
        elif not self.pipeline_dir.exists():
            missing.append(
                f"lab repo missing scripts/pipeline/ directory: {self.pipeline_dir}"
            )
        hint = "; ".join(missing) if missing else "unknown precondition"
        raise LiveLabNotEnabledError(
            f"{action} requires the live lab adapter to be enabled. "
            f"Set the following in .env and retry: {hint}"
        )

    def live_log_dir(self, run_id: str) -> Path:
        """Return the directory used to capture live subprocess stdout/stderr."""

        path = self.workspace_path / "demo_data" / "live_logs" / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def safe_summary(self) -> dict[str, Any]:
        """Return a secret-free summary suitable for audit logs and the UI."""

        return {
            "mode": self.mode,
            "enable_ssh": self.enable_ssh,
            "allow_real_robot": self.allow_real_robot,
            "enabled": self.enabled,
            "lab_repo_path": _mask_path(str(self.lab_repo_path)) if self.lab_repo_path else "",
            "pipeline_dir": _mask_path(str(self.pipeline_dir)) if self.pipeline_dir else "",
            "remote_repo_path": _mask_path(self.remote_repo_path),
            "gpu0_host": _mask_host(self.gpu0_host),
            "gpu1_host": _mask_host(self.gpu1_host),
            "research_pc_host": _mask_host(self.research_pc_host),
            "robot_host": _mask_host(self.robot_host),
            "train_host_primary": _mask_host(self.train_host_primary),
            "train_host_fallbacks": _mask_host_list(list(self.train_host_fallbacks)),
            "robot_fallbacks": _mask_host_list(list(self.robot_fallbacks)),
            "ssh_user": "<configured_user>" if self.ssh_user else "",
            "ssh_key_configured": self.ssh_key_configured,
            "operator_approval_required": self.operator_approval_required,
            "estop_dry_run_required": self.estop_dry_run_required,
            "live_demo_mock": self.live_demo_mock,
        }


def workspace_root() -> Path:
    """Return the workspace root (sibling helper for the package)."""

    return ROOT
