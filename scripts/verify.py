from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

PUBLIC_TEXT_SUFFIXES = {
    ".css",
    ".csv",
    ".env",
    ".example",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

PRIVATE_PATTERNS = {
    "reason" + "_rock",
    "REASON" + "~1",
    "C:" + "\\Users",
    "C:" + "\\\\" + "Users",
    "/home/" + "reason" + "_rock",
    "10." + "0.0.",
    "10." + "0.19.",
    "192." + "168.",
    "darwin-op" + "-retrofit",
    "gpu1" + "-pc-new",
    "gpu0" + "-pc",
    "BEGIN " + "PRIVATE KEY",
    "OPENAI_API_KEY=" + "sk-",
    "GOOGLE_API_KEY=" + "AIza",
    "KAGGLE_" + "KEY=",
}


def run(
    name: str,
    args: list[str],
    stdin: str | None = None,
    cwd: Path = ROOT,
) -> str:
    env = {**os.environ, "GAITLAB_USE_GOOGLE_API": "false"}
    proc = subprocess.run(
        [PYTHON, *args],
        input=stdin,
        text=True,
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"FAIL {name}")
    print(f"PASS {name}")
    return proc.stdout + proc.stderr


def main() -> None:
    demo = run("cli demo", ["run_demo.py"])
    assert re.search(r"Experiment Report: pair_\d{5,}", demo)
    assert "Safety level: `supported_test_only`" in demo

    replay = run(
        "real replay workflow",
        [
            "-c",
            (
                "from gaitlab.orchestrator import GaitLabOrchestrator; "
                "r=GaitLabOrchestrator(data_mode='real_replay').handle_request('forward fall replay'); "
                "print(r.evaluations[r.pair.treatment['run_id']]['evidence_mode']); "
                "print(r.safety['safety_level'])"
            ),
        ],
    )
    assert "sanitized_real_replay" in replay
    assert "supported_test_only" in replay

    evals = run("agent evals", ["evals/run_evals.py"])
    assert "PASS safety case: free_walk_candidate" in evals

    unit = run("unit tests", ["-m", "unittest", "discover", "-s", "tests"])
    assert "OK" in unit or "Ran " in unit

    pycache_prefix = str(ROOT / ".pycache_verify")
    compile_out = run(
        "compile",
        [
            "-X",
            f"pycache_prefix={pycache_prefix}",
            "-m",
            "compileall",
            "gaitlab",
            "evals",
            "scripts",
            "run_demo.py",
            "web",
        ],
    )
    assert "Listing 'gaitlab'" in compile_out

    message = json.dumps({"tool": "list_tools", "arguments": {}}) + "\n"
    mcp = run("mcp dispatcher", ["-m", "gaitlab.mcp.server"], stdin=message)
    assert "create_experiment_pair" in mcp
    assert "run_robot_safety_gate" in mcp

    optional = run(
        "optional integration adapters",
        [
            "-c",
            (
                "from gaitlab.mcp import official_server; "
                "from gaitlab.adk_app import agent; "
                "print(official_server.create_server); "
                "print(agent.root_agent)"
            ),
        ],
    )
    assert "create_server" in optional

    backend = run(
        "fastapi backend import",
        [
            "-c",
            (
                "from web.backend.main import app; "
                "from web.backend import schemas, job_store, sse; "
                "paths = set(app.openapi().get('paths', {}).keys()); "
                "assert '/api/health' in paths, paths; "
                "assert '/api/workflow' in paths, paths; "
                "assert '/sse/lab' in paths, paths; "
                "assert '/api/lab/jobs' in paths, paths; "
                "print('OK')"
            ),
        ],
    )
    assert "OK" in backend

    run("submission zip", ["scripts/build_submission_zip.py"])
    zip_path = ROOT / "submission" / "physical-ai-safety-agent-public.zip"
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert ".env" not in names
    assert ".env.example" in names
    assert not any(name.startswith(".venv/") for name in names)
    assert not any(name.startswith("docs/ko/") for name in names)
    assert not any(name.startswith("gaitlab/lab/") for name in names), (
        "gaitlab/lab/ must never ship in the public submission zip"
    )
    assert "scripts/sync_training_history.py" not in names, (
        "private training-history sync script must not ship"
    )
    assert "demo_data/training_history.db" not in names, (
        "private live training-history DB must not ship"
    )
    assert "tests/test_lab_adapter.py" not in names, (
        "private lab-adapter tests require excluded live-lab modules"
    )
    assert not any(name.startswith("demo_data/artifacts/live_smoke_") for name in names), (
        "private live smoke artifacts must not ship"
    )
    assert not any(name.startswith("demo_data/logs/live_smoke_") for name in names), (
        "private live smoke scalar logs must not ship"
    )
    assert not any(name.startswith("web/frontend/node_modules/") for name in names), (
        "web/frontend/node_modules/ must never ship in the public submission zip"
    )
    assert not any(name.startswith("web/frontend/.next/") for name in names), (
        "web/frontend/.next/ must never ship in the public submission zip"
    )
    assert not any("app.py" == name for name in names), (
        "Streamlit app.py was deleted; it must not appear in the zip"
    )
    assert any(name.startswith("demo_data/real_replay/") for name in names)

    _scan_public_zip(zip_path)
    _smoke_test_public_zip(zip_path)

    print("All verification checks passed.")


def _scan_public_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            suffix = Path(info.filename).suffix.lower()
            if suffix not in PUBLIC_TEXT_SUFFIXES:
                continue
            text = archive.read(info).decode("utf-8", errors="replace")
            for pattern in PRIVATE_PATTERNS:
                assert pattern not in text, (
                    f"private pattern {pattern!r} found in public zip file {info.filename}"
                )
    print("PASS public zip private-pattern scan")


def _smoke_test_public_zip(zip_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="gaitlab-public-") as tmp:
        public_root = Path(tmp)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(public_root)
        smoke = run(
            "public zip smoke",
            [
                "-c",
                (
                    "from gaitlab.orchestrator import GaitLabOrchestrator; "
                    "from web.backend.main import app; "
                    "from web.backend.lab_api import get_lab_config; "
                    "paths=set(app.openapi().get('paths',{}).keys()); "
                    "assert '/api/health' in paths, paths; "
                    "assert '/api/workflow' in paths, paths; "
                    "cfg=get_lab_config(); "
                    "assert cfg['enabled'] is False, cfg; "
                    "r=GaitLabOrchestrator(data_mode='real_replay').handle_request('forward fall replay'); "
                    "assert r.safety['safety_level']=='supported_test_only'; "
                    "print('OK')"
                ),
            ],
            cwd=public_root,
        )
        assert "OK" in smoke
        unit = run(
            "public zip unit tests",
            ["-m", "unittest", "discover", "-s", "tests"],
            cwd=public_root,
        )
        assert "OK" in unit or "Ran " in unit


if __name__ == "__main__":
    main()
