"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { useDashboard, dataModeFromEvidence } from "@/lib/store";
import { displayNodeAliasesInText, useAlias } from "@/lib/aliases";
import { Card, PageHeader, Pill, SectionTitle } from "@/components/ui";
import {
  SCENARIOS,
  ScenarioCard,
  StepBadge,
  type Scenario,
} from "@/components/scenarios";

const DEFAULT_EVALUATION_ROLLOUTS = 256;
const MIN_EVALUATION_ROLLOUTS = 32;
const MAX_EVALUATION_ROLLOUTS = 5000;

export default function RunExperimentPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const evidenceMode = useDashboard((s) => s.evidenceMode);
  const operatorToken = useDashboard((s) => s.operatorToken);
  const setOperatorToken = useDashboard((s) => s.setOperatorToken);
  const setResult = useDashboard((s) => s.setResult);
  const gpu0Name = useAlias("gpu0");
  const gpu1Name = useAlias("gpu1");

  const [picked, setPicked] = useState<Scenario | null>(null);
  const [request, setRequest] = useState("");
  const [rollouts, setRollouts] = useState(DEFAULT_EVALUATION_ROLLOUTS);
  const [strictness, setStrictness] = useState<"standard" | "strict">("standard");
  const [operatorConfirmed, setOperatorConfirmed] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const isLive = evidenceMode === "Live Lab";
  const displayedRollouts = Math.max(MIN_EVALUATION_ROLLOUTS, rollouts);

  useEffect(() => {
    if (rollouts < MIN_EVALUATION_ROLLOUTS) {
      setRollouts(DEFAULT_EVALUATION_ROLLOUTS);
    }
  }, [rollouts]);

  function pickScenario(s: Scenario) {
    setPicked(s);
    setRequest(
      displayNodeAliasesInText(s.request, {
        gpu0: gpu0Name,
        gpu1: gpu1Name,
      })
    );
    setRollouts(s.rollouts);
    setStrictness(s.strictness);
    setError("");
    // Smooth-scroll to the run button.
    document.getElementById("run-button")?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!request.trim()) {
      setError(t("runExperiment.errorNeedRequest"));
      return;
    }
    if (isLive && !operatorConfirmed) {
      setError(t("runExperiment.errorNeedOperator"));
      return;
    }
    setRunning(true);
    try {
      // Live Lab needs an explicit human click on the Plan page before any GPU
      // SSH submit happens. The run-experiment step only builds the controlled
      // experiment plan.
      const dataMode = isLive ? "mock" : dataModeFromEvidence(evidenceMode);
      const result = await api.runWorkflow({
        request,
        num_rollouts: displayedRollouts,
        safety_strictness: strictness,
        data_mode: dataMode,
        operator_token: operatorToken || null,
        operator_confirmed: operatorConfirmed,
      });
      setResult(result);
      router.push("/plan");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="animate-fade-in space-y-8">
      <PageHeader
        title={t("runExperiment.title")}
        subtitle={t("runExperiment.subtitle")}
        right={
          <Pill tone={isLive ? "warn" : "brand"}>{evidenceMode}</Pill>
        }
      />

      {/* Step 1: pick a scenario */}
      <section className="space-y-3">
        <StepBadge n={1}>{t("runExperiment.step1")}</StepBadge>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {SCENARIOS.map((s) => (
            <ScenarioCard
              key={s.id}
              scenario={s}
              active={picked?.id === s.id}
              onPick={() => pickScenario(s)}
            />
          ))}
        </div>
        <div className="text-xs text-faint">{t("runExperiment.step1Hint")}</div>
      </section>

      {/* Step 2: review options */}
      <section className="space-y-3">
        <StepBadge n={2}>{t("runExperiment.step2")}</StepBadge>
        <Card className="space-y-4 p-5">
          <div>
            <SectionTitle className="mb-2">
              {t("runExperiment.experimentRequest")}
            </SectionTitle>
            <textarea
              value={request}
              onChange={(e) => {
                setRequest(e.target.value);
                setPicked(null);
              }}
              rows={6}
              className="textarea"
              placeholder={t("runExperiment.placeholder")}
            />
            <div className="mt-1 flex items-center justify-between text-[11px] text-faint">
              <span>
                {request.length} {t("runExperiment.chars")}
              </span>
              {picked && (
                <span>
                  {t("runExperiment.fromScenario")} {picked.title}
                </span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {/* Rollouts */}
            <div>
              <SectionTitle className="mb-2">
                {t("runExperiment.evaluationRollouts")}
              </SectionTitle>
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-2xl font-extrabold text-ink">
                  {displayedRollouts}
                </span>
                <span className="text-[11px] text-faint">
                  {t("runExperiment.rollouts")}
                </span>
              </div>
              <input
                type="range"
                min={MIN_EVALUATION_ROLLOUTS}
                max={MAX_EVALUATION_ROLLOUTS}
                step={32}
                value={displayedRollouts}
                onChange={(e) => setRollouts(Number(e.target.value))}
                className="mt-2 w-full accent-brand-500"
              />
            </div>

            {/* Strictness */}
            <div>
              <SectionTitle className="mb-2">
                {t("runExperiment.safetyStrictness")}
              </SectionTitle>
              <div className="space-y-1.5">
                {(["standard", "strict"] as const).map((s) => {
                  const active = strictness === s;
                  return (
                    <button
                      key={s}
                      type="button"
                      onClick={() => setStrictness(s)}
                      className={`flex w-full items-center justify-between rounded-md border px-3 py-2 text-xs font-semibold transition ${
                        active
                          ? "border-brand-500 bg-brand-50 text-brand-600"
                          : "border-line text-muted hover:bg-bg"
                      }`}
                    >
                      <span>
                        {s === "standard"
                          ? t("runExperiment.standard")
                          : t("runExperiment.strict")}
                      </span>
                      {active && (
                        <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Mode summary */}
            <div>
              <SectionTitle className="mb-2">
                {t("runExperiment.evidenceMode")}
              </SectionTitle>
              <div className="rounded-md border border-line bg-bg px-3 py-2 text-xs">
                <div className="font-bold text-ink">{evidenceMode}</div>
                <div className="mt-1 text-faint">
                  {isLive
                    ? t("runExperiment.liveLabHardware")
                    : t("runExperiment.noSsh")}
                </div>
              </div>
            </div>
          </div>

          {isLive && (
            <div className="rounded-md border border-warn-100 bg-warn-50/60 p-3">
              <div className="text-xs font-bold text-warn-600">
                {t("runExperiment.operatorApproval")}
              </div>
              <div className="mt-2 grid grid-cols-1 gap-3">
                <label className="flex cursor-pointer items-center gap-2 text-sm text-ink">
                  <input
                    type="checkbox"
                    checked={operatorConfirmed}
                    onChange={(e) => setOperatorConfirmed(e.target.checked)}
                    className="h-4 w-4 accent-warn-500"
                  />
                  <span>{t("runExperiment.operatorReady")}</span>
                </label>
                <input
                  type="hidden"
                  value={operatorToken}
                  onChange={(e) => setOperatorToken(e.target.value)}
                />
              </div>
            </div>
          )}
        </Card>
      </section>

      {/* Step 3: run */}
      <section className="space-y-3">
        <StepBadge n={3}>{t("runExperiment.step3")}</StepBadge>
        <Card className="flex flex-col items-start gap-3 p-5 md:flex-row md:items-center md:justify-between">
          <div className="text-sm text-muted">
            {running ? (
              <span className="flex items-center gap-2">
                <span className="h-2 w-2 animate-pulse rounded-full bg-brand-500" />
                {t("runExperiment.running")}
              </span>
            ) : (
              <span>{t("runExperiment.runReady")}</span>
            )}
          </div>
          <button
            id="run-button"
            type="button"
            onClick={onSubmit}
            disabled={running || !request.trim()}
            className="btn btn-primary px-6 py-3 text-sm"
          >
            {running ? t("runExperiment.runningButton") : t("runExperiment.runButton")}
          </button>
        </Card>
        {error && (
          <Card className="border-danger-100 bg-danger-50/60 p-3 text-sm text-danger-600">
            {error}
          </Card>
        )}
      </section>
    </div>
  );
}
