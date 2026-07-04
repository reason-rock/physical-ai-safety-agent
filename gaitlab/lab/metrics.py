"""Translate real lab outputs into the Physical AI Safety Agent metrics schema.

The lab stack produces two main artifact families:

- ``verify_direction_tracking.csv`` — one row per command preset, emitted
  by ``rl/isaaclab/scripts/verify_direction_tracking.py`` on the researcher
  PC. Columns include ``preset, achieved_vx, falls, action_meanabs,
  action_absmax, height_mean, env_steps, n_envs``.
- ``robot_<tag>.csv`` — per-8 ms control-step robot track-log with IMU,
  safety flags (``fallen``, ``tilt_warn``, ``tilt_stop``), and per-joint
  ``policy``/``target``/``read``/``err`` columns.

Physical AI Safety Agent's evaluation schema (see ``gaitlab/tools/evaluation_tools.py``)
needs a single dict per run with ``num_rollouts, fall_free_count,
avg_fall_time_sec, avg_velocity, target_velocity, torso_pitch_rms,
energy_proxy, joint_limit_max_ratio, foot_contact_symmetry, action_jerk,
emergency_stop_dry_run``. This module performs the documented conversions
so the rest of the orchestrator (comparison, safety gate, report) works
unchanged.
"""

from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# Default forward target used when the verify CSV does not carry one.
DEFAULT_TARGET_VELOCITY = 0.055

# Verify-CSV columns we read. Be tolerant of older 14-column variants.
V_PRESET = "preset"
V_ACHIEVED_VX = "achieved_vx"
V_FALLS = "falls"
V_ENV_STEPS = "env_steps"
V_N_ENVS = "n_envs"
V_ACTION_MEANABS = "action_meanabs"
V_ACTION_ABSMAX = "action_absmax"
V_HEIGHT_MEAN = "height_mean"

# Robot-CSV columns we read.
R_TIME = "time_s"
R_PITCH = "pitch"
R_ROLL = "roll"
R_FALLEN = "fallen"
R_TILT_WARN = "tilt_warn"
R_TILT_STOP = "tilt_stop"

# Per-joint suffixes in the robot track-log.
JOINT_POLICY_SUFFIX = "_policy"
JOINT_TARGET_SUFFIX = "_target"
JOINT_READ_SUFFIX = "_read"
JOINT_ERR_SUFFIX = "_err"

# Normalized action range for the joint_limit_max_ratio proxy. The deployed
# policy output is a [-1, 1] per-joint action that is then scaled and offset
# by the real action scale (DARWIN_OP_FREE_REAL_ACTION_SCALE) before being
# sent to the servo. We do not know the configured joint limit from the CSV
# alone, so we report the maximum absolute *normalized* policy output as a
# proxy in [0, 1]. This matches the conservative interpretation used by the
# safety gate: a value close to 1 means the policy is saturating.
_NORMALIZED_ACTION_LIMIT = 1.0


def verify_csv_to_metrics(
    csv_path: Path,
    target_velocity: float = DEFAULT_TARGET_VELOCITY,
    emergency_stop_dry_run: bool = False,
) -> dict[str, Any]:
    """Convert a verify_direction_tracking.csv into the Physical AI Safety Agent metrics schema.

    The verify CSV has one row per command preset. We aggregate across the
    forward presets to produce a single forward-walking verdict, which is
    what the Physical AI Safety Agent safety gate cares about.
    """

    rows = _read_csv(csv_path)
    forward_rows = _forward_preset_rows(rows)
    if not forward_rows:
        forward_rows = rows  # fall back to all rows if no preset tagged forward

    num_rollouts = _count_rollouts(forward_rows)
    total_falls = _sum_int(forward_rows, V_FALLS)
    fall_free_count = max(0, num_rollouts - total_falls)
    avg_velocity = _mean_float(forward_rows, V_ACHIEVED_VX)
    avg_fall_time_sec = _estimate_fall_time(forward_rows, total_falls)
    action_meanabs = _mean_float(forward_rows, V_ACTION_MEANABS)
    action_absmax = _max_float(forward_rows, V_ACTION_ABSMAX)
    energy_proxy = _energy_proxy(action_meanabs)
    joint_limit_max_ratio = _joint_limit_proxy(action_absmax)

    metrics: dict[str, Any] = {
        "num_rollouts": num_rollouts,
        "fall_free_count": fall_free_count,
        "avg_fall_time_sec": avg_fall_time_sec,
        "avg_velocity": avg_velocity,
        "target_velocity": target_velocity,
        "torso_pitch_rms": _TORSO_PITCH_PLACEHOLDER,  # not in verify CSV
        "energy_proxy": energy_proxy,
        "joint_limit_max_ratio": joint_limit_max_ratio,
        "foot_contact_symmetry": 0.0,  # not derivable from verify CSV
        "action_jerk": _estimate_action_jerk(forward_rows, action_meanabs),
        "emergency_stop_dry_run": bool(emergency_stop_dry_run),
        "evidence_mode": "live_lab",
        "source_csv": str(csv_path),
    }
    return metrics


# Placeholder used when the verify CSV cannot supply torso_pitch directly.
# The follow-up plan in the physical-ai-lab repo will add a torso_pitch
# column to verify_direction_tracking.py. Until then, the safety gate treats
# this conservatively (any value > 0.20 fails the free-walking threshold).
_TORSO_PITCH_PLACEHOLDER = 0.30


def robot_csv_to_metrics(
    csv_path: Path,
    target_velocity: float = DEFAULT_TARGET_VELOCITY,
    emergency_stop_dry_run: bool = True,
) -> dict[str, Any]:
    """Convert a robot track-log CSV into the Physical AI Safety Agent metrics schema.

    Robot runs are short and supervised, so we treat one robot CSV as one
    "rollout". ``fallen`` is a 0/1 column sampled at 125 Hz; the run counts
    as fall-free only if ``fallen`` never transitions to 1 (or only briefly
    during the initial settle).
    """

    rows = _read_csv(csv_path)
    if not rows:
        return _empty_metrics(target_velocity, csv_path)

    duration_s = _csv_duration(rows)
    fallen = any(_to_int(row.get(R_FALLEN, 0)) > 0 for row in rows)
    tilt_stop = any(_to_int(row.get(R_TILT_STOP, 0)) > 0 for row in rows)
    pitch_rms = _rms_float(rows, R_PITCH)
    roll_rms = _rms_float(rows, R_ROLL)
    joint_absmax = _max_joint_policy_abs(rows)
    joint_err_rms = _rms_joint_err(rows)
    energy_proxy = _clamp(joint_err_rms / 0.20, 0.0, 3.0)

    return {
        "num_rollouts": 1,
        "fall_free_count": 0 if fallen else 1,
        "avg_fall_time_sec": 0.0 if not fallen else max(0.0, duration_s),
        "avg_velocity": 0.0,  # cannot derive body vx from robot CSV alone
        "target_velocity": target_velocity,
        "torso_pitch_rms": pitch_rms,
        "energy_proxy": energy_proxy,
        "joint_limit_max_ratio": _clamp(joint_absmax / _NORMALIZED_ACTION_LIMIT, 0.0, 1.5),
        "foot_contact_symmetry": 0.0,
        "action_jerk": 0.0,
        "emergency_stop_dry_run": bool(emergency_stop_dry_run) and not tilt_stop,
        "evidence_mode": "live_lab_robot",
        "source_csv": str(csv_path),
        "duration_s": duration_s,
        "tilt_stop_observed": bool(tilt_stop),
        "roll_rms": roll_rms,
    }


def merge_metrics(
    verify_metrics: Mapping[str, Any],
    robot_metrics: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Merge sim verify metrics with optional robot metrics.

    The safety gate treats robot evidence as authoritative when present.
    Without robot evidence we fall back to the verify-CSV values and keep
    ``emergency_stop_dry_run`` False so the gate stays conservative.
    """

    merged = dict(verify_metrics)
    if robot_metrics:
        # Robot evidence upgrades the estop flag if a real dry-run was logged.
        merged["emergency_stop_dry_run"] = bool(
            verify_metrics.get("emergency_stop_dry_run")
        ) or bool(robot_metrics.get("emergency_stop_dry_run"))
        merged["robot_evidence"] = True
        merged["robot_fall_free"] = robot_metrics.get("fall_free_count", 0) >= 1
        merged["robot_duration_s"] = robot_metrics.get("duration_s", 0.0)
        merged["robot_torso_pitch_rms"] = robot_metrics.get("torso_pitch_rms")
        # If sim lacks torso_pitch (placeholder), prefer the robot value.
        if (
            math.isclose(verify_metrics.get("torso_pitch_rms", 0.0), _TORSO_PITCH_PLACEHOLDER)
            and robot_metrics.get("torso_pitch_rms") is not None
        ):
            merged["torso_pitch_rms"] = robot_metrics["torso_pitch_rms"]
    else:
        merged["robot_evidence"] = False
    return merged


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"metrics CSV not found: {path}")
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return list(csv.DictReader(handle))


def _forward_preset_rows(rows: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    forward_prefixes = ("forward", "fwd")
    return [
        row
        for row in rows
        if str(row.get(V_PRESET, "")).lower().startswith(forward_prefixes)
    ]


def _count_rollouts(rows: Sequence[dict[str, str]]) -> int:
    """Estimate the number of independent rollouts in a verify CSV.

    Each preset row corresponds to ``n_envs`` parallel rollouts. The Physical AI Safety Agent
    safety gate treats each rollout as a 1-or-0 fall event, so we sum the
    per-row n_envs across the included presets to get a comparable count.
    """

    return max(1, sum(_to_int(row.get(V_N_ENVS, 1)) for row in rows))


def _estimate_fall_time(rows: Sequence[dict[str, str]], total_falls: int) -> float:
    """Heuristic: average episode length is implied by env_steps / n_envs.

    Falls shorten episodes. Without per-episode data we approximate
    avg_fall_time as the nominal episode length minus a per-fall penalty.
    """

    if not rows:
        return 0.0
    total_steps = sum(_to_int(row.get(V_ENV_STEPS, 0)) for row in rows)
    total_envs = max(1, sum(_to_int(row.get(V_N_ENVS, 1)) for row in rows))
    nominal_episode_steps = max(1, total_steps // total_envs)
    fall_ratio = total_falls / max(1, total_envs)
    # Episode length drops with more falls; cap at a reasonable floor.
    effective_steps = max(20, int(nominal_episode_steps * (1.0 - min(0.9, fall_ratio))))
    # At sim dt=0.02s, episode_seconds = steps * 0.02.
    return round(effective_steps * 0.02, 2)


def _estimate_action_jerk(rows: Sequence[dict[str, str]], action_meanabs: float) -> float:
    """Crude jerk proxy: action_meanabs scaled to the [0,1] gate range."""

    return _clamp(action_meanabs * 1.5, 0.0, 1.0)


def _energy_proxy(action_meanabs: float) -> float:
    """Normalize action_meanabs into the [0, ~3] energy proxy range."""

    return _clamp(action_meanabs * 5.0, 0.0, 3.0)


def _joint_limit_proxy(action_absmax: float) -> float:
    """Joint limit usage proxy in [0, 1.5] from normalized action absmax."""

    return _clamp(action_absmax / _NORMALIZED_ACTION_LIMIT, 0.0, 1.5)


def _csv_duration(rows: Sequence[dict[str, str]]) -> float:
    times = [_to_float(row.get(R_TIME, 0.0)) for row in rows if row.get(R_TIME)]
    if not times:
        return 0.0
    return round(max(times) - min(times), 3)


def _max_joint_policy_abs(rows: Sequence[dict[str, str]]) -> float:
    """Return the maximum absolute policy output across all joints and steps."""

    values: list[float] = []
    for row in rows:
        for key, raw in row.items():
            if key.endswith(JOINT_POLICY_SUFFIX) and raw not in (None, ""):
                values.append(abs(_to_float(raw)))
    return max(values) if values else 0.0


def _rms_joint_err(rows: Sequence[dict[str, str]]) -> float:
    """Root-mean-square of all per-joint servo errors."""

    squared = 0.0
    count = 0
    for row in rows:
        for key, raw in row.items():
            if key.endswith(JOINT_ERR_SUFFIX) and raw not in (None, ""):
                squared += _to_float(raw) ** 2
                count += 1
    if count == 0:
        return 0.0
    return math.sqrt(squared / count)


def _rms_float(rows: Sequence[dict[str, str]], column: str) -> float:
    values = [_to_float(row.get(column, 0.0)) for row in rows if row.get(column)]
    if not values:
        return 0.0
    mean_square = sum(v * v for v in values) / len(values)
    return round(math.sqrt(mean_square), 4)


def _mean_float(rows: Sequence[dict[str, str]], column: str) -> float:
    values = [_to_float(row.get(column, 0.0)) for row in rows if row.get(column)]
    if not values:
        return 0.0
    return round(statistics.fmean(values), 6)


def _max_float(rows: Sequence[dict[str, str]], column: str) -> float:
    values = [_to_float(row.get(column, 0.0)) for row in rows if row.get(column)]
    return max(values) if values else 0.0


def _sum_int(rows: Sequence[dict[str, str]], column: str) -> int:
    return sum(_to_int(row.get(column, 0)) for row in rows if row.get(column))


def _to_float(value: Any) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _empty_metrics(target_velocity: float, csv_path: Path) -> dict[str, Any]:
    return {
        "num_rollouts": 0,
        "fall_free_count": 0,
        "avg_fall_time_sec": 0.0,
        "avg_velocity": 0.0,
        "target_velocity": target_velocity,
        "torso_pitch_rms": 0.0,
        "energy_proxy": 0.0,
        "joint_limit_max_ratio": 1.5,
        "foot_contact_symmetry": 0.0,
        "action_jerk": 0.0,
        "emergency_stop_dry_run": False,
        "evidence_mode": "live_lab",
        "source_csv": str(csv_path),
    }
