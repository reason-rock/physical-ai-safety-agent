"""Pydantic schemas mirroring the ``gaitlab.*`` dataclasses.

These models are the single source of truth for the JSON contract between
the FastAPI backend and the Next.js frontend. They mirror
``gaitlab.models.WorkflowResult`` / ``ExperimentPair`` (which stay as
dataclasses for the CLI path) plus request bodies for the HTTP endpoints.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class WorkflowRequest(BaseModel):
    """Body for ``POST /api/workflow``."""

    request: str = Field(
        ...,
        description="Natural-language experiment request fed to the design agent.",
    )
    num_rollouts: int = Field(256, ge=1, le=5000)
    safety_strictness: Literal["standard", "strict"] = "standard"
    data_mode: Literal["mock", "real_replay", "live_lab"] = "mock"
    operator_token: str | None = None
    operator_confirmed: bool = Field(
        False,
        description="Required to be True when data_mode == 'live_lab'.",
    )


class SubmitJobRequest(BaseModel):
    """Body for ``POST /api/lab/jobs``."""

    node: Literal["GPU0", "GPU1"]
    run_id: str
    parent_stage: str = "stage45_scratch"
    patch: dict[str, Any] | None = None
    num_envs: int = Field(1024, ge=64, le=65536)
    max_iterations: int = Field(5000, ge=1, le=200000)
    wall_clock_cap: str = "4h"
    seed: int = Field(0, ge=0, le=999999)


class KillSessionRequest(BaseModel):
    """Body for ``POST /api/lab/sessions/kill``."""

    host: str
    session: str


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------


class ExperimentPairModel(BaseModel):
    pair_id: str
    control: dict[str, Any]
    treatment: dict[str, Any]
    controlled_variables: list[str]
    hypothesis: str
    warning: str | None = None


class WorkflowResultModel(BaseModel):
    """JSON-serialisable mirror of ``gaitlab.models.WorkflowResult``."""

    pair: ExperimentPairModel
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
    audit_log: list[str] = Field(default_factory=list)


class NodeModel(BaseModel):
    name: str
    role: str
    status: str
    host: str | None = None


class NodeListResponse(BaseModel):
    nodes: list[NodeModel]


class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"
    live_lab_enabled: bool = False


class JobSummaryModel(BaseModel):
    """One tracked live training job."""

    job_id: str
    node: str
    run_id: str
    config_path: str = ""
    status: str
    progress: float = 0.0
    latest_step: int = 0
    estimated_remaining_min: int = 0
    latest_reward: float = 0.0
    fall_rate: float = 0.0
    evidence_mode: str = "live_lab"
    stage_name: str = ""
    tmux_session: str = ""
    host_masked: str = ""
    submitted_at: float = 0.0
    max_iterations: int = 0
    status_history: list[list[Any]] = Field(default_factory=list)
    collected: bool = False


class LabStateResponse(BaseModel):
    """Snapshot of the in-memory live control state."""

    jobs: list[JobSummaryModel]
    node_cache: dict[str, Any]
    node_cache_ts: float


class LabUpdateEvent(BaseModel):
    """SSE event payload pushed every refresh cycle."""

    ts: float
    nodes: dict[str, Any]
    jobs: list[JobSummaryModel]


class OkResponse(BaseModel):
    ok: bool = True


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
