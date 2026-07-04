"""FastAPI application factory for the Physical AI Safety Agent dashboard backend."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from web.backend import schemas
from web.backend.history_api import router as history_router
from web.backend.lab_api import router as lab_router
from web.backend.replay_api import router as replay_router
from web.backend.sse import router as sse_router
from web.backend.workflow_api import router as workflow_router


def create_app() -> FastAPI:
    """Build the FastAPI app with all routers mounted."""

    app = FastAPI(
        title="Physical AI Safety Agent",
        version="0.1.0",
        description=(
            "Backend for the Physical AI Safety Agent dashboard. Wraps the "
            "gaitlab.* Python API (orchestrator + lab adapter + safety "
            "gate) so a Next.js frontend can drive it over HTTP/SSE."
        ),
    )

    # CORS: in dev the Next.js app runs on :3000 and the API on :8000.
    # Wide-open CORS is fine here because the API is single-operator and
    # never accepts credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", response_model=schemas.HealthResponse, tags=["meta"])
    def health() -> schemas.HealthResponse:
        """Lightweight liveness probe used by the frontend and verify.py."""

        live_enabled = False
        try:
            from gaitlab.lab.config import LiveLabConfig

            live_enabled = LiveLabConfig.load().enabled
        except Exception:  # noqa: BLE001 - health must never fail
            live_enabled = False
        return schemas.HealthResponse(status="ok", live_lab_enabled=live_enabled)

    app.include_router(workflow_router)
    app.include_router(replay_router)
    app.include_router(history_router)
    app.include_router(lab_router)
    app.include_router(sse_router)

    # Start the SSE background refresh loop on app startup (idempotent).
    @app.on_event("startup")
    def _start_sse_loop() -> None:
        try:
            from web.backend.sse import ensure_background_loop

            ensure_background_loop()
        except Exception:  # noqa: BLE001 - startup must not fail
            pass

    # In production, serve the Next.js static export if it exists.
    frontend_out = Path(__file__).resolve().parents[2] / "web" / "frontend" / "out"
    if frontend_out.exists():
        app.mount(
            "/_next",
            StaticFiles(directory=frontend_out / "_next"),
            name="next-static",
        )

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> FileResponse | JSONResponse:
            """SPA fallback: serve index.html for any non-API path."""

            candidate = frontend_out / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            index = frontend_out / "index.html"
            if index.exists():
                return FileResponse(index)
            return JSONResponse(
                {"detail": "frontend not built. Run `npm run build` in web/frontend."},
                status_code=404,
            )

    return app


app = create_app()
