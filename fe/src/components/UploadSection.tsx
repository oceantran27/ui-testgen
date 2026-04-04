import { useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { useImageUpload } from "../hooks/useImageUpload";

interface UploadSectionProps {
  selectedImage: string | null;
  onSelectedImage: (url: string) => void;
  onOpenGallery: () => void;
  onAnalyze: (url: string) => Promise<void>;
  isAnalyzing: boolean;
}

export function UploadSection({
  selectedImage,
  onSelectedImage,
  onOpenGallery,
  onAnalyze,
  isAnalyzing,
}: UploadSectionProps) {
  const [localFile, setLocalFile] = useState<File | null>(null);
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  const { uploadImage, isUploading, uploadError, progress, resetUploadState } =
    useImageUpload();

  const canUpload = useMemo(
    () => !!localFile && !isUploading,
    [localFile, isUploading],
  );
  const canAnalyze = useMemo(
    () => !!selectedImage && !isAnalyzing,
    [selectedImage, isAnalyzing],
  );

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0] ?? null;
    setLocalFile(nextFile);
    resetUploadState();

    if (localPreview) {
      URL.revokeObjectURL(localPreview);
    }

    setLocalPreview(nextFile ? URL.createObjectURL(nextFile) : null);
  };

  const handleUpload = async () => {
    if (!localFile) {
      return;
    }

    const result = await uploadImage(localFile);
    onSelectedImage(result.cdnUrl || result.fileUrl);
  };

  const handleAnalyze = async () => {
    if (!selectedImage) {
      return;
    }
    await onAnalyze(selectedImage);
  };

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="mb-1 text-2xl font-bold text-slate-800">Image Input</h2>
      <p className="mb-5 text-sm text-slate-600">
        Upload an image to B2 or pick one from defaults, then run analysis.
      </p>

      <div className="grid gap-4 sm:grid-cols-[1fr_auto_auto]">
        <input
          type="file"
          accept="image/*"
          onChange={onFileChange}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
        <button
          type="button"
          onClick={() => void handleUpload()}
          disabled={!canUpload}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {isUploading ? "Uploading..." : "Upload to B2"}
        </button>
        <button
          type="button"
          onClick={onOpenGallery}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-700"
        >
          Open Gallery
        </button>
      </div>

      {isUploading && (
        <p className="mt-3 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700">
          Upload progress: {progress}%
        </p>
      )}
      {uploadError && (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {uploadError}
        </p>
      )}

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
          <p className="mb-2 text-sm font-medium text-slate-600">
            Local preview
          </p>
          {localPreview ? (
            <img
              src={localPreview}
              alt="Local preview"
              className="h-48 w-full rounded-lg object-cover"
            />
          ) : (
            <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-slate-300 text-sm text-slate-500">
              Select a file to preview
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
          <p className="mb-2 text-sm font-medium text-slate-600">
            Selected image (global state)
          </p>
          {selectedImage ? (
            <img
              src={selectedImage}
              alt="Selected"
              className="h-48 w-full rounded-lg object-cover"
            />
          ) : (
            <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-slate-300 text-sm text-slate-500">
              Upload or choose from gallery
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={() => void handleAnalyze()}
          disabled={!canAnalyze}
          className="rounded-lg bg-amber-500 px-5 py-2.5 text-sm font-semibold text-slate-900 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
        >
          {isAnalyzing ? "Analyzing..." : "Analyze Selected Image"}
        </button>
      </div>
    </section>
  );
}
