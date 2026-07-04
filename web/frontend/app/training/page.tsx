"use client";

import { useTranslation } from "react-i18next";
import { useDashboard } from "@/lib/store";
import { useLabUpdates } from "@/lib/sse";
import { formatProgressPercent } from "@/lib/live-status";
import { presentEvidenceText } from "@/lib/presentation";
import { Card, EmptyState, PageHeader, Pill, Progress, SectionTitle, Stat } from "@/components/ui";
import { displayNodeName } from "@/lib/aliases";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export default function TrainingPage() {
  const { t } = useTranslation();
  const result = useDashboard((s) => s.result);
  const evidenceMode = useDashboard((s) => s.evidenceMode);
  const isLive = evidenceMode === "Live Lab";
  const { latest, refresh } = useLabUpdates(isLive);
  const liveJobs = latest?.jobs ?? [];
  const trainingJobs = isLive && liveJobs.length > 0 ? liveJobs : result?.training_jobs ?? [];

  if (!result && trainingJobs.length === 0) return <EmptyState title={t("training.empty")} />;

  const controlId =
    (trainingJobs.find((job) => String(job.run_id).startsWith("control"))?.run_id as string | undefined) ??
    (result?.pair.control.run_id as string | undefined) ??
    "control";
  const treatmentId =
    (trainingJobs.find((job) => String(job.run_id).startsWith("treatment"))?.run_id as string | undefined) ??
    (result?.pair.treatment.run_id as string | undefined) ??
    "treatment";
  const chartData = isLive
    ? buildLiveChartData(trainingJobs)
    : trainingJobs.map((job) => ({
        run: job.run_id,
        reward: Number((job.latest_reward ?? 0).toFixed(2)),
        fall_rate: Number((job.fall_rate ?? 0).toFixed(3)),
      }));

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title={t("training.title")}
        subtitle={t("training.subtitle", {
          controlId,
          treatmentId,
        })}
        right={
          isLive ? (
            <button type="button" onClick={() => refresh()} className="btn btn-ghost px-3 py-1.5">
              {t("live.refreshNow")}
            </button>
          ) : undefined
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {trainingJobs.map((job) => {
          const pct = Math.max(0, Math.min(1, Number(job.progress ?? 0)));
          const runId = job.run_id as string;
          const isTreatment = runId === treatmentId || runId.startsWith("treatment") || job.node === "GPU0";
          const evidenceLabel = presentEvidenceText(
            isLive ? "live_lab" : job.evidence_mode ?? "deterministic_mock"
          );
          return (
            <Card key={job.job_id ?? job.run_id} hoverable className="p-5">
              <div className="mb-3 flex items-center justify-between">
                <div className="min-w-0">
                  <SectionTitle>{displayNodeName(job.node)}</SectionTitle>
                  <div className="mt-0.5 truncate font-mono text-sm font-bold text-ink">
                    {job.run_id}
                  </div>
                </div>
                <Pill tone={isTreatment ? "brand" : "muted"}>
                  {isTreatment ? t("training.treatment") : t("training.control")}
                </Pill>
              </div>
              <div className="mb-4">
                <div className="mb-1 flex items-center justify-between text-[10px] text-faint">
                  <span>{t("training.progress")}</span>
                  <span className="font-mono">{formatProgressPercent(pct)}</span>
                </div>
                <Progress value={pct} tone={pct >= 1 ? "safe" : "brand"} />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <Stat
                  label={t("training.step")}
                  value={(job.latest_step ?? 0).toLocaleString()}
                />
                <Stat
                  label={t("training.reward")}
                  value={(job.latest_reward ?? 0).toFixed(1)}
                />
                <Stat
                  label={t("training.fallRate")}
                  value={(job.fall_rate ?? 0).toFixed(2)}
                />
              </div>
              <div className="mt-3 text-[10px] text-faint">
                {evidenceLabel}
              </div>
            </Card>
          );
        })}
      </div>

      <Card className="p-5">
        <SectionTitle className="mb-3">{t("training.latestSnapshot")}</SectionTitle>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 6, right: 8, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e3e8f0" />
              <XAxis dataKey={isLive ? "step" : "run"} />
              <YAxis yAxisId="left" />
              <YAxis yAxisId="right" orientation="right" />
              <Tooltip />
              <Legend />
              {isLive ? (
                <>
                  <Line yAxisId="left" type="monotone" dataKey="control_reward" stroke="#5c6f8f" strokeWidth={2.2} dot={false} name={`${t("training.control")} ${t("training.reward")}`} />
                  <Line yAxisId="left" type="monotone" dataKey="treatment_reward" stroke="#2f5f9f" strokeWidth={2.5} dot={false} name={`${t("training.treatment")} ${t("training.reward")}`} />
                  <Line yAxisId="right" type="monotone" dataKey="control_fall_rate" stroke="#b96b6b" strokeWidth={2} dot={false} name={`${t("training.control")} ${t("training.fallRate")}`} />
                  <Line yAxisId="right" type="monotone" dataKey="treatment_fall_rate" stroke="#a83232" strokeWidth={2.2} dot={false} name={`${t("training.treatment")} ${t("training.fallRate")}`} />
                </>
              ) : (
                <>
                  <Line yAxisId="left" type="monotone" dataKey="reward" stroke="#2f5f9f" strokeWidth={2.5} dot={{ r: 4 }} name={t("training.reward")} />
                  <Line yAxisId="right" type="monotone" dataKey="fall_rate" stroke="#a83232" strokeWidth={2.5} dot={{ r: 4 }} name={t("training.fallRate")} />
                </>
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-3 text-[11px] text-faint">
          {isLive
            ? "Live Lab mode plots reward and fall-rate history by training iteration."
            : t("training.chartCaption")}
        </p>
      </Card>
    </div>
  );
}

function buildLiveChartData(jobs: Array<{
  run_id: string;
  node: string;
  latest_step?: number;
  latest_reward?: number;
  fall_rate?: number;
  status_history?: Array<[number, string, Record<string, unknown>]>;
}>) {
  const rows = new Map<number, Record<string, number | string>>();

  for (const job of jobs) {
    const role =
      String(job.run_id).startsWith("treatment") || job.node === "GPU0"
        ? "treatment"
        : "control";
    const samples = job.status_history?.length
      ? job.status_history.map((entry) => entry[2])
      : [job];

    for (const sample of samples) {
      const step = Number(sample.latest_step ?? 0);
      const reward = Number(sample.latest_reward ?? 0);
      const fallRate = Number(sample.fall_rate ?? 0);
      if (!Number.isFinite(step)) continue;
      const row = rows.get(step) ?? { step };
      row[`${role}_reward`] = Number(reward.toFixed(2));
      row[`${role}_fall_rate`] = Number(fallRate.toFixed(4));
      rows.set(step, row);
    }
  }

  return Array.from(rows.values()).sort((a, b) => Number(a.step) - Number(b.step));
}
