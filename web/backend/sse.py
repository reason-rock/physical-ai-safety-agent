"""Server-Sent Events endpoint for live lab updates.

A single background daemon thread wakes every few seconds, refreshes the
node snapshots and any active tracked jobs, and pushes a JSON event to
every connected subscriber. Subscribers connect via ``GET /sse/lab`` and
re-render the Live Control UI on each push.

The background thread is started lazily on the first subscriber or on
FastAPI startup via :func:`ensure_background_loop`. It only runs when
live lab is enabled.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from web.backend import schemas
from web.backend.job_store import JobStore, get_store

if TYPE_CHECKING:
    from gaitlab.lab.config import LiveLabConfig


router = APIRouter(prefix="/sse", tags=["sse"])

REFRESH_INTERVAL_SEC = 5.0


# ---------------------------------------------------------------------------
# Subscriber registry + background loop
# ---------------------------------------------------------------------------

# Each subscriber is an asyncio.Queue. Subscribers can be added/removed from
# any thread (we hold a regular lock around the list), but the queues
# themselves are asyncio-safe so the producer (background thread) can call
# ``put_nowait`` cross-thread without breaking the consumer.
_subscribers: list[asyncio.Queue[str]] = []
_subscribers_lock = threading.Lock()
_background_started = False
_background_start_lock = threading.Lock()


def ensure_background_loop() -> None:
    """Start the background refresh thread once per process (idempotent)."""

    global _background_started
    with _background_start_lock:
        if _background_started:
            return
        config = _load_config_or_none()
        if config is None or not config.enabled:
            # Nothing to poll; do not start a thread. The SSE handler will
            # emit an "adapter disabled" event to subscribers instead.
            return
        thread = threading.Thread(
            target=_refresh_loop,
            args=(config,),
            name="gaitlab-sse-loop",
            daemon=True,
        )
        thread.start()
        _background_started = True


# Alias kept for legacy callers (older verify.py / test code).
def maybe_start_background(app_state: dict[str, Any] | None = None) -> None:
    ensure_background_loop()


def _refresh_loop(config: LiveLabConfig) -> None:
    """Forever: refresh node snapshots + active jobs, push to subscribers."""

    from web.backend.job_store import STORE

    while True:
        try:
            STORE.snapshot_both(config)
            STORE.refresh_all_active(config)
            payload = _build_event(STORE)
            _broadcast(payload)
        except Exception as exc:  # noqa: BLE001 - loop must not die
            err = json.dumps({"error": str(exc)[:200], "ts": time.time()})
            _broadcast(err)
        time.sleep(REFRESH_INTERVAL_SEC)


def _broadcast(payload: str) -> None:
    """Push ``payload`` to every subscriber queue (cross-thread safe)."""

    with _subscribers_lock:
        queues = list(_subscribers)
    for queue in queues:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass


# ---------------------------------------------------------------------------
# SSE endpoint
# ---------------------------------------------------------------------------


@router.get("/lab")
async def lab_stream(
    request: Request,
    store: JobStore = Depends(get_store),
) -> EventSourceResponse:
    """Emit a ``LabUpdate`` event every few seconds until the client drops."""

    # Make sure the background loop is running.
    ensure_background_loop()

    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=64)
    with _subscribers_lock:
        _subscribers.append(queue)

    config = _load_config_or_none()

    async def event_generator():
        try:
            # Emit one immediate event so the UI shows something without
            # waiting for the first background tick. Build it from the
            # latest cached snapshot (which may be empty on cold start).
            await queue.put(_build_event(store))
            # If we have no cached snapshot yet AND live lab is enabled,
            # trigger an immediate one-shot snapshot in a worker thread so
            # the user does not stare at "waiting for first snapshot".
            cache, _ts = store.get_node_cache()
            if not cache and config is not None and config.enabled:
                try:
                    await asyncio.to_thread(store.snapshot_both, config)
                    await queue.put(_build_event(store))
                except Exception as exc:  # noqa: BLE001
                    await queue.put(
                        json.dumps({"error": str(exc)[:200], "ts": time.time()})
                    )
            while not await request.is_disconnected():
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # Keep-alive comment so the browser does not drop us.
                    yield {"event": "ping", "data": str(int(time.time()))}
                    continue
                yield {
                    "event": "lab-update",
                    "data": payload,
                }
        finally:
            with _subscribers_lock:
                try:
                    _subscribers.remove(queue)
                except ValueError:
                    pass

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_event(store: JobStore) -> str:
    """Serialise the current store state as a LabUpdateEvent JSON string."""

    jobs = store.list_jobs()
    cache, _ts = store.get_node_cache()
    event = {
        "ts": time.time(),
        "nodes": cache,
        "jobs": [_coerce_job(job) for job in jobs],
    }
    return json.dumps(event, default=str)


def _coerce_job(job: dict) -> dict:
    allowed = set(schemas.JobSummaryModel.model_fields.keys())
    return {k: v for k, v in job.items() if k in allowed}


def _load_config_or_none() -> LiveLabConfig | None:
    try:
        from gaitlab.lab.config import LiveLabConfig

        return LiveLabConfig.load()
    except Exception:  # noqa: BLE001
        return None
