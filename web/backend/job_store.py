"""Thread-safe in-memory store for live lab jobs and node snapshots.

Replaces ``gaitlab.lab.live_control.LiveControlState`` + Streamlit
``st.session_state``. The backend creates a single process-wide instance
and the lab router / SSE loop read and mutate it through the public methods.

The store is intentionally simple: a single ``threading.Lock`` guards all
mutations. Live lab work is low-frequency (one job submit every few
minutes, snapshots every 5 seconds), so coarse locking is plenty.
"""

from __future__ import annotations

import threading
import time
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gaitlab.lab.config import LiveLabConfig

DEMO_SECONDS_PER_ITERATION = 6.0
DEMO_GPU_LOAD_SECONDS = 3.8
DEMO_GPU_UNLOAD_SECONDS = 8.0
DEMO_GPU0_STAGGER_SECONDS = 0.2
DEMO_GPU1_STAGGER_SECONDS = 1.1


@dataclass
class _Store:
    """Internal mutable state. Always accessed under ``JobStore._lock``."""

    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    node_cache: dict[str, Any] = field(default_factory=dict)
    node_cache_ts: float = 0.0
    last_error: str = ""


class JobStore:
    """Process-wide store for tracked live lab jobs.

    Methods mirror the public functions in
    :mod:`gaitlab.lab.live_control` but take an explicit ``LiveLabConfig``
    and never touch Streamlit. The store is safe to call from request
    handlers and the SSE background loop concurrently.
    """

    def __init__(self) -> None:
        self._state = _Store()
        self._lock = threading.Lock()
        self._snapshot_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Snapshot helpers (read-only SSH probes)
    # ------------------------------------------------------------------

    def snapshot_both(self, config: LiveLabConfig) -> dict[str, dict[str, Any]]:
        """Probe GPU0 + GPU1 and cache, without stacking SSH probes."""

        if getattr(config, "live_demo_mock", False):
            snap = self._demo_snapshot_both(config)
            with self._lock:
                self._state.node_cache = snap
                self._state.node_cache_ts = time.time()
            return snap

        # Imported here so the module loads cleanly in tests that stub
        # the lab package.
        from gaitlab.lab.live_control import snapshot_both

        if not self._snapshot_lock.acquire(blocking=False):
            cache, _ts = self.get_node_cache()
            return cache
        try:
            snap = snapshot_both(config)
            with self._lock:
                self._state.node_cache = snap
                self._state.node_cache_ts = time.time()
            return snap
        finally:
            self._snapshot_lock.release()

    def get_node_cache(self) -> tuple[dict[str, Any], float]:
        with self._lock:
            return dict(self._state.node_cache), self._state.node_cache_ts

    # ------------------------------------------------------------------
    # Job lifecycle
    # ------------------------------------------------------------------

    def submit(
        self,
        config: LiveLabConfig,
        *,
        node: str,
        run_id: str,
        parent_stage: str,
        patch: dict[str, Any] | None = None,
        num_envs: int = 1024,
        max_iterations: int = 5000,
        wall_clock_cap: str = "5m",
        seed: int = 0,
    ) -> dict[str, Any]:
        """Submit a training job to a Cell and track it."""

        if getattr(config, "live_demo_mock", False):
            return self._demo_submit(
                config,
                node=node,
                run_id=run_id,
                parent_stage=parent_stage,
                patch=patch,
                num_envs=num_envs,
                max_iterations=max_iterations,
                wall_clock_cap=wall_clock_cap,
                seed=seed,
            )

        from gaitlab.lab.training import LiveTrainingNodeAgent

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
        summary["status_history"] = [(time.time(), "submitted", dict(summary))]
        with self._lock:
            self._state.jobs[summary["job_id"]] = summary
        return dict(summary)

    def refresh_status(self, config: LiveLabConfig, job_id: str) -> dict[str, Any]:
        """Poll the latest status of one tracked job."""

        with self._lock:
            job = self._state.jobs.get(job_id)
        if not job:
            return {"error": f"unknown job_id {job_id}"}
        if getattr(config, "live_demo_mock", False):
            return self._demo_refresh_status(job_id)
        from gaitlab.lab.training import LiveTrainingNodeAgent

        agent = LiveTrainingNodeAgent(node_name=job["node"], config=config, data_mode="live_lab")
        try:
            status = agent.status(job_id)
        except Exception as exc:  # noqa: BLE001 - surface as status error
            status = self._fallback_status_from_cache(job, str(exc)[:200])
        with self._lock:
            for key in (
                "status",
                "progress",
                "latest_step",
                "latest_reward",
                "fall_rate",
                "estimated_remaining_min",
            ):
                if key in status:
                    job[key] = status[key]
            history = job.setdefault("status_history", [])
            history.append((time.time(), status.get("status", "?"), dict(status)))
            if len(history) > 200:
                job["status_history"] = history[-200:]
        return status

    def refresh_all_active(self, config: LiveLabConfig) -> list[dict[str, Any]]:
        """Refresh every job whose status looks active. Used by the SSE loop."""

        with self._lock:
            active_ids = [
                job_id
                for job_id, job in self._state.jobs.items()
                if job.get("status")
                in ("submitted_live", "running", "submitted", "submitted_demo", "starting", "unloading")
            ]
        results = []
        for job_id in active_ids:
            results.append(self.refresh_status(config, job_id))
        return results

    def kill(self, config: LiveLabConfig, job_id: str) -> dict[str, Any]:
        """Kill a tracked job's tmux session."""

        with self._lock:
            job = self._state.jobs.get(job_id)
        if not job:
            return {"error": f"unknown job_id {job_id}"}
        if getattr(config, "live_demo_mock", False):
            with self._lock:
                job["status"] = "killed_by_operator"
                job["progress"] = min(float(job.get("progress", 0.0)), 0.99)
                result = {
                    "rc": 0,
                    "status": "killed_by_operator",
                    "out": "demo mode: no remote tmux session was touched",
                    "session": job.get("tmux_session", ""),
                }
                history = job.setdefault("status_history", [])
                history.append((time.time(), job["status"], dict(result)))
            return result
        session = job.get("tmux_session", "")
        host = self._resolve_host(config, job["node"])
        result = _ssh_kill_session(host, session)
        with self._lock:
            job["status"] = result.get(
                "status",
                "killed_by_operator" if result.get("rc") == 0 else "kill_failed",
            )
            history = job.setdefault("status_history", [])
            history.append((time.time(), job["status"], dict(result)))
            if len(history) > 200:
                job["status_history"] = history[-200:]
        return result

    def collect(self, config: LiveLabConfig, job_id: str) -> dict[str, Any]:
        """Trigger artifact collection for a tracked job."""

        with self._lock:
            job = self._state.jobs.get(job_id)
        if not job:
            return {"error": f"unknown job_id {job_id}"}
        if getattr(config, "live_demo_mock", False):
            result = {
                "status": "collected",
                "run_id": job.get("run_id", ""),
                "artifact_dir": f"artifacts/live/{job.get('run_id', 'run')}",
                "note": "training artifacts indexed for evaluation",
            }
            with self._lock:
                job["collected"] = True
                job["collect_result"] = result
            return {
                **result,
            }
        from gaitlab.lab.training import LiveTrainingNodeAgent

        agent = LiveTrainingNodeAgent(node_name=job["node"], config=config, data_mode="live_lab")
        try:
            result = agent.collect(job["run_id"])
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)[:400]}
        with self._lock:
            job["collected"] = True
            job["collect_result"] = result
        return result

    # ------------------------------------------------------------------
    # Read-only views
    # ------------------------------------------------------------------

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(job) for job in self._state.jobs.values()]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._state.jobs.get(job_id)
            return dict(job) if job else None

    def reset(self) -> None:
        with self._lock:
            self._state = _Store()

    @staticmethod
    def _resolve_host(config: LiveLabConfig, node: str) -> str:
        if node == "GPU0":
            return config.train_host_fallbacks[0] if config.train_host_fallbacks else config.gpu0_host
        if node == "GPU1":
            return config.train_host_primary or config.gpu1_host
        raise ValueError(f"unknown training node: {node}")

    def _demo_submit(
        self,
        config: LiveLabConfig,
        *,
        node: str,
        run_id: str,
        parent_stage: str,
        patch: dict[str, Any] | None,
        num_envs: int,
        max_iterations: int,
        wall_clock_cap: str,
        seed: int,
    ) -> dict[str, Any]:
        now = time.time()
        session = f"gaitlab_{run_id}"
        role = "control" if run_id.startswith("control") else "treatment"
        summary = {
            "job_id": f"{node.lower()}_demo_{int(now)}_{len(self._state.jobs) + 1}",
            "node": node,
            "run_id": run_id,
            "config_path": f"demo_data/configs/{run_id}.yaml",
            "status": "running",
            "progress": 0.0,
            "latest_step": 0,
            "estimated_remaining_min": max(1, int(max_iterations * DEMO_SECONDS_PER_ITERATION / 60)),
            "latest_reward": 812.4 if role == "treatment" else 774.2,
            "fall_rate": 0.02 if role == "treatment" else 0.04,
            "evidence_mode": "live_demo_mock",
            "stage_name": f"gaitlab_{run_id}",
            "tmux_session": session,
            "host_masked": "demo-training-pc",
            "submitted_at": now,
            "max_iterations": max_iterations,
            "demo_role": role,
            "parent_stage": parent_stage,
            "patch": patch or {},
            "num_envs": num_envs,
            "wall_clock_cap": wall_clock_cap,
            "seed": seed,
        }
        summary["status_history"] = [(now, "submitted_demo", dict(summary))]
        with self._lock:
            self._state.jobs[summary["job_id"]] = summary
        return dict(summary)

    def _demo_refresh_status(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._state.jobs.get(job_id)
            if not job:
                return {"error": f"unknown job_id {job_id}"}
            status = self._demo_status_for_job(job)
            for key, value in status.items():
                if key in {
                    "status",
                    "progress",
                    "latest_step",
                    "latest_reward",
                    "fall_rate",
                    "estimated_remaining_min",
                }:
                    job[key] = value
            history = job.setdefault("status_history", [])
            history.append((time.time(), status.get("status", "?"), dict(status)))
            if len(history) > 200:
                job["status_history"] = history[-200:]
            return status

    @staticmethod
    def _demo_node_stagger(job_or_label: dict[str, Any] | str) -> float:
        label = job_or_label if isinstance(job_or_label, str) else str(job_or_label.get("node", ""))
        if label == "GPU1":
            return DEMO_GPU1_STAGGER_SECONDS
        return DEMO_GPU0_STAGGER_SECONDS

    def _demo_timing_for_job(self, job: dict[str, Any]) -> tuple[float, float, float, int]:
        load_delay = DEMO_GPU_LOAD_SECONDS + self._demo_node_stagger(job)
        unload_delay = DEMO_GPU_UNLOAD_SECONDS + self._demo_node_stagger(job) * 0.5
        max_iterations = max(1, int(job.get("max_iterations") or 5000))
        train_duration = max_iterations * DEMO_SECONDS_PER_ITERATION
        complete_at = load_delay + train_duration
        return load_delay, unload_delay, complete_at, max_iterations

    def _demo_status_for_job(self, job: dict[str, Any]) -> dict[str, Any]:
        submitted_at = float(job.get("submitted_at") or time.time())
        elapsed = max(0.0, time.time() - submitted_at)
        load_delay, unload_delay, complete_at, max_iterations = self._demo_timing_for_job(job)
        training_elapsed = max(0.0, elapsed - load_delay)
        latest_step = min(max_iterations, int(training_elapsed / DEMO_SECONDS_PER_ITERATION))
        progress = min(1.0, latest_step / max_iterations)
        treatment = job.get("demo_role") == "treatment" or str(job.get("run_id", "")).startswith("treatment")
        reward_base = 812.0 if treatment else 774.0
        reward_gain = 118.0 if treatment else 82.0
        fall_base = 0.018 if treatment else 0.042
        remaining_iterations = max(0, max_iterations - latest_step)
        return {
            "job_id": job.get("job_id"),
            "node": job.get("node"),
            "run_id": job.get("run_id"),
            "status": self._demo_job_status(elapsed, load_delay, complete_at, unload_delay, latest_step, max_iterations),
            "progress": round(progress, 4),
            "latest_step": latest_step,
            "latest_reward": round(reward_base + reward_gain * progress, 2),
            "fall_rate": round(max(0.0, fall_base * (1.0 - progress * 0.65)), 4),
            "estimated_remaining_min": int(remaining_iterations * DEMO_SECONDS_PER_ITERATION / 60),
            "tmux_session": job.get("tmux_session", ""),
            "evidence_mode": "live_demo_mock",
        }

    @staticmethod
    def _demo_job_status(
        elapsed: float,
        load_delay: float,
        complete_at: float,
        unload_delay: float,
        latest_step: int,
        max_iterations: int,
    ) -> str:
        if elapsed < load_delay:
            return "starting"
        if latest_step < max_iterations:
            return "running"
        if elapsed < complete_at + unload_delay:
            return "unloading"
        return "completed"

    def _demo_snapshot_both(self, config: LiveLabConfig) -> dict[str, dict[str, Any]]:
        with self._lock:
            jobs = [dict(job) for job in self._state.jobs.values()]
        def active_for(node: str) -> dict[str, Any] | None:
            node_jobs = [job for job in jobs if job.get("node") == node]
            for job in sorted(node_jobs, key=lambda item: float(item.get("submitted_at") or 0), reverse=True):
                status = self._demo_status_for_job(job)
                if status["status"] != "completed" and str(job.get("status")) not in {"killed_by_operator", "stopped"}:
                    return job
            return None

        active = {
            "GPU0": active_for("GPU0"),
            "GPU1": active_for("GPU1"),
        }
        return {
            "gpu0": self._demo_node_snapshot("GPU0", config.gpu0_host or "demo-gpu0", active["GPU0"]),
            "gpu1": self._demo_node_snapshot("GPU1", config.gpu1_host or "demo-gpu1", active["GPU1"]),
        }

    def _demo_node_snapshot(self, label: str, host: str, job: dict[str, Any] | None) -> dict[str, Any]:
        busy = job is not None
        if job:
            status = self._demo_status_for_job(job)
            if status["status"] == "completed":
                job = None
                busy = False
        if job:
            elapsed = max(0.0, time.time() - float(job.get("submitted_at") or time.time()))
            load_delay, unload_delay, complete_at, _max_iterations = self._demo_timing_for_job(job)
            phase = 0.0 if label == "GPU0" else 1.7
            warming_up = elapsed < load_delay
            unloading = status["status"] == "unloading"
            mem_base = 22184 if label == "GPU0" else 21472
            mem_wave = int(
                560 * math.sin(elapsed / 7.0 + phase)
                + 230 * math.sin(elapsed / 2.6 + phase)
                + 90 * math.sin(elapsed / 1.3 + phase)
            )
            if warming_up:
                idle_base = 1280 if label == "GPU0" else 1440
                ramp = max(0.0, elapsed / load_delay)
                mem_used = int(idle_base + 420 * ramp + 45 * math.sin(elapsed * 2.0 + phase))
                util = max(0, int(4 + 10 * ramp + 2 * math.sin(elapsed * 1.6 + phase)))
                training_procs = []
            elif unloading:
                idle_base = 1280 if label == "GPU0" else 1440
                unload_elapsed = max(0.0, elapsed - complete_at)
                ramp_down = min(1.0, unload_elapsed / unload_delay)
                loaded_mem = max(18000, min(30000, mem_base + mem_wave))
                mem_used = int(loaded_mem * (1.0 - ramp_down) + idle_base * ramp_down)
                util = int(max(3, 42 * (1.0 - ramp_down) + 5 * math.sin(elapsed + phase)))
                training_procs = []
            else:
                active_elapsed = elapsed - load_delay
                mem_used = max(18000, min(30000, mem_base + mem_wave + int((active_elapsed % 5) * 31)))
                util = int(
                    max(
                        72,
                        min(
                            99,
                            90
                            + 6 * math.sin(active_elapsed / 4.2 + phase)
                            + 3 * math.sin(active_elapsed / 1.9 + phase),
                        ),
                    )
                )
                training_procs = [
                    {
                        "pid": 43120 if label == "GPU0" else 42888,
                        "cmd": f"demo train.sh {job.get('stage_name', '')} --max_iterations {job.get('max_iterations', 5000)}",
                        "elapsed_sec": int(active_elapsed),
                        "task_name": "free_direct",
                        "num_envs": int(job.get("num_envs") or 1024),
                        "max_iterations": int(job.get("max_iterations") or 5000),
                        "seed": int(job.get("seed") or 0),
                        "label": f"free_direct - {int(job.get('num_envs') or 1024):,} envs - iter {int(job.get('max_iterations') or 5000):,}",
                    }
                ]
            tmux_sessions = [str(job.get("tmux_session", "gaitlab_demo"))]
            scalars = {} if warming_up or unloading else {
                "iteration": status["latest_step"],
                "reward": status["latest_reward"],
                "ep_len": 486.2 if label == "GPU0" else 472.5,
            }
        else:
            phase = 0.0 if label == "GPU0" else 1.7
            now = time.time()
            mem_base = 1280 if label == "GPU0" else 1440
            mem_used = mem_base + int(80 * math.sin(now / 11.0 + phase))
            util = max(0, int(2 + 2 * math.sin(now / 5.0 + phase)))
            training_procs = []
            tmux_sessions = []
            scalars = {}
        return {
            "label": label,
            "host": host,
            "reachable": True,
            "ts": time.time(),
            "hostname": "managed-node-a" if label == "GPU0" else "managed-node-b",
            "gpu": {
                "name": "NVIDIA GeForce RTX 5090",
                "mem_used": f"{mem_used} MiB",
                "mem_total": "32607 MiB",
                "util": f"{util} %",
            },
            "tmux_sessions": tmux_sessions,
            "training_procs": training_procs,
            "busy": busy,
            "latest_run_dir": f"/demo/live/{job.get('run_id')}" if job else "",
            "scalars": scalars,
            "demo_mode": True,
        }

    def _fallback_status_from_cache(self, job: dict[str, Any], error: str) -> dict[str, Any]:
        """Return a useful status when SSH polling times out.

        If the last node snapshot is reachable and shows no tmux sessions or
        training processes, the job is no longer active even if the direct
        status SSH call timed out. Treat that as a stopped/completed state
        instead of leaving the card stuck or marking a transient SSH timeout as
        the job's real status.
        """

        node_key = "gpu0" if job.get("node") == "GPU0" else "gpu1"
        with self._lock:
            snap = dict(self._state.node_cache.get(node_key, {}) or {})
        no_sessions = not snap.get("tmux_sessions")
        no_procs = not snap.get("training_procs")
        if snap.get("reachable") and no_sessions and no_procs:
            latest_step = int(job.get("latest_step") or 0)
            max_iterations = int(job.get("max_iterations") or 0)
            completed = max_iterations > 0 and latest_step >= max_iterations
            return {
                "job_id": job.get("job_id"),
                "node": job.get("node"),
                "run_id": job.get("run_id"),
                "status": "completed" if completed else "stopped",
                "progress": job.get("progress", 0.0),
                "latest_step": latest_step,
                "latest_reward": job.get("latest_reward", 0.0),
                "fall_rate": job.get("fall_rate", 0.0),
                "estimated_remaining_min": 0,
                "tmux_session": job.get("tmux_session", ""),
                "evidence_mode": "live_lab",
                "warning": f"status SSH timed out; inferred from node snapshot: {error}",
            }
        return {
            "job_id": job.get("job_id"),
            "node": job.get("node"),
            "run_id": job.get("run_id"),
            "status": job.get("status", "unknown"),
            "progress": job.get("progress", 0.0),
            "latest_step": job.get("latest_step", 0),
            "latest_reward": job.get("latest_reward", 0.0),
            "fall_rate": job.get("fall_rate", 0.0),
            "estimated_remaining_min": job.get("estimated_remaining_min", 0),
            "tmux_session": job.get("tmux_session", ""),
            "evidence_mode": "live_lab",
            "warning": error,
        }


# ---------------------------------------------------------------------------
# SSH helpers (kept here so the store is self-contained)
# ---------------------------------------------------------------------------


def _ssh_kill_session(host: str, session: str) -> dict[str, Any]:
    import shlex
    import subprocess

    if not session:
        return {"error": "no tmux_session provided"}
    ssh_args = [
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=4",
        "-o", "ServerAliveCountMax=3",
    ]
    cmd = ["ssh", *ssh_args, host, f"tmux kill-session -t {shlex.quote(session)} 2>&1; echo RC=$?"]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"rc": 127, "out": str(exc), "host": host, "session": session}
    out = proc.stdout
    rc = proc.returncode
    # The remote echo appends RC=N; parse it for a definitive status.
    for line in reversed(out.splitlines()):
        if line.startswith("RC="):
            try:
                rc = int(line[3:])
            except ValueError:
                pass
            break
    normalized = out.lower()
    if rc != 0 and (
        "can't find session" in normalized
        or "no server running" in normalized
        or "failed to connect to server" in normalized
    ):
        return {
            "rc": 0,
            "out": out,
            "host": host,
            "session": session,
            "status": "stopped",
            "note": "tmux session was already absent",
        }
    return {
        "rc": rc,
        "out": out,
        "host": host,
        "session": session,
        "status": "killed_by_operator" if rc == 0 else "kill_failed",
    }


# Process-wide singleton. The FastAPI app and the SSE loop share this.
STORE = JobStore()


def get_store() -> JobStore:
    """FastAPI dependency that returns the process-wide :class:`JobStore`."""

    return STORE
