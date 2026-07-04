from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Eval cases must be deterministic and must not consume API quota even when
# a local .env enables the optional Google design agent.
os.environ["GAITLAB_USE_GOOGLE_API"] = "false"

from gaitlab.agents.experiment_design_agent import ExperimentDesignAgent
from gaitlab.orchestrator import GaitLabOrchestrator
from gaitlab.tools.safety_tools import run_robot_safety_gate


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_agent_cases() -> list[str]:
    logs: list[str] = []
    design_agent = ExperimentDesignAgent()
    for case in load_json(ROOT / "evals" / "agent_eval_cases.json"):
        pair = design_agent.create_pair(case["input"])
        patch_keys = set(pair.treatment["patch"])
        for expected in case["expected_treatment_patch"]:
            assert expected in patch_keys, f"{case['id']}: missing patch {expected}"
        result = GaitLabOrchestrator().handle_request(case["input"])
        assert re.match(r"^pair_\d{5,}$", result.pair.pair_id), result.pair.pair_id
        assert re.match(r"^control_\d{5,}$", result.pair.control["run_id"]), result.pair.control["run_id"]
        assert re.match(r"^treatment_\d{5,}$", result.pair.treatment["run_id"]), result.pair.treatment["run_id"]
        assert result.comparison["recommendation"] == case["expected_recommendation"]
        assert "real_robot_commands=blocked" in result.audit_log
        assert result.deployment_package["package_type"] == "safety_manifest_only"
        assert result.deployment_package["human_approval_required"] is True
        logs.append(f"PASS agent case: {case['id']}")
    return logs


def test_safety_cases() -> list[str]:
    logs: list[str] = []
    for case in load_json(ROOT / "evals" / "safety_gate_cases.json"):
        result = run_robot_safety_gate("policy_under_test", case["metrics"])
        assert result["safety_level"] == case["expected_safety_level"], case["id"]
        assert result["free_walking_allowed"] is case["expected_free_walking_allowed"], case["id"]
        logs.append(f"PASS safety case: {case['id']}")
    return logs


def main() -> None:
    logs = []
    logs.extend(test_agent_cases())
    logs.extend(test_safety_cases())
    output = ROOT / "evals" / "results.md"
    output.write_text("# Physical AI Safety Agent Eval Results\n\n" + "\n".join(f"- {line}" for line in logs) + "\n", encoding="utf-8")
    print("\n".join(logs))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
