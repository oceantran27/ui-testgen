import axios from "axios";
import { useCallback, useEffect, useMemo, useState } from "react";
import { FiImage, FiLoader, FiTrash2, FiUploadCloud } from "react-icons/fi";
import { Link } from "react-router-dom";
import { toast } from "react-hot-toast";
import { postBehaviorFlowOrganize } from "../api/behaviorFlow";
import { responseToViewGroups } from "../utils/behaviorFlowMappers";
import type { BehaviorFlowViewGroup } from "../types/behaviorFlow";
import { BehaviorFlowAlbum } from "./BehaviorFlowAlbum";
import { BehaviorFlowNav } from "./BehaviorFlowNav";

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

function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      return JSON.stringify(detail);
    }
    return error.message || "An unknown error occurred.";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "An unknown error occurred.";
}

function isImageFile(f: File) {
  return f.type.startsWith("image/") && !f.type.includes("image/svg");
}

export function BehaviorFlowPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [viewGroups, setViewGroups] = useState<BehaviorFlowViewGroup[] | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [lastInputId, setLastInputId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const previewUrls = useMemo(() => {
    return files.map((f) => URL.createObjectURL(f));
  }, [files]);

  useEffect(() => {
    return () => {
      previewUrls.forEach((u) => {
        if (u.startsWith("blob:")) {
          URL.revokeObjectURL(u);
        }
      });
    };
  }, [previewUrls]);

  const addFiles = useCallback((incoming: FileList | File[]) => {
    const list = Array.from(incoming).filter(isImageFile);
    if (list.length === 0) {
      toast.error("Add image files (PNG, JPG, etc.).");
      return;
    }
    setFiles((prev) => [...prev, ...list]);
    setViewGroups(null);
    setErrorMessage(null);
    setLastInputId(null);
  }, []);

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setViewGroups(null);
    setErrorMessage(null);
  }, []);

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(e.target.files);
    }
    e.target.value = "";
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const onDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  };

  const handleOrganize = async () => {
    if (files.length === 0) {
      toast.error("Add at least one image.");
      return;
    }
    const toastId = toast.loading("Clustering and ordering screenshots…");
    setIsSubmitting(true);
    setErrorMessage(null);
    setViewGroups(null);
    setLastInputId(null);

    const requestId = createCorrelationId("req");
    const batchId = createCorrelationId("batch");

    try {
      const data = await postBehaviorFlowOrganize(files, {
        "X-Request-Id": requestId,
        "X-Batch-Id": batchId,
      });
      setLastInputId(data.input_id);
      setViewGroups(responseToViewGroups(data, files));
      toast.success("Behavior flows ready.", { id: toastId });
    } catch (err) {
      const msg = extractErrorMessage(err);
      setErrorMessage(msg);
      toast.error(msg, { id: toastId });
    } finally {
      setIsSubmitting(false);
    }
  };

  const hasResults = viewGroups && viewGroups.length > 0;
  const showEmpty = !isSubmitting && !hasResults && !errorMessage;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="container mx-auto max-w-5xl p-4 sm:p-6 lg:p-8">
        <header className="mb-8 text-center">
          <h1 className="text-gradient text-4xl font-extrabold sm:text-5xl">
            Behavior flow album
          </h1>
          <p className="mt-2 text-lg text-zinc-400">
            Upload many UI screenshots; we group and order them by user flow (legacy clustering).
          </p>
          <div className="mt-4">
            <Link
              to="/"
              className="font-semibold text-cyan-400 hover:text-cyan-300"
            >
              Back to home
            </Link>
          </div>
        </header>

        <div className="space-y-8">
          <div className="card">
            <h2 className="mb-3 flex items-center text-2xl font-bold text-zinc-100">
              <FiUploadCloud className="mr-3 text-cyan-400" />
              Multi-image upload
            </h2>
            <p className="mb-4 text-sm text-zinc-400">
              Choose or drag in multiple screenshots. Order here does not matter —
              the server will cluster and order by behavior flow. Submit uses the
              same order to label <code className="font-mono text-zinc-300">img_001</code>, …
            </p>

            <div
              onDragEnter={onDragEnter}
              onDragLeave={onDragLeave}
              onDragOver={onDragOver}
              onDrop={onDrop}
              className={
                isDragging
                  ? "file-input-label border-blue-400 bg-blue-50/80"
                  : "file-input-label"
              }
            >
              <input
                type="file"
                accept="image/*"
                multiple
                onChange={onInputChange}
                className="hidden"
                id="behavior-flow-file-input"
              />
              <label
                htmlFor="behavior-flow-file-input"
                className="block cursor-pointer"
              >
                Drop images here or click to browse (multi-select)
              </label>
            </div>

            {files.length > 0 ? (
              <ul className="mt-4 flex max-h-56 flex-col gap-2 overflow-y-auto custom-scrollbar rounded-lg border border-zinc-700/60 p-2">
                {files.map((f, i) => (
                  <li
                    key={`${f.name}-${i}`}
                    className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/70 px-2 py-1.5"
                  >
                    <div className="h-12 w-12 shrink-0 overflow-hidden rounded border border-zinc-700">
                      {previewUrls[i] ? (
                        <img
                          src={previewUrls[i]}
                          alt=""
                          className="h-full w-full object-cover"
                        />
                      ) : null}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-zinc-200">
                        {f.name}
                      </p>
                      <p className="text-xs text-zinc-500">
                        <span className="font-mono text-zinc-400">img_{String(i + 1).padStart(3, "0")}</span>
                        {" · "}
                        {(f.size / 1024).toFixed(0)} KB
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        removeFile(i);
                      }}
                      className="shrink-0 rounded p-1.5 text-zinc-500 hover:bg-red-950/60 hover:text-red-300"
                      aria-label={`Remove ${f.name}`}
                    >
                      <FiTrash2 />
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  void handleOrganize();
                }}
                disabled={isSubmitting || files.length === 0}
                className="btn btn-primary"
              >
                {isSubmitting ? (
                  <FiLoader className="-ml-1 mr-2 animate-spin" />
                ) : null}
                {isSubmitting ? "Organizing…" : "Organize by behavior flow"}
              </button>
              {lastInputId ? (
                <span className="text-sm text-zinc-400">
                  Input ID: <code className="font-mono text-zinc-200">{lastInputId}</code>
                </span>
              ) : null}
            </div>
          </div>

          {errorMessage ? (
            <div
              className="rounded-xl border border-red-500/40 bg-red-950/40 px-4 py-3 text-sm text-red-200"
              role="alert"
            >
              {errorMessage}
            </div>
          ) : null}

          {showEmpty && files.length > 0 ? (
            <div className="card flex flex-col items-center justify-center gap-2 py-12 text-center text-zinc-500">
              <FiImage className="h-12 w-12 text-zinc-600" aria-hidden />
              <p>Press <strong>Organize by behavior flow</strong> to see results.</p>
            </div>
          ) : null}

          {showEmpty && files.length === 0 ? (
            <div className="card flex flex-col items-center justify-center gap-2 py-12 text-center text-zinc-500">
              <FiImage className="h-12 w-12 text-zinc-600" aria-hidden />
              <p>No images yet. Add screenshots to get started.</p>
            </div>
          ) : null}

          {isSubmitting ? (
            <div>
              <h3 className="mb-2 text-sm font-semibold text-zinc-400">
                Analyzing…
              </h3>
              <BehaviorFlowAlbum groups={[]} isLoading />
            </div>
          ) : null}

          {!isSubmitting && hasResults && viewGroups ? (
            <>
              <BehaviorFlowNav groups={viewGroups} />
              <BehaviorFlowAlbum groups={viewGroups} isLoading={false} />
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
