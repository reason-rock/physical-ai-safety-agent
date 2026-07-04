// Typed fetch wrappers for every backend endpoint. All paths are
// relative to the Next.js dev origin because next.config.mjs rewrites
// /api/* and /sse/* to the FastAPI backend on :8000.

import type {
  HealthResponse,
  HistoryRun,
  LabConfig,
  LabState,
  LabUpdateEvent,
  NodeEntry,
  NodeSnapshot,
  ReplayRun,
  SubmitJobBody,
  WorkflowRequestBody,
  WorkflowResult,
} from "./types";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} — ${text}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => jsonFetch<HealthResponse>("/api/health"),
  nodes: () => jsonFetch<{ nodes: NodeEntry[] }>("/api/nodes"),

  runWorkflow: (body: WorkflowRequestBody) =>
    jsonFetch<WorkflowResult>("/api/workflow", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // Live lab
  labConfig: () => jsonFetch<LabConfig>("/api/lab/config"),
  labSnapshot: () =>
    jsonFetch<{ gpu0: NodeSnapshot; gpu1: NodeSnapshot }>(
      "/api/lab/nodes/snapshot"
    ),
  labState: () => jsonFetch<LabState>("/api/lab/state"),
  labRefresh: () =>
    jsonFetch<LabState>("/api/lab/refresh", { method: "POST" }),
  labReset: () =>
    jsonFetch<{ ok: boolean }>("/api/lab/state", { method: "DELETE" }),

  submitJob: (body: SubmitJobBody) =>
    jsonFetch<LabState["jobs"][number]>("/api/lab/jobs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  jobStatus: (id: string) =>
    jsonFetch<Record<string, unknown>>(`/api/lab/jobs/${id}/status`),
  killJob: (id: string) =>
    jsonFetch<Record<string, unknown>>(`/api/lab/jobs/${id}/kill`, {
      method: "POST",
    }),
  collectJob: (id: string) =>
    jsonFetch<Record<string, unknown>>(`/api/lab/jobs/${id}/collect`, {
      method: "POST",
    }),
  killSession: (host: string, session: string) =>
    jsonFetch<Record<string, unknown>>("/api/lab/sessions/kill", {
      method: "POST",
      body: JSON.stringify({ host, session }),
    }),

  // Replay browser (Sanitized Real Replay mode)
  replayManifest: () =>
    jsonFetch<Record<string, unknown>>("/api/replay/manifest"),
  replayRuns: () =>
    jsonFetch<{ runs: ReplayRun[]; dataset: string; privacy: Record<string, unknown> }>(
      "/api/replay/runs"
    ),
  replayRunFull: (role: string) =>
    jsonFetch<{
      role: string;
      scalars: { role: string; alias: string; rows: Record<string, unknown>[] };
      metrics: Record<string, unknown>;
    }>(`/api/replay/runs/${role}/full`),
  replayCompare: () =>
    jsonFetch<Record<string, unknown>>("/api/replay/compare"),

  // Training history DB (167 runs from GPU0/GPU1)
  historyStats: () =>
    jsonFetch<Record<string, unknown>>("/api/history/stats"),
  historyRuns: (params?: {
    server?: string;
    task?: string;
    min_iter?: number;
    search?: string;
    sort?: string;
    order?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) qs.set(k, String(v));
      }
    }
    return jsonFetch<{ total: number; limit: number; offset: number; runs: HistoryRun[] }>(
      `/api/history/runs?${qs.toString()}`
    );
  },
  historyRunScalarsSummary: (runId: number, tag?: string, buckets?: number) => {
    const qs = new URLSearchParams();
    if (tag) qs.set("tag", tag);
    if (buckets) qs.set("buckets", String(buckets));
    return jsonFetch<{
      run_id: number;
      run_dir: string;
      server: string;
      tag: string;
      total: number;
      points: Array<{ step: number; value: number }>;
    }>(`/api/history/runs/${runId}/scalars/summary?${qs.toString()}`);
  },
  historyRunTags: (runId: number) =>
    jsonFetch<{ run_id: number; tags: Array<{ tag: string; count: number }> }>(
      `/api/history/runs/${runId}/tags`
    ),
};

// SSE subscriber. Returns an unsubscribe function. The onData callback is
// invoked on every "lab-update" event.
export function subscribeLabUpdates(
  onData: (event: LabUpdateEvent) => void,
  onError?: (err: Event) => void
): () => void {
  const src = new EventSource("/sse/lab");
  src.addEventListener("lab-update", (e) => {
    try {
      onData(JSON.parse((e as MessageEvent).data));
    } catch {
      /* ignore parse errors */
    }
  });
  if (onError) src.onerror = onError;
  return () => src.close();
}
