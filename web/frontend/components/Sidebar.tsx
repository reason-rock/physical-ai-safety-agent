"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useDashboard } from "@/lib/store";
import { useTranslation } from "react-i18next";
import type { HealthResponse } from "@/lib/types";
import { LanguageToggle } from "./LanguageToggle";
import { presentModeLabel } from "@/lib/presentation";

const NAV_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/run-experiment", label: "Run Experiment" },
  { href: "/history", label: "History" },
  { href: "/plan", label: "Plan" },
  { href: "/training", label: "Training" },
  { href: "/evaluation", label: "Evaluation" },
  { href: "/safety", label: "Safety" },
  { href: "/report", label: "Report" },
];

const REPLAY_NAV_ITEM = { href: "/replay", label: "Replay Browser" };

const MODES = ["Mock Demo", "Sanitized Real Replay", "Live Lab"] as const;

export function Sidebar() {
  const pathname = usePathname();
  const evidenceMode = useDashboard((s) => s.evidenceMode);
  const setEvidenceMode = useDashboard((s) => s.setEvidenceMode);
  const isLive = evidenceMode === "Live Lab";
  const isReplay = evidenceMode === "Sanitized Real Replay";
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const { t } = useTranslation();

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => void 0);
  }, []);

  // Build nav items dynamically based on mode.
  let items = [...NAV_ITEMS];
  if (isReplay) {
    items = [...NAV_ITEMS.slice(0, 2), REPLAY_NAV_ITEM, ...NAV_ITEMS.slice(2)];
  }
  if (isLive) {
    items = [
      ...NAV_ITEMS.slice(0, 2),
      { href: "/live-control", label: "Live Control" },
      ...NAV_ITEMS.slice(2),
    ];
  }

  return (
    <aside className="sticky top-6 hidden h-[calc(100vh-3rem)] w-72 shrink-0 flex-col self-start md:flex">
      {/* Brand mark */}
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-sm font-black text-white shadow-pop">
          PA
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-extrabold tracking-tight text-ink">
            {t("app.title")}
          </div>
          <div className="truncate text-[10px] font-semibold uppercase tracking-wider text-faint">
            {t("app.subtitle")}
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="space-y-0.5">
        {items.map((item) => {
          const active = pathname === item.href;
          const isLiveControl = item.href === "/live-control";
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`group flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-soft ${
                active
                  ? "bg-brand-500 text-white shadow-sm"
                  : "text-ink-soft hover:bg-brand-50 hover:text-brand-600"
              } ${isLiveControl ? "border border-warn-100 bg-warn-50/60" : ""} ${
                isLiveControl && active ? "bg-warn-500 text-white" : ""
              }`}
              style={{ transitionDuration: "120ms" }}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  active ? "bg-white" : "bg-faint group-hover:bg-brand-500"
                } ${isLiveControl && active ? "bg-white" : ""}`}
              />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Evidence-mode segmented control */}
      <div className="mt-7">
        <div className="section-title mb-2">{t("mode.label")}</div>
        <div className="space-y-1 rounded-lg border border-line bg-panel p-1">
          {MODES.map((mode) => {
            const active = evidenceMode === mode;
            const modeIsLive = mode === "Live Lab";
            return (
              <button
                key={mode}
                type="button"
                onClick={() => setEvidenceMode(mode)}
                className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-xs font-semibold transition-soft ${
                  active
                    ? modeIsLive
                      ? "bg-warn-500 text-white shadow-sm"
                      : "bg-brand-500 text-white shadow-sm"
                    : "text-ink-soft hover:bg-bg"
                }`}
                style={{ transitionDuration: "120ms" }}
              >
                <span>{presentModeLabel(mode)}</span>
                {modeIsLive && !active && (
                  <span className="h-1.5 w-1.5 rounded-full bg-warn-500 animate-pulse" />
                )}
              </button>
            );
          })}
        </div>
        {isLive && (
          <div className="mt-2 rounded-md border border-warn-100 bg-warn-50 px-2.5 py-1.5 text-[10px] leading-snug text-warn-600">
            Live Lab monitoring is active. Review the plan before submitting any training job.
          </div>
        )}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Footer: backend status + data mode + language toggle */}
      <div className="mt-6 space-y-1 border-t border-line pt-3 text-[10px] text-faint">
        <div className="flex items-center justify-between">
          <span>{t("footer.backend")}</span>
          <span
            className={`pill ${health?.status === "ok" ? "pill--safe" : "pill--muted"}`}
          >
            {health?.status === "ok" ? t("home.online") : t("home.checking")}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span>{t("footer.liveAdapter")}</span>
          <span className={`pill ${health?.live_lab_enabled ? "pill--brand" : "pill--muted"}`}>
            {health?.live_lab_enabled ? t("home.enabled") : t("home.disabled")}
          </span>
        </div>
        <div className="mt-2 flex justify-end">
          <LanguageToggle />
        </div>
      </div>
    </aside>
  );
}
