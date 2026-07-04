"""Convert a TensorBoard run directory into the Physical AI Safety Agent scalars.csv schema.

The training stack emits ``events.out.tfevents.*`` files containing scalar
tags such as ``Train/mean_reward``, ``Train/mean_episode_length`` and many
per-reward-term suffixes (see ``snapshot_training_metrics.py`` in the lab
repo). Physical AI Safety Agent's Streamlit UI consumes a simple CSV with the columns
``step, reward, fall_rate, avg_velocity, torso_pitch_rms, energy_proxy``.

This module parses the TensorBoard event file lazily (tensorboard is an
optional dependency), derives each Physical AI Safety Agent scalar from the available tags,
and writes the result next to the mock logs so the existing UI code in
``app.py`` works without modification.
"""

from __future__ import annotations

import csv
import glob
import math
import os
from pathlib import Path
from typing import Any, Iterable

# TensorBoard scalar tags we read, in priority order.
REWARD_TAG_CANDIDATES = [
    "Train/mean_rewards",
    "Train/mean_reward",
    "Episode_Reward/mean",
]
EPISODE_LENGTH_TAG_CANDIDATES = [
    "Train/mean_episode_length",
    "Train/mean_episode_lengths",
]

# Per-term tags used for derived scalars. We match by suffix because the
# full tag includes a reward namespace prefix.
FORWARD_VELOCITY_REWARD_SUFFIX = "forward_velocity_reward"
LATERAL_VELOCITY_REWARD_SUFFIX = "lateral_velocity_reward"
RAW_ACTION_SATURATION_SUFFIX = "raw_action_saturation_penalty"
TARGET_RATE_SUFFIX = "target_rate_penalty"
FORWARD_PITCH_SUFFIX = "forward_pitch_penalty"

# Sim env step in seconds (matches darwin_op_free_env.py).
SIM_DT_SEC = 0.02
# Approximate episode length (in env steps) used to derive fall_rate from
# episode length when no direct fall tag exists. The training stack uses
# 1000-step episodes by default for the Free task.
NOMINAL_EPISODE_STEPS = 1000


def has_tensorboard() -> bool:
    try:
        import tensorboard  # noqa: F401
    except Exception:
        return False
    return True


def find_event_files(run_dir: Path) -> list[Path]:
    return sorted(
        (Path(p) for p in glob.glob(os.path.join(str(run_dir), "events.out.tfevents.*"))),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
    )


def load_scalar_events(run_dir: Path) -> dict[str, list[tuple[int, float]]]:
    """Load every scalar tag from a TensorBoard run directory.

    Returns ``{tag: [(step, value), ...]}``. Raises ``RuntimeError`` when
    tensorboard is unavailable or no event files exist.
    """

    files = find_event_files(run_dir)
    if not files:
        raise RuntimeError(f"no TensorBoard event files under {run_dir}")
    try:
        from tensorboard.backend.event_processing import event_accumulator
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "tensorboard is not installed in this environment. Run the live "
            "adapter inside the IsaacLab/Isaac Sim venv where tensorboard is "
            "available, or install it with `pip install tensorboard`."
        ) from exc

    accumulator = event_accumulator.EventAccumulator(
        str(files[-1]),
        size_guidance={event_accumulator.SCALARS: 0},
    )
    accumulator.Reload()
    tags = accumulator.Tags().get("scalars", [])
    out: dict[str, list[tuple[int, float]]] = {}
    for tag in tags:
        events = accumulator.Scalars(tag)
        out[tag] = [(int(event.step), float(event.value)) for event in events]
    return out


def derive_scalars(scalars_by_tag: dict[str, list[tuple[int, float]]]) -> list[dict[str, float]]:
    """Project TensorBoard scalars onto Physical AI Safety Agent scalars.csv rows.

    The output columns are ``step, reward, fall_rate, avg_velocity,
    torso_pitch_rms, energy_proxy``. Each derived column is documented
    inline; missing tags fall back to neutral placeholders so the UI keeps
    rendering instead of crashing.
    """

    reward_tag = _first_match(scalars_by_tag, REWARD_TAG_CANDIDATES)
    episode_tag = _first_match(scalars_by_tag, EPISODE_LENGTH_TAG_CANDIDATES)
    fwd_vel_tag = _first_match_suffix(scalars_by_tag, FORWARD_VELOCITY_REWARD_SUFFIX)
    pitch_tag = _first_match_suffix(scalars_by_tag, FORWARD_PITCH_SUFFIX)
    sat_tag = _first_match_suffix(scalars_by_tag, RAW_ACTION_SATURATION_SUFFIX)
    rate_tag = _first_match_suffix(scalars_by_tag, TARGET_RATE_SUFFIX)

    if reward_tag is None:
        return []

    # Use the reward tag's step grid as the master index.
    reward_series = scalars_by_tag[reward_tag]
    steps_to_index = {step: idx for idx, (step, _) in enumerate(reward_series)}
    episode_series = scalars_by_tag.get(episode_tag, [])
    fwd_vel_series = scalars_by_tag.get(fwd_vel_tag, []) if fwd_vel_tag else []
    pitch_series = scalars_by_tag.get(pitch_tag, []) if pitch_tag else []
    sat_series = scalars_by_tag.get(sat_tag, []) if sat_tag else []
    rate_series = scalars_by_tag.get(rate_tag, []) if rate_tag else []

    rows: list[dict[str, float]] = []
    for step, reward in reward_series:
        episode_len = _sample_at(episode_series, step, default=NOMINAL_EPISODE_STEPS)
        fwd_vel_reward = _sample_at(fwd_vel_series, step, default=0.0)
        pitch_penalty = _sample_at(pitch_series, step, default=0.0)
        sat_penalty = _sample_at(sat_series, step, default=0.0)
        rate_penalty = _sample_at(rate_series, step, default=0.0)

        # fall_rate: shorter episodes mean more frequent termination. Map
        # episode length ratio -> fall probability in [0, 1].
        episode_ratio = max(0.0, min(1.0, episode_len / NOMINAL_EPISODE_STEPS))
        fall_rate = round(1.0 - episode_ratio, 4)

        # avg_velocity proxy: forward_velocity_reward sign and magnitude track
        # the achieved vx. The reward term is bounded, so we normalize.
        avg_velocity = round(_clamp(fwd_vel_reward * 0.02, 0.0, 0.20), 4)

        # torso_pitch_rms proxy: the forward_pitch_penalty grows with pitch
        # deviation. Roughly map the penalty into radians.
        torso_pitch_rms = round(_clamp(pitch_penalty * 0.05, 0.0, 1.0), 4)

        # energy_proxy: sum of saturation + rate penalties normalized to ~[0, 3].
        energy_proxy = round(_clamp((sat_penalty + rate_penalty) * 0.5, 0.0, 3.0), 4)

        rows.append(
            {
                "step": float(step),
                "reward": round(reward, 4),
                "fall_rate": fall_rate,
                "avg_velocity": avg_velocity,
                "torso_pitch_rms": torso_pitch_rms,
                "energy_proxy": energy_proxy,
            }
        )
    return rows


def write_scalars_csv(rows: Iterable[dict[str, float]], csv_path: Path) -> Path:
    """Write Physical AI Safety Agent scalars rows to ``csv_path`` and return it."""

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["step", "reward", "fall_rate", "avg_velocity", "torso_pitch_rms", "energy_proxy"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    return csv_path


def convert_run_dir(run_dir: Path, csv_path: Path) -> Path:
    """Parse a TensorBoard run dir and write the Physical AI Safety Agent scalars CSV."""

    scalars = load_scalar_events(run_dir)
    rows = derive_scalars(scalars)
    if not rows:
        raise RuntimeError(f"no reward scalar found in {run_dir}")
    return write_scalars_csv(rows, csv_path)


def _first_match(
    scalars_by_tag: dict[str, list[tuple[int, float]]],
    candidates: Iterable[str],
) -> str | None:
    for tag in candidates:
        if tag in scalars_by_tag:
            return tag
    return None


def _first_match_suffix(
    scalars_by_tag: dict[str, list[tuple[int, float]]],
    suffix: str,
) -> str | None:
    for tag in scalars_by_tag:
        if tag.endswith(suffix):
            return tag
    return None


def _sample_at(
    series: list[tuple[int, float]],
    step: int,
    default: float,
) -> float:
    """Return the value of ``series`` whose step is closest to ``step``."""

    if not series:
        return default
    # Linear scan is fine; these series are at most a few thousand points.
    closest_step, closest_value = series[0]
    closest_distance = abs(step - closest_step)
    for s, value in series:
        distance = abs(step - s)
        if distance < closest_distance:
            closest_distance = distance
            closest_step, closest_value = s, value
    return closest_value


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def summarize_for_audit(run_dir: Path, csv_path: Path) -> dict[str, Any]:
    """Return a secret-free audit summary of a TB -> CSV conversion."""

    event_files = find_event_files(run_dir)
    return {
        "run_dir": str(run_dir),
        "event_files": [str(p) for p in event_files],
        "output_csv": str(csv_path),
        "tensorboard_available": has_tensorboard(),
    }
