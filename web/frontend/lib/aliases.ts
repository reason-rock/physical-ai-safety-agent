"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

/**
 * Per-node display aliases, stored in a global Zustand store with
 * localStorage persistence so the same alias is visible everywhere
 * (CellCard, JobCard, Sidebar, Plan page, etc.) and survives reloads.
 *
 * The canonical keys are "gpu0" / "gpu1". Components call
 * ``useAlias("gpu0")`` to get the user's name (or fallback) and
 * ``useSetAlias`` to change it.
 */

const CANONICAL_FALLBACK: Record<string, string> = {
  gpu0: "GPU0",
  gpu1: "GPU1",
};

interface AliasState {
  aliases: Partial<Record<string, string>>;
  setAlias: (key: string, alias: string) => void;
  resetAlias: (key: string) => void;
}

export const useAliasStore = create<AliasState>()(
  persist(
    (set) => ({
      aliases: {},
      setAlias: (key, alias) =>
        set((state) => {
          const trimmed = alias.trim();
          const next = { ...state.aliases };
          // Empty alias or alias === canonical name both reset to default.
          if (!trimmed || trimmed.toLowerCase() === CANONICAL_FALLBACK[key]?.toLowerCase()) {
            delete next[key];
          } else {
            next[key] = trimmed;
          }
          return { aliases: next };
        }),
      resetAlias: (key) =>
        set((state) => {
          const next = { ...state.aliases };
          delete next[key];
          return { aliases: next };
        }),
    }),
    {
      name: "gaitlab.nodeAliases.v1",
      storage: createJSONStorage(() =>
        typeof window !== "undefined" ? window.localStorage : (undefined as unknown as Storage)
      ),
    }
  )
);

/**
 * Convenience hook: returns the alias for ``key`` (or the canonical
 * fallback "GPU0" / "GPU1" when no alias is set). Re-renders any
 * component that consumes it when the alias changes.
 *
 * ``key`` is normalised to lowercase to avoid "GPU0" vs "gpu0" bugs.
 */
export function useAlias(key: string): string {
  const k = key.toLowerCase();
  const alias = useAliasStore((s) => s.aliases[k]);
  return alias || CANONICAL_FALLBACK[k] || key;
}

/** Convenience setter hook. */
export function useSetAlias(): (key: string, alias: string) => void {
  return useAliasStore((s) => s.setAlias);
}

/** Format a number of seconds as ``2h 13m`` / ``14m 32s`` / ``42s``. */
export function formatElapsed(sec: number | undefined): string {
  if (!sec || sec <= 0) return "—";
  const s = Math.floor(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${r}s`;
  return `${r}s`;
}

/**
 * Pure helper for components that can't use hooks (e.g. plain functions).
 * Reads the current alias synchronously from the store.
 */
export function aliasFor(key: string): string {
  const k = key.toLowerCase();
  const alias = useAliasStore.getState().aliases[k];
  return alias || CANONICAL_FALLBACK[k] || key;
}

/**
 * Convert a node name that might come from the backend ("GPU0", "GPU1")
 * into the user's chosen alias. Use this anywhere a backend string needs
 * to be displayed.
 */
export function displayNodeName(rawName: string | undefined | null): string {
  if (!rawName) return "—";
  return aliasFor(rawName);
}

/**
 * Replace canonical backend node labels in user-visible prose. This keeps the
 * backend payload stable while making Markdown reports honor the same aliases
 * used by cards, charts, and tables.
 */
export function displayNodeAliasesInText(
  input: string,
  names?: { gpu0?: string; gpu1?: string }
): string {
  const replacements: Array<[string, string]> = [
    ["GPU0", names?.gpu0 ?? aliasFor("gpu0")],
    ["GPU1", names?.gpu1 ?? aliasFor("gpu1")],
    ["gpu0", names?.gpu0 ?? aliasFor("gpu0")],
    ["gpu1", names?.gpu1 ?? aliasFor("gpu1")],
  ];

  return replacements.reduce((text, [canonical, display]) => {
    const pattern = new RegExp(`\\b${canonical}\\b`, "g");
    return text.replace(pattern, () => display);
  }, input);
}
