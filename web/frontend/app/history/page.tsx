"use client";

import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { useAlias } from "@/lib/aliases";
import { presentEvidenceText } from "@/lib/presentation";
import { Card, PageHeader, Pill, SectionTitle, Stat } from "@/components/ui";
import type { HistoryRun } from "@/lib/types";
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

const PAGE_SIZE = 25;
const CHART_TAG = "Train/mean_reward";

function presentTaskName(task: string): string {
  const clean = presentEvidenceText(task)
    .replace("darwin_op_walk_", "")
    .replace("_direct", "")
    .replaceAll("_", " ");
  if (clean === "free") return "locomotion";
  if (clean === "rule ref") return "reference tracking";
  if (clean === "direct") return "direct locomotion";
  return clean;
}

export default function HistoryPage() {
  const { t } = useTranslation();
  const gpu0Name = useAlias("gpu0");
  const gpu1Name = useAlias("gpu1");

  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [runs, setRuns] = useState<HistoryRun[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  // Filters
  const [serverFilter, setServerFilter] = useState<string>("");
  const [taskFilter, setTaskFilter] = useState<string>("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("start_ts");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(0);

  // Selected run for detail modal
  const [selectedRun, setSelectedRun] = useState<HistoryRun | null>(null);

  // Multi-select for comparison
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [showCompare, setShowCompare] = useState(false);

  // Cache all fetched runs so the compare modal can look them up across pages.
  const [allRunsMap, setAllRunsMap] = useState<Map<number, HistoryRun>>(new Map());

  // Update cache whenever runs change.
  useEffect(() => {
    setAllRunsMap((prev) => {
      const next = new Map(prev);
      for (const r of runs) next.set(r.id, r);
      return next;
    });
  }, [runs]);

  const fetchRuns = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.historyRuns({
        server: serverFilter || undefined,
        task: taskFilter || undefined,
        search: search || undefined,
        sort,
        order,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setRuns(res.runs);
      setTotal(res.total);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [serverFilter, taskFilter, search, sort, order, page]);

  useEffect(() => {
    api.historyStats().then(setStats).catch(() => void 0);
  }, []);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  // Reset to page 0 when filters change.
  useEffect(() => {
    setPage(0);
  }, [serverFilter, taskFilter, search, sort, order]);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  function toggleSelect(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const serverName = (s: string) => (s === "gpu0" ? gpu0Name : gpu1Name);

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title={t("history.title")}
        subtitle={t("history.subtitle")}
        right={
          <div className="flex items-center gap-2">
            <Pill tone="brand">
              {total} {t("history.compareRuns")}
            </Pill>
            {stats && (
              <Pill tone="muted">
                {Number(stats.total_scalars).toLocaleString()} {t("history.events")}
              </Pill>
            )}
          </div>
        }
      />

      {/* Stats strip */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          <Card className="p-4">
            <Stat label={t("history.totalRuns")} value={Number(stats.total_runs)} />
          </Card>
          {(stats.by_server as Array<Record<string, unknown>>)?.map((srv) => (
            <Card key={srv.server as string} className="p-4">
              <Stat
                label={serverName(srv.server as string)}
                value={srv.runs as number}
                hint={`${Number(srv.events).toLocaleString()} ${t("history.events")}`}
              />
            </Card>
          ))}
          <Card className="p-4">
            <Stat
              label={t("history.bestReward")}
              value={
                (stats.best_reward as Record<string, unknown>)?.final_reward != null
                  ? Number((stats.best_reward as Record<string, unknown>).final_reward).toFixed(1)
                  : "—"
              }
              hint={(stats.best_reward as Record<string, unknown>)?.run_dir as string}
            />
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card className="p-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
          <div>
            <SectionTitle className="mb-1">{t("history.server")}</SectionTitle>
            <select
              value={serverFilter}
              onChange={(e) => setServerFilter(e.target.value)}
              className="select"
            >
              <option value="">{t("history.all")}</option>
              <option value="gpu0">{gpu0Name}</option>
              <option value="gpu1">{gpu1Name}</option>
            </select>
          </div>
          <div>
            <SectionTitle className="mb-1">{t("history.task")}</SectionTitle>
            <select
              value={taskFilter}
              onChange={(e) => setTaskFilter(e.target.value)}
              className="select"
            >
              <option value="">{t("history.all")}</option>
              <option value="darwin_op_walk_free_direct">locomotion</option>
              <option value="darwin_op_walk_rule_ref_direct">reference tracking</option>
              <option value="darwin_op_walk_direct">direct locomotion</option>
            </select>
          </div>
          <div>
            <SectionTitle className="mb-1">{t("history.search")}</SectionTitle>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("history.runDirPlaceholder")}
              className="input font-mono text-xs"
            />
          </div>
          <div>
            <SectionTitle className="mb-1">{t("history.sort")}</SectionTitle>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="select"
            >
              <option value="start_ts">{t("history.date")}</option>
              <option value="max_iteration">{t("history.iterations")}</option>
              <option value="final_reward">{t("history.reward")}</option>
              <option value="num_checkpoints">{t("history.checkpoints")}</option>
            </select>
          </div>
          <div>
            <SectionTitle className="mb-1">{t("history.order")}</SectionTitle>
            <button
              type="button"
              onClick={() => setOrder((o) => (o === "desc" ? "asc" : "desc"))}
              className="select text-center"
            >
              {order === "desc" ? t("history.descArrow") : t("history.ascArrow")}
            </button>
          </div>
        </div>
        {(selectedIds.size > 0 || search || serverFilter || taskFilter) && (
          <div className="mt-3 flex items-center gap-2 text-xs text-muted">
            {selectedIds.size > 0 && (
              <span className="pill pill--brand">
                {selectedIds.size} {t("history.selectedForCompare")}
              </span>
            )}
            {(search || serverFilter || taskFilter) && (
              <button
                type="button"
                onClick={() => {
                  setSearch("");
                  setServerFilter("");
                  setTaskFilter("");
                }}
                className="text-brand-600 hover:underline"
              >
                {t("history.clearFilters")}
              </button>
            )}
          </div>
        )}
      </Card>

      {/* Run table */}
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line bg-bg/60 text-left text-[10px] uppercase tracking-wider text-faint">
                <th className="w-8 px-3 py-2 font-bold">✓</th>
                <th className="px-3 py-2 font-bold">{t("history.server")}</th>
                <th className="px-3 py-2 font-bold">{t("history.runDir")}</th>
                <th className="px-3 py-2 text-right font-bold">{t("history.iter")}</th>
                <th className="px-3 py-2 text-right font-bold">{t("history.reward")}</th>
                <th className="px-3 py-2 text-right font-bold">{t("history.ckpts")}</th>
                <th className="px-3 py-2 text-right font-bold">{t("history.eventsCol")}</th>
                <th className="px-3 py-2 font-bold">{t("history.task")}</th>
                <th className="px-3 py-2 font-bold">Stage</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-muted">
                    {t("history.loading")}
                  </td>
                </tr>
              ) : runs.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-muted">
                    {t("history.noRuns")}
                  </td>
                </tr>
              ) : (
                runs.map((run) => (
                  <tr
                    key={run.id}
                    className={`cursor-pointer border-t border-line/60 transition hover:bg-bg/40 ${
                      selectedIds.has(run.id) ? "bg-brand-50/40" : ""
                    }`}
                    onClick={() => setSelectedRun(run)}
                  >
                    <td
                      className="px-3 py-2"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleSelect(run.id);
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedIds.has(run.id)}
                        onChange={() => toggleSelect(run.id)}
                        onClick={(e) => e.stopPropagation()}
                        className="h-3.5 w-3.5 accent-brand-500"
                      />
                    </td>
                    <td className="px-3 py-2 text-xs">
                      <Pill tone={run.server === "gpu0" ? "brand" : "muted"}>
                        {serverName(run.server)}
                      </Pill>
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px] text-ink">
                      {presentEvidenceText(run.run_dir)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs text-muted">
                      {run.max_iteration.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs font-bold text-ink">
                      {run.final_reward.toFixed(1)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs text-muted">
                      {run.num_checkpoints}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-[10px] text-faint">
                      {run.num_events > 0
                        ? `${(run.num_events / 1000).toFixed(0)}k`
                        : "—"}
                    </td>
                    <td className="px-3 py-2 text-[10px] text-faint">
                      {presentTaskName(run.task)}
                    </td>
                    <td className="px-3 py-2 font-mono text-[10px] text-ink-soft">
                      {run.stage_tag || "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-line px-4 py-2 text-xs text-muted">
            <span>
              {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} / {total}
            </span>
            <div className="flex gap-1">
              <button
                type="button"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
                className="rounded border border-line px-2 py-1 disabled:opacity-40"
              >
                ←
              </button>
              <span className="px-2 py-1">{page + 1} / {totalPages}</span>
              <button
                type="button"
                disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => p + 1)}
                className="rounded border border-line px-2 py-1 disabled:opacity-40"
              >
                →
              </button>
            </div>
          </div>
        )}
      </Card>

      {/* Comparison bar */}
      {selectedIds.size > 0 && (
        <Card className="flex flex-wrap items-center justify-between gap-3 border-brand-100 bg-brand-50/30 p-3">
          <div className="flex items-center gap-2 text-sm">
            <Pill tone="brand">
              {selectedIds.size} {t("history.selected")}
            </Pill>
            {selectedIds.size < 2 && (
              <span className="text-xs text-faint">{t("history.selectMore")}</span>
            )}
            {selectedIds.size > 10 && (
              <span className="text-xs text-warn-600">{t("history.maxReached")}</span>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setSelectedIds(new Set())}
              className="btn btn-ghost px-3 py-1.5 text-xs"
            >
              {t("history.clear")}
            </button>
            {selectedIds.size >= 2 && selectedIds.size <= 10 && (
              <button
                type="button"
                onClick={() => setShowCompare(true)}
                className="btn btn-primary px-4 py-1.5 text-xs"
              >
                {t("history.compare")} {selectedIds.size} {t("history.compareRuns")} →
              </button>
            )}
          </div>
        </Card>
      )}

      {/* Comparison modal */}
      {showCompare && (
        <CompareModal
          runIds={Array.from(selectedIds)}
          allRuns={allRunsMap}
          serverName={serverName}
          onClose={() => setShowCompare(false)}
        />
      )}

      {/* Detail modal */}
      {selectedRun && (
        <RunDetailModal
          run={selectedRun}
          serverName={serverName}
          onClose={() => setSelectedRun(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail modal: shows one run's reward curve + all scalar tags
// ---------------------------------------------------------------------------

function RunDetailModal({
  run,
  serverName,
  onClose,
}: {
  run: HistoryRun;
  serverName: (s: string) => string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [chartData, setChartData] = useState<Array<{ step: number; value: number }>>([]);
  const [tags, setTags] = useState<Array<{ tag: string; count: number }>>([]);
  const [selectedTag, setSelectedTag] = useState(CHART_TAG);
  const [loadingChart, setLoadingChart] = useState(true);

  useEffect(() => {
    setLoadingChart(true);
    api
      .historyRunScalarsSummary(run.id, selectedTag, 150)
      .then((res) => setChartData(res.points))
      .catch(() => setChartData([]))
      .finally(() => setLoadingChart(false));
  }, [run.id, selectedTag]);

  useEffect(() => {
    api
      .historyRunTags(run.id)
      .then((r) => setTags(r.tags))
      .catch(() => void 0);
  }, [run.id]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-panel shadow-panel"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <div>
            <div className="flex items-center gap-2">
              <Pill tone={run.server === "gpu0" ? "brand" : "muted"}>
                {serverName(run.server)}
              </Pill>
              <span className="font-mono text-sm font-bold text-ink">
                {presentEvidenceText(run.run_dir)}
              </span>
            </div>
            <div className="mt-0.5 text-[10px] text-faint">{presentTaskName(run.task)}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-faint hover:bg-bg hover:text-ink"
          >
            ✕
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-3 border-b border-line px-5 py-3">
          <Stat label={t("history.iteration")} value={run.max_iteration.toLocaleString()} />
          <Stat label={t("history.finalReward")} value={run.final_reward.toFixed(2)} />
          <Stat label={t("history.epLengthShort")} value={run.final_ep_len.toFixed(0)} />
          <Stat label={t("history.checkpoints")} value={run.num_checkpoints} />
        </div>

        {/* Policy info: stage, git commit, reward terms */}
        {(run.stage_tag || run.git_commit || run.reward_terms) && (
          <div className="border-b border-line px-5 py-3">
            {run.stage_tag && (
              <div className="mb-2 flex items-center gap-2">
                <SectionTitle>Stage</SectionTitle>
                <span className="font-mono text-xs font-bold text-ink">{run.stage_tag}</span>
                {run.git_commit && (
                  <span className="font-mono text-[10px] text-faint">git: {run.git_commit}</span>
                )}
              </div>
            )}
            {run.reward_terms && (() => {
              try {
                const terms = JSON.parse(run.reward_terms);
                const entries = Object.entries(terms) as [string, number][];
                if (entries.length === 0) return null;
                // Sort by absolute value descending.
                entries.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
                return (
                  <div>
                    <SectionTitle className="mb-1">
                      Reward terms (last iter, top {Math.min(entries.length, 15)})
                    </SectionTitle>
                    <div className="flex flex-wrap gap-1">
                      {entries.slice(0, 15).map(([name, value]) => (
                        <span
                          key={name}
                          className={`rounded-md border px-1.5 py-0.5 font-mono text-[10px] ${
                            value > 0
                              ? "border-safe-100 bg-safe-50 text-safe-600"
                              : value < 0
                                ? "border-danger-100 bg-danger-50 text-danger-600"
                                : "border-line bg-bg text-faint"
                          }`}
                          title={`${name} = ${value}`}
                        >
                          {name.length > 25 ? name.slice(0, 22) + "…" : name}: {value}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              } catch {
                return null;
              }
            })()}
          </div>
        )}

        {/* Chart */}
        <div className="px-5 py-3">
          <div className="mb-2 flex items-center justify-between">
            <SectionTitle>{t("history.rewardCurve")}</SectionTitle>
            <select
              value={selectedTag}
              onChange={(e) => setSelectedTag(e.target.value)}
              className="select max-w-xs text-xs"
            >
              <option value="Train/mean_reward">Train/mean_reward</option>
              <option value="Train/mean_episode_length">Train/mean_episode_length</option>
              {tags
                .filter((t) => !t.tag.startsWith("Train/"))
                .slice(0, 50)
                .map((t) => (
                  <option key={t.tag} value={t.tag}>
                    {t.tag}
                  </option>
                ))}
            </select>
          </div>
          <div className="h-64">
            {loadingChart ? (
              <div className="flex h-full items-center justify-center text-sm text-muted">
                {t("history.loading")}
              </div>
            ) : chartData.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-faint">
                {t("history.noData")}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e3e8f0" />
                  <XAxis
                    dataKey="step"
                    tickFormatter={(v) => `${(Number(v) / 1000).toFixed(0)}k`}
                  />
                  <YAxis />
                  <Tooltip
                    labelFormatter={(v) => `iter ${Number(v).toLocaleString()}`}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#2f5f9f"
                    strokeWidth={1.5}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* All tags */}
        {tags.length > 0 && (
          <div className="border-t border-line px-5 py-3">
            <SectionTitle className="mb-2">
              {t("history.allScalarTags")} ({tags.length})
            </SectionTitle>
            <div className="flex flex-wrap gap-1">
              {tags.map((t) => (
                <button
                  key={t.tag}
                  type="button"
                  onClick={() => setSelectedTag(t.tag)}
                  className={`rounded-md border px-2 py-0.5 font-mono text-[10px] transition ${
                    selectedTag === t.tag
                      ? "border-brand-500 bg-brand-50 text-brand-600"
                      : "border-line text-faint hover:bg-bg"
                  }`}
                  title={t.tag}
                >
                  {t.tag} ({t.count})
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Compare modal: overlay up to 10 runs across multiple metric tags
// ---------------------------------------------------------------------------

const COMPARE_TAGS = [
  { tag: "Train/mean_reward", labelKey: "history.rewardLabel" },
  { tag: "Train/mean_episode_length", labelKey: "history.episodeLengthLabel" },
];

const COMPARE_COLORS = [
  "#2f5f9f", "#a83232", "#1c7a4f", "#a8660f",
  "#6b7689", "#7c3aed", "#0891b2", "#db2777",
  "#ea580c", "#4d7c0f",
];

function CompareModal({
  runIds,
  allRuns,
  serverName,
  onClose,
}: {
  runIds: number[];
  allRuns: Map<number, HistoryRun>;
  serverName: (s: string) => string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [extraTag, setExtraTag] = useState<string>("");
  const [availableTags, setAvailableTags] = useState<string[]>([]);
  const [chartDataByTag, setChartDataByTag] = useState<Record<string, Array<Record<string, number | string | null>>>>({});
  const [loading, setLoading] = useState(true);

  // Fetch reward curves for all selected runs + discover available tags.
  useEffect(() => {
    setLoading(true);
    // First, get tags from the first run to populate the extra-tag selector.
    api.historyRunTags(runIds[0]).then((r) => {
      const tags = r.tags
        .map((t) => t.tag)
        .filter((t) => !t.startsWith("Train/"));
      setAvailableTags(tags);
    }).catch(() => void 0);

    // Fetch all compare tags for all runs.
    const tagsToFetch = [...COMPARE_TAGS.map((t) => t.tag)];
    if (extraTag) tagsToFetch.push(extraTag);

    Promise.all(
      tagsToFetch.flatMap((tag) =>
        runIds.map((id) =>
          api.historyRunScalarsSummary(id, tag, 100).then((res) => ({
            tag,
            runId: id,
            points: res.points,
          }))
        )
      )
    )
      .then((results) => {
        const byTag: Record<string, Array<Record<string, number | string | null>>> = {};
        for (const { tag } of results) {
          if (!byTag[tag]) {
            byTag[tag] = [];
          }
        }
        // For each tag, merge all runs by index.
        for (const tag of tagsToFetch) {
          const tagResults = results.filter((r) => r.tag === tag);
          const maxLen = Math.max(...tagResults.map((r) => r.points.length), 0);
          const merged: Array<Record<string, number | string | null>> = [];
          for (let i = 0; i < maxLen; i++) {
            const row: Record<string, number | string | null> = { idx: i };
            tagResults.forEach((r) => {
              const pt = r.points[i];
              const runIdx = runIds.indexOf(r.runId);
              if (pt && runIdx >= 0) {
                row[`run${runIdx}`] = pt.value;
                if (i === 0) row[`step${runIdx}`] = pt.step;
              }
            });
            merged.push(row);
          }
          byTag[tag] = merged;
        }
        setChartDataByTag(byTag);
      })
      .catch(() => void 0)
      .finally(() => setLoading(false));
  }, [runIds.join(","), extraTag]);

  const tagsToShow = [...COMPARE_TAGS.map((t) => t.tag)];
  if (extraTag) tagsToShow.push(extraTag);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-xl bg-panel shadow-panel"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-panel px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-ink">
              {t("history.compare")} {runIds.length} {t("history.compareRuns")}
            </span>
            <div className="flex flex-wrap gap-1">
              {runIds.map((id, idx) => {
                const run = allRuns.get(id);
                return (
                  <span
                    key={id}
                    className="flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold"
                    style={{ background: `${COMPARE_COLORS[idx % 10]}20`, color: COMPARE_COLORS[idx % 10] }}
                  >
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ background: COMPARE_COLORS[idx % 10] }}
                    />
                    {run ? `${serverName(run.server)}/run ${run.id}` : `run ${id}`}
                  </span>
                );
              })}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-faint hover:bg-bg hover:text-ink"
          >
            ✕
          </button>
        </div>

        {/* Extra tag selector */}
        <div className="border-b border-line px-5 py-2">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-faint">{t("history.additionalMetric")}</span>
            <select
              value={extraTag}
              onChange={(e) => setExtraTag(e.target.value)}
              className="select max-w-md text-xs"
            >
              <option value="">{t("history.none")}</option>
              {availableTags.slice(0, 100).map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Charts */}
        <div className="space-y-4 p-5">
          {loading ? (
            <div className="flex h-32 items-center justify-center text-sm text-muted">
              {t("history.loadingComparison")}
            </div>
          ) : (
            tagsToShow.map((tag) => {
              const data = chartDataByTag[tag] || [];
              const compareTag = COMPARE_TAGS.find((t) => t.tag === tag);
              const label = compareTag ? t(compareTag.labelKey) : tag;
              return (
                <div key={tag}>
                  <div className="mb-1 text-xs font-bold text-ink">{label}</div>
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={data} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e3e8f0" />
                        <XAxis dataKey="idx" />
                        <YAxis />
                        <Tooltip />
                        <Legend wrapperStyle={{ fontSize: 10 }} />
                        {runIds.map((id, idx) => {
                          const run = allRuns.get(id);
                          return (
                            <Line
                              key={id}
                              type="monotone"
                              dataKey={`run${idx}`}
                              name={run ? `${serverName(run.server)}/run ${run.id}` : `run ${id}`}
                              stroke={COMPARE_COLORS[idx % 10]}
                              strokeWidth={1.5}
                              dot={false}
                            />
                          );
                        })}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
