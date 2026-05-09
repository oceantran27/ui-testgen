import { useEffect, useMemo, useRef } from "react";
import { FiAlertCircle, FiCheck, FiClock, FiLoader } from "react-icons/fi";
import type {
  PipelinePhaseProgress,
  PipelineRunTiming,
  RunStatus,
  StateGraphRunStatusResponsePayload,
} from "../types/stateGraph";
import { formatMillis } from "../utils/formatMillis";

type PipelineProgressModalProps = {
  isOpen: boolean;
  status: StateGraphRunStatusResponsePayload | null;
  onClose: () => void;
  onShowResult?: () => void;
  /** True while awaiting HTTP polling (covers gap before first status payload). */
  pollingActive?: boolean;
};

function PhaseIcon({ row }: { row: PipelinePhaseProgress }) {
  if (row.status === "completed") {
    return <FiCheck className="size-5 text-emerald-400" aria-hidden />;
  }
  if (row.status === "failed") {
    return <FiAlertCircle className="size-5 text-red-400" aria-hidden />;
  }
  if (row.status === "running") {
    return <FiLoader className="size-5 animate-spin text-cyan-400" aria-hidden />;
  }
  return <FiClock className="size-5 text-zinc-500" aria-hidden />;
}

function summarizeRunStatus(run: RunStatus): string {
  if (run === "queued") return "Queued";
  if (run === "running") return "Running";
  if (run === "completed") return "Completed";
  return "Failed";
}

export function PipelineProgressModal({
  isOpen,
  status,
  onClose,
  onShowResult,
  pollingActive = false,
}: PipelineProgressModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (status?.status !== "running" && status?.status !== "queued") {
          onClose();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose, status?.status]);

  const timing: PipelineRunTiming | null | undefined = status?.timing;

  const phaseRows = useMemo(() => status?.phases ?? [], [status?.phases]);

  if (!isOpen) {
    return null;
  }

  const busy =
    pollingActive ||
    status?.status === "queued" ||
    status?.status === "running";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="pipeline-progress-title"
        className="card-dark max-h-[90vh] w-full max-w-lg overflow-y-auto p-6 shadow-2xl"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2
              id="pipeline-progress-title"
              className="text-lg font-bold text-zinc-100"
            >
              Pipeline progress
            </h2>
            {status ? (
              <p className="mt-1 text-xs text-zinc-500">
                Run:{" "}
                <span className="font-mono text-zinc-300">{status.input_id}</span>
                {" · "}
                {summarizeRunStatus(status.status)}
              </p>
            ) : (
              <p className="mt-1 text-xs text-zinc-500">Starting…</p>
            )}
          </div>
          {busy ? (
            <FiLoader className="mt-1 size-6 shrink-0 animate-spin text-cyan-400" />
          ) : null}
        </div>

        {status?.error ? (
          <div
            className="mb-4 rounded-lg border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-200"
            role="alert"
          >
            {status.error}
          </div>
        ) : null}

        <ol className="space-y-3">
          {phaseRows.map((row) => (
            <li
              key={row.id}
              className="flex gap-3 rounded-lg border border-zinc-700/60 bg-zinc-900/50 px-3 py-2.5"
            >
              <div className="pt-0.5">
                <PhaseIcon row={row} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-zinc-100">{row.label}</p>
                <p className="text-xs text-zinc-500">
                  {row.status === "running" && row.started_at_iso
                    ? `Started ${row.started_at_iso}`
                    : null}
                  {row.status === "completed" && row.duration_ms != null
                    ? formatMillis(row.duration_ms)
                    : null}
                  {row.status === "pending" ? "Waiting" : null}
                  {row.status === "failed" ? "Failed" : null}
                </p>
              </div>
            </li>
          ))}
        </ol>

        {timing && status?.status === "completed" ? (
          <div className="mt-5 rounded-lg border border-zinc-700/60 bg-zinc-950/80 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Timings
            </p>
            <ul className="mt-2 space-y-1 text-sm text-zinc-300">
              {timing.phases.map((p) => (
                <li key={p.phase_id} className="flex justify-between gap-2">
                  <span className="text-zinc-400">{p.label}</span>
                  <span className="font-mono text-zinc-200">
                    {formatMillis(p.duration_ms)}
                  </span>
                </li>
              ))}
            </ul>
            <div className="mt-2 flex justify-between border-t border-zinc-700/50 pt-2 text-sm font-semibold text-zinc-100">
              <span>Total (wall)</span>
              <span className="font-mono">{formatMillis(timing.wall_clock_ms)}</span>
            </div>
          </div>
        ) : null}

        <div className="mt-6 flex flex-wrap justify-end gap-2">
          {status?.status === "completed" && onShowResult ? (
            <button type="button" className="btn btn-primary" onClick={onShowResult}>
              Show result
            </button>
          ) : null}
          <button
            type="button"
            className="btn border border-zinc-600 bg-zinc-800 text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
            onClick={onClose}
            disabled={busy}
          >
            {busy ? "Running…" : "Close"}
          </button>
        </div>
      </div>
    </div>
  );
}
