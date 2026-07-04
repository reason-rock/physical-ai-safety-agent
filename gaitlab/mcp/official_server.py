from __future__ import annotations

import json
from typing import Any

from gaitlab.tools.deployment_tools import create_deployment_package as create_package_impl
from gaitlab.tools.evaluation_tools import evaluate_policy_on_pc as evaluate_impl
from gaitlab.tools.experiment_store import create_experiment_pair as create_pair_impl
from gaitlab.tools.node_registry import list_nodes as list_nodes_impl
from gaitlab.tools.replay_data import load_replay_manifest
from gaitlab.tools.safety_tools import run_robot_safety_gate as safety_gate_impl
from gaitlab.tools.training_tools import submit_training_job as submit_training_impl

try:  # pragma: no cover - optional integration import
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:  # pragma: no cover - default public demo path
    FastMCP = None  # type: ignore[assignment]


def create_server():
    """Create an official MCP SDK server for Physical AI Safety Agent tools.

    The default capstone demo does not require the MCP SDK. Install the optional
    integration with `pip install -e .[integrations]` before running this file.
    """

    if FastMCP is None:
        raise RuntimeError(
            "The official MCP SDK is not installed. Run "
            "`.\\.venv\\Scripts\\python.exe -m pip install -e .[integrations]` "
            "or use the lightweight JSON dispatcher in gaitlab.mcp.server."
        )

    server = FastMCP("Physical AI Safety Agent", json_response=True)

    @server.tool()
    def list_nodes() -> dict[str, Any]:
        """List public-demo lab nodes and their safety status."""

        return list_nodes_impl()

    @server.tool()
    def create_experiment_pair(
        baseline_config: str,
        treatment_patch: dict[str, Any],
        control_node: str = "GPU1",
        treatment_node: str = "GPU0",
        paired_seeds: list[int] | None = None,
    ) -> dict[str, Any]:
        """Create a controlled baseline/treatment experiment pair."""

        return create_pair_impl(
            baseline_config=baseline_config,
            treatment_patch=treatment_patch,
            control_node=control_node,
            treatment_node=treatment_node,
            paired_seeds=paired_seeds or [44, 45, 46],
        )

    @server.tool()
    def submit_training_job(
        node: str,
        run_id: str,
        config_path: str,
        data_mode: str = "mock",
    ) -> dict[str, Any]:
        """Submit a mock or sanitized replay training job."""

        return submit_training_impl(
            node=node,
            run_id=run_id,
            config_path=config_path,
            data_mode=data_mode,
        )

    @server.tool()
    def evaluate_policy_on_pc(
        checkpoint_path: str,
        eval_config: str,
        num_rollouts: int = 10,
        data_mode: str = "mock",
    ) -> dict[str, Any]:
        """Evaluate a checkpoint through mock or sanitized replay metrics."""

        return evaluate_impl(
            checkpoint_path=checkpoint_path,
            eval_config=eval_config,
            num_rollouts=num_rollouts,
            data_mode=data_mode,
        )

    @server.tool()
    def run_robot_safety_gate(
        policy_id: str,
        metrics: dict[str, Any],
        strictness: str = "standard",
    ) -> dict[str, Any]:
        """Classify hardware-test readiness from evaluation metrics."""

        return safety_gate_impl(policy_id=policy_id, metrics=metrics, strictness=strictness)

    @server.tool()
    def create_deployment_package(
        policy_id: str,
        safety_level: str,
        free_walking_allowed: bool,
    ) -> dict[str, Any]:
        """Create a mock deployment manifest without executable hardware code."""

        return create_package_impl(
            policy_id=policy_id,
            safety_level=safety_level,
            free_walking_allowed=free_walking_allowed,
        )

    @server.resource("gaitlab://real-replay/manifest")
    def real_replay_manifest() -> str:
        """Expose sanitized replay provenance without private paths."""

        return json.dumps(load_replay_manifest(), indent=2)

    return server


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
