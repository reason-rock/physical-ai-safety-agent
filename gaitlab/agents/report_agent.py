from __future__ import annotations

from gaitlab.tools.report_tools import render_experiment_report


class ReportAgent:
    """Renders Markdown reports for Kaggle and research notes."""

    def render(self, **kwargs) -> str:
        return render_experiment_report(**kwargs)

