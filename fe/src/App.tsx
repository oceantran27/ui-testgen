import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { Toaster, toast } from "react-hot-toast";
import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { apiClient } from "./api/client";
import { toCdnUrl } from "./utils/cdn";
import { GalleryModal } from "./components/GalleryModal";
import { AdminCRUD } from "./components/AdminCRUD.tsx";
import { AnalysisResultDisplay } from "./components/AnalysisResultDisplay";
import { AnalysisHistoryPanel } from "./components/AnalysisHistoryPanel";
import { UploadPanel } from "./components/UploadPanel";
import { DebateFloatingBubble } from "./components/DebateFloatingBubble";
import { DebateTranscriptModal } from "./components/DebateTranscriptModal";
import { ImageLightboxModal } from "./components/ImageLightboxModal";
import { Error404Page } from "./components/Error404Page.tsx";
import type {
  AnalysisRecord,
  DebateEvent,
  DebateEventsPollResponse,
  DebateStreamStatus,
} from "./components/types";

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
  const [records, setRecords] = useState<AnalysisRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [historyModalOpen, setHistoryModalOpen] = useState(false);
  const [historyImageSrc, setHistoryImageSrc] = useState<string | null>(null);
  const [expandedRecordId, setExpandedRecordId] = useState<number | null>(null);
  const [selectedImageUrl, setSelectedImageUrl] = useState<string | null>(null);
  const [debateRequestId, setDebateRequestId] = useState<string | null>(null);
  const [debateEvents, setDebateEvents] = useState<DebateEvent[]>([]);
  const [debateStreamStatus, setDebateStreamStatus] =
    useState<DebateStreamStatus>("idle");
  const [debatePollingError, setDebatePollingError] = useState<string | null>(
    null,
  );
  const [debateUnreadCount, setDebateUnreadCount] = useState(0);
  const [isDebateModalOpen, setIsDebateModalOpen] = useState(false);
  const [debatePollNonce, setDebatePollNonce] = useState(0);

  const debateNextSeqRef = useRef(0);
  const debateRetryRef = useRef(0);
  const debateModalOpenRef = useRef(false);

  const resetUploadState = useCallback(() => {
    // Keep compatibility with existing handlers that clear upload-related UX state.
  }, []);

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

  const startDebateStream = useCallback((requestId: string) => {
    setDebateRequestId(requestId);
    setDebateEvents([]);
    setDebateStreamStatus("running");
    setDebatePollingError(null);
    setDebateUnreadCount(0);
    debateNextSeqRef.current = 0;
    debateRetryRef.current = 0;
    setDebatePollNonce((value) => value + 1);
  }, []);

  const openDebateModal = useCallback(() => {
    setIsDebateModalOpen(true);
    setDebateUnreadCount(0);
  }, []);

  const retryDebatePolling = useCallback(() => {
    if (!debateRequestId) {
      return;
    }
    debateRetryRef.current = 0;
    setDebatePollingError(null);
    setDebateStreamStatus((current) =>
      current === "completed" || current === "failed" ? current : "running",
    );
    setDebatePollNonce((value) => value + 1);
  }, [debateRequestId]);

  useEffect(() => {
    debateModalOpenRef.current = isDebateModalOpen;
    if (isDebateModalOpen) {
      setDebateUnreadCount(0);
    }
  }, [isDebateModalOpen]);

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
        resetUploadState();
        toast.success("Image pasted!");
        break;
      }
    };

    window.addEventListener("paste", handlePaste);
    return () => {
      window.removeEventListener("paste", handlePaste);
    };
  }, [filePreview, resetUploadState]);

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

  useEffect(() => {
    if (!debateRequestId) {
      return;
    }

    let isCancelled = false;
    let timerId: number | null = null;

    const scheduleNext = (delayMs: number) => {
      timerId = window.setTimeout(() => {
        void pollDebateEvents();
      }, delayMs);
    };

    const pollDebateEvents = async () => {
      try {
        const response = await apiClient.get<DebateEventsPollResponse>(
          `debate-events/${encodeURIComponent(debateRequestId)}`,
          {
            params: {
              since_seq: debateNextSeqRef.current,
              limit: 120,
            },
          },
        );

        if (isCancelled) {
          return;
        }

        const payload = response.data;
        const incoming = Array.isArray(payload.events) ? payload.events : [];

        if (incoming.length > 0) {
          setDebateEvents((previous) => {
            const seen = new Set(previous.map((event) => event.sequence));
            const merged = [...previous];

            for (const event of incoming) {
              if (seen.has(event.sequence)) {
                continue;
              }
              merged.push(event);
              seen.add(event.sequence);
            }

            merged.sort((left, right) => left.sequence - right.sequence);
            return merged;
          });

          if (!debateModalOpenRef.current) {
            setDebateUnreadCount((count) => count + incoming.length);
          }
        }

        if (Number.isFinite(payload.next_seq)) {
          debateNextSeqRef.current = payload.next_seq;
        }

        debateRetryRef.current = 0;
        setDebatePollingError(null);

        if (payload.completed) {
          const terminalStatus =
            String(payload.status).toLowerCase() === "failed"
              ? "failed"
              : "completed";
          setDebateStreamStatus(terminalStatus);
          return;
        }

        setDebateStreamStatus("running");
        scheduleNext(1200);
      } catch (error) {
        if (isCancelled) {
          return;
        }

        if (axios.isAxiosError(error) && error.response?.status === 404) {
          setDebateStreamStatus("expired");
          setDebatePollingError(
            "Debate stream was not found or already expired.",
          );
          return;
        }

        debateRetryRef.current += 1;
        const delayMs = Math.min(5000, 1000 + debateRetryRef.current * 700);
        setDebateStreamStatus("error");
        setDebatePollingError(extractErrorMessage(error));
        scheduleNext(delayMs);
      }
    };

    void pollDebateEvents();

    return () => {
      isCancelled = true;
      if (timerId !== null) {
        window.clearTimeout(timerId);
      }
    };
  }, [debatePollNonce, debateRequestId, extractErrorMessage]);

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
      resetUploadState();
      return;
    }

    setFile(null);
    setFilePreview(null);
    setSelectedImageUrl(null);
  };

  const analyzeByImageUrl = async (imageUrl: string, fileKey?: string) => {
    const toastId = toast.loading("Analyzing screenshot...");
    const requestId = createCorrelationId("req");
    const batchId = createCorrelationId("batch");

    startDebateStream(requestId);
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
      setDebateStreamStatus("failed");
      notifyAndRedirectError(err, toastId);
    } finally {
      setIsLoading(false);
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

    startDebateStream(requestId);

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
      setDebateStreamStatus("failed");
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

  const showDebateBubble = useMemo(() => {
    if (!debateRequestId) {
      return false;
    }
    return (
      isLoading || debateEvents.length > 0 || debateStreamStatus !== "idle"
    );
  }, [debateEvents.length, debateRequestId, debateStreamStatus, isLoading]);

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
            <div className="mt-4">
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
                selectedPreviewLabel={selectedPreviewLabel}
                onFileChange={handleFileChange}
                onAnalyzeClick={() => void handleAnalyzeClick()}
                onOpenDefaultGallery={() => setIsDefaultGalleryOpen(true)}
                onOpenPreviewModal={() => setIsModalOpen(true)}
              />

              {analysisResult && (
                <AnalysisResultDisplay result={analysisResult} />
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

      <DebateFloatingBubble
        visible={showDebateBubble}
        status={debateStreamStatus}
        eventCount={debateEvents.length}
        unreadCount={debateUnreadCount}
        onOpen={openDebateModal}
      />

      <DebateTranscriptModal
        isOpen={isDebateModalOpen}
        requestId={debateRequestId}
        status={debateStreamStatus}
        events={debateEvents}
        errorMessage={debatePollingError}
        onClose={() => setIsDebateModalOpen(false)}
        onRetry={retryDebatePolling}
      />

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
        <Route path="/admin" element={<AdminCRUD />} />
        <Route path="/404" element={<Error404Page />} />
        <Route path="*" element={<Navigate to="/404" replace />} />
      </Routes>
    </>
  );
}

export default App;
