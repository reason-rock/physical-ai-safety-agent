"use client";

import { useTranslation } from "react-i18next";
import { useDashboard } from "@/lib/store";
import { useLabUpdates } from "@/lib/sse";
import { shouldHoldFinalLiveEvidence } from "@/lib/live-status";
import { presentEvidenceObject, presentEvidenceText } from "@/lib/presentation";
import { Card, EmptyState, PageHeader, Pill, SectionTitle, Stat } from "@/components/ui";

function safetyTone(level: string): "safe" | "warn" | "danger" {
  if (level === "candidate_for_free_walking") return "safe";
  if (level === "supported_test_only") return "warn";
  return "danger";
}

export default function SafetyPage() {
  const { t } = useTranslation();
  const result = useDashboard((s) => s.result);
  const evidenceMode = useDashboard((s) => s.evidenceMode);
  const isLive = evidenceMode === "Live Lab";
  const { latest } = useLabUpdates(isLive);
  if (!result) return <EmptyState title={t("safety.empty")} />;
  if (isLive && shouldHoldFinalLiveEvidence(latest?.jobs)) {
    return (
      <LiveEvidencePending
        title={t("safety.title")}
        message="This page will not reuse the older deterministic workflow gate for Live Lab jobs. Collect and evaluate the latest run pair before producing a safety decision."
      />
    );
  }
  const { safety, deployment_package, robot_action_diff, audit_log } = result;
  const presentedDeploymentPackage = presentEvidenceObject(deployment_package);
  const presentedRobotActionDiff = presentEvidenceText(robot_action_diff);
  const presentedAuditLog = audit_log.map((line) => presentEvidenceText(line));

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title={t("safety.title")}
        subtitle={t("safety.subtitle")}
        right={<Pill tone={safetyTone(safety.safety_level)}>{safety.safety_level}</Pill>}
      />

      <Card className="p-5">
        <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
          <Stat
            label={t("safety.safetyLevel")}
            value={<Pill tone={safetyTone(safety.safety_level)}>{safety.safety_level}</Pill>}
          />
          <Stat
            label={t("safety.freeWalking")}
            value={safety.free_walking_allowed ? t("safety.yes") : t("safety.no")}
          />
          <Stat
            label={t("safety.supportedTest")}
            value={safety.supported_test_allowed ? t("safety.yes") : t("safety.no")}
          />
          <Stat
            label={t("safety.reasons")}
            value={safety.reasons.length}
            hint={t("safety.gatingReasons")}
          />
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card className="p-5">
          <SectionTitle className="mb-3">{t("safety.reasons")}</SectionTitle>
          <ul className="space-y-1.5 text-sm">
            {safety.reasons.length === 0 ? (
              <li className="text-xs text-faint">{t("safety.nonePassed")}</li>
            ) : (
              safety.reasons.map((r) => (
                <li key={r} className="border-l-2 border-warn-100 pl-3 text-ink-soft">
                  {r}
                </li>
              ))
            )}
          </ul>
        </Card>
        <Card className="p-5">
          <SectionTitle className="mb-3">{t("safety.requiredActions")}</SectionTitle>
          <ul className="space-y-1.5 text-sm">
            {safety.required_actions.length === 0 ? (
              <li className="text-xs text-faint">{t("safety.none")}</li>
            ) : (
              safety.required_actions.map((r) => (
                <li key={r} className="border-l-2 border-danger-100 pl-3 text-ink-soft">
                  {r}
                </li>
              ))
            )}
          </ul>
        </Card>
      </div>

      <Card className="p-5">
        <SectionTitle className="mb-3">{t("safety.deploymentPackage")}</SectionTitle>
        <pre className="overflow-x-auto rounded-md bg-bg p-3 font-mono text-[11px] leading-relaxed text-ink-soft">
          {JSON.stringify(presentedDeploymentPackage, null, 2)}
        </pre>
      </Card>

      <Card className="p-5">
        <SectionTitle className="mb-3">{t("safety.robotActionDiff")}</SectionTitle>
        <pre className="whitespace-pre-wrap break-words rounded-md bg-bg p-3 font-mono text-[11px] leading-relaxed text-ink-soft">
          {presentedRobotActionDiff}
        </pre>
      </Card>

      <Card className="p-4">
        <details>
          <summary className="cursor-pointer text-sm font-semibold text-muted">
            {t("safety.auditLog")} ({presentedAuditLog.length} {t("safety.entries")})
          </summary>
          <ul className="mt-2 space-y-0.5 font-mono text-[10px] text-faint">
            {presentedAuditLog.map((line, idx) => (
              <li key={idx} className="border-l border-line pl-2">
                {line}
              </li>
            ))}
          </ul>
        </details>
      </Card>
    </div>
  );
}

function LiveEvidencePending({ title, message }: { title: string; message: string }) {
  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader title={title} subtitle="Waiting for collected live evidence." />
      <Card className="border-warn-100 bg-warn-50/50 p-6">
        <div className="text-sm font-bold text-warn-600">Gate not ready</div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-warn-600/90">{message}</p>
      </Card>
    </div>
  );
}
