"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { useDashboard } from "@/lib/store";
import { useAlias } from "@/lib/aliases";
import { Card, EmptyState, PageHeader, Pill, SectionTitle, Stat } from "@/components/ui";
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
import type { ReplayRun } from "@/lib/types";

interface FullRun {
  scalars: { rows: Record<string, number>[] };
  metrics: Record<string, number | string | boolean | string[]>;
}

export default function ReplayPage() {
  const { t } = useTranslation();
  const evidenceMode = useDashboard((s) => s.evidenceMode);
  const gpu0Name = useAlias("gpu0");
  const gpu1Name = useAlias("gpu1");
  const [runs, setRuns] = useState<ReplayRun[]>([]);
  const [fullRuns, setFullRuns] = useState<Record<string, FullRun>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    Promise.all([api.replayRuns(), api.replayCompare()])
      .then(([runsRes, compareRes]) => {
        setRuns(runsRes.runs);
        const full: Record<string, FullRun> = {};
        for (const run of runsRes.runs) {
          const key = run.role;
          const data = (compareRes as Record<string, unknown>)[key] as
            | { scalars?: { rows: Record<string, number>[] }; metrics?: Record<string, unknown> }
            | undefined;
          if (data?.scalars && data?.metrics) {
            full[key] = {
              scalars: { rows: data.scalars.rows as Record<string, number>[] },
              metrics: data.metrics as Record<string, number | string | boolean | string[]>,
            };
          }
        }
        setFullRuns(full);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  if (evidenceMode !== "Sanitized Real Replay") {
    return (
      <EmptyState
        title={t("replay.notInReplay")}
        body={t("replay.notInReplayBody")}
      />
    );
  }

  if (loading) {
    return <Card className="p-8 text-center text-sm text-muted">{t("replay.loading")}</Card>;
  }

  if (error) {
    return (
      <Card className="border-danger-100 bg-danger-50/60 p-4 text-sm text-danger-600">
        {error}
      </Card>
    );
  }

  // Build comparison chart data from scalars.
  const controlScalars = fullRuns["control"]?.scalars.rows ?? [];
  const treatmentScalars = fullRuns["treatment"]?.scalars.rows ?? [];
  const chartData = mergeScalars(controlScalars, treatmentScalars);

  const controlMetrics = fullRuns["control"]?.metrics;
  const treatmentMetrics = fullRuns["treatment"]?.metrics;

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title={t("replay.title")}
        subtitle={t("replay.subtitle")}
        right={<Pill tone="brand">{runs.length} {t("replay.runs")}</Pill>}
      />

      {/* Run cards */}
      <section className="space-y-3">
        <SectionTitle>{t("replay.availableRuns")}</SectionTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {runs.map((run) => {
            const metrics = fullRuns[run.role]?.metrics;
            return (
              <Card key={run.role} hoverable className="p-5">
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <SectionTitle>
                      {run.role === "control" ? gpu1Name : gpu0Name}
                    </SectionTitle>
                    <div className="mt-0.5 font-mono text-sm font-bold text-ink">
                      {run.alias}
                    </div>
                  </div>
                  <Pill tone={run.role === "treatment" ? "brand" : "muted"}>
                    {run.role}
                  </Pill>
                </div>
                <div className="mb-3 grid grid-cols-3 gap-3 border-y border-line py-3">
                  <Stat
                    label={t("replay.rows")}
                    value={run.rows.toLocaleString()}
                    hint={t("replay.csvRows")}
                  />
                  <Stat
                    label={t("replay.duration")}
                    value={`${run.duration_sec.toFixed(1)}s`}
                  />
                  <Stat
                    label={t("replay.fallFree")}
                    value={
                      metrics
                        ? `${metrics.fall_free_count}/${metrics.num_rollouts}`
                        : "—"
                    }
                  />
                </div>
                {metrics && (
                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <MetricRow
                      label={t("replay.reward")}
                      value={(metrics as Record<string, number>).reward?.toFixed(1)}
                    />
                    <MetricRow
                      label={t("replay.velocity")}
                      value={(metrics as Record<string, number>).avg_velocity?.toFixed(3)}
                    />
                    <MetricRow
                      label={t("replay.torsoPitch")}
                      value={(metrics as Record<string, number>).torso_pitch_rms?.toFixed(3)}
                    />
                    <MetricRow
                      label={t("replay.jointLimit")}
                      value={(metrics as Record<string, number>).joint_limit_max_ratio?.toFixed(3)}
                    />
                  </div>
                )}
                <div className="mt-3 text-[10px] text-faint">
                  {t("replay.source")} {run.source_kind}
                </div>
              </Card>
            );
          })}
        </div>
      </section>

      {/* Comparison chart */}
      {chartData.length > 0 && (
        <Card className="p-5">
          <SectionTitle className="mb-3">{t("replay.trainingCurves")}</SectionTitle>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <ChartBlock
              title={t("replay.rewardTitle")}
              data={chartData}
              dataKeys={[
                { key: "control_reward", name: gpu1Name, color: "#5a6779" },
                { key: "treatment_reward", name: gpu0Name, color: "#2f5f9f" },
              ]}
            />
            <ChartBlock
              title={t("replay.fallRateTitle")}
              data={chartData}
              dataKeys={[
                { key: "control_fall_rate", name: gpu1Name, color: "#5a6779" },
                { key: "treatment_fall_rate", name: gpu0Name, color: "#2f5f9f" },
              ]}
            />
            <ChartBlock
              title={t("replay.torsoPitchRms")}
              data={chartData}
              dataKeys={[
                { key: "control_pitch", name: gpu1Name, color: "#5a6779" },
                { key: "treatment_pitch", name: gpu0Name, color: "#2f5f9f" },
              ]}
            />
            <ChartBlock
              title={t("replay.energyProxy")}
              data={chartData}
              dataKeys={[
                { key: "control_energy", name: gpu1Name, color: "#5a6779" },
                { key: "treatment_energy", name: gpu0Name, color: "#2f5f9f" },
              ]}
            />
          </div>
        </Card>
      )}

      {/* Eval comparison table */}
      {controlMetrics && treatmentMetrics && (
        <Card className="overflow-hidden">
          <div className="border-b border-line px-4 py-3">
            <SectionTitle>{t("replay.evalComparison")}</SectionTitle>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-bg/60 text-left text-[10px] uppercase tracking-wider text-faint">
                <th className="px-4 py-2 font-bold">{t("replay.metric")}</th>
                <th className="px-4 py-2 font-bold">
                  {gpu1Name} {t("replay.controlSuffix")}
                </th>
                <th className="px-4 py-2 font-bold">
                  {gpu0Name} {t("replay.treatmentSuffix")}
                </th>
              </tr>
            </thead>
            <tbody>
              {[
                "fall_free_count",
                "avg_fall_time_sec",
                "avg_velocity",
                "torso_pitch_rms",
                "energy_proxy",
                "joint_limit_max_ratio",
                "foot_contact_symmetry",
              ].map((key) => (
                <tr key={key} className="border-t border-line/60">
                  <td className="px-4 py-2.5 text-xs text-ink-soft">{key}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-muted">
                    {fmtMetric(controlMetrics[key])}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs font-bold text-ink">
                    {fmtMetric(treatmentMetrics[key])}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* Metric notes */}
      {treatmentMetrics?.metric_notes && (
        <Card className="p-4">
          <SectionTitle className="mb-2">{t("replay.metricNotes")}</SectionTitle>
          <ul className="space-y-1 text-[11px] text-muted">
            {(treatmentMetrics.metric_notes as string[]).map((note, i) => (
              <li key={i} className="border-l-2 border-line pl-2">{note}</li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function mergeScalars(
  control: Record<string, number>[],
  treatment: Record<string, number>[]
): Array<Record<string, number>> {
  // Match by step. Both runs should have the same 5 steps.
  const byStep = new Map<number, Record<string, number>>();
  for (const row of control) {
    const step = row.step;
    const entry = byStep.get(step) ?? { step };
    entry.control_reward = row.reward;
    entry.control_fall_rate = row.fall_rate;
    entry.control_pitch = row.torso_pitch_rms;
    entry.control_energy = row.energy_proxy;
    byStep.set(step, entry);
  }
  for (const row of treatment) {
    const step = row.step;
    const entry = byStep.get(step) ?? { step };
    entry.treatment_reward = row.reward;
    entry.treatment_fall_rate = row.fall_rate;
    entry.treatment_pitch = row.torso_pitch_rms;
    entry.treatment_energy = row.energy_proxy;
    byStep.set(step, entry);
  }
  return Array.from(byStep.values()).sort((a, b) => a.step - b.step);
}

function ChartBlock({
  title,
  data,
  dataKeys,
}: {
  title: string;
  data: Array<Record<string, number>>;
  dataKeys: Array<{ key: string; name: string; color: string }>;
}) {
  return (
    <div>
      <div className="mb-2 text-xs font-bold text-ink">{title}</div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e3e8f0" />
            <XAxis
              dataKey="step"
              tickFormatter={(v) => `${(v / 1e6).toFixed(0)}M`}
            />
            <YAxis />
            <Tooltip
              labelFormatter={(v) => `step ${Number(v).toLocaleString()}`}
            />
            <Legend />
            {dataKeys.map((dk) => (
              <Line
                key={dk.key}
                type="monotone"
                dataKey={dk.key}
                name={dk.name}
                stroke={dk.color}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function MetricRow({ label, value }: { label: string; value: string | undefined }) {
  return (
    <div className="flex justify-between">
      <span className="text-faint">{label}</span>
      <span className="font-mono text-ink-soft">{value ?? "—"}</span>
    </div>
  );
}

function fmtMetric(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return v.toFixed(3);
  return String(v);
}
