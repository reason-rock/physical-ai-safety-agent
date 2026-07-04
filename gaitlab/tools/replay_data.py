from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPLAY_ROOT = ROOT / "demo_data" / "real_replay"


def is_real_replay(data_mode: str) -> bool:
    return data_mode == "real_replay"


def load_replay_manifest() -> dict[str, Any]:
    path = REPLAY_ROOT / "real_replay_manifest.json"
    if not path.exists():
        raise FileNotFoundError(
            "Sanitized real replay manifest is missing. Run "
            "`.\\.venv\\Scripts\\python.exe scripts\\build_real_replay.py "
            "--control-csv <private-control.csv> --treatment-csv <private-treatment.csv>` "
            "or switch back to mock mode."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_replay_metrics(kind: str) -> dict[str, Any]:
    path = REPLAY_ROOT / "metrics" / f"{kind}_real_replay_eval.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing sanitized replay metrics: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def copy_replay_log(kind: str, run_id: str) -> Path:
    source = REPLAY_ROOT / "logs" / f"{kind}_real_replay_scalars.csv"
    if not source.exists():
        raise FileNotFoundError(f"Missing sanitized replay training log: {source}")
    target = ROOT / "demo_data" / "logs" / f"{run_id}_scalars.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def final_replay_row(kind: str) -> dict[str, str]:
    path = REPLAY_ROOT / "logs" / f"{kind}_real_replay_scalars.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing sanitized replay training log: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Replay training log has no rows: {path}")
    return rows[-1]


def replay_kind(run_id: str) -> str:
    return "treatment" if run_id.startswith("treatment") else "control"
