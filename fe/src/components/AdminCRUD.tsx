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
    <section className="space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-2xl font-bold text-slate-800">
            Admin CRUD: default_inputs
          </h2>
          <Link
            to="/"
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:-translate-y-px hover:border-slate-400 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300 active:translate-y-0"
          >
            Back to Home
          </Link>
        </div>
        <p className="mt-1 text-sm text-slate-600">
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
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>

          {isUploading && (
            <p className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700">
              Upload progress: {progress}%
            </p>
          )}
          {uploadError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
              {uploadError}
            </p>
          )}
          {uploaded?.imageUrl && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
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
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:-translate-y-px hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 active:translate-y-0 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {submitting || isUploading ? "Uploading..." : "Upload"}
            </button>
            <button
              type="button"
              onClick={resetForm}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:-translate-y-px hover:border-slate-400 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300 active:translate-y-0"
            >
              Reset
            </button>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-xl font-bold text-slate-800">Current Inputs</h3>

        {loading && (
          <p className="mt-4 rounded-lg bg-blue-50 p-3 text-blue-700">
            Loading default inputs...
          </p>
        )}
        {error && (
          <p className="mt-4 rounded-lg bg-red-50 p-3 text-red-700">{error}</p>
        )}

        {!loading && (
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-600">
                  <th className="px-3 py-2">No</th>
                  <th className="px-3 py-2">Image</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, index) => {
                  const imageUrl = toCdnUrl(extractImageUrl(item));
                  return (
                    <tr key={item.id} className="border-b border-slate-100">
                      <td className="px-3 py-2 text-slate-500">{index + 1}</td>
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
                          <span className="text-slate-400">No image</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => void handleDelete(item.id)}
                            className="rounded bg-rose-600 px-3 py-1.5 font-semibold text-white transition hover:-translate-y-px hover:bg-rose-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300 active:translate-y-0"
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
                      className="px-3 py-4 text-center text-slate-500"
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
    </section>
  );
}
