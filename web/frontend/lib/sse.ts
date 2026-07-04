"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, subscribeLabUpdates } from "@/lib/api";
import type { LabUpdateEvent } from "@/lib/types";

/**
 * Subscribe to /sse/lab on mount (when ``autoSubscribe`` is true) and
 * surface the latest event via React state so the UI re-renders on each
 * push. Returns the latest event (or null) and a manual refresh function
 * that pulls a one-shot snapshot via REST.
 */
export function useLabUpdates(autoSubscribe: boolean): {
  latest: LabUpdateEvent | null;
  refresh: () => Promise<void>;
} {
  const [latest, setLatest] = useState<LabUpdateEvent | null>(null);
  const lastUpdateAt = useRef(0);
  const refreshing = useRef(false);

  const applyLatest = useCallback((event: LabUpdateEvent) => {
    lastUpdateAt.current = Date.now();
    setLatest(event);
  }, []);

  const refresh = useCallback(async () => {
    if (refreshing.current) return;
    refreshing.current = true;
    try {
      const state = await api.labRefresh();
      applyLatest({
        ts: Date.now() / 1000,
        nodes: state.node_cache,
        jobs: state.jobs,
      });
    } catch {
      /* surfaced via UI error state elsewhere */
    } finally {
      refreshing.current = false;
    }
  }, [applyLatest]);

  // Seed from REST once so the UI shows real Cell data even if SSE is slow.
  useEffect(() => {
    if (!autoSubscribe) return;
    let cancelled = false;
    (async () => {
      try {
        const state = await api.labState();
        if (!cancelled && Object.keys(state.node_cache ?? {}).length > 0) {
          applyLatest({
            ts: state.node_cache_ts || Date.now() / 1000,
            nodes: state.node_cache,
            jobs: state.jobs ?? [],
          });
        }
      } catch {
        /* fall through to the fresh refresh below */
      } finally {
        if (!cancelled) void refresh();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [applyLatest, autoSubscribe, refresh]);

  // SSE subscription.
  useEffect(() => {
    if (!autoSubscribe) return;
    const unsub = subscribeLabUpdates(
      (event) => applyLatest(event),
      () => void 0
    );
    return unsub;
  }, [applyLatest, autoSubscribe]);

  // If the EventSource stream stalls behind the dev proxy, keep the dashboard
  // live with the same REST refresh path used by the manual button.
  useEffect(() => {
    if (!autoSubscribe) return;
    const id = window.setInterval(() => {
      const staleForMs = Date.now() - lastUpdateAt.current;
      if (!lastUpdateAt.current || staleForMs > 7000) void refresh();
    }, 5000);
    return () => window.clearInterval(id);
  }, [autoSubscribe, refresh]);

  return { latest, refresh };
}
