"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { useLabUpdates } from "@/lib/sse";
import type { JobSummary, LabConfig } from "@/lib/types";
import { CellCard } from "@/components/CellCard";
import { Card, PageHeader, Pill, Progress, SectionTitle, Stat } from "@/components/ui";
import { useAlias } from "@/lib/aliases";
import { presentEvidenceText } from "@/lib/presentation";

export default function LiveControlPage() {
  const { t } = useTranslation();
  const [config, setConfig] = useState<LabConfig | null>(null);
  const [auto, setAuto] = useState(true);
  const [error, setError] = useState("");
  const { latest, refresh } = useLabUpdates(auto);
  const gpu0Name = useAlias("gpu0");
  const gpu1Name = useAlias("gpu1");

  useEffect(() => {
    api.labConfig().then(setConfig).catch((e) => setError(String(e)));
  }, []);

  if (!config) {
    return (
      <Card className="p-8 text-center text-sm text-muted">
        {error ? `Lab config error: ${error}` : t("live.loading")}
      </Card>
    );
  }

  if (!config.enabled) {
    return (
      <Card className="border-warn-100 bg-warn-50/50 p-6">
        <h1 className="text-lg font-bold text-warn-600">{t("live.notEnabled")}</h1>
        <p className="mt-1 text-sm text-warn-600/90">
          Lab monitoring is not enabled for this environment. Check the local
          operator configuration and reload.
        </p>
      </Card>
    );
  }

  const nodes = latest?.nodes ?? {};
  const jobs = latest?.jobs ?? [];
  const lastUpdate = latest?.ts ? new Date(latest.ts * 1000).toLocaleTimeString() : "?";

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title={t("live.title")}
        subtitle={t("live.subtitleTpl", { gpu0: gpu0Name, gpu1: gpu1Name })}
        right={
          <div className="flex items-center gap-2">
            <Pill tone={auto ? "safe" : "muted"}>
              {auto ? t("live.autoRefresh") : t("live.manual")}
            </Pill>
            <span className="text-[10px] text-faint">
              {t("live.last")} {lastUpdate}
            </span>
            <label className="ml-1 flex items-center gap-1.5 text-[11px] text-muted">
              <input
                type="checkbox"
                checked={auto}
                onChange={(e) => setAuto(e.target.checked)}
                className="h-3.5 w-3.5 accent-brand-500"
              />
              {t("live.auto")}
            </label>
            <button
              type="button"
              onClick={() => refresh()}
              className="btn btn-ghost px-3 py-1.5"
            >
              {t("live.refreshNow")}
            </button>
          </div>
        }
      />

      <Card className="border-warn-100 bg-warn-50/40 p-3 text-xs text-warn-600">
        <strong>
          {t("live.warning")}
        </strong>{" "}
        {t("live.warningBody", { gpu0: gpu0Name, gpu1: gpu1Name })}{" "}
        <code className="font-mono">audit log</code>.
      </Card>

      {/* Cell cards */}
      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <CellCard snap={nodes.gpu0 ?? emptySnap("GPU0", config.gpu0_host)} />
        <CellCard snap={nodes.gpu1 ?? emptySnap("GPU1", config.gpu1_host)} />
      </section>

      {/* Tracked jobs */}
      <section className="space-y-3">
        <div className="flex items-baseline justify-between">
          <SectionTitle>
            {t("live.trackedJobs")} ({jobs.length})
          </SectionTitle>
          {jobs.length > 0 && (
            <button
              type="button"
              onClick={() => api.labReset().then(() => refresh())}
              className="text-[11px] text-muted underline-offset-2 hover:underline"
            >
              {t("live.clearHistory")}
            </button>
          )}
        </div>
        {jobs.length === 0 ? (
          <Card className="p-4 text-xs text-faint">{t("live.noJobs")}</Card>
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {jobs.map((job) => (
              <JobCard key={job.job_id} job={job} onRefresh={refresh} />
            ))}
          </div>
        )}
      </section>

      {/* Submit form */}
      <SubmitForm />
    </div>
  );
}

function JobCard({
  job,
  onRefresh,
}: {
  job: JobSummary;
  onRefresh: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const nodeName = useAlias(job.node);

  const pct = Math.max(0, Math.min(1, job.progress)) * 100;
  const inactiveStatuses = new Set([
    "completed",
    "completed_mock",
    "stopped",
    "killed_by_operator",
  ]);
  const canKill = !inactiveStatuses.has(job.status);
  const tone =
    job.status === "completed" ||
    job.status === "completed_mock" ||
    job.status === "stopped" ||
    job.status === "killed_by_operator"
      ? "safe"
      : job.status === "running" || job.status === "submitted_live"
        ? "brand"
        : "danger";

  async function call(
    fn: () => Promise<unknown>,
    label: string,
    successMessage?: (res: unknown) => string
  ) {
    setBusy(true);
    setMsg("");
    try {
      const res = await fn();
      await onRefresh();
      setMsg(successMessage ? successMessage(res) : `${label} OK`);
    } catch (e) {
      setMsg(`${label} failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  const history = (job.status_history ?? [])
    .filter((h) => typeof h[2]?.latest_reward === "number")
    .map((h, idx) => ({
      idx,
      reward: Number((h[2] as { latest_reward?: number }).latest_reward ?? 0),
    }));

  return (
    <Card hoverable className="p-5">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Pill tone={tone}>{presentEvidenceText(job.status)}</Pill>
        <span className="text-sm font-bold text-ink">
          {nodeName} / {job.run_id}
        </span>
      </div>
      <div className="mb-3 text-[11px] text-muted">
        {t("live.stageLabel")}:{" "}
        <code className="break-all font-mono">{presentEvidenceText(job.stage_name)}</code> /{" "}
        {t("live.iterLabel")} <strong>{job.latest_step}</strong> / {job.max_iterations}
      </div>

      <div className="mb-3">
        <Progress value={pct / 100} tone={pct >= 100 ? "safe" : "brand"} />
      </div>

      <div className="mb-3 grid grid-cols-3 gap-3 border-y border-line py-3">
        <Stat label={t("live.rewardStat")} value={job.latest_reward.toFixed(1)} />
        <Stat label={t("live.fallRateStat")} value={job.fall_rate.toFixed(3)} />
        <Stat label={t("live.iterStat")} value={job.latest_step} />
      </div>

      {history.length >= 2 && <RewardSpark history={history} />}

      <div className="mt-4 grid grid-cols-3 gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => call(() => api.jobStatus(job.job_id), t("live.btnRefresh"))}
          className="btn btn-ghost"
        >
          {t("live.btnRefresh")}
        </button>
        <button
          type="button"
          disabled={busy || !canKill}
          onClick={() => call(() => api.killJob(job.job_id), t("live.btnKill"))}
          className="btn btn-danger"
        >
          {t("live.btnKill")}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            call(
              () => api.collectJob(job.job_id),
              t("live.btnCollect"),
              (res) => {
                const runId =
                  typeof res === "object" && res && "run_id" in res
                    ? String((res as { run_id?: unknown }).run_id ?? job.run_id)
                    : job.run_id;
                return `Collect OK: artifacts indexed for ${runId}`;
              }
            )
          }
          className="btn btn-brand-soft"
        >
          {t("live.btnCollect")}
        </button>
      </div>
      {msg && <div className="mt-2 break-all text-[11px] text-muted">{msg}</div>}
    </Card>
  );
}

function RewardSpark({
  history,
}: {
  history: Array<{ idx: number; reward: number }>;
}) {
  const { t } = useTranslation();
  if (history.length < 2) return null;
  const w = 240;
  const h = 40;
  const xs = history.map((_, i) => (i / (history.length - 1)) * w);
  const rewards = history.map((p) => p.reward);
  const min = Math.min(...rewards);
  const max = Math.max(...rewards);
  const range = max - min || 1;
  const ys = rewards.map((r) => h - ((r - min) / range) * (h - 6) - 3);
  const d = xs
    .map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${ys[i].toFixed(1)}`)
    .join(" ");
  return (
    <div className="mb-3">
      <SectionTitle className="mb-1">{t("live.rewardHistory")}</SectionTitle>
      <svg width={w} height={h} className="block">
        <path d={d} fill="none" stroke="#2f5f9f" strokeWidth={1.5} />
      </svg>
    </div>
  );
}

function SubmitForm() {
  const { t } = useTranslation();
  const [node, setNode] = useState<"GPU0" | "GPU1">("GPU0");
  const gpu0Name = useAlias("gpu0");
  const gpu1Name = useAlias("gpu1");
  const [stage, setStage] = useState("managed_baseline");
  const [iters, setIters] = useState(5000);
  const [envs, setEnvs] = useState(1024);
  const [patch, setPatch] = useState("");
  const [seed, setSeed] = useState(0);
  const [cap, setCap] = useState("4h");
  const [runId, setRunId] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMsg("");
    if (!confirm) {
      setMsg(t("live.errorCheckOperator"));
      return;
    }
    let parsedPatch: Record<string, number | string> | null = null;
    if (patch.trim()) {
      try {
        parsedPatch = JSON.parse(patch);
      } catch (err) {
        setMsg(
          `${t("live.errorInvalidPatch")} ${err instanceof Error ? err.message : String(err)}`
        );
        return;
      }
    }
    setBusy(true);
    try {
      const id = runId.trim() || `live_${Math.floor(Date.now() / 1000)}`;
      const res = await api.submitJob({
        node,
        run_id: id,
        parent_stage: stage,
        patch: parsedPatch,
        num_envs: envs,
        max_iterations: iters,
        wall_clock_cap: cap,
        seed,
      });
      setMsg(
        `${t("live.submittedJob")} ${(res as { job_id?: string }).job_id ?? id}`
      );
      setRunId("");
      setPatch("");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-5">
      <SectionTitle className="mb-4">{t("live.submitNew")}</SectionTitle>
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Field label={t("live.targetNode")}>
            <select
              value={node}
              onChange={(e) => setNode(e.target.value as "GPU0" | "GPU1")}
              className="select"
            >
              <option value="GPU0">{gpu0Name}</option>
              <option value="GPU1">{gpu1Name}</option>
            </select>
          </Field>
          <Field label={t("live.parentStage")}>
            <input
              type="text"
              value={stage}
              onChange={(e) => setStage(e.target.value)}
              className="input font-mono text-xs"
            />
          </Field>
          <Field label={t("live.maxIterations")}>
            <input
              type="number"
              min={1}
              max={200000}
              value={iters}
              onFocus={(e) => e.currentTarget.select()}
              onChange={(e) => setIters(parseIntegerInput(e.target.value, 1))}
              className="input"
            />
          </Field>
          <Field label={t("live.numEnvs")}>
            <input
              type="number"
              min={64}
              max={65536}
              step={64}
              value={envs}
              onFocus={(e) => e.currentTarget.select()}
              onChange={(e) => setEnvs(parseIntegerInput(e.target.value, 64))}
              className="input"
            />
          </Field>
          <Field label={t("live.treatmentPatch")} className="md:col-span-2">
            <input
              type="text"
              value={patch}
              onChange={(e) => setPatch(e.target.value)}
              placeholder='{"reward.orientation_penalty": 1.3}'
              className="input font-mono text-xs"
            />
          </Field>
          <Field label={t("live.seed")}>
            <input
              type="number"
              min={0}
              max={999999}
              value={seed}
              onFocus={(e) => e.currentTarget.select()}
              onChange={(e) => setSeed(parseIntegerInput(e.target.value, 0))}
              className="input"
            />
          </Field>
          <Field label={t("live.wallClockCap")}>
            <input
              type="text"
              value={cap}
              onChange={(e) => setCap(e.target.value)}
              className="input"
            />
          </Field>
          <Field label={t("live.runIdSuffix")} className="md:col-span-4">
            <input
              type="text"
              value={runId}
              onChange={(e) => setRunId(e.target.value)}
              placeholder="auto"
              className="input"
            />
          </Field>
        </div>

        <label className="flex cursor-pointer items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={confirm}
            onChange={(e) => setConfirm(e.target.checked)}
            className="h-4 w-4 accent-warn-500"
          />
          {t("live.operatorConfirm")}
        </label>

        {msg && (
          <div className="rounded-md border border-line bg-bg px-3 py-2 text-xs text-muted">
            {msg}
          </div>
        )}

        <button
          type="submit"
          disabled={busy}
          className="btn btn-primary px-5 py-2.5 text-sm"
        >
          {busy ? t("live.submitting") : t("live.submit")}
        </button>
      </form>
    </Card>
  );
}

function parseIntegerInput(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function Field({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={`block ${className ?? ""}`}>
      <span className="section-title mb-1 block">{label}</span>
      {children}
    </label>
  );
}

function emptySnap(label: string, host: string) {
  return {
    label,
    host,
    reachable: false,
    error: "waiting for first snapshot",
    ts: 0,
  };
}

