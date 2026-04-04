import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { apiClient } from "../api/client";
import type { DefaultInput } from "../types/defaultInput";
import { toCdnUrl } from "../utils/cdn";
import { useImageUpload } from "../hooks/useImageUpload";

interface FormState {
  title: string;
}

interface UploadedState {
  imageUrl: string;
  fileKey?: string;
}

const extractImageUrl = (item: DefaultInput): string => {
  return item.cdn_url ?? item.image_url ?? item.imageUrl ?? "";
};

export function AdminCRUD() {
  const [items, setItems] = useState<DefaultInput[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>({ title: "" });
  const [editingId, setEditingId] = useState<number | string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploaded, setUploaded] = useState<UploadedState | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { uploadImage, isUploading, uploadError, progress, resetUploadState } =
    useImageUpload();

  const isEditing = useMemo(() => editingId !== null, [editingId]);

  const loadItems = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.get<
        DefaultInput[] | { items: DefaultInput[] }
      >("/api/defaults");
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
    setForm({ title: "" });
    setEditingId(null);
    setSelectedFile(null);
    setUploaded(null);
    resetUploadState();
  };

  const handleUploadForForm = async () => {
    if (!selectedFile) {
      return;
    }

    const result = await uploadImage(selectedFile);
    setUploaded({
      imageUrl: result.cdnUrl || result.fileUrl,
      fileKey: result.fileKey,
    });
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!form.title.trim()) {
      setError("Title is required.");
      return;
    }

    if (!uploaded?.imageUrl && !isEditing) {
      setError("Please upload an image to B2 before creating a record.");
      return;
    }

    setSubmitting(true);
    setError(null);

    const payload = {
      title: form.title.trim(),
      image_url: uploaded?.imageUrl,
      file_key: uploaded?.fileKey,
    };

    try {
      if (isEditing && editingId !== null) {
        await apiClient.put(`/api/defaults/${editingId}`, payload);
      } else {
        await apiClient.post("/api/defaults", payload);
      }
      await loadItems();
      resetForm();
    } catch (err) {
      const message = axios.isAxiosError(err)
        ? (err.response?.data?.detail ?? err.message)
        : "Failed to save default input.";
      setError(
        typeof message === "string" ? message : "Failed to save default input.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const startEdit = (item: DefaultInput) => {
    setEditingId(item.id);
    setForm({ title: item.title });
    const imageUrl = toCdnUrl(extractImageUrl(item));
    setUploaded({ imageUrl, fileKey: item.file_key ?? item.b2_key });
    setSelectedFile(null);
    resetUploadState();
  };

  const handleDelete = async (id: string | number) => {
    setError(null);
    try {
      await apiClient.delete(`/api/defaults/${id}`);
      setItems((prev) => prev.filter((item) => item.id !== id));
      if (editingId === id) {
        resetForm();
      }
    } catch (err) {
      const message = axios.isAxiosError(err)
        ? (err.response?.data?.detail ?? err.message)
        : "Failed to delete default input.";
      setError(
        typeof message === "string"
          ? message
          : "Failed to delete default input.",
      );
    }
  };

  return (
    <section className="space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-2xl font-bold text-slate-800">
          Admin CRUD: default_inputs
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Create, edit, or remove default gallery entries.
        </p>

        <form className="mt-5 grid gap-4" onSubmit={handleSubmit}>
          <label className="grid gap-1">
            <span className="text-sm font-medium text-slate-700">Title</span>
            <input
              value={form.title}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, title: event.target.value }))
              }
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              placeholder="Landing Page Hero"
            />
          </label>

          <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
            <input
              type="file"
              accept="image/*"
              onChange={(event) => {
                setSelectedFile(event.target.files?.[0] ?? null);
                resetUploadState();
              }}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <button
              type="button"
              onClick={() => void handleUploadForForm()}
              disabled={!selectedFile || isUploading}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {isUploading ? "Uploading..." : "Upload Image"}
            </button>
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
              type="submit"
              disabled={submitting || isUploading}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {submitting ? "Saving..." : isEditing ? "Update" : "Create"}
            </button>
            <button
              type="button"
              onClick={resetForm}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700"
            >
              Reset
            </button>
          </div>
        </form>
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
                  <th className="px-3 py-2">ID</th>
                  <th className="px-3 py-2">Title</th>
                  <th className="px-3 py-2">Image</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const imageUrl = toCdnUrl(extractImageUrl(item));
                  return (
                    <tr key={item.id} className="border-b border-slate-100">
                      <td className="px-3 py-2 text-slate-500">{item.id}</td>
                      <td className="px-3 py-2 font-medium text-slate-800">
                        {item.title}
                      </td>
                      <td className="px-3 py-2">
                        {imageUrl ? (
                          <img
                            src={imageUrl}
                            alt={item.title}
                            className="h-14 w-20 rounded object-cover"
                          />
                        ) : (
                          <span className="text-slate-400">No image</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => startEdit(item)}
                            className="rounded bg-amber-400 px-3 py-1.5 font-semibold text-slate-900 hover:bg-amber-300"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleDelete(item.id)}
                            className="rounded bg-rose-600 px-3 py-1.5 font-semibold text-white hover:bg-rose-700"
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
                      colSpan={4}
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
    </section>
  );
}
