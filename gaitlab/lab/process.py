"""Subprocess wrapper for invoking the lab pipeline scripts.

The adapter never opens SSH sockets directly. It shells out to the
already-verified pipeline scripts in ``physical-ai-lab/scripts/pipeline/``,
which themselves enforce the 3-machine role contract (training server /
dev PC / robot) and handle SSH retries, fallbacks, and watchdogs.

Each invocation captures stdout and stderr under
``demo_data/live_logs/<run_id>/`` for auditability.
"""

from __future__ import annotations

import os
import platform
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from gaitlab.lab.config import LiveLabConfig


@dataclass(frozen=True)
class PipelineResult:
    """Outcome of a pipeline script invocation."""

    command: str
    returncode: int
    stdout: str
    stderr: str
    log_path: Path

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def raise_for_status(self, action: str) -> "PipelineResult":
        if not self.ok:
            raise RuntimeError(
                f"{action} failed (exit {self.returncode}). "
                f"Log: {self.log_path}. Command: {self.command}"
            )
        return self


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _build_command(
    script_path: Path,
    args: Sequence[str],
) -> list[str]:
    """Return the command list for invoking a .ps1 or .sh script.

    PowerShell scripts use ``powershell -ExecutionPolicy Bypass -File``.
    Bash scripts use ``bash``. On Windows the bash invocation falls back
    to the system ``bash`` if available (Git Bash / WSL); the underlying
    lab scripts guard themselves against running on the wrong host.
    """

    suffix = script_path.suffix.lower()
    quoted_args = list(args)
    if suffix == ".ps1":
        return [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            *quoted_args,
        ]
    if suffix == ".sh":
        return ["bash", str(script_path), *quoted_args]
    # Treat anything else as a plain executable.
    return [str(script_path), *quoted_args]


def run_pipeline_script(
    config: LiveLabConfig,
    script: str | Path,
    args: Sequence[str] = (),
    run_id: str = "live",
    env_overrides: dict[str, str] | None = None,
    cwd: Path | None = None,
    timeout: float | None = None,
    check: bool = False,
    capture: bool = True,
) -> PipelineResult:
    """Invoke a pipeline script and return its captured result.

    The script path may be absolute or relative to ``config.pipeline_dir``.
    The stdout/stderr of every invocation is tee'd into
    ``demo_data/live_logs/<run_id>/<script-stem>_<timestamp>.log`` so an
    operator can audit any live run after the fact.
    """

    script_path = Path(script)
    if not script_path.is_absolute():
        script_path = config.pipeline_dir / script_path
    if not script_path.exists():
        raise FileNotFoundError(f"pipeline script not found: {script_path}")

    command_list = _build_command(script_path, args)
    command_str = " ".join(shlex.quote(part) for part in command_list)

    full_env = dict(os.environ)
    if env_overrides:
        full_env.update({k: str(v) for k, v in env_overrides.items()})

    log_dir = config.live_log_dir(run_id)
    log_path = log_dir / f"{script_path.stem}.log"

    with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
        log_handle.write(f"$ {command_str}\n")
        log_handle.write(f"cwd: {cwd or Path.cwd()}\n")
        log_handle.write(f"env_overrides_keys: {sorted(env_overrides or {})}\n")
        log_handle.flush()
        try:
            proc = subprocess.run(
                command_list,
                cwd=str(cwd) if cwd else None,
                env=full_env,
                capture_output=capture,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            log_handle.write(f"FILE_NOT_FOUND: {exc}\n")
            raise
        except subprocess.TimeoutExpired as exc:
            log_handle.write(f"TIMEOUT after {timeout}s\n")
            raise RuntimeError(
                f"pipeline script timed out after {timeout}s: {script_path.name}"
            ) from exc

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        log_handle.write("\n--- stdout ---\n")
        log_handle.write(stdout)
        log_handle.write("\n--- stderr ---\n")
        log_handle.write(stderr)
        log_handle.write(f"\n[exit {proc.returncode}]\n")

    result = PipelineResult(
        command=command_str,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
        log_path=log_path,
    )
    if check:
        result.raise_for_status(action=f"pipeline script {script_path.name}")
    return result


def quote_host(user_at_host: str) -> str:
    """Return ``user_at_host`` with any surrounding whitespace trimmed."""

    return (user_at_host or "").strip()


def join_host_args(hosts: Sequence[str]) -> list[str]:
    """Return the hosts as a single comma-joined CLI argument value."""

    return [",".join(h for h in hosts if h)] if any(hosts) else []


def summarize_for_audit(result: PipelineResult) -> dict[str, Any]:
    """Return a secret-free audit summary of a pipeline invocation."""

    return {
        "command": result.command,
        "returncode": result.returncode,
        "ok": result.ok,
        "log_path": str(result.log_path),
        "stdout_tail": result.stdout[-400:],
        "stderr_tail": result.stderr[-400:],
    }
