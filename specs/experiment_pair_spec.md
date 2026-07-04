# Experiment Pair Spec

Rules:

1. Control keeps the baseline config unchanged.
2. Treatment includes only the declared patch.
3. Both runs share hardware model, simulator, target velocity, total steps, timestep, and paired seeds.
4. The treatment and control training rigs run matched jobs.
5. Researcher PC evaluates both policies with the same config.
6. Hardware target receives only safety decisions and mock deployment manifests in public demo mode.
