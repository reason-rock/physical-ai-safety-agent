from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gaitlab.tools.replay_data import is_real_replay, load_replay_metrics, replay_kind


ROOT = Path(__file__).resolve().parents[2]


def evaluate_policy_on_pc(
    checkpoint_path: str,
    eval_config: str,
    num_rollouts: int,
    data_mode: str = "mock",
) -> dict[str, Any]:
    """Return Researcher PC metrics for the selected public-demo evidence mode."""

    run_id = Path(checkpoint_path).parent.name
    is_treatment = run_id.startswith("treatment")
    if is_real_replay(data_mode):
        metrics = load_replay_metrics(replay_kind(run_id))
    else:
        metrics = _treatment_metrics(num_rollouts) if is_treatment else _control_metrics(num_rollouts)

    metrics = dict(metrics)
    metrics["run_id"] = run_id
    metrics["checkpoint"] = Path(checkpoint_path).name
    metrics["eval_config"] = eval_config
    metrics["evidence_mode"] = "sanitized_real_replay" if is_real_replay(data_mode) else "deterministic_mock"

    path = ROOT / "demo_data" / "metrics" / f"{run_id}_eval.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return metrics


def compare_experiment_pair(
    control_run_id: str,
    treatment_run_id: str,
    evaluations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    control = evaluations[control_run_id]
    treatment = evaluations[treatment_run_id]

    metric_rows = [
        _row(
            "Fall-free rollouts",
            f"{control['fall_free_count']}/{control['num_rollouts']}",
            f"{treatment['fall_free_count']}/{treatment['num_rollouts']}",
            _higher_is_better(treatment["fall_free_count"], control["fall_free_count"]),
        ),
        _row(
            "Avg fall time",
            f"{control['avg_fall_time_sec']:.1f}s",
            f"{treatment['avg_fall_time_sec']:.1f}s",
            _higher_is_better(treatment["avg_fall_time_sec"], control["avg_fall_time_sec"]),
        ),
        _row(
            "Torso pitch RMS",
            f"{control['torso_pitch_rms']:.2f}",
            f"{treatment['torso_pitch_rms']:.2f}",
            _lower_is_better(treatment["torso_pitch_rms"], control["torso_pitch_rms"]),
        ),
        _row(
            "Avg velocity",
            f"{control['avg_velocity']:.3f}",
            f"{treatment['avg_velocity']:.3f}",
            _higher_is_better(treatment["avg_velocity"], control["avg_velocity"], tolerance=0.002),
        ),
        _row(
            "Energy proxy",
            f"{control['energy_proxy']:.2f}",
            f"{treatment['energy_proxy']:.2f}",
            _lower_is_better(treatment["energy_proxy"], control["energy_proxy"], tolerance=0.02),
        ),
        _row(
            "Joint limit ratio",
            f"{control['joint_limit_max_ratio']:.2f}",
            f"{treatment['joint_limit_max_ratio']:.2f}",
            _lower_is_better(treatment["joint_limit_max_ratio"], control["joint_limit_max_ratio"], tolerance=0.02),
        ),
    ]

    velocity_ratio = treatment["avg_velocity"] / max(treatment["target_velocity"], 1e-9)
    if treatment["fall_free_count"] > control["fall_free_count"] and velocity_ratio < 0.85:
        decision = "safer_but_slower"
        recommendation = "supported_test_only"
    elif treatment["fall_free_count"] < control["fall_free_count"]:
        decision = "faster_but_unsafe"
        recommendation = "blocked"
    elif treatment["fall_free_count"] == treatment["num_rollouts"] and velocity_ratio >= 0.9:
        decision = "candidate_improvement"
        recommendation = "candidate_for_free_walking"
    else:
        decision = "needs_follow_up_experiment"
        recommendation = "supported_test_only"

    return {
        "decision": decision,
        "recommendation": recommendation,
        "improvements": [
            "fall-free rollouts improved",
            "average fall time improved",
            "torso pitch RMS reduced",
        ],
        "regressions": [
            "average velocity reduced",
            "energy proxy increased",
            "joint limit ratio increased",
        ],
        "metric_rows": metric_rows,
    }


def _row(metric: str, control: str, treatment: str, verdict: str) -> dict[str, str]:
    return {"metric": metric, "control": control, "treatment": treatment, "verdict": verdict}


def _higher_is_better(treatment: float, control: float, tolerance: float = 0.0) -> str:
    if treatment > control + tolerance:
        return "Improved"
    if treatment < control - tolerance:
        return "Regressed"
    return "Neutral"


def _lower_is_better(treatment: float, control: float, tolerance: float = 0.0) -> str:
    if treatment < control - tolerance:
        return "Improved"
    if treatment > control + tolerance:
        return "Regressed"
    return "Neutral"


def _control_metrics(num_rollouts: int) -> dict[str, Any]:
    fall_free = max(0, round(num_rollouts * 0.60))
    return {
        "num_rollouts": num_rollouts,
        "fall_free_count": fall_free,
        "avg_fall_time_sec": 3.2,
        "avg_velocity": 0.052,
        "target_velocity": 0.055,
        "torso_pitch_rms": 0.31,
        "energy_proxy": 1.00,
        "joint_limit_max_ratio": 0.81,
        "foot_contact_symmetry": 0.68,
        "action_jerk": 0.24,
        "emergency_stop_dry_run": False,
    }


def _treatment_metrics(num_rollouts: int) -> dict[str, Any]:
    fall_free = min(num_rollouts, round(num_rollouts * 0.90))
    return {
        "num_rollouts": num_rollouts,
        "fall_free_count": fall_free,
        "avg_fall_time_sec": 8.9,
        "avg_velocity": 0.041,
        "target_velocity": 0.055,
        "torso_pitch_rms": 0.18,
        "energy_proxy": 1.18,
        "joint_limit_max_ratio": 0.92,
        "foot_contact_symmetry": 0.74,
        "action_jerk": 0.28,
        "emergency_stop_dry_run": False,
    }
