import { useEffect, useMemo } from "react";
import { FiAlertCircle, FiCheck, FiClock, FiLoader } from "react-icons/fi";
import type { GraphStatusResponse } from "../../types/run";
import type { RunResponse } from "../../types/run";
import { buildPipelineStepRows } from "../../utils/pipelineUi";
import type { PipelineHints } from "../../utils/pipelineUi";

type RunProgressModalProps = {
  isOpen: boolean;
  run: RunResponse | null;
  graphStatus: GraphStatusResponse | null;
  hints?: PipelineHints;
  onClose: () => void;
  /** When true, Escape and backdrop do not close while run is in-flight */
  lockWhileBusy?: boolean;
};

function StatusBadge({ status }: { status: string }) {
  const base =
    "rounded-full px-2.5 py-0.5 text-xs font-bold uppercase tracking-wide";
  if (status === "completed") {
    return (
      <span className={`${base} bg-emerald-500/15 text-emerald-300`}>
        {status}
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className={`${base} bg-red-500/15 text-red-300`}>{status}</span>
    );
  }
  if (status === "processing" || status === "queued") {
    return (
      <span className={`${base} bg-cyan-500/15 text-cyan-300`}>{status}</span>
    );
  }
  return (
    <span className={`${base} bg-zinc-500/20 text-zinc-300`}>{status}</span>
  );
}

export function RunProgressModal({
  isOpen,
  run,
  graphStatus,
  hints,
  onClose,
  lockWhileBusy = true,
}: RunProgressModalProps) {
  const busy =
    run?.status === "processing" ||
    run?.status === "queued" ||
    run?.status === "uploaded";

  const steps = useMemo(
    () => buildPipelineStepRows(run, graphStatus, hints),
    [run, graphStatus, hints],
  );

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && (!lockWhileBusy || !busy)) {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose, lockWhileBusy, busy]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && (!lockWhileBusy || !busy)) {
          onClose();
        }
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-progress-title"
        className="card-dark max-h-[90vh] w-full max-w-lg overflow-y-auto p-6 shadow-2xl"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2
              id="run-progress-title"
              className="text-lg font-bold text-[var(--fg-primary)]"
            >
              Run progress
            </h2>
            {run ? (
              <p className="mt-1 font-mono text-xs text-[var(--fg-muted)]">
                {run.run_id}
              </p>
            ) : null}
          </div>
          {run ? <StatusBadge status={run.status} /> : null}
        </div>

        {run?.current_node || graphStatus?.current_node ? (
          <p className="mb-4 text-sm text-[var(--fg-muted)]">
            Graph node:{" "}
            <span className="font-mono text-cyan-300/90">
              {run?.current_node ?? graphStatus?.current_node}
            </span>
            {(run?.progress_percentage ?? graphStatus?.progress_percentage) !=
            null ? (
              <span className="ml-2">
                (
                {run?.progress_percentage ?? graphStatus?.progress_percentage}
                %)
              </span>
            ) : null}
          </p>
        ) : null}

        <ul className="custom-scrollbar max-h-[50vh] space-y-2 overflow-y-auto pr-1">
          {steps.map((row) => (
            <li
              key={row.id}
              className="flex items-center gap-3 rounded-lg border border-zinc-700/50 bg-zinc-950/50 px-3 py-2"
            >
              {row.status === "done" ? (
                <FiCheck className="size-5 shrink-0 text-emerald-400" />
              ) : null}
              {row.status === "failed" ? (
                <FiAlertCircle className="size-5 shrink-0 text-red-400" />
              ) : null}
              {row.status === "running" ? (
                <FiLoader className="size-5 shrink-0 animate-spin text-cyan-400" />
              ) : null}
              {row.status === "pending" ? (
                <FiClock className="size-5 shrink-0 text-zinc-600" />
              ) : null}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-zinc-200">{row.label}</p>
                <p className="font-mono text-[10px] text-zinc-500">{row.id}</p>
              </div>
            </li>
          ))}
        </ul>

        {run?.error_message ? (
          <div
            className="mt-4 rounded-lg border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-200"
            role="alert"
          >
            {run.error_message}
          </div>
        ) : null}

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-lg border border-zinc-600 px-4 py-2 text-sm font-semibold text-zinc-300 hover:bg-zinc-800/80"
            onClick={onClose}
            disabled={lockWhileBusy && !!busy}
          >
            {busy ? "Running…" : "Close"}
          </button>
        </div>
      </div>
    </div>
  );
}
