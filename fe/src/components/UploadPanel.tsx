import type { ChangeEvent } from "react";
import { FiLoader, FiUploadCloud } from "react-icons/fi";

interface UploadPanelProps {
  file: File | null;
  selectedImageUrl: string | null;
  filePreview: string | null;
  isScenarioLoading: boolean;
  selectedPreviewLabel: string;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onGenerateScenariosClick: () => void;
  onOpenDefaultGallery: () => void;
  onOpenPreviewModal: () => void;
}

export function UploadPanel({
  file,
  selectedImageUrl,
  filePreview,
  isScenarioLoading,
  selectedPreviewLabel,
  onFileChange,
  onGenerateScenariosClick,
  onOpenDefaultGallery,
  onOpenPreviewModal,
}: UploadPanelProps) {
  const busy = isScenarioLoading;
  return (
    <div className="card">
      <h2 className="mb-4 flex items-center text-2xl font-bold text-gray-700">
        <FiUploadCloud className="mr-3 text-blue-500" />
        Screenshot → test scenarios
      </h2>
      <p className="mb-3 text-sm text-gray-500">
        <strong className="text-gray-600">Generate test scenarios</strong> produces structured
        scenarios from the screenshot using the configured vision model.
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
            type="button"
            onClick={onGenerateScenariosClick}
            disabled={busy || (!file && !selectedImageUrl)}
            className="btn border border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700"
          >
            {isScenarioLoading ? (
              <FiLoader className="-ml-1 mr-2 animate-spin" />
            ) : null}
            {isScenarioLoading ? "Generating scenarios..." : "Generate scenarios"}
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
