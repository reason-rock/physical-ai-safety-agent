---
name: experiment-pair-design
description: Design controlled baseline/treatment physical-AI experiment pairs for Physical AI Safety Agent.
---

# Experiment Pair Design

Use this skill when the user asks to compare a baseline physical-AI policy
against a treatment.

## Rules

1. Keep the control config unchanged.
2. Put only the declared change in the treatment patch.
3. Preserve hardware model, simulator, target velocity, timestep, total steps, and seeds.
4. Warn if more than three treatment variables change at once.
5. Write a falsifiable hypothesis before training.

## Output

- Pair ID
- Control run
- Treatment run
- Controlled variables
- Treatment patch
- Hypothesis
