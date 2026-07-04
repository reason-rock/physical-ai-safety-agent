from __future__ import annotations

import json
import sys

from gaitlab.mcp.schemas import TOOL_SCHEMAS
from gaitlab.tools.deployment_tools import create_deployment_package
from gaitlab.tools.evaluation_tools import evaluate_policy_on_pc
from gaitlab.tools.experiment_store import create_experiment_pair
from gaitlab.tools.node_registry import list_nodes
from gaitlab.tools.safety_tools import run_robot_safety_gate
from gaitlab.tools.training_tools import submit_training_job


TOOLS = {
    "list_nodes": lambda args: list_nodes(),
    "create_experiment_pair": create_experiment_pair,
    "submit_training_job": submit_training_job,
    "evaluate_policy_on_pc": evaluate_policy_on_pc,
    "run_robot_safety_gate": run_robot_safety_gate,
    "create_deployment_package": create_deployment_package,
}


def dispatch(message: dict) -> dict:
    """Dispatch a minimal JSON tool call.

    This is intentionally tiny: it documents the MCP-compatible boundary used
    by the public demo without requiring a real MCP runtime.
    """

    tool = message.get("tool")
    args = message.get("arguments", {})
    if tool == "list_tools":
        return {"tools": TOOL_SCHEMAS}
    if tool not in TOOLS:
        return {"error": f"unknown tool: {tool}"}
    return {"result": TOOLS[tool](**args)}


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = dispatch(message)
        except Exception as exc:  # pragma: no cover - defensive server loop
            response = {"error": str(exc)}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
