from pathlib import Path


def make_run_config(path: str, run_id: str, node: str) -> None:
    Path(path).write_text(f"run_id: {run_id}\nnode: {node}\n", encoding="utf-8")

