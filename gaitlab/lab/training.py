"""Live training node agent for GPU0 / GPU1.

Mirrors the public-demo :class:`gaitlab.agents.cell_training_agent.TrainingNodeAgent`
API (``submit`` / ``collect``) but drives the real GPU servers via the lab
pipeline scripts instead of synthesising deterministic data.

Flow:

1. ``submit(run_config)`` writes a ``scripts/stages/gaitlab_<run_id>.env``
   file (treatment) or reuses the parent stage (control), then SSHes into
   the assigned training host and launches ``train.sh`` inside a tmux
   session. The session name is recorded so ``status()`` can poll it.
2. ``status(job_id)`` reads the TensorBoard event file via
   ``snapshot_training_metrics.py`` and reports the latest iteration,
   reward, fall_rate proxy, and progress fraction.
3. ``collect(run_id)`` rsyncs the run directory back to the researcher PC
   and converts the TensorBoard scalars into Physical AI Safety Agent's ``scalars.csv``
   schema so the existing UI keeps working.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from gaitlab.lab.config import LiveLabConfig
from gaitlab.lab.process import PipelineResult, run_pipeline_script, summarize_for_audit
from gaitlab.lab.stage_env import (
    StageEnvPlan,
    describe_for_audit,
    plan_run,
    write_stage_env,
)
from gaitlab.lab.tb_to_scalars import convert_run_dir, summarize_for_audit as tb_audit


# Defaults that match the lab repo's train.sh and stage envs.
DEFAULT_NUM_ENVS = "32768"
DEFAULT_MAX_ITERATIONS = "60000"
DEFAULT_WALL_CLOCK_CAP = "4h"
DEFAULT_SEED = "42"
DEFAULT_DEVICE = "cuda:0"

# How long ``submit`` waits for the remote tmux session to come up before
# returning. ``train.sh`` itself is long-running; we only need to confirm
# the launch succeeded.
SUBMIT_VERIFY_SECONDS = 6.0


@dataclass
class LiveTrainingJob:
    """Tracks one live training submission."""

    job_id: str
    run_id: str
    node: str
    host: str
    config_path: str
    stage_name: str
    tmux_session: str
    is_control: bool
    plan: StageEnvPlan
    max_iterations: int = int(DEFAULT_MAX_ITERATIONS)
    audit: list[dict[str, Any]] = field(default_factory=list)


class LiveTrainingNodeAgent:
    """Adapter that submits, polls, and collects real lab training jobs.

    The class is intentionally small: it owns the SSH/tmux mechanics and
    delegates reward/iteration parsing to the lab's
    ``snapshot_training_metrics.py`` and Physical AI Safety Agent's ``tb_to_scalars.py``.
    """

    def __init__(
        self,
        node_name: str,
        config: LiveLabConfig,
        data_mode: str = "live_lab",
    ) -> None:
        if data_mode != "live_lab":
            raise ValueError(
                f"LiveTrainingNodeAgent requires data_mode='live_lab', got {data_mode!r}"
            )
        self.node_name = node_name
        self.config = config
        self.data_mode = data_mode
        config.require_enabled(action=f"live training on {node_name}")
        self.host = self._resolve_host(node_name)

    # ------------------------------------------------------------------
    # Public API (mirrors gaitlab.agents.cell_training_agent.TrainingNodeAgent)
    # ------------------------------------------------------------------

    def submit(self, run_config: Mapping[str, Any]) -> dict[str, Any]:
        """Launch a training job on the assigned node.

        ``run_config`` follows the shape produced by
        :func:`gaitlab.tools.experiment_store.create_experiment_pair`:
        ``{run_id, node, base_config, patch, paired_seeds, config_path}``.
        """

        run_id = run_config["run_id"]
        patch = dict(run_config.get("patch", {}))
        parent_stage = run_config.get("parent_stage")
        env_overrides = self._env_overrides_for({}, run_config)
        plan = plan_run(
            config=self.config,
            run_id=run_id,
            node=self.node_name,
            patch=patch,
            parent_stage=parent_stage,
            run_overrides=env_overrides,
        )
        write_stage_env(plan)

        tmux_session = _tmux_session_name(run_id)
        self._launch_remote_train(plan, env_overrides, tmux_session)

        max_iter = int(env_overrides.get("MAX_ITERATIONS", DEFAULT_MAX_ITERATIONS))
        job = LiveTrainingJob(
            job_id=f"{self.node_name.lower()}_live_{int(time.time())}",
            run_id=run_id,
            node=self.node_name,
            host=self.host,
            config_path=run_config["config_path"],
            stage_name=plan.stage_name,
            tmux_session=tmux_session,
            is_control=plan.is_control,
            plan=plan,
            max_iterations=max_iter,
            audit=[
                {"event": "submit", "stage": plan.stage_name, "host": self.host},
                describe_for_audit(plan),
            ],
        )
        self._persist_job_state(job)
        return _job_summary(job, status="submitted_live")

    def status(self, job_id: str) -> dict[str, Any]:
        """Return the latest training status for ``job_id``."""

        job = self._load_job_state(job_id)
        run_dir = self._resolve_remote_run_dir(job)
        snapshot = self._snapshot_metrics(run_dir)
        iteration = snapshot.get("iteration", 0)
        reward = snapshot.get("reward")
        ep_len = snapshot.get("ep_len")
        fall_rate = _derive_fall_rate(ep_len)
        progress = min(1.0, iteration / max(1, job.max_iterations))
        alive = self._tmux_session_alive(job.tmux_session)
        return {
            "job_id": job.job_id,
            "node": job.node,
            "run_id": job.run_id,
            "status": "running" if alive else ("completed" if progress >= 0.999 else "stopped"),
            "progress": round(progress, 4),
            "latest_step": iteration,
            "latest_reward": reward if reward is not None else 0.0,
            "fall_rate": fall_rate,
            "estimated_remaining_min": _estimate_remaining_min(progress, job.max_iterations),
            "tmux_session": job.tmux_session,
            "evidence_mode": "live_lab",
        }

    def collect(self, run_id: str) -> dict[str, Any]:
        """Fetch a completed run's directory and convert it to Physical AI Safety Agent schema."""

        job = self._find_job_by_run_id(run_id)
        remote_run_dir = self._resolve_remote_run_dir(job)
        local_run_dir = self._local_run_dir(run_id)
        self._rsync_run_dir(remote_run_dir, local_run_dir)

        # The remote run dir is a timestamped folder (e.g.
        # ``2026-06-26_19-42-30/``) containing events.out.tfevents.* and
        # model_*.pt. After extraction local_run_dir may contain either
        # the events directly (when tar captured a flat dir) or a nested
        # timestamped subdir. Resolve to whichever level actually holds
        # the events.
        tb_run_dir = _resolve_tb_run_dir(local_run_dir)
        scalars_csv = self.config.workspace_path / "demo_data" / "logs" / f"{run_id}_scalars.csv"
        try:
            convert_run_dir(tb_run_dir, scalars_csv)
            tb_summary = tb_audit(tb_run_dir, scalars_csv)
        except RuntimeError as exc:
            tb_summary = {"error": str(exc), "output_csv": str(scalars_csv)}

        checkpoints = _list_local_checkpoints(tb_run_dir)
        self._write_checkpoint_meta(run_id, job, tb_run_dir, checkpoints)
        return {
            "run_id": run_id,
            "log_path": str(scalars_csv.relative_to(self.config.workspace_path)).replace("\\", "/"),
            "checkpoints": [
                str(p.relative_to(self.config.workspace_path)).replace("\\", "/")
                for p in checkpoints
            ],
            "checkpoint_meta": (
                f"demo_data/artifacts/{run_id}/checkpoint_meta.json"
            ),
            "evidence_mode": "live_lab",
            "audit": {"tb_conversion": tb_summary},
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_host(self, node_name: str) -> str:
        if node_name == "GPU0":
            # Match the Live Control snapshot mapping: GPU0 is the secondary
            # training PC when a fallback is configured.
            return self.config.train_host_fallbacks[0] if self.config.train_host_fallbacks else self.config.gpu0_host
        if node_name == "GPU1":
            return self.config.train_host_primary or self.config.gpu1_host
        raise ValueError(f"unknown training node: {node_name}")

    def _env_overrides_for(
        self,
        plan: StageEnvPlan,
        run_config: Mapping[str, Any],
    ) -> dict[str, str]:
        """Build the env var overrides passed to ``train.sh``.

        The stage env file already encodes the treatment patch, but a few
        run-level knobs (seed, num_envs, max_iterations, wall_clock_cap)
        may come from the Physical AI Safety Agent run config and need to win.
        """

        overrides: dict[str, str] = {
            "NUM_ENVS": str(run_config.get("num_envs", DEFAULT_NUM_ENVS)),
            "MAX_ITERATIONS": str(run_config.get("max_iterations", DEFAULT_MAX_ITERATIONS)),
            "WALL_CLOCK_CAP": str(run_config.get("wall_clock_cap", DEFAULT_WALL_CLOCK_CAP)),
            "SEED": str(run_config.get("seed", DEFAULT_SEED)),
            "DEVICE": str(run_config.get("device", DEFAULT_DEVICE)),
        }
        # Pair seeds: the lab repo seeds from a single SEED env var; we
        # honor the first paired seed to keep control/treatment matched.
        paired_seeds = run_config.get("paired_seeds") or []
        if paired_seeds:
            overrides["SEED"] = str(paired_seeds[0])
        return overrides

    def _launch_remote_train(
        self,
        plan: StageEnvPlan,
        env_overrides: Mapping[str, str],
        tmux_session: str,
    ) -> None:
        """SSH into the training host and launch ``train.sh`` inside tmux."""

        # Use the *remote* repo path (Linux) on the training server, NOT the
        # local lab_repo_path (which is a Windows path on the dev PC).
        repo = self.config.remote_repo_path
        env_prefix = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env_overrides.items())

        # The generated gaitlab_<run_id>.env file lives on the LOCAL dev PC
        # (because that's where Physical AI Safety Agent writes it). train.sh on the remote
        # GPU server needs to be able to source it, so we scp the file to
        # the remote scripts/stages/ directory before launching.
        self._copy_stage_env_to_remote(plan)

        wrapped = (
            f"cd {shlex.quote(repo)} && mkdir -p tmp && "
            f"tmux new-session -d -s {shlex.quote(tmux_session)} "
            f"'{env_prefix} bash scripts/pipeline/train.sh {shlex.quote(plan.stage_name)}"
            f" 2>&1 | tee -a tmp/{tmux_session}.log'"
        )
        self._ssh(self.host, wrapped, run_id=plan.run_id, action="launch_train", timeout=30)

    def _copy_stage_env_to_remote(self, plan: StageEnvPlan) -> None:
        """Copy the generated gaitlab_<run_id>.env to the remote training host.

        Only gaitlab_* files we generated ourselves are ever pushed; parent
        stage envs already exist on the remote repo. The remote file is
        overwritten verbatim so the latest Physical AI Safety Agent plan wins.
        """

        if not plan.stage_name.startswith("gaitlab_"):
            return  # parent stage: already on the remote, nothing to copy
        if not plan.stage_path.exists():
            raise FileNotFoundError(
                f"local stage env not found: {plan.stage_path}. "
                f"Call write_stage_env(plan) before _launch_remote_train."
            )
        # Normalise CRLF -> LF before uploading to a Linux host, in case
        # the file was written by an older Physical AI Safety Agent version or edited by a
        # Windows tool. bash on Linux refuses to source files with '\r'.
        text = plan.stage_path.read_text(encoding="utf-8")
        normalised = text.replace("\r\n", "\n").replace("\r", "\n")
        if normalised != text:
            plan.stage_path.write_text(normalised, encoding="utf-8", newline="\n")
        repo = self.config.remote_repo_path
        remote_stages_dir = f"{repo}/scripts/stages"
        remote_path = f"{remote_stages_dir}/{plan.stage_path.name}"
        # mkdir on the remote (idempotent), then scp.
        self._ssh(
            self.host,
            f"mkdir -p {shlex.quote(remote_stages_dir)}",
            run_id=plan.run_id,
            action="mkdir_stages",
            check=False,
            timeout=20,
        )
        scp_cmd = [
            "scp",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=8",
            "-o", "ServerAliveCountMax=4",
            str(plan.stage_path),
            f"{self.host}:{remote_path}",
        ]
        log_path = self.config.live_log_dir(plan.run_id) / "scp_stage_env.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8", errors="replace") as handle:
            handle.write("$ " + " ".join(shlex.quote(c) for c in scp_cmd) + "\n")
            try:
                proc = subprocess.run(
                    scp_cmd,
                    check=False,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=30,
                )
            except subprocess.TimeoutExpired as exc:
                handle.write("TIMEOUT after 30s\n")
                raise RuntimeError(
                    f"scp of stage env to {self.host} timed out after 30s. Log: {log_path}"
                ) from exc
            except FileNotFoundError as exc:
                handle.write(f"SCP_MISSING: {exc}\n")
                raise RuntimeError(
                    "scp is required to upload the gaitlab stage env but was not found."
                ) from exc
            handle.write(proc.stdout)
            handle.write(f"\n[scp exit {proc.returncode}]\n")
            if proc.returncode != 0:
                raise RuntimeError(
                    f"scp of stage env failed (exit {proc.returncode}). Log: {log_path}"
                )

    def _snapshot_metrics(self, run_dir: str) -> dict[str, Any]:
        """Run ``snapshot_training_metrics.py`` on the training host."""

        repo = self.config.remote_repo_path
        picker = "scripts/pipeline/snapshot_training_metrics.py"
        cmd = (
            f"cd {shlex.quote(repo)} && "
            f"(bash scripts/pipeline/snapshot_training_metrics.sh {shlex.quote(run_dir)} "
            f"|| rl/.venv_isaaclab/bin/python {picker} {shlex.quote(run_dir)} "
            f"|| true)"
        )
        result = self._ssh(self.host, cmd, run_id="snapshot", action="snapshot", check=False)
        return _parse_snapshot_output(result.stdout)

    def _resolve_remote_run_dir(self, job: LiveTrainingJob) -> str:
        """Return the latest TensorBoard run dir on the training host.

        ``train.sh`` writes to ``$LOG_ROOT/<YYYY-MM-DD_HH-MM-SS>/``. We use
        the lab's ``_common.sh`` resolver indirectly via a one-liner that
        lists run dirs sorted by mtime.
        """

        cmd = (
            "bash -lc '"
            f"ls -1td $HOME/IsaacLab/logs/rsl_rl/darwin_op_walk_free_direct/*/ 2>/dev/null "
            "| head -1'"
        )
        result = self._ssh(self.host, cmd, run_id=job.run_id, action="resolve_run_dir", check=False)
        path = result.stdout.strip().rstrip("/")
        if not path:
            raise RuntimeError(
                f"no TensorBoard run dir found on {self.host} for {job.run_id}"
            )
        return path

    def _rsync_run_dir(self, remote_run_dir: str, local_run_dir: Path) -> None:
        """Fetch a remote run directory into ``local_run_dir``.

        Prefers ``rsync`` (incremental, resumable, low-bandwidth) and falls
        back to ``tar | scp`` only when rsync is unavailable on the dev PC.
        rsync is the optimal choice for TensorBoard event files, which are
        append-only and grow over the course of a training run — rsync
        transfers only the new tail on each poll, while tar+scp would
        re-transfer the whole file every time.
        """

        local_run_dir.mkdir(parents=True, exist_ok=True)
        if _has_rsync():
            self._rsync_run_dir_via_rsync(remote_run_dir, local_run_dir)
        else:
            self._rsync_run_dir_via_tar_scp(remote_run_dir, local_run_dir)

    def _rsync_run_dir_via_rsync(self, remote_run_dir: str, local_run_dir: Path) -> None:
        """rsync over SSH — optimal for incremental TensorBoard polls.

        Two environment quirks are handled here so rsync works on the
        Windows dev PC out of the box:

        - MSYS2 rsync mangles Windows paths (``C:\\Users`` looks remote
          because of the colon). We convert the local target to the MSYS2
          mount form (``/c/Users/...``) and disable posix-path conversion
          via ``MSYS2_ARG_CONV_EXCL=*``.
        - MSYS2 rsync spawns MSYS2 ssh, which keeps its keys under the
          MSYS2 home, not the Windows user profile. We point MSYS2 ssh at
          the right keys by putting ``C:\\msys64\\usr\\bin`` at the front
          of PATH and copying ``id_ed25519`` into the MSYS2 home during
          installation. ``_ensure_msys2_ssh_keys`` does the copy lazily.
        """

        remote_run_dir = remote_run_dir.rstrip("/")
        remote = f"{self.host}:{remote_run_dir}/"
        ssh_opts = (
            "ssh -o BatchMode=yes -o ConnectTimeout=15 "
            "-o ServerAliveInterval=8 -o ServerAliveCountMax=4"
        )
        local = _to_msys_path(local_run_dir) + "/"
        cmd = [
            "rsync",
            "-az",                  # archive + compress
            "--partial",            # resume interrupted transfers
            "--inplace",            # update files in place (append-friendly for events)
            "--timeout=300",        # network IO timeout (5 min)
            "-e", ssh_opts,
            remote,
            local,
        ]
        env = dict(os.environ)
        env["MSYS2_ARG_CONV_EXCL"] = "*"
        env["MSYS_NO_PATHCONV"] = "1"
        # Make MSYS2 ssh/win32 helpers discoverable ahead of Windows OpenSSH.
        msys_bin = Path("C:/msys64/usr/bin")
        if msys_bin.exists():
            env["PATH"] = str(msys_bin) + os.pathsep + env.get("PATH", "")
            _ensure_msys2_ssh_keys()
        log_dir = self.config.live_log_dir("fetch")
        log_path = log_dir / f"{Path(remote_run_dir).name}.rsync.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8", errors="replace") as handle:
            handle.write("$ " + " ".join(shlex.quote(c) for c in cmd) + "\n")
            handle.write(f"local_target (msys): {local}\n")
            try:
                proc = subprocess.run(
                    cmd,
                    check=False,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
            except FileNotFoundError as exc:
                handle.write(f"RSYNC_MISSING: {exc}\n")
                # rsync disappeared between the _has_rsync check and now —
                # fall back to tar+scp rather than failing the whole collect.
                handle.write("falling back to tar+scp\n")
                self._rsync_run_dir_via_tar_scp(remote_run_dir, local_run_dir)
                return
            handle.write(proc.stdout)
            handle.write(f"\n[rsync exit {proc.returncode}]\n")
            if proc.returncode != 0:
                raise RuntimeError(
                    f"rsync failed (exit {proc.returncode}) for {remote}. "
                    f"Log: {log_path}"
                )

    def _rsync_run_dir_via_tar_scp(self, remote_run_dir: str, local_run_dir: Path) -> None:
        """Fallback: tar on the remote, scp back, extract locally.

        Used only when rsync is not installed on the dev PC. Re-transfers
        the whole run directory every call, so it is fine for a one-shot
        post-training collect but wasteful for repeated polling.
        """

        remote_run_dir = remote_run_dir.rstrip("/")
        run_basename = os.path.basename(remote_run_dir)
        remote_tar = f"/tmp/{run_basename}.tar.gz"

        tar_remote_cmd = (
            f"tar -C {shlex.quote(os.path.dirname(remote_run_dir))} "
            f"-czf {shlex.quote(remote_tar)} {shlex.quote(run_basename)}"
        )
        tar_result = self._ssh(
            self.host,
            tar_remote_cmd,
            run_id="fetch_tar",
            action="tar_run_dir",
            check=False,
        )
        if tar_result.returncode != 0:
            raise RuntimeError(
                f"remote tar failed (exit {tar_result.returncode}) for "
                f"{remote_run_dir}. Log: {tar_result.log_path}"
            )

        log_dir = self.config.live_log_dir("fetch")
        log_path = log_dir / f"{run_basename}.fetch.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        remote_source = f"{self.host}:{remote_tar}"
        local_tar = local_run_dir.parent / f"{run_basename}.tar.gz"

        scp_cmd = [
            "scp",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=8",
            "-o", "ServerAliveCountMax=4",
            remote_source,
            str(local_tar),
        ]
        with log_path.open("w", encoding="utf-8", errors="replace") as handle:
            handle.write("$ " + " ".join(shlex.quote(c) for c in scp_cmd) + "\n")
            try:
                proc = subprocess.run(
                    scp_cmd,
                    check=False,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
            except FileNotFoundError as exc:
                handle.write(f"SCP_MISSING: {exc}\n")
                raise RuntimeError(
                    "scp is required for live artifact collection but was not found."
                ) from exc
            handle.write(proc.stdout)
            handle.write(f"\n[scp exit {proc.returncode}]\n")
            if proc.returncode != 0:
                raise RuntimeError(
                    f"scp failed (exit {proc.returncode}) for {remote_source}. "
                    f"Log: {log_path}"
                )

            import tarfile

            try:
                with tarfile.open(local_tar, "r:gz") as archive:
                    archive.extractall(local_run_dir)
                handle.write(f"extracted to {local_run_dir}\n")
            except Exception as exc:
                handle.write(f"EXTRACT_FAILED: {exc}\n")
                raise RuntimeError(f"failed to extract {local_tar}: {exc}") from exc
            finally:
                try:
                    local_tar.unlink()
                except OSError:
                    pass

        # Best-effort cleanup of the remote tarball; ignore failures.
        self._ssh(
            self.host,
            f"rm -f {shlex.quote(remote_tar)}",
            run_id="fetch_tar",
            action="rm_remote_tar",
            check=False,
        )

    def _tmux_session_alive(self, tmux_session: str) -> bool:
        cmd = f"tmux has-session -t {shlex.quote(tmux_session)} 2>/dev/null && echo ALIVE || echo DONE"
        result = self._ssh(self.host, cmd, run_id="session", action="tmux_has_session", check=False)
        return "ALIVE" in result.stdout

    def _ssh(
        self,
        host: str,
        remote_command: str,
        *,
        run_id: str,
        action: str,
        check: bool = True,
        timeout: int = 60,
    ) -> PipelineResult:
        """Run a remote command via SSH and capture the result.

        We deliberately shell out to the system ``ssh`` rather than depend
        on paramiko: the lab's existing pipeline scripts use the same
        OpenSSH and SSH key setup, so reusing it keeps behaviour identical.
        """

        ssh_args = [
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=12",
            "-o",
            "ServerAliveInterval=8",
            "-o",
            "ServerAliveCountMax=4",
        ]
        command_list = ["ssh", *ssh_args, host, remote_command]
        command_str = " ".join(shlex.quote(part) for part in command_list)
        log_dir = self.config.live_log_dir(run_id)
        log_path = log_dir / f"ssh_{action}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8", errors="replace") as handle:
            handle.write(f"$ {command_str}\n")
            handle.flush()
            try:
                proc = subprocess.run(
                    command_list,
                    check=False,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                handle.write(f"TIMEOUT after {timeout}s\n")
                raise RuntimeError(
                    f"ssh {action} on {host} timed out after {timeout}s"
                ) from exc
            handle.write(proc.stdout)
            handle.write(f"\n[exit {proc.returncode}]\n")
        result = PipelineResult(
            command=command_str,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr="",
            log_path=log_path,
        )
        if check:
            result.raise_for_status(action=f"ssh {action} on {host}")
        return result

    def _local_run_dir(self, run_id: str) -> Path:
        return (
            self.config.workspace_path
            / "demo_data"
            / "artifacts"
            / run_id
            / "server_run"
        )

    def _write_checkpoint_meta(
        self,
        run_id: str,
        job: LiveTrainingJob,
        local_run_dir: Path,
        checkpoints: list[Path],
    ) -> None:
        import json

        meta_dir = self.config.workspace_path / "demo_data" / "artifacts" / run_id
        meta_dir.mkdir(parents=True, exist_ok=True)
        selected = checkpoints[-1] if checkpoints else None
        meta = {
            "run_id": run_id,
            "selected_checkpoint": selected.name if selected else None,
            "selection_reason": "latest model_*.pt in the live run dir",
            "mock_only": False,
            "sanitized_real_replay": False,
            "raw_checkpoint_included": False,
            "stage_name": job.stage_name,
            "node": job.node,
            "host": job.host,
            "is_control": job.is_control,
            "tmux_session": job.tmux_session,
            "local_run_dir": str(local_run_dir),
        }
        (meta_dir / "checkpoint_meta.json").write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8"
        )

    def _persist_job_state(self, job: LiveTrainingJob) -> None:
        import json

        state_dir = self.config.workspace_path / "demo_data" / "live_state"
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / f"{job.job_id}.json"
        path.write_text(
            json.dumps(
                {
                    "job_id": job.job_id,
                    "run_id": job.run_id,
                    "node": job.node,
                    "host": job.host,
                    "config_path": job.config_path,
                    "stage_name": job.stage_name,
                    "tmux_session": job.tmux_session,
                    "is_control": job.is_control,
                    "parent_stage": job.plan.parent_stage,
                    "max_iterations": job.max_iterations,
                    "audit": job.audit,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _load_job_state(self, job_id: str) -> LiveTrainingJob:
        import json

        path = (
            self.config.workspace_path
            / "demo_data"
            / "live_state"
            / f"{job_id}.json"
        )
        if not path.exists():
            raise FileNotFoundError(f"unknown live job_id: {job_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        plan = plan_run(
            config=self.config,
            run_id=data["run_id"],
            node=data["node"],
            patch={},
            parent_stage=data.get("parent_stage"),
        )
        return LiveTrainingJob(
            job_id=data["job_id"],
            run_id=data["run_id"],
            node=data["node"],
            host=data["host"],
            config_path=data["config_path"],
            stage_name=data["stage_name"],
            tmux_session=data["tmux_session"],
            is_control=data["is_control"],
            plan=plan,
            max_iterations=data.get("max_iterations", int(DEFAULT_MAX_ITERATIONS)),
        )

    def _find_job_by_run_id(self, run_id: str) -> LiveTrainingJob:
        state_dir = self.config.workspace_path / "demo_data" / "live_state"
        if not state_dir.exists():
            raise FileNotFoundError(f"no live state for run_id {run_id}")
        for candidate in state_dir.glob("*.json"):
            data = __import__("json").loads(candidate.read_text(encoding="utf-8"))
            if data.get("run_id") == run_id:
                return self._load_job_state(data["job_id"])
        raise FileNotFoundError(f"no live state for run_id {run_id}")


def _job_summary(job: LiveTrainingJob, *, status: str) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "node": job.node,
        "run_id": job.run_id,
        "config_path": job.config_path,
        "status": status,
        "progress": 0.0,
        "latest_step": 0,
        "estimated_remaining_min": 0,
        "latest_reward": 0.0,
        "fall_rate": 0.0,
        "evidence_mode": "live_lab",
        "stage_name": job.stage_name,
        "tmux_session": job.tmux_session,
        "host_masked": _mask_host(job.host),
    }


def _mask_host(user_at_host: str) -> str:
    if "@" in user_at_host:
        user, _, host = user_at_host.partition("@")
        return f"{user[:3]}***@{host}"
    return user_at_host


def _tmux_session_name(run_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", run_id).strip("_").lower()
    return f"gaitlab_{safe}"


def _parse_snapshot_output(stdout: str) -> dict[str, Any]:
    """Parse ``snapshot_training_metrics.py``'s ``<label> <step> <value>`` lines."""

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
            out["reward"] = value
        elif label == "ep_len":
            out["ep_len"] = value
    return out


def _derive_fall_rate(ep_len: float | None) -> float:
    """Map mean episode length to a [0, 1] fall-rate proxy."""

    if ep_len is None or ep_len <= 0:
        return 1.0
    nominal = 1000.0
    ratio = max(0.0, min(1.0, ep_len / nominal))
    return round(1.0 - ratio, 4)


def _estimate_remaining_min(progress: float, max_iterations: int) -> int:
    if progress >= 1.0:
        return 0
    # Coarse estimate: ~6s per iteration observed in lab logs.
    remaining_iters = int(max_iterations * (1.0 - progress))
    return max(0, int(remaining_iters * 6 / 60))


def _list_local_checkpoints(local_run_dir: Path) -> list[Path]:
    return sorted(local_run_dir.glob("model_*.pt"), key=lambda p: p.name)


def _has_rsync() -> bool:
    """Return True when ``rsync`` is available on the dev PC's PATH.

    Cached after the first call so we do not shell out on every collect.
    rsync is the optimal transport for live artifact collection (incremental,
    resumable, append-friendly for TensorBoard events). When unavailable we
    fall back to tar+scp transparently.
    """

    global _RSYNC_AVAILABLE
    if _RSYNC_AVAILABLE is None:
        try:
            subprocess.run(
                ["rsync", "--version"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _RSYNC_AVAILABLE = True
        except FileNotFoundError:
            _RSYNC_AVAILABLE = False
    return _RSYNC_AVAILABLE


_RSYNC_AVAILABLE: bool | None = None


def _to_msys_path(path: Path) -> str:
    """Convert a Windows path to the MSYS2 mount form rsync understands.

    ``C:\\Users\\foo`` -> ``/c/Users/foo``. Other drive letters follow the
    same pattern. If the input is already POSIX-style (e.g. when running
    on Linux) it is returned unchanged.
    """

    text = str(path)
    if os.name != "nt":
        return text
    # Drive letter at the start: C:\... -> /c/...
    if len(text) >= 2 and text[1] == ":" and text[0].isalpha():
        drive = text[0].lower()
        rest = text[2:].replace("\\", "/")
        return f"/{drive}{rest}"
    return text.replace("\\", "/")


def _ensure_msys2_ssh_keys() -> None:
    """Copy the Windows OpenSSH default keys into the MSYS2 home, once.

    MSYS2 ssh keeps keys in ``C:\\msys64\\home\\<user>\\.ssh``, which is a
    different location from the Windows profile. We copy ``id_ed25519``
    and ``id_rsa`` (and their .pub counterparts) so MSYS2 ssh can authenticate
    against the same hosts as Windows OpenSSH. Idempotent; checks mtime.
    """

    if os.name != "nt":
        return
    msys_home = Path("C:/msys64/home") / os.environ.get("USERNAME", "")
    if not msys_home.exists():
        return
    win_ssh = Path(os.environ["USERPROFILE"]) / ".ssh"
    msys_ssh = msys_home / ".ssh"
    if not win_ssh.exists():
        return
    msys_ssh.mkdir(parents=True, exist_ok=True)
    for name in ("id_ed25519", "id_ed25519.pub", "id_rsa", "id_rsa.pub"):
        src = win_ssh / name
        dst = msys_ssh / name
        if not src.exists():
            continue
        if dst.exists() and src.stat().st_mtime <= dst.stat().st_mtime:
            continue
        try:
            import shutil

            shutil.copy2(src, dst)
        except OSError:
            pass


def _resolve_tb_run_dir(local_run_dir: Path) -> Path:
    """Return the directory that actually contains ``events.out.tfevents.*``.

    The remote run dir is a single timestamped folder. After tar+extract
    on the local PC, ``local_run_dir`` may end up holding either:

    - the events directly (when the run folder was flat), or
    - a single timestamped subdir that contains the events.

    This helper picks the right level so TB parsing and checkpoint
    discovery work in both layouts.
    """

    if list(local_run_dir.glob("events.out.tfevents.*")):
        return local_run_dir
    children = [p for p in local_run_dir.iterdir() if p.is_dir()]
    for child in children:
        if list(child.glob("events.out.tfevents.*")):
            return child
    # Fall back to the original dir so error messages stay informative.
    return local_run_dir
