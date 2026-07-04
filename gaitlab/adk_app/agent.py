from __future__ import annotations

from typing import Any

from gaitlab.orchestrator import GaitLabOrchestrator
from gaitlab.tools.node_registry import list_nodes
from gaitlab.tools.replay_data import load_replay_manifest

try:  # pragma: no cover - optional integration import
    from google.adk import Agent
except ModuleNotFoundError:  # pragma: no cover - default public demo path
    Agent = None  # type: ignore[assignment]


def list_lab_nodes() -> dict[str, Any]:
    """Return Physical AI Safety Agent public-demo node status."""

    return list_nodes()


def inspect_real_replay_manifest() -> dict[str, Any]:
    """Return sanitized real replay provenance without private paths."""

    return load_replay_manifest()


def run_gaitlab_workflow(
    request: str,
    data_mode: str = "mock",
    safety_strictness: str = "standard",
    num_rollouts: int = 10,
) -> dict[str, Any]:
    """Run the Physical AI Safety Agent workflow and return judge-relevant results."""

    result = GaitLabOrchestrator(
        num_rollouts=num_rollouts,
        safety_strictness=safety_strictness,
        data_mode=data_mode,
    ).handle_request(request)
    return {
        "pair_id": result.pair.pair_id,
        "decision": result.comparison["decision"],
        "recommendation": result.comparison["recommendation"],
        "safety": result.safety,
        "deployment_package": result.deployment_package,
        "audit_log": result.audit_log,
        "report_excerpt": result.report_markdown[:2000],
    }


def build_root_agent():
    """Build a Google ADK root agent around the Physical AI Safety Agent workflow."""

    if Agent is None:
        raise RuntimeError(
            "Google ADK is not installed. Run "
            "`.\\.venv\\Scripts\\python.exe -m pip install -e .[integrations]` "
            "to enable the optional ADK adapter."
        )

    return Agent(
        name="gaitlab_root_agent",
        model="gemini-3.5-flash",
        instruction=(
            "You are Physical AI Safety Agent, a safety-first multi-agent control tower for "
            "physical-AI experiments. Use the provided tools to list lab nodes, "
            "inspect sanitized real replay evidence, run controlled A/B policy "
            "workflows, and explain why unsupervised hardware testing remains "
            "blocked unless all safety evidence and human-review requirements are "
            "present. Never request secrets or execute hardware commands."
        ),
        tools=[
            list_lab_nodes,
            inspect_real_replay_manifest,
            run_gaitlab_workflow,
        ],
    )


root_agent = build_root_agent() if Agent is not None else None
