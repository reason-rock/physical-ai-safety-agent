# Safety Gate Spec

Unsupervised hardware candidate requires:

- All rollouts fall-free.
- Joint limit max ratio at or below 0.85 in standard mode.
- Torso pitch RMS at or below 0.20 rad.
- Action jerk at or below 0.30.
- Emergency-stop dry-run evidence present.

Supported test only requires:

- At most one failed rollout.
- Joint limit max ratio at or below 0.95 in standard mode.

Blocked:

- More than one failed rollout.
- Joint limit max ratio above supported-test threshold.
- Missing critical metrics.

Public demo guarantee:

- No real hardware command is available from this repository.
