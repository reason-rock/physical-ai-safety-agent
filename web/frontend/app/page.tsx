"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { useDashboard } from "@/lib/store";
import { Card, PageHeader, Pill, SectionTitle, Stat } from "@/components/ui";
import { SCENARIOS } from "@/components/scenarios";
import {
  displayNodeAliasesInText,
  displayNodeName,
  useAlias,
} from "@/lib/aliases";
import { presentEvidenceText, presentModeLabel, presentNodeRole } from "@/lib/presentation";
import type { HealthResponse, NodeEntry } from "@/lib/types";

export default function HomePage() {
  const { t } = useTranslation();
  const evidenceMode = useDashboard((s) => s.evidenceMode);
  const setEvidenceMode = useDashboard((s) => s.setEvidenceMode);
  const result = useDashboard((s) => s.result);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [nodes, setNodes] = useState<NodeEntry[]>([]);
  const gpu0Name = useAlias("gpu0");
  const gpu1Name = useAlias("gpu1");

  useEffect(() => {
    api.health().then(setHealth).catch(() => void 0);
    api.nodes().then((r) => setNodes(r.nodes)).catch(() => void 0);
  }, []);

  const liveEnabled = health?.live_lab_enabled ?? false;
  const isLive = evidenceMode === "Live Lab";

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title={t("home.title")}
        subtitle={t("home.subtitle")}
        right={
          <Pill tone={isLive ? "warn" : "brand"}>{presentModeLabel(evidenceMode)}</Pill>
        }
      />

      {/* Top stats strip */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card className="p-4">
          <Stat
            label={t("home.backend")}
            value={health?.status === "ok" ? t("home.online") : t("home.checking")}
            hint={t("home.fastApiHint")}
          />
        </Card>
        <Card className="p-4">
          <Stat
            label={t("home.liveAdapter")}
            value={liveEnabled ? t("home.enabled") : t("home.disabled")}
            hint={liveEnabled ? t("home.sshReady") : t("home.mockOnly")}
          />
        </Card>
        <Card className="p-4">
          <Stat
            label={t("home.trackedNodes")}
            value={nodes.length}
            hint={`${gpu0Name}/${gpu1Name}/Evaluation/Safety`}
          />
        </Card>
        <Card className="p-4">
          <Stat
            label={t("home.lastResult")}
            value={result ? result.pair.pair_id : "—"}
            hint={result ? result.safety.safety_level : t("home.noWorkflow")}
          />
        </Card>
      </div>

      {/* Quick actions */}
      <section className="space-y-3">
        <SectionTitle>{t("home.quickActions")}</SectionTitle>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <ActionCard
            href="/run-experiment"
            tone="brand"
            title={t("home.runExperiment")}
            body={t("home.runExperimentBody")}
            cta={t("home.openRunExperiment")}
          />
          <ActionCard
            href="/live-control"
            tone={liveEnabled ? "safe" : "muted"}
            title={`${t("home.monitorCells")} ${gpu0Name} / ${gpu1Name}`}
            body={
              liveEnabled
                ? t("home.monitorBody")
                : t("home.monitorBodyDisabled")
            }
            cta={liveEnabled ? t("home.openLiveControl") : t("home.disabled")}
            disabled={!liveEnabled}
          />
          {result ? (
            <ActionCard
              href="/report"
              tone="warn"
              title={t("home.viewReport")}
              body={`Pair ${result.pair.pair_id} — ${result.safety.safety_level}.`}
              cta={t("home.openReport")}
            />
          ) : (
            <ActionCard
              href="/run-experiment"
              tone="muted"
              title={t("home.noReportYet")}
              body={t("home.noReportBody")}
              cta={t("common.goToRun")}
            />
          )}
        </div>
      </section>

      {/* Scenario shortcuts */}
      <section className="space-y-3">
        <SectionTitle>{t("home.scenarios")}</SectionTitle>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {SCENARIOS.map((s) => (
            <Link
              key={s.id}
              href="/run-experiment"
              className="card card-hoverable flex flex-col gap-2 p-4"
            >
              <Pill
                tone={
                  s.tone === "danger"
                    ? "danger"
                    : s.tone === "warn"
                      ? "warn"
                      : s.tone === "safe"
                        ? "safe"
                        : "brand"
                }
              >
                {s.emoji}
              </Pill>
              <div className="text-sm font-bold text-ink">{s.title}</div>
              <div className="text-xs text-muted">
                {displayNodeAliasesInText(s.oneLine, {
                  gpu0: gpu0Name,
                  gpu1: gpu1Name,
                })}
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* Node registry */}
      {nodes.length > 0 && (
        <section className="space-y-3">
          <SectionTitle>{t("home.configuredNodes")}</SectionTitle>
          <Card className="overflow-hidden">
            <table className="w-full text-sm">
              <tbody>
                {nodes.map((n) => (
                  <tr key={n.name} className="border-t border-line/60 first:border-t-0">
                    <td className="px-4 py-2.5 font-mono text-xs text-ink">
                      {displayNodeName(n.name)}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted">{presentNodeRole(n.role)}</td>
                    <td className="px-4 py-2.5 text-xs text-faint">—</td>
                    <td className="px-4 py-2.5 text-right">
                      <Pill tone={n.status.includes("blocked") ? "danger" : "safe"}>
                        {presentEvidenceText(n.status).toUpperCase()}
                      </Pill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </section>
      )}
    </div>
  );
}

function ActionCard({
  href,
  tone,
  title,
  body,
  cta,
  disabled,
}: {
  href: string;
  tone: "brand" | "safe" | "warn" | "muted";
  title: string;
  body: string;
  cta: string;
  disabled?: boolean;
}) {
  const toneClass = {
    brand: "hover:border-brand-500 hover:bg-brand-50/40",
    safe: "hover:border-safe-500 hover:bg-safe-50/40",
    warn: "hover:border-warn-500 hover:bg-warn-50/40",
    muted: "opacity-60",
  }[tone];

  if (disabled) {
    return (
      <div className={`card p-4 ${toneClass}`}>
        <div className="text-sm font-bold text-ink">{title}</div>
        <div className="mt-1 text-xs text-muted">{body}</div>
        <div className="mt-3 text-[11px] font-bold uppercase text-faint">{cta}</div>
      </div>
    );
  }
  return (
    <Link href={href} className={`card card-hoverable block p-4 ${toneClass}`}>
      <div className="text-sm font-bold text-ink">{title}</div>
      <div className="mt-1 text-xs text-muted">{body}</div>
      <div className="mt-3 text-[11px] font-bold uppercase text-brand-600">{cta} →</div>
    </Link>
  );
}
