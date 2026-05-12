import { useCallback, useEffect, useMemo, useState } from "react";
import {
  FiImage,
  FiLoader,
  FiTrash2,
  FiUploadCloud,
  FiZap,
} from "react-icons/fi";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "react-hot-toast";
import {
  createRun,
  deleteRun,
  listRuns,
  submitRun,
  uploadRunImages,
} from "../../api/runs";
import { AppShell } from "../layout/AppShell";
import { extractApiError } from "../../utils/errors";
import type { RunResponse } from "../../types/run";

function isImageFile(f: File): boolean {
  return f.type.startsWith("image/") && !f.type.includes("image/svg");
}

export function RunListPage() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<RunResponse[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [createdRunId, setCreatedRunId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const [files, setFiles] = useState<File[]>([]);
  const [projectName, setProjectName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [dragging, setDragging] = useState(false);

  const previewUrls = useMemo(
    () => files.map((f) => URL.createObjectURL(f)),
    [files],
  );

  useEffect(() => {
    return () => {
      previewUrls.forEach((u) => {
        if (u.startsWith("blob:")) {
          URL.revokeObjectURL(u);
        }
      });
    };
  }, [previewUrls]);

  const loadRuns = useCallback(async () => {
    setListLoading(true);
    setListError(null);
    try {
      const res = await listRuns();
      setRuns(res.runs);
    } catch (e) {
      setListError(extractApiError(e));
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  const addFiles = useCallback((incoming: FileList | File[]) => {
    const list = Array.from(incoming).filter(isImageFile);
    if (list.length === 0) {
      toast.error("Add image files (PNG, JPG, etc.).");
      return;
    }
    setFiles((prev) => [...prev, ...list]);
  }, []);

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleDeleteRun = async (e: React.MouseEvent, runId: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this run?")) return;
    try {
      await deleteRun(runId);
      toast.success("Run deleted.");
      void loadRuns();
    } catch (e) {
      toast.error(extractApiError(e));
    }
  };

  const handleStep1Next = async () => {
    setSubmitting(true);
    try {
      const run = await createRun({
        project_name: projectName.trim() || undefined,
        description: description.trim() || undefined,
      });
      setCreatedRunId(run.run_id);
      setStep(2);
    } catch (e) {
      toast.error(extractApiError(e));
    } finally {
      setSubmitting(false);
    }
  };

  const handleUploadImages = async () => {
    if (!createdRunId) return;
    if (files.length === 0) {
      toast.error("Add at least one screenshot.");
      return;
    }
    setUploading(true);
    try {
      const up = await uploadRunImages(createdRunId, files);
      if ((up.failed_count ?? 0) > 0) {
        toast.error(`${up.failed_count ?? 0} file(s) failed to upload.`);
      }
      if ((up.uploaded_count ?? 0) > 0) {
        setStep(3);
      }
    } catch (e) {
      toast.error(extractApiError(e));
    } finally {
      setUploading(false);
    }
  };

  const handleFinalSubmit = async () => {
    if (!createdRunId) return;
    setSubmitting(true);
    try {
      await submitRun(createdRunId);
      toast.success("Run submitted successfully.");
      navigate(`/runs/${encodeURIComponent(createdRunId)}`);
    } catch (e) {
      toast.error(extractApiError(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppShell>
      <div className="grid gap-10 lg:grid-cols-5">
        <section className="card-dark space-y-6 lg:col-span-3">
          <div className="flex items-center justify-between border-b border-zinc-800 pb-4">
            <h2 className="flex items-center text-xl font-bold text-[var(--fg-primary)]">
              <FiZap className="mr-2 text-[var(--accent)]" aria-hidden />
              New Analysis Run
            </h2>
            <div className="flex gap-2">
              {[1, 2, 3].map((s) => (
                <div
                  key={s}
                  className={`h-2 w-8 rounded-full transition-colors ${
                    step >= s ? "bg-cyan-500" : "bg-zinc-800"
                  }`}
                />
              ))}
            </div>
          </div>

          {step === 1 && (
            <div className="space-y-4">
              <div className="space-y-1">
                <p className="text-sm font-semibold text-zinc-100">
                  Step 1: Run Information
                </p>
                <p className="text-xs text-zinc-500">
                  Define the project for this analysis.
                </p>
              </div>
              <label className="block text-xs font-bold uppercase tracking-wider text-zinc-500">
                Project Name
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-950/80 px-3 py-2 text-sm text-zinc-100"
                  placeholder="e.g. Checkout Redesign"
                />
              </label>
              <label className="block text-xs font-bold uppercase tracking-wider text-zinc-500">
                Description
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={3}
                  className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-950/80 px-3 py-2 text-sm text-zinc-100"
                  placeholder="Goals or context for this analysis..."
                />
              </label>
              <div className="pt-4">
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => void handleStep1Next()}
                  className="btn btn-primary w-full sm:w-auto"
                >
                  {submitting && <FiLoader className="mr-2 animate-spin" />}
                  Continue to Upload
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <div className="space-y-1">
                <p className="text-sm font-semibold text-zinc-100">
                  Step 2: Upload Screenshots
                </p>
                <p className="text-xs text-zinc-500">
                  Upload high-quality viewport screenshots of the user flow.
                </p>
              </div>

              <div
                role="presentation"
                onDragEnter={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={(e) => {
                  e.preventDefault();
                  setDragging(false);
                }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  if (e.dataTransfer.files?.length) {
                    addFiles(e.dataTransfer.files);
                  }
                }}
                className={
                  dragging
                    ? "file-input-label-dark border-cyan-500/60 bg-cyan-950/30"
                    : "file-input-label-dark"
                }
              >
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  className="hidden"
                  id="new-run-files"
                  onChange={(e) => {
                    if (e.target.files?.length) {
                      addFiles(e.target.files);
                    }
                    e.target.value = "";
                  }}
                />
                <label htmlFor="new-run-files" className="block cursor-pointer">
                  <FiUploadCloud className="mx-auto mb-2 text-2xl text-zinc-600" />
                  Drop screenshots here or click to browse
                </label>
              </div>

              {files.length > 0 && (
                <ul className="custom-scrollbar grid grid-cols-2 gap-2 overflow-y-auto rounded-lg border border-zinc-800 p-2 sm:grid-cols-3">
                  {files.map((f, i) => (
                    <li
                      key={`${f.name}-${i}`}
                      className="group relative h-24 overflow-hidden rounded-lg border border-zinc-800"
                    >
                      {previewUrls[i] && (
                        <img
                          src={previewUrls[i]}
                          alt=""
                          className="h-full w-full object-cover transition group-hover:scale-105"
                        />
                      )}
                      <button
                        type="button"
                        onClick={() => removeFile(i)}
                        className="absolute right-1 top-1 rounded bg-red-600 p-1 text-white opacity-0 transition group-hover:opacity-100"
                      >
                        <FiTrash2 size={12} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  disabled={uploading || files.length === 0}
                  onClick={() => void handleUploadImages()}
                  className="btn btn-primary"
                >
                  {uploading && <FiLoader className="mr-2 animate-spin" />}
                  {uploading ? "Uploading..." : "Upload Images"}
                </button>
                <button
                  type="button"
                  disabled={uploading}
                  onClick={() => setStep(1)}
                  className="rounded-lg px-4 py-2 text-sm font-semibold text-zinc-400 hover:bg-zinc-900"
                >
                  Back
                </button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <div className="space-y-1">
                <p className="text-sm font-semibold text-zinc-100">
                  Step 3: Review & Submit
                </p>
                <p className="text-xs text-zinc-500">
                  Verify the uploaded images before starting the LangGraph pipeline.
                </p>
              </div>

              <div className="rounded-lg border border-amber-500/20 bg-amber-950/10 p-3 text-xs text-amber-200/70">
                <strong>Ordering Warning:</strong> If screenshots are not uploaded
                in the correct chronological order, the AI will still attempt to
                infer the flow using structured reasoning, but grounding confidence
                may be reduced.
              </div>

              <div className="grid grid-cols-4 gap-2">
                {files.slice(0, 8).map((_, i) => (
                  <div
                    key={i}
                    className="aspect-square rounded border border-zinc-800 bg-zinc-900"
                  >
                    {previewUrls[i] && (
                      <img
                        src={previewUrls[i]}
                        alt=""
                        className="h-full w-full object-cover"
                      />
                    )}
                  </div>
                ))}
                {files.length > 8 && (
                  <div className="flex aspect-square items-center justify-center rounded border border-zinc-800 bg-zinc-900 text-xs font-bold text-zinc-500">
                    +{files.length - 8} MORE
                  </div>
                )}
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => void handleFinalSubmit()}
                  className="btn btn-primary"
                >
                  {submitting && <FiLoader className="mr-2 animate-spin" />}
                  Submit to Pipeline
                </button>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => setStep(2)}
                  className="rounded-lg px-4 py-2 text-sm font-semibold text-zinc-400 hover:bg-zinc-900"
                >
                  Back to Upload
                </button>
              </div>
            </div>
          )}
        </section>

        <section className="card-dark lg:col-span-2">
          <div className="mb-4 flex items-center justify-between gap-2">
            <h2 className="text-xl font-bold text-[var(--fg-primary)]">Recent runs</h2>
            <button
              type="button"
              onClick={() => void loadRuns()}
              className="text-sm font-semibold text-[var(--accent)] hover:underline"
            >
              Refresh
            </button>
          </div>
          {listLoading ? (
            <p className="flex items-center gap-2 text-sm text-zinc-400">
              <FiLoader className="animate-spin" /> Loading…
            </p>
          ) : null}
          {listError ? (
            <p className="text-sm text-red-300" role="alert">
              {listError}
            </p>
          ) : null}
          {!listLoading && runs.length === 0 ? (
            <p className="flex items-center gap-2 text-sm text-zinc-500">
              <FiImage className="text-zinc-600" aria-hidden />
              No runs yet.
            </p>
          ) : null}
          <ul className="custom-scrollbar mt-3 max-h-96 space-y-2 overflow-y-auto">
            {runs.map((r) => (
              <li key={r.run_id} className="group relative">
                <Link
                  to={`/runs/${encodeURIComponent(r.run_id)}`}
                  className="block rounded-xl border border-zinc-700/60 bg-zinc-950/40 px-4 py-3 transition hover:border-zinc-600 hover:bg-zinc-900/50"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-cyan-300/90">{r.run_id}</span>
                    <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] font-bold uppercase text-zinc-300">
                      {r.status}
                    </span>
                  </div>
                  {r.project_name ? (
                    <p className="mt-1 text-sm font-medium text-zinc-200">{r.project_name}</p>
                  ) : null}
                  <p className="mt-1 text-xs text-zinc-500">
                    Images: {r.total_images ?? 0}
                    {r.updated_at ? ` · ${r.updated_at}` : ""}
                  </p>
                </Link>
                <button
                  type="button"
                  onClick={(e) => void handleDeleteRun(e, r.run_id)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-2 text-zinc-600 opacity-0 transition hover:bg-red-950/80 hover:text-red-400 group-hover:opacity-100"
                  aria-label="Delete run"
                >
                  <FiTrash2 size={16} />
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </AppShell>
  );
}
