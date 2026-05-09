import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { FiX } from "react-icons/fi";

function shortenId(id: string, n = 10): string {
  if (id.length <= n) {
    return id;
  }
  return `${id.slice(0, n)}…`;
}

type ScreenThumbnailProps = {
  src?: string;
  imageId: string;
  size?: "sm" | "md";
};

function ScreenImageLightbox({
  src,
  imageId,
  onClose,
}: {
  src: string;
  imageId: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prevOverflow;
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") {
        return;
      }
      e.preventDefault();
      e.stopImmediatePropagation();
      onClose();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/80 p-4 pt-14 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <button
        type="button"
        className="absolute right-4 top-4 z-[71] rounded-lg border border-zinc-600 bg-zinc-900/95 p-2 text-zinc-200 shadow-lg hover:bg-zinc-800"
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
        aria-label="Close preview"
      >
        <FiX className="size-6" aria-hidden />
      </button>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Screen preview ${shortenId(imageId, 20)}`}
        className="flex max-h-full max-w-full flex-col items-center gap-3"
      >
        <img
          src={src}
          alt=""
          className="max-h-[90vh] max-w-[min(96vw,1200px)] rounded-lg border border-zinc-700 object-contain shadow-2xl"
        />
        <p className="max-w-[min(96vw,1200px)] truncate font-mono text-xs text-zinc-400" title={imageId}>
          {shortenId(imageId, 48)}
        </p>
      </div>
    </div>,
    document.body,
  );
}

export function ScreenThumbnail({ src, imageId, size = "sm" }: ScreenThumbnailProps) {
  const [broken, setBroken] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const closePreview = useCallback(() => setPreviewOpen(false), []);

  const box =
    size === "md"
      ? "h-20 w-32 text-[10px]"
      : "h-14 w-24 text-[9px]";
  const maxChars = size === "md" ? 18 : 14;

  if (!src || broken) {
    return (
      <div
        className={`flex shrink-0 items-center justify-center overflow-hidden rounded border border-zinc-600 bg-zinc-900 px-1 ${box}`}
        title={imageId}
      >
        <span className="text-center font-mono leading-tight text-zinc-500">
          {shortenId(imageId, maxChars)}
        </span>
      </div>
    );
  }

  const imgHw = size === "md" ? "h-20 w-32" : "h-14 w-24";

  return (
    <>
      <button
        type="button"
        className={`${imgHw} shrink-0 cursor-pointer rounded border border-zinc-600 p-0 ring-offset-zinc-950 transition hover:border-cyan-500/50 hover:opacity-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 focus-visible:ring-offset-2`}
        aria-haspopup="dialog"
        aria-expanded={previewOpen}
        aria-label={`View larger: screen ${shortenId(imageId, 16)}`}
        title={imageId}
        onClick={(e) => {
          e.stopPropagation();
          setPreviewOpen(true);
        }}
      >
        <img
          src={src}
          alt=""
          aria-hidden
          className={`${imgHw} block rounded object-cover`}
          onError={() => setBroken(true)}
        />
      </button>
      {previewOpen ? (
        <ScreenImageLightbox src={src} imageId={imageId} onClose={closePreview} />
      ) : null}
    </>
  );
}
