import { useCallback, useEffect, useState } from "react";
import { FiChevronLeft, FiChevronRight, FiX } from "react-icons/fi";

export interface FlowLightboxModalProps {
  isOpen: boolean;
  images: string[];
  startIndex: number;
  flowTitle: string;
  onClose: () => void;
}

export function FlowLightboxModal({
  isOpen,
  images,
  startIndex,
  flowTitle,
  onClose,
}: FlowLightboxModalProps) {
  const [index, setIndex] = useState(startIndex);

  useEffect(() => {
    if (isOpen) {
      setIndex(Math.min(startIndex, Math.max(0, images.length - 1)));
    }
  }, [isOpen, startIndex, images.length]);

  const go = useCallback(
    (dir: -1 | 1) => {
      setIndex((i) => {
        const n = i + dir;
        if (n < 0) {
          return 0;
        }
        if (n >= images.length) {
          return images.length - 1;
        }
        return n;
      });
    },
    [images.length],
  );

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowLeft") {
        go(-1);
      } else if (e.key === "ArrowRight") {
        go(1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [isOpen, onClose, go]);

  if (!isOpen || images.length === 0) {
    return null;
  }

  const current = images[index];
  if (!current) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <button
        type="button"
        className="absolute right-4 top-4 z-10 text-3xl text-white/90 hover:text-white"
        onClick={onClose}
        aria-label="Close"
      >
        <FiX />
      </button>
      {images.length > 1 ? (
        <button
          type="button"
          className="absolute left-2 top-1/2 z-10 -translate-y-1/2 rounded-full bg-white/10 p-3 text-white hover:bg-white/20 disabled:opacity-30 sm:left-4"
          onClick={(e) => {
            e.stopPropagation();
            go(-1);
          }}
          disabled={index <= 0}
          aria-label="Previous"
        >
          <FiChevronLeft className="h-8 w-8" />
        </button>
      ) : null}
      {images.length > 1 ? (
        <button
          type="button"
          className="absolute right-2 top-1/2 z-10 -translate-y-1/2 rounded-full bg-white/10 p-3 text-white hover:bg-white/20 disabled:opacity-30 sm:right-4"
          onClick={(e) => {
            e.stopPropagation();
            go(1);
          }}
          disabled={index >= images.length - 1}
          aria-label="Next"
        >
          <FiChevronRight className="h-8 w-8" />
        </button>
      ) : null}
      <div
        className="max-h-[90vh] max-w-[95vw] text-center"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="mb-2 text-sm text-white/80">
          {flowTitle} — {index + 1} / {images.length}
        </p>
        <img
          src={current}
          alt={`${flowTitle} ${index + 1}`}
          className="max-h-[85vh] max-w-full rounded-lg object-contain shadow-2xl"
        />
      </div>
    </div>
  );
}
