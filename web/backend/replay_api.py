"""HTTP router for Sanitized Real Replay data.

Serves the replay manifest, per-run scalars CSVs, and per-run eval JSON
from ``demo_data/real_replay/`` so the frontend can browse past training
records when the user selects ``Sanitized Real Replay`` mode.
"""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from gaitlab.config import ROOT


router = APIRouter(prefix="/api/replay", tags=["replay"])

REPLAY_ROOT = ROOT / "demo_data" / "real_replay"


def _manifest_path() -> Path:
    return REPLAY_ROOT / "real_replay_manifest.json"


@router.get("/manifest")
def get_manifest() -> dict[str, Any]:
    """Return the replay manifest with the list of available runs."""

    path = _manifest_path()
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="No replay manifest found. Run scripts/build_real_replay.py first.",
        )
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/runs")
def list_runs() -> dict[str, Any]:
    """Return a flat list of available replay runs with their metadata."""

    manifest = get_manifest()
    runs: list[dict[str, Any]] = []
    for role, info in manifest.get("runs", {}).items():
        runs.append(
            {
                "role": role,
                "alias": info.get("alias", role),
                "source_kind": info.get("source_kind", ""),
                "rows": info.get("rows", 0),
                "duration_sec": info.get("duration_sec", 0),
                "metrics_file": info.get("metrics_file", ""),
                "scalars_file": info.get("scalars_file", ""),
            }
        )
    return {"runs": runs, "dataset": manifest.get("dataset", ""), "privacy": manifest.get("privacy", {})}


@router.get("/runs/{role}/scalars")
def get_run_scalars(role: str) -> dict[str, Any]:
    """Return the scalars CSV for one replay run as JSON rows."""

    manifest = get_manifest()
    run_info = manifest.get("runs", {}).get(role)
    if not run_info:
        raise HTTPException(status_code=404, detail=f"Unknown replay run: {role}")
    scalars_path = REPLAY_ROOT / run_info["scalars_file"]
    if not scalars_path.exists():
        raise HTTPException(status_code=404, detail=f"Scalars file not found: {scalars_path}")
    rows = _parse_csv(scalars_path)
    return {"role": role, "alias": run_info.get("alias", role), "rows": rows}


@router.get("/runs/{role}/metrics")
def get_run_metrics(role: str) -> dict[str, Any]:
    """Return the eval metrics JSON for one replay run."""

    manifest = get_manifest()
    run_info = manifest.get("runs", {}).get(role)
    if not run_info:
        raise HTTPException(status_code=404, detail=f"Unknown replay run: {role}")
    metrics_path = REPLAY_ROOT / run_info["metrics_file"]
    if not metrics_path.exists():
        raise HTTPException(status_code=404, detail=f"Metrics file not found: {metrics_path}")
    return json.loads(metrics_path.read_text(encoding="utf-8"))


@router.get("/runs/{role}/full")
def get_run_full(role: str) -> dict[str, Any]:
    """Return scalars + metrics for one run in a single response."""

    return {
        "role": role,
        "scalars": get_run_scalars(role),
        "metrics": get_run_metrics(role),
    }


@router.get("/compare")
def get_compare() -> dict[str, Any]:
    """Return all replay runs' scalars + metrics in one shot for the comparison view."""

    manifest = get_manifest()
    out: dict[str, Any] = {}
    for role in manifest.get("runs", {}):
        out[role] = get_run_full(role)
    out["manifest"] = manifest
    return out


def _parse_csv(path: Path) -> list[dict[str, Any]]:
    """Parse a CSV into a list of dicts, coercing numeric columns."""

    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(StringIO(text))
    rows: list[dict[str, Any]] = []
    for row in reader:
        coerced: dict[str, Any] = {}
        for key, value in row.items():
            coerced[key] = _try_number(value)
        rows.append(coerced)
    return rows


def _try_number(value: str) -> int | float | str:
    try:
        return int(value)
    except (ValueError, TypeError):
        pass
    try:
        return float(value)
    except (ValueError, TypeError):
        pass
    return value
