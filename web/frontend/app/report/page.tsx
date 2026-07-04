"use client";

import { useTranslation } from "react-i18next";
import { useDashboard } from "@/lib/store";
import { useLabUpdates } from "@/lib/sse";
import { shouldHoldFinalLiveEvidence } from "@/lib/live-status";
import { displayNodeAliasesInText, useAlias } from "@/lib/aliases";
import { presentEvidenceText } from "@/lib/presentation";
import { Card, EmptyState, PageHeader, Pill } from "@/components/ui";

export default function ReportPage() {
  const { t } = useTranslation();
  const result = useDashboard((s) => s.result);
  const evidenceMode = useDashboard((s) => s.evidenceMode);
  const isLive = evidenceMode === "Live Lab";
  const { latest } = useLabUpdates(isLive);
  const gpu0Name = useAlias("gpu0");
  const gpu1Name = useAlias("gpu1");
  if (!result) return <EmptyState title={t("report.empty")} />;
  if (isLive && shouldHoldFinalLiveEvidence(latest?.jobs)) {
    return (
      <div className="animate-fade-in space-y-6">
        <PageHeader title={t("report.title")} subtitle="Waiting for final live evidence." />
        <Card className="border-warn-100 bg-warn-50/50 p-6">
          <div className="text-sm font-bold text-warn-600">Final report not ready</div>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-warn-600/90">
            Live Lab jobs are tracked separately from the deterministic workflow result. The final
            report should be produced only after collection, evaluation, and safety gating are run
            for the latest control/treatment pair.
          </p>
        </Card>
      </div>
    );
  }
  const { report_markdown, pair } = result;
  const reportMarkdown = presentEvidenceText(
    displayNodeAliasesInText(report_markdown, {
      gpu0: gpu0Name,
      gpu1: gpu1Name,
    })
  );

  function download() {
    const blob = new Blob([reportMarkdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${pair.pair_id}_report.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title={t("report.title")}
        subtitle={
          <>
            {t("report.subtitle")}{" "}
            <code className="font-mono">{pair.pair_id}</code>.
          </>
        }
        right={
          <button type="button" onClick={download} className="btn btn-brand-soft">
            {t("report.download")}
          </button>
        }
      />

      <Card className="p-6">
        <pre className="whitespace-pre-wrap break-words rounded-md bg-bg p-4 font-mono text-[12px] leading-relaxed text-ink-soft">
          {reportMarkdown}
        </pre>
      </Card>

      <Card className="p-4">
        <Pill tone="muted">
          {reportMarkdown.length} {t("report.chars")}
        </Pill>
      </Card>
    </div>
  );
}
