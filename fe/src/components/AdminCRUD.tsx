import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "react-hot-toast";
import { Link } from "react-router-dom";
import { apiClient } from "../api/client";
import type { DefaultInput } from "../types/defaultInput";
import { toCdnUrl } from "../utils/cdn";
import { useImageUpload } from "../hooks/useImageUpload";
import { ImageLightboxModal } from "./ImageLightboxModal";

interface UploadedState {
  imageUrl: string;
  fileKey?: string;
}

const extractImageUrl = (item: DefaultInput): string => {
  return item.cdn_url ?? item.image_url ?? item.imageUrl ?? "";
};

const DEFAULTS_ENDPOINT = "api/defaults";

export function AdminCRUD() {
  const [items, setItems] = useState<DefaultInput[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploaded, setUploaded] = useState<UploadedState | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);

  const { uploadImage, isUploading, uploadError, progress, resetUploadState } =
    useImageUpload();

  const loadItems = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.get<
        DefaultInput[] | { items: DefaultInput[] }
      >(DEFAULTS_ENDPOINT);
      const data = Array.isArray(response.data)
        ? response.data
        : response.data.items;
      setItems(data ?? []);
    } catch (err) {
      const message = axios.isAxiosError(err)
        ? (err.response?.data?.detail ?? err.message)
        : "Failed to fetch default inputs.";
      setError(
        typeof message === "string"
          ? message
          : "Failed to fetch default inputs.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadItems();
  }, []);

  const resetForm = () => {
    setSelectedFile(null);
    setUploaded(null);
    resetUploadState();
  };

  const handleUploadAndSave = async () => {
    if (!selectedFile) {
      const message = "Please select an image to upload.";
      setError(message);
      toast.error(message);
      return;
    }

    setSubmitting(true);
    setError(null);
    const toastId = toast.loading("Uploading and creating...");

    try {
      const uploadResult = await uploadImage(selectedFile, "default");
      const payload = {
        image_url: uploadResult.cdnUrl || uploadResult.fileUrl,
        file_key: uploadResult.fileKey,
      };

      await apiClient.post(DEFAULTS_ENDPOINT, payload);

      setUploaded({
        imageUrl: payload.image_url,
        fileKey: payload.file_key,
      });
      await loadItems();
      resetForm();
      toast.success("Default image uploaded successfully.", { id: toastId });
    } catch (err) {
      const message = axios.isAxiosError(err)
        ? (err.response?.data?.detail ?? err.message)
        : "Failed to save default input.";
      const normalized =
        typeof message === "string" ? message : "Failed to save default input.";
      setError(normalized);
      toast.error(normalized, { id: toastId });
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: string | number) => {
    setError(null);
    try {
      await apiClient.delete(`${DEFAULTS_ENDPOINT}/${id}`);
      setItems((prev) => prev.filter((item) => item.id !== id));
      toast.success("Default input deleted.");
    } catch (err) {
      const message = axios.isAxiosError(err)
        ? (err.response?.data?.detail ?? err.message)
        : "Failed to delete default input.";
      const normalized =
        typeof message === "string"
          ? message
          : "Failed to delete default input.";
      setError(normalized);
      toast.error(normalized);
    }
  };

  return (
    <section className="min-h-screen bg-linear-to-br from-gray-50 to-gray-100 text-gray-800">
      <div className="container mx-auto space-y-6 p-4 sm:p-6 lg:p-8">
        <header className="mb-2">
          <h1 className="text-gradient from-blue-600 to-indigo-500 text-4xl font-extrabold sm:text-5xl">
            Admin Dashboard
          </h1>
          <p className="mt-2 text-sm text-gray-500 sm:text-base">
            Manage default gallery inputs used across the app.
          </p>
        </header>

        <div className="card">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-2xl font-bold text-gray-700">
              Admin CRUD: default_inputs
            </h2>
            <Link
              to="/"
              className="btn border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:border-gray-400 hover:bg-gray-100/80 focus:ring-gray-300/60"
            >
              Back to Home
            </Link>
          </div>
          <p className="mt-1 text-sm text-gray-500">
            Create, replace, or remove default gallery images.
          </p>

          <div className="mt-5 grid gap-4">
            <div className="grid gap-3">
              <input
                type="file"
                accept="image/*"
                onChange={(event) => {
                  setSelectedFile(event.target.files?.[0] ?? null);
                  setUploaded(null);
                  resetUploadState();
                }}
                className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 shadow-xs transition-colors focus:border-blue-400 focus:outline-none"
              />
            </div>

            {isUploading && (
              <p className="rounded-lg border border-blue-200 bg-blue-50/90 px-3 py-2 text-sm text-blue-700">
                Upload progress: {progress}%
              </p>
            )}
            {uploadError && (
              <p className="rounded-lg border border-red-200 bg-red-50/90 px-3 py-2 text-sm text-red-700">
                {uploadError}
              </p>
            )}
            {uploaded?.imageUrl && (
              <div className="rounded-xl border border-emerald-200/80 bg-emerald-50/70 p-3">
                <p className="mb-2 text-sm font-medium text-emerald-700">
                  Uploaded image ready
                </p>
                <img
                  src={uploaded.imageUrl}
                  alt="Uploaded"
                  className="h-40 w-full rounded-md object-cover sm:w-72"
                />
              </div>
            )}

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void handleUploadAndSave()}
                disabled={submitting || isUploading || !selectedFile}
                className="btn btn-primary px-4 py-2 text-sm disabled:opacity-70"
              >
                {submitting || isUploading ? "Uploading..." : "Upload"}
              </button>
              <button
                type="button"
                onClick={resetForm}
                className="btn border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:border-gray-400 hover:bg-gray-100/80 focus:ring-gray-300/60"
              >
                Reset
              </button>
            </div>
          </div>
        </div>

        <div className="card">
          <h3 className="text-xl font-bold text-gray-700">Current Inputs</h3>

          {loading && (
            <p className="mt-4 rounded-lg border border-blue-200 bg-blue-50/90 p-3 text-blue-700">
              Loading default inputs...
            </p>
          )}
          {error && (
            <p className="mt-4 rounded-lg border border-red-200 bg-red-50/90 p-3 text-red-700">
              {error}
            </p>
          )}

          {!loading && (
            <div className="mt-4 overflow-x-auto rounded-xl border border-gray-200/80 bg-white/70">
              <table className="min-w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-gray-600">
                    <th className="px-3 py-2 font-semibold">No</th>
                    <th className="px-3 py-2 font-semibold">Image</th>
                    <th className="px-3 py-2 font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, index) => {
                    const imageUrl = toCdnUrl(extractImageUrl(item));
                    return (
                      <tr
                        key={item.id}
                        className="border-b border-gray-100/80 last:border-b-0"
                      >
                        <td className="px-3 py-2 text-gray-500">{index + 1}</td>
                        <td className="px-3 py-2">
                          {imageUrl ? (
                            <img
                              src={imageUrl}
                              alt="Default input"
                              className="h-14 w-20 cursor-pointer rounded object-cover transition-all hover:ring-2 hover:ring-blue-400"
                              onClick={() => {
                                setPreviewSrc(imageUrl);
                                setPreviewOpen(true);
                              }}
                            />
                          ) : (
                            <span className="text-gray-400">No image</span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => void handleDelete(item.id)}
                              className="btn rounded bg-rose-600 px-3 py-1.5 font-semibold text-white hover:bg-rose-700 focus:ring-rose-300/60"
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}

                  {items.length === 0 && (
                    <tr>
                      <td
                        className="px-3 py-4 text-center text-gray-500"
                        colSpan={3}
                      >
                        No default inputs found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <ImageLightboxModal
          isOpen={previewOpen}
          imageSrc={previewSrc}
          alt="Default input preview"
          onClose={() => {
            setPreviewOpen(false);
            setPreviewSrc(null);
          }}
        />
      </div>
    </section>
  );
}
