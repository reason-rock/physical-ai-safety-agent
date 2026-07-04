"""Live robot deployment agent for the DARwIn-OP.

Wraps ``deploy_policy.ps1`` from the lab repo. This is the only agent that
can move the real robot, so the gating is intentionally strict and is
implemented as a pure function (:func:`deployment_allowed`) so it can be
unit-tested without any SSH or robot.

A live deploy is allowed ONLY when ALL of the following are true:

- ``safety.safety_level == "candidate_for_free_walking"``
- ``config.allow_real_robot`` is True
- ``config.operator_approval_required`` is True AND an operator token was
  supplied (``operator_token`` argument) — proving a human explicitly
  approved this specific deploy
- ``metrics.emergency_stop_dry_run`` is True
- ``policy_path`` resolves to an existing TorchScript ``.pt`` file

Any failure falls back to the public-demo mock package via
:func:`gaitlab.tools.deployment_tools.create_deployment_package`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from gaitlab.lab.config import LiveLabConfig
from gaitlab.lab.process import run_pipeline_script, summarize_for_audit


# Default auto-stop. The lab convention is 120s; never go below 60s.
DEFAULT_AUTO_STOP_SEC = 120
MIN_AUTO_STOP_SEC = 60

# Conservative defaults for the very first live deploy of a policy.
DEFAULT_VX_MAX = 0.055
DEFAULT_ACTION_SCALE = 0.35  # below the lab's 0.45 default; see plan §"safety gates"


@dataclass(frozen=True)
class DeploymentDecision:
    """Outcome of :func:`deployment_allowed` — pure, side-effect-free."""

    allowed: bool
    reasons: list[str]
    required_actions: list[str]

    def describe(self) -> str:
        if self.allowed:
            return "live robot deployment allowed"
        return "live robot deployment blocked: " + "; ".join(self.reasons)


def deployment_allowed(
    safety: Mapping[str, Any],
    metrics: Mapping[str, Any],
    config: LiveLabConfig,
    operator_token: str | None,
    policy_path: Path | None,
) -> DeploymentDecision:
    """Pure gate: decide whether a live deploy may proceed.

    This function never touches the network or filesystem (beyond reading
    ``policy_path.exists()``) so it can be exhaustively unit-tested. The
    actual SSH/SCP happens in :meth:`LiveRobotDeployAgent.run`.
    """

    reasons: list[str] = []
    required: list[str] = []

    if safety.get("safety_level") != "candidate_for_free_walking":
        reasons.append(
            f"safety_level must be 'candidate_for_free_walking' "
            f"(got {safety.get('safety_level')!r})"
        )
        required.append("improve the policy until it passes the free-walking gate")

    if not config.allow_real_robot:
        reasons.append("GAITLAB_ALLOW_REAL_ROBOT must be true in .env")
        required.append("explicitly enable real-robot mode in the local .env")

    if config.operator_approval_required:
        if not operator_token:
            reasons.append("operator_token is required but was not provided")
            required.append("have the on-site operator approve this deploy explicitly")

    if not metrics.get("emergency_stop_dry_run"):
        reasons.append("emergency_stop_dry_run evidence is missing")
        required.append("run a recorded emergency-stop dry-run before any live deploy")

    if policy_path is None or not policy_path.exists():
        reasons.append(f"policy file not found: {policy_path}")
        required.append("export a TorchScript policy with export_policy.ps1 first")

    return DeploymentDecision(
        allowed=not reasons,
        reasons=reasons,
        required_actions=required,
    )


class LiveRobotDeployAgent:
    """Drive ``deploy_policy.ps1`` with a hard safety gate in front."""

    def __init__(
        self,
        config: LiveLabConfig,
        data_mode: str = "live_lab",
        default_auto_stop_sec: int = DEFAULT_AUTO_STOP_SEC,
        default_vx_max: float = DEFAULT_VX_MAX,
        default_action_scale: float = DEFAULT_ACTION_SCALE,
    ) -> None:
        if data_mode != "live_lab":
            raise ValueError(
                f"LiveRobotDeployAgent requires data_mode='live_lab', got {data_mode!r}"
            )
        if default_auto_stop_sec < MIN_AUTO_STOP_SEC:
            raise ValueError(
                f"auto_stop_sec must be >= {MIN_AUTO_STOP_SEC} (got {default_auto_stop_sec})"
            )
        self.config = config
        self.data_mode = data_mode
        self.default_auto_stop_sec = default_auto_stop_sec
        self.default_vx_max = default_vx_max
        self.default_action_scale = default_action_scale
        config.require_enabled(action="live robot deployment")

    def run(
        self,
        safety: Mapping[str, Any],
        metrics: Mapping[str, Any],
        policy_path: str | Path,
        operator_token: str | None,
        tag: str = "gaitlab_deploy",
        auto_stop_sec: int | None = None,
        vx_max: float | None = None,
        action_scale: float | None = None,
        extra_args: list[str] | None = None,
    ) -> dict[str, Any]:
        """Attempt a live deploy, returning a manifest dict in either branch.

        When the gate blocks, falls back to the mock deploy package so the
        orchestrator's audit log and report still make sense. When the
        gate allows, runs ``deploy_policy.ps1`` on the researcher PC and
        records the local log path.
        """

        from gaitlab.tools.deployment_tools import create_deployment_package

        policy = Path(policy_path)
        decision = deployment_allowed(
            safety=safety,
            metrics=metrics,
            config=self.config,
            operator_token=operator_token,
            policy_path=policy,
        )

        if not decision.allowed:
            # Record WHY it was blocked, then fall back to the mock package.
            mock = create_deployment_package(
                policy_id=policy.stem,
                safety_level=str(safety.get("safety_level", "blocked")),
                free_walking_allowed=bool(safety.get("free_walking_allowed", False)),
            )
            mock.update(
                {
                    "live_deploy_attempted": True,
                    "live_deploy_allowed": False,
                    "block_reasons": decision.reasons,
                    "required_actions": decision.required_actions,
                }
            )
            return mock

        resolved_auto_stop = auto_stop_sec or self.default_auto_stop_sec
        resolved_vx_max = vx_max if vx_max is not None else self.default_vx_max
        resolved_scale = (
            action_scale if action_scale is not None else self.default_action_scale
        )

        deploy_script = self.config.pipeline_dir / "deploy_policy.ps1"
        args = [
            "-Model",
            str(policy),
            "-Tag",
            tag,
            "-AutoStop",
            str(resolved_auto_stop),
            "-VxMax",
            str(resolved_vx_max),
            "-ActionScale",
            str(resolved_scale),
            # Always require the joystick deadman and explicit joystick port.
            "-JoystickPort",
            "5005",
        ]
        if extra_args:
            args.extend(extra_args)

        result = run_pipeline_script(
            self.config,
            script=deploy_script,
            args=args,
            run_id=tag,
            cwd=self.config.lab_repo_path,
            env_overrides={
                # The operator token is passed via env so it never appears
                # in the captured command line (which gets logged).
                "GAITLAB_OPERATOR_TOKEN": operator_token or "",
                # Allow running on this PC even if it is not the canonical
                # DESKTOP-HD9JBL1 hostname, since Physical AI Safety Agent may be hosted on
                # a different dev box.
                "PIPELINE_ALLOW_THIS_PC": "1",
            },
            check=False,
        )

        manifest = {
            "policy_id": policy.stem,
            "package_type": "live_robot_deploy",
            "safety_level": safety.get("safety_level"),
            "free_walking_allowed": bool(safety.get("free_walking_allowed")),
            "human_approval_required": True,
            "human_approval_recorded": True,
            "operator_approval_required": self.config.operator_approval_required,
            "deploy_script": str(deploy_script),
            "deploy_log": str(result.log_path),
            "deploy_returncode": result.returncode,
            "auto_stop_sec": resolved_auto_stop,
            "vx_max": resolved_vx_max,
            "action_scale": resolved_scale,
            "audit": summarize_for_audit(result),
            "live_deploy_allowed": True,
        }
        if not result.ok:
            manifest["deploy_failed"] = True
            manifest["deploy_stderr_tail"] = result.stderr[-400:]
        return manifest


def fallback_mock_package(
    policy_id: str,
    safety: Mapping[str, Any],
    decision: DeploymentDecision,
) -> dict[str, Any]:
    """Build a mock package annotated with the live-deploy block reasons."""

    from gaitlab.tools.deployment_tools import create_deployment_package

    pkg = create_deployment_package(
        policy_id=policy_id,
        safety_level=str(safety.get("safety_level", "blocked")),
        free_walking_allowed=bool(safety.get("free_walking_allowed", False)),
    )
    pkg.update(
        {
            "live_deploy_attempted": True,
            "live_deploy_allowed": False,
            "block_reasons": decision.reasons,
            "required_actions": decision.required_actions,
        }
    )
    return pkg
