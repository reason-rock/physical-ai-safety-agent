from __future__ import annotations

from typing import Any


def run_robot_safety_gate(
    policy_id: str,
    metrics: dict[str, Any],
    strictness: str = "standard",
) -> dict[str, Any]:
    """Decide whether evidence is strong enough for hardware-facing testing."""

    reasons: list[str] = []
    required_actions: list[str] = []
    num_rollouts = metrics["num_rollouts"]
    fall_free = metrics["fall_free_count"]
    joint_limit = metrics["joint_limit_max_ratio"]
    velocity_ratio = metrics["avg_velocity"] / max(metrics["target_velocity"], 1e-9)
    torso_pitch = metrics["torso_pitch_rms"]
    action_jerk = metrics.get("action_jerk", 1.0)
    estop_ready = metrics.get("emergency_stop_dry_run", False)

    free_joint_limit = 0.80 if strictness == "strict" else 0.85
    supported_joint_limit = 0.92 if strictness == "strict" else 0.95

    if fall_free < num_rollouts:
        reasons.append("not all simulated rollouts are fall-free")
        required_actions.append("run more stable rollouts before any unsupervised hardware test")
    if joint_limit > free_joint_limit:
        reasons.append("joint limit usage is too high for unsupervised hardware testing")
        required_actions.append("reduce action scale and rerun evaluation")
    if velocity_ratio < 0.85:
        reasons.append("velocity tracking is below the target band")
        required_actions.append("add a velocity recovery term after stability threshold")
    if not estop_ready:
        reasons.append("no emergency-stop dry-run log is present")
        required_actions.append("prepare human operator and emergency stop dry-run")

    free_ok = (
        fall_free == num_rollouts
        and joint_limit <= free_joint_limit
        and torso_pitch <= 0.20
        and action_jerk <= 0.30
        and estop_ready
    )
    supported_ok = fall_free >= max(1, num_rollouts - 1) and joint_limit <= supported_joint_limit

    if free_ok:
        safety_level = "candidate_for_free_walking"
        free_walking_allowed = True
    elif supported_ok:
        safety_level = "supported_test_only"
        free_walking_allowed = False
    else:
        safety_level = "blocked"
        free_walking_allowed = False
        if not required_actions:
            required_actions.append("collect missing evaluation metrics")

    return {
        "policy_id": policy_id,
        "safety_level": safety_level,
        "free_walking_allowed": free_walking_allowed,
        "supported_test_allowed": safety_level in {"supported_test_only", "candidate_for_free_walking"},
        "reasons": reasons,
        "required_actions": _dedupe(required_actions),
    }


def create_robot_action_diff(policy_id: str, safety: dict[str, Any], metrics: dict[str, Any]) -> str:
    """Explain what would change in a hardware-facing test, without executing it."""

    return "\n".join(
        [
            "# Robot Action Diff",
            "",
            "Original intent:",
            f"- Consider `{policy_id}` for a physical-AI hardware test.",
            "",
            "Proposed hardware-facing action:",
            "- Create a low-speed deployment package.",
            "- Use reduced action scale before supported testing.",
            "- Require human operator and emergency stop readiness.",
            "",
            "Safety result:",
            f"- Safety level: `{safety['safety_level']}`",
            f"- Unsupervised hardware allowed: `{safety['free_walking_allowed']}`",
            "",
            "Evidence:",
            f"- Fall-free rollouts: {metrics['fall_free_count']}/{metrics['num_rollouts']}",
            f"- Avg velocity: {metrics['avg_velocity']:.3f} m/s",
            f"- Target velocity: {metrics['target_velocity']:.3f} m/s",
            f"- Torso pitch RMS: {metrics['torso_pitch_rms']:.2f} rad",
            f"- Joint limit max ratio: {metrics['joint_limit_max_ratio']:.2f}",
            "",
            "Required before any private lab hardware test:",
            *[f"- {item}" for item in safety["required_actions"]],
        ]
    )


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
