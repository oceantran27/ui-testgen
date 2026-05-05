import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { apiClient } from "../api/client";
import type { DefaultInput } from "../types/defaultInput";
import { toCdnUrl } from "../utils/cdn";

interface GalleryModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedImage: string | null;
  onSelectImage: (url: string) => void;
}

const extractImageUrl = (item: DefaultInput): string => {
  return item.cdn_url ?? item.image_url ?? item.imageUrl ?? "";
};

const DEFAULTS_ENDPOINT = "api/defaults";

const getImageLabel = (item: DefaultInput): string => {
  return item.file_key ?? item.b2_key ?? `Default input ${item.id}`;
};

export function GalleryModal({
  isOpen,
  onClose,
  selectedImage,
  onSelectImage,
}: GalleryModalProps) {
  const [items, setItems] = useState<DefaultInput[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const fetchDefaults = async () => {
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
          : "Failed to load default input gallery.";
        setError(
          typeof message === "string"
            ? message
            : "Failed to load default input gallery.",
        );
      } finally {
        setLoading(false);
      }
    };

    void fetchDefaults();
  }, [isOpen]);

  const cardItems = useMemo(
    () =>
      items.map((item) => {
        const imageUrl = toCdnUrl(extractImageUrl(item));
        return { item, imageUrl };
      }),
    [items],
  );

  const handleSelect = (url: string) => {
    onSelectImage(url);
    onClose();
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/70 p-4">
      <div className="w-full max-w-6xl rounded-2xl bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-2xl font-bold text-slate-800">
            Default Input Gallery
          </h2>
          <button
            type="button"
            className="rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-200"
            onClick={onClose}
          >
            Close
          </button>
        </div>

        {loading && (
          <p className="rounded-lg bg-blue-50 p-3 text-blue-700">
            Loading images...
          </p>
        )}
        {error && (
          <p className="rounded-lg bg-red-50 p-3 text-red-700">{error}</p>
        )}

        {!loading && !error && (
          <div className="grid max-h-[65vh] grid-cols-2 gap-4 overflow-auto sm:grid-cols-3 lg:grid-cols-4">
            {cardItems.map(({ item, imageUrl }) => (
              <button
                key={item.id}
                type="button"
                onClick={() => handleSelect(imageUrl)}
                className={`overflow-hidden rounded-xl border text-left transition ${
                  selectedImage === imageUrl
                    ? "border-amber-400 ring-2 ring-amber-200"
                    : "border-slate-200 hover:border-amber-300"
                }`}
              >
                <img
                  src={imageUrl}
                  alt={getImageLabel(item)}
                  className="h-36 w-full object-cover"
                />
                <div className="bg-slate-50 px-3 py-2">
                  <p className="truncate text-sm font-semibold text-slate-700">
                    {getImageLabel(item)}
                  </p>
                </div>
              </button>
            ))}

            {cardItems.length === 0 && (
              <p className="col-span-full rounded-lg bg-slate-50 p-4 text-center text-slate-600">
                No default inputs available.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
