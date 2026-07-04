from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "submission" / "physical-ai-safety-agent-public.zip"
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".pycache_verify",
    "__pycache__",
    # Next.js / Node build artifacts — never ship in the public zip.
    "node_modules",
    ".next",
}
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".zip",
}
EXCLUDED_FILES = {
    ".env",
    ".streamlit/secrets.toml",
    # Private lab history is rebuilt locally from real servers and should not
    # be part of the public no-credential demo.
    "demo_data/training_history.db",
    "scripts/sync_training_history.py",
    "tests/test_lab_adapter.py",
}
EXCLUDED_PREFIXES = {
    "submission/",
    "reports/",
    "demo_data/artifacts/",
    "demo_data/generated/",
    "demo_data/artifacts/live_smoke_",
    "demo_data/logs/live_smoke_",
    "demo_data/live_logs/",
    "demo_data/live_state/",
    "docs/ko/",
    "web/frontend/out/",  # built static export; reviewers rebuild from source
}
# Whole sub-trees that must never reach the public Kaggle submission.
# ``gaitlab/lab/`` is the private lab adapter (real SSH, real robot deploy)
# and is excluded by design. The rest of ``gaitlab/`` ships normally so
# reviewers can run the safe-by-default demo.
EXCLUDED_SUBPATHS = {
    "gaitlab/lab",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a public-safe Physical AI Safety Agent submission zip.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in _iter_public_files(ROOT):
            rel = path.relative_to(ROOT).as_posix()
            archive.write(path, rel)

    print(f"Wrote {output}")


def _excluded(path: Path, rel: str) -> bool:
    if rel == ".env.example":
        return False
    parts = set(path.relative_to(ROOT).parts)
    if parts & EXCLUDED_DIRS:
        return True
    if rel in EXCLUDED_FILES:
        return True
    if _has_excluded_prefix(rel):
        return True
    if any(_within_subpath(rel, sub) for sub in EXCLUDED_SUBPATHS):
        return True
    if path.suffix in EXCLUDED_SUFFIXES:
        return True
    if path.name.startswith(".env."):
        return True
    return False


def _iter_public_files(root: Path):
    """Yield public-safe files without descending into excluded directories."""

    stack = [root]
    while stack:
        current = stack.pop()
        for child in current.iterdir():
            rel = child.relative_to(root).as_posix()
            if child.is_dir():
                parts = set(child.relative_to(root).parts)
                if parts & EXCLUDED_DIRS:
                    continue
                if _has_excluded_prefix(rel):
                    continue
                if any(_within_subpath(rel, sub) for sub in EXCLUDED_SUBPATHS):
                    continue
                stack.append(child)
                continue
            if not _excluded(child, rel):
                yield child


def _within_subpath(rel: str, sub: str) -> bool:
    """True when ``rel`` is inside the sub-tree ``sub`` (e.g. ``gaitlab/lab``)."""

    rel = rel.replace("\\", "/")
    return rel == sub or rel.startswith(sub + "/")


def _has_excluded_prefix(rel: str) -> bool:
    """True when ``rel`` matches an excluded public-zip prefix."""

    rel = rel.replace("\\", "/")
    for prefix in EXCLUDED_PREFIXES:
        prefix = prefix.rstrip("/")
        if rel == prefix or rel.startswith(prefix + "/") or rel.startswith(prefix):
            return True
    return False


if __name__ == "__main__":
    main()
