import type { JobSummary } from "./types";

const ACTIVE_STATUSES = new Set([
  "starting",
  "submitted",
  "submitted_demo",
  "submitted_live",
  "running",
  "unloading",
]);

export function hasActiveLiveJobs(jobs: JobSummary[]): boolean {
  return jobs.some((job) => {
    const status = String(job.status ?? "").toLowerCase();
    return ACTIVE_STATUSES.has(status);
  });
}

export function shouldHoldFinalLiveEvidence(jobs?: JobSummary[] | null): boolean {
  if (!jobs) return true;
  if (jobs.length === 0) return false;
  if (hasActiveLiveJobs(jobs)) return true;
  return jobs.some((job) => !job.collected);
}

export function formatProgressPercent(progress: number): string {
  const pct = Math.max(0, Math.min(100, progress * 100));
  if (pct > 0 && pct < 1) return `${pct.toFixed(2)}%`;
  if (pct > 0 && pct < 10) return `${pct.toFixed(1)}%`;
  return `${pct.toFixed(0)}%`;
}
