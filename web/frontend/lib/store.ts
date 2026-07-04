"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { DataMode, WorkflowResult } from "./types";

interface DashboardState {
  // The latest workflow result (mock / real_replay / live_lab). Null until
  // the user runs a workflow.
  result: WorkflowResult | null;
  setResult: (r: WorkflowResult | null) => void;

  evidenceMode: "Mock Demo" | "Sanitized Real Replay" | "Live Lab";
  setEvidenceMode: (m: DashboardState["evidenceMode"]) => void;

  operatorToken: string;
  setOperatorToken: (t: string) => void;

  // True while a workflow is running (used for the spinner / disabled state).
  isRunning: boolean;
  setRunning: (r: boolean) => void;

  lastError: string;
  setError: (e: string) => void;
}

export const dataModeFromEvidence = (
  m: DashboardState["evidenceMode"]
): DataMode => {
  if (m === "Sanitized Real Replay") return "real_replay";
  if (m === "Live Lab") return "live_lab";
  return "mock";
};

export const useDashboard = create<DashboardState>()(
  persist(
    (set) => ({
      result: null,
      setResult: (r) => set({ result: r }),
      evidenceMode: "Mock Demo",
      setEvidenceMode: (m) => set({ evidenceMode: m }),
      operatorToken: "",
      setOperatorToken: (t) => set({ operatorToken: t }),
      isRunning: false,
      setRunning: (r) => set({ isRunning: r }),
      lastError: "",
      setError: (e) => set({ lastError: e }),
    }),
    {
      name: "physical-ai-safety-dashboard",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        result: state.result,
        evidenceMode: state.evidenceMode,
      }),
    }
  )
);
