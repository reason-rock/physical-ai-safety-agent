from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from gaitlab.models import ExperimentPair
from gaitlab.tools.experiment_store import create_experiment_pair


class ExperimentDesignAgent:
    """Converts a researcher request into a controlled A/B experiment pair."""

    def create_pair(self, user_request: str) -> ExperimentPair:
        design = self._design_with_google(user_request) or {}
        patch = self._sanitize_patch(
            design.get("patch")
            if isinstance(design.get("patch"), dict)
            else self._infer_patch(user_request)
        )
        design_runtime = "google_gemini" if design else "deterministic_rules"
        result = create_experiment_pair(
            baseline_config="demo_data/configs/previous_stable_baseline.yaml",
            treatment_patch=patch,
            control_node="GPU1",
            treatment_node="GPU0",
            paired_seeds=[101, 102, 103],
        )
        changed = ", ".join(sorted(patch))
        warning = None
        if len(patch) > 3:
            warning = "Treatment changes more than three variables; causal attribution may be weak."
        return ExperimentPair(
            pair_id=result["pair_id"],
            control=result["control"],
            treatment=result["treatment"],
            controlled_variables=[
                "robot_model=darwin_op",
                "sim_backend=controlled_simulation",
                "target_velocity=0.055",
                "total_steps=20000000",
                "sim_timestep=0.008",
                "seed_group=paired_101_102_103",
                f"design_runtime={design_runtime}",
            ],
            hypothesis=self._sanitize_text(design.get("hypothesis"))
            if design.get("hypothesis")
            else (
                "Increasing orientation stability penalties should reduce forward falls, "
                "but may reduce forward velocity or increase energy use."
            )
            if "reward.orientation_penalty" in patch
            else f"Changing {changed} should improve the declared physical-AI failure mode.",
            warning=self._sanitize_text(design.get("warning")) if design.get("warning") else warning,
        )

    def _design_with_google(self, user_request: str) -> dict[str, Any] | None:
        if not _env_bool("GAITLAB_USE_GOOGLE_API"):
            return None
        api_key = _setting("GOOGLE_API_KEY") or _setting("GEMINI_API_KEY")
        if not api_key:
            return None
        try:
            from google import genai
        except ModuleNotFoundError:
            return None

        model = _setting("GAITLAB_GEMINI_MODEL") or "gemini-3.5-flash"
        prompt = (
            "You are the experiment-design subagent for Physical AI Safety Agent. "
            "Convert the researcher request into a controlled A/B treatment patch. "
            "Return ONLY compact JSON with keys patch, hypothesis, warning. "
            "patch may only use these numeric keys: "
            "reward.orientation_penalty, reward.action_smoothness, "
            "reward.velocity_tracking, reward.pitch_penalty, reward.action_l2. "
            "Use multiplier values between 0.5 and 2.0. Control must remain unchanged. "
            "Never request credentials and never propose robot or hardware commands.\n\n"
            f"Researcher request:\n{user_request}"
        )
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(model=model, contents=prompt)
            text = getattr(response, "text", "") or ""
            return self._parse_json_object(text)
        except Exception:
            return None

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any] | None:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        match = re.search(r"\{.*\}", stripped, flags=re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _sanitize_patch(raw: dict[str, Any]) -> dict[str, float]:
        allowed = {
            "reward.orientation_penalty",
            "reward.action_smoothness",
            "reward.velocity_tracking",
            "reward.pitch_penalty",
            "reward.action_l2",
        }
        patch: dict[str, float] = {}
        for key, value in raw.items():
            if key not in allowed:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            patch[key] = max(0.5, min(2.0, numeric))
        return patch or {"reward.orientation_penalty": 1.15}

    @staticmethod
    def _sanitize_text(raw: Any) -> str:
        return str(raw).strip().replace("\n", " ")[:320]

    @staticmethod
    def _infer_patch(user_request: str) -> dict[str, float]:
        text = user_request.lower()
        patch: dict[str, float] = {}
        if "orientation" in text or "forward" in text or "fell" in text or "fall" in text:
            patch["reward.orientation_penalty"] = 1.30
            patch["reward.action_smoothness"] = 1.15
        if "velocity" in text or "frozen" in text or "not move" in text:
            patch["reward.velocity_tracking"] = 1.25
        if not patch:
            patch["reward.orientation_penalty"] = 1.15
        return patch


def _env_bool(name: str) -> bool:
    return _setting(name).strip().lower() in {"1", "true", "yes", "on"}


def _setting(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return ""
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        if key.strip() == name:
            return raw_value.strip().strip('"').strip("'")
    return ""
