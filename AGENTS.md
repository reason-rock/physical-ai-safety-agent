# GaitLab Agent Project Instructions

- Keep public demo mode safe by default.
- Do not add real SSH, robot, or motor-command execution without a separate lab adapter.
- Treat GPU0, GPU1, ResearcherPC, and Robot as mocked nodes in this repository.
- Preserve controlled A/B experiment semantics: control keeps baseline, treatment changes only the declared patch.
- Safety gate decisions must be deterministic and explain their reasons.
- Evaluation and CLI demo must run without API keys.
- Never commit `.env` or `.env.*` files except `.env.example`.
- Do not print secret values from `.env`; use masked summaries only.
