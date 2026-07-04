"""Offline tests for the live lab adapter.

These tests exercise the parts of ``gaitlab/lab`` that can be validated
without SSH, without a GPU, and without a real robot:

- ``patch_map``: dotted-key -> env-var mapping and multiplier handling.
- ``stage_env``: writing a treatment stage env from a patch dict, with a
  synthetic parent stage env on a temp lab repo.
- ``metrics``: verify-CSV and robot-CSV -> GaitLab metrics schema.
- ``tb_to_scalars``: deriving GaitLab scalar rows from synthetic TensorBoard
  events.
- ``deployment``: the pure :func:`deployment_allowed` gate, including
  every blocked case.
- ``orchestrator``: live_lab mode without SSH enabled falls back to mock
  with an explicit audit message.
"""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock
from unittest import mock

from gaitlab.lab.config import LiveLabConfig, LiveLabNotEnabledError
from gaitlab.lab.deployment import DeploymentDecision, deployment_allowed
from gaitlab.lab.metrics import (
    DEFAULT_TARGET_VELOCITY,
    merge_metrics,
    robot_csv_to_metrics,
    verify_csv_to_metrics,
)
from gaitlab.lab.patch_map import (
    GAITLAB_PATCH_TO_ENV,
    MULTIPLIER_KEYS,
    resolve_env_var,
    split_known_and_passthrough,
)
from gaitlab.lab.stage_env import (
    parse_parent_env,
    plan_run,
    stage_name_for,
    write_stage_env,
)
from gaitlab.orchestrator import GaitLabOrchestrator


class PatchMapTests(unittest.TestCase):
    def test_known_keys_resolve_to_darwin_env_vars(self) -> None:
        self.assertEqual(
            resolve_env_var("reward.orientation_penalty"),
            "DARWIN_OP_FREE_FORWARD_PITCH_PENALTY_WEIGHT",
        )
        self.assertEqual(
            resolve_env_var("reward.velocity_tracking"),
            "DARWIN_OP_FREE_FORWARD_VELOCITY_REWARD_WEIGHT",
        )

    def test_raw_envvar_passthrough(self) -> None:
        self.assertEqual(
            resolve_env_var("DARWIN_OP_FREE_CUSTOM_KNOB"),
            "DARWIN_OP_FREE_CUSTOM_KNOB",
        )
        self.assertIsNone(resolve_env_var("not.a.real.key"))

    def test_multiplier_keys_set_is_a_subset_of_known_keys(self) -> None:
        self.assertTrue(MULTIPLIER_KEYS.issubset(set(GAITLAB_PATCH_TO_ENV)))
        # action_scale, target_velocity, max_iterations are absolute, not multipliers.
        self.assertNotIn("action_scale", MULTIPLIER_KEYS)
        self.assertNotIn("target_velocity", MULTIPLIER_KEYS)
        self.assertNotIn("max_iterations", MULTIPLIER_KEYS)

    def test_split_separates_known_from_passthrough(self) -> None:
        patch = {
            "reward.orientation_penalty": 1.3,
            "DARWIN_OP_FREE_CUSTOM_KNOB": 5.0,
            "max_iterations": 100,
        }
        known, passthrough = split_known_and_passthrough(patch)
        self.assertIn("DARWIN_OP_FREE_FORWARD_PITCH_PENALTY_WEIGHT", known)
        self.assertIn("MAX_ITERATIONS", known)
        self.assertEqual(passthrough, {"DARWIN_OP_FREE_CUSTOM_KNOB": "5"})

    def test_unknown_dotted_key_raises(self) -> None:
        with self.assertRaises(KeyError):
            split_known_and_passthrough({"reward.does_not_exist": 1.0})


class StageEnvTests(unittest.TestCase):
    def _write_parent_stage(self, lab_repo: Path) -> str:
        stages_dir = lab_repo / "scripts" / "stages"
        stages_dir.mkdir(parents=True, exist_ok=True)
        pipeline_dir = lab_repo / "scripts" / "pipeline"
        pipeline_dir.mkdir(parents=True, exist_ok=True)
        parent_name = "stage_test_parent"
        parent_path = stages_dir / f"{parent_name}.env"
        parent_path.write_text(
            "\n".join(
                [
                    "#! /usr/bin/env bash",
                    'STAGE_TAG="stage_test_parent"',
                    'STAGE_DESC="test parent"',
                    'export DARWIN_OP_FREE_FORWARD_PITCH_PENALTY_WEIGHT="${DARWIN_OP_FREE_FORWARD_PITCH_PENALTY_WEIGHT:-2.0}"',
                    'export DARWIN_OP_FREE_REAL_ACTION_SCALE="${DARWIN_OP_FREE_REAL_ACTION_SCALE:-0.45}"',
                    'export MAX_ITERATIONS="${MAX_ITERATIONS:-60000}"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return parent_name

    def _fake_config(self, lab_repo: Path) -> LiveLabConfig:
        return LiveLabConfig(
            mode="private_lab",
            enable_ssh=True,
            allow_real_robot=False,
            lab_repo_path=lab_repo,
            gpu0_host="GPU0",
            gpu1_host="GPU1",
            research_pc_host="localhost",
            robot_host="offline_mock",
            train_host_primary="managed-node-a",
            train_host_fallbacks=["managed-node-b"],
            robot_fallbacks=[],
            ssh_user="operator",
            ssh_key_configured=True,
            operator_approval_required=True,
            estop_dry_run_required=True,
            workspace_path=Path(tempfile.gettempdir()) / "gaitlab_test_workspace",
            pipeline_dir=lab_repo / "scripts" / "pipeline",
            remote_repo_path="/home/operator/physical-ai-lab",
        )

    def test_parse_parent_env_extracts_default_literals(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            lab_repo = Path(raw_dir)
            parent = self._write_parent_stage(lab_repo)
            parent_path = lab_repo / "scripts" / "stages" / f"{parent}.env"
            values = parse_parent_env(parent_path)
            self.assertEqual(values["DARWIN_OP_FREE_FORWARD_PITCH_PENALTY_WEIGHT"], "2.0")
            self.assertEqual(values["DARWIN_OP_FREE_REAL_ACTION_SCALE"], "0.45")
            self.assertEqual(values["MAX_ITERATIONS"], "60000")

    def test_live_training_host_mapping_matches_cell_pcs(self) -> None:
        from gaitlab.lab.training import LiveTrainingNodeAgent
        from web.backend.job_store import JobStore

        with tempfile.TemporaryDirectory() as raw_dir:
            (Path(raw_dir) / "scripts" / "pipeline").mkdir(parents=True)
            config = replace(
                self._fake_config(Path(raw_dir)),
                train_host_primary="managed-node-b",
                train_host_fallbacks=["managed-node-a"],
            )
            self.assertEqual(
                LiveTrainingNodeAgent("GPU0", config, data_mode="live_lab").host,
                "managed-node-a",
            )
            self.assertEqual(
                LiveTrainingNodeAgent("GPU1", config, data_mode="live_lab").host,
                "managed-node-b",
            )
            self.assertEqual(JobStore._resolve_host(config, "GPU0"), "managed-node-a")
            self.assertEqual(JobStore._resolve_host(config, "GPU1"), "managed-node-b")

    def test_plan_treatment_writes_overlay_with_multiplied_weight(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            lab_repo = Path(raw_dir)
            parent = self._write_parent_stage(lab_repo)
            config = self._fake_config(lab_repo)
            patch = {
                "reward.orientation_penalty": 1.30,  # multiplier
                "action_scale": 0.35,  # absolute
                "max_iterations": 5000,  # absolute
            }
            plan = plan_run(
                config=config,
                run_id="treatment_999",
                node="GPU0",
                patch=patch,
                parent_stage=parent,
            )
            self.assertFalse(plan.is_control)
            self.assertEqual(plan.parent_stage, parent)
            self.assertEqual(plan.stage_name, "gaitlab_treatment_999")
            # Multiplier: base 2.0 * 1.30 = 2.6
            self.assertEqual(
                plan.overlay_env["DARWIN_OP_FREE_FORWARD_PITCH_PENALTY_WEIGHT"], "2.6"
            )
            # Absolute: written verbatim
            self.assertEqual(plan.overlay_env["DARWIN_OP_FREE_REAL_ACTION_SCALE"], "0.35")
            self.assertEqual(plan.overlay_env["MAX_ITERATIONS"], "5000")

            written = write_stage_env(plan)
            self.assertTrue(written.exists())
            text = written.read_text(encoding="utf-8")
            self.assertIn(f'source "$_STAGE_DIR/{parent}.env"', text)
            self.assertIn('STAGE_TAG="gaitlab_treatment_999"', text)
            self.assertIn(
                'export DARWIN_OP_FREE_FORWARD_PITCH_PENALTY_WEIGHT="2.6"', text
            )

    def test_plan_control_writes_gaitlab_env_with_run_overrides(self) -> None:
        """Control runs always get a gaitlab_<run_id>.env so run-level
        overrides (MAX_ITERATIONS, WALL_CLOCK_CAP, etc.) win over the
        parent stage's defaults inside train.sh."""

        with tempfile.TemporaryDirectory() as raw_dir:
            lab_repo = Path(raw_dir)
            parent = self._write_parent_stage(lab_repo)
            config = self._fake_config(lab_repo)
            plan = plan_run(
                config=config,
                run_id="control_999",
                node="GPU1",
                patch={},
                parent_stage=parent,
                run_overrides={"MAX_ITERATIONS": "20", "WALL_CLOCK_CAP": "5m"},
            )
            self.assertTrue(plan.is_control)
            self.assertEqual(plan.stage_name, "gaitlab_control_999")
            self.assertEqual(plan.overlay_env, {})
            self.assertEqual(
                plan.run_overrides, {"MAX_ITERATIONS": "20", "WALL_CLOCK_CAP": "5m"}
            )
            written = write_stage_env(plan)
            self.assertEqual(written.name, "gaitlab_control_999.env")
            text = written.read_text(encoding="utf-8")
            # Must source the parent, then re-export our overrides so they win.
            self.assertIn(f'source "$_STAGE_DIR/{parent}.env"', text)
            self.assertIn('export MAX_ITERATIONS="20"', text)
            self.assertIn('export WALL_CLOCK_CAP="5m"', text)

    def test_plan_control_without_overrides_still_writes_gaitlab_env(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            lab_repo = Path(raw_dir)
            parent = self._write_parent_stage(lab_repo)
            config = self._fake_config(lab_repo)
            plan = plan_run(
                config=config,
                run_id="control_999",
                node="GPU1",
                patch={},
                parent_stage=parent,
            )
            written = write_stage_env(plan)
            self.assertEqual(written.name, "gaitlab_control_999.env")
            self.assertIn(f"{parent}.env", written.read_text(encoding="utf-8"))

    def test_stage_name_sanitises_run_id(self) -> None:
        self.assertEqual(stage_name_for("treatment_10001"), "gaitlab_treatment_10001")
        self.assertEqual(stage_name_for("treatment-10001 v2"), "gaitlab_treatment_10001_v2")

    def test_written_stage_env_uses_lf_line_endings(self) -> None:
        """Regression: Windows CRLF in stage envs breaks bash on the GPU server."""

        with tempfile.TemporaryDirectory() as raw_dir:
            lab_repo = Path(raw_dir)
            parent = self._write_parent_stage(lab_repo)
            config = self._fake_config(lab_repo)
            plan = plan_run(
                config=config,
                run_id="treatment_lf",
                node="GPU0",
                patch={"reward.orientation_penalty": 1.5},
                parent_stage=parent,
                run_overrides={"MAX_ITERATIONS": "10"},
            )
            written = write_stage_env(plan)
            raw_bytes = written.read_bytes()
            self.assertNotIn(b"\r\n", raw_bytes)
            self.assertNotIn(b"\r", raw_bytes)

    def test_written_stage_env_contains_run_overrides_after_source(self) -> None:
        """Regression: run overrides must appear AFTER source so they win."""

        with tempfile.TemporaryDirectory() as raw_dir:
            lab_repo = Path(raw_dir)
            parent = self._write_parent_stage(lab_repo)
            config = self._fake_config(lab_repo)
            plan = plan_run(
                config=config,
                run_id="control_overrides",
                node="GPU1",
                patch={},
                parent_stage=parent,
                run_overrides={"MAX_ITERATIONS": "20", "WALL_CLOCK_CAP": "5m"},
            )
            written = write_stage_env(plan)
            text = written.read_text(encoding="utf-8")
            source_line = text.index(f"source")
            export_iter = text.index('export MAX_ITERATIONS="20"')
            export_cap = text.index('export WALL_CLOCK_CAP="5m"')
            self.assertGreater(export_iter, source_line)
            self.assertGreater(export_cap, source_line)


class MetricsTests(unittest.TestCase):
    def _write_verify_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "preset",
                    "cmd_vx",
                    "achieved_vx",
                    "falls",
                    "env_steps",
                    "n_envs",
                    "action_meanabs",
                    "action_absmax",
                    "height_mean",
                ],
            )
            writer.writeheader()
            for preset, achieved, falls in [
                ("forward", 0.052, 1),
                ("forward_slow", 0.040, 0),
                ("lateral_left", 0.001, 0),
            ]:
                writer.writerow(
                    {
                        "preset": preset,
                        "cmd_vx": 0.055,
                        "achieved_vx": achieved,
                        "falls": falls,
                        "env_steps": 1000,
                        "n_envs": 4,
                        "action_meanabs": 0.18,
                        "action_absmax": 0.62,
                        "height_mean": 0.305,
                    }
                )

    def test_verify_csv_to_metrics_shape(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            csv_path = Path(raw_dir) / "verify.csv"
            self._write_verify_csv(csv_path)
            metrics = verify_csv_to_metrics(csv_path)
            # Two forward presets x 4 envs = 8 rollouts.
            self.assertEqual(metrics["num_rollouts"], 8)
            # 1 fall out of 8 -> 7 fall-free.
            self.assertEqual(metrics["fall_free_count"], 7)
            self.assertAlmostEqual(
                metrics["avg_velocity"], (0.052 + 0.040) / 2, places=4
            )
            self.assertGreater(metrics["energy_proxy"], 0.0)
            self.assertGreater(metrics["joint_limit_max_ratio"], 0.0)
            self.assertEqual(metrics["evidence_mode"], "live_lab")

    def test_robot_csv_to_metrics_marks_fall(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            csv_path = Path(raw_dir) / "robot.csv"
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=["time_s", "pitch", "roll", "fallen", "L_HIP_YAW_policy", "L_HIP_YAW_err"]
                )
                writer.writeheader()
                writer.writerow(
                    {"time_s": "0.000", "pitch": "0.05", "roll": "0.01", "fallen": "0", "L_HIP_YAW_policy": "0.20", "L_HIP_YAW_err": "0.01"}
                )
                writer.writerow(
                    {"time_s": "0.008", "pitch": "0.07", "roll": "0.02", "fallen": "1", "L_HIP_YAW_policy": "0.30", "L_HIP_YAW_err": "0.02"}
                )
            metrics = robot_csv_to_metrics(csv_path, emergency_stop_dry_run=True)
            self.assertEqual(metrics["num_rollouts"], 1)
            self.assertEqual(metrics["fall_free_count"], 0)
            self.assertGreater(metrics["torso_pitch_rms"], 0.0)
            self.assertTrue(metrics["emergency_stop_dry_run"])

    def test_merge_metrics_prefers_robot_torso_pitch_when_sim_placeholder(self) -> None:
        sim = {
            "num_rollouts": 10,
            "fall_free_count": 10,
            "avg_velocity": 0.05,
            "target_velocity": DEFAULT_TARGET_VELOCITY,
            "torso_pitch_rms": 0.30,  # placeholder
            "energy_proxy": 0.9,
            "joint_limit_max_ratio": 0.4,
            "action_jerk": 0.1,
            "emergency_stop_dry_run": False,
        }
        robot = {
            "num_rollouts": 1,
            "fall_free_count": 1,
            "avg_velocity": 0.0,
            "target_velocity": DEFAULT_TARGET_VELOCITY,
            "torso_pitch_rms": 0.12,
            "energy_proxy": 0.5,
            "joint_limit_max_ratio": 0.3,
            "action_jerk": 0.0,
            "emergency_stop_dry_run": True,
            "duration_s": 12.0,
        }
        merged = merge_metrics(sim, robot)
        self.assertTrue(merged["robot_evidence"])
        self.assertTrue(merged["emergency_stop_dry_run"])  # robot upgraded it
        self.assertEqual(merged["torso_pitch_rms"], 0.12)  # robot overrode placeholder


class TbToScalarsTests(unittest.TestCase):
    def test_derive_scalars_handles_minimal_reward_only_tag(self) -> None:
        from gaitlab.lab.tb_to_scalars import derive_scalars

        scalars = {
            "Train/mean_reward": [
                (0, -100.0),
                (10, -50.0),
                (20, 5.0),
            ],
        }
        rows = derive_scalars(scalars)
        self.assertEqual(len(rows), 3)
        self.assertEqual([row["step"] for row in rows], [0, 10, 20])
        self.assertEqual(rows[0]["reward"], -100.0)
        self.assertEqual(rows[2]["reward"], 5.0)
        # Without episode-length tag, the proxy defaults to NOMINAL_EPISODE_STEPS,
        # which means fall_rate = 1 - 1.0 = 0.0.
        self.assertEqual(rows[0]["fall_rate"], 0.0)

    def test_derive_scalars_uses_episode_length_for_fall_rate(self) -> None:
        from gaitlab.lab.tb_to_scalars import derive_scalars

        scalars = {
            "Train/mean_reward": [(0, 0.0), (10, 1.0)],
            "Train/mean_episode_length": [(0, 250.0), (10, 800.0)],
        }
        rows = derive_scalars(scalars)
        # 250/1000 -> fall_rate 0.75 ; 800/1000 -> 0.2
        self.assertAlmostEqual(rows[0]["fall_rate"], 0.75, places=4)
        self.assertAlmostEqual(rows[1]["fall_rate"], 0.2, places=4)

    def test_derive_scalars_returns_empty_without_reward_tag(self) -> None:
        from gaitlab.lab.tb_to_scalars import derive_scalars

        self.assertEqual(derive_scalars({"Train/mean_episode_length": [(0, 100.0)]}), [])


class DeploymentGateTests(unittest.TestCase):
    def _config(self, **overrides) -> LiveLabConfig:
        defaults = dict(
            mode="private_lab",
            enable_ssh=True,
            allow_real_robot=True,
            lab_repo_path=Path("/nonexistent"),
            gpu0_host="GPU0",
            gpu1_host="GPU1",
            research_pc_host="localhost",
            robot_host="operator@robot",
            train_host_primary="managed-node-a",
            train_host_fallbacks=[],
            robot_fallbacks=[],
            ssh_user="operator",
            ssh_key_configured=True,
            operator_approval_required=True,
            estop_dry_run_required=True,
            workspace_path=Path("/tmp/ws"),
            pipeline_dir=Path("/nonexistent/scripts/pipeline"),
            remote_repo_path="/home/operator/physical-ai-lab",
        )
        defaults.update(overrides)
        return LiveLabConfig(**defaults)

    def _good_safety(self) -> dict:
        return {
            "safety_level": "candidate_for_free_walking",
            "free_walking_allowed": True,
        }

    def _good_metrics(self) -> dict:
        return {"emergency_stop_dry_run": True}

    def test_all_conditions_met_allows_deploy(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pt") as policy_file:
            decision = deployment_allowed(
                safety=self._good_safety(),
                metrics=self._good_metrics(),
                config=self._config(),
                operator_token="operator",
                policy_path=Path(policy_file.name),
            )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reasons, [])

    def test_blocks_when_safety_level_is_wrong(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pt") as policy_file:
            decision = deployment_allowed(
                safety={"safety_level": "supported_test_only", "free_walking_allowed": False},
                metrics=self._good_metrics(),
                config=self._config(),
                operator_token="operator",
                policy_path=Path(policy_file.name),
            )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("candidate_for_free_walking" in r for r in decision.reasons))

    def test_blocks_when_allow_real_robot_false(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pt") as policy_file:
            decision = deployment_allowed(
                safety=self._good_safety(),
                metrics=self._good_metrics(),
                config=self._config(allow_real_robot=False),
                operator_token="operator",
                policy_path=Path(policy_file.name),
            )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("GAITLAB_ALLOW_REAL_ROBOT" in r for r in decision.reasons))

    def test_blocks_when_operator_token_missing_and_required(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pt") as policy_file:
            decision = deployment_allowed(
                safety=self._good_safety(),
                metrics=self._good_metrics(),
                config=self._config(operator_approval_required=True),
                operator_token=None,
                policy_path=Path(policy_file.name),
            )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("operator_token" in r for r in decision.reasons))

    def test_operator_token_optional_when_not_required(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pt") as policy_file:
            decision = deployment_allowed(
                safety=self._good_safety(),
                metrics=self._good_metrics(),
                config=self._config(operator_approval_required=False),
                operator_token=None,
                policy_path=Path(policy_file.name),
            )
        self.assertTrue(decision.allowed)

    def test_blocks_when_estop_dry_run_missing(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pt") as policy_file:
            decision = deployment_allowed(
                safety=self._good_safety(),
                metrics={"emergency_stop_dry_run": False},
                config=self._config(),
                operator_token="operator",
                policy_path=Path(policy_file.name),
            )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("emergency_stop_dry_run" in r for r in decision.reasons))

    def test_blocks_when_policy_file_missing(self) -> None:
        decision = deployment_allowed(
            safety=self._good_safety(),
            metrics=self._good_metrics(),
            config=self._config(),
            operator_token="operator",
            policy_path=Path("/does/not/exist.pt"),
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("policy file not found" in r for r in decision.reasons))

    def test_decision_describe_strings(self) -> None:
        decision = DeploymentDecision(allowed=True, reasons=[], required_actions=[])
        self.assertEqual(decision.describe(), "live robot deployment allowed")
        decision = DeploymentDecision(
            allowed=False, reasons=["a", "b"], required_actions=[]
        )
        self.assertIn("blocked", decision.describe())
        self.assertIn("a", decision.describe())


class LiveLabDisabledTests(unittest.TestCase):
    def _patch_disabled(self):
        # Force LiveLabConfig.enabled to read as False regardless of the
        # real .env, so these tests are hermetic and do not depend on the
        # developer's local SSH/robot flags.
        import gaitlab.lab as lab_pkg
        from gaitlab.lab import config as lab_config

        class _DisabledConfig(LiveLabConfig):
            @property
            def enabled(self) -> bool:
                return False

        original_load = LiveLabConfig.load

        def _load(*args, **kwargs):  # type: ignore[no-redef]
            base = original_load()
            return _DisabledConfig(
                mode=base.mode,
                enable_ssh=False,
                allow_real_robot=False,
                lab_repo_path=base.lab_repo_path,
                gpu0_host=base.gpu0_host,
                gpu1_host=base.gpu1_host,
                research_pc_host=base.research_pc_host,
                robot_host=base.robot_host,
                train_host_primary=base.train_host_primary,
                train_host_fallbacks=base.train_host_fallbacks,
                robot_fallbacks=base.robot_fallbacks,
                ssh_user=base.ssh_user,
                ssh_key_configured=base.ssh_key_configured,
                operator_approval_required=base.operator_approval_required,
                estop_dry_run_required=base.estop_dry_run_required,
                workspace_path=base.workspace_path,
                pipeline_dir=base.pipeline_dir,
                remote_repo_path=base.remote_repo_path,
            )

        # Patch both the canonical location AND the re-export in
        # ``gaitlab.lab.__init__`` so all callers see the disabled config.
        patchers = [
            mock.patch.object(lab_config, "LiveLabConfig"),
            mock.patch.object(lab_pkg, "LiveLabConfig"),
        ]
        for p in patchers:
            mock_cls = p.start()
            mock_cls.load.side_effect = _load
            mock_cls.side_effect = LiveLabConfig
        return patchers

    def test_data_mode_live_lab_falls_back_to_mock_when_ssh_disabled(self) -> None:
        patchers = self._patch_disabled()
        try:
            result = GaitLabOrchestrator(data_mode="live_lab").handle_request(
                "forward fall orientation penalty"
            )
        finally:
            for p in patchers:
                p.stop()
        self.assertIn(
            "live_lab_adapter=requested_but_disabled_falling_back_to_mock",
            result.audit_log,
        )
        self.assertIn("real_robot_commands=blocked", result.audit_log)
        self.assertEqual(
            result.deployment_package["package_type"], "safety_manifest_only"
        )

    def test_build_training_agent_raises_when_ssh_disabled(self) -> None:
        from gaitlab.lab import build_training_agent

        patchers = self._patch_disabled()
        try:
            with self.assertRaises(LiveLabNotEnabledError):
                build_training_agent("GPU0", data_mode="live_lab")
        finally:
            for p in patchers:
                p.stop()


if __name__ == "__main__":
    unittest.main()
