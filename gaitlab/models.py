from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExperimentPair:
    pair_id: str
    control: dict[str, Any]
    treatment: dict[str, Any]
    controlled_variables: list[str]
    hypothesis: str
    warning: str | None = None


@dataclass
class WorkflowResult:
    pair: ExperimentPair
    nodes: list[dict[str, Any]]
    training_jobs: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    evaluations: dict[str, dict[str, Any]]
    comparison: dict[str, Any]
    failure_analysis: dict[str, Any]
    safety: dict[str, Any]
    deployment_package: dict[str, Any]
    robot_action_diff: str
    report_markdown: str
    audit_log: list[str] = field(default_factory=list)
