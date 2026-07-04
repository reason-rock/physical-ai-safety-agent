"""Mapping table between Physical AI Safety Agent dotted-patch keys and lab env vars.

Physical AI Safety Agent's experiment design layer speaks a small dotted YAML vocabulary
(e.g. ``reward.orientation_penalty``). The real training stack in
``physical-ai-lab`` is driven by ``DARWIN_OP_FREE_*`` environment
variables sourced from ``scripts/stages/<name>.env`` files.

This module is the single source of truth for that translation. Unknown
patch keys fall through to raw env-var passthrough so advanced users can
still set any ``DARWIN_OP_FREE_*`` value directly via the patch dict.
"""

from __future__ import annotations

from typing import Iterable, Mapping

# Dotted Physical AI Safety Agent patch key -> lab env var name.
# Keep this in sync with the keys documented in the plan and in
# gaitlab/lab/stage_env.py.
GAITLAB_PATCH_TO_ENV: dict[str, str] = {
    # reward terms (multipliers unless overridden)
    "reward.orientation_penalty": "DARWIN_OP_FREE_FORWARD_PITCH_PENALTY_WEIGHT",
    "reward.pitch_penalty": "DARWIN_OP_FREE_PITCH_PENALTY_WEIGHT",
    "reward.action_smoothness": "DARWIN_OP_FREE_POLICY_ACTION_RATE_WEIGHT",
    "reward.action_l2": "DARWIN_OP_FREE_POLICY_ACTION_L2_WEIGHT",
    "reward.velocity_tracking": "DARWIN_OP_FREE_FORWARD_VELOCITY_REWARD_WEIGHT",
    "reward.lateral_velocity": "DARWIN_OP_FREE_LATERAL_VELOCITY_REWARD_WEIGHT",
    "reward.yaw_rate": "DARWIN_OP_FREE_YAW_RATE_REWARD_WEIGHT",
    "reward.termination": "DARWIN_OP_FREE_TERMINATION_PENALTY",
    # action / deploy model (absolute values)
    "action_scale": "DARWIN_OP_FREE_REAL_ACTION_SCALE",
    "action_scale_min": "DARWIN_OP_FREE_REAL_ACTION_SCALE_MIN",
    "action_scale_max": "DARWIN_OP_FREE_REAL_ACTION_SCALE_MAX",
    "action_lpf_alpha": "DARWIN_OP_FREE_ACTION_LPF_ALPHA",
    # curriculum / command targets (absolute values)
    "target_velocity": "DARWIN_OP_FREE_TARGET_FORWARD_VELOCITY",
    # training knobs (absolute values, no DARWIN_OP_ prefix)
    "max_iterations": "MAX_ITERATIONS",
    "num_envs": "NUM_ENVS",
    "seed": "SEED",
    "wall_clock_cap": "WALL_CLOCK_CAP",
    "resume_checkpoint": "RESUME_CHECKPOINT",
}

# Patch keys whose values are MULTIPLIERS of the parent stage's base weight.
# A treatment value of 1.30 means "base_weight * 1.30". The stage_env writer
# reads the parent value via a dry parse and emits the multiplied absolute
# value so the lab env loader keeps its simple ``${VAR:-default}`` semantics.
MULTIPLIER_KEYS: frozenset[str] = frozenset(
    {
        "reward.orientation_penalty",
        "reward.pitch_penalty",
        "reward.action_smoothness",
        "reward.action_l2",
        "reward.velocity_tracking",
        "reward.lateral_velocity",
        "reward.yaw_rate",
        "reward.termination",
    }
)

# Patch keys whose values are absolute (used verbatim).
ABSOLUTE_KEYS: frozenset[str] = frozenset(
    key for key in GAITLAB_PATCH_TO_ENV if key not in MULTIPLIER_KEYS
)

# Keys that look like reward multipliers but must never be treated as raw
# env-var names (i.e. they are part of the Physical AI Safety Agent vocabulary, not the lab
# vocabulary). Listed here so the passthrough path can warn the user.
RESERVED_GAITLAB_KEYS: frozenset[str] = frozenset(GAITLAB_PATCH_TO_ENV.keys())


def resolve_env_var(patch_key: str) -> str | None:
    """Return the lab env var for a patch key, or None if unknown.

    Unknown keys that already look like uppercase env vars (e.g.
    ``DARWIN_OP_FREE_*`` or ``MAX_ITERATIONS``) are returned verbatim so
    advanced users can override any lab knob directly.
    """

    if patch_key in GAITLAB_PATCH_TO_ENV:
        return GAITLAB_PATCH_TO_ENV[patch_key]
    # Allow raw env-var passthrough: must be uppercase, no dots, no spaces.
    if (
        patch_key
        and patch_key.isupper()
        and "." not in patch_key
        and " " not in patch_key
        and patch_key.replace("_", "").isalnum()
    ):
        return patch_key
    return None


def is_multiplier(patch_key: str) -> bool:
    """Return True when the patch value should multiply the parent base weight."""

    return patch_key in MULTIPLIER_KEYS


def split_known_and_passthrough(
    patch: Mapping[str, float | str | bool],
) -> tuple[dict[str, str], dict[str, str]]:
    """Split a patch dict into (known, passthrough) env-var assignments.

    - ``known``: patch keys in :data:`GAITLAB_PATCH_TO_ENV`, resolved to env vars.
      Values kept as the original Python objects; multiplier handling happens
      in :mod:`gaitlab.lab.stage_env` once the parent base is known.
    - ``passthrough``: raw uppercase env var names with their literal values.
    """

    known: dict[str, str] = {}
    passthrough: dict[str, str] = {}
    for key, value in patch.items():
        if key in GAITLAB_PATCH_TO_ENV:
            known[GAITLAB_PATCH_TO_ENV[key]] = _stringify(value)
            continue
        env_var = resolve_env_var(key)
        if env_var is not None:
            passthrough[env_var] = _stringify(value)
        else:
            raise KeyError(
                f"Unknown Physical AI Safety Agent patch key {key!r}. Use a known dotted key or "
                f"an uppercase env var name (e.g. DARWIN_OP_FREE_*)."
            )
    return known, passthrough


def known_keys() -> Iterable[str]:
    """Return an iterable over the documented Physical AI Safety Agent patch keys."""

    return GAITLAB_PATCH_TO_ENV.keys()


def _stringify(value: float | str | bool) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        # Preserve enough precision for reward weights while keeping the
        # stage-env readable.
        return f"{value:.6f}".rstrip("0").rstrip(".") or "0"
    return str(value)
