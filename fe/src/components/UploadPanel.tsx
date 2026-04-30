import type { ChangeEvent } from "react";
import { FiLoader, FiUploadCloud } from "react-icons/fi";

interface UploadPanelProps {
  file: File | null;
  selectedImageUrl: string | null;
  filePreview: string | null;
  isLoading: boolean;
  isBddLoading: boolean;
  isBddRankedLoading: boolean;
  selectedPreviewLabel: string;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onAnalyzeClick: () => void;
  onBddClick: () => void;
  onBddRankedClick: () => void;
  onOpenDefaultGallery: () => void;
  onOpenPreviewModal: () => void;
}

export function UploadPanel({
  file,
  selectedImageUrl,
  filePreview,
  isLoading,
  isBddLoading,
  isBddRankedLoading,
  selectedPreviewLabel,
  onFileChange,
  onAnalyzeClick,
  onBddClick,
  onBddRankedClick,
  onOpenDefaultGallery,
  onOpenPreviewModal,
}: UploadPanelProps) {
  const busy = isLoading || isBddLoading || isBddRankedLoading;
  return (
    <div className="card">
      <h2 className="mb-4 flex items-center text-2xl font-bold text-gray-700">
        <FiUploadCloud className="mr-3 text-blue-500" />
        Screenshot: Analyze & BDD
      </h2>
      <p className="mb-3 text-sm text-gray-500">
        <strong className="text-gray-600">Analyze</strong> returns ranked
        scenarios from the vision pipeline.{" "}
        <strong className="text-gray-600">Generate BDD</strong> returns
        happy-path Gherkin in model order.{" "}
        <strong className="text-gray-600">Generate BDD (ranked)</strong> runs
        the same generation, then a follow-up step reorders scenarios using
        inferred <span className="italic">business intent</span>.
      </p>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <label className="file-input-label">
            <input
              type="file"
              accept="image/*"
              onChange={onFileChange}
              className="hidden"
            />
            <span className="truncate">
              {file ? file.name : "Choose a file..."}
            </span>
          </label>
          <button
            onClick={onAnalyzeClick}
            disabled={busy || (!file && !selectedImageUrl)}
            className="btn btn-primary"
          >
            {isLoading ? (
              <FiLoader className="-ml-1 mr-2 animate-spin" />
            ) : null}
            {isLoading ? "Analyzing..." : "Analyze"}
          </button>
          <button
            type="button"
            onClick={onBddClick}
            disabled={busy || (!file && !selectedImageUrl)}
            className="btn border border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700"
          >
            {isBddLoading ? (
              <FiLoader className="-ml-1 mr-2 animate-spin" />
            ) : null}
            {isBddLoading ? "Generating BDD..." : "Generate BDD"}
          </button>
          <button
            type="button"
            title="Second LLM pass reorders scenarios by business intent"
            onClick={onBddRankedClick}
            disabled={busy || (!file && !selectedImageUrl)}
            className="btn border border-teal-700 bg-teal-700 text-white hover:bg-teal-800"
          >
            {isBddRankedLoading ? (
              <FiLoader className="-ml-1 mr-2 animate-spin" />
            ) : null}
            {isBddRankedLoading ? "Ranking BDD..." : "Generate BDD (ranked)"}
          </button>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={onOpenDefaultGallery}
            className="btn bg-slate-700 px-4 py-2 text-sm text-white hover:bg-slate-800"
          >
            Choose Default Image
          </button>
        </div>

        <p className="text-xs font-medium text-gray-500">
          {selectedPreviewLabel}
        </p>
      </div>

      {filePreview && (
        <div className="mt-4">
          <p className="mb-2 text-sm font-medium text-gray-600">
            Selected image preview:
          </p>
          <img
            src={filePreview}
            alt="Selected preview"
            className="h-auto max-h-48 w-full max-w-xs cursor-pointer rounded-lg border border-gray-200 object-contain transition-all hover:ring-2 hover:ring-blue-400"
            onClick={onOpenPreviewModal}
          />
        </div>
      )}
    </div>
  );
}
