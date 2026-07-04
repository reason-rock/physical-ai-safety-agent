from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def create_deployment_package(
    policy_id: str,
    safety_level: str,
    free_walking_allowed: bool,
) -> dict[str, Any]:
    """Create a safety-gated deployment manifest without executable hardware code."""

    out_dir = ROOT / "deployment"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "policy_id": policy_id,
        "package_type": "safety_manifest_only",
        "safety_level": safety_level,
        "free_walking_allowed": free_walking_allowed,
        "contains": [
            "policy_metadata.json",
            "evaluation_summary.json",
            "robot_action_diff.md",
            "operator_checklist.md",
        ],
        "does_not_contain": [
            "real hardware credentials",
            "SSH private keys",
            "motor command scripts",
            "auto-run deployment hooks",
        ],
        "human_approval_required": True,
    }
    manifest_path = out_dir / f"{policy_id}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "manifest_path": str(manifest_path.relative_to(ROOT)).replace("\\", "/"),
        "package_type": manifest["package_type"],
        "human_approval_required": True,
        "free_walking_allowed": free_walking_allowed,
        "contains": manifest["contains"],
    }
