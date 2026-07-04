"""HTTP router for Live Control endpoints.

All endpoints are gated by :func:`LiveLabConfig.enabled` (the same gate
the Streamlit app used). When live lab is not configured, these return
HTTP 400 with a clear message instead of crashing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from web.backend import schemas
from web.backend.job_store import JobStore, get_store

if TYPE_CHECKING:
    from gaitlab.lab.config import LiveLabConfig


router = APIRouter(prefix="/api/lab", tags=["live-lab"])


def _require_config() -> LiveLabConfig:
    """Load LiveLabConfig and 400 when live lab is not enabled."""

    LiveLabConfig = _load_live_lab_config()
    config = LiveLabConfig.load()
    if not config.enabled:
        raise HTTPException(
            status_code=400,
            detail=(
                "Live Lab adapter is not enabled. Set GAITLAB_ENABLE_SSH=true "
                "and GAITLAB_LAB_REPO_PATH in .env."
            ),
        )
    return config


@router.get("/config")
def get_lab_config() -> dict:
    """Return a secret-free summary of the live lab configuration."""

    try:
        LiveLabConfig = _load_live_lab_config()
    except HTTPException:
        return _public_lab_summary()
    config = LiveLabConfig.load()
    return config.safe_summary()


@router.get("/nodes/snapshot")
def snapshot_nodes(config: LiveLabConfig = Depends(_require_config)) -> dict:
    """Probe GPU0 + GPU1 right now and return the snapshots."""

    from gaitlab.lab.live_control import snapshot_both

    return snapshot_both(config)


@router.get("/state", response_model=schemas.LabStateResponse)
def get_state(store: JobStore = Depends(get_store)) -> schemas.LabStateResponse:
    """Return the tracked jobs and the cached node snapshots."""

    return _state_response(store)


@router.post("/refresh", response_model=schemas.LabStateResponse)
def refresh_state(
    config: LiveLabConfig = Depends(_require_config),
    store: JobStore = Depends(get_store),
) -> schemas.LabStateResponse:
    """Refresh node snapshots and every active tracked job, then return state."""

    store.snapshot_both(config)
    store.refresh_all_active(config)
    return _state_response(store)


@router.delete("/state", response_model=schemas.OkResponse)
def reset_state(store: JobStore = Depends(get_store)) -> schemas.OkResponse:
    store.reset()
    return schemas.OkResponse()


@router.post("/jobs", response_model=schemas.JobSummaryModel)
def submit_job(
    req: schemas.SubmitJobRequest,
    config: LiveLabConfig = Depends(_require_config),
    store: JobStore = Depends(get_store),
) -> schemas.JobSummaryModel:
    """Submit one training job to a Cell and start tracking it."""

    try:
        summary = store.submit(
            config,
            node=req.node,
            run_id=req.run_id,
            parent_stage=req.parent_stage,
            patch=req.patch,
            num_envs=req.num_envs,
            max_iterations=req.max_iterations,
            wall_clock_cap=req.wall_clock_cap,
            seed=req.seed,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if exc.__class__.__name__ == "LiveLabNotEnabledError":
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise
    return schemas.JobSummaryModel(**_coerce_job(summary))


@router.get("/jobs/{job_id}/status")
def get_job_status(
    job_id: str,
    config: LiveLabConfig = Depends(_require_config),
    store: JobStore = Depends(get_store),
) -> dict:
    """Poll the latest status of a tracked job."""

    return store.refresh_status(config, job_id)


@router.post("/jobs/{job_id}/kill")
def kill_job(
    job_id: str,
    config: LiveLabConfig = Depends(_require_config),
    store: JobStore = Depends(get_store),
) -> dict:
    """Kill a tracked job's tmux session."""

    return store.kill(config, job_id)


@router.post("/jobs/{job_id}/collect")
def collect_job(
    job_id: str,
    config: LiveLabConfig = Depends(_require_config),
    store: JobStore = Depends(get_store),
) -> dict:
    """Trigger rsync + TensorBoard conversion for a tracked job."""

    return store.collect(config, job_id)


@router.post("/sessions/kill")
def kill_session(
    req: schemas.KillSessionRequest,
    config: LiveLabConfig = Depends(_require_config),
) -> dict:
    """Kill an arbitrary tmux session on a host (not necessarily tracked)."""

    from gaitlab.lab.live_control import kill_session_by_name

    return kill_session_by_name(req.host, req.session)


def _coerce_job(job: dict) -> dict:
    """Coerce a tracked-job dict into JobSummaryModel-compatible kwargs.

    Skips keys the model does not declare (e.g. ``collect_result``).
    """

    allowed = set(schemas.JobSummaryModel.model_fields.keys())
    return {k: v for k, v in job.items() if k in allowed}


def _state_response(store: JobStore) -> schemas.LabStateResponse:
    jobs = store.list_jobs()
    cache, ts = store.get_node_cache()
    return schemas.LabStateResponse(
        jobs=[schemas.JobSummaryModel(**_coerce_job(job)) for job in jobs],
        node_cache=cache,
        node_cache_ts=ts,
    )


def _load_live_lab_config():
    """Load the private lab adapter only when a live-lab endpoint needs it."""

    try:
        from gaitlab.lab.config import LiveLabConfig
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("gaitlab.lab"):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Live Lab adapter is not included in the public demo. "
                    "Use Mock Demo or Sanitized Real Replay."
                ),
            ) from exc
        raise
    return LiveLabConfig


def _public_lab_summary() -> dict:
    """Secret-free disabled config returned by the public submission build."""

    return {
        "mode": "public_demo",
        "enable_ssh": False,
        "allow_real_robot": False,
        "enabled": False,
        "lab_repo_path": "",
        "pipeline_dir": "",
        "remote_repo_path": "",
        "gpu0_host": "GPU0",
        "gpu1_host": "GPU1",
        "research_pc_host": "localhost",
        "robot_host": "offline_mock",
        "train_host_primary": "",
        "train_host_fallbacks": [],
        "robot_fallbacks": [],
        "ssh_user": "",
        "ssh_key_configured": False,
        "operator_approval_required": True,
        "estop_dry_run_required": True,
        "message": "Live Lab adapter is excluded from the public demo.",
    }
