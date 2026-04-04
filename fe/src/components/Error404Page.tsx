import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiClient } from "../api/client";

type ErrorPageState = {
  errorMessage?: string;
  at?: string;
};

type BackendLogResponse = {
  lines?: string[];
  detail?: string;
};

export function Error404Page() {
  const location = useLocation();
  const state = (location.state as ErrorPageState | null) ?? null;
  const [logs, setLogs] = useState<string[]>([]);
  const [isLoadingLogs, setIsLoadingLogs] = useState(true);
  const [logsError, setLogsError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const fetchLogs = async () => {
      try {
        const response = await apiClient.get<BackendLogResponse>(
          "/api/v1/logs/backend",
          {
            params: { lines: 200 },
          },
        );

        if (!mounted) {
          return;
        }

        setLogs(response.data.lines ?? []);
      } catch (error) {
        if (!mounted) {
          return;
        }

        const message =
          error instanceof Error
            ? error.message
            : "Failed to load backend logs.";
        setLogsError(message);
      } finally {
        if (mounted) {
          setIsLoadingLogs(false);
        }
      }
    };

    void fetchLogs();

    return () => {
      mounted = false;
    };
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 px-4 py-10 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <section className="rounded-2xl border border-red-500/30 bg-red-950/30 p-6">
          <p className="text-sm font-semibold uppercase tracking-wide text-red-300">
            Error Page
          </p>
          <h1 className="mt-2 text-5xl font-black text-white">404</h1>
          <p className="mt-3 text-sm text-red-200">
            A critical action failed and the app redirected here.
          </p>
          <div className="mt-4 space-y-2 text-sm">
            <p>
              <span className="font-semibold text-red-300">
                Frontend error:
              </span>{" "}
              {state?.errorMessage ?? "Unknown error"}
            </p>
            <p>
              <span className="font-semibold text-red-300">Occurred at:</span>{" "}
              {state?.at ? new Date(state.at).toLocaleString() : "N/A"}
            </p>
          </div>
          <div className="mt-5">
            <Link
              to="/"
              className="inline-flex rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-200"
            >
              Back to Home
            </Link>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
          <h2 className="text-lg font-bold text-white">Backend Logs</h2>
          <p className="mt-1 text-sm text-slate-400">
            Latest 200 lines from backend log file.
          </p>

          {isLoadingLogs && (
            <p className="mt-4 rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-300">
              Loading backend logs...
            </p>
          )}

          {logsError && (
            <p className="mt-4 rounded-lg bg-red-900/40 px-3 py-2 text-sm text-red-200">
              {logsError}
            </p>
          )}

          {!isLoadingLogs && !logsError && (
            <pre className="custom-scrollbar mt-4 max-h-[50vh] overflow-auto rounded-lg border border-slate-700 bg-slate-950 p-3 text-xs leading-5 text-slate-200">
              {logs.length > 0 ? logs.join("\n") : "No backend logs available."}
            </pre>
          )}
        </section>
      </div>
    </main>
  );
}
