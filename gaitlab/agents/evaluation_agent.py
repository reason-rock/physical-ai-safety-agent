from __future__ import annotations

from gaitlab.tools.evaluation_tools import compare_experiment_pair, evaluate_policy_on_pc


class EvaluationAgent:
    """Runs Researcher PC evaluation and compares control/treatment metrics."""

    def __init__(self, num_rollouts: int = 10, data_mode: str = "mock") -> None:
        self.num_rollouts = num_rollouts
        self.data_mode = data_mode

    def evaluate(self, run_id: str) -> dict:
        return evaluate_policy_on_pc(
            checkpoint_path=f"demo_data/artifacts/{run_id}/ckpt_20m.pt",
            eval_config="specs/safety_gate_spec.md",
            num_rollouts=self.num_rollouts,
            data_mode=self.data_mode,
        )

    def compare(
        self,
        control_run_id: str,
        treatment_run_id: str,
        evaluations: dict[str, dict],
    ) -> dict:
        return compare_experiment_pair(control_run_id, treatment_run_id, evaluations)
