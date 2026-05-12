import { useCallback, useEffect, useRef, useState } from "react";
import { getGraphStatus, getRun } from "../api/runs";
import type { GraphStatusResponse, RunResponse } from "../types/run";

const TERMINAL_RUN_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
]);

export type UseRunPollingOptions = {
  enabled?: boolean;
  intervalMs?: number;
};

export function useRunPolling(
  runId: string | null | undefined,
  options: UseRunPollingOptions = {},
) {
  const { enabled = true, intervalMs = 2000 } = options;
  const [run, setRun] = useState<RunResponse | null>(null);
  const [graphStatus, setGraphStatus] = useState<GraphStatusResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const runIdRef = useRef(runId);
  const lastGraphRef = useRef<GraphStatusResponse | null>(null);

  runIdRef.current = runId;

  const refresh = useCallback(async () => {
    const id = runIdRef.current;
    if (!id) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const r = await getRun(id);
      setRun(r);
      try {
        const g = await getGraphStatus(id);
        lastGraphRef.current = g;
        setGraphStatus(g);
      } catch {
        setGraphStatus(lastGraphRef.current);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load run");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!runId || !enabled) {
      return;
    }
    lastGraphRef.current = null;
    setGraphStatus(null);
    let cancelled = false;

    const tick = async () => {
      if (cancelled || !runIdRef.current) {
        return;
      }
      try {
        const r = await getRun(runId);
        if (cancelled) {
          return;
        }
        setRun(r);
        setError(null);

        try {
          const g = await getGraphStatus(runId);
          if (cancelled) {
            return;
          }
          lastGraphRef.current = g;
          setGraphStatus(g);
        } catch {
          if (!cancelled) {
            setGraphStatus(lastGraphRef.current);
          }
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Poll failed");
        }
      }
    };

    void tick();
    const timer = window.setInterval(() => {
      void tick();
    }, intervalMs);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [runId, enabled, intervalMs]);

  const isTerminal =
    run != null && TERMINAL_RUN_STATUSES.has(run.status);

  return {
    run,
    graphStatus,
    loading,
    error,
    refresh,
    isTerminal,
  };
}
