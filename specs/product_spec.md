# Product Spec

## Product

Physical AI Safety Agent is a safety-first experiment copilot for physical-AI teams. The
first demo domain is humanoid walking, but the product value is broader:
helping humans make controlled, evidence-backed decisions before an AI policy
moves from simulation toward hardware.

## User

The primary user is a small physical-AI team: a researcher, student, or human
safety operator who runs repeated policy experiments and needs fair comparison
before any hardware-facing test.

## Job To Be Done

When a physical-AI policy fails or partially improves, the user needs to run a
matched baseline and treatment experiment, evaluate both under identical
metrics, and decide whether supported hardware testing is justified.

## Non-Goals

- Training a real RL policy inside the public demo.
- Sending commands to real hardware.
- Managing private SSH credentials.
- Claiming that mocked or replay metrics prove hardware readiness.

## Success Criteria

- A natural-language request becomes a controlled experiment pair.
- Control and treatment mock jobs run under matched variables.
- Researcher PC evaluation produces comparable metrics.
- Safety Gate blocks unsafe hardware claims.
- The report explains improvements, regressions, and next steps.
