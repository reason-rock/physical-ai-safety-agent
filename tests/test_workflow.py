from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from gaitlab.orchestrator import GaitLabOrchestrator
from gaitlab.tools.safety_tools import run_robot_safety_gate


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def test_forward_fall_workflow_blocks_free_walking(self) -> None:
        result = GaitLabOrchestrator().handle_request(
            "The previous policy fell forward. Increase orientation penalty on GPU0 and compare with GPU1."
        )
        self.assertRegex(result.pair.pair_id, r"^pair_\d{5,}$")
        self.assertRegex(result.pair.control["run_id"], r"^control_\d{5,}$")
        self.assertRegex(result.pair.treatment["run_id"], r"^treatment_\d{5,}$")
        pair_num = int(re.search(r"\d+", result.pair.pair_id).group(0))
        control_num = int(re.search(r"\d+", result.pair.control["run_id"]).group(0))
        treatment_num = int(re.search(r"\d+", result.pair.treatment["run_id"]).group(0))
        self.assertEqual((control_num, treatment_num), (pair_num + 1, pair_num + 2))
        self.assertEqual(result.comparison["decision"], "safer_but_slower")
        self.assertEqual(result.safety["safety_level"], "supported_test_only")
        self.assertFalse(result.safety["free_walking_allowed"])
        self.assertEqual(result.deployment_package["package_type"], "safety_manifest_only")

    def test_real_replay_uses_sanitized_evidence(self) -> None:
        result = GaitLabOrchestrator(data_mode="real_replay").handle_request(
            "Replay the latest sanitized real robot comparison and decide whether hardware testing is safe."
        )
        treatment_id = result.pair.treatment["run_id"]
        treatment_eval = result.evaluations[treatment_id]
        self.assertEqual(treatment_eval["evidence_mode"], "sanitized_real_replay")
        self.assertFalse(treatment_eval["raw_log_included"])
        self.assertEqual(result.safety["safety_level"], "supported_test_only")
        self.assertFalse(result.safety["free_walking_allowed"])

    def test_free_walking_requires_full_evidence(self) -> None:
        metrics = {
            "num_rollouts": 10,
            "fall_free_count": 10,
            "avg_velocity": 0.052,
            "target_velocity": 0.055,
            "torso_pitch_rms": 0.16,
            "joint_limit_max_ratio": 0.80,
            "action_jerk": 0.20,
            "emergency_stop_dry_run": True,
        }
        result = run_robot_safety_gate("candidate", metrics)
        self.assertEqual(result["safety_level"], "candidate_for_free_walking")
        self.assertTrue(result["free_walking_allowed"])

    def test_mcp_tool_listing(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "gaitlab.mcp.server"],
            input=json.dumps({"tool": "list_tools", "arguments": {}}) + "\n",
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("create_experiment_pair", proc.stdout)
        self.assertIn("create_deployment_package", proc.stdout)


if __name__ == "__main__":
    unittest.main()
