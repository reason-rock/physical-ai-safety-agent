---
name: parallel-training-orchestration
description: Submit and track matched GPU0 and GPU1 physical-AI training runs.
---

# Parallel Training Orchestration

Use this skill when a Physical AI Safety Agent experiment pair needs training jobs.

## Public Demo Rule

GPU0 and GPU1 are mock nodes. No SSH, SCP, rsync, or remote execution is
allowed in the public repository.

## Steps

1. Confirm GPU0 and GPU1 are available.
2. Submit treatment to GPU0.
3. Submit control to GPU1.
4. Track progress with matched budgets.
5. Collect logs, mock checkpoints, and metadata.
