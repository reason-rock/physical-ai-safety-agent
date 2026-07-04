from __future__ import annotations


class FailureAnalysisAgent:
    """Classifies physical-AI demo failure signatures from comparison and metrics."""

    def analyze(self, comparison: dict, treatment_metrics: dict) -> dict:
        failures: list[str] = []
        causes: list[str] = []
        next_steps: list[str] = []

        if treatment_metrics["fall_free_count"] < treatment_metrics["num_rollouts"]:
            failures.append("residual_forward_fall_risk")
            causes.append("orientation stability improved but is not complete")
            next_steps.append("keep orientation penalty and add recovery reward after stable stance")
        if treatment_metrics["avg_velocity"] < treatment_metrics["target_velocity"] * 0.85:
            failures.append("slow_or_over_conservative_gait")
            causes.append("stability terms may be suppressing forward motion")
            next_steps.append("reduce action smoothing or add velocity recovery after safety threshold")
        if treatment_metrics["joint_limit_max_ratio"] >= 0.90:
            failures.append("joint_limit_risk")
            causes.append("candidate policy approaches configured joint limits")
            next_steps.append("reduce action scale before any supported hardware test")

        if not failures:
            failures.append("no_major_failure_detected")
            causes.append("treatment passes the public demo evaluation thresholds")
            next_steps.append("run additional seeds before private lab deployment")

        return {
            "failure_categories": failures,
            "likely_causes": causes,
            "next_experiment": next_steps,
            "summary": comparison["decision"],
        }
