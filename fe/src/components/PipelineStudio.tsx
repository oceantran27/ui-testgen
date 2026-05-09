import axios from "axios";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FiImage, FiLoader, FiTrash2, FiUploadCloud, FiZap } from "react-icons/fi";
import { Link } from "react-router-dom";
import { toast } from "react-hot-toast";
import {
  getStateGraphPipelineStatus,
  pollStateGraphUntilTerminal,
  postStateGraphPipelineStart,
} from "../api/stateGraph";
import { PipelineProgressModal } from "./PipelineProgressModal";
import { PipelineScenarioResultModal } from "./PipelineScenarioResultModal";
import { StateGraphResults } from "./StateGraphResults";
import type { StateGraphOrganizeResponsePayload } from "../types/stateGraph";

const createCorrelationId = (prefix: "req" | "batch"): string => {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return `${prefix}-${suffix}`;
};

function isImageFile(f: File): boolean {
  return f.type.startsWith("image/") && !f.type.includes("image/svg");
}

export function PipelineStudio() {
  const [pipelineFiles, setPipelineFiles] = useState<File[]>([]);
  const [pipeDragging, setPipeDragging] = useState(false);
  const [pipelineSubmitting, setPipelineSubmitting] = useState(false);
  const [pipelineFinal, setPipelineFinal] =
    useState<StateGraphOrganizeResponsePayload | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);

  const [progressOpen, setProgressOpen] = useState(false);
  const [pollStatus, setPollStatus] = useState<Awaited<
    ReturnType<typeof getStateGraphPipelineStatus>
  > | null>(null);
  const pollAbortRef = useRef<AbortController | null>(null);
  const [scenarioModalOpen, setScenarioModalOpen] = useState(false);

  const pipelinePreviewUrls = useMemo(() => {
    return pipelineFiles.map((f) => URL.createObjectURL(f));
  }, [pipelineFiles]);

  useEffect(() => {
    return () => {
      pipelinePreviewUrls.forEach((u) => {
        if (u.startsWith("blob:")) {
          URL.revokeObjectURL(u);
        }
      });
    };
  }, [pipelinePreviewUrls]);

  const extractErrorMessage = useCallback((error: unknown): string => {
    if (axios.isAxiosError(error)) {
      const detail = error.response?.data?.detail;
      if (typeof detail === "string" && detail.trim()) {
        return detail;
      }
      return error.message || "An unknown error occurred.";
    }
    if (error instanceof Error) {
      return error.message;
    }
    return "An unknown error occurred.";
  }, []);

  const addPipelineFiles = useCallback((incoming: FileList | File[]) => {
    const list = Array.from(incoming).filter(isImageFile);
    if (list.length === 0) {
      toast.error("Add image files (PNG, JPG, etc.).");
      return;
    }
    setPipelineFiles((prev) => [...prev, ...list]);
    setPipelineFinal(null);
    setPipelineError(null);
  }, []);

  const removePipelineFile = useCallback((index: number) => {
    setPipelineFiles((prev) => prev.filter((_, i) => i !== index));
    setPipelineFinal(null);
  }, []);

  const onPipeDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    setPipeDragging(true);
  };
  const onPipeDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setPipeDragging(false);
  };
  const onPipeDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };
  const onPipeDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setPipeDragging(false);
    if (e.dataTransfer.files?.length) {
      addPipelineFiles(e.dataTransfer.files);
    }
  };

  const runPipeline = async () => {
    if (pipelineFiles.length === 0) {
      toast.error("Add at least one screenshot.");
      return;
    }
    pollAbortRef.current?.abort();
    const ac = new AbortController();
    pollAbortRef.current = ac;

    setPipelineSubmitting(true);
    setPipelineError(null);
    setPipelineFinal(null);
    setScenarioModalOpen(false);
    setProgressOpen(true);
    setPollStatus(null);

    const requestId = createCorrelationId("req");
    const batchId = createCorrelationId("batch");
    try {
      const start = await postStateGraphPipelineStart(pipelineFiles, {
        "X-Request-Id": requestId,
        "X-Batch-Id": batchId,
      });
      const snapshot = await getStateGraphPipelineStatus(start.input_id);
      setPollStatus(snapshot);
      const final = await pollStateGraphUntilTerminal(start.input_id, {
        signal: ac.signal,
        onUpdate: setPollStatus,
      });
      if (final.status === "failed") {
        setPipelineError(final.error ?? "Pipeline failed.");
        toast.error(final.error ?? "Pipeline failed.");
      }
      if (final.result) {
        setPipelineFinal(final.result);
        toast.success("Pipeline completed.");
      } else if (final.status === "completed") {
        setPipelineError("Completed but response payload missing.");
        toast.error("Missing result payload.");
      }
    } catch (err) {
      const msg =
        err instanceof DOMException && err.name === "AbortError"
          ? "Cancelled."
          : extractErrorMessage(err);
      if (!(err instanceof DOMException)) {
        setPipelineError(msg);
        toast.error(msg);
      }
    } finally {
      setPipelineSubmitting(false);
      pollAbortRef.current = null;
    }
  };

  const pipelineDisplay =
    pipelineFinal ?? (pollStatus?.result ? pollStatus.result : null);

  const openScenarioResultsModal = () => {
    setProgressOpen(false);
    setScenarioModalOpen(true);
  };

  return (
    <div className="min-h-screen bg-zinc-950 bg-[radial-gradient(ellipse_120%_80%_at_50%_-20%,rgba(34,211,238,0.12),transparent)] text-zinc-100">
      <div className="container mx-auto p-4 sm:p-6 lg:p-8">
        <header className="mb-10 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-gradient text-4xl font-extrabold tracking-tight sm:text-5xl">
              UI TestGen
            </h1>
            <p className="mt-2 max-w-xl text-sm text-zinc-400">
              Multi-screen pipeline: dedupe → parallel UI extraction & intents → state graph → E2E
              Actor–Critic scenarios.
            </p>
          </div>
          <nav className="flex flex-wrap gap-4 text-sm font-semibold">
            <Link
              className="text-cyan-400/90 transition hover:text-cyan-300"
              to="/behavior-flows"
            >
              Behavior flow album
            </Link>
            <Link
              className="text-cyan-400/90 transition hover:text-cyan-300"
              to="/admin"
            >
              Admin
            </Link>
          </nav>
        </header>

        <main className="mx-auto max-w-4xl space-y-8">
          <div className="card-dark space-y-4">
            <h2 className="flex items-center text-xl font-bold text-zinc-100">
              <FiZap className="mr-2 text-cyan-400" aria-hidden />
              Full pipeline
              <span className="ml-2 text-sm font-normal text-zinc-500">(multi-image)</span>
            </h2>
            <p className="text-sm text-zinc-400">
              Upload unordered screenshots; the backend deduplicates near-identical frames, then runs
              vision + graph + scenario generation.
            </p>
            <div
              role="presentation"
              onDragEnter={onPipeDragEnter}
              onDragLeave={onPipeDragLeave}
              onDragOver={onPipeDragOver}
              onDrop={onPipeDrop}
              className={
                pipeDragging
                  ? "file-input-label-dark border-cyan-500/60 bg-cyan-950/30"
                  : "file-input-label-dark"
              }
            >
              <input
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                id="pipeline-multi-input"
                onChange={(e) => {
                  if (e.target.files?.length) {
                    addPipelineFiles(e.target.files);
                  }
                  e.target.value = "";
                }}
              />
              <label htmlFor="pipeline-multi-input" className="block cursor-pointer">
                Drop screenshots here or click to browse (multi-select)
              </label>
            </div>

            {pipelineFiles.length > 0 ? (
              <ul className="custom-scrollbar flex max-h-56 flex-col gap-2 overflow-y-auto rounded-lg border border-zinc-700/60 p-2">
                {pipelineFiles.map((f, i) => (
                  <li
                    key={`${f.name}-${i}`}
                    className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/80 px-2 py-1.5"
                  >
                    <div className="h-11 w-11 shrink-0 overflow-hidden rounded border border-zinc-700">
                      {pipelinePreviewUrls[i] ? (
                        <img
                          src={pipelinePreviewUrls[i]}
                          alt=""
                          className="h-full w-full object-cover"
                        />
                      ) : null}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-zinc-200">{f.name}</p>
                      <p className="text-xs text-zinc-500">
                        {(f.size / 1024).toFixed(0)} KB
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        removePipelineFile(i);
                      }}
                      className="shrink-0 rounded p-1.5 text-zinc-500 hover:bg-red-950/80 hover:text-red-300"
                      aria-label={`Remove ${f.name}`}
                    >
                      <FiTrash2 />
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}

            <button
              type="button"
              disabled={pipelineSubmitting || pipelineFiles.length === 0}
              className="btn btn-primary"
              onClick={() => void runPipeline()}
            >
              {pipelineSubmitting ? (
                <FiLoader className="-ml-1 mr-2 animate-spin" />
              ) : (
                <FiUploadCloud className="-ml-1 mr-2" />
              )}
              {pipelineSubmitting ? "Running pipeline…" : "Run full pipeline"}
            </button>

            {pipelineError ? (
              <div
                className="rounded-lg border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-200"
                role="alert"
              >
                {pipelineError}
              </div>
            ) : null}
          </div>
        </main>

        {pipelineDisplay ? (
          <div className="mx-auto mt-12 max-w-5xl pb-16">
            <StateGraphResults payload={pipelineDisplay} />
          </div>
        ) : (
          <div className="mx-auto mt-8 max-w-5xl pb-16 text-center text-sm text-zinc-600">
            {pipelineSubmitting ? (
              <p className="flex items-center justify-center gap-2">
                <FiLoader className="animate-spin text-cyan-500" aria-hidden /> Pipeline running…
                open progress for live phases.
              </p>
            ) : (
              <p className="flex items-center justify-center gap-2">
                <FiImage className="text-zinc-700" aria-hidden />
                Pipeline results appear here when a run succeeds.
              </p>
            )}
          </div>
        )}
      </div>

      <PipelineProgressModal
        isOpen={progressOpen || pipelineSubmitting}
        pollingActive={pipelineSubmitting}
        status={pollStatus}
        onClose={() => {
          if (
            pipelineSubmitting &&
            pollStatus?.status !== "completed" &&
            pollStatus?.status !== "failed"
          ) {
            return;
          }
          setProgressOpen(false);
        }}
        onShowResult={pipelineDisplay ? openScenarioResultsModal : undefined}
      />

      <PipelineScenarioResultModal
        isOpen={scenarioModalOpen}
        payload={pipelineDisplay}
        onClose={() => setScenarioModalOpen(false)}
      />
    </div>
  );
}
