# Capstone Requirements Mapping

| Requirement concept | Physical AI Safety Agent evidence |
| --- | --- |
| Real-world problem | Physical-AI teams need safer, more reproducible decisions before moving policies from simulation toward hardware. Humanoid gait RL is the concrete demo domain, not the whole value proposition. |
| Agent system | `gaitlab/orchestrator.py` coordinates specialist agents in `gaitlab/agents`. |
| Multi-agent design | Design, treatment training, control training, Evaluation, Failure Analysis, Safety, and Report agents. |
| Tools / MCP | `gaitlab/tools`, `gaitlab/mcp/server.py`, and optional official FastMCP server `gaitlab/mcp/official_server.py`. |
| Google ADK | Optional ADK `root_agent` wrapper in `gaitlab/adk_app/agent.py`. |
| Agent Skills | `gaitlab/skills/*/SKILL.md` contains reusable workflow instructions. |
| Real replay evidence | `demo_data/real_replay` contains sanitized aggregate robot-log CSV/JSON; `scripts/build_real_replay.py` documents the redaction process. |
| Security | `docs/security_model.md`, Safety Gate, mock hardware boundary, no secrets, no SSH, sanitized replay only, human approval before private lab actions. |
| Evaluation | `evals/run_evals.py`, `evals/agent_eval_cases.json`, `evals/safety_gate_cases.json`, replay workflow test. |
| Deployability | FastAPI + Next.js dashboard, CLI demo, static demo, optional MCP server, optional ADK adapter, reproducible `.venv` setup. |
| Documentation | `README.md`, `SUBMISSION.md`, specs, public safety notes, and evaluation evidence. |
