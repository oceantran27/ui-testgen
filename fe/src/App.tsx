import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Toaster, toast } from "react-hot-toast";
import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { apiClient } from "./api/client";
import {
  imageUrlToFile,
  postBddHappyPath,
  postBddHappyPathRanked,
} from "./api/bdd";
import { toCdnUrl } from "./utils/cdn";
import { GalleryModal } from "./components/GalleryModal";
import { AdminCRUD } from "./components/AdminCRUD.tsx";
import { AnalysisResultDisplay } from "./components/AnalysisResultDisplay";
import { AnalysisHistoryPanel } from "./components/AnalysisHistoryPanel";
import { UploadPanel } from "./components/UploadPanel";
import { ImageLightboxModal } from "./components/ImageLightboxModal";
import { Error404Page } from "./components/Error404Page.tsx";
import { BehaviorFlowPage } from "./components/BehaviorFlowPage";
import type { AnalysisRecord } from "./components/types";

const resolveImageSrc = (path: string): string => {
  if (
    /^(https?:)?\/\//i.test(path) ||
    path.startsWith("data:") ||
    path.startsWith("blob:")
  ) {
    return toCdnUrl(path);
  }
  return path.startsWith("/") ? path : `/${path}`;
};

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

function LegacyHome() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [filePreview, setFilePreview] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isDefaultGalleryOpen, setIsDefaultGalleryOpen] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<string | null>(null);
  const [bddResult, setBddResult] = useState<string | null>(null);
  const [records, setRecords] = useState<AnalysisRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isBddLoading, setIsBddLoading] = useState(false);
  const [isBddRankedLoading, setIsBddRankedLoading] = useState(false);
  const [historyModalOpen, setHistoryModalOpen] = useState(false);
  const [historyImageSrc, setHistoryImageSrc] = useState<string | null>(null);
  const [expandedRecordId, setExpandedRecordId] = useState<number | null>(null);
  const [selectedImageUrl, setSelectedImageUrl] = useState<string | null>(null);

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

  const redirectToErrorPage = useCallback(
    (errorMessage: string) => {
      navigate("/404", {
        replace: true,
        state: {
          errorMessage,
          at: new Date().toISOString(),
        },
      });
    },
    [navigate],
  );

  const notifyAndRedirectError = useCallback(
    (error: unknown, toastId?: string) => {
      const message = extractErrorMessage(error);
      toast.error(message, toastId ? { id: toastId } : undefined);
      redirectToErrorPage(message);
    },
    [extractErrorMessage, redirectToErrorPage],
  );

  const handleToggleExpand = (recordId: number) => {
    setExpandedRecordId(expandedRecordId === recordId ? null : recordId);
  };

  useEffect(() => {
    const handlePaste = (event: ClipboardEvent) => {
      const items = event.clipboardData?.items;
      if (!items) {
        return;
      }

      for (let i = 0; i < items.length; i += 1) {
        if (!items[i].type.includes("image")) {
          continue;
        }

        const blob = items[i].getAsFile();
        if (!blob) {
          break;
        }

        if (filePreview?.startsWith("blob:")) {
          URL.revokeObjectURL(filePreview);
        }

        const newFile = new File([blob], "pasted-image.png", {
          type: blob.type,
        });
        const localPreview = URL.createObjectURL(newFile);

        setFile(newFile);
        setFilePreview(localPreview);
        setSelectedImageUrl(null);
        setAnalysisResult(null);
        setBddResult(null);
        toast.success("Image pasted!");
        break;
      }
    };

    window.addEventListener("paste", handlePaste);
    return () => {
      window.removeEventListener("paste", handlePaste);
    };
  }, [filePreview]);

  useEffect(() => {
    return () => {
      if (filePreview?.startsWith("blob:")) {
        URL.revokeObjectURL(filePreview);
      }
    };
  }, [filePreview]);

  const fetchRecords = useCallback(
    async (options?: { showToast?: boolean }) => {
      const toastId = options?.showToast
        ? toast.loading("Loading records...")
        : undefined;
      try {
        const response = await apiClient.get<AnalysisRecord[]>("records");
        const data = response.data;
        setRecords(
          data.sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime(),
          ),
        );
        if (toastId) {
          toast.success("Loaded records successfully.", { id: toastId });
        }
      } catch (err) {
        notifyAndRedirectError(err, toastId);
      }
    },
    [notifyAndRedirectError],
  );

  useEffect(() => {
    void fetchRecords({ showToast: true });
  }, [fetchRecords]);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (filePreview?.startsWith("blob:")) {
      URL.revokeObjectURL(filePreview);
    }

    if (event.target.files && event.target.files.length > 0) {
      const newFile = event.target.files[0];
      const localPreview = URL.createObjectURL(newFile);

      setFile(newFile);
      setFilePreview(localPreview);
      setSelectedImageUrl(null);
      setAnalysisResult(null);
      setBddResult(null);
      return;
    }

    setFile(null);
    setFilePreview(null);
    setSelectedImageUrl(null);
    setAnalysisResult(null);
    setBddResult(null);
  };

  const analyzeByImageUrl = async (imageUrl: string, fileKey?: string) => {
    const toastId = toast.loading("Analyzing screenshot...");
    const requestId = createCorrelationId("req");
    const batchId = createCorrelationId("batch");

    setIsLoading(true);
    setAnalysisResult(null);

    try {
      const response = await apiClient.post(
        "api/analyze",
        {
          image_url: imageUrl,
          file_key: fileKey,
        },
        {
          headers: {
            "X-Request-Id": requestId,
            "X-Batch-Id": batchId,
          },
        },
      );
      const payload = response.data;
      const result =
        typeof payload === "string"
          ? payload
          : JSON.stringify(payload, null, 2);
      setAnalysisResult(result);
      toast.success("Analysis complete!", { id: toastId });
      void fetchRecords();
    } catch (err) {
      notifyAndRedirectError(err, toastId);
    } finally {
      setIsLoading(false);
    }
  };

  const handleBddClick = async () => {
    if (!file && !selectedImageUrl) {
      toast.error("Please select a screenshot (file or default image).");
      return;
    }

    const toastId = toast.loading("Generating BDD scenarios...");
    const requestId = createCorrelationId("req");
    const batchId = createCorrelationId("batch");

    setIsBddLoading(true);
    setBddResult(null);

    try {
      const fileToSend = file
        ? file
        : await imageUrlToFile(
            selectedImageUrl as string,
            "screenshot.jpg",
          );
      const data = await postBddHappyPath(fileToSend, {
        "X-Request-Id": requestId,
        "X-Batch-Id": batchId,
      });
      setBddResult(JSON.stringify(data, null, 2));
      toast.success("BDD scenarios ready.", { id: toastId });
      void fetchRecords();
    } catch (err) {
      notifyAndRedirectError(err, toastId);
    } finally {
      setIsBddLoading(false);
    }
  };

  const handleBddRankedClick = async () => {
    if (!file && !selectedImageUrl) {
      toast.error("Please select a screenshot (file or default image).");
      return;
    }

    const toastId = toast.loading("Generating ranked BDD...");
    const requestId = createCorrelationId("req");
    const batchId = createCorrelationId("batch");

    setIsBddRankedLoading(true);
    setBddResult(null);

    try {
      const fileToSend = file
        ? file
        : await imageUrlToFile(
            selectedImageUrl as string,
            "screenshot.jpg",
          );
      const data = await postBddHappyPathRanked(fileToSend, {
        "X-Request-Id": requestId,
        "X-Batch-Id": batchId,
      });
      setBddResult(JSON.stringify(data, null, 2));
      toast.success("Ranked BDD scenarios ready.", { id: toastId });
      void fetchRecords();
    } catch (err) {
      notifyAndRedirectError(err, toastId);
    } finally {
      setIsBddRankedLoading(false);
    }
  };

  const handleAnalyzeClick = async () => {
    if (selectedImageUrl) {
      await analyzeByImageUrl(selectedImageUrl);
      return;
    }

    if (!file) {
      toast.error("Please select a file to analyze.");
      return;
    }

    setIsLoading(true);
    setAnalysisResult(null);
    const toastId = toast.loading("Analyzing screenshot...");
    const requestId = createCorrelationId("req");
    const batchId = createCorrelationId("batch");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await apiClient.post<string>("analyze", formData, {
        headers: {
          "X-Request-Id": requestId,
          "X-Batch-Id": batchId,
        },
      });
      const payload = response.data;
      const result =
        typeof payload === "string"
          ? payload
          : JSON.stringify(payload, null, 2);
      setAnalysisResult(result);
      toast.success("Analysis complete!", { id: toastId });
      void fetchRecords();
    } catch (err) {
      notifyAndRedirectError(err, toastId);
    } finally {
      setIsLoading(false);
    }
  };

  const handleHistoryImageClick = (src: string) => {
    setHistoryImageSrc(src);
    setHistoryModalOpen(true);
  };

  const handleDeleteRecord = async (recordId: number) => {
    const toastId = toast.loading("Deleting record...");
    try {
      const recordToDelete = records.find((r) => r.id === recordId);
      if (!recordToDelete) {
        toast.error("Could not find record to delete.", { id: toastId });
        return;
      }

      await apiClient.delete(`records/${recordId}`);

      toast.success("Record deleted.", { id: toastId });

      if (historyImageSrc === resolveImageSrc(recordToDelete.image_path)) {
        setHistoryModalOpen(false);
        setHistoryImageSrc(null);
      }
      setRecords(records.filter((r) => r.id !== recordId));
    } catch (err) {
      notifyAndRedirectError(err, toastId);
    }
  };

  const selectedPreviewLabel = useMemo(() => {
    if (selectedImageUrl) {
      return "Selected source: B2/Gallery";
    }
    if (file) {
      return `Selected source: Local file (${file.name})`;
    }
    return "Selected source: none";
  }, [selectedImageUrl, file]);

  return (
    <>
      <div className="min-h-screen bg-linear-to-br from-gray-50 to-gray-100 text-gray-800">
        <div className="container mx-auto p-4 sm:p-6 lg:p-8">
          <header className="mb-12 text-center">
            <h1 className="text-gradient from-blue-600 to-indigo-500 text-5xl font-extrabold sm:text-6xl">
              UI TestGen
            </h1>
            <p className="mt-3 text-lg text-gray-500">
              Generate UI test scenarios from screenshots using AI
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-4">
              <Link
                className="font-semibold text-blue-600 hover:text-blue-800"
                to="/behavior-flows"
              >
                Behavior flow album
              </Link>
              <span className="text-gray-300" aria-hidden>
                |
              </span>
              <Link
                className="font-semibold text-blue-600 hover:text-blue-800"
                to="/admin"
              >
                Go to Admin Dashboard
              </Link>
            </div>
          </header>

          <main className="grid grid-cols-1 gap-8 lg:grid-cols-5">
            <div className="space-y-8 lg:col-span-2">
              <UploadPanel
                file={file}
                selectedImageUrl={selectedImageUrl}
                filePreview={filePreview}
                isLoading={isLoading}
                isBddLoading={isBddLoading}
                isBddRankedLoading={isBddRankedLoading}
                selectedPreviewLabel={selectedPreviewLabel}
                onFileChange={handleFileChange}
                onAnalyzeClick={() => void handleAnalyzeClick()}
                onBddClick={() => void handleBddClick()}
                onBddRankedClick={() => void handleBddRankedClick()}
                onOpenDefaultGallery={() => setIsDefaultGalleryOpen(true)}
                onOpenPreviewModal={() => setIsModalOpen(true)}
              />

              {analysisResult && (
                <AnalysisResultDisplay result={analysisResult} />
              )}

              {bddResult && (
                <AnalysisResultDisplay result={bddResult} />
              )}
            </div>

            <AnalysisHistoryPanel
              records={records}
              expandedRecordId={expandedRecordId}
              onToggleExpand={handleToggleExpand}
              onHistoryImageClick={handleHistoryImageClick}
              onDeleteRecord={(recordId) => void handleDeleteRecord(recordId)}
              resolveImageSrc={resolveImageSrc}
            />
          </main>
        </div>
      </div>

      <ImageLightboxModal
        isOpen={isModalOpen}
        imageSrc={filePreview}
        alt="Selected screenshot"
        onClose={() => setIsModalOpen(false)}
      />
      <ImageLightboxModal
        isOpen={historyModalOpen}
        imageSrc={historyImageSrc}
        alt="History screenshot"
        onClose={() => setHistoryModalOpen(false)}
      />

      <GalleryModal
        isOpen={isDefaultGalleryOpen}
        onClose={() => setIsDefaultGalleryOpen(false)}
        selectedImage={selectedImageUrl}
        onSelectImage={(url) => {
          setSelectedImageUrl(toCdnUrl(url));
          setFile(null);
          setFilePreview(toCdnUrl(url));
          setAnalysisResult(null);
          setBddResult(null);
        }}
        analyze={analyzeByImageUrl}
      />
    </>
  );
}

function App() {
  return (
    <>
      <Toaster
        position="top-center"
        reverseOrder={false}
        toastOptions={{
          className:
            "rounded-xl border border-gray-200/80 bg-white/80 shadow-lg backdrop-blur-sm",
          style: {
            color: "#333",
          },
        }}
      />
      <Routes>
        <Route path="/" element={<LegacyHome />} />
        <Route path="/behavior-flows" element={<BehaviorFlowPage />} />
        <Route path="/admin" element={<AdminCRUD />} />
        <Route path="/404" element={<Error404Page />} />
        <Route path="*" element={<Navigate to="/404" replace />} />
      </Routes>
    </>
  );
}

export default App;
