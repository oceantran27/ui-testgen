import { useState, useEffect } from "react";
import { Toaster, toast } from "react-hot-toast";
import {
  FiUploadCloud,
  FiTrash2,
  FiLoader,
  FiImage,
  FiChevronDown,
  FiServer,
  FiX,
} from "react-icons/fi";

const API_BASE_URL = "/api/v1";

// Define types for our data
interface AnalysisScenario {
  [key: string]: unknown;
}

interface AnalysisResponse {
  scenario: AnalysisScenario;
}

interface AnalysisRecord {
  id: number;
  image_path: string;
  scenario_json: string;
  created_at: string;
}

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [filePreview, setFilePreview] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<AnalysisScenario | null>(
    null,
  );
  const [records, setRecords] = useState<AnalysisRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [historyModalOpen, setHistoryModalOpen] = useState(false);
  const [historyImageSrc, setHistoryImageSrc] = useState<string | null>(null);

  useEffect(() => {
    fetchRecords();
  }, []);

  // Clean up object URL on component unmount
  useEffect(() => {
    return () => {
      if (filePreview) {
        URL.revokeObjectURL(filePreview);
      }
    };
  }, [filePreview]);

  const fetchRecords = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/records`);
      if (!response.ok) {
        throw new Error("Failed to fetch records.");
      }
      const data: AnalysisRecord[] = await response.json();
      setRecords(
        data.sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
        ),
      );
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "An unknown error occurred.";
      toast.error(message);
    }
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (filePreview) {
      URL.revokeObjectURL(filePreview);
    }

    if (event.target.files && event.target.files.length > 0) {
      const newFile = event.target.files[0];
      setFile(newFile);
      setFilePreview(URL.createObjectURL(newFile));
      setAnalysisResult(null);
    } else {
      setFile(null);
      setFilePreview(null);
    }
  };

  const handleAnalyzeClick = async () => {
    if (!file) {
      toast.error("Please select a file to analyze.");
      return;
    }

    setIsLoading(true);
    setAnalysisResult(null);
    const toastId = toast.loading("Analyzing screenshot...");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${API_BASE_URL}/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Analysis failed.");
      }

      const result: AnalysisResponse = await response.json();
      setAnalysisResult(result.scenario);
      toast.success("Analysis complete!", { id: toastId });
      fetchRecords(); // Refresh records
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "An unknown error occurred.";
      toast.error(message, { id: toastId });
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
      const response = await fetch(`${API_BASE_URL}/records/${recordId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Failed to delete record.");
      }

      toast.success("Record deleted.", { id: toastId });
      if (historyImageSrc?.endsWith(record.image_path)) {
        setHistoryModalOpen(false);
        setHistoryImageSrc(null);
      }
      setRecords(records.filter((r) => r.id !== recordId));
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "An unknown error occurred.";
      toast.error(message, { id: toastId });
    }
  };

  return (
    <>
      <div className="min-h-screen text-gray-800 bg-gradient-to-br from-gray-50 to-gray-100">
        <Toaster
          position="top-center"
          reverseOrder={false}
          toastOptions={{
            className:
              "bg-white/80 backdrop-blur-sm border border-gray-200/80 shadow-lg rounded-xl",
            style: {
              color: "#333",
            },
          }}
        />
        <div className="container mx-auto p-4 sm:p-6 lg:p-8">
          <header className="text-center mb-12">
            <h1 className="text-5xl sm:text-6xl font-extrabold text-gradient from-blue-600 to-indigo-500">
              UI TestGen
            </h1>
            <p className="text-gray-500 mt-3 text-lg">
              Generate UI test scenarios from screenshots using AI
            </p>
          </header>

          <main className="grid grid-cols-1 lg:grid-cols-5 gap-8">
            {/* Left Column */}
            <div className="lg:col-span-2 space-y-8">
              <div className="card">
                <h2 className="text-2xl font-bold text-gray-700 mb-4 flex items-center">
                  <FiUploadCloud className="mr-3 text-blue-500" />
                  Analyze New Screenshot
                </h2>
                <div className="flex items-center space-x-4">
                  <label className="file-input-label">
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleFileChange}
                      className="hidden"
                    />
                    <span className="truncate">
                      {file ? file.name : "Choose a file..."}
                    </span>
                  </label>
                  <button
                    onClick={handleAnalyzeClick}
                    disabled={isLoading || !file}
                    className="btn btn-primary"
                  >
                    {isLoading ? (
                      <FiLoader className="animate-spin -ml-1 mr-2" />
                    ) : null}
                    {isLoading ? "Analyzing..." : "Analyze"}
                  </button>
                </div>
                {filePreview && (
                  <div className="mt-4">
                    <p className="text-sm font-medium text-gray-600 mb-2">
                      Selected image preview:
                    </p>
                    <img
                      src={filePreview}
                      alt="Selected preview"
                      className="w-full h-auto max-w-xs max-h-48 object-contain rounded-lg border border-gray-200 cursor-pointer hover:ring-2 hover:ring-blue-400 transition-all"
                      onClick={() => setIsModalOpen(true)}
                    />
                  </div>
                )}
              </div>

              {analysisResult && (
                <div className="card">
                  <h2 className="text-2xl font-bold text-gray-700 mb-4">
                    Analysis Result
                  </h2>
                  <pre className="bg-gray-100 p-4 rounded-lg text-sm overflow-x-auto custom-scrollbar">
                    {JSON.stringify(analysisResult, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Right Column (History) */}
            <div className="card lg:col-span-3 row-span-2">
              <h2 className="text-2xl font-bold text-gray-700 mb-4 flex items-center">
                <FiServer className="mr-3 text-blue-500" />
                Analysis History
              </h2>
              <div className="space-y-4 max-h-[75vh] overflow-y-auto pr-2 custom-scrollbar">
                {records.length === 0 && (
                  <div className="text-center text-gray-500 py-10">
                    <FiImage className="mx-auto text-4xl mb-2" />
                    <p>No analysis records found.</p>
                    <p className="text-sm">
                      Upload a screenshot to get started.
                    </p>
                  </div>
                )}
                {records.map((record) => (
                  <div
                    key={record.id}
                    className="group flex items-start space-x-4 p-4 rounded-xl bg-gray-50/80 border border-transparent hover:border-gray-200 transition-all"
                  >
                    <div className="w-24 h-16 flex-shrink-0 bg-gray-200 rounded-md cursor-pointer" onClick={() => handleHistoryImageClick(`/${record.image_path}`)}>
                      <img src={`/${record.image_path}`} alt={`Record ${record.id}`} className="w-full h-full object-cover rounded-md"/>
                    </div>
                    <div className="flex-1">
                      <p className="font-semibold text-gray-700">
                        Record ID: {record.id}
                      </p>
                      <p className="text-sm text-gray-500">
                        {new Date(record.created_at).toLocaleString()}
                      </p>
                      <details className="mt-2 text-sm">
                        <summary className="cursor-pointer font-medium text-blue-600 hover:underline flex items-center">
                          <FiChevronDown className="inline mr-1" /> View
                          Scenario
                        </summary>
                        <pre className="bg-gray-100 p-2 mt-2 rounded-md overflow-x-auto custom-scrollbar">
                          {JSON.stringify(
                            JSON.parse(record.scenario_json),
                            null,
                            2,
                          )}
                        </pre>
                      </details>
                    </div>
                    <button
                      onClick={() => handleDeleteRecord(record.id)}
                      className="text-gray-400 hover:text-red-500 hover:bg-red-100/50 p-2 rounded-full transition-all opacity-0 group-hover:opacity-100"
                      aria-label="Delete record"
                    >
                      <FiTrash2 size={18} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </main>
        </div>
      </div>
      {isModalOpen && filePreview && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm"
          onClick={() => setIsModalOpen(false)}
        >
          <button
            className="absolute top-4 right-4 text-white text-3xl hover:text-gray-300"
            onClick={() => setIsModalOpen(false)}
          >
            <FiX />
          </button>
          <img
            src={filePreview}
            alt="Selected screenshot"
            className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()} // Prevent closing modal when clicking on image
          />
        </div>
      )}
      {historyModalOpen && historyImageSrc && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm"
          onClick={() => setHistoryModalOpen(false)}
        >
          <button
            className="absolute top-4 right-4 text-white text-3xl hover:text-gray-300"
            onClick={() => setHistoryModalOpen(false)}
          >
            <FiX />
          </button>
          <img
            src={historyImageSrc}
            alt="History screenshot"
            className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()} // Prevent closing modal when clicking on image
          />
        </div>
      )}
    </>
  );
}

export default App;
