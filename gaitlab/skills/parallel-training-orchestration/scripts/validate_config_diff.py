def validate_config_diff(patch: dict) -> list[str]:
    warnings = []
    if len(patch) > 3:
        warnings.append("More than three treatment variables changed.")
    return warnings

