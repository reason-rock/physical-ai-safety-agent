"""``python -m web.backend.run`` starts uvicorn on port 8000."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("GAITLAB_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("GAITLAB_WEB_PORT", "8000"))
    reload = os.environ.get("GAITLAB_WEB_RELOAD", "0") == "1"
    uvicorn.run(
        "web.backend.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
