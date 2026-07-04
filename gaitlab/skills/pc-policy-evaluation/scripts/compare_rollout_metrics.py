def velocity_ratio(metrics: dict) -> float:
    return metrics["avg_velocity"] / max(metrics["target_velocity"], 1e-9)

