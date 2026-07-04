def select_top_checkpoints(checkpoints: list[str], top_k: int = 1) -> list[str]:
    return checkpoints[-top_k:]

