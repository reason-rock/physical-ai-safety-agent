TOOL_SCHEMAS = {
    "list_nodes": {
        "description": "List public-demo lab nodes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    "create_experiment_pair": {
        "description": "Create a controlled baseline/treatment experiment pair.",
        "input_schema": {
            "type": "object",
            "required": ["baseline_config", "treatment_patch", "control_node", "treatment_node", "paired_seeds"],
        },
    },
    "submit_training_job": {
        "description": "Submit a mock or sanitized replay training job to GPU0 or GPU1.",
        "input_schema": {"type": "object", "required": ["node", "run_id", "config_path"]},
    },
    "evaluate_policy_on_pc": {
        "description": "Evaluate a mock or sanitized replay checkpoint on the Researcher PC.",
        "input_schema": {"type": "object", "required": ["checkpoint_path", "eval_config", "num_rollouts"]},
    },
    "run_robot_safety_gate": {
        "description": "Classify hardware-test readiness from evaluation metrics.",
        "input_schema": {"type": "object", "required": ["policy_id", "metrics"]},
    },
    "create_deployment_package": {
        "description": "Create a mock deployment manifest for an approved safety level.",
        "input_schema": {"type": "object", "required": ["policy_id", "safety_level", "free_walking_allowed"]},
    },
}
