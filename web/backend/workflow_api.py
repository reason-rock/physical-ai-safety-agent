"""HTTP router for the workflow + node registry endpoints.

Wraps :class:`gaitlab.orchestrator.GaitLabOrchestrator` and
:func:`gaitlab.tools.node_registry.list_nodes` so the Next.js frontend
can run the same workflow the Streamlit app did.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from gaitlab.models import WorkflowResult
from gaitlab.orchestrator import GaitLabOrchestrator
from gaitlab.tools.node_registry import list_nodes
from web.backend import schemas


router = APIRouter(prefix="/api", tags=["workflow"])


@router.get("/nodes", response_model=schemas.NodeListResponse)
def get_nodes() -> schemas.NodeListResponse:
    """Return the configured lab node registry."""

    data = list_nodes()
    return schemas.NodeListResponse(
        nodes=[schemas.NodeModel(**node) for node in data["nodes"]]
    )


@router.post("/workflow", response_model=schemas.WorkflowResultModel)
def run_workflow(req: schemas.WorkflowRequest) -> schemas.WorkflowResultModel:
    """Run one full Physical AI Safety Agent workflow synchronously and return the result.

    For ``data_mode="live_lab"`` the caller MUST set ``operator_confirmed``.
    Long-running live workflows block this request until completion; the
    Live Control tab uses the async ``/api/lab/*`` endpoints instead.
    """

    if req.data_mode == "live_lab" and not req.operator_confirmed:
        raise HTTPException(
            status_code=400,
            detail=(
                "Live Lab workflow requires operator_confirmed=true. The "
                "operator must check the emergency-stop confirmation box."
            ),
        )

    orchestrator = GaitLabOrchestrator(
        num_rollouts=req.num_rollouts,
        safety_strictness=req.safety_strictness,
        data_mode=req.data_mode,
        operator_token=req.operator_token,
    )
    result: WorkflowResult = orchestrator.handle_request(req.request)
    return _serialize_result(result)


def _serialize_result(result: WorkflowResult) -> schemas.WorkflowResultModel:
    """Convert a WorkflowResult dataclass into its Pydantic mirror."""

    pair = schemas.ExperimentPairModel(
        pair_id=result.pair.pair_id,
        control=result.pair.control,
        treatment=result.pair.treatment,
        controlled_variables=result.pair.controlled_variables,
        hypothesis=result.pair.hypothesis,
        warning=result.pair.warning,
    )
    return schemas.WorkflowResultModel(
        pair=pair,
        nodes=list(result.nodes),
        training_jobs=list(result.training_jobs),
        artifacts=list(result.artifacts),
        evaluations={k: dict(v) for k, v in result.evaluations.items()},
        comparison=dict(result.comparison),
        failure_analysis=dict(result.failure_analysis),
        safety=dict(result.safety),
        deployment_package=dict(result.deployment_package),
        robot_action_diff=result.robot_action_diff,
        report_markdown=result.report_markdown,
        audit_log=list(result.audit_log),
    )
