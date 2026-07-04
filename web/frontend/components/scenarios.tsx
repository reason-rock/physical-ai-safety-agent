"use client";

import type { ReactNode } from "react";
import { displayNodeAliasesInText, useAlias } from "@/lib/aliases";

/** Pre-built experiment scenarios. Picking one fills the Run Experiment form
 *  so the user never has to write the prompt from scratch. */

export interface Scenario {
  id: string;
  emoji: string;
  title: string;
  oneLine: string;
  /** Exact prompt text dropped into the textarea. */
  request: string;
  /** Recommended safety strictness for this scenario. */
  strictness: "standard" | "strict";
  /** Recommended rollout count. */
  rollouts: number;
  /** Suggested patch (only used in Live Lab mode). */
  patchHint?: Record<string, number>;
  /** Tone for the badge in the UI. */
  tone: "warn" | "danger" | "brand" | "safe";
}

export const SCENARIOS: Scenario[] = [
  {
    id: "forward-fall",
    emoji: "forward",
    title: "Fix forward falls",
    oneLine: "Compare the previous stable baseline against a stability-focused treatment.",
    request: `Recent replay evidence shows the previous stable baseline improved reward, but the latest matched evaluation packet still shows forward pitch spikes after push recovery and joint-limit usage near the safety limit. Keep the previous stable baseline unchanged on the control training rig. On the treatment training rig, run one treatment with +30% torso orientation penalty and +15% action smoothness using the same seed group and evaluation script. Do not send hardware commands; return the comparison, failure notes, and whether this is blocked, supported-harness only, or ready for human hardware review.`,
    strictness: "standard",
    rollouts: 256,
    patchHint: {
      "reward.orientation_penalty": 1.3,
      "reward.action_smoothness": 1.15,
    },
    tone: "warn",
  },
  {
    id: "frozen-gait",
    emoji: "frozen",
    title: "Unstick frozen gait",
    oneLine: "Policy is stable but barely moves; boost velocity reward.",
    request: `The latest candidate does not fall but barely moves. Increase velocity tracking reward on the treatment training rig and compare it against the unchanged previous stable baseline on the control training rig. Do not send hardware commands; return the comparison and the safety verdict.`,
    strictness: "standard",
    rollouts: 256,
    patchHint: {
      "reward.velocity_tracking": 1.25,
    },
    tone: "brand",
  },
  {
    id: "hardware-check",
    emoji: "robot",
    title: "Hardware test gate",
    oneLine: "Is this checkpoint safe to put on the real robot?",
    request: `Evaluate the latest treatment checkpoint under the standard physical-AI safety evaluation and decide whether it is ready for human hardware review. Do not send any motor command; return the safety level, blocking reasons, and required pre-test actions.`,
    strictness: "strict",
    rollouts: 512,
    tone: "danger",
  },
];

export function ScenarioCard({
  scenario,
  active,
  onPick,
}: {
  scenario: Scenario;
  active: boolean;
  onPick: () => void;
}) {
  const gpu0Name = useAlias("gpu0");
  const gpu1Name = useAlias("gpu1");
  const oneLine = displayNodeAliasesInText(scenario.oneLine, {
    gpu0: gpu0Name,
    gpu1: gpu1Name,
  });

  return (
    <button
      type="button"
      onClick={onPick}
      className={`card card-hoverable group flex flex-col gap-2 p-4 text-left transition ${
        active ? "ring-2 ring-brand-500 ring-offset-2 ring-offset-bg" : ""
      }`}
    >
      <div className="flex items-center justify-between">
        <span
          className={`pill ${
            scenario.tone === "danger"
              ? "pill--danger"
              : scenario.tone === "warn"
                ? "pill--warn"
                : scenario.tone === "safe"
                  ? "pill--safe"
                  : "pill--brand"
          }`}
        >
          {scenario.emoji}
        </span>
        {active && <span className="pill pill--brand">selected</span>}
      </div>
      <div className="text-sm font-bold text-ink">{scenario.title}</div>
      <div className="text-xs text-muted">{oneLine}</div>
    </button>
  );
}

export function StepBadge({ n, children }: { n: number; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-500 text-xs font-black text-white">
        {n}
      </span>
      <span className="text-sm font-bold text-ink">{children}</span>
    </div>
  );
}
