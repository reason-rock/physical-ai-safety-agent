from __future__ import annotations

import csv
import json
from pathlib import Path

from gaitlab.tools.replay_data import copy_replay_log, final_replay_row, is_real_replay, replay_kind


ROOT = Path(__file__).resolve().parents[2]


def submit_training_job(node: str, run_id: str, config_path: str, data_mode: str = "mock") -> dict:
    """Submit a deterministic public-demo training job."""

    is_treatment = run_id.startswith("treatment")
    if is_real_replay(data_mode):
        kind = replay_kind(run_id)
        copy_replay_log(kind, run_id)
        _write_checkpoint_meta(run_id, is_treatment, data_mode=data_mode)
        final_row = final_replay_row(kind)
        return {
            "job_id": f"{node.lower()}_replay_20260624_001",
            "node": node,
            "run_id": run_id,
            "config_path": config_path,
            "status": "completed_sanitized_real_replay",
            "progress": 1.0,
            "latest_step": int(float(final_row["step"])),
            "estimated_remaining_min": 0,
            "latest_reward": float(final_row["reward"]),
            "fall_rate": float(final_row["fall_rate"]),
            "evidence_mode": "sanitized_real_replay",
        }

    job = {
        "job_id": f"{node.lower()}_job_20260624_001",
        "node": node,
        "run_id": run_id,
        "config_path": config_path,
        "status": "completed_mock",
        "progress": 1.0,
        "latest_step": 20_000_000,
        "estimated_remaining_min": 0,
        "latest_reward": 64.8 if is_treatment else 52.0,
        "fall_rate": 0.10 if is_treatment else 0.40,
        "evidence_mode": "deterministic_mock",
    }
    _write_training_log(run_id, is_treatment)
    _write_checkpoint_meta(run_id, is_treatment, data_mode=data_mode)
    return job


def collect_training_artifacts(run_id: str, data_mode: str = "mock") -> dict:
    """Return artifact paths for a completed public-demo run."""

    artifact_dir = ROOT / "demo_data" / "artifacts" / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    ckpts = ["ckpt_10m.pt", "ckpt_15m.pt", "ckpt_20m.pt"]
    for ckpt in ckpts:
        path = artifact_dir / ckpt
        if not path.exists():
            placeholder = (
                "sanitized real replay checkpoint reference\n"
                if is_real_replay(data_mode)
                else "mock checkpoint placeholder\n"
            )
            path.write_text(placeholder, encoding="utf-8")
    return {
        "run_id": run_id,
        "log_path": f"demo_data/logs/{run_id}_scalars.csv",
        "checkpoints": [f"demo_data/artifacts/{run_id}/{ckpt}" for ckpt in ckpts],
        "checkpoint_meta": f"demo_data/artifacts/{run_id}/checkpoint_meta.json",
        "evidence_mode": "sanitized_real_replay" if is_real_replay(data_mode) else "deterministic_mock",
    }


def _write_training_log(run_id: str, is_treatment: bool) -> None:
    path = ROOT / "demo_data" / "logs" / f"{run_id}_scalars.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = _treatment_rows() if is_treatment else _control_rows()
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "step",
                "reward",
                "fall_rate",
                "avg_velocity",
                "torso_pitch_rms",
                "energy_proxy",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_checkpoint_meta(run_id: str, is_treatment: bool, data_mode: str = "mock") -> None:
    artifact_dir = ROOT / "demo_data" / "artifacts" / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    real_replay = is_real_replay(data_mode)
    meta = {
        "run_id": run_id,
        "selected_checkpoint": "ckpt_20m.pt",
        "selection_reason": "best stability window with complete public-demo metrics"
        if is_treatment
        else "baseline checkpoint at matched training budget",
        "mock_only": not real_replay,
        "sanitized_real_replay": real_replay,
        "raw_checkpoint_included": False,
    }
    (artifact_dir / "checkpoint_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )


def _control_rows() -> list[dict]:
    return [
        {"step": 1_000_000, "reward": 12.4, "fall_rate": 0.80, "avg_velocity": 0.031, "torso_pitch_rms": 0.42, "energy_proxy": 0.90},
        {"step": 5_000_000, "reward": 28.7, "fall_rate": 0.60, "avg_velocity": 0.044, "torso_pitch_rms": 0.35, "energy_proxy": 1.00},
        {"step": 10_000_000, "reward": 44.2, "fall_rate": 0.40, "avg_velocity": 0.052, "torso_pitch_rms": 0.31, "energy_proxy": 1.05},
        {"step": 15_000_000, "reward": 49.1, "fall_rate": 0.30, "avg_velocity": 0.050, "torso_pitch_rms": 0.29, "energy_proxy": 1.10},
        {"step": 20_000_000, "reward": 52.0, "fall_rate": 0.40, "avg_velocity": 0.052, "torso_pitch_rms": 0.31, "energy_proxy": 1.00},
    ]


def _treatment_rows() -> list[dict]:
    return [
        {"step": 1_000_000, "reward": 14.2, "fall_rate": 0.70, "avg_velocity": 0.030, "torso_pitch_rms": 0.39, "energy_proxy": 0.98},
        {"step": 5_000_000, "reward": 35.5, "fall_rate": 0.40, "avg_velocity": 0.038, "torso_pitch_rms": 0.28, "energy_proxy": 1.05},
        {"step": 10_000_000, "reward": 56.3, "fall_rate": 0.20, "avg_velocity": 0.042, "torso_pitch_rms": 0.22, "energy_proxy": 1.12},
        {"step": 15_000_000, "reward": 62.0, "fall_rate": 0.10, "avg_velocity": 0.041, "torso_pitch_rms": 0.19, "energy_proxy": 1.16},
        {"step": 20_000_000, "reward": 64.8, "fall_rate": 0.10, "avg_velocity": 0.041, "torso_pitch_rms": 0.18, "energy_proxy": 1.18},
    ]
