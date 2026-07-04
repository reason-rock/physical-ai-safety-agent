"""HTTP router for the training history SQLite database.

Serves the 167-run, 17.6M-event local DB at ``demo_data/training_history.db``
so the frontend can browse, search, filter, and compare all past training
runs from GPU0/GPU1 without touching the remote servers.

Endpoints:
  GET /api/history/stats                  — aggregate stats (run count, by server/task)
  GET /api/history/runs                   — paginated run list with filtering
  GET /api/history/runs/{id}              — one run's metadata
  GET /api/history/runs/{id}/scalars      — scalar rows for a run (optionally filtered by tag)
  GET /api/history/runs/{id}/scalars/summary — downsampled scalars for charting
  POST /api/history/compare               — compare multiple runs side by side
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from gaitlab.config import ROOT


router = APIRouter(prefix="/api/history", tags=["history"])

DB_PATH = ROOT / "demo_data" / "training_history.db"


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="Training history DB not found. Run scripts/sync_training_history.py first.",
        )
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/stats")
def get_stats() -> dict[str, Any]:
    """Aggregate statistics across all runs."""

    conn = _connect()
    try:
        total_runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        # Sum num_events from the runs table (pre-computed during sync) instead
        # of COUNT(*) on the 17.6M-row scalars table, which takes 10+ seconds.
        total_events = conn.execute(
            "SELECT COALESCE(SUM(num_events), 0) FROM runs"
        ).fetchone()[0]
        by_server = [
            {"server": r[0], "runs": r[1], "events": r[2] or 0, "max_iter": r[3]}
            for r in conn.execute(
                "SELECT server, COUNT(*), SUM(num_events), MAX(max_iteration) FROM runs GROUP BY server"
            )
        ]
        by_task = [
            {"task": r[0], "runs": r[1]}
            for r in conn.execute("SELECT task, COUNT(*) FROM runs GROUP BY task")
        ]
        date_range = conn.execute(
            "SELECT MIN(run_dir), MAX(run_dir) FROM runs WHERE run_dir LIKE '2026%'"
        ).fetchone()
        best_reward = conn.execute(
            "SELECT server, run_dir, final_reward FROM runs ORDER BY final_reward DESC LIMIT 1"
        ).fetchone()
        return {
            "total_runs": total_runs,
            "total_scalars": total_events,
            "by_server": by_server,
            "by_task": by_task,
            "date_range": {"min": date_range[0], "max": date_range[1]},
            "best_reward": _row_to_dict(best_reward) if best_reward else None,
        }
    finally:
        conn.close()


@router.get("/runs")
def list_runs(
    server: str | None = Query(None, description="Filter by server (gpu0/gpu1)"),
    task: str | None = Query(None, description="Filter by task name"),
    min_iter: int | None = Query(None, description="Minimum max_iteration"),
    search: str | None = Query(None, description="Search run_dir"),
    sort: str = Query("start_ts", description="Sort field"),
    order: str = Query("desc", description="asc or desc"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Paginated, filtered run list."""

    allowed_sorts = {"start_ts", "max_iteration", "final_reward", "run_dir", "num_checkpoints"}
    if sort not in allowed_sorts:
        sort = "start_ts"
    direction = "DESC" if order.lower() == "desc" else "ASC"

    conditions = []
    params: list[Any] = []
    if server:
        conditions.append("server = ?")
        params.append(server)
    if task:
        conditions.append("task = ?")
        params.append(task)
    if min_iter is not None:
        conditions.append("max_iteration >= ?")
        params.append(min_iter)
    if search:
        conditions.append("run_dir LIKE ?")
        params.append(f"%{search}%")

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    conn = _connect()
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM runs{where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM runs{where} ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return {
            "total": count,
            "limit": limit,
            "offset": offset,
            "runs": [_row_to_dict(r) for r in rows],
        }
    finally:
        conn.close()


@router.get("/runs/{run_id}")
def get_run(run_id: int) -> dict[str, Any]:
    """One run's metadata."""

    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return _row_to_dict(row)
    finally:
        conn.close()


@router.get("/runs/{run_id}/scalars")
def get_run_scalars(
    run_id: int,
    tag: str | None = Query(None, description="Filter by scalar tag"),
    limit: int = Query(5000, ge=1, le=50000),
) -> dict[str, Any]:
    """Scalar rows for one run, optionally filtered by tag."""

    conn = _connect()
    try:
        # Verify run exists.
        row = conn.execute("SELECT id, run_dir, server, task FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        if tag:
            scalars = conn.execute(
                "SELECT step, tag, value FROM scalars WHERE run_id=? AND tag=? ORDER BY step LIMIT ?",
                (run_id, tag, limit),
            ).fetchall()
        else:
            scalars = conn.execute(
                "SELECT step, tag, value FROM scalars WHERE run_id=? ORDER BY tag, step LIMIT ?",
                (run_id, limit),
            ).fetchall()
        return {
            "run_id": run_id,
            "run_dir": row["run_dir"],
            "server": row["server"],
            "task": row["task"],
            "count": len(scalars),
            "scalars": [_row_to_dict(s) for s in scalars],
        }
    finally:
        conn.close()


@router.get("/runs/{run_id}/scalars/summary")
def get_run_scalars_summary(
    run_id: int,
    tag: str = Query("Train/mean_reward", description="Scalar tag to summarise"),
    buckets: int = Query(100, ge=10, le=500, description="Downsample to N buckets"),
) -> dict[str, Any]:
    """Downsampled scalars for chart-friendly payloads.

    Instead of sending every data point (which can be tens of thousands),
    this returns ``buckets`` evenly-spaced samples along the step axis.
    """

    conn = _connect()
    try:
        row = conn.execute("SELECT id, run_dir, server FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        total = conn.execute(
            "SELECT COUNT(*) FROM scalars WHERE run_id=? AND tag=?", (run_id, tag)
        ).fetchone()[0]
        if total == 0:
            return {"run_id": run_id, "tag": tag, "points": [], "total": 0}

        # Even spacing: pick every Nth row.
        step_size = max(1, total // buckets)
        scalars = conn.execute(
            """SELECT step, value FROM scalars
               WHERE run_id=? AND tag=?
               ORDER BY step
               LIMIT ? OFFSET 0""",
            (run_id, tag, total),
        ).fetchall()
        # Downsample.
        downsampled = [
            {"step": scalars[i]["step"], "value": scalars[i]["value"]}
            for i in range(0, len(scalars), step_size)
        ]
        # Always include the last point.
        if downsampled and scalars and downsampled[-1]["step"] != scalars[-1]["step"]:
            downsampled.append({"step": scalars[-1]["step"], "value": scalars[-1]["value"]})

        return {
            "run_id": run_id,
            "run_dir": row["run_dir"],
            "server": row["server"],
            "tag": tag,
            "total": total,
            "points": downsampled,
        }
    finally:
        conn.close()


@router.get("/runs/{run_id}/tags")
def get_run_tags(run_id: int) -> dict[str, Any]:
    """List all scalar tag names available for a run."""

    conn = _connect()
    try:
        row = conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        tags = conn.execute(
            "SELECT DISTINCT tag, COUNT(*) as count FROM scalars WHERE run_id=? GROUP BY tag ORDER BY tag",
            (run_id,),
        ).fetchall()
        return {"run_id": run_id, "tags": [_row_to_dict(t) for t in tags]}
    finally:
        conn.close()
