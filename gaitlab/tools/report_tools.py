from __future__ import annotations

from gaitlab.models import ExperimentPair


def render_experiment_report(
    pair: ExperimentPair,
    nodes: list[dict],
    training_jobs: list[dict],
    evaluations: dict[str, dict],
    comparison: dict,
    failure_analysis: dict,
    safety: dict,
    deployment_package: dict,
    robot_action_diff: str,
    audit_log: list[str],
) -> str:
    control_id = pair.control["run_id"]
    treatment_id = pair.treatment["run_id"]
    control = evaluations[control_id]
    treatment = evaluations[treatment_id]
    evidence_mode = _display_evidence_mode(treatment.get("evidence_mode", "deterministic_mock"))
    controlled_variables = [_display_controlled_variable(item) for item in pair.controlled_variables]
    metric_table = "\n".join(
        f"| {row['metric']} | {row['control']} | {row['treatment']} | {row['verdict']} |"
        for row in comparison["metric_rows"]
    )
    jobs = "\n".join(
        f"- {job['node']} / {job['run_id']}: {job['status']}, step {job['latest_step']:,}"
        for job in training_jobs
    )
    summary = (
        "Treatment meets the supported-test threshold but does not satisfy every "
        "unsupervised-hardware requirement. The public demo therefore blocks "
        "unassisted hardware testing and allows only a supported, low-speed "
        "private-lab test after the listed safety actions."
        if safety["safety_level"] == "supported_test_only"
        else "Treatment remains blocked until the listed safety actions and evidence gaps are resolved."
    )
    return f"""# Experiment Report: {pair.pair_id}

## Hypothesis

{pair.hypothesis}

## Experiment Pair

Control:
- Run: `{control_id}`
- Node: `{pair.control['node']}`
- Patch: none

Treatment:
- Run: `{treatment_id}`
- Node: `{pair.treatment['node']}`
- Patch: `{pair.treatment['patch']}`

Controlled variables:
{chr(10).join(f"- {item}" for item in controlled_variables)}

## Configured Lab Nodes

| Node | Role | Host | Status |
| --- | --- | --- | --- |
{chr(10).join(f"| {node['name']} | {node['role']} | {node.get('host', '')} | {node['status']} |" for node in nodes)}

## Training Jobs

{jobs}

## Research PC Evaluation

Evidence mode: `{evidence_mode}`

| Metric | Control | Treatment | Verdict |
| --- | ---: | ---: | --- |
{metric_table}

## Decision

- Comparison: `{comparison['decision']}`
- Recommendation: `{comparison['recommendation']}`
- Safety level: `{safety['safety_level']}`
- Unsupervised hardware allowed: `{safety['free_walking_allowed']}`

## Failure Analysis

Detected categories:
{chr(10).join(f"- {item}" for item in failure_analysis['failure_categories'])}

Likely causes:
{chr(10).join(f"- {item}" for item in failure_analysis['likely_causes'])}

Next experiment:
{chr(10).join(f"- {item}" for item in failure_analysis['next_experiment'])}

## Safety Gate

Reasons:
{chr(10).join(f"- {item}" for item in safety['reasons'])}

Required actions:
{chr(10).join(f"- {item}" for item in safety['required_actions'])}

## Safety-Gated Deployment Package

- Manifest: `{deployment_package['manifest_path']}`
- Type: `{deployment_package['package_type']}`
- Human approval required: `{deployment_package['human_approval_required']}`
- Unsupervised hardware allowed: `{deployment_package['free_walking_allowed']}`

{robot_action_diff}

## Safety Audit Log

{chr(10).join(f"- {item}" for item in audit_log)}

## Summary

{summary}
"""


def _display_evidence_mode(value: str) -> str:
    replacements = {
        "deterministic_mock": "controlled_simulation",
        "live_demo_mock": "controlled_live_lab",
        "mock": "controlled_simulation",
    }
    return replacements.get(value, value)


def _display_controlled_variable(value: str) -> str:
    return (
        value.replace("mock_public_demo", "controlled_simulation")
        .replace("deterministic_mock", "controlled_simulation")
        .replace("live_demo_mock", "controlled_live_lab")
    )
