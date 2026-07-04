"""Live lab adapter for Physical AI Safety Agent.

This package connects Physical AI Safety Agent to the real GPU0/GPU1 GPU training
servers, the researcher PC, and the DARwIn-OP robot by wrapping the
already-verified pipeline scripts in the ``physical-ai-lab`` repository.

The package is opt-in via ``data_mode="live_lab"`` and refuses to construct
any agent when ``GAITLAB_ENABLE_SSH`` is not true or when the lab repository
path does not exist on disk. It is excluded from the public submission zip
by ``scripts/build_submission_zip.py``.
"""

from __future__ import annotations

from gaitlab.lab.config import LiveLabConfig, LiveLabNotEnabledError
from gaitlab.lab.deployment import LiveRobotDeployAgent
from gaitlab.lab.evaluation import LiveEvaluationAgent
from gaitlab.lab.training import LiveTrainingNodeAgent

__all__ = [
    "LiveLabConfig",
    "LiveLabNotEnabledError",
    "LiveTrainingNodeAgent",
    "LiveEvaluationAgent",
    "LiveRobotDeployAgent",
    "is_live_lab",
    "build_training_agent",
    "build_evaluation_agent",
    "build_deployment_agent",
]


def is_live_lab(data_mode: str) -> bool:
    """Return True when the requested data mode requires the live lab adapter."""

    return data_mode == "live_lab"


def build_training_agent(node_name: str, data_mode: str) -> LiveTrainingNodeAgent:
    """Construct a live training node agent, refusing when SSH is disabled."""

    config = LiveLabConfig.load()
    if not is_live_lab(data_mode):
        raise LiveLabNotEnabledError(
            f"data_mode={data_mode!r} does not use the live lab adapter"
        )
    config.require_enabled(action=f"live training on {node_name}")
    return LiveTrainingNodeAgent(node_name=node_name, config=config)


def build_evaluation_agent(data_mode: str) -> LiveEvaluationAgent:
    """Construct a live evaluation agent, refusing when SSH is disabled."""

    config = LiveLabConfig.load()
    if not is_live_lab(data_mode):
        raise LiveLabNotEnabledError(
            f"data_mode={data_mode!r} does not use the live lab adapter"
        )
    config.require_enabled(action="live policy evaluation")
    return LiveEvaluationAgent(config=config)


def build_deployment_agent(data_mode: str) -> LiveRobotDeployAgent:
    """Construct a live robot deployment agent, refusing when SSH is disabled."""

    config = LiveLabConfig.load()
    if not is_live_lab(data_mode):
        raise LiveLabNotEnabledError(
            f"data_mode={data_mode!r} does not use the live lab adapter"
        )
    config.require_enabled(action="live robot deployment")
    return LiveRobotDeployAgent(config=config)
