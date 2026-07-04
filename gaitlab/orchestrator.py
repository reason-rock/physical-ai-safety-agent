from __future__ import annotations

from typing import Any, Protocol

from gaitlab.agents.cell_training_agent import TrainingNodeAgent
from gaitlab.agents.evaluation_agent import EvaluationAgent
from gaitlab.agents.experiment_design_agent import ExperimentDesignAgent
from gaitlab.agents.failure_analysis_agent import FailureAnalysisAgent
from gaitlab.agents.report_agent import ReportAgent
from gaitlab.agents.safety_gate_agent import SafetyGateAgent
from gaitlab.config import GaitLabConfig
from gaitlab.models import WorkflowResult
from gaitlab.tools.deployment_tools import create_deployment_package
from gaitlab.tools.node_registry import list_nodes


class _TrainingLike(Protocol):
    def submit(self, run_config: dict) -> dict: ...
    def collect(self, run_id: str) -> dict: ...


class _EvaluationLike(Protocol):
    def evaluate(self, run_id: str) -> dict: ...
    def compare(
        self,
        control_run_id: str,
        treatment_run_id: str,
        evaluations: dict,
    ) -> dict: ...


def _is_live_lab(data_mode: str) -> bool:
    return data_mode == "live_lab"


class GaitLabOrchestrator:
    """Coordinates the Physical AI Safety Agent workflow.

    The default ``data_mode="mock"`` keeps the public-demo behavior intact.
    ``data_mode="live_lab"`` swaps in the real lab adapter from
    :mod:`gaitlab.lab` and may, when every safety precondition is met,
    deploy a policy to the real robot. ``data_mode="real_replay"`` reads
    sanitized real replay evidence and is unchanged.
    """

    def __init__(
        self,
        num_rollouts: int = 10,
        safety_strictness: str = "standard",
        data_mode: str = "mock",
        operator_token: str | None = None,
    ) -> None:
        self.num_rollouts = num_rollouts
        self.safety_strictness = safety_strictness
        self.data_mode = data_mode
        self.operator_token = operator_token
        self.design_agent = ExperimentDesignAgent()
        self.failure_agent = FailureAnalysisAgent()
        self.safety_agent = SafetyGateAgent(strictness=safety_strictness)
        self.report_agent = ReportAgent()
        self.evaluation_agent = self._build_evaluation_agent()
        self._live_lab_enabled = _is_live_lab(data_mode) and self._safe_to_enable_live_lab()

    # ------------------------------------------------------------------
    # Agent factories
    # ------------------------------------------------------------------

    def _safe_to_enable_live_lab(self) -> bool:
        """Probe whether the live lab adapter is configured enough to use.

        Does NOT raise: if the lab adapter is not enabled (e.g. SSH flag
        off, or the lab repo path missing), we want the orchestrator to
        fall back to mock behavior with a clear audit message rather than
        crash. Hard refusal happens inside the adapter's
        ``require_enabled`` when something actually tries to do live work.
        """

        try:
            from gaitlab.lab.config import LiveLabConfig

            return LiveLabConfig.load().enabled
        except Exception:
            return False

    def _build_evaluation_agent(self) -> Any:
        if _is_live_lab(self.data_mode) and self._safe_to_enable_live_lab():
            from gaitlab.lab.evaluation import LiveEvaluationAgent

            try:
                return LiveEvaluationAgent(
                    data_mode=self.data_mode, num_rollouts=self.num_rollouts
                )
            except Exception:
                # Fall back to the mock agent; live mode is best-effort here.
                pass
        return EvaluationAgent(num_rollouts=self.num_rollouts, data_mode=self.data_mode)

    def _build_training_agent(self, node_name: str) -> Any:
        if self._live_lab_enabled:
            from gaitlab.lab.training import LiveTrainingNodeAgent

            try:
                return LiveTrainingNodeAgent(
                    node_name=node_name, data_mode=self.data_mode
                )
            except Exception:
                pass
        return TrainingNodeAgent(node_name, data_mode=self.data_mode)

    # ------------------------------------------------------------------
    # Main workflow
    # ------------------------------------------------------------------

    def handle_request(self, user_request: str) -> WorkflowResult:
        config = GaitLabConfig.load()
        audit_log: list[str] = [
            f"mode={config.mode}",
            f"use_mock_nodes={config.use_mock_nodes}",
            f"enable_ssh={config.enable_ssh}",
            f"allow_real_robot={config.allow_real_robot}",
            f"data_mode={self.data_mode}",
            f"live_lab_enabled={self._live_lab_enabled}",
        ]
        # ``real_robot_commands=blocked`` is the default. When a live deploy
        # actually happens, this line is overwritten near the end of the run
        # with ``real_robot_commands=deployed_with_approval``. The safety
        # gate and the live deploy agent together decide whether to deploy.
        audit_log.append("real_robot_commands=blocked")
        if self._live_lab_enabled:
            audit_log.append("live_lab_adapter=active")
        elif _is_live_lab(self.data_mode):
            audit_log.append(
                "live_lab_adapter=requested_but_disabled_falling_back_to_mock"
            )

        nodes = list_nodes()["nodes"]
        pair = self.design_agent.create_pair(user_request)
        audit_log.append(f"created_pair={pair.pair_id}")

        control_agent = self._build_training_agent("GPU1")
        treatment_agent = self._build_training_agent("GPU0")

        control_job = control_agent.submit(pair.control)
        treatment_job = treatment_agent.submit(pair.treatment)
        training_jobs = [treatment_job, control_job]
        audit_log.extend(
            [f"submitted={treatment_job['job_id']}", f"submitted={control_job['job_id']}"]
        )

        artifacts = [
            treatment_agent.collect(pair.treatment["run_id"]),
            control_agent.collect(pair.control["run_id"]),
        ]

        evaluations = {
            pair.control["run_id"]: self.evaluation_agent.evaluate(pair.control["run_id"]),
            pair.treatment["run_id"]: self.evaluation_agent.evaluate(pair.treatment["run_id"]),
        }
        comparison = self.evaluation_agent.compare(
            control_run_id=pair.control["run_id"],
            treatment_run_id=pair.treatment["run_id"],
            evaluations=evaluations,
        )
        failure_analysis = self.failure_agent.analyze(
            comparison, evaluations[pair.treatment["run_id"]]
        )
        safety = self.safety_agent.run_gate(
            policy_id=f"{pair.treatment['run_id']}_ckpt_20m",
            metrics=evaluations[pair.treatment["run_id"]],
        )
        deployment_package = self._build_deployment_package(
            pair=pair,
            safety=safety,
            metrics=evaluations[pair.treatment["run_id"]],
            audit_log=audit_log,
        )
        audit_log.append(f"deployment_manifest={deployment_package['manifest_path']}")
        robot_action_diff = self.safety_agent.create_robot_action_diff(
            policy_id=f"{pair.treatment['run_id']}_ckpt_20m",
            safety=safety,
            metrics=evaluations[pair.treatment["run_id"]],
        )
        report_markdown = self.report_agent.render(
            pair=pair,
            nodes=nodes,
            training_jobs=training_jobs,
            evaluations=evaluations,
            comparison=comparison,
            failure_analysis=failure_analysis,
            safety=safety,
            deployment_package=deployment_package,
            robot_action_diff=robot_action_diff,
            audit_log=audit_log,
        )

        return WorkflowResult(
            pair=pair,
            nodes=nodes,
            training_jobs=training_jobs,
            artifacts=artifacts,
            evaluations=evaluations,
            comparison=comparison,
            failure_analysis=failure_analysis,
            safety=safety,
            deployment_package=deployment_package,
            robot_action_diff=robot_action_diff,
            report_markdown=report_markdown,
            audit_log=audit_log,
        )

    def _build_deployment_package(
        self,
        pair,
        safety,
        metrics,
        audit_log,
    ) -> dict:
        """Return the deployment package, possibly executing a live deploy.

        When live lab mode is enabled AND the safety gate AND the live
        deploy gate both allow it, this invokes the real robot. Otherwise
        it returns the public-demo mock package unchanged.
        """

        policy_id = f"{pair.treatment['run_id']}_ckpt_20m"
        if not self._live_lab_enabled:
            return create_deployment_package(
                policy_id=policy_id,
                safety_level=safety["safety_level"],
                free_walking_allowed=safety["free_walking_allowed"],
            )

        from gaitlab.lab.deployment import LiveRobotDeployAgent, deployment_allowed

        try:
            deploy_agent = LiveRobotDeployAgent(data_mode=self.data_mode)
        except Exception as exc:
            audit_log.append(f"live_deploy_agent_unavailable={exc}")
            return create_deployment_package(
                policy_id=policy_id,
                safety_level=safety["safety_level"],
                free_walking_allowed=safety["free_walking_allowed"],
            )

        # Resolve the exported TorchScript policy if it exists. Live deploy
        # requires a real file; mock mode never did, so this doubles as the
        # natural fallback path.
        candidate_policy = self._resolve_live_policy_path(pair.treatment["run_id"])
        decision = deployment_allowed(
            safety=safety,
            metrics=metrics,
            config=deploy_agent.config,
            operator_token=self.operator_token,
            policy_path=candidate_policy,
        )
        audit_log.append(
            f"live_deploy_decision_allowed={decision.allowed}"
        )
        if not decision.allowed:
            audit_log.append(
                "live_deploy_block_reasons=" + "; ".join(decision.reasons)
            )

        if decision.allowed and candidate_policy is not None:
            manifest = deploy_agent.run(
                safety=safety,
                metrics=metrics,
                policy_path=candidate_policy,
                operator_token=self.operator_token,
                tag=pair.treatment["run_id"],
            )
            if manifest.get("live_deploy_allowed") and manifest.get(
                "deploy_returncode", 1
            ) == 0:
                # Flip the audit line: a real robot deploy actually happened.
                self._replace_audit_line(
                    audit_log,
                    "real_robot_commands=blocked",
                    "real_robot_commands=deployed_with_approval",
                )
            return manifest

        # Gate blocked (or policy file missing): fall back to mock package
        # annotated with the live-deploy decision for transparency.
        mock = create_deployment_package(
            policy_id=policy_id,
            safety_level=safety["safety_level"],
            free_walking_allowed=safety["free_walking_allowed"],
        )
        mock.update(
            {
                "live_deploy_attempted": True,
                "live_deploy_allowed": False,
                "block_reasons": decision.reasons,
                "required_actions": decision.required_actions,
            }
        )
        return mock

    def _resolve_live_policy_path(self, run_id: str):
        """Return the path to an exported TorchScript policy, or None."""

        if not self._live_lab_enabled:
            return None
        try:
            from gaitlab.lab.config import LiveLabConfig

            config = LiveLabConfig.load()
        except Exception:
            return None
        # Look under rl/model/ for a tag matching the run id, then for a
        # current/policy.pt. This is best-effort: the live deploy agent's
        # own gate re-checks existence before doing anything.
        candidates = [
            config.lab_repo_path / "rl" / "model" / "current" / "policy.pt",
            config.lab_repo_path / "rl" / "model" / f"{run_id}.pt",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _replace_audit_line(audit_log: list[str], old: str, new: str) -> None:
        try:
            idx = audit_log.index(old)
        except ValueError:
            audit_log.append(new)
            return
        audit_log[idx] = new
