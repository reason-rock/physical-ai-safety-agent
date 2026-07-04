"""Live evaluation agent for the researcher PC.

Mirrors the public-demo :class:`gaitlab.agents.evaluation_agent.EvaluationAgent`
API (``evaluate`` / ``compare``) but invokes the real lab stack:

1. ``pick_checkpoint.py`` — picks the best checkpoint from a TensorBoard run.
2. ``verify_policy.ps1`` → ``policy_cli.py verify`` — runs the directional
   tracking verifier in Isaac Sim and emits a per-preset CSV.
3. ``metrics.verify_csv_to_metrics`` — converts the verify CSV into the
   Physical AI Safety Agent metrics schema so :func:`compare_experiment_pair` keeps working.

The agent runs entirely on the researcher PC (this machine). It does not
SSH anywhere itself; the verify scripts assume they are already on the
right host and refuse otherwise (per ``_common.sh`` host-role checks).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from gaitlab.lab.config import LiveLabConfig
from gaitlab.lab.metrics import (
    DEFAULT_TARGET_VELOCITY,
    merge_metrics,
    verify_csv_to_metrics,
)
from gaitlab.lab.process import run_pipeline_script, summarize_for_audit


@dataclass(frozen=True)
class VerifyRunResult:
    """Outcome of one ``verify_policy`` invocation."""

    checkpoint: Path
    verify_csv: Path
    metrics: dict[str, Any]


class LiveEvaluationAgent:
    """Adapter that evaluates real checkpoints on the researcher PC."""

    def __init__(
        self,
        config: LiveLabConfig,
        data_mode: str = "live_lab",
        num_rollouts: int = 10,
        preset_set: str = "forward_only",
    ) -> None:
        if data_mode != "live_lab":
            raise ValueError(
                f"LiveEvaluationAgent requires data_mode='live_lab', got {data_mode!r}"
            )
        self.config = config
        self.data_mode = data_mode
        self.num_rollouts = num_rollouts
        self.preset_set = preset_set
        config.require_enabled(action="live policy evaluation")

    # ------------------------------------------------------------------
    # Public API (mirrors gaitlab.agents.evaluation_agent.EvaluationAgent)
    # ------------------------------------------------------------------

    def evaluate(
        self,
        run_id: str,
        checkpoint_path: str | None = None,
        run_dir: str | Path | None = None,
        target_velocity: float = DEFAULT_TARGET_VELOCITY,
        emergency_stop_dry_run: bool = False,
    ) -> dict[str, Any]:
        """Pick a checkpoint, run the verifier, and return Physical AI Safety Agent metrics.

        ``checkpoint_path`` may point at either a raw RSL-RL checkpoint
        (``model_<iter>.pt``) or an exported TorchScript policy. If it is
        omitted, the agent runs ``pick_checkpoint.py`` against ``run_dir``
        first.
        """

        self.config.require_enabled(action="live policy evaluation")
        checkpoint = self._resolve_checkpoint(checkpoint_path, run_id, run_dir)
        verify_csv = self._run_verify(checkpoint, run_id)
        metrics = verify_csv_to_metrics(
            verify_csv,
            target_velocity=target_velocity,
            emergency_stop_dry_run=emergency_stop_dry_run,
        )
        metrics["run_id"] = run_id
        metrics["checkpoint"] = checkpoint.name
        metrics["eval_config"] = "scripts/pipeline/verify_policy.ps1"
        # Persist so the rest of the orchestrator can find it the same way
        # the mock agent does (demo_data/metrics/<run_id>_eval.json).
        self._persist_metrics(run_id, metrics)
        return VerifyRunResult(
            checkpoint=checkpoint,
            verify_csv=verify_csv,
            metrics=metrics,
        ).metrics

    def compare(
        self,
        control_run_id: str,
        treatment_run_id: str,
        evaluations: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Reuse the public-demo comparator so verdicts stay consistent."""

        # Imported lazily to keep this module importable when the demo
        # package has not been initialised (e.g. unit tests of the lab
        # adapter alone).
        from gaitlab.tools.evaluation_tools import compare_experiment_pair

        return compare_experiment_pair(
            control_run_id=control_run_id,
            treatment_run_id=treatment_run_id,
            evaluations=dict(evaluations),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_checkpoint(
        self,
        checkpoint_path: str | None,
        run_id: str,
        run_dir: str | Path | None,
    ) -> Path:
        if checkpoint_path:
            path = Path(checkpoint_path)
            if not path.exists():
                # Allow relative-to-workspace paths used in the mock demo.
                alt = self.config.workspace_path / checkpoint_path
                if alt.exists():
                    path = alt
            if path.exists():
                return path
            raise FileNotFoundError(f"checkpoint not found: {checkpoint_path}")

        candidate_run_dir = self._resolve_run_dir(run_id, run_dir)
        picked_iter = self._pick_checkpoint(candidate_run_dir, run_id)
        return candidate_run_dir / f"model_{picked_iter}.pt"

    def _resolve_run_dir(self, run_id: str, run_dir: str | Path | None) -> Path:
        if run_dir:
            return Path(run_dir)
        # Default to the local mirror created by LiveTrainingNodeAgent.collect().
        local = (
            self.config.workspace_path
            / "demo_data"
            / "artifacts"
            / run_id
            / "server_run"
        )
        if local.exists():
            return local
        raise FileNotFoundError(
            f"could not locate a run directory for {run_id}. "
            f"Pass run_dir= explicitly, or call LiveTrainingNodeAgent.collect() first."
        )

    def _pick_checkpoint(self, run_dir: Path, run_id: str) -> int:
        """Run pick_checkpoint.py against a TensorBoard run dir."""

        picker = self.config.pipeline_dir / "pick_checkpoint.py"
        if not picker.exists():
            # Fall back to the highest-numbered model_*.pt.
            ckpts = sorted(run_dir.glob("model_*.pt"))
            if not ckpts:
                raise FileNotFoundError(
                    f"no model_*.pt under {run_dir}; cannot pick a checkpoint"
                )
            return _iter_from_name(ckpts[-1].name)

        result = run_pipeline_script(
            self.config,
            script=picker,
            args=[
                "--run-dir",
                str(run_dir),
                "--emit-only",
            ],
            run_id=run_id,
            cwd=self.config.lab_repo_path,
            check=False,
        )
        if not result.ok:
            # TensorBoard may be missing in stripped environments; fall back.
            ckpts = sorted(run_dir.glob("model_*.pt"))
            if not ckpts:
                raise RuntimeError(
                    f"pick_checkpoint.py failed and no model_*.pt fallback under {run_dir}. "
                    f"Log: {result.log_path}"
                )
            return _iter_from_name(ckpts[-1].name)
        iter_str = result.stdout.strip().splitlines()[-1].strip()
        try:
            return int(iter_str)
        except ValueError as exc:
            raise RuntimeError(
                f"pick_checkpoint.py returned non-integer iter {iter_str!r}"
            ) from exc

    def _run_verify(self, checkpoint: Path, run_id: str) -> Path:
        """Run verify_policy.ps1 and return the verify CSV path."""

        verify_script = self.config.pipeline_dir / "verify_policy.ps1"
        out_csv = (
            self.config.workspace_path
            / "demo_data"
            / "live_logs"
            / run_id
            / "verify.csv"
        )
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        args = [
            "-Checkpoint",
            str(checkpoint),
            "-Out",
            str(out_csv),
            "-PresetSet",
            self.preset_set,
            "-Tag",
            run_id,
        ]
        # The verify scripts are opinionated about running on the dev PC.
        # If the user is running on a non-dev host (e.g. CI), the script
        # will refuse with a clear error; we surface that error rather than
        # try to work around it.
        try:
            result = run_pipeline_script(
                self.config,
                script=verify_script,
                args=args,
                run_id=run_id,
                cwd=self.config.lab_repo_path,
                check=False,
                env_overrides={"PIPELINE_ALLOW_THIS_PC": "1"},
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"verify_policy.ps1 not found at {verify_script}. Ensure the lab "
                f"repo path is correct in .env (GAITLAB_LAB_REPO_PATH)."
            ) from exc

        if not result.ok or not out_csv.exists():
            raise RuntimeError(
                f"verify_policy.ps1 failed (exit {result.returncode}). "
                f"Log: {result.log_path}. This command must run on the researcher PC "
                f"with Isaac Sim installed."
            )
        return out_csv

    def _persist_metrics(self, run_id: str, metrics: dict[str, Any]) -> None:
        path = self.config.workspace_path / "demo_data" / "metrics" / f"{run_id}_eval.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")


def _iter_from_name(filename: str) -> int:
    match = re.search(r"model_(\d+)\.pt", filename)
    if not match:
        raise ValueError(f"could not parse iter from {filename}")
    return int(match.group(1))


def evaluate_with_optional_robot(
    agent: LiveEvaluationAgent,
    run_id: str,
    robot_csv: Path | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience helper: evaluate in sim, then optionally merge robot evidence."""

    from gaitlab.lab.metrics import robot_csv_to_metrics

    sim_metrics = agent.evaluate(run_id, **kwargs)
    if robot_csv is None:
        return sim_metrics
    robot_metrics = robot_csv_to_metrics(robot_csv)
    return merge_metrics(sim_metrics, robot_metrics)
