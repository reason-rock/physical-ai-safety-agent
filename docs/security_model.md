# Security Model

## Threats

- Accidental real hardware command execution.
- Leaking private SSH credentials or lab paths.
- Treating simulation-only evidence as permission for physical testing.
- Treating replay-only evidence as permission for unsupervised hardware testing.
- Uncontrolled tool calls that modify remote machines.
- Unsafe hardware-readiness claims from incomplete metrics.

## Public Demo Controls

- GPU0, GPU1, the evaluation workstation, and the hardware target are controlled demo nodes.
- No SSH, SCP, rsync, or socket client exists in the public demo.
- `.env` is ignored and `.env.example` contains no secrets.
- Safety Gate is deterministic and blocks unsupervised hardware testing unless strict thresholds pass.
- Deployment output is a mock manifest, not an executable hardware package.
- Robot Action Diff explains the proposed hardware-facing action before any private lab step.
- Sanitized real replay data contains only aggregate CSV/JSON evidence.
- Raw lab CSVs, hostnames, private paths, credentials, and checkpoints are excluded.
- The optional official MCP server and ADK adapter call the same safe local tools.

## Private Lab Extension Requirements

Before replacing mock tools with real adapters:

1. Add human approval before any hardware-facing action.
2. Log every tool call and artifact path.
3. Scope credentials to one lab environment.
4. Keep unsupervised hardware testing blocked unless all safety evidence is present.
5. Run static balance and emergency-stop dry-run checks first.
