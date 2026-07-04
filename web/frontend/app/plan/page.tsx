"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { useDashboard } from "@/lib/store";
import { Card, EmptyState, PageHeader, Pill, SectionTitle } from "@/components/ui";
import { useAlias } from "@/lib/aliases";
import { presentEvidenceObject, presentEvidenceText, presentNodeRole } from "@/lib/presentation";
import type { JobSummary, SubmitJobBody } from "@/lib/types";

export default function PlanPage() {
  const { t } = useTranslation();
  const result = useDashboard((s) => s.result);
  const evidenceMode = useDashboard((s) => s.evidenceMode);
  const gpu0Name = useAlias("gpu0");
  const gpu1Name = useAlias("gpu1");
  if (!result) {
    return (
      <EmptyState
        title={t("plan.empty")}
        body={t("plan.emptyBody")}
        action={
          <Link href="/run-experiment" className="btn btn-primary">
            {t("plan.goToRun")}
          </Link>
        }
      />
    );
  }

  const { pair, nodes } = result;
  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title={t("plan.title")}
        subtitle={t("plan.subtitle", { pairId: pair.pair_id })}
        right={<Pill tone="brand">{pair.pair_id}</Pill>}
      />

      <Card className="p-5">
        <SectionTitle className="mb-2">{t("plan.hypothesis")}</SectionTitle>
        <p className="text-[15px] leading-relaxed text-ink-soft">{pair.hypothesis}</p>
        {pair.warning && (
          <div className="mt-3 flex items-start gap-2 rounded-md border border-warn-100 bg-warn-50 px-3 py-2 text-xs text-warn-600">
            <span className="pill pill--warn">{t("plan.warning")}</span>
            <span>{pair.warning}</span>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <SectionTitle>{t("plan.control")}</SectionTitle>
            <Pill tone="muted">{gpu1Name}</Pill>
          </div>
          <pre className="overflow-x-auto rounded-md bg-bg p-3 font-mono text-[11px] leading-relaxed text-ink-soft">
            {JSON.stringify(presentEvidenceObject(pair.control), null, 2)}
          </pre>
        </Card>
        <Card className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <SectionTitle>{t("plan.treatment")}</SectionTitle>
            <Pill tone="brand">{gpu0Name}</Pill>
          </div>
          <pre className="overflow-x-auto rounded-md bg-bg p-3 font-mono text-[11px] leading-relaxed text-ink-soft">
            {JSON.stringify(presentEvidenceObject(pair.treatment), null, 2)}
          </pre>
        </Card>
      </div>

      <Card className="p-4">
        <SectionTitle className="mb-3">{t("plan.controlledVariables")}</SectionTitle>
        <div className="flex flex-wrap gap-1.5">
          {pair.controlled_variables.map((v) => (
            <span
              key={v}
              className="rounded-md border border-line bg-bg px-2 py-1 font-mono text-[11px] text-ink-soft"
            >
              {presentEvidenceText(v)}
            </span>
          ))}
        </div>
      </Card>

      {evidenceMode === "Live Lab" && (
        <LiveSubmitPanel
          control={pair.control}
          treatment={pair.treatment}
          controlName={gpu1Name}
          treatmentName={gpu0Name}
        />
      )}

      <Card className="overflow-hidden">
        <div className="border-b border-line px-4 py-3">
          <SectionTitle>{t("plan.configuredNodes")}</SectionTitle>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-bg/60 text-left text-[10px] uppercase tracking-wider text-faint">
              <th className="px-4 py-2 font-bold">{t("plan.name")}</th>
              <th className="px-4 py-2 font-bold">{t("plan.role")}</th>
              <th className="px-4 py-2 font-bold">{t("plan.host")}</th>
              <th className="px-4 py-2 font-bold">{t("plan.status")}</th>
            </tr>
          </thead>
          <tbody>
            {nodes.map((n) => (
              <tr key={n.name} className="border-t border-line/60">
                <td className="px-4 py-2.5 font-mono text-xs text-ink">
                  {presentEvidenceText(n.name)}
                </td>
                <td className="px-4 py-2.5 text-xs text-muted">{presentNodeRole(n.role)}</td>
                <td className="px-4 py-2.5 font-mono text-xs text-muted">
                  {presentEvidenceText(n.host ?? "managed endpoint")}
                </td>
                <td className="px-4 py-2.5">
                  <Pill tone={n.status.includes("blocked") ? "danger" : "safe"}>
                    {presentEvidenceText(n.status).toUpperCase()}
                  </Pill>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function LiveSubmitPanel({
  control,
  treatment,
  controlName,
  treatmentName,
}: {
  control: Record<string, unknown>;
  treatment: Record<string, unknown>;
  controlName: string;
  treatmentName: string;
}) {
  const { t } = useTranslation();
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [message, setMessage] = useState("");
  const [stage, setStage] = useState("managed_baseline");
  const [iterations, setIterations] = useState(5000);
  const [envs, setEnvs] = useState(1024);
  const [cap, setCap] = useState("4h");
  const [seed, setSeed] = useState(0);

  async function submitPlan() {
    setMessage("");
    if (!confirmed) {
      setMessage(t("plan.liveConfirmError", "Check the operator confirmation first."));
      return;
    }
    setBusy(true);
    try {
      const controlBody = buildSubmitBody({
        node: "GPU1",
        run: control,
        fallbackRunId: `control_live_${Math.floor(Date.now() / 1000)}`,
        stage,
        iterations,
        envs,
        cap,
        seed,
        forceEmptyPatch: true,
      });
      const treatmentBody = buildSubmitBody({
        node: "GPU0",
        run: treatment,
        fallbackRunId: `treatment_live_${Math.floor(Date.now() / 1000)}`,
        stage,
        iterations,
        envs,
        cap,
        seed,
      });
      const submitted = await Promise.all([
        api.submitJob(controlBody),
        api.submitJob(treatmentBody),
      ]);
      setJobs(submitted);
      setMessage(
        t("plan.liveSubmitted", "Submitted control and treatment jobs to the live training rigs.")
      );
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="space-y-4 border-warn-100 bg-warn-50/50 p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <SectionTitle className="mb-2">
            {t("plan.liveSubmitTitle", "Send this plan to training PCs")}
          </SectionTitle>
          <p className="max-w-3xl text-sm leading-relaxed text-ink-soft">
            {t(
              "plan.liveSubmitBody",
              "Run Experiment only builds the controlled plan. This button submits the baseline control job to {{controlName}} and the patched treatment job to {{treatmentName}} through the Live Lab adapter.",
              { controlName, treatmentName }
            )}
          </p>
        </div>
        <Link href="/live-control" className="btn btn-secondary whitespace-nowrap px-4 py-2 text-sm">
          {t("plan.openLiveControl", "Open Live Control")}
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <LiveField label={t("live.parentStage", "Parent stage env")}>
          <input
            value={stage}
            onChange={(e) => setStage(e.target.value)}
            className="input font-mono text-xs"
          />
        </LiveField>
        <LiveField label={t("live.maxIterations", "Max iterations")}>
          <input
            type="number"
            min={1}
            max={200000}
            value={iterations}
            onFocus={(e) => e.currentTarget.select()}
            onChange={(e) => setIterations(parseIntegerInput(e.target.value, 1))}
            className="input"
          />
        </LiveField>
        <LiveField label={t("live.numEnvs", "Num envs")}>
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
        </LiveField>
        <LiveField label={t("live.seed", "Seed")}>
          <input
            type="number"
            min={0}
            max={999999}
            value={seed}
            onFocus={(e) => e.currentTarget.select()}
            onChange={(e) => setSeed(parseIntegerInput(e.target.value, 0))}
            className="input"
          />
        </LiveField>
        <LiveField label={t("live.wallClockCap", "Wall-clock cap")}>
          <input
            value={cap}
            onChange={(e) => setCap(e.target.value)}
            className="input"
          />
        </LiveField>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <PlanRunPreview title={t("plan.control", "Control")} node={controlName} run={control} baseline />
        <PlanRunPreview title={t("plan.treatment", "Treatment")} node={treatmentName} run={treatment} />
      </div>

      <label className="flex cursor-pointer items-center gap-2 text-sm text-ink">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
          className="h-4 w-4 accent-warn-500"
        />
        {t("live.operatorConfirm", "I am the operator and emergency stop is ready")}
      </label>

      {message && (
        <div className="rounded-md border border-line bg-white/70 px-3 py-2 text-xs text-muted">
          {message}
        </div>
      )}

      {jobs.length > 0 && (
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {jobs.map((job) => (
            <div key={job.job_id} className="rounded-md border border-line bg-white/70 p-3 text-xs">
              <div className="font-mono font-bold text-ink">{job.run_id}</div>
              <div className="mt-1 text-muted">
                {presentEvidenceText(job.status)} · managed training session
              </div>
            </div>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={submitPlan}
        disabled={busy}
        className="btn btn-primary px-5 py-2.5 text-sm"
      >
        {busy
          ? t("plan.liveSubmitting", "Submitting to training PCs...")
          : t("plan.liveSubmitButton", "Send plan to training PCs")}
      </button>
    </Card>
  );
}

function buildSubmitBody({
  node,
  run,
  fallbackRunId,
  stage,
  iterations,
  envs,
  cap,
  seed,
  forceEmptyPatch = false,
}: {
  node: "GPU0" | "GPU1";
  run: Record<string, unknown>;
  fallbackRunId: string;
  stage: string;
  iterations: number;
  envs: number;
  cap: string;
  seed: number;
  forceEmptyPatch?: boolean;
}): SubmitJobBody {
  return {
    node,
    run_id: stringField(run.run_id, fallbackRunId),
    parent_stage: stage,
    patch: forceEmptyPatch ? null : patchField(run.patch),
    num_envs: envs,
    max_iterations: iterations,
    wall_clock_cap: cap,
    seed,
  };
}

function stringField(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function patchField(value: unknown): Record<string, number | string> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const patch: Record<string, number | string> = {};
  for (const [key, raw] of Object.entries(value)) {
    if (typeof raw === "number" || typeof raw === "string") patch[key] = raw;
  }
  return Object.keys(patch).length ? patch : null;
}

function parseIntegerInput(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function LiveField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="space-y-1">
      <span className="text-[11px] font-bold uppercase tracking-wide text-faint">
        {label}
      </span>
      {children}
    </label>
  );
}

function PlanRunPreview({
  title,
  node,
  run,
  baseline = false,
}: {
  title: string;
  node: string;
  run: Record<string, unknown>;
  baseline?: boolean;
}) {
  const { t } = useTranslation();
  const patch = patchField(run.patch);
  return (
    <div className="rounded-md border border-line bg-white/70 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-xs font-bold text-ink">{title}</div>
        <Pill tone="muted">{node}</Pill>
      </div>
      <div className="font-mono text-[11px] text-muted">
        {presentEvidenceText(stringField(run.run_id, "auto"))}
      </div>
      <div className="mt-2 text-[11px] font-bold uppercase tracking-wide text-faint">
        {baseline ? t("plan.baselinePatchLabel", "Baseline patch") : t("plan.treatmentPatchLabel", "Treatment patch")}
      </div>
      <pre className="mt-2 max-h-28 overflow-auto rounded bg-bg p-2 font-mono text-[10px] leading-relaxed text-ink-soft">
        {baseline
          ? t("plan.baselinePatchEmpty", "No patch. Uses the parent stage exactly as-is.")
          : JSON.stringify(patch ?? {}, null, 2)}
      </pre>
    </div>
  );
}
