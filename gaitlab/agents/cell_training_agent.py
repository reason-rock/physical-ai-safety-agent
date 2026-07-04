from __future__ import annotations

from gaitlab.tools.training_tools import collect_training_artifacts, submit_training_job


class TrainingNodeAgent:
    """Public-demo adapter for a GPU0 or GPU1 training node."""

    def __init__(self, node_name: str, data_mode: str = "mock") -> None:
        self.node_name = node_name
        self.data_mode = data_mode

    def submit(self, run_config: dict) -> dict:
        return submit_training_job(
            node=self.node_name,
            run_id=run_config["run_id"],
            config_path=run_config["config_path"],
            data_mode=self.data_mode,
        )

    def collect(self, run_id: str) -> dict:
        return collect_training_artifacts(run_id, data_mode=self.data_mode)
