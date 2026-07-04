"""Offline unit tests for the FastAPI backend JobStore.

Exercises the parts of :class:`web.backend.job_store.JobStore` that do
not require SSH or a live lab: state lifecycle, error paths, and the
in-process bookkeeping. Live SSH paths are covered by manual smoke
testing against the real Cells.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from web.backend import schemas  # noqa: E402
from web.backend.job_store import JobStore, _ssh_kill_session  # noqa: E402


class JobStoreStateTests(unittest.TestCase):
    def test_initial_state_is_empty(self) -> None:
        store = JobStore()
        self.assertEqual(store.list_jobs(), [])
        cache, ts = store.get_node_cache()
        self.assertEqual(cache, {})
        self.assertEqual(ts, 0.0)

    def test_reset_clears_tracked_jobs(self) -> None:
        store = JobStore()
        # Inject a fake job directly into the internal state.
        store._state.jobs["fake_job"] = {"job_id": "fake_job", "status": "running"}
        self.assertEqual(len(store.list_jobs()), 1)
        store.reset()
        self.assertEqual(store.list_jobs(), [])

    def test_get_unknown_job_returns_none(self) -> None:
        store = JobStore()
        self.assertIsNone(store.get_job("does_not_exist"))

    def test_refresh_status_unknown_job_returns_error(self) -> None:
        store = JobStore()
        result = store.refresh_status(_StubConfig(), "no_such_job")
        self.assertIn("error", result)
        self.assertIn("no_such_job", result["error"])

    def test_kill_unknown_job_returns_error(self) -> None:
        store = JobStore()
        result = store.kill(_StubConfig(), "no_such_job")
        self.assertIn("error", result)

    def test_collect_unknown_job_returns_error(self) -> None:
        store = JobStore()
        result = store.collect(_StubConfig(), "no_such_job")
        self.assertIn("error", result)


class SshKillSessionTests(unittest.TestCase):
    def test_empty_session_returns_error_without_ssh(self) -> None:
        result = _ssh_kill_session("somehost", "")
        self.assertIn("error", result)
        # No rc key when we refused to invoke ssh at all.

    def test_unreachable_host_returns_error_rc(self) -> None:
        # 127.0.0.1:1 is guaranteed to refuse; subprocess.run will get a
        # non-zero rc. This exercises the parsing path without depending
        # on any real host.
        result = _ssh_kill_session("nonexistent.invalid", "fake_session")
        self.assertIn("rc", result)
        # rc is non-zero because the host does not resolve.
        self.assertNotEqual(result["rc"], 0)


class SchemasTests(unittest.TestCase):
    def test_workflow_request_defaults(self) -> None:
        req = schemas.WorkflowRequest(request="hello")
        self.assertEqual(req.num_rollouts, 256)
        self.assertEqual(req.safety_strictness, "standard")
        self.assertEqual(req.data_mode, "mock")
        self.assertFalse(req.operator_confirmed)

    def test_workflow_request_rejects_invalid_mode(self) -> None:
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            schemas.WorkflowRequest(request="x", data_mode="bogus")  # type: ignore[arg-type]

    def test_job_summary_model_round_trip(self) -> None:
        job = schemas.JobSummaryModel(
            job_id="j1",
            node="GPU0",
            run_id="r1",
            status="submitted_live",
            progress=0.1,
            latest_step=5,
            latest_reward=-12.3,
            fall_rate=0.9,
            stage_name="gaitlab_r1",
            tmux_session="gaitlab_r1",
            host_masked="rea***@host",
            submitted_at=123.0,
            max_iterations=20,
        )
        dumped = job.model_dump()
        self.assertEqual(dumped["job_id"], "j1")
        self.assertEqual(dumped["status"], "submitted_live")

    def test_submit_job_request_enforces_node_enum(self) -> None:
        from pydantic import ValidationError

        ok = schemas.SubmitJobRequest(node="GPU0", run_id="r1")
        self.assertEqual(ok.node, "GPU0")
        with self.assertRaises(ValidationError):
            schemas.SubmitJobRequest(node="Cell99", run_id="r1")  # type: ignore[arg-type]


class _StubConfig:
    """Minimal stand-in for LiveLabConfig for tests that don't touch SSH."""

    pass


if __name__ == "__main__":
    unittest.main()
