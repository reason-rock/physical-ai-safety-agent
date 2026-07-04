---
name: sim-to-real-safety-gate
description: Decide whether a physical-AI policy can move from simulation toward hardware testing.
---

# Sim-To-Real Safety Gate

Use this skill before any hardware-facing action.

## Public Demo Boundary

No real hardware command is available. The skill returns a decision and Robot
Action Diff only.

## Levels

- blocked
- supported_test_only
- candidate_for_free_walking (internal label for an unsupervised-hardware review candidate)

## Required Evidence

- rollout metrics
- joint-limit ratio
- torso pitch RMS
- action jerk
- emergency-stop dry-run flag
