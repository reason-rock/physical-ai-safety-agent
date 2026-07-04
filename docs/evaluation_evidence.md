# Evaluation Evidence

Run:

```powershell
.\.venv\Scripts\python.exe scripts\verify.py
```

Expected checks:

- CLI demo renders an experiment report.
- Real replay workflow renders `sanitized_real_replay` and `supported_test_only`.
- Agent eval cases pass:
  - `forward_fall_pair`
  - `frozen_gait_pair`
- Safety eval cases pass:
  - `supported_only`
  - `blocked`
  - `free_walk_candidate`
- Python compile check passes.
- Lightweight MCP dispatcher lists tools.
- Optional official MCP and ADK adapter modules import without requiring secrets.
- Unit tests pass through `python -m unittest discover -s tests`.
- FastAPI backend imports and exposes `/api/health`, `/api/workflow`,
  `/sse/lab`, and `/api/lab/jobs`.
- Public-safe ZIP is generated without `.env`, `.venv`, private lab adapter,
  private history DB, or live smoke artifacts.
- Public-safe ZIP is scanned for private path/IP/key patterns.
- Public-safe ZIP is extracted into a temporary directory and smoke-tested.
- Public-safe ZIP unit tests pass from the extracted copy.
- Static demo renders treatment/control training rigs, Safety Gate, and Robot Action Diff.

The latest generated eval result file is `evals/results.md`.

Latest local verification:

```text
PASS cli demo
PASS real replay workflow
PASS agent evals
PASS unit tests
PASS compile
PASS mcp dispatcher
PASS optional integration adapters
PASS fastapi backend import
PASS submission zip
PASS public zip private-pattern scan
PASS public zip smoke
PASS public zip unit tests
All verification checks passed.
```
