"""Write ``scripts/stages/gaitlab_<run_id>.env`` files in the lab repo.

A Physical AI Safety Agent treatment patch is converted into a lab stage env that:

1. Sources a parent (control) stage env verbatim, so the control and
   treatment runs share every variable except the patched ones.
2. Overlays the mapped ``DARWIN_OP_FREE_*`` exports from the patch.
   Multiplier keys (e.g. ``reward.orientation_penalty``) are resolved
   against the parent's base value; absolute keys (e.g. ``max_iterations``,
   ``target_velocity``) are written verbatim.
3. Sets ``STAGE_TAG`` and ``STAGE_DESC`` so ``train.sh`` accepts the file.

The control run uses the parent stage env directly (no overlay file).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from gaitlab.lab.config import LiveLabConfig
from gaitlab.lab.patch_map import (
    GAITLAB_PATCH_TO_ENV,
    MULTIPLIER_KEYS,
    resolve_env_var,
    split_known_and_passthrough,
)


_GAITLAB_STAGE_PREFIX = "gaitlab_"


@dataclass(frozen=True)
class StageEnvPlan:
    """Describes how a run maps onto the lab stage-env system."""

    run_id: str
    node: str
    parent_stage: str
    stage_name: str
    stage_path: Path
    is_control: bool
    overlay_env: dict[str, str]
    run_overrides: dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.run_overrides is None:
            object.__setattr__(self, "run_overrides", {})

    def describe(self) -> str:
        role = "control" if self.is_control else "treatment"
        return (
            f"{role} run {self.run_id} on {self.node} via lab stage "
            f"{self.stage_name} (parent={self.parent_stage})"
        )


_EXPORT_RE = re.compile(
    r"""^\s*export\s+(?P<key>[A-Z_][A-Z0-9_]*)\s*=\s*(?P<value>.+?)\s*(?:#.*)?$""",
    re.MULTILINE,
)


def default_parent_stage(control_pair_id: str = "pair_10000") -> str:
    """Return the default parent stage used as the control baseline.

    The plan keeps control/treatment semantics explicit: the control run
    re-trains the latest known-good lineage. Operators can override this
    per-call by passing ``parent_stage`` to :func:`plan_run`.
    """

    # ``stage6810_bridge_p2_yaw_authority_t2a_scale045`` is the most recent
    # stable lineage head observed in the lab repo; it is a safe default.
    # The operator can always override it.
    return "stage6810_bridge_p2_yaw_authority_t2a_scale045"


def parse_parent_env(parent_path: Path) -> dict[str, str]:
    """Return the final export values defined directly in a parent stage env.

    Only ``export KEY=VALUE`` lines at this file's own level are returned.
    Values use the shell ``${VAR:-default}`` form, so when the inner default
    is a literal number we return that literal; otherwise we return the
    whole ``${VAR:-default}`` expression for transparency.
    """

    if not parent_path.exists():
        return {}
    text = parent_path.read_text(encoding="utf-8", errors="replace")
    out: dict[str, str] = {}
    for match in _EXPORT_RE.finditer(text):
        key = match.group("key")
        raw = match.group("value").strip().strip('"').strip("'")
        out[key] = _extract_default(raw)
    return out


def _extract_default(raw: str) -> str:
    """If raw is ``${VAR:-default}`` and default is a literal, return default."""

    match = re.fullmatch(r"\$\{[A-Z_][A-Z0-9_]*:-([^}]*)\}", raw)
    if match:
        return match.group(1).strip()
    return raw


def stage_name_for(run_id: str) -> str:
    """Return the lab stage name for a Physical AI Safety Agent run id."""

    safe = re.sub(r"[^A-Za-z0-9_]+", "_", run_id).strip("_").lower()
    return f"{_GAITLAB_STAGE_PREFIX}{safe}"


def plan_run(
    config: LiveLabConfig,
    run_id: str,
    node: str,
    patch: Mapping[str, Any],
    parent_stage: str | None = None,
    run_overrides: Mapping[str, Any] | None = None,
) -> StageEnvPlan:
    """Plan a lab stage env for one Physical AI Safety Agent run.

    ``patch`` must be ``{}`` for a control run. Non-empty patch means the
    run is a treatment; its keys are mapped via :mod:`gaitlab.lab.patch_map`
    and resolved against the parent stage's base values.

    ``run_overrides`` is an optional dict of run-level knobs (e.g.
    ``MAX_ITERATIONS``, ``NUM_ENVS``, ``WALL_CLOCK_CAP``, ``SEED``) that
    win over both the parent stage and the patch. These are written as
    export lines AFTER the parent stage is sourced, so train.sh's
    ``${VAR:-default}`` patterns pick them up correctly.
    """

    config.require_enabled(action="planning lab stage env")
    parent = parent_stage or default_parent_stage()
    parent_path = config.lab_repo_path / "scripts" / "stages" / f"{parent}.env"
    if not parent_path.exists():
        raise FileNotFoundError(
            f"parent stage env not found: {parent_path}. "
            f"Set parent_stage= to a name that exists under scripts/stages/."
        )

    stage_name = stage_name_for(run_id)
    stage_path = config.lab_repo_path / "scripts" / "stages" / f"{stage_name}.env"
    is_control = not patch
    overrides = {k: str(v) for k, v in (run_overrides or {}).items()}

    if is_control:
        return StageEnvPlan(
            run_id=run_id,
            node=node,
            parent_stage=parent,
            stage_name=stage_name,
            stage_path=stage_path,
            is_control=True,
            overlay_env={},
            run_overrides=overrides,
        )

    parent_values = parse_parent_env(parent_path)
    known, passthrough = split_known_and_passthrough(patch)
    overlay = _resolve_overlay(known, parent_values, patch)
    overlay.update(passthrough)

    return StageEnvPlan(
        run_id=run_id,
        node=node,
        parent_stage=parent,
        stage_name=stage_name,
        stage_path=stage_path,
        is_control=False,
        overlay_env=overlay,
        run_overrides=overrides,
    )


def _resolve_overlay(
    known_env_to_value_str: Mapping[str, str],
    parent_values: Mapping[str, str],
    original_patch: Mapping[str, Any],
) -> dict[str, str]:
    """Resolve multiplier vs absolute values into final env-var assignments."""

    overlay: dict[str, str] = {}
    env_to_patch_key = {v: k for k, v in GAITLAB_PATCH_TO_ENV.items()}
    for env_var, literal_value in known_env_to_value_str.items():
        patch_key = env_to_patch_key.get(env_var, "")
        if patch_key in MULTIPLIER_KEYS:
            base = _to_float(parent_values.get(env_var, "0"))
            multiplier = _to_float(literal_value)
            overlay[env_var] = _format_weight(base * multiplier)
        else:
            overlay[env_var] = literal_value
    return overlay


def write_stage_env(plan: StageEnvPlan) -> Path:
    """Materialise the planned stage env file on disk.

    Both control and treatment runs get a ``gaitlab_<run_id>.env`` file so
    that run-level overrides (``MAX_ITERATIONS``, ``WALL_CLOCK_CAP``, etc.)
    can be applied AFTER the parent stage is sourced. Without this, the
    parent's ``export MAX_ITERATIONS=...`` would overwrite our override
    via train.sh's ``${VAR:-default}`` pattern.
    """

    plan.stage_path.parent.mkdir(parents=True, exist_ok=True)
    role = "control" if plan.is_control else "treatment"
    header = [
        "#! /usr/bin/env bash",
        f"# Auto-generated by Physical AI Safety Agent for {role} run {plan.run_id} on {plan.node}.",
        f"# Sources the parent stage {plan.parent_stage!r}, then overlays the",
        "# Physical AI Safety Agent treatment patch mapped to DARWIN_OP_FREE_* env vars AND the",
        "# run-level overrides (iterations, wall-clock cap, etc.) so train.sh's",
        "# ${VAR:-default} patterns pick up the Physical AI Safety Agent values, not the parent's.",
        "# Manual edits will be overwritten on the next Physical AI Safety Agent run.",
        "",
        f'_STAGE_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"',
        f'# shellcheck source=./{plan.parent_stage}.env',
        f'source "$_STAGE_DIR/{plan.parent_stage}.env"',
        "",
        f'STAGE_TAG="{plan.stage_name}"',
        f'STAGE_DESC="Physical AI Safety Agent {role} run {plan.run_id} on {plan.node} (parent={plan.parent_stage})"',
        "",
    ]

    sections: list[str] = []
    if plan.overlay_env:
        sections.append("# ---- Physical AI Safety Agent treatment patch overlay ----")
        sections.extend(
            f'export {key}="{value}"' for key, value in plan.overlay_env.items()
        )
        sections.append("")
    if plan.run_overrides:
        sections.append("# ---- Physical AI Safety Agent run-level overrides (win over parent) ----")
        sections.extend(
            f'export {key}="{value}"' for key, value in plan.run_overrides.items()
        )
        sections.append("")

    text = "\n".join(header + sections) + "\n"
    # Force LF line endings: this file is uploaded to a Linux training
    # server and sourced by bash, which would otherwise choke on '\r'.
    plan.stage_path.write_text(text, encoding="utf-8", newline="\n")
    return plan.stage_path


def _to_float(value: str | float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_weight(value: float) -> str:
    # Match the formatting style used by the real stage envs: trailing
    # zeros trimmed, up to 6 decimal places.
    formatted = f"{value:.6f}".rstrip("0").rstrip(".")
    return formatted or "0"


def describe_for_audit(plan: StageEnvPlan) -> dict[str, Any]:
    """Return a secret-free audit summary of a stage env plan."""

    return {
        "run_id": plan.run_id,
        "node": plan.node,
        "parent_stage": plan.parent_stage,
        "stage_name": plan.stage_name,
        "is_control": plan.is_control,
        "stage_path": str(plan.stage_path),
        "overlay_env_keys": sorted(plan.overlay_env.keys()),
        "run_override_keys": sorted((plan.run_overrides or {}).keys()),
    }
