from __future__ import annotations

from gaitlab.config import GaitLabConfig, _mask_host


def list_nodes() -> dict:
    """Return configured lab node availability without opening network connections."""

    config = GaitLabConfig.load()
    status = config.node_status()
    return {
        "nodes": [
            {"name": "GPU0", "role": "training", "status": status, "host": _mask_host(config.gpu0_host)},
            {"name": "GPU1", "role": "training", "status": status, "host": _mask_host(config.gpu1_host)},
            {
                "name": "ResearcherPC",
                "role": "evaluation",
                "status": status,
                "host": _mask_host(config.research_pc_host),
            },
            {
                "name": "Robot",
                "role": "safety_gated_target",
                "status": "blocked_by_policy" if not config.allow_real_robot else status,
                "host": _mask_host(config.robot_host),
            },
        ]
    }
