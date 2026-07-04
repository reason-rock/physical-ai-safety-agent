"""Live lab control plane (UI-agnostic).

Wraps :mod:`gaitlab.lab.training` and a few SSH probes with caching that
is safe to call from a request loop (FastAPI, Streamlit, or a CLI). Each
function returns plain JSON-serialisable dicts.

State used to be stored in ``st.session_state`` when this module was
Streamlit-only. The state container is now :class:`JobStore` (defined in
``web.backend.job_store``) and is passed explicitly to the stateful
functions. A module-level default store is kept so existing callers
(Streamlit app until it is removed, CLI smoke scripts) keep working.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from gaitlab.lab.config import LiveLabConfig
from gaitlab.lab.training import LiveTrainingNodeAgent, _has_rsync

SSH_OPTS = [
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=8",
    "-o", "ServerAliveInterval=4",
    "-o", "ServerAliveCountMax=3",
]
LOG_ROOT = "~/IsaacLab/logs/rsl_rl/darwin_op_walk_free_direct"


# ---------------------------------------------------------------------------
# Store protocol + default in-memory store
# ---------------------------------------------------------------------------


class _StoreLike(Protocol):
    """Subset of :class:`web.backend.job_store.JobStore` we depend on."""

    jobs: dict[str, dict[str, Any]]
    node_cache: dict[str, Any]
    node_cache_ts: float
    last_error: str


@dataclass
class LiveControlState:
    """Default in-memory state container (used by non-web callers).

    The web backend uses :class:`web.backend.job_store.JobStore` instead.
    Both expose the same field names so the stateful functions below can
    be given either.
    """

    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    node_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    node_cache_ts: float = 0.0
    last_error: str = ""


# Module-level default store. Tests and the legacy Streamlit app read/write
# this directly; the FastAPI backend injects its own JobStore.
_DEFAULT_STORE = LiveControlState()


def get_default_store() -> LiveControlState:
    """Return the module-level default :class:`LiveControlState`.

    The Streamlit app (until removed) calls this. The FastAPI backend
    ignores it and uses ``web.backend.job_store.STORE`` instead.
    """

    return _DEFAULT_STORE


def load_state() -> LiveControlState:
    """Legacy alias for :func:`get_default_store`.

    Kept so any caller that imported the old name still works. The
    Streamlit dependency has been removed.
    """

    return _DEFAULT_STORE


def reset_state() -> None:
    """Reset the module-level default store."""

    global _DEFAULT_STORE
    _DEFAULT_STORE = LiveControlState()


# ---------------------------------------------------------------------------
# Read-only probes (safe to call on every rerun)
# ---------------------------------------------------------------------------


def _ssh(host: str, command: str, timeout: int = 10) -> tuple[int, str]:
    cmd = ["ssh", *SSH_OPTS, host, command]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s"
    except FileNotFoundError as exc:
        return 127, str(exc)


def snapshot_node(label: str, host: str, remote_repo_path: str = "~/physical-ai-lab") -> dict[str, Any]:
    """Probe one training node and return a JSON snapshot.

    This is a read-only operation: it never starts or stops anything on
    the remote host. Safe to call on every Streamlit rerun.
    """

    rc, out = _ssh(host, "echo OK", timeout=8)
    if rc != 0 or not out.strip().startswith("OK"):
        return {
            "label": label,
            "host": host,
            "reachable": False,
            "error": out.strip()[:200],
            "ts": time.time(),
        }

    snap: dict[str, Any] = {
        "label": label,
        "host": host,
        "reachable": True,
        "ts": time.time(),
    }
    rc, hostname = _ssh(host, "hostname", timeout=4)
    snap["hostname"] = hostname.strip() if rc == 0 else ""

    rc, gpu = _ssh(
        host,
        "nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu "
        "--format=csv,noheader",
        timeout=8,
    )
    if rc == 0 and gpu.strip():
        parts = [p.strip() for p in gpu.strip().split(",")]
        if len(parts) >= 4:
            snap["gpu"] = {
                "name": parts[0],
                "mem_used": parts[1],
                "mem_total": parts[2],
                "util": parts[3],
            }

    rc, tmux = _ssh(host, "tmux ls 2>/dev/null | awk -F: '{print $1}'", timeout=6)
    snap["tmux_sessions"] = (
        [s.strip() for s in tmux.splitlines() if s.strip()] if rc == 0 else []
    )

    # Detect training even when it is NOT running inside a tmux session
    # (e.g. launched from a bare shell, nohup, systemd, or another user).
    # We look for the actual training entrypoint processes. ``pgrep -af``
    # prints the full command line so we can also surface the pid + run
    # dir in the UI.
    rc, procs = _ssh(
        host,
        "pgrep -af 'train_darwin_op.py|isaaclab.sh.*train_darwin' | "
        "grep -v pgrep | grep -v snapshot_training_metrics",
        timeout=6,
    )
    pids: list[str] = []
    training_procs: list[dict[str, Any]] = []
    if rc == 0:
        for line in procs.splitlines():
            line = line.strip()
            if not line:
                continue
            pid, _, rest = line.partition(" ")
            pids.append(pid)
            proc_info: dict[str, Any] = {"pid": int(pid), "cmd": rest.strip()[:240]}
            # Parse useful fields from the command line so the UI can show
            # a human-readable task label instead of just a raw PID.
            proc_info.update(_parse_proc_cmd(rest))
            training_procs.append(proc_info)

    # For each detected PID, fetch its elapsed seconds via ``ps -o etimes``.
    # Lets the UI show "running for 2h 13m" without keeping its own timer.
    if pids:
        pid_csv = ",".join(pids)
        rc, etime_out = _ssh(
            host,
            f"ps -o pid=,etimes= -p {shlex.quote(pid_csv)} 2>/dev/null",
            timeout=6,
        )
        if rc == 0:
            etime_by_pid: dict[int, int] = {}
            for line in etime_out.splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2 and parts[0].isdigit():
                    try:
                        etime_by_pid[int(parts[0])] = int(parts[1])
                    except ValueError:
                        pass
            for proc in training_procs:
                proc["elapsed_sec"] = etime_by_pid.get(proc["pid"], 0)
    snap["training_procs"] = training_procs

    # ``busy`` is true when EITHER a tmux session OR a live training
    # process is present. The tmux-only check used to miss jobs started
    # outside tmux (nohup, bare shells, other users).
    snap["busy"] = bool(snap["tmux_sessions"]) or bool(training_procs)

    if not snap["busy"]:
        snap["latest_run_dir"] = ""
        snap["scalars"] = {}
        return snap

    rc, latest = _ssh(host, f"ls -1td {LOG_ROOT}/*/ 2>/dev/null | head -1", timeout=8)
    snap["latest_run_dir"] = latest.strip().rstrip("/") if rc == 0 else ""

    # Latest iteration/reward via snapshot_training_metrics.py.
    if snap["latest_run_dir"]:
        repo = shlex.quote(remote_repo_path or "~/physical-ai-lab")
        rc, tb = _ssh(
            host,
            f"cd {repo} && "
            "(bash scripts/pipeline/snapshot_training_metrics.sh "
            f"{shlex.quote(snap['latest_run_dir'])} 2>/dev/null || "
            "rl/.venv_isaaclab/bin/python scripts/pipeline/snapshot_training_metrics.py "
            f"{shlex.quote(snap['latest_run_dir'])} 2>/dev/null || true)",
            timeout=12,
        )
        snap["scalars"] = _parse_scalars(tb) if rc == 0 else {}

    return snap


def snapshot_both(config: LiveLabConfig) -> dict[str, dict[str, Any]]:
    """Convenience: snapshot both GPU0 and GPU1 in one call."""

    gpu0_host = (
        config.train_host_fallbacks[0]
        if config.train_host_fallbacks
        else config.gpu0_host
    )
    gpu1_host = config.train_host_primary or config.gpu1_host
    with ThreadPoolExecutor(max_workers=2) as pool:
        gpu0 = pool.submit(snapshot_node, "GPU0", gpu0_host, config.remote_repo_path)
        gpu1 = pool.submit(snapshot_node, "GPU1", gpu1_host, config.remote_repo_path)
        return {
            "gpu0": gpu0.result(),
            "gpu1": gpu1.result(),
        }


def _parse_proc_cmd(cmd: str) -> dict[str, Any]:
    """Extract human-readable fields from a training process command line.

    Returns keys like ``task_name``, ``num_envs``, ``max_iterations``,
    ``seed``, ``resume_from`` so the UI can show what's running without
    the user reading the raw command.
    """

    import re

    info: dict[str, Any] = {}
    # --task Isaac-Darwin-OP-Walk-Free-Direct-v0 → "Walk-Free-Direct"
    m = re.search(r"--task\s+\S*Darwin-OP-(\S+?)-v\d", cmd)
    if m:
        raw = m.group(1)
        # "Walk-Free-Direct" → "free_direct" (last two words, snake_case)
        parts = raw.split("-")
        short = "_".join(p.lower() for p in parts[-2:]) if len(parts) >= 2 else raw.lower()
        info["task_name"] = short
    else:
        # fallback: any --task value
        m2 = re.search(r"--task\s+(\S+)", cmd)
        info["task_name"] = m2.group(1).split("-")[-1].lower() if m2 else "unknown"

    m = re.search(r"--num_envs\s+(\d+)", cmd)
    if m:
        info["num_envs"] = int(m.group(1))

    m = re.search(r"--max_iterations\s+(\d+)", cmd)
    if m:
        info["max_iterations"] = int(m.group(1))

    m = re.search(r"--seed\s+(\d+)", cmd)
    if m:
        info["seed"] = int(m.group(1))

    m = re.search(r"--resume_checkpoint\s+(\S+)", cmd)
    if m:
        # Extract just the run dir + model name, not the full path.
        path_parts = m.group(1).split("/")
        info["resume_from"] = "/".join(path_parts[-2:]) if len(path_parts) >= 2 else m.group(1)

    # Build a short label like "free_direct · 16384 envs · iter 3000 · resume"
    label_parts = [info.get("task_name", "?")]
    if info.get("num_envs"):
        label_parts.append(f"{info['num_envs']:,} envs")
    if info.get("max_iterations"):
        label_parts.append(f"iter {info['max_iterations']:,}")
    if info.get("resume_from"):
        label_parts.append("resume")
    info["label"] = " · ".join(label_parts)

    return info


def _parse_scalars(stdout: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        label, step_str, value_str = parts
        try:
            step = int(step_str)
            value = float(value_str)
        except ValueError:
            continue
        if label == "reward":
            out["iteration"] = step
            out["reward"] = round(value, 2)
        elif label == "ep_len":
            out["ep_len"] = round(value, 1)
    return out


# ---------------------------------------------------------------------------
# Mutating actions (return immediately; UI polls for status)
# ---------------------------------------------------------------------------


def submit_training(
    config: LiveLabConfig,
    node: str,
    run_id: str,
    parent_stage: str,
    patch: dict[str, Any] | None = None,
    num_envs: int = 1024,
    max_iterations: int = 5000,
    wall_clock_cap: str = "5m",
    seed: int = 0,
) -> dict[str, Any]:
    """Submit one training job to ``node`` and record it in session state.

    Returns the job summary. The UI then polls :func:`refresh_job_status`
    on subsequent reruns to follow progress.
    """

    state = load_state()
    agent = LiveTrainingNodeAgent(node_name=node, config=config, data_mode="live_lab")
    run_config = {
        "run_id": run_id,
        "node": node,
        "base_config": f"scripts/stages/{parent_stage}.env",
        "patch": patch or {},
        "paired_seeds": [seed],
        "config_path": f"demo_data/configs/{run_id}.yaml",
        "parent_stage": parent_stage,
        "num_envs": num_envs,
        "max_iterations": max_iterations,
        "wall_clock_cap": wall_clock_cap,
        "seed": seed,
        "device": "cuda:0",
    }
    summary = agent.submit(run_config)
    summary["node"] = node
    summary["run_id"] = run_id
    summary["submitted_at"] = time.time()
    summary["max_iterations"] = max_iterations
    summary["status_history"] = [(time.time(), "submitted", summary.copy())]
    state.jobs[summary["job_id"]] = summary
    return summary


def refresh_job_status(config: LiveLabConfig, job_id: str) -> dict[str, Any]:
    """Poll the latest status of a tracked job and update its history."""

    state = load_state()
    job = state.jobs.get(job_id)
    if not job:
        return {"error": f"unknown job_id {job_id}"}
    agent = LiveTrainingNodeAgent(node_name=job["node"], config=config, data_mode="live_lab")
    try:
        status = agent.status(job_id)
    except Exception as exc:
        status = {"status": "error", "error": str(exc)[:200]}
    # Update fields in place so the UI sees them on the next rerun.
    for key in ("status", "progress", "latest_step", "latest_reward", "fall_rate", "estimated_remaining_min"):
        if key in status:
            job[key] = status[key]
    history = job.setdefault("status_history", [])
    history.append((time.time(), status.get("status", "?"), status.copy()))
    # Cap history to last 200 samples so session_state stays small.
    if len(history) > 200:
        job["status_history"] = history[-200:]
    return status


def kill_job(config: LiveLabConfig, job_id: str) -> dict[str, Any]:
    """Kill a tracked job's tmux session on its training node."""

    state = load_state()
    job = state.jobs.get(job_id)
    if not job:
        return {"error": f"unknown job_id {job_id}"}
    session = job.get("tmux_session", "")
    if not session:
        return {"error": "no tmux_session recorded for this job"}
    node = job["node"]
    host = (
        config.train_host_fallbacks[0]
        if node == "GPU0" and config.train_host_fallbacks
        else config.train_host_primary
    )
    rc, out = _ssh(host, f"tmux kill-session -t {shlex.quote(session)} 2>&1; echo RC=$?", timeout=10)
    job["status"] = "killed_by_operator" if rc == 0 else "kill_failed"
    return {"rc": rc, "out": out, "job_id": job_id, "status": job["status"]}


def kill_session_by_name(host: str, session: str) -> dict[str, Any]:
    """Kill an arbitrary tmux session on a host (not necessarily tracked)."""

    rc, out = _ssh(host, f"tmux kill-session -t {shlex.quote(session)} 2>&1; echo RC=$?", timeout=10)
    return {"rc": rc, "out": out, "host": host, "session": session}


def collect_job_artifacts(config: LiveLabConfig, job_id: str) -> dict[str, Any]:
    """Trigger artifact collection (rsync + TB conversion) for a job."""

    state = load_state()
    job = state.jobs.get(job_id)
    if not job:
        return {"error": f"unknown job_id {job_id}"}
    agent = LiveTrainingNodeAgent(node_name=job["node"], config=config, data_mode="live_lab")
    try:
        result = agent.collect(job["run_id"])
        job["collected"] = True
        job["collect_result"] = result
        return result
    except Exception as exc:
        return {"error": str(exc)[:400]}
