from __future__ import annotations

from gaitlab.tools.safety_tools import create_robot_action_diff, run_robot_safety_gate


class SafetyGateAgent:
    """Applies deterministic sim-to-real safety rules."""

    def __init__(self, strictness: str = "standard") -> None:
        self.strictness = strictness

    def run_gate(self, policy_id: str, metrics: dict) -> dict:
        return run_robot_safety_gate(policy_id, metrics, strictness=self.strictness)

    def create_robot_action_diff(self, policy_id: str, safety: dict, metrics: dict) -> str:
        return create_robot_action_diff(policy_id, safety, metrics)

