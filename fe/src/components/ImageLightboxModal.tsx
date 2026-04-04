import { FiX } from "react-icons/fi";

interface ImageLightboxModalProps {
  isOpen: boolean;
  imageSrc: string | null;
  alt: string;
  onClose: () => void;
}

export function ImageLightboxModal({
  isOpen,
  imageSrc,
  alt,
  onClose,
}: ImageLightboxModalProps) {
  if (!isOpen || !imageSrc) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <button
        className="absolute right-4 top-4 text-3xl text-white hover:text-gray-300"
        onClick={onClose}
      >
        <FiX />
      </button>
      <img
        src={imageSrc}
        alt={alt}
        className="max-h-[90vh] max-w-[90vw] rounded-lg object-contain shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}
