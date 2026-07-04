"use client";

import { useTranslation } from "react-i18next";
import { useDashboard } from "@/lib/store";
import { useLabUpdates } from "@/lib/sse";
import { shouldHoldFinalLiveEvidence } from "@/lib/live-status";
import { presentEvidenceText } from "@/lib/presentation";
import { Card, EmptyState, PageHeader, Pill, SectionTitle, Stat } from "@/components/ui";

function verdictTone(v: string): "safe" | "danger" | "muted" {
  const s = v.toLowerCase();
  if (s.includes("improve")) return "safe";
  if (s.includes("regress") || s.includes("risk")) return "danger";
  return "muted";
}

export default function EvaluationPage() {
  const { t } = useTranslation();
  const result = useDashboard((s) => s.result);
  const evidenceMode = useDashboard((s) => s.evidenceMode);
  const isLive = evidenceMode === "Live Lab";
  const { latest } = useLabUpdates(isLive);
  if (!result) return <EmptyState title={t("eval.empty")} />;
  if (isLive && shouldHoldFinalLiveEvidence(latest?.jobs)) {
    return (
      <LiveEvidencePending
        title={t("eval.title")}
        message="Live Lab jobs are tracked separately from the deterministic workflow result. Collect and evaluate the latest control/treatment jobs before using this final comparison."
      />
    );
  }
  const { comparison, evaluations, pair } = result;
  const control = evaluations[pair.control.run_id as string];
  const treatment = evaluations[pair.treatment.run_id as string];

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title={t("eval.title")}
        subtitle={t("eval.subtitle")}
        right={
          <Pill tone={comparison.decision.includes("safer") ? "safe" : "warn"}>
            {comparison.decision}
          </Pill>
        }
      />

      <Card className="p-5">
        <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
          <Stat label={t("eval.decision")} value={comparison.decision} />
          <Stat
            label={t("eval.recommendation")}
            value={comparison.recommendation}
          />
          <Stat
            label={t("eval.improvements")}
            value={comparison.improvements?.length ?? 0}
            hint={t("eval.metricCount")}
          />
          <Stat
            label={t("eval.regressions")}
            value={comparison.regressions?.length ?? 0}
            hint={t("eval.metricCount")}
          />
        </div>
        {treatment?.evidence_mode && (
          <div className="mt-3 text-[10px] text-faint">
            {t("eval.evidenceModeLabel")}:{" "}
            <code className="font-mono">{presentEvidenceText(treatment.evidence_mode)}</code>
          </div>
        )}
      </Card>

      <Card className="overflow-hidden">
        <div className="border-b border-line px-4 py-3">
          <SectionTitle>{t("eval.metricComparison")}</SectionTitle>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-bg/60 text-left text-[10px] uppercase tracking-wider text-faint">
              <th className="px-4 py-2 font-bold">{t("eval.metric")}</th>
              <th className="px-4 py-2 font-bold">{t("eval.control")}</th>
              <th className="px-4 py-2 font-bold">{t("eval.treatment")}</th>
              <th className="px-4 py-2 font-bold">{t("eval.verdict")}</th>
            </tr>
          </thead>
          <tbody>
            {comparison.metric_rows.map((row) => (
              <tr key={row.metric} className="border-t border-line/60">
                <td className="px-4 py-2.5 text-ink-soft">{row.metric}</td>
                <td className="px-4 py-2.5 font-mono text-xs text-muted">{row.control}</td>
                <td className="px-4 py-2.5 font-mono text-xs font-bold text-ink">{row.treatment}</td>
                <td className="px-4 py-2.5">
                  <Pill tone={verdictTone(row.verdict)}>{row.verdict}</Pill>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {control && treatment && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {[
            {
              label: t("eval.fallFree"),
              c: `${control.fall_free_count}/${control.num_rollouts}`,
              t: `${treatment.fall_free_count}/${treatment.num_rollouts}`,
            },
            {
              label: t("eval.fallTime"),
              c: `${control.avg_fall_time_sec.toFixed(1)}s`,
              t: `${treatment.avg_fall_time_sec.toFixed(1)}s`,
            },
            {
              label: t("eval.velocity"),
              c: control.avg_velocity.toFixed(3),
              t: treatment.avg_velocity.toFixed(3),
            },
            {
              label: t("eval.jointLimit"),
              c: control.joint_limit_max_ratio.toFixed(2),
              t: treatment.joint_limit_max_ratio.toFixed(2),
            },
          ].map((m) => (
            <Card key={m.label} className="p-4">
              <Stat
                label={m.label}
                value={m.t}
                hint={`${t("eval.vsControl")} ${m.c}`}
              />
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function LiveEvidencePending({ title, message }: { title: string; message: string }) {
  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader title={title} subtitle="Waiting for collected live evidence." />
      <Card className="border-warn-100 bg-warn-50/50 p-6">
        <div className="text-sm font-bold text-warn-600">Final evaluation not ready</div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-warn-600/90">{message}</p>
      </Card>
    </div>
  );
}
