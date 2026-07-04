"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useDashboard } from "@/lib/store";
import { LanguageToggle } from "./LanguageToggle";
import { presentModeLabel } from "@/lib/presentation";

const NAV_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/run-experiment", label: "Run" },
  { href: "/history", label: "History" },
  { href: "/plan", label: "Plan" },
  { href: "/training", label: "Train" },
  { href: "/evaluation", label: "Eval" },
  { href: "/safety", label: "Safety" },
  { href: "/report", label: "Report" },
];

/** Compact top-nav for small screens (where the sidebar is hidden). */
export function MobileNav() {
  const pathname = usePathname();
  const evidenceMode = useDashboard((s) => s.evidenceMode);
  const setEvidenceMode = useDashboard((s) => s.setEvidenceMode);
  const isLive = evidenceMode === "Live Lab";
  const isReplay = evidenceMode === "Sanitized Real Replay";

  let items = [...NAV_ITEMS];
  if (isReplay) {
    items = [...NAV_ITEMS.slice(0, 2), { href: "/replay", label: "Replay" }, ...NAV_ITEMS.slice(2)];
  }
  if (isLive) {
    items = [...NAV_ITEMS.slice(0, 2), { href: "/live-control", label: "Live" }, ...NAV_ITEMS.slice(2)];
  }

  return (
    <div className="mb-4 md:hidden">
      {/* Brand row */}
      <div className="mb-3 flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 text-xs font-black text-white">
          PA
        </div>
        <span className="text-sm font-extrabold tracking-tight text-ink flex-1">
          Physical AI Safety Agent
        </span>
        <LanguageToggle />
      </div>

      {/* Mode chips */}
      <div className="mb-3 flex flex-wrap gap-1">
        {(["Mock Demo", "Sanitized Real Replay", "Live Lab"] as const).map((m) => {
          const active = evidenceMode === m;
          return (
            <button
              key={m}
              type="button"
              onClick={() => setEvidenceMode(m)}
              className={`rounded-full px-2.5 py-1 text-[10px] font-bold transition ${
                active
                  ? m === "Live Lab"
                    ? "bg-warn-500 text-white"
                    : "bg-brand-500 text-white"
                  : "bg-line text-muted"
              }`}
            >
              {presentModeLabel(m)}
            </button>
          );
        })}
      </div>

      {/* Page chips */}
      <div className="flex flex-wrap gap-1">
        {items.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded-full px-2.5 py-1 text-[11px] font-semibold transition ${
                active
                  ? "bg-ink text-white"
                  : "bg-bg text-muted hover:bg-line"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
