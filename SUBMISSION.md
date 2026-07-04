# Physical AI Safety Agent Submission Pack

## Kaggle Project

Title:
Physical AI Safety Agent: Safety-First Experiment Copilot for Physical-AI Teams

One-line pitch:
Physical AI Safety Agent helps physical-AI teams turn messy policy experiments into
controlled comparisons, matched evidence, conservative safety gates, and
human-reviewable hardware decisions.

Track:
Freestyle

## Required Links

- Project README: `README.md`
- Security model: `docs/security_model.md`
- Evaluation evidence: `docs/evaluation_evidence.md`
- Capstone mapping: `docs/capstone_requirements_mapping.md`
- Sanitized real replay manifest: `demo_data/real_replay/real_replay_manifest.json`
- Official MCP wrapper: `gaitlab/mcp/official_server.py`
- Google ADK adapter: `gaitlab/adk_app/agent.py`
- Cover image: `docs/cover-gpu0-gpu1.svg`
- Architecture image: `docs/architecture-gpu0-gpu1.svg`
- Static demo: `site/index.html`

## Local Verification

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\python.exe run_demo.py --data-mode real_replay
.\.venv\Scripts\python.exe scripts\build_submission_zip.py
.\.venv\Scripts\python.exe -m web.backend.run
cd web\frontend
npm install
npm run dev
start .\site\index.html
```

Expected result:

- CLI demo passes.
- Sanitized real replay workflow passes.
- Agent eval cases pass.
- Safety gate eval cases pass.
- Lightweight MCP dispatcher responds.
- Optional official MCP and ADK adapter modules import.
- Public-safe zip can be built without `.env` or `.venv`.
- Public-safe zip is smoke-tested after extraction.
- Unit tests pass.
- FastAPI backend opens on `http://localhost:8000`.
- Next.js dashboard opens on `http://localhost:3000`.
- Static demo opens without a server.

## Submission Narrative

Physical AI Safety Agent is safe-by-default. The public version never connects to GPU0,
GPU1, or real hardware. Instead, it exposes a safe tool boundary with
deterministic mock nodes and sanitized real replay evidence, then demonstrates
the full agentic workflow: experiment design, parallel training, matched
evaluation, failure analysis, safety gating, report generation, and a mock
deployment manifest. The humanoid walking scenario is the demo domain; the core
value is safer, more reproducible physical-AI decision support. Optional
official MCP and ADK adapters wrap the same safe tools for course-concept
evidence.

## Before Publishing

Delete or exclude `.env`. It contains private lab host/path configuration.
Keep `.env.example` in the submission.
