from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _mask_host(value: str) -> str:
    """Return a display-safe host label without exposing private addresses."""

    if not value:
        return ""
    if value in {"GPU0", "GPU1", "ResearcherPC", "localhost", "offline_mock"}:
        return value
    return "<configured_host>"


def _mask_host_list(values: list[str]) -> list[str]:
    return [f"<configured_host_{idx}>" for idx, _ in enumerate(values, start=1)]


def _mask_path(value: str) -> str:
    """Return a display-safe path label without exposing local directories."""

    if not value:
        return ""
    normalized = value.replace("\\", "/")
    if normalized.startswith("demo_data/") or normalized in {"demo_data", "."}:
        return normalized
    return "<configured_path>"


@dataclass(frozen=True)
class GaitLabConfig:
    mode: str
    use_mock_nodes: bool
    enable_ssh: bool
    allow_real_robot: bool
    gpu0_host: str
    gpu1_host: str
    research_pc_host: str
    robot_host: str
    robot_fallbacks: list[str]
    train_host_primary: str
    train_host_fallbacks: list[str]
    lab_repo_path: str
    workspace_path: str
    artifact_root: str
    eval_root: str
    ssh_user: str
    ssh_key_path: str
    operator_approval_required: bool
    estop_dry_run_required: bool
    live_demo_mock: bool

    @classmethod
    def load(cls, env_path: Path | None = None) -> "GaitLabConfig":
        values = _read_env_file(env_path or ROOT / ".env")
        return cls(
            mode=values.get("GAITLAB_MODE", "public_demo"),
            use_mock_nodes=_bool(values.get("GAITLAB_USE_MOCK_NODES"), True),
            enable_ssh=_bool(values.get("GAITLAB_ENABLE_SSH"), False),
            allow_real_robot=_bool(values.get("GAITLAB_ALLOW_REAL_ROBOT"), False),
            gpu0_host=values.get("GAITLAB_GPU0_HOST", "GPU0"),
            gpu1_host=values.get("GAITLAB_GPU1_HOST", "GPU1"),
            research_pc_host=values.get("GAITLAB_RESEARCH_PC_HOST", "localhost"),
            robot_host=values.get("GAITLAB_ROBOT_HOST", "offline_mock"),
            robot_fallbacks=_split_csv(values.get("GAITLAB_ROBOT_HOST_FALLBACKS")),
            train_host_primary=values.get("GAITLAB_TRAIN_HOST_PRIMARY", ""),
            train_host_fallbacks=_split_csv(values.get("GAITLAB_TRAIN_HOST_FALLBACKS")),
            lab_repo_path=values.get("GAITLAB_LAB_REPO_PATH", ""),
            workspace_path=values.get("GAITLAB_WORKSPACE_PATH", str(ROOT)),
            artifact_root=values.get("GAITLAB_ARTIFACT_ROOT", "demo_data/artifacts"),
            eval_root=values.get("GAITLAB_EVAL_ROOT", "demo_data/metrics"),
            ssh_user=values.get("GAITLAB_SSH_USER", ""),
            ssh_key_path=values.get("GAITLAB_SSH_KEY_PATH", ""),
            operator_approval_required=_bool(values.get("GAITLAB_OPERATOR_APPROVAL_REQUIRED"), True),
            estop_dry_run_required=_bool(values.get("GAITLAB_ESTOP_DRY_RUN_REQUIRED"), True),
            live_demo_mock=_bool(values.get("GAITLAB_LIVE_DEMO_MOCK"), False),
        )

    def node_status(self) -> str:
        if self.mode == "public_demo":
            return "mock_public_demo"
        if self.use_mock_nodes:
            return "configured_mock_private_lab"
        if self.enable_ssh:
            return "configured_external_ssh"
        return "configured_no_transport"

    def safe_summary(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "use_mock_nodes": self.use_mock_nodes,
            "enable_ssh": self.enable_ssh,
            "allow_real_robot": self.allow_real_robot,
            "gpu0_host": _mask_host(self.gpu0_host),
            "gpu1_host": _mask_host(self.gpu1_host),
            "research_pc_host": _mask_host(self.research_pc_host),
            "robot_host": _mask_host(self.robot_host),
            "robot_fallbacks": _mask_host_list(self.robot_fallbacks),
            "train_host_primary": _mask_host(self.train_host_primary),
            "train_host_fallbacks": _mask_host_list(self.train_host_fallbacks),
            "lab_repo_path": _mask_path(self.lab_repo_path),
            "workspace_path": _mask_path(self.workspace_path),
            "artifact_root": _mask_path(self.artifact_root),
            "eval_root": _mask_path(self.eval_root),
            "ssh_user": "<configured_user>" if self.ssh_user else "",
            "ssh_key_configured": bool(self.ssh_key_path),
            "operator_approval_required": self.operator_approval_required,
            "estop_dry_run_required": self.estop_dry_run_required,
            "live_demo_mock": self.live_demo_mock,
        }
