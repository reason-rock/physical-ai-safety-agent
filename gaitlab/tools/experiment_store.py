from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
COUNTER_PATH = ROOT / "demo_data" / "run_id_counter.json"
RUN_ID_FLOOR = 10000
RUN_ID_BLOCK_SIZE = 3


def create_experiment_pair(
    baseline_config: str,
    treatment_patch: dict[str, float],
    control_node: str,
    treatment_node: str,
    paired_seeds: list[int],
) -> dict[str, Any]:
    """Create a public-demo experiment pair with non-conflicting live-safe IDs."""

    pair_num, control_num, treatment_num = _allocate_run_numbers()
    pair_id = f"pair_{pair_num}"
    control_run_id = f"control_{control_num}"
    treatment_run_id = f"treatment_{treatment_num}"

    control = {
        "run_id": control_run_id,
        "node": control_node,
        "base_config": baseline_config,
        "patch": {},
        "paired_seeds": paired_seeds,
        "config_path": f"demo_data/configs/{control_run_id}.yaml",
    }
    treatment = {
        "run_id": treatment_run_id,
        "node": treatment_node,
        "base_config": baseline_config,
        "patch": treatment_patch,
        "paired_seeds": paired_seeds,
        "config_path": f"demo_data/configs/{treatment_run_id}.yaml",
    }

    _write_run_config(control)
    _write_run_config(treatment)

    return {
        "pair_id": pair_id,
        "control_run_id": control_run_id,
        "treatment_run_id": treatment_run_id,
        "control_config": control["config_path"],
        "treatment_config": treatment["config_path"],
        "control": control,
        "treatment": treatment,
    }


def _allocate_run_numbers() -> tuple[int, int, int]:
    """Reserve a 10k-range ID block for pair/control/treatment.

    The lab may already contain many manually launched or historical runs, so
    the app never emits small demo IDs such as ``044``. A persisted counter is
    combined with a filesystem scan so deleting the counter does not make the
    next generated plan collide with existing local artifacts.
    """

    next_id = max(_read_counter(), _scan_existing_max_id() + 1, RUN_ID_FLOOR)
    pair_num = next_id
    control_num = next_id + 1
    treatment_num = next_id + 2
    _write_counter(next_id + RUN_ID_BLOCK_SIZE)
    return pair_num, control_num, treatment_num


def _read_counter() -> int:
    try:
        data = json.loads(COUNTER_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return RUN_ID_FLOOR
    value = data.get("next_run_id")
    return value if isinstance(value, int) else RUN_ID_FLOOR


def _write_counter(next_run_id: int) -> None:
    COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    COUNTER_PATH.write_text(
        json.dumps({"next_run_id": next_run_id}, indent=2) + "\n",
        encoding="utf-8",
    )


def _scan_existing_max_id() -> int:
    max_id = RUN_ID_FLOOR - 1
    for base in (
        ROOT / "demo_data" / "configs",
        ROOT / "demo_data" / "logs",
        ROOT / "demo_data" / "artifacts",
        ROOT / "demo_data" / "metrics",
        ROOT / "demo_data" / "live_logs",
        ROOT / "deployment",
    ):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            max_id = max(max_id, _extract_max_10k_id(path.name))
    return max_id


def _extract_max_10k_id(text: str) -> int:
    matches = [
        int(m)
        for m in re.findall(
            r"(?:pair|control|treatment)_(\d{5,})(?!\d)",
            text,
        )
    ]
    return max(matches, default=RUN_ID_FLOOR - 1)


def _write_run_config(config: dict[str, Any]) -> None:
    path = ROOT / config["config_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    text = [
        f"run_id: {config['run_id']}",
        f"node: {config['node']}",
        f"base_config: {config['base_config']}",
        "controlled_variables:",
        "  robot_model: darwin_op",
        "  sim_backend: mock_public_demo",
        "  total_steps: 20000000",
        "  target_velocity: 0.055",
        "  sim_timestep: 0.008",
        f"  paired_seeds: {json.dumps(config['paired_seeds'])}",
        "patch:",
    ]
    if config["patch"]:
        for key, value in config["patch"].items():
            text.append(f"  {key}: {value}")
    else:
        text.append("  {}")
    path.write_text("\n".join(text) + "\n", encoding="utf-8")
