"use client";

import { useEffect, useState } from "react";
import type { NodeSnapshot } from "@/lib/types";
import { Card, Pill, SectionTitle, Stat } from "./ui";
import { Gauge, gaugeColor } from "./Gauge";
import { Dropdown, DropdownRow } from "./Dropdown";
import { formatElapsed, useAlias, useSetAlias } from "@/lib/aliases";
import { presentEvidenceText } from "@/lib/presentation";

function parseMi(value: string | undefined): number {
  if (!value) return 0;
  const m = value.match(/\d[\d,]*/);
  if (!m) return 0;
  return Number(m[0].replace(/,/g, ""));
}

function parsePct(value: string | undefined): number {
  if (!value) return 0;
  const m = value.match(/\d+(\.\d+)?/);
  return m ? Number(m[0]) : 0;
}

function shortGpu(name: string | undefined): string {
  if (!name || name === "?") return "?";
  const parts = name.split(" ");
  if (parts.length >= 2 && /nvidia|geforce|amd|radeon/i.test(parts[0])) {
    const out: string[] = [];
    for (const token of parts.slice(1)) {
      out.push(token);
      if (/\d/.test(token)) break;
    }
    return out.join(" ") || name;
  }
  return name;
}

export function CellCard({ snap }: { snap: NodeSnapshot }) {
  // ``label`` is "GPU0" / "GPU1" ??derive the storage key from it.
  const storageKey = snap.label.toLowerCase();
  const displayName = useAlias(storageKey);
  const setAlias = useSetAlias();

  // Local "now" tick so the elapsed display refreshes every second.
  // The server snapshot gives us elapsed_sec AT snapshot time (snap.ts);
  // we recompute the live elapsed every tick by adding (now - snap.ts)
  // to the snapshot's elapsed_sec, so the counter visibly advances.
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(id);
  }, []);

  if (!snap.reachable) {
    return (
      <Card className="border-danger-100 bg-danger-50/40 p-4">
        <div className="flex items-center justify-between">
          <EditableLabel
            displayName={displayName}
            canonical={snap.label}
            onCommit={(v) => setAlias(storageKey, v)}
          />
          <Pill tone="danger">unreachable</Pill>
        </div>
        <p className="mt-2 break-all text-xs text-danger-600/80">
          {snap.error?.slice(0, 200) ?? "unknown error"}
        </p>
      </Card>
    );
  }

  const gpu = snap.gpu;
  const memUsed = parseMi(gpu?.mem_used);
  const memTotal = parseMi(gpu?.mem_total);
  const memPct = memTotal ? (memUsed / memTotal) * 100 : 0;
  const utilPct = parsePct(gpu?.util);
  const scalars = snap.scalars;
  const busy = snap.busy;
  const showLiveScalars = busy && scalars;
  const primaryProc = snap.training_procs?.[0];

  // Live elapsed: snapshot.elapsed_sec was measured at snap.ts. Add the
  // wall-clock delta since then so the value visibly advances every tick.
  const snapshotElapsed = primaryProc?.elapsed_sec ?? 0;
  const snapshotAge = Math.max(0, now - (snap.ts ?? now));
  const elapsed = snapshotElapsed ? snapshotElapsed + snapshotAge : undefined;

  // Training timing: start time, elapsed, estimated end.
  // Parse --max_iterations from the process command line.
  const maxIters = parseMaxIterations(primaryProc?.cmd);
  const currentIter = showLiveScalars ? scalars.iteration : undefined;
  const startTime = primaryProc?.elapsed_sec
    ? new Date((snap.ts - primaryProc.elapsed_sec) * 1000)
    : undefined;
  // ETA: if we know max_iters and current iter and elapsed, extrapolate.
  // rate = currentIter / elapsed; remaining = (maxIters - currentIter) / rate
  let etaString: string | undefined;
  let etaTimestamp: Date | undefined;
  if (elapsed && maxIters && currentIter && currentIter > 0 && elapsed > 5) {
    const rate = currentIter / elapsed; // iters/sec
    if (rate > 0) {
      const remainingSec = Math.max(0, (maxIters - currentIter) / rate);
      const totalSec = maxIters / rate;
      etaTimestamp = new Date((snap.ts + remainingSec) * 1000);
      // Format as "Xh Ym" or "Ym" or "<1m"
      etaString = formatRemaining(totalSec);
    }
  }

  return (
    <Card hoverable className="p-5">
      {/* Header: status dot + editable title + busy pill + elapsed + ??menu */}
      <div className="mb-4 flex flex-wrap items-center gap-2.5">
        <span className="relative inline-flex h-2.5 w-2.5">
          {busy && (
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-danger-500 opacity-75" />
          )}
          <span
            className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
              busy ? "bg-danger-500" : "bg-safe-500"
            }`}
          />
        </span>
        <div className="min-w-0 flex-1">
          <EditableLabel
            displayName={displayName}
            canonical={snap.label}
            onCommit={(v) => setAlias(storageKey, v)}
          />
          {/* No hostname/host shown here on purpose ??they live in the ??              dropdown so the card is safe to screenshot/record. */}
        </div>
        <div className="flex flex-col items-end gap-1">
          <Pill tone={busy ? "danger" : "safe"}>
            {busy ? "training" : "idle"}
          </Pill>
          {busy && elapsed !== undefined && (
            <span className="font-mono text-[10px] text-faint">
              {formatElapsed(elapsed)}
            </span>
          )}
        </div>
        {/* Details menu: no hostname, host, session name, or raw command is shown. */}
        <Dropdown
          trigger={<span className="text-base leading-none">...</span>}
          align="right"
        >
          <div className="space-y-1">
            {snap.latest_run_dir && (
              <DropdownRow label="latest run" value={presentEvidenceText(snap.latest_run_dir)} />
            )}
            {snap.training_procs && snap.training_procs.length > 0 && (
              <>
                <DropdownRow
                  label="active processes"
                  value={snap.training_procs.length.toLocaleString()}
                />
                {primaryProc?.elapsed_sec !== undefined && primaryProc.elapsed_sec > 0 && (
                  <DropdownRow
                    label="elapsed"
                    value={formatElapsed(primaryProc.elapsed_sec + snapshotAge)}
                  />
                )}
              </>
            )}
            {!busy && (
              <div className="py-1 text-[11px] italic text-faint">
                No active training process.
              </div>
            )}
          </div>
        </Dropdown>
      </div>

      {/* GPU model */}
      <div className="mb-3 text-xs text-muted">
        <SectionTitle>GPU</SectionTitle>
        <div className="mt-0.5 font-bold text-ink">{shortGpu(gpu?.name)}</div>
      </div>

      {/* Gauges */}
      <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <Gauge
          value={memPct}
          label="VRAM"
          rightLabel={`${memUsed.toLocaleString()} / ${memTotal.toLocaleString()} MiB`}
          color={gaugeColor(memPct)}
        />
        <Gauge
          value={utilPct}
          label="Util"
          rightLabel={`${utilPct.toFixed(0)}%`}
          color={gaugeColor(utilPct)}
        />
      </div>

      {/* Scalars */}
      {showLiveScalars && (
        <div className="mb-4 grid grid-cols-3 gap-3 border-y border-line py-3">
          <Stat label="iter" value={scalars.iteration} />
          <Stat label="reward" value={scalars.reward} />
          <Stat label="ep len" value={scalars.ep_len} />
        </div>
      )}

      {/* Training timing: start / elapsed / ETA */}
      {busy && elapsed !== undefined && (
        <div className="mb-4 grid grid-cols-3 gap-3 rounded-md bg-bg/50 px-3 py-2.5">
          <TimingStat
            label="started"
            value={startTime ? formatClock(startTime) : "n/a"}
          />
          <TimingStat
            label="elapsed"
            value={formatElapsed(elapsed)}
            live
          />
          <TimingStat
            label="ETA"
            value={etaString ? `~${etaString}` : "n/a"}
            hint={etaTimestamp ? formatClock(etaTimestamp) : undefined}
          />
        </div>
      )}

      {/* Footer: task label + status. No host info. */}
      <div className="text-[11px] text-faint">
        {busy ? (
          primaryProc ? (
            <div className="space-y-0.5">
              <div className="font-mono text-[11px] text-ink-soft">
                {presentTrainingLabel(primaryProc)}
              </div>
              {(primaryProc.task_name || primaryProc.num_envs) && (
                <div className="text-[10px] text-faint">
                  {presentEvidenceText(primaryProc.task_name ?? "policy training")}
                  {primaryProc.num_envs ? ` / ${primaryProc.num_envs.toLocaleString()} envs` : ""}
                  {primaryProc.max_iterations ? ` / max iter ${primaryProc.max_iterations.toLocaleString()}` : ""}
                  {primaryProc.resume_from ? ` / resume ${presentEvidenceText(primaryProc.resume_from)}` : ""}
                </div>
              )}
            </div>
          ) : (
            <span className="font-mono">training session active</span>
          )
        ) : (
          <span className="italic">no active training</span>
        )}
      </div>
    </Card>
  );
}

/** Inline-editable title. Click the name to rename; Enter to commit,
 *  Esc to cancel, empty to reset. Renames persist via the global alias
 *  store so the change is visible everywhere immediately. */
function EditableLabel({
  displayName,
  canonical,
  onCommit,
}: {
  displayName: string;
  canonical: string;
  onCommit: (value: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(displayName);

  useEffect(() => {
    if (!editing) setDraft(displayName);
  }, [displayName, editing]);

  function commit() {
    const next = draft.trim();
    // Empty or canonical reset ??store empty so the fallback kicks in.
    onCommit(next === canonical ? "" : next);
    setEditing(false);
  }

  if (editing) {
    return (
      <div className="flex items-center gap-1">
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") {
              setDraft(displayName);
              setEditing(false);
            }
          }}
          className="w-32 rounded border border-line bg-panel px-1.5 py-0.5 text-sm font-bold text-ink focus:border-brand-500 focus:outline-none"
        />
        <button
          type="button"
          onClick={commit}
          className="text-[10px] text-brand-600 hover:underline"
        >
          save
        </button>
      </div>
    );
  }
  return (
    <div className="group/edit flex items-center gap-1">
      <span className="truncate text-sm font-bold text-ink">{displayName}</span>
      <button
        type="button"
        onClick={() => setEditing(true)}
        title="Rename"
        className="opacity-0 transition group-hover/edit:opacity-100"
      >
        <span className="text-[11px] text-faint hover:text-brand-600">edit</span>
      </button>
    </div>
  );
}

/** Small stat block for timing info. */
function TimingStat({
  label,
  value,
  hint,
  live = false,
}: {
  label: string;
  value: string;
  hint?: string;
  live?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[9px] font-bold uppercase tracking-wider text-faint">
        {label}
      </div>
      <div
        className={`mt-0.5 font-mono text-xs font-bold ${
          live ? "text-brand-600" : "text-ink-soft"
        }`}
      >
        {value}
      </div>
      {hint && (
        <div className="mt-0.5 font-mono text-[9px] text-faint">{hint}</div>
      )}
    </div>
  );
}

function presentTrainingLabel(proc: {
  label?: string;
  task_name?: string;
  num_envs?: number;
  max_iterations?: number;
  pid: number;
}): string {
  const task = presentEvidenceText(proc.task_name || "policy training");
  const envs = proc.num_envs ? ` - ${proc.num_envs.toLocaleString()} envs` : "";
  const maxIter = proc.max_iterations ? ` - iter ${proc.max_iterations.toLocaleString()}` : "";
  if (proc.label) return `${task}${envs}${maxIter}`;
  return `training process ${proc.pid}`;
}

/** Parse --max_iterations NNN from a process command line. */
function parseMaxIterations(cmd: string | undefined): number | undefined {
  if (!cmd) return undefined;
  const m = cmd.match(/--max_iterations\s+(\d+)/);
  return m ? Number(m[1]) : undefined;
}

/** Format a Date as HH:MM for display. */
function formatClock(d: Date): string {
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** Format total seconds as "Xh Ym" or "Ym" or "<1m". */
function formatRemaining(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return "<1m";
}
